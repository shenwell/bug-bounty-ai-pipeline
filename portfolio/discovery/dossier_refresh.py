"""Refresh single-contract dossier after human selection — live fetch + raw archive."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from portfolio.common.config import AppConfig
from portfolio.common.logging import get_logger
from portfolio.common.models import Contract, DisclosedReport
from portfolio.discovery.disclosed_runner import load_disclosed_reports
from portfolio.discovery.hunt_plan import write_hunt_plan
from portfolio.discovery.landscape import enrich_contract_landscape
from portfolio.discovery.next_data_parser import extract_program_page_props
from portfolio.discovery.parser import parse_program

from portfolio.discovery.dossier import bind_contract_dossier, ensure_dossier

logger = get_logger(__name__)


def save_raw_dossier(
    config: AppConfig,
    slug: str,
    *,
    html: str,
    page_props: dict[str, Any] | None,
    source_url: str,
) -> Path:
    raw = ensure_dossier(config, slug) / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "page.html").write_text(html, encoding="utf-8")
    meta = {
        "source_url": source_url,
        "fetched_at": datetime.now(UTC).isoformat(),
        "has_page_props": page_props is not None,
    }
    (raw / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    if page_props:
        (raw / "page_props.json").write_text(
            json.dumps(page_props, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        program = page_props.get("program")
        reward = page_props.get("reward")
        if program:
            (raw / "program.json").write_text(
                json.dumps(program, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        if reward:
            (raw / "reward.json").write_text(
                json.dumps(reward, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
    return raw


def apply_program_html(
    config: AppConfig,
    contract: Contract,
    *,
    html: str,
    url: str,
    tab_sections: dict[str, str] | None = None,
    disclosed_reports: list[DisclosedReport] | None = None,
) -> tuple[Contract, dict[str, Any] | None]:
    """Archive a fetched program page and rebuild landscape + hunt plan."""
    page_props = extract_program_page_props(html)
    save_raw_dossier(config, contract.slug, html=html, page_props=page_props, source_url=url)

    preserved = {
        "id": contract.id,
        "program_id": contract.program_id,
        "score": contract.score,
        "score_reason": contract.score_reason,
        "target_vectors": contract.target_vectors,
        "status": contract.status,
    }
    refreshed = parse_program(
        contract.slug,
        contract.name,
        html,
        url,
        program_id=contract.program_id,
        tab_sections=tab_sections or {},
    )
    for key, value in preserved.items():
        setattr(refreshed, key, value)

    reports = disclosed_reports if disclosed_reports is not None else load_disclosed_reports(config)
    refreshed = enrich_contract_landscape(config, refreshed, reports)
    refreshed = bind_contract_dossier(config, refreshed)
    refreshed.dossier_refreshed_at = datetime.now(UTC).isoformat()
    refreshed.hunt_plan_file = write_hunt_plan(config, refreshed, reports)

    logger.info(
        "dossier_refreshed",
        slug=contract.slug,
        tabs=list(refreshed.tab_sections.keys()),
        scope=len(refreshed.scope),
    )
    return refreshed, page_props


async def refresh_contract_dossier(
    config: AppConfig,
    contract: Contract,
    scraper=None,
    *,
    disclosed_reports: list[DisclosedReport] | None = None,
) -> tuple[Contract, dict[str, Any] | None]:
    """Re-fetch program from Standoff, archive raw JSON/HTML, rebuild landscape + hunt plan."""
    from portfolio.discovery.scraper import StandoffScraper

    if scraper is None:
        raise ValueError("refresh_contract_dossier requires an active StandoffScraper")
    path = contract.source_url.split("bugbounty.standoff365.com")[-1]
    if not path or "/programs/" not in path:
        path = f"/en-US/programs/{contract.slug}/"

    url, html, tab_sections = await scraper.fetch_program_page(path, next_data_only=True)
    return apply_program_html(
        config,
        contract,
        html=html,
        url=url,
        tab_sections=tab_sections,
        disclosed_reports=disclosed_reports,
    )
