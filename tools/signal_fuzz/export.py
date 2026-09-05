"""Export fuzz signals and internal state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .redaction import redact_dict

SIGNALS_DEFAULT = Path("recon/fuzz-signals.json")
STATE_DEFAULT = Path("brain/fuzz-corpus/run-state.json")


def load_run_state(root: Path) -> dict[str, Any]:
    p = root / STATE_DEFAULT
    if not p.exists():
        return {"queued_signals": [], "attempts_summary": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"queued_signals": [], "attempts_summary": {}}


def save_run_state(root: Path, state: dict[str, Any]) -> Path:
    p = root / STATE_DEFAULT
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return p


def queue_signal(state: dict[str, Any], candidate: dict[str, Any], oracle: dict[str, Any]) -> None:
    if oracle.get("signal_tier") != "oracle+readback":
        return
    sig_id = f"sf-{len(state.get('queued_signals', [])) + 1:03d}"
    entry = {
        "id": sig_id,
        "signal_tier": "oracle+readback",
        "endpoint": candidate.get("endpoint") or candidate.get("url"),
        "suggested_class": oracle.get("suggested_class") or candidate.get("class_hint", "idor"),
        "suggested_hunter": oracle.get("suggested_hunter") or "idor-hunter",
        "oracle_kind": oracle.get("kind", ""),
        "cross_role_evidence": bool(candidate.get("cross_role_required")),
        "trace_key": candidate.get("trace_key", ""),
        "repro_template": {
            "method": candidate.get("method", "GET"),
            "path": candidate.get("endpoint") or candidate.get("url"),
            "session_role": candidate.get("auth_role", "A"),
            "mutations": candidate.get("mutations") or [],
        },
        "readback_curl_template": oracle.get("readback_curl_template", ""),
        "energy": float(candidate.get("energy") or 1.0),
    }
    state.setdefault("queued_signals", []).append(entry)


def export_signals(
    root: Path,
    *,
    output: Path | None = None,
    target: str = "",
) -> tuple[Path, list[dict[str, Any]]]:
    """Export only oracle+readback tier to fuzz-signals.json."""
    state = load_run_state(root)
    signals = [
        redact_dict(s)
        for s in state.get("queued_signals", [])
        if s.get("signal_tier") == "oracle+readback"
    ]
    out = output or (root / SIGNALS_DEFAULT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(signals, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if target and signals:
        try:
            from cheatsheet import append_entry

            for sig in signals[:5]:
                append_entry(
                    root,
                    target,
                    "signal",
                    f"{sig.get('id')} {sig.get('oracle_kind')} {sig.get('endpoint')}",
                    vuln_class=str(sig.get("suggested_class") or ""),
                )
        except Exception:
            pass
    return out, signals


def load_fuzz_signals(root: Path, path: Path | None = None) -> list[dict[str, Any]]:
    p = path or (root / SIGNALS_DEFAULT)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []
