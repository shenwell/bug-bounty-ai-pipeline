#!/usr/bin/env python3
"""Multi-wave autopilot ledger."""

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
from focus_areas import focus_areas_path, load_focus_areas, next_pending_slice, update_slice_status  # noqa: E402
from threat_model import slugify_target  # noqa: E402


def wave_ledger_path(root: Path, target: str) -> Path:
    return root / "brain" / "waves" / f"{slugify_target(target)}.json"


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def empty_ledger(target: str) -> dict:
    return {
        "version": 1,
        "target": target,
        "current_wave": 0,
        "waves": [],
        "next_slices": [],
        "known_shallow": [],
        "updated_at": _utc_now_iso(),
    }


def load_ledger(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_ledger(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = dict(doc)
    doc["updated_at"] = _utc_now_iso()
    atomic_write_text(path, json.dumps(doc, indent=2) + "\n")


def start_wave(root: Path, target: str, max_waves: int = 1) -> dict:
    path = wave_ledger_path(root, target)
    doc = load_ledger(path) or empty_ledger(target)
    fa = load_focus_areas(focus_areas_path(root, target))
    pending = next_pending_slice(fa) if fa else None
    wave_no = int(doc.get("current_wave") or 0) + 1
    if wave_no > max_waves and max_waves > 0:
        return doc
    wave = {
        "wave": wave_no,
        "slice_id": pending.get("id") if pending else "",
        "slices_completed": [],
        "classes_completed": [],
        "signals": [],
        "started_at": _utc_now_iso(),
        "ended_at": None,
    }
    doc["current_wave"] = wave_no
    doc.setdefault("waves", []).append(wave)
    if fa:
        doc["next_slices"] = [
            s.get("id") for s in fa.get("slices") or [] if s.get("status") in ("pending", "in_progress")
        ]
    save_ledger(path, doc)
    if pending and fa:
        fa = update_slice_status(fa, pending["id"], "in_progress")
        atomic_write_text(focus_areas_path(root, target), json.dumps(fa, indent=2) + "\n")
    return doc


def complete_slice(
    root: Path,
    target: str,
    slice_id: str,
    *,
    classes: list[str] | None = None,
    signals: list[str] | None = None,
) -> dict:
    path = wave_ledger_path(root, target)
    doc = load_ledger(path) or empty_ledger(target)
    waves = doc.get("waves") or []
    if not waves:
        start_wave(root, target)
        doc = load_ledger(path) or empty_ledger(target)
        waves = doc.get("waves") or []
    wave = waves[-1]
    if slice_id and slice_id not in wave.get("slices_completed", []):
        wave.setdefault("slices_completed", []).append(slice_id)
    for cls in classes or []:
        if cls not in wave.get("classes_completed", []):
            wave.setdefault("classes_completed", []).append(cls)
    for sig in signals or []:
        if sig not in wave.get("signals", []):
            wave.setdefault("signals", []).append(sig)
    fa_path = focus_areas_path(root, target)
    fa = load_focus_areas(fa_path)
    if fa and slice_id:
        fa = update_slice_status(fa, slice_id, "exhausted")
        atomic_write_text(fa_path, json.dumps(fa, indent=2) + "\n")
    save_ledger(path, doc)
    return doc


def complete_wave(root: Path, target: str) -> dict:
    path = wave_ledger_path(root, target)
    doc = load_ledger(path) or empty_ledger(target)
    waves = doc.get("waves") or []
    if waves:
        waves[-1]["ended_at"] = _utc_now_iso()
    save_ledger(path, doc)
    return doc


def add_shallow(root: Path, target: str, note: str) -> None:
    path = wave_ledger_path(root, target)
    doc = load_ledger(path) or empty_ledger(target)
    shallow = doc.setdefault("known_shallow", [])
    if note not in shallow:
        shallow.append(note)
    save_ledger(path, doc)


def cmd_start(args: argparse.Namespace) -> int:
    doc = start_wave(Path(args.root), args.target, max_waves=args.max_waves)
    print(json.dumps(doc, indent=2))
    return 0


def cmd_complete_slice(args: argparse.Namespace) -> int:
    classes = [c.strip() for c in (args.classes or "").split(",") if c.strip()]
    signals = [s.strip() for s in (args.signals or "").split(",") if s.strip()]
    doc = complete_slice(Path(args.root), args.target, args.slice_id, classes=classes, signals=signals)
    print(json.dumps(doc, indent=2))
    return 0


def cmd_complete_wave(args: argparse.Namespace) -> int:
    doc = complete_wave(Path(args.root), args.target)
    print(json.dumps(doc, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    path = wave_ledger_path(Path(args.root), args.target)
    doc = load_ledger(path)
    if not doc:
        print(f"MISSING: {path}")
        return 1
    print(json.dumps(doc, indent=2))
    return 0


def cmd_add_shallow(args: argparse.Namespace) -> int:
    add_shallow(Path(args.root), args.target, args.note)
    print(f"ADDED shallow: {args.note}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Wave ledger for multi-wave autopilot")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Start next wave")
    start.add_argument("--target", required=True)
    start.add_argument("--max-waves", type=int, default=99)
    start.set_defaults(func=cmd_start)

    cs = sub.add_parser("complete-slice", help="Mark slice complete in current wave")
    cs.add_argument("--target", required=True)
    cs.add_argument("--slice-id", required=True)
    cs.add_argument("--classes", default="")
    cs.add_argument("--signals", default="")
    cs.set_defaults(func=cmd_complete_slice)

    cw = sub.add_parser("complete-wave", help="End current wave")
    cw.add_argument("--target", required=True)
    cw.set_defaults(func=cmd_complete_wave)

    st = sub.add_parser("status", help="Show ledger")
    st.add_argument("--target", required=True)
    st.set_defaults(func=cmd_status)

    ash = sub.add_parser("add-shallow", help="Record known-shallow sibling endpoint")
    ash.add_argument("--target", required=True)
    ash.add_argument("--note", required=True)
    ash.set_defaults(func=cmd_add_shallow)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
