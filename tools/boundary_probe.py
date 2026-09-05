#!/usr/bin/env python3
"""Field BVA — parse 422/limit hints into cabinet intel markdown."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

LIMIT_RE = re.compile(
    r"(?:max(?:imum)?|limit|must be (?:at most|<=?))\s*[:=]?\s*(\d+)",
    re.I,
)
FIELD_RE = re.compile(r'["\']?(?:field|param|parameter)["\']?\s*[:=]\s*["\']?(\w+)', re.I)


def probes_for_type(ftype: str, limit: int | None) -> str:
    ftype = (ftype or "text").lower()
    if ftype in {"numeric", "number", "integer", "int"}:
        if limit:
            return f"0, -1, {limit-1}, {limit}, {limit+1}"
        return "0, -1, non-numeric, 2147483647"
    if limit:
        return f"empty, 1 char, {limit}, {limit+1}"
    return "empty, 1 char, unicode flood"


def parse_422_hints(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in (text or "").splitlines():
        if not any(x in line.lower() for x in ("422", "400", "validation", "invalid", "limit", "max")):
            continue
        lm = LIMIT_RE.search(line)
        fm = FIELD_RE.search(line)
        if lm or fm:
            rows.append(
                {
                    "field": fm.group(1) if fm else "unknown",
                    "limits": lm.group(1) if lm else "",
                    "hint": line.strip()[:120],
                }
            )
    return rows


def render_bva_table(rows: list[dict[str, str]], *, endpoint: str = "POST /api/...") -> str:
    lines = [
        "## Field BVA (from UI-walk)",
        "",
        "| Field | Endpoint | Type | Limits known | BVA probes |",
        "|-------|----------|------|--------------|------------|",
    ]
    if not rows:
        lines.append("| (pending) | — | — | run traffic replay | — |")
    for row in rows:
        limit = int(row["limits"]) if row.get("limits", "").isdigit() else None
        probes = probes_for_type("numeric" if limit else "text", limit)
        limits = row.get("limits") or row.get("hint", "")[:40]
        lines.append(
            f"| {row.get('field','?')} | {endpoint} | text | {limits} | {probes} |"
        )
    return "\n".join(lines) + "\n"


def append_to_intel(root: Path, table_md: str) -> Path:
    intel = root / "hunt" / "07-shared-sandbox-intel.md"
    if not intel.exists():
        intel.parent.mkdir(parents=True, exist_ok=True)
        intel.write_text("# Cabinet intel\n\n", encoding="utf-8")
    text = intel.read_text(encoding="utf-8")
    if "## Field BVA" in text:
        before, _ = text.split("## Field BVA", 1)
        text = before.rstrip() + "\n\n" + table_md
    else:
        text = text.rstrip() + "\n\n" + table_md
    intel.write_text(text, encoding="utf-8")
    return intel


def cmd_from_file(args: argparse.Namespace) -> int:
    root = Path(args.root)
    src = Path(args.file)
    text = src.read_text(encoding="utf-8", errors="replace")
    rows = parse_422_hints(text)
    table = render_bva_table(rows, endpoint=args.endpoint or "POST /api/...")
    out = append_to_intel(root, table)
    print(f"WROTE Field BVA ({len(rows)} rows) -> {out}")
    return 0


def cmd_from_jsonl(args: argparse.Namespace) -> int:
    root = Path(args.root)
    rows: list[dict[str, str]] = []
    for path in root.glob("evidence/**/signal-fuzz/attempts.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                marker = str(row.get("marker") or "")
                rows.extend(parse_422_hints(marker))
            except json.JSONDecodeError:
                pass
    table = render_bva_table(rows, endpoint=args.endpoint or "POST /api/...")
    out = append_to_intel(root, table)
    print(f"WROTE Field BVA ({len(rows)} rows) -> {out}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Field BVA boundary probe utilities")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    ff = sub.add_parser("from-file", help="Parse 422 hints from a text/log file")
    ff.add_argument("--file", required=True)
    ff.add_argument("--endpoint", default="")
    ff.set_defaults(func=cmd_from_file)

    fj = sub.add_parser("from-jsonl", help="Parse hints from signal-fuzz attempts JSONL")
    fj.add_argument("--endpoint", default="")
    fj.set_defaults(func=cmd_from_jsonl)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
