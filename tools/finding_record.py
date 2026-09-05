#!/usr/bin/env python3
"""Canonical structured finding records for the validation pipeline."""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from file_safety import atomic_write_text  # noqa: E402

VALID_STATUSES = {"potential", "confirmed", "killed", "reported"}
GATE_KEYS = (
    "witness",
    "validator",
    "browser_verifier",
    "devils_advocate",
    "evidence_score",
    "judge",
)
JSON_REF_RE = re.compile(r"json:(evidence/[^\s]+)")


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def finding_path(root: Path, host: str, finding_id: str) -> Path:
    return root / "evidence" / host / "findings" / f"{finding_id}.json"


def empty_finding(
    *,
    target: str,
    host: str,
    vuln_class: str,
    title: str = "",
    severity_claimed: str = "medium",
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "target": target,
        "host": host,
        "class": vuln_class,
        "title": title,
        "severity_claimed": severity_claimed,
        "preconditions": [],
        "evidence": {
            "exploit_curl": "",
            "readback_curl": "",
            "marker": "",
        },
        "gates": {key: None for key in GATE_KEYS},
        "status": "potential",
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
    }


def load_finding(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save_finding(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(record)
    record["updated_at"] = _utc_now_iso()
    atomic_write_text(path, json.dumps(record, indent=2) + "\n")


def create_finding(root: Path, record: dict[str, Any]) -> Path:
    host = record.get("host") or record.get("target") or "unknown"
    fid = record.get("id") or str(uuid.uuid4())
    record["id"] = fid
    path = finding_path(root, host, fid)
    save_finding(path, record)
    return path


def update_gate(root: Path, path: Path, gate: str, payload: dict[str, Any]) -> dict[str, Any]:
    if gate not in GATE_KEYS:
        raise ValueError(f"unknown gate: {gate}")
    record = load_finding(path)
    if not record:
        raise FileNotFoundError(path)
    gates = dict(record.get("gates") or {})
    gates[gate] = payload
    record["gates"] = gates
    if gate == "validator" and payload.get("decision") == "PASS":
        record["status"] = "potential"
    if gate == "judge" and payload.get("verdict") == "CONFIRM":
        record["status"] = "confirmed"
    if gate == "devils_advocate" and payload.get("verdict") == "KILLED":
        record["status"] = "killed"
    if gate == "witness" and payload.get("ok") is False:
        record["status"] = "potential"
    save_finding(path, record)
    return record


def brain_line(record: dict[str, Any], path: Path) -> str:
    rel = path.as_posix()
    if rel.startswith("./"):
        rel = rel[2:]
    status = record.get("status", "potential").upper()
    cls = record.get("class", "unknown")
    return f"- [{status}] {cls} — json:{rel}"


def parse_json_ref_from_brain(line: str) -> Path | None:
    match = JSON_REF_RE.search(line)
    if not match:
        return None
    return Path(match.group(1))


def gates_complete_for_confirm(record: dict[str, Any]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    gates = record.get("gates") or {}
    validator = gates.get("validator") or {}
    if validator.get("decision") != "PASS":
        missing.append("validator:PASS")
    da = gates.get("devils_advocate") or {}
    if str(da.get("verdict", "")).upper() not in {"SURVIVES", "DOWNGRADE"}:
        missing.append("devils-advocate:SURVIVES|DOWNGRADE")
    witness = gates.get("witness") or {}
    if witness.get("ok") is not True:
        missing.append("witness:ok")
    ev = gates.get("evidence_score") or {}
    if int(ev.get("score", 0) or 0) < 75:
        missing.append("evidence_score>=75")
    cls = str(record.get("class", "")).lower()
    if re.search(r"xss|dom|postmessage|prototype", cls):
        bv = gates.get("browser_verifier") or {}
        if str(bv.get("verdict", "")).lower() not in {"browser_confirmed", "browser_partial", "confirmed", "partial"}:
            missing.append("browser-verified")
    return (len(missing) == 0, missing)


def cmd_create(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    record = empty_finding(
        target=args.target,
        host=args.host or args.target,
        vuln_class=args.vuln_class,
        title=args.title or "",
        severity_claimed=args.severity or "medium",
    )
    if args.exploit_curl:
        record["evidence"]["exploit_curl"] = args.exploit_curl
    if args.readback_curl:
        record["evidence"]["readback_curl"] = args.readback_curl
    if args.marker:
        record["evidence"]["marker"] = args.marker
    path = create_finding(root, record)
    print(json.dumps({"path": str(path), "id": record["id"], "brain_line": brain_line(record, path)}))
    return 0


def cmd_gate_update(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path = Path(args.finding)
    payload = json.loads(args.payload) if args.payload else {}
    if args.witness:
        from witness import evaluate_witness

        record = load_finding(path)
        if not record:
            print(f"NOT FOUND: {path}", file=sys.stderr)
            return 1
        payload = evaluate_witness(record)
    record = update_gate(root, path, args.gate, payload)
    print(json.dumps(record, indent=2))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    record = load_finding(Path(args.finding))
    if not record:
        print("NOT FOUND")
        return 1
    ok, missing = gates_complete_for_confirm(record)
    print(json.dumps({"ok": ok, "missing": missing}))
    return 0 if ok else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Structured finding records")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a new finding JSON")
    create.add_argument("--target", required=True)
    create.add_argument("--host", default="")
    create.add_argument("--vuln-class", required=True)
    create.add_argument("--title", default="")
    create.add_argument("--severity", default="medium")
    create.add_argument("--exploit-curl", default="")
    create.add_argument("--readback-curl", default="")
    create.add_argument("--marker", default="")
    create.set_defaults(func=cmd_create)

    gu = sub.add_parser("gate-update", help="Update one gate on a finding")
    gu.add_argument("--finding", required=True)
    gu.add_argument("--gate", required=True, choices=GATE_KEYS)
    gu.add_argument("--payload", default="{}")
    gu.add_argument("--witness", action="store_true", help="Run programmatic witness")
    gu.set_defaults(func=cmd_gate_update)

    chk = sub.add_parser("check", help="Check if finding gates are complete")
    chk.add_argument("--finding", required=True)
    chk.set_defaults(func=cmd_check)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
