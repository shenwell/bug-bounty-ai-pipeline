#!/usr/bin/env python3
"""Backward-compatible wrapper for portfolio build."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from portfolio.build import build_dossiers


def main() -> None:
    parser = argparse.ArgumentParser(description="Build full dossier for one or more programs")
    parser.add_argument("slug", nargs="+", help="Program slug(s)")
    parser.add_argument("--skip-recon", action="store_true")
    parser.add_argument("--platform", choices=["standoff365", "bizone"], default="standoff365")
    args = parser.parse_args()
    asyncio.run(build_dossiers(args.slug, platform=args.platform, skip_recon=args.skip_recon))


if __name__ == "__main__":
    main()
