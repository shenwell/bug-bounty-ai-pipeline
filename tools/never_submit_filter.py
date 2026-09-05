#!/usr/bin/env python3
"""Programmatic never-submit filter for report path only (not discovery)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

FEEDER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("graphql_introspection", re.compile(r"graphql.*introspection|introspection.*alone", re.I)),
    ("missing_headers", re.compile(r"missing (csp|hsts|x-frame|security header)", re.I)),
    ("open_redirect_alone", re.compile(r"open redirect(?!.*oauth|.*chain|.*token)", re.I)),
    ("cors_wildcard", re.compile(r"cors.*wildcard(?!.*exfil|.*credentialed)", re.I)),
    ("ssrf_dns_only", re.compile(r"ssrf.*dns.?only|dns.?only.*ssrf", re.I)),
    ("logout_csrf", re.compile(r"logout csrf", re.I)),
    ("banner_disclosure", re.compile(r"banner|version disclosure(?!.*cve)", re.I)),
]


def check_finding(record: dict[str, Any]) -> dict[str, Any]:
    title = str(record.get("title", ""))
    cls = str(record.get("class", ""))
    combined = f"{title} {cls}"
    chain_id = record.get("chain_id") or record.get("gates", {}).get("chain_id")
    for name, pattern in FEEDER_PATTERNS:
        if pattern.search(combined):
            if chain_id:
                return {"block": False, "reason": f"feeder {name} allowed with chain_id"}
            return {
                "block": True,
                "reason": f"never-submit class {name} without chain",
                "suggest": "/chain",
            }
    return {"block": False, "reason": "not on never-submit list"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Never-submit report filter")
    parser.add_argument("--finding", required=True, help="Path to finding JSON")
    args = parser.parse_args()
    from pathlib import Path

    data = json.loads(Path(args.finding).read_text(encoding="utf-8"))
    result = check_finding(data)
    print(json.dumps(result))
    sys.exit(2 if result.get("block") else 0)


if __name__ == "__main__":
    main()
