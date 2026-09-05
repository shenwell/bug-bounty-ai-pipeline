"""Standoff365 Playwright scraper with auth and throttling."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from tenacity import retry, stop_after_attempt, wait_exponential

from portfolio.common.config import AppConfig
from portfolio.common.logging import get_logger
from portfolio.discovery.next_data_parser import extract_program_page_props, parse_tab_sections_from_next
from portfolio.guardrails.limits import RateLimiter

logger = get_logger(__name__)

AUTH_BASE = "https://auth.standoff365.com"

TAB_LABEL_MARKERS = (
    "описан",
    "description",
    "scope",
    "област",
    "правил",
    "rules",
    "вознаграж",
    "reward",
    "огранич",
    "restrict",
    "критер",
    "criteria",
    "принима",
    "accept",
    "уязвим",
    "vulnerab",
    "рейтинг",
    "ranking",
    "верси",
    "version",
)

PROGRAM_TAB_LABELS = (
    "Description",
    "Описание",
    "Vulnerabilities",
    "Уязвимости",
    "Ranking",
    "Рейтинг",
    "Versions",
    "Версии",
    "Scope",
    "Rewards",
    "Rules",
)


class SessionExpiredError(Exception):
    pass


class AuthBlockedError(Exception):
    """Login blocked (e.g. captcha) — use STF_SESSION cookie from a real browser session."""


class StandoffScraper:
    def __init__(self, config: AppConfig, rate_limiter: RateLimiter | None = None):
        self._config = config
        self._base = config.standoff.base_url.rstrip("/")
        self._rate = rate_limiter or RateLimiter(config.limits)
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> "StandoffScraper":
        pw = await async_playwright().start()
        self._browser = await pw.chromium.launch(headless=True)
        self._context = await self._browser.new_context()
        await self._authenticate()
        return self

    async def __aexit__(self, *args) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()

    async def _authenticate(self) -> None:
        assert self._context is not None
        cookie = self._config.standoff.session_cookie()
        if cookie:
            await self._context.add_cookies([
                {
                    "name": "sessionid",
                    "value": cookie,
                    "domain": ".standoff365.com",
                    "path": "/",
                }
            ])
            page = await self._context.new_page()
            await page.goto(f"{self._base}/programs/")
            if await self._is_logged_out(page):
                raise SessionExpiredError("STF_SESSION cookie expired or invalid")
            await page.close()
            logger.info("authenticated_via_cookie")
            return

        username = self._config.standoff.username()
        password = self._config.standoff.password()
        if not username or not password:
            raise ValueError("Set STF_SESSION or STF_USERNAME/STF_PASSWORD")

        return_url = f"{self._base}/programs/"
        login_url = (
            f"{AUTH_BASE}/en-US/account/login?return_url={quote(return_url, safe='')}"
        )
        page = await self._context.new_page()
        await page.goto(login_url, wait_until="networkidle", timeout=60000)
        await page.fill('input[name="username"]', username)
        await page.fill('input[name="password"]', password)
        submit = page.locator('button[type="submit"]')
        if not await submit.is_enabled():
            raise AuthBlockedError(
                "Login submit disabled (likely SmartCaptcha). "
                "Log in manually in the browser and set STF_SESSION in config/.env"
            )
        await submit.click()
        await page.wait_for_load_state("networkidle")
        if await self._is_logged_out(page):
            raise SessionExpiredError("Login failed — check credentials or use STF_SESSION cookie")
        await page.close()
        logger.info("authenticated_via_credentials")

    async def _is_logged_out(self, page: Page) -> bool:
        url = page.url
        if "/login" in url or "/account/login" in url:
            return True
        content = await page.content()
        return "Войти" in content and "logout" not in content.lower()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def _fetch_page(self, path: str) -> tuple[str, str]:
        self._rate.acquire("standoff")
        assert self._context is not None
        page = await self._context.new_page()
        url = f"{self._base}{path}"
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            if await self._is_logged_out(page):
                raise SessionExpiredError("Session expired during scrape")
            html = await page.content()
            return url, html
        finally:
            await page.close()

    async def list_programs(self, max_pages: int = 50) -> list[dict[str, str]]:
        programs: list[dict[str, str]] = []
        seen_slugs: set[str] = set()

        for page_num in range(1, max_pages + 1):
            batch = await self._list_programs_page(page_num)
            if not batch:
                break
            added = 0
            for p in batch:
                if p["slug"] not in seen_slugs:
                    seen_slugs.add(p["slug"])
                    programs.append(p)
                    added += 1
            if added == 0:
                break

        logger.info("programs_discovered", count=len(programs), pages=min(page_num, max_pages))
        return programs

    async def _list_programs_page(self, page_num: int) -> list[dict[str, str]]:
        path = f"/en-US/programs/?page={page_num}" if page_num > 1 else "/en-US/programs/"
        programs: list[dict[str, str]] = []
        assert self._context is not None
        page = await self._context.new_page()
        try:
            await page.goto(f"{self._base}{path}", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(1200)
            anchors = page.locator('a[href*="/programs/"]')
            count = await anchors.count()
            for i in range(count):
                link = anchors.nth(i)
                href = await link.get_attribute("href") or ""
                if "/programs/" not in href:
                    continue
                rel = href.split("bugbounty.standoff365.com")[-1].split("?", 1)[0]
                after = rel.split("/programs/")[-1].strip("/")
                if not after:
                    continue
                slug = after.split("/")[0]
                if slug in ("programs", "en-US", "ru-RU"):
                    continue
                name = (await link.inner_text()).strip().split("\n")[0] or slug
                programs.append({"slug": slug, "name": name, "path": rel})
        finally:
            await page.close()
        return programs

    async def list_disclosed_reports(self, max_pages: int = 100) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        seen_paths: set[str] = set()

        for page_num in range(1, max_pages + 1):
            batch = await self._list_disclosed_page(page_num)
            if not batch:
                break
            added = 0
            for row in batch:
                if row["path"] not in seen_paths:
                    seen_paths.add(row["path"])
                    items.append(row)
                    added += 1
            if added == 0:
                break

        logger.info("disclosed_reports_listed", count=len(items))
        return items

    async def _list_disclosed_page(self, page_num: int) -> list[dict[str, str]]:
        path = (
            f"/en-US/disclosed-reports/?page={page_num}"
            if page_num > 1
            else "/en-US/disclosed-reports/"
        )
        rows: list[dict[str, str]] = []
        assert self._context is not None
        page = await self._context.new_page()
        try:
            await page.goto(f"{self._base}{path}", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(1200)
            anchors = page.locator('a[href*="/disclosed-reports/"]')
            count = await anchors.count()
            for i in range(count):
                link = anchors.nth(i)
                href = await link.get_attribute("href") or ""
                if not re.search(r"/disclosed-reports/\d+$", href):
                    continue
                rel = href.split("bugbounty.standoff365.com")[-1]
                text = (await link.inner_text()).strip()
                if not text or len(text) < 5:
                    continue
                rows.append({"path": rel, "text": text, "url": href})
        finally:
            await page.close()
        return rows

    async def fetch_disclosed_report(self, path: str) -> tuple[str, str, str | None]:
        if not path.startswith("/"):
            path = f"/en-US/disclosed-reports/{path}"
        if path.startswith("/disclosed-reports/"):
            path = f"/en-US{path}"
        self._rate.acquire("standoff")
        assert self._context is not None
        page = await self._context.new_page()
        url = f"{self._base}{path}"
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            if await self._is_logged_out(page):
                raise SessionExpiredError("Session expired during scrape")
            html = await page.content()
            program_href = None
            prog = page.locator('a[href*="/programs/"]')
            if await prog.count() > 0:
                for i in range(await prog.count()):
                    href = await prog.nth(i).get_attribute("href") or ""
                    if re.search(r"/programs/[^/]+/?$", href):
                        program_href = href
                        break
            return url, html, program_href
        finally:
            await page.close()

    async def fetch_program_page(
        self, path: str, *, next_data_only: bool = False
    ) -> tuple[str, str, dict[str, str]]:
        if not path.startswith("/") and not path.startswith("http"):
            path = f"/programs/{path}/"
        if path.startswith("/programs/") and "/en-US/" not in path and "/ru-RU/" not in path:
            path = f"/en-US{path}"
        url, html, tab_sections = await self._fetch_page_with_tabs(path, next_data_only=next_data_only)
        return url, html, tab_sections

    async def _fetch_page_with_tabs(
        self, path: str, *, next_data_only: bool = False
    ) -> tuple[str, str, dict[str, str]]:
        self._rate.acquire("standoff")
        assert self._context is not None
        page = await self._context.new_page()
        url = f"{self._base}{path}"
        tab_sections: dict[str, str] = {}
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            if await self._is_logged_out(page):
                raise SessionExpiredError("Session expired during scrape")
            html = await page.content()
            tab_sections = await self._collect_tab_sections(page, next_data_only=next_data_only)
            if tab_sections:
                combined = "\n".join(tab_sections.values())
                html = f"{html}\n<!-- pipeline-tabs -->\n{combined}"
            return url, html, tab_sections
        finally:
            await page.close()

    async def _collect_tab_sections(self, page: Page, *, next_data_only: bool = False) -> dict[str, str]:
        sections: dict[str, str] = {}
        html = await page.content()
        page_props = extract_program_page_props(html)
        if page_props:
            sections.update(parse_tab_sections_from_next(page_props))

        if next_data_only:
            logger.info("program_tabs_collected", count=len(sections), labels=list(sections), mode="next_data")
            return sections

        seen_labels: set[str] = {label.lower() for label in sections}
        for label in PROGRAM_TAB_LABELS:
            norm = label.lower()
            if norm in seen_labels:
                continue
            existing = sections.get(label) or sections.get(label.capitalize())
            if existing and len(existing) > 400:
                continue
            try:
                button = page.get_by_role("button", name=label, exact=True)
                if await button.count() == 0:
                    button = page.locator(f'button:has-text("{label}")').first
                if await button.count() == 0 or not await button.is_visible():
                    continue
                await button.click()
                await page.wait_for_timeout(500)
                panel = page.locator("main").first
                content = (await panel.inner_text()).strip() if await panel.count() else ""
                if content and len(content) > 40:
                    sections[label] = content
                    seen_labels.add(norm)
            except Exception as exc:
                logger.debug("toggle_tab_skip", label=label, error=str(exc))

        if not sections:
            tab_locator = page.locator(
                '[role="tab"], .nav-tabs a, .nav-tabs button, '
                'button[data-tab], a[data-tab]'
            )
            count = await tab_locator.count()
            for i in range(count):
                tab = tab_locator.nth(i)
                try:
                    if not await tab.is_visible():
                        continue
                    label = (await tab.inner_text()).strip()
                    if not label or len(label) > 80:
                        continue
                    norm = label.lower()
                    if norm in seen_labels:
                        continue
                    if not any(marker in norm for marker in TAB_LABEL_MARKERS):
                        continue
                    seen_labels.add(norm)
                    await tab.click()
                    await page.wait_for_timeout(400)
                    panel = page.locator('[role="tabpanel"]:visible, .tab-pane.active')
                    if await panel.count() > 0:
                        content = await panel.first.inner_text()
                    else:
                        content = await page.locator("main").first.inner_text()
                    sections[label] = content.strip()
                except Exception as exc:
                    logger.debug("tab_scrape_skip", index=i, error=str(exc))

        logger.info("program_tabs_collected", count=len(sections), labels=list(sections))
        return sections

    async def save_snapshot(self, slug: str, html: str, snapshots_dir: str) -> Path:
        out = Path(snapshots_dir) / f"{slug}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        return out
