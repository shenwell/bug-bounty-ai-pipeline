#!/usr/bin/env python3
"""
Cursor hook: subagentStop + stop → prepare user-proxy pending brief.

Reads hook JSON from stdin, writes brain/persona/user-proxy-pending.md via
user_persona.py, returns followup_message for the orchestrator.

Exit 0 always (fail-open) so hunts are never blocked by persona layer.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
PERSONA_TOOL = TOOLS / "user_persona.py"

SKIP_AGENTS = frozenset({"user-proxy"})


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


def _target(payload: dict) -> str:
    for key in ("target", "cwd", "workspace"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return os.environ.get("AUTOPILOT_TARGET", "")


def _status(payload: dict) -> str:
    for key in ("status", "result", "exit_status"):
        val = payload.get(key)
        if val is None:
            continue
        text = str(val).lower()
        if text in {"ok", "success", "0", "completed"}:
            return "ok"
        if text in {"fail", "error", "failed"}:
            return "fail"
    return "unknown"


def _run_on_stop(agent: str, target: str, status: str, hook_event: str) -> None:
    cmd = [
        sys.executable,
        str(PERSONA_TOOL),
        "on-stop",
        "--agent",
        agent,
        "--target",
        target,
        "--status",
        status,
        "--hook-event",
        hook_event,
    ]
    subprocess.run(cmd, cwd=ROOT, check=False)


def _followup(agent: str, hook_event: str) -> dict:
    msg = (
        f"Hook `{hook_event}`: subagent `{agent}` finished. "
        "Mandatory before the next dispatch: read `brain/persona/user-proxy-pending.md` "
        "and apply `.cursor/agents/user-proxy.md` — emit one `USER_PROXY_DECISION` block "
        "(verdict, rationale, next_action, confidence). "
        "Honor researcher vetoes; do not ask clarifying questions if persona autonomy is high."
    )
    return {"followup_message": msg}


def main() -> None:
    payload = _read_stdin()
    hook_event = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CURSOR_HOOK_EVENT", "subagentStop")
    agent = _agent_name(payload)

    if agent in SKIP_AGENTS:
        print(json.dumps({}))
        return

    target = _target(payload)
    status = _status(payload)

    if PERSONA_TOOL.exists():
        _run_on_stop(agent, target, status, hook_event)

    print(json.dumps(_followup(agent, hook_event)))


if __name__ == "__main__":
    main()
