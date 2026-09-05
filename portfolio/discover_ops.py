"""Platform discovery and contract selection helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from portfolio.common.config import AppConfig, load_config
from portfolio.common.models import Contract
from portfolio.discovery.bizone_companies_list import list_all_companies
from portfolio.discovery.runner import run_discovery
from portfolio.scoring.scorer import ContractScorer


def load_contracts(config: AppConfig) -> list[Contract]:
    path = Path(config.data.contracts_file)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return [Contract(**c) for c in data.get("programs", [])]


def save_contracts(config: AppConfig, contracts: list[Contract]) -> None:
    path = Path(config.data.contracts_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"programs": [c.model_dump(mode="json") for c in contracts]}
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(payload, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


async def discover_platform(config: AppConfig, platform: str) -> list[Contract]:
    if platform == "standoff365":
        contracts = await run_discovery(config)
        scorer = ContractScorer(config)
        scored = [scorer.score(c) for c in contracts]
        save_contracts(config, scored)
        return scored

    if platform == "bizone":
        companies = list_all_companies(
            base_url=config.monitor.bizone_base_url,
            max_pages=config.monitor.max_pages,
            delay_sec=config.monitor.page_delay_sec,
            timeout_sec=config.monitor.request_timeout_sec,
        )
        scorer = ContractScorer(config)
        contracts: list[Contract] = []
        for company in companies:
            from portfolio.discovery.bizone_company import parse_bizone_company

            payload = {
                **company,
                "rules": "",
                "maxPrice": 0,
                "needVpn": False,
            }
            contract = parse_bizone_company(payload, base_url=config.monitor.bizone_base_url)
            contract = scorer.score(contract)
            contracts.append(contract)
        save_contracts(config, contracts)
        return contracts

    raise ValueError(f"Unknown platform: {platform}")


def contract_candidates(
    config: AppConfig,
    *,
    platform: str | None = None,
    limit: int = 25,
) -> list[dict]:
    scorer = ContractScorer(config)
    rows: list[dict] = []
    for contract in load_contracts(config):
        if platform and contract.platform != platform:
            continue
        rows.append(
            {
                "slug": contract.slug,
                "name": contract.name,
                "platform": contract.platform,
                "score": contract.score,
                "should_hunt": scorer.should_hunt(contract),
                "is_paid": contract.is_paid,
                "scope_count": len(contract.scope),
            }
        )
    rows.sort(key=lambda r: (not r["should_hunt"], -(r["score"] or 0)))
    return rows[:limit]


def select_contract(config: AppConfig, slug: str) -> Contract:
    from portfolio.discovery.disclosed_runner import load_disclosed_reports
    from portfolio.discovery.dossier import init_selected_dossier

    contracts = load_contracts(config)
    match = next((c for c in contracts if c.slug == slug), None)
    if not match:
        raise FileNotFoundError(f"Contract {slug} not in {config.data.contracts_file}. Run discover first.")
    disclosed = load_disclosed_reports(config)
    return init_selected_dossier(config, match, disclosed, stage="select")


async def refresh_standoff_contract(config: AppConfig, slug: str) -> Contract:
    from portfolio.discovery.disclosed_runner import load_disclosed_reports
    from portfolio.discovery.dossier_refresh import refresh_contract_dossier
    from portfolio.discovery.scraper import StandoffScraper
    from portfolio.guardrails.limits import RateLimiter

    contracts = load_contracts(config)
    contract = next((c for c in contracts if c.slug == slug), None)
    if not contract:
        raise FileNotFoundError(slug)
    disclosed = load_disclosed_reports(config)
    rate = RateLimiter(config.limits)
    async with StandoffScraper(config, rate) as scraper:
        contract, _ = await refresh_contract_dossier(config, contract, scraper, disclosed_reports=disclosed)
    scorer = ContractScorer(config)
    contract = scorer.score(contract)
    save_contracts(config, [c if c.slug != slug else contract for c in contracts])
    from portfolio.discovery.dossier_status import write_dossier_status, write_portfolio_status

    write_dossier_status(config, slug)
    write_portfolio_status(config)
    return contract
