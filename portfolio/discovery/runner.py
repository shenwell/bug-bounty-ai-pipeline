"""Discovery orchestration — scrape, parse, dedup, persist."""

from __future__ import annotations

from pathlib import Path

import yaml

from portfolio.common.config import AppConfig
from portfolio.common.logging import get_logger
from portfolio.common.models import Contract
from portfolio.discovery.disclosed_runner import enrich_contracts_with_disclosed, run_disclosed_discovery
from portfolio.discovery.parser import parse_program
from portfolio.discovery.scraper import StandoffScraper
from portfolio.guardrails.audit import AuditTrail
from portfolio.guardrails.limits import RateLimiter

logger = get_logger(__name__)


def _load_existing(path: Path) -> dict[str, Contract]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    programs = data.get("programs", [])
    return {c["slug"]: Contract(**c) for c in programs}


def _save_contracts(path: Path, contracts: list[Contract]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"programs": [c.model_dump(mode="json") for c in contracts]}
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(payload, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


async def run_discovery(config: AppConfig) -> list[Contract]:
    audit = AuditTrail(config)
    audit.init_schema()
    rate = RateLimiter(config.limits)
    contracts_path = Path(config.data.contracts_file)
    existing = _load_existing(contracts_path)

    async with StandoffScraper(config, rate) as scraper:
        programs = await scraper.list_programs(config.discover.max_program_pages)
        results: list[Contract] = []

        for prog in programs:
            url, html, tab_sections = await scraper.fetch_program_page(prog["path"])
            await scraper.save_snapshot(prog["slug"], html, config.data.snapshots_dir)
            contract = parse_program(
                prog["slug"], prog["name"], html, url, tab_sections=tab_sections
            )

            if prog["slug"] in existing:
                old = existing[prog["slug"]]
                if old.model_dump() != contract.model_dump():
                    audit.log(
                        "discovery",
                        "contract_updated",
                        "contract",
                        contract.id,
                        input_data={"slug": prog["slug"]},
                    )
            else:
                audit.log(
                    "discovery",
                    "contract_discovered",
                    "contract",
                    contract.id,
                    input_data={"slug": prog["slug"]},
                )

            results.append(contract)

    await run_disclosed_discovery(config)
    results = enrich_contracts_with_disclosed(config, results)

    _save_contracts(contracts_path, results)
    logger.info("discovery_complete", count=len(results), path=str(contracts_path))
    return results
