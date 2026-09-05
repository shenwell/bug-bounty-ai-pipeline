#!/usr/bin/env python3
"""Portfolio CLI — Phase 1 dossier discovery and build."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_tools_dir = str(Path(__file__).resolve().parent)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# Running as `python tools/portfolio.py` puts tools/ on sys.path[0] and shadows the portfolio package.
if sys.path and sys.path[0] == _tools_dir:
    sys.path.pop(0)
elif _tools_dir in sys.path:
    sys.path.remove(_tools_dir)

from portfolio.build import build_dossiers  # noqa: E402
from portfolio.common.config import load_config  # noqa: E402
from portfolio.discover_ops import (  # noqa: E402
    contract_candidates,
    discover_platform,
    load_contracts,
    refresh_standoff_contract,
    select_contract,
)
from portfolio.scoring.scorer import ContractScorer  # noqa: E402


def _print_scoring_breakdown(contract, scorer: ContractScorer) -> None:
    w = scorer._weights
    reward = scorer._reward_component(contract)
    scope = scorer._scope_component(contract)
    competency = scorer._competency_component(contract)
    restrictions = scorer._restrictions_component(contract)
    llm_adj, vectors, mismatch = scorer._llm_assessment(contract)
    deterministic = (
        reward * w.reward
        + scope * w.scope_size
        + competency * w.competency_match
        + restrictions * w.restrictions
    )
    print("\n=== SCORING BREAKDOWN ===")
    print(f"slug:                  {contract.slug}")
    print(f"platform:              {contract.platform}")
    print(f"reward_component:      {reward:.4f}  x {w.reward} = {reward * w.reward:.4f}")
    print(f"scope_component:       {scope:.4f}  x {w.scope_size} = {scope * w.scope_size:.4f}")
    print(f"competency_component:  {competency:.4f}  x {w.competency_match} = {competency * w.competency_match:.4f}")
    print(f"restrictions_component:{restrictions:.4f}  x {w.restrictions} = {restrictions * w.restrictions:.4f}")
    print(f"deterministic subtotal: {deterministic:.4f}")
    print(f"llm_adjustment:        {llm_adj:.4f}")
    print(f"llm_vectors:           {vectors}")
    if mismatch:
        print(f"llm_mismatch:          {mismatch}")
    print(f"stored score:          {contract.score}")
    print(f"should_hunt:           {scorer.should_hunt(contract)}")
    print(f"score_reason:          {contract.score_reason}")


def cmd_discover(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    contracts = asyncio.run(discover_platform(config, args.platform))
    print(json.dumps({"platform": args.platform, "count": len(contracts)}, indent=2))
    return 0


def cmd_candidates(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    rows = contract_candidates(config, platform=args.platform, limit=args.limit)
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    scorer = ContractScorer(config)
    contracts = load_contracts(config)
    match = next((c for c in contracts if c.slug == args.slug), None)
    if not match:
        print(f"Slug {args.slug} not in contracts.yaml", file=sys.stderr)
        return 1
    if args.platform and match.platform != args.platform:
        print(f"Platform mismatch: {match.platform} != {args.platform}", file=sys.stderr)
    _print_scoring_breakdown(match, scorer)
    return 0


def cmd_select(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    contract = select_contract(config, args.slug)
    print(json.dumps({"slug": contract.slug, "dossier_dir": contract.dossier_dir}, indent=2))
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    asyncio.run(
        build_dossiers(
            args.slug,
            platform=args.platform,
            skip_recon=args.skip_recon,
            config=config,
        )
    )
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.platform != "standoff365":
        print("refresh currently supports standoff365 only", file=sys.stderr)
        return 1
    contract = asyncio.run(refresh_standoff_contract(config, args.slug))
    print(json.dumps({"slug": contract.slug, "dossier_dir": contract.dossier_dir}, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from portfolio.discovery.dossier_status import (
        write_all_dossier_statuses,
        write_dossier_status,
        write_portfolio_status,
    )

    config = load_config(args.config)
    if args.slug:
        path = write_dossier_status(config, args.slug)
        portfolio = write_portfolio_status(config)
        print(json.dumps({"slug": args.slug, "status_md": str(path), "portfolio_md": str(portfolio)}, indent=2))
    else:
        paths = write_all_dossier_statuses(config)
        print(json.dumps({"count": len(paths) - 1, "paths": [str(p) for p in paths]}, indent=2))
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    from portfolio.record import record_finding, record_report

    config = load_config(args.config)
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if args.kind == "finding":
        path = record_finding(config, args.slug, data)
    else:
        path = record_report(config, args.slug, data)
    print(json.dumps({"saved": str(path)}, indent=2))
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    from portfolio.monitor.programs import run_programs_monitor

    config = load_config(args.config)
    result = run_programs_monitor(
        config,
        platform=args.platform,
        init=args.init,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Portfolio — dossier discovery and build (Phase 1)")
    parser.add_argument("--config", default=None, help="Path to config/portfolio.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("discover", help="Scan platform → contracts.yaml")
    p.add_argument("--platform", choices=["standoff365", "bizone"], default="standoff365")
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("candidates", help="Top should_hunt programs")
    p.add_argument("--platform", choices=["standoff365", "bizone"], default=None)
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=cmd_candidates)

    p = sub.add_parser("analyze", help="Scoring breakdown for one slug")
    p.add_argument("slug")
    p.add_argument("--platform", choices=["standoff365", "bizone"], default=None)
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("select", help="Init dossier shell for slug from contracts.yaml")
    p.add_argument("slug")
    p.set_defaults(func=cmd_select)

    p = sub.add_parser("build", help="Build full dossier")
    p.add_argument("slug", nargs="+")
    p.add_argument("--platform", choices=["standoff365", "bizone"], default="standoff365")
    p.add_argument("--skip-recon", action="store_true")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("refresh", help="Re-fetch Standoff program into dossier")
    p.add_argument("slug")
    p.add_argument("--platform", choices=["standoff365", "bizone"], default="standoff365")
    p.set_defaults(func=cmd_refresh)

    p = sub.add_parser("status", help="Regenerate STATUS.md")
    p.add_argument("slug", nargs="?", default=None)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("record", help="Save finding or report JSON into dossier")
    p.add_argument("kind", choices=["finding", "report"])
    p.add_argument("slug")
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("monitor", help="New program monitor (optional)")
    p.add_argument("--platform", choices=["standoff365", "bizone"], default="standoff365")
    p.add_argument("--init", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_monitor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
