#!/usr/bin/env python3
"""Enforce platform-appropriate CVSS version on vector strings."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CVSS31_RE = re.compile(r"^CVSS:3\.[01]/", re.I)
CVSS40_RE = re.compile(r"^CVSS:4\.0/", re.I)


def expected_version(platform: str) -> str:
    p = platform.strip().lower()
    if p in {"hackerone", "h1"}:
        return "3.1"
    return "4.0"


def validate_vector(platform: str, vector: str) -> dict:
    vector = vector.strip()
    exp = expected_version(platform)
    ok = False
    reason = ""
    if exp == "3.1":
        ok = bool(CVSS31_RE.match(vector))
        reason = "HackerOne requires CVSS 3.1 vector prefix CVSS:3.0/ or CVSS:3.1/"
    else:
        ok = bool(CVSS40_RE.match(vector))
        reason = "Non-HackerOne platforms require CVSS 4.0 vector prefix CVSS:4.0/"
    return {
        "ok": ok,
        "platform": platform,
        "expected_version": exp,
        "vector": vector,
        "reason": reason if not ok else "",
    }


def platform_from_scope(root: Path) -> str:
    scope = root / "scope.yaml"
    if not scope.exists():
        return "bugcrowd"
    text = scope.read_text(encoding="utf-8").lower()
    if "hackerone" in text or "platform: h1" in text:
        return "hackerone"
    if "intigriti" in text:
        return "intigriti"
    if "bugcrowd" in text:
        return "bugcrowd"
    return "bugcrowd"


def main() -> None:
    parser = argparse.ArgumentParser(description="CVSS version guard")
    parser.add_argument("--vector", required=True)
    parser.add_argument("--platform", default="")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    platform = args.platform or platform_from_scope(Path(args.root))
    result = validate_vector(platform, args.vector)
    print(json.dumps(result))
    sys.exit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
