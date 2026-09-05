#!/usr/bin/env python3
"""Check dossier precondition before Phase 2 hunt/autopilot."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def dossier_ready(slug: str, workspace: Path | None = None) -> tuple[bool, str]:
    """Return (ready, message)."""
    ws = workspace or Path.cwd()
    dossier_contract = ROOT / "data" / "dossiers" / slug / "contract.json"
    if dossier_contract.is_file():
        return True, str(dossier_contract)

    scope = ws / "scope.yaml"
    if scope.is_file() and f"dossiers/{slug}" in scope.read_text(encoding="utf-8"):
        return True, str(scope)

    eng_contract = ROOT / "engagements" / slug / "scope.yaml"
    if eng_contract.is_file():
        text = eng_contract.read_text(encoding="utf-8")
        if "dossier_source" in text:
            return True, str(eng_contract)

    return False, (
        f"No dossier for `{slug}`. Run Phase 1 first: "
        f"`uv run python tools/portfolio.py build {slug}` or `/portfolio build {slug}`"
    )


def main(argv: list[str] | None = None) -> int:
    if not argv or len(argv) < 2:
        print("usage: dossier_precondition.py <slug> [workspace]", file=sys.stderr)
        return 2
    slug = argv[1]
    ws = Path(argv[2]) if len(argv) > 2 else Path.cwd()
    ok, msg = dossier_ready(slug, ws)
    print(json.dumps({"ready": ok, "message": msg}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
