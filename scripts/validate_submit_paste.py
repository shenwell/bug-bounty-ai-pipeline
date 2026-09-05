#!/usr/bin/env python3
"""Lint final Standoff paste markdown (description block only — not drafts)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from portfolio.review.submit_text import lint_submit_paste_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paste_file", type=Path, help="reports/submit/standoff365-*-paste.md")
    parser.add_argument(
        "--lead",
        default=None,
        help="Own lead id (e.g. LEAD-024) — allowed in attachment filenames only",
    )
    args = parser.parse_args()

    text = args.paste_file.read_text(encoding="utf-8")
    issues = lint_submit_paste_file(text, lead_id=args.lead)

    if not issues:
        print(f"OK: {args.paste_file}")
        return

    print(f"FAIL: {len(issues)} issue(s) in submit paste body\n", file=sys.stderr)
    for issue in issues:
        print(f"  [{issue.rule}] {issue.message}", file=sys.stderr)
        if issue.excerpt:
            print(f"    …{issue.excerpt}…", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
