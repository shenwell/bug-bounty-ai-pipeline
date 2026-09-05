"""Fetch and persist disclosed reports from Standoff365."""

from __future__ import annotations

from pathlib import Path

import yaml

from portfolio.common.config import AppConfig
from portfolio.common.logging import get_logger
from portfolio.common.models import DisclosedReport
from portfolio.discovery.coverage import attach_disclosed_to_contracts
from portfolio.discovery.disclosed_parser import parse_disclosed_detail, parse_disclosed_list_item
from portfolio.guardrails.audit import AuditTrail
from portfolio.guardrails.limits import RateLimiter

logger = get_logger(__name__)


def _load_existing(path: Path) -> dict[str, DisclosedReport]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    reports = data.get("reports", [])
    out: dict[str, DisclosedReport] = {}
    for r in reports:
        item = DisclosedReport(**r)
        key = item.report_no or item.list_path
        if key:
            out[key] = item
    return out


def _save_reports(path: Path, reports: list[DisclosedReport]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"reports": [r.model_dump(mode="json") for r in reports]}
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(payload, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


async def run_disclosed_discovery(config: AppConfig) -> list[DisclosedReport]:
    from portfolio.discovery.scraper import StandoffScraper

    audit = AuditTrail(config)
    audit.init_schema()
    rate = RateLimiter(config.limits)
    out_path = Path(config.data.disclosed_reports_file)
    existing = _load_existing(out_path)
    results: dict[str, DisclosedReport] = dict(existing)

    async with StandoffScraper(config, rate) as scraper:
        listed = await scraper.list_disclosed_reports(config.discover.max_disclosed_pages)
        logger.info("disclosed_list_fetched", count=len(listed))

        for item in listed:
            base = parse_disclosed_list_item(item["path"], item["text"], item["url"])
            key = base.list_path

            if config.discover.fetch_disclosed_details:
                url, html, program_href = await scraper.fetch_disclosed_report(item["path"])
                report = parse_disclosed_detail(html, url, program_href, base)
                await scraper.save_snapshot(
                    f"disclosed-{report.report_no or key.strip('/')}",
                    html,
                    config.data.snapshots_dir,
                )
            else:
                report = base

            dedup_key = report.report_no or key
            if dedup_key in results and results[dedup_key].model_dump() == report.model_dump():
                continue
            results[dedup_key] = report
            audit.log(
                "discovery",
                "disclosed_report_saved",
                "disclosed_report",
                report.id,
                input_data={"report_no": report.report_no, "program": report.program_slug},
            )

    ordered = sorted(results.values(), key=lambda r: r.report_no or "", reverse=True)
    _save_reports(out_path, ordered)
    logger.info("disclosed_discovery_complete", count=len(ordered), path=str(out_path))
    return ordered


def load_disclosed_reports(config: AppConfig) -> list[DisclosedReport]:
    path = Path(config.data.disclosed_reports_file)
    return list(_load_existing(path).values())


def enrich_contracts_with_disclosed(config: AppConfig, contracts: list) -> list:
    from portfolio.discovery.landscape import enrich_all_landscapes

    reports = load_disclosed_reports(config)
    return enrich_all_landscapes(config, contracts, reports)
