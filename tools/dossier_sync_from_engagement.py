#!/usr/bin/env python3
"""Sync hunt summaries from engagement workspace back into portfolio dossier."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from portfolio.common.config import load_config


def _engagement_dir(config, slug: str) -> Path:
    base = Path(config.data.engagements_dir)
    if not base.is_absolute():
        base = ROOT / base
    direct = base / slug
    if direct.is_dir():
        return direct
    alt = ROOT / "engagements" / slug
    if alt.is_dir():
        return alt
    return direct


def sync_engagement(slug: str, *, engagement: Path | None = None, config_path: str | None = None) -> dict:
    config = load_config(config_path)
    eng = engagement or _engagement_dir(config, slug)
    dossier = Path(config.data.dossiers_dir)
    if not dossier.is_absolute():
        dossier = ROOT / dossier
    dossier = dossier / slug
    dossier.mkdir(parents=True, exist_ok=True)
    hunt_dst = dossier / "hunt"
    hunt_dst.mkdir(exist_ok=True)

    copied: list[str] = []
    eng_hunt = eng / "hunt"
    if eng_hunt.is_dir():
        for pattern in ("*-summary.md", "00-pipeline-phases.md", "03-leads.md"):
            for src in eng_hunt.glob(pattern):
                dst = hunt_dst / src.name
                shutil.copy2(src, dst)
                copied.append(f"hunt/{src.name}")

    for name in ("landscape.md", "hunt_plan.md"):
        src = eng / name
        if src.is_file():
            shutil.copy2(src, dossier / name)
            copied.append(name)

    from portfolio.discovery.dossier_status import write_dossier_status, write_portfolio_status

    write_dossier_status(config, slug)
    write_portfolio_status(config)
    return {"slug": slug, "engagement": str(eng), "dossier": str(dossier), "copied": copied}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="Program slug")
    parser.add_argument("--engagement", type=Path, default=None, help="Override engagement path")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    if not args.engagement and not _engagement_dir(load_config(args.config), args.slug).is_dir():
        print(f"Engagement not found for {args.slug}", file=sys.stderr)
        return 1
    result = sync_engagement(args.slug, engagement=args.engagement, config_path=args.config)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
