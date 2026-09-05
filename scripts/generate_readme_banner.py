#!/usr/bin/env python3
"""Generate README ASCII banner — matches ai-software-factory-pipeline layout."""
from __future__ import annotations

from pathlib import Path

import pyfiglet

INNER = 88  # chars between ║ and ║ (border line length = INNER + 2)
REPO_ROOT = Path(__file__).resolve().parent.parent
FONT = "ansi_shadow"


def border_top() -> str:
    return "╔" + "═" * INNER + "╗"


def border_bottom() -> str:
    return "╚" + "═" * INNER + "╝"


def row(text: str) -> str:
    if len(text) > INNER:
        raise ValueError(f"{len(text)} > {INNER}: {text!r}")
    line = f"║{text.ljust(INNER)}║"
    if len(line) != INNER + 2:
        raise ValueError(f"bad line len {len(line)} for {text!r}")
    return line


def empty() -> str:
    return row("")


def figlet_block(text: str) -> list[str]:
    lines = [ln.rstrip() for ln in pyfiglet.figlet_format(text, font=FONT).splitlines() if ln.strip()]
    if len(lines) != 6:
        raise ValueError(f"expected 6 figlet rows for {text!r}, got {len(lines)}")
    return lines


def pad_art(line: str) -> str:
    """Leading space + left align — same as ai-software-factory-pipeline."""
    return (" " + line.rstrip()).ljust(INNER)[:INNER]


def join_words(left: str, right: str, gap: int = 2) -> list[str]:
    """Side-by-side block letters on one row (AI GAME / BUG BOUNTY style)."""
    a, b = figlet_block(left), figlet_block(right)
    spacer = " " * gap
    return [pad_art(x + spacer + y) for x, y in zip(a, b, strict=True)]


def single_block(text: str) -> list[str]:
    return [pad_art(ln) for ln in figlet_block(text)]


def build_banner() -> str:
    bug_bounty = join_words("BUG", "BOUNTY")
    pipeline = single_block("PIPELINE")

    lines = [
        border_top(),
        empty(),
        *map(row, bug_bounty),
        empty(),
        *map(row, pipeline),
        empty(),
        row("        Two-phase bug bounty pipeline for Cursor — dossiers to hunt / submit        "),
        row("          Cursor · memo-session-skill · goal-mode · interceptor                       "),
        row("       /portfolio · /new · /sync · /hunt · /autopilot · /validate · MIT              "),
        row("     git clone https://github.com/shenwell/bug-bounty-ai-pipeline                    "),
        empty(),
        border_bottom(),
    ]
    return "```\n" + "\n".join(lines) + "\n```"


def main() -> None:
    readme = REPO_ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    start = text.index("```")
    end = text.index("```", start + 3) + 3
    readme.write_text(text[:start] + build_banner() + text[end:], encoding="utf-8")


if __name__ == "__main__":
    main()
