#!/usr/bin/env python3
"""Programmatic witness checks before LLM validation."""

from __future__ import annotations

import re
from typing import Any


def evaluate_witness(record: dict[str, Any]) -> dict[str, Any]:
    """Return witness gate payload: {ok, details}."""
    cls = str(record.get("class", "")).lower()
    evidence = record.get("evidence") or {}
    exploit = (evidence.get("exploit_curl") or "").strip()
    readback = (evidence.get("readback_curl") or "").strip()
    marker = (evidence.get("marker") or "").strip()

    if not exploit:
        return {"ok": False, "details": "missing exploit_curl"}

    if cls in {"idor", "bac", "privilege-escalation", "business-logic"}:
        if readback and marker:
            return {"ok": True, "details": "readback curl + marker present for access-control class"}
        return {
            "ok": False,
            "details": "IDOR/BAC requires readback_curl and marker showing cross-account delta",
        }

    if cls.startswith("xss") or cls in {"xss", "open-redirect", "header-injection"}:
        if marker or re.search(r"[<>]|%3c|script|onerror", exploit, re.I):
            return {"ok": True, "details": "reflection marker or payload present; browser-verifier required for execution"}
        return {"ok": False, "details": "XSS class requires reflection marker in evidence"}

    if cls in {"race-condition", "business-logic"} and readback:
        return {"ok": True, "details": "race/business-logic readback present"}

    if "unauth" in cls or cls == "auth-bypass":
        if readback or marker:
            return {"ok": True, "details": "unauth/auth bypass has readback or state marker"}
        return {"ok": False, "details": "auth bypass needs independent readback proving state change"}

    if cls == "ssrf":
        if marker and "dns" not in marker.lower():
            return {"ok": True, "details": "SSRF witness beyond DNS-only"}
        return {"ok": False, "details": "SSRF requires response body/timing witness, not DNS-only"}

    if marker or readback:
        return {"ok": True, "details": "generic marker/readback present"}

    return {"ok": True, "details": "exploit curl present; class-specific witness not required"}


def main() -> None:
    import argparse
    import json
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Witness evaluator")
    parser.add_argument("--finding", required=True)
    args = parser.parse_args()
    path = Path(args.finding)
    data = json.loads(path.read_text(encoding="utf-8"))
    result = evaluate_witness(data)
    print(json.dumps(result))
    sys.exit(0 if result.get("ok") else 2)


if __name__ == "__main__":
    main()
