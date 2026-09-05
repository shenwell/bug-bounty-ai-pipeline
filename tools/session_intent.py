#!/usr/bin/env python3
"""Session intent — thin aim pointer for pipeline v4.

Stores per-session hunting focus as references into threat-model and focus-areas.
Does NOT duplicate crown jewels or priority classes — resolves them at read time.

Usage:
    python3 tools/session_intent.py write --target example.com \\
        --session-goal "billing IDOR" --slice billing_wallet \\
        --classes idor,business-logic --crown-jewel-ref billing_data
    python3 tools/session_intent.py show --target example.com
    python3 tools/session_intent.py validate --target example.com
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from file_safety import atomic_write_text  # noqa: E402
from focus_areas import get_slice, load_focus_areas  # noqa: E402
from threat_model import load_threat_model, slugify_target, threat_model_path  # noqa: E402

INTENT_VERSION = 1
MAX_SELECTED_CLASSES = 2


def session_intent_path(root: Path, target: str) -> Path:
    return root / "brain" / "session-intent" / f"{slugify_target(target)}.json"


def empty_session_intent(target: str) -> dict:
    return {
        "version": INTENT_VERSION,
        "target": target,
        "updated_at": _utc_now_iso(),
        "session_goal": "",
        "primary_crown_jewel_ref": "",
        "selected_slice_id": "",
        "selected_classes": [],
        "differential_axis": "",
        "route": "feature-based",
    }


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def load_session_intent(root: Path, target: str) -> dict | None:
    path = session_intent_path(root, target)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save_session_intent(root: Path, intent: dict) -> Path:
    target = intent.get("target") or "unknown"
    path = session_intent_path(root, target)
    path.parent.mkdir(parents=True, exist_ok=True)
    intent = dict(intent)
    intent["updated_at"] = _utc_now_iso()
    atomic_write_text(path, json.dumps(intent, indent=2) + "\n")
    return path


def resolve_crown_jewel(root: Path, target: str, jewel_ref: str) -> str | None:
    if not jewel_ref:
        return None
    tm_json = threat_model_path(root, target, as_json=True)
    tm_md = threat_model_path(root, target, as_json=False)
    tm = load_threat_model(tm_json) if tm_json.exists() else load_threat_model(tm_md)
    if not tm:
        return None
    ref_lower = jewel_ref.lower()
    for idx, jewel in enumerate(tm.get("crown_jewels") or []):
        text = str(jewel).lower()
        if ref_lower in text or ref_lower == f"jewel_{idx}":
            return str(jewel)
    return None


def resolve_slice_classes(root: Path, target: str, slice_id: str) -> list[str]:
    if not slice_id:
        return []
    fa_path = root / "brain" / "focus-areas" / f"{slugify_target(target)}.json"
    fa = load_focus_areas(fa_path)
    if not fa:
        return []
    row = get_slice(fa, slice_id)
    if not row:
        return []
    return list(row.get("priority_classes") or [])


def resolve_session_intent(root: Path, target: str) -> dict:
    """Merge stored intent with resolved threat-model / focus-area references."""
    intent = load_session_intent(root, target) or empty_session_intent(target)
    jewel_ref = intent.get("primary_crown_jewel_ref") or ""
    slice_id = intent.get("selected_slice_id") or ""
    slice_classes = resolve_slice_classes(root, target, slice_id)
    selected = [c.lower().replace("_", "-") for c in (intent.get("selected_classes") or [])]
    if slice_classes and selected:
        allowed = {c.lower().replace("_", "-") for c in slice_classes}
        selected = [c for c in selected if c in allowed]
    return {
        **intent,
        "resolved_crown_jewel": resolve_crown_jewel(root, target, jewel_ref),
        "resolved_slice_classes": slice_classes,
        "resolved_selected_classes": selected,
    }


def session_intent_boosts(root: Path, target: str) -> dict[str, float]:
    """Score boosts for intel_engine: selected classes get +40, others +5 floor."""
    resolved = resolve_session_intent(root, target)
    selected = resolved.get("resolved_selected_classes") or []
    if not selected:
        return {}
    boosts: dict[str, float] = {}
    for idx, cls in enumerate(selected[:MAX_SELECTED_CLASSES]):
        boosts[cls.lower().replace("_", "-")] = 40.0 - idx * 5.0
    return boosts


def validate_session_intent(root: Path, target: str) -> tuple[bool, list[str]]:
    issues: list[str] = []
    intent = load_session_intent(root, target)
    if not intent:
        issues.append("session-intent missing — fill via Phase 0 /hunt before first HTTP")
        return False, issues
    if not (intent.get("session_goal") or "").strip():
        issues.append("session_goal is empty")
    selected = intent.get("selected_classes") or []
    if not selected:
        issues.append("selected_classes is empty — pick max 2 classes")
    elif len(selected) > MAX_SELECTED_CLASSES:
        issues.append(f"selected_classes has {len(selected)} entries; max is {MAX_SELECTED_CLASSES}")
    slice_id = intent.get("selected_slice_id") or ""
    if slice_id:
        fa_path = root / "brain" / "focus-areas" / f"{slugify_target(target)}.json"
        fa = load_focus_areas(fa_path)
        if fa and not get_slice(fa, slice_id):
            issues.append(f"selected_slice_id '{slice_id}' not found in focus-areas")
    jewel_ref = intent.get("primary_crown_jewel_ref") or ""
    if jewel_ref and not resolve_crown_jewel(root, target, jewel_ref):
        issues.append(f"primary_crown_jewel_ref '{jewel_ref}' not resolved in threat-model")
    return len(issues) == 0, issues


def cmd_write(args: argparse.Namespace) -> int:
    root = Path(args.root)
    classes = [c.strip() for c in (args.classes or "").split(",") if c.strip()]
    if len(classes) > MAX_SELECTED_CLASSES:
        print(f"ERROR: max {MAX_SELECTED_CLASSES} selected_classes", file=sys.stderr)
        return 1
    intent = load_session_intent(root, args.target) or empty_session_intent(args.target)
    if args.session_goal:
        intent["session_goal"] = args.session_goal
    if args.slice:
        intent["selected_slice_id"] = args.slice
    if classes:
        intent["selected_classes"] = classes
    if args.crown_jewel_ref:
        intent["primary_crown_jewel_ref"] = args.crown_jewel_ref
    if args.differential_axis:
        intent["differential_axis"] = args.differential_axis
    if args.route:
        intent["route"] = args.route
    path = save_session_intent(root, intent)
    print(f"WROTE: {path}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    resolved = resolve_session_intent(Path(args.root), args.target)
    print(json.dumps(resolved, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    ok, issues = validate_session_intent(Path(args.root), args.target)
    if ok:
        print("OK session-intent valid")
        return 0
    for issue in issues:
        print(f"FAIL: {issue}")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Session intent (thin aim pointer)")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    wr = sub.add_parser("write", help="Write session-intent.json")
    wr.add_argument("--target", required=True)
    wr.add_argument("--session-goal", default="")
    wr.add_argument("--slice", default="")
    wr.add_argument("--classes", default="", help="Comma-separated, max 2")
    wr.add_argument("--crown-jewel-ref", default="")
    wr.add_argument("--differential-axis", default="")
    wr.add_argument("--route", default="", choices=["", "feature-based", "vuln-based"])
    wr.set_defaults(func=cmd_write)

    sh = sub.add_parser("show", help="Show resolved session intent")
    sh.add_argument("--target", required=True)
    sh.set_defaults(func=cmd_show)

    val = sub.add_parser("validate", help="Validate session intent for gate")
    val.add_argument("--target", required=True)
    val.set_defaults(func=cmd_validate)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
