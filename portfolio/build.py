"""Standoff365 and BI.ZONE dossier build orchestration."""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from datetime import UTC, datetime

from portfolio.agents.profiles.base import get_profile
from portfolio.common.config import AppConfig, load_config
from portfolio.discovery.bizone_company import fetch_company, parse_bizone_company, save_bizone_raw
from portfolio.discovery.disclosed_runner import load_disclosed_reports
from portfolio.discovery.dossier import (
    dossier_layout,
    finalize_recon_dossier,
    init_selected_dossier,
    should_recon_asset,
    write_hunt_bootstrap,
    write_workspace_pointer,
)
from portfolio.discovery.dossier_refresh import apply_program_html
from portfolio.discovery.hunt_plan import update_hunt_plan_surfaces, write_hunt_plan
from portfolio.discovery.landscape import enrich_contract_landscape
from portfolio.discovery.link_enrichment import enrich_contract_links
from portfolio.discovery.next_data_parser import extract_program_page_props, parse_tab_sections_from_next
from portfolio.discovery.parser import parse_program
from portfolio.discovery.programs_list import fetch_program_html
from portfolio.discovery.test_accounts import check_test_accounts
from portfolio.routing.router import route_contract
from portfolio.scoring.scorer import ContractScorer


def merge_contracts_yaml(path: Path, built: dict[str, dict]) -> None:
    existing: list[dict] = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        existing = [c for c in data.get("programs", []) if c.get("slug") not in built]
    payload = {"programs": existing + list(built.values())}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(payload, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


async def build_standoff_dossier(
    config: AppConfig,
    slug: str,
    *,
    skip_recon: bool = False,
) -> tuple:
    disclosed = load_disclosed_reports(config)
    print(f"Fetching Standoff365 {slug}...")
    url, html = fetch_program_html(
        slug,
        base_url=config.standoff.base_url,
        timeout_sec=config.monitor.request_timeout_sec,
    )
    page_props = extract_program_page_props(html) or {}
    tab_sections = parse_tab_sections_from_next(page_props)
    program = page_props.get("program") or {}
    name = str(program.get("name") or slug)

    contract = parse_program(slug, name, html, url, tab_sections=tab_sections)
    contract.platform = "standoff365"
    scorer = ContractScorer(config)
    contract = scorer.score(contract)
    contract = route_contract(contract)

    contract = init_selected_dossier(config, contract, disclosed, stage="recon")
    print(f"  init -> {contract.dossier_dir}/")

    contract, _ = apply_program_html(
        config,
        contract,
        html=html,
        url=url,
        tab_sections=tab_sections,
        disclosed_reports=disclosed,
    )
    contract = scorer.score(contract)
    contract = route_contract(contract)
    print(f"  refresh -> landscape, hunt_plan, raw/  scope={len(contract.scope)}")

    contract.external_refs = await enrich_contract_links(config, contract)
    print(f"  links -> {len(contract.external_refs)} refs")

    surfaces: dict = {}
    if not skip_recon:
        for asset in contract.assets:
            if asset.status in ("human_queue", "blocked_awaiting_env"):
                continue
            if not should_recon_asset(asset.identifier):
                print(f"  recon skip -> {asset.identifier}")
                continue
            profile = get_profile(asset.engagement_profile or "web_api", config)
            surfaces[asset.identifier] = await profile.recon(contract, asset)
        print(f"  recon -> {len(surfaces)} assets")

    auth_check = await check_test_accounts(config, contract, surfaces=surfaces)
    print(
        f"  test_accounts -> {auth_check.summary.get('status')} "
        f"(accounts={len(auth_check.accounts)}, logins={len(auth_check.login_urls)})"
    )

    contract.hunt_plan_file = update_hunt_plan_surfaces(config, contract, surfaces, disclosed)
    contract = finalize_recon_dossier(config, contract, surfaces, disclosed, stage="hunt")
    write_workspace_pointer(config, contract)
    write_hunt_bootstrap(
        config,
        contract,
        recon_note=f"portfolio build {slug} (Standoff365 public page + live recon)",
    )
    from portfolio.discovery.dossier_status import write_dossier_status, write_portfolio_status

    write_dossier_status(config, contract.slug)
    write_portfolio_status(config)

    layout = dossier_layout(config, slug)
    print(f"\n=== DOSSIER READY: {contract.dossier_dir}/ ===")
    for key, path in layout.items():
        if path:
            mark = "+" if Path(path).exists() else "-"
            print(f"  {mark} {key}: {path}")
    print(f"\nscore={contract.score:.3f} should_hunt={scorer.should_hunt(contract)}")
    return contract, scorer


async def build_bizone_dossier(
    config: AppConfig,
    slug: str,
    *,
    skip_recon: bool = True,
) -> tuple:
    disclosed = load_disclosed_reports(config)
    print(f"Fetching BI.ZONE {slug}...")
    payload = fetch_company(slug, base_url=config.monitor.bizone_base_url)
    save_bizone_raw(config, slug, payload)
    contract = parse_bizone_company(payload, base_url=config.monitor.bizone_base_url)
    scorer = ContractScorer(config)
    contract = scorer.score(contract)
    contract = route_contract(contract)

    contract = init_selected_dossier(config, contract, disclosed, stage="recon")
    contract = enrich_contract_landscape(config, contract, disclosed)
    contract.dossier_refreshed_at = datetime.now(UTC).isoformat()
    contract.hunt_plan_file = write_hunt_plan(config, contract, disclosed)

    surfaces: dict = {}
    if not skip_recon:
        for asset in contract.assets:
            if not should_recon_asset(asset.identifier):
                continue
            profile = get_profile(asset.engagement_profile or "web_api", config)
            surfaces[asset.identifier] = await profile.recon(contract, asset)

    auth_check = await check_test_accounts(config, contract, surfaces=surfaces)
    print(
        f"  test_accounts -> {auth_check.summary.get('status')} "
        f"(accounts={len(auth_check.accounts)})"
    )

    contract.hunt_plan_file = update_hunt_plan_surfaces(config, contract, surfaces, disclosed)
    contract = finalize_recon_dossier(config, contract, surfaces, disclosed, stage="hunt")
    write_workspace_pointer(config, contract)
    write_hunt_bootstrap(
        config,
        contract,
        recon_note=f"portfolio build {slug} (BI.ZONE API)",
    )
    from portfolio.discovery.dossier_status import write_dossier_status, write_portfolio_status

    write_dossier_status(config, contract.slug)
    write_portfolio_status(config)
    print(f"\n=== DOSSIER READY: {contract.dossier_dir}/ ===")
    return contract, scorer


async def build_dossiers(
    slugs: list[str],
    *,
    platform: str = "standoff365",
    skip_recon: bool = False,
    config: AppConfig | None = None,
) -> None:
    config = config or load_config()
    config.ensure_data_dirs()
    built: dict[str, dict] = {}
    for slug in slugs:
        if platform == "bizone":
            contract, _ = await build_bizone_dossier(config, slug, skip_recon=skip_recon or True)
        else:
            contract, _ = await build_standoff_dossier(config, slug, skip_recon=skip_recon)
        built[slug] = contract.model_dump(mode="json")
        print()
    merge_contracts_yaml(Path(config.data.contracts_file), built)
    print(f"contracts.yaml updated ({len(built)} program(s))")
