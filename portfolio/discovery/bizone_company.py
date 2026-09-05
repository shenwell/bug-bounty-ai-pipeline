"""BI.ZONE company detail API → Contract model."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from portfolio.common.models import (
    Asset,
    AssetType,
    Contract,
    ProgramConstraints,
    ProgramFormat,
    RewardRange,
)

DEFAULT_BASE_URL = "https://bugbounty.bi.zone"
COMPANY_PATH = "/api/bug-bounty/companies/{slug}/"

URL_RE = re.compile(r"https?://[^\s\)`\"'<>]+", re.IGNORECASE)


def fetch_company(
    slug: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout_sec: float = 30.0,
) -> dict:
    url = f"{base_url.rstrip('/')}{COMPANY_PATH.format(slug=slug)}"
    response = httpx.get(url, timeout=timeout_sec, headers={"User-Agent": "pentest-agents-portfolio/1.0"})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected BI.ZONE response for {slug}")
    return payload


def _extract_scope_hosts(rules: str, site: str) -> list[str]:
    hosts: list[str] = []
    seen: set[str] = set()
    if site:
        parsed = urlparse(site if "://" in site else f"https://{site}")
        host = (parsed.hostname or "").lower()
        if host and host not in seen:
            seen.add(host)
            hosts.append(host)
    for match in URL_RE.findall(rules or ""):
        parsed = urlparse(match.rstrip(".,;"))
        host = (parsed.hostname or "").lower()
        if host and host not in seen and "." in host:
            seen.add(host)
            hosts.append(host)
    return hosts


def parse_bizone_company(payload: dict, *, base_url: str = DEFAULT_BASE_URL) -> Contract:
    slug = str(payload.get("slug") or payload.get("id") or "").strip()
    name = str(payload.get("name") or slug)
    rules = str(payload.get("rules") or "")
    site = str(payload.get("site") or "")
    source_url = f"{base_url.rstrip('/')}/companies/{slug}"

    reward_ranges: list[RewardRange] = []
    for sev, prefix in (
        ("critical", "Critical"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ):
        min_k = f"min{prefix}Price"
        max_k = f"max{prefix}Price"
        if min_k in payload or max_k in payload:
            reward_ranges.append(
                RewardRange(
                    severity=sev,
                    min_amount=float(payload.get(min_k) or 0),
                    max_amount=float(payload.get(max_k) or payload.get("maxPrice") or 0),
                    currency="RUB",
                )
            )

    scope = _extract_scope_hosts(rules, site)
    assets = [
        Asset(identifier=h, asset_type=AssetType.WEB_API, engagement_profile="web_api")
        for h in scope
    ]
    if site and not scope:
        assets = [Asset(identifier=site, asset_type=AssetType.WEB_API, engagement_profile="web_api")]

    constraints = ProgramConstraints(
        vpn_required=bool(payload.get("needVpn")),
        raw_rules=[line.strip() for line in rules.splitlines() if line.strip()][:40],
    )

    is_paid = float(payload.get("maxPrice") or 0) > 0 or bool(reward_ranges)

    return Contract(
        program_id=slug,
        slug=slug,
        name=name,
        platform="bizone",
        client=name,
        scope=scope,
        assets=assets,
        reward_ranges=reward_ranges,
        constraints=constraints,
        program_format=ProgramFormat.CLASSIC,
        is_paid=is_paid,
        tab_sections={"rules": rules[:12000]} if rules else {},
        source_url=source_url,
        acceptance_criteria=rules[:4000] if rules else "",
    )


def save_bizone_raw(config, slug: str, payload: dict) -> None:
    from portfolio.discovery.dossier import ensure_dossier
    import json
    from datetime import UTC, datetime

    raw = ensure_dossier(config, slug) / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "company.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (raw / "meta.json").write_text(
        json.dumps(
            {"source": "bizone_api", "fetched_at": datetime.now(UTC).isoformat(), "slug": slug},
            indent=2,
        ),
        encoding="utf-8",
    )
