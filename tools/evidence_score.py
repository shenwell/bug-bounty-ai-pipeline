#!/usr/bin/env python3
"""Deterministic evidence quality score for finding gate trail."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from finding_record import load_finding, update_gate  # noqa: E402

THEORETICAL_RE = re.compile(
    r"\b(could|might|may|theoretically|potentially|possibly)\b",
    re.I,
)
DNS_ONLY_RE = re.compile(r"\bdns[- ]?(only|callback)\b", re.I)

ACCESS_CLASSES = frozenset(
    {"idor", "bac", "privilege-escalation", "business-logic", "auth-bypass", "mass-assignment"}
)
CLIENT_CLASSES = re.compile(r"xss|dom|postmessage|prototype", re.I)


def score_finding(record: dict[str, Any]) -> dict[str, Any]:
    """Return {score, decision, reasons[]}. decision PASS if score >= 75."""
    score = 50
    reasons: list[str] = []

    evidence = record.get("evidence") or {}
    gates = record.get("gates") or {}
    cls = str(record.get("class", "")).lower()
    title = str(record.get("title", ""))

    witness = gates.get("witness") or {}
    if witness.get("ok") is True:
        score += 15
        reasons.append("+15 witness ok")
    else:
        score -= 25
        reasons.append("-25 witness not ok")

    exploit = (evidence.get("exploit_curl") or "").strip()
    readback = (evidence.get("readback_curl") or "").strip()
    marker = (evidence.get("marker") or "").strip()

    if readback and marker:
        score += 30
        reasons.append("+30 readback curl + marker")
    elif readback:
        score += 20
        reasons.append("+20 readback curl")
    elif marker:
        score += 10
        reasons.append("+10 marker only")

    if cls in ACCESS_CLASSES and not (readback and marker):
        score -= 20
        reasons.append("-20 access-control class without readback+marker")

    if cls == "ssrf" and DNS_ONLY_RE.search(marker + title):
        score -= 50
        reasons.append("-50 DNS-only SSRF")

    if THEORETICAL_RE.search(title):
        score -= 40
        reasons.append("-40 theoretical language in title")

    bv = gates.get("browser_verifier") or {}
    if CLIENT_CLASSES.search(cls):
        verdict = str(bv.get("verdict", "")).lower()
        if verdict in {"browser_confirmed", "browser_partial", "confirmed", "partial"}:
            score += 15
            reasons.append("+15 browser verifier pass")
        else:
            score -= 30
            reasons.append("-30 client-side class without browser verification")

    if gates.get("devils_advocate", {}).get("verdict") == "KILLED":
        score -= 40
        reasons.append("-40 devils advocate killed")

    score = max(0, min(100, score))
    decision = "PASS" if score >= 75 else "FAIL"
    return {"score": score, "decision": decision, "reasons": reasons}


def cmd_score(args: argparse.Namespace) -> int:
    path = Path(args.finding)
    record = load_finding(path)
    if not record:
        print(f"NOT FOUND: {path}", file=sys.stderr)
        return 1
    result = score_finding(record)
    print(json.dumps(result, indent=2))
    if args.update_gate:
        update_gate(Path(args.root), path, "evidence_score", result)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Evidence quality scorer")
    parser.add_argument("--finding", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--update-gate", action="store_true", help="Write score to finding JSON")
    args = parser.parse_args()
    sys.exit(cmd_score(args))


if __name__ == "__main__":
    main()
