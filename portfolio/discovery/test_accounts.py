"""Detect and probe program test / demo accounts during dossier RECON."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from portfolio.common.config import AppConfig
from portfolio.common.logging import get_logger
from portfolio.common.models import Contract, ExternalReference
from portfolio.discovery.dossier import dossier_path, ensure_dossier
from portfolio.discovery.scope_match import is_in_scope, is_out_of_scope
from portfolio.guardrails.limits import RateLimiter

logger = get_logger(__name__)

ON_REQUEST_MARKERS = (
    "тестовую учётную запись",
    "тестовую учетную запись",
    "тестовый аккаунт",
    "test account",
    "testing account",
    "demo account",
    "sandbox account",
    "предоставим учётную",
    "предоставим учетную",
    "we can provide",
    "we may provide",
    "upon request",
    "по предварительному согласованию",
    "pre-created test",
)

DEMO_DOC_MARKERS = (
    "demo account",
    "демо-кабинет",
    "демо кабинет",
    "демо-аккаунт",
    "демо аккаунт",
    "access-to-demo",
    "demo-environment",
    "sandbox",
    "staging account",
    "test credentials",
    "тестовые данные для входа",
)

CAPTCHA_MARKERS = (
    "captcha",
    "smartcaptcha",
    "recaptcha",
    "hcaptcha",
    "подтвердите, что вы не робот",
    "я не робот",
)

LOGIN_PATH_MARKERS = ("/login", "/signin", "/sign-in", "/auth", "/account/login")
PHONE_RE = re.compile(
    r"(?:\+7|8)[\s\-\(]*(?:000|7\d{2})[\s\-\)]*[\d\s\-]{6,10}\d",
    re.IGNORECASE,
)
PASSWORD_LABEL_RE = re.compile(
    r"(?:пароль|password|pass(?:word)?)\s*[:|]\s*[`'\"]?([^\s`'\|<]+)",
    re.IGNORECASE,
)
LOGIN_LABEL_RE = re.compile(
    r"(?:логин|login|телефон|phone|e-?mail)\s*[:|]\s*[`'\"]?([^\s`'\|<]+)",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s\]`\)\"'<>]+", re.IGNORECASE)
MD_TABLE_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)


@dataclass
class TestAccountCheck:
    checked_at: str
    program_slug: str
    summary: dict[str, Any] = field(default_factory=dict)
    mentions: list[dict[str, Any]] = field(default_factory=list)
    accounts: list[dict[str, Any]] = field(default_factory=list)
    login_urls: list[dict[str, Any]] = field(default_factory=list)
    probes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked_at": self.checked_at,
            "program_slug": self.program_slug,
            "summary": self.summary,
            "mentions": self.mentions,
            "accounts": self.accounts,
            "login_urls": self.login_urls,
            "probes": self.probes,
        }


def _contract_text_blocks(contract: Contract) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    if contract.acceptance_criteria:
        blocks.append(("acceptance_criteria", contract.acceptance_criteria))
    for label, content in contract.tab_sections.items():
        if content.strip():
            blocks.append((f"tab:{label}", content))
    for rule in contract.constraints.raw_rules:
        if rule.strip():
            blocks.append(("rules", rule))
    return blocks


def _strip_html(text: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text).strip()


def _read_ref_text(ref: ExternalReference, limit: int = 20000) -> str:
    parts: list[str] = []
    if ref.preview:
        parts.append(ref.preview)
    if ref.file_path:
        path = Path(ref.file_path)
        if path.exists() and path.is_file():
            try:
                body = path.read_bytes()[:limit]
                if path.suffix.lower() in (".html", ".htm"):
                    parts.append(_strip_html(body.decode("utf-8", errors="replace")))
                else:
                    parts.append(body.decode("utf-8", errors="replace"))
            except OSError:
                pass
    return "\n".join(parts)


def _mask_secret(value: str) -> str:
    if len(value) <= 4:
        return "****"
    if len(value) <= 8:
        return value[:2] + "****"
    return value[:3] + "****" + value[-2:]


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if digits.startswith("7"):
        return f"+{digits}"
    return phone.strip()


def _extract_mentions(text: str, source: str) -> list[dict[str, Any]]:
    lower = text.lower()
    found: list[dict[str, Any]] = []
    for marker in ON_REQUEST_MARKERS:
        idx = lower.find(marker.lower())
        if idx >= 0:
            snippet = text[max(0, idx - 40) : idx + len(marker) + 120].strip()
            found.append(
                {
                    "kind": "on_request",
                    "marker": marker,
                    "source": source,
                    "snippet": snippet[:300],
                }
            )
            break
    for marker in DEMO_DOC_MARKERS:
        if marker.lower() in lower:
            found.append(
                {
                    "kind": "demo_documentation",
                    "marker": marker,
                    "source": source,
                    "snippet": text[:300],
                }
            )
            break
    return found


def _extract_accounts_from_text(text: str, source: str) -> list[dict[str, Any]]:
    accounts: list[dict[str, Any]] = []
    phones = {_normalize_phone(m.group(0)) for m in PHONE_RE.finditer(text)}
    passwords = [m.group(1).strip("`'\" ") for m in PASSWORD_LABEL_RE.finditer(text)]
    logins = [m.group(1).strip("`'\" ") for m in LOGIN_LABEL_RE.finditer(text)]

    for row_match in MD_TABLE_ROW_RE.finditer(text):
        key = row_match.group(1).strip().lower()
        val = row_match.group(2).strip()
        if not val or val in ("—", "-", "n/a"):
            continue
        if any(k in key for k in ("пароль", "password")):
            passwords.append(val.strip("`'\" "))
        if any(k in key for k in ("телефон", "phone", "логин", "login", "email")):
            logins.append(val.strip("`'\" "))
            if PHONE_RE.search(val):
                phones.add(_normalize_phone(val))

    login_urls = [u.rstrip(".,;)") for u in URL_RE.findall(text) if any(m in u.lower() for m in LOGIN_PATH_MARKERS)]

    if phones or passwords or logins:
        account: dict[str, Any] = {
            "source": source,
            "kind": "self_service_demo",
            "login_urls": login_urls[:5],
        }
        if phones:
            account["phones"] = sorted(phones)
        if logins:
            account["logins"] = list(dict.fromkeys(logins))[:5]
        if passwords:
            account["passwords_masked"] = [_mask_secret(p) for p in passwords[:3]]
            account["has_password"] = True
        accounts.append(account)
    return accounts


def _collect_login_urls(contract: Contract, surfaces: dict[str, Any] | None) -> list[str]:
    urls: list[str] = []
    for _, text in _contract_text_blocks(contract):
        for url in URL_RE.findall(text):
            url = url.rstrip(".,;)")
            if any(marker in url.lower() for marker in LOGIN_PATH_MARKERS):
                urls.append(url)
    for host in contract.scope:
        host = host.strip().lstrip("*.")
        if not host:
            continue
        for scheme in ("https", "http"):
            for marker in LOGIN_PATH_MARKERS:
                urls.append(f"{scheme}://{host}{marker}")

    if surfaces:
        for surface in surfaces.values():
            if not isinstance(surface, dict):
                continue
            for endpoint in surface.get("endpoints") or []:
                ep = str(endpoint).lower()
                if any(marker in ep for marker in LOGIN_PATH_MARKERS):
                    if endpoint.startswith("http"):
                        urls.append(str(endpoint))
            for host in surface.get("live_hosts") or []:
                host = str(host).split("/")[0]
                if host and not host.startswith("http"):
                    urls.append(f"https://{host}/login")

    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        normalized = url.lower().rstrip("/")
        if normalized not in seen:
            seen.add(normalized)
            deduped.append(url)
    return deduped[:20]


def _bb_headers(contract: Contract) -> dict[str, str]:
    headers: dict[str, str] = {"User-Agent": "bug-bounty-pipeline/test-accounts"}
    for name, expected in contract.constraints.required_headers.items():
        value = expected
        if "{user}" in value:
            user = os.environ.get("BUG_BOUNTY_USER", "")
            value = value.replace("{user}", user)
        headers[name] = value
    user = os.environ.get("BUG_BOUNTY_USER")
    if user and "X-Bug-Bounty" not in headers and "x-bug-bounty" not in {k.lower() for k in headers}:
        headers["X-Bug-Bounty"] = user
    return headers


def _url_in_scope(url: str, contract: Contract) -> bool:
    host = urlparse(url).netloc
    if not host:
        return False
    if is_out_of_scope(host, contract.out_of_scope):
        return False
    return is_in_scope(host, contract.scope, contract.out_of_scope)


def _build_summary(check: TestAccountCheck) -> dict[str, Any]:
    has_demo = any(a.get("kind") == "self_service_demo" for a in check.accounts)
    on_request = any(m.get("kind") == "on_request" for m in check.mentions)
    captcha_blocked = any(p.get("captcha_detected") for p in check.probes)
    reachable = [p for p in check.probes if p.get("reachable")]

    if has_demo and reachable and not captcha_blocked:
        status = "demo_ready"
        ready = True
    elif has_demo and captcha_blocked:
        status = "demo_credentials_captcha_blocked"
        ready = False
    elif has_demo:
        status = "demo_credentials_found"
        ready = False
    elif on_request:
        status = "on_request_only"
        ready = False
    elif check.login_urls:
        status = "login_urls_only"
        ready = False
    else:
        status = "none_found"
        ready = False

    blockers: list[str] = []
    if captcha_blocked:
        blockers.append("captcha_on_login")
    if on_request and not has_demo:
        blockers.append("accounts_on_request")
    if status == "none_found":
        blockers.append("no_test_accounts_documented")

    return {
        "status": status,
        "ready_for_auth_hunt": ready,
        "self_service_demo": has_demo,
        "on_request_available": on_request,
        "login_urls_found": len(check.login_urls),
        "reachable_login_pages": len(reachable),
        "blockers": blockers,
    }


def build_auth_accounts_markdown(check: TestAccountCheck, contract: Contract) -> str:
    summary = check.summary
    lines = [
        f"# Тестовые аккаунты — {contract.name} (`{contract.slug}`)",
        "",
        "> Автопроверка при сборке досье. Не коммитить живые сессии и одноразовые коды.",
        "",
        f"- **Проверено:** {check.checked_at}",
        f"- **Статус:** `{summary.get('status', 'unknown')}`",
        f"- **Готов к auth-hunt:** {'да' if summary.get('ready_for_auth_hunt') else 'нет'}",
        "",
    ]

    blockers = summary.get("blockers") or []
    if blockers:
        lines.append("## Блокеры")
        lines.append("")
        for blocker in blockers:
            lines.append(f"- `{blocker}`")
        lines.append("")

    if check.accounts:
        lines.extend(["## Найденные учётные данные", ""])
        for idx, account in enumerate(check.accounts, 1):
            lines.append(f"### {idx}. {account.get('kind', 'account')} ({account.get('source', '—')})")
            if account.get("phones"):
                lines.append(f"- Телефон: `{', '.join(account['phones'])}`")
            if account.get("logins"):
                lines.append(f"- Логин: `{', '.join(account['logins'])}`")
            if account.get("has_password"):
                lines.append("- Пароль: указан в описании программы / внешней документации (см. источник)")
            for url in account.get("login_urls") or []:
                lines.append(f"- Login URL: {url}")
            lines.append("")

    if check.mentions:
        lines.extend(["## Упоминания в правилах", ""])
        for mention in check.mentions:
            lines.append(f"- **{mention.get('kind')}** ({mention.get('source')}): {mention.get('snippet', '')[:200]}")
        lines.append("")

    if check.login_urls:
        lines.extend(["## Login URLs", ""])
        for item in check.login_urls:
            tag = "in-scope" if item.get("in_scope") else "external"
            lines.append(
                f"- [{item.get('url')}]({item.get('url')}) ({tag}, HTTP {item.get('status_code', '—')})"
            )
        lines.append("")

    if check.probes:
        lines.extend(["## Пробы доступности", ""])
        for probe in check.probes:
            captcha = " + captcha" if probe.get("captcha_detected") else ""
            lines.append(
                f"- `{probe.get('url')}` → HTTP {probe.get('status_code', '—')}, "
                f"reachable={probe.get('reachable')}{captcha}"
            )
        lines.append("")

    lines.extend(
        [
            "## Следующие шаги",
            "",
            "- Если `demo_credentials_captcha_blocked` — один human step: пройти captcha в браузере.",
            "- Если `on_request_only` — запросить тестовый аккаунт у triager до authz-hunt.",
            "- После входа сохранить сессию в `hunt/*-auth-session.json` (в git не коммитить).",
            "",
            "Структурированные данные: `auth_accounts.json`.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def scan_contract_for_test_accounts(
    contract: Contract,
    *,
    external_refs: list[ExternalReference] | None = None,
    surfaces: dict[str, Any] | None = None,
) -> TestAccountCheck:
    """Parse program text and external refs for demo / test account hints."""
    check = TestAccountCheck(
        checked_at=datetime.now(UTC).isoformat(),
        program_slug=contract.slug,
    )

    for source, text in _contract_text_blocks(contract):
        check.mentions.extend(_extract_mentions(text, source))
        check.accounts.extend(_extract_accounts_from_text(text, source))

    refs = external_refs if external_refs is not None else contract.external_refs
    for ref in refs:
        blob = _read_ref_text(ref)
        if not blob:
            continue
        source = f"external_ref:{ref.url}"
        lower_url = ref.url.lower()
        if any(marker in lower_url for marker in ("demo", "test-account", "sandbox", "access-to")) or any(
            marker in blob.lower() for marker in DEMO_DOC_MARKERS
        ):
            check.mentions.extend(_extract_mentions(blob, source))
            check.accounts.extend(_extract_accounts_from_text(blob, source))

    dedup_accounts: list[dict[str, Any]] = []
    seen_account_keys: set[str] = set()
    for account in check.accounts:
        key = "|".join(
            [
                account.get("source", ""),
                ",".join(account.get("phones") or []),
                ",".join(account.get("logins") or []),
            ]
        )
        if key not in seen_account_keys:
            seen_account_keys.add(key)
            dedup_accounts.append(account)
    check.accounts = dedup_accounts

    dedup_mentions: list[dict[str, Any]] = []
    seen_mention_keys: set[str] = set()
    for mention in check.mentions:
        key = f"{mention.get('kind')}|{mention.get('marker')}|{mention.get('source')}"
        if key not in seen_mention_keys:
            seen_mention_keys.add(key)
            dedup_mentions.append(mention)
    check.mentions = dedup_mentions

    for url in _collect_login_urls(contract, surfaces):
        check.login_urls.append(
            {
                "url": url,
                "in_scope": _url_in_scope(url, contract),
                "source": "scope_and_text",
            }
        )

    check.summary = _build_summary(check)
    return check


async def probe_test_account_access(
    config: AppConfig,
    contract: Contract,
    check: TestAccountCheck,
) -> TestAccountCheck:
    """Light reachability probe for login pages (no credential brute-force)."""
    headers = _bb_headers(contract)
    rate = RateLimiter(config.limits)
    timeout = config.recon.link_fetch_timeout_sec

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        for item in check.login_urls:
            url = item["url"]
            if not item.get("in_scope"):
                continue
            rate.acquire(f"test-accounts:{contract.slug}")
            probe: dict[str, Any] = {"url": url, "reachable": False, "captcha_detected": False}
            try:
                response = await client.get(url, headers=headers)
                probe["status_code"] = response.status_code
                body = response.text[:8000].lower()
                probe["reachable"] = response.status_code < 500
                probe["captcha_detected"] = any(marker in body for marker in CAPTCHA_MARKERS)
                item["status_code"] = response.status_code
            except Exception as exc:
                probe["error"] = str(exc)
                item["error"] = str(exc)
            check.probes.append(probe)

    check.summary = _build_summary(check)
    return check


def write_auth_accounts(
    config: AppConfig,
    contract: Contract,
    check: TestAccountCheck,
) -> tuple[str, str]:
    ensure_dossier(config, contract.slug)
    json_path = dossier_path(config, contract.slug, "auth_accounts.json")
    md_path = dossier_path(config, contract.slug, "auth_accounts.md")
    json_path.write_text(json.dumps(check.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(build_auth_accounts_markdown(check, contract), encoding="utf-8")
    logger.info(
        "test_accounts_checked",
        slug=contract.slug,
        status=check.summary.get("status"),
        accounts=len(check.accounts),
    )
    return str(json_path).replace("\\", "/"), str(md_path).replace("\\", "/")


async def check_test_accounts(
    config: AppConfig,
    contract: Contract,
    *,
    surfaces: dict[str, Any] | None = None,
    probe: bool = True,
) -> TestAccountCheck:
    """Full scan + optional login-page probe; writes auth_accounts.* into dossier."""
    check = scan_contract_for_test_accounts(
        contract,
        external_refs=contract.external_refs,
        surfaces=surfaces,
    )
    if probe and check.login_urls:
        check = await probe_test_account_access(config, contract, check)
    write_auth_accounts(config, contract, check)
    return check
