"""Fetch BI.ZONE Bug Bounty company catalog from public REST API (no auth)."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

DEFAULT_BASE_URL = "https://bugbounty.bi.zone"
COMPANIES_PATH = "/api/bug-bounty/companies/"
DEFAULT_PAGE_SIZE = 100


class BizoneCompaniesListError(Exception):
    pass


def normalize_company(raw: dict[str, Any], *, base_url: str = DEFAULT_BASE_URL) -> dict[str, Any]:
    slug = str(raw.get("slug") or raw.get("id") or "").strip()
    if not slug:
        raise BizoneCompaniesListError("Company record without slug")
    name = str(raw.get("name") or slug).strip()
    return {
        "slug": slug,
        "name": name,
        "id": raw.get("id"),
        "public": raw.get("public"),
        "is_active": raw.get("isActive"),
        "published_at": raw.get("registrationDate"),
        "url": f"{base_url.rstrip('/')}/companies/{slug}",
    }


def _parse_results(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise BizoneCompaniesListError("Companies response is not a JSON object")
    results = payload.get("results")
    if not isinstance(results, list):
        raise BizoneCompaniesListError("Companies response missing results list")
    return results


def fetch_companies_page(
    client: httpx.Client,
    *,
    base_url: str = DEFAULT_BASE_URL,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
    timeout_sec: float = 30.0,
) -> tuple[list[dict[str, Any]], str | None]:
    url = f"{base_url.rstrip('/')}{COMPANIES_PATH}"
    response = client.get(url, params={"limit": limit, "offset": offset}, timeout=timeout_sec)
    response.raise_for_status()
    payload = response.json()
    raw_companies = _parse_results(payload)
    companies = [normalize_company(item, base_url=base_url) for item in raw_companies]
    next_url = payload.get("next")
    if isinstance(next_url, str) and next_url.strip():
        return companies, next_url
    return companies, None


def _offset_from_next_url(next_url: str) -> int | None:
    query = parse_qs(urlparse(next_url).query)
    raw = query.get("offset", [None])[0]
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def list_all_companies(
    *,
    base_url: str = DEFAULT_BASE_URL,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = 50,
    delay_sec: float = 0.25,
    timeout_sec: float = 30.0,
    public_only: bool = True,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Paginate public companies list until no new slugs appear."""
    own_client = client is None
    http = client or httpx.Client(headers={"User-Agent": "bug-bounty-pipeline/monitor"})
    companies: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    offset = 0

    try:
        for _page in range(1, max_pages + 1):
            batch, next_url = fetch_companies_page(
                http,
                base_url=base_url,
                limit=page_size,
                offset=offset,
                timeout_sec=timeout_sec,
            )
            if not batch:
                break

            added = 0
            for company in batch:
                if public_only and company.get("public") is False:
                    continue
                slug = company["slug"]
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                companies.append(company)
                added += 1

            if added == 0 and not next_url:
                break
            if not next_url:
                break

            next_offset = _offset_from_next_url(next_url)
            if next_offset is None:
                break
            offset = next_offset
            if delay_sec > 0:
                time.sleep(delay_sec)
    finally:
        if own_client:
            http.close()

    return companies
