"""Compose validation before signal_fuzz run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scope_check import check_scope, find_scope_file

from .corpus import load_corpus, validate_seed


def _brain_content(root: Path) -> str:
    for rel in ("brain/MEMORY.md", "MEMORY.md"):
        p = root / rel
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    return ""


def validate_compose(root: Path, *, corpus_path: Path | None = None) -> tuple[bool, list[str]]:
    """Return (ok, messages). Compose traffic_informed + scope + session + schema."""
    root = Path(root)
    messages: list[str] = []
    errors: list[str] = []

    brain = _brain_content(root)
    try:
        from traffic_informed import validate_traffic_informed

        ok, reason = validate_traffic_informed(root, brain)
        messages.append(f"traffic_informed: {reason}")
        if not ok:
            errors.append(reason)
    except ImportError:
        messages.append("traffic_informed: skipped (import)")

    if "recon-skip:signal-fuzz" in brain.lower():
        messages.append("signal-fuzz skipped via recon-skip policy")
        return True, messages

    seeds = load_corpus(root, corpus_path)
    if not seeds:
        errors.append("empty or missing fuzz corpus — run build-corpus first")
    else:
        messages.append(f"corpus: {len(seeds)} seeds")

    scope = find_scope_file(root) or {}
    in_scope_count = 0
    for seed in seeds[:200]:
        ok_seed, reason = validate_seed(seed)
        if not ok_seed:
            errors.append(f"seed invalid: {reason}")
            continue
        ep = str(seed.get("endpoint") or "")
        if scope:
            verdict = check_scope(ep, scope)
            if verdict.get("status") != "IN_SCOPE":
                errors.append(f"out of scope: {ep} ({verdict.get('status')})")
            else:
                in_scope_count += 1
        else:
            in_scope_count += 1
    messages.append(f"scope_ok: {in_scope_count}/{min(len(seeds), 200)}")

    try:
        from session_bridge import list_role_sessions

        roles = list_role_sessions(root)
        messages.append(f"roles: {len(roles)} ({', '.join(roles) or 'none'})")
        cross = [s for s in seeds if s.get("cross_role_required")]
        if cross and len(roles) < 2:
            messages.append(f"warn: {len(cross)} cross-role seeds but roles < 2")
    except ImportError:
        pass

    return len(errors) == 0, messages + errors
