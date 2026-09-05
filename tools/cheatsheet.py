#!/usr/bin/env python3
"""Per-target cheatsheet flywheel for hunter dispatch preambles."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from file_safety import atomic_write_text  # noqa: E402
from threat_model import slugify_target  # noqa: E402

KINDS = ("hit", "miss", "signal", "dead-end")


def cheatsheet_path(root: Path, target: str) -> Path:
    return root / "brain" / "cheatsheet" / f"{slugify_target(target)}.md"


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def append_entry(
    root: Path,
    target: str,
    kind: str,
    text: str,
    *,
    slice_id: str = "",
    vuln_class: str = "",
) -> Path:
    if kind not in KINDS:
        kind = "signal"
    path = cheatsheet_path(root, target)
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix_parts = [f"[{kind.upper()}]", _utc_now()]
    if slice_id:
        prefix_parts.append(f"slice={slice_id}")
    if vuln_class:
        prefix_parts.append(f"class={vuln_class}")
    line = f"- {' '.join(prefix_parts)}: {text.strip()}\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        atomic_write_text(path, existing.rstrip() + "\n" + line)
    else:
        header = f"# Cheatsheet: {target}\n\n"
        atomic_write_text(path, header + line)
    return path


def render_for_dispatch(root: Path, target: str, limit: int = 8) -> str:
    path = cheatsheet_path(root, target)
    parts: list[str] = []
    if path.exists():
        lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.startswith("- ")]
        if lines:
            selected = lines[-limit:]
            parts.append("CHEATSHEET (recent hits/misses on this target):\n" + "\n".join(selected))
    try:
        from signal_fuzz.mutations import BOUNDARY_STRINGS

        sample = BOUNDARY_STRINGS[:12]
        parts.append(
            "BOUNDARY_STRINGS (Bug Magnet — string-field probes, skip PII fields):\n"
            + ", ".join(repr(s) if len(s) < 20 else repr(s[:17] + "...") for s in sample)
        )
    except Exception:
        pass
    try:
        from session_bridge import render_curl_preamble

        session_block = render_curl_preamble(root)
        if session_block:
            parts.append(session_block)
    except Exception:
        pass
    return "\n\n".join(parts)


def cmd_append(args: argparse.Namespace) -> int:
    path = append_entry(
        Path(args.root),
        args.target,
        args.kind,
        args.text,
        slice_id=args.slice or "",
        vuln_class=args.vuln_class or "",
    )
    print(f"APPENDED: {path}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    text = render_for_dispatch(Path(args.root), args.target, limit=args.limit)
    if not text:
        print("(empty cheatsheet)")
        return 0
    print(text)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Target cheatsheet utilities")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    append_p = sub.add_parser("append", help="Append one cheatsheet line")
    append_p.add_argument("--target", required=True)
    append_p.add_argument("--kind", choices=KINDS, default="signal")
    append_p.add_argument("--text", required=True)
    append_p.add_argument("--slice", default="")
    append_p.add_argument("--vuln-class", default="")
    append_p.set_defaults(func=cmd_append)

    render_p = sub.add_parser("render-for-dispatch", help="Render preamble block")
    render_p.add_argument("--target", required=True)
    render_p.add_argument("--limit", type=int, default=8)
    render_p.set_defaults(func=cmd_render)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
