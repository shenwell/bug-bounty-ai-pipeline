"""Fetch Standoff365 program catalog from public __NEXT_DATA__ (no auth)."""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://bugbounty.standoff365.com"
DEFAULT_LOCALE = "en-US"
DEFAULT_PAGE_SIZE = 20
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    flags=re.DOTALL | re.IGNORECASE,
)


class ProgramsListError(Exception):
    pass


def _extract_programs_from_html(html: str) -> list[dict[str, Any]]:
    match = NEXT_DATA_RE.search(html)
    if not match:
        raise ProgramsListError("No __NEXT_DATA__ pageProps on programs page")
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ProgramsListError("Invalid __NEXT_DATA__ JSON") from exc
    page_props = data.get("props", {}).get("pageProps")
    if not isinstance(page_props, dict):
        raise ProgramsListError("pageProps missing on programs page")
    programs = page_props.get("programs")
    if not isinstance(programs, list):
        raise ProgramsListError("pageProps.programs missing or not a list")
    return programs


def _programs_path(page: int, locale: str = DEFAULT_LOCALE) -> str:
    if page <= 1:
        return f"/{locale}/programs/"
    return f"/{locale}/programs/?page={page}"


def parse_programs_page(html: str) -> list[dict[str, Any]]:
    return _extract_programs_from_html(html)


def normalize_program(raw: dict[str, Any], *, base_url: str = DEFAULT_BASE_URL) -> dict[str, Any]:
    slug = str(raw.get("slug") or "").strip()
    if not slug:
        raise ProgramsListError("Program record without slug")
    name = str(raw.get("name") or slug).strip()
    locale_path = f"/en-US/programs/{slug}/"
    return {
        "slug": slug,
        "name": name,
        "id": raw.get("id"),
        "visibility": raw.get("visibility"),
        "published_at": raw.get("publishedAt"),
        "created_at": raw.get("createdAt"),
        "updated_at": raw.get("updatedAt"),
        "url": f"{base_url.rstrip('/')}{locale_path}",
    }


def fetch_program_html(
    slug: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    locale: str = DEFAULT_LOCALE,
    timeout_sec: float = 30.0,
    client: httpx.Client | None = None,
) -> tuple[str, str]:
    """Fetch a public program page by slug. Returns (final_url, html)."""
    clean = slug.strip().strip("/")
    if not clean:
        raise ProgramsListError("Empty program slug")
    path = f"/{locale}/programs/{clean}/"
    url = f"{base_url.rstrip('/')}{path}"
    own_client = client is None
    http = client or httpx.Client(headers={"User-Agent": "bug-bounty-pipeline/dossier"})
    try:
        response = http.get(url, timeout=timeout_sec, follow_redirects=True)
        response.raise_for_status()
        return str(response.url), response.text
    finally:
        if own_client:
            http.close()


def fetch_programs_page(
    client: httpx.Client,
    *,
    page: int = 1,
    base_url: str = DEFAULT_BASE_URL,
    locale: str = DEFAULT_LOCALE,
    timeout_sec: float = 30.0,
) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}{_programs_path(page, locale)}"
    response = client.get(url, timeout=timeout_sec, follow_redirects=True)
    response.raise_for_status()
    raw_programs = parse_programs_page(response.text)
    return [normalize_program(item, base_url=base_url) for item in raw_programs]


def list_all_programs(
    *,
    base_url: str = DEFAULT_BASE_URL,
    locale: str = DEFAULT_LOCALE,
    max_pages: int = 50,
    delay_sec: float = 0.25,
    timeout_sec: float = 30.0,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Paginate public programs list until no new slugs appear."""
    own_client = client is None
    http = client or httpx.Client(headers={"User-Agent": "bug-bounty-pipeline/monitor"})
    programs: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    try:
        for page in range(1, max_pages + 1):
            batch = fetch_programs_page(
                http,
                page=page,
                base_url=base_url,
                locale=locale,
                timeout_sec=timeout_sec,
            )
            if not batch:
                break

            added = 0
            for program in batch:
                slug = program["slug"]
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                programs.append(program)
                added += 1

            if added == 0:
                break
            if len(batch) < DEFAULT_PAGE_SIZE:
                break
            if page < max_pages and delay_sec > 0:
                time.sleep(delay_sec)
    finally:
        if own_client:
            http.close()

    return programs
