#!/usr/bin/env python3
"""Compute CVSS score from vector string (model writes vector, tool computes score)."""

from __future__ import annotations

import argparse
import json
import re
import sys

CVSS31_RE = re.compile(r"^CVSS:3\.[01]/", re.I)
CVSS40_RE = re.compile(r"^CVSS:4\.0/", re.I)


def parse_vector(vector: str) -> dict[str, str]:
    vector = vector.strip()
    if "/" not in vector:
        return {}
    prefix, _, rest = vector.partition("/")
    metrics: dict[str, str] = {"prefix": prefix}
    for part in rest.split("/"):
        if ":" in part:
            k, v = part.split(":", 1)
            metrics[k.upper()] = v
    return metrics


def score_cvss31(vector: str) -> float | None:
    """Approximate CVSS 3.1 base score from vector (simplified calculator)."""
    m = parse_vector(vector)
    if not m:
        return None
    av = m.get("AV", "N")
    ac = m.get("AC", "L")
    pr = m.get("PR", "N")
    ui = m.get("UI", "N")
    c = m.get("C", "N")
    i = m.get("I", "N")
    a = m.get("A", "N")

    impact_map = {"N": 0.0, "L": 0.22, "H": 0.56}
    isc = 1 - (1 - impact_map.get(c, 0)) * (1 - impact_map.get(i, 0)) * (1 - impact_map.get(a, 0))
    if isc <= 0:
        return 0.0
    exploitability = 8.22
    if av == "L":
        exploitability *= 0.55
    elif av == "P":
        exploitability *= 0.2
    if ac == "H":
        exploitability *= 0.44
    if pr == "L":
        exploitability *= 0.62
    elif pr == "H":
        exploitability *= 0.27
    if ui == "R":
        exploitability *= 0.62
    if isc > 0:
        base = min(10.0, 1.08 * (isc + exploitability))
    else:
        base = 0.0
    return round(base, 1)


def score_cvss40(vector: str) -> float | None:
    """Placeholder: return None to force external calc; vector validation only."""
    if not CVSS40_RE.match(vector.strip()):
        return None
    return None


def calculate_score(vector: str) -> dict:
    vector = vector.strip()
    if CVSS31_RE.match(vector):
        score = score_cvss31(vector)
        return {"version": "3.1", "vector": vector, "score": score, "computed": score is not None}
    if CVSS40_RE.match(vector):
        return {
            "version": "4.0",
            "vector": vector,
            "score": None,
            "computed": False,
            "note": "Use NVD CVSS 4.0 calculator or FIRST API for exact score",
        }
    return {"version": "unknown", "vector": vector, "score": None, "computed": False}


def main() -> None:
    parser = argparse.ArgumentParser(description="CVSS vector score helper")
    parser.add_argument("vector", help="CVSS vector string")
    args = parser.parse_args()
    result = calculate_score(args.vector)
    print(json.dumps(result))
    if result.get("score") is None and not result.get("note"):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
