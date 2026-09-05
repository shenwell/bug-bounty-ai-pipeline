#!/usr/bin/env python3
"""
Cursor hook: subagentStop → append chain-pending for feeder-class findings.

Scans evidence/**/findings/*.json for witness-ok feeder signals.
Fail-open (exit 0) like user_proxy_stop.py.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHAIN_PENDING = ROOT / "brain" / "chain-pending.md"

FEEDER_CLASSES = frozenset(
    {
        "open-redirect",
        "cors",
        "cors-hunter",
        "info-disclosure",
        "csrf",
        "csrf-hunter",
        "subdomain-takeover",
        "xxe",
        "xxe-hunter",
        "file-upload",
        "race-condition",
        "business-logic",
        "privilege-escalation",
    }
)

SKIP_AGENTS = frozenset({"user-proxy", "chain-builder", "finding-judge", "sibling-mapper"})


def _read_stdin() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _agent_name(payload: dict) -> str:
    for key in ("subagent_type", "agent_name", "agentName", "name", "type"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return "unknown"


def _normalize_class(cls: str) -> str:
    cls = cls.lower().replace("_", "-")
    for feeder in FEEDER_CLASSES:
        if cls == feeder or cls.startswith(feeder):
            return feeder
    return cls


def _scan_structured_findings() -> list[tuple[str, str]]:
    """Return (vuln_class, path) for witness-ok feeders without chain marker."""
    hits: list[tuple[str, str]] = []
    evidence = ROOT / "evidence"
    if not evidence.exists():
        return hits
    for path in evidence.glob("**/findings/*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("status") == "killed":
            continue
        gates = data.get("gates") or {}
        witness = gates.get("witness") or {}
        if witness.get("ok") is not True:
            continue
        cls = _normalize_class(str(data.get("class", "")))
        if cls not in FEEDER_CLASSES:
            continue
        if data.get("chain_id") or gates.get("chain"):
            continue
        hits.append((cls, path.relative_to(ROOT).as_posix()))
    return hits


def _extract_class(payload: dict) -> str:
    for key in ("vuln_class", "class", "finding_class"):
        val = payload.get(key)
        if isinstance(val, str):
            return _normalize_class(val)
    text = json.dumps(payload).lower()
    for cls in FEEDER_CLASSES:
        if cls in text:
            return cls
    return ""


def _append_pending(agent: str, vuln_class: str, note: str) -> None:
    CHAIN_PENDING.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"- [{ts}] agent={agent} class={vuln_class} — {note}\n"
    if CHAIN_PENDING.exists():
        existing = CHAIN_PENDING.read_text(encoding="utf-8")
        if vuln_class in existing and "pending chain" in existing.lower():
            return
        CHAIN_PENDING.write_text(existing.rstrip() + "\n" + line, encoding="utf-8")
    else:
        CHAIN_PENDING.write_text(f"# Chain pending\n\n{line}", encoding="utf-8")


def main() -> None:
    payload = _read_stdin()
    agent = _agent_name(payload)
    if agent in SKIP_AGENTS:
        sys.exit(0)

    for vuln_class, fpath in _scan_structured_findings():
        _append_pending("finding-record", vuln_class, f"json:{fpath} — chain-builder before atomic report")
        sys.exit(0)

    vuln_class = _extract_class(payload)
    if vuln_class not in FEEDER_CLASSES:
        sys.exit(0)
    status = str(payload.get("status", "")).lower()
    if status in {"kill", "killed", "exhausted"}:
        sys.exit(0)
    _append_pending(agent, vuln_class, "feeder signal — run chain-builder before atomic report")
    sys.exit(0)


if __name__ == "__main__":
    main()
