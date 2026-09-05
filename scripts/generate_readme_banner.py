#!/usr/bin/env python3
"""Generate README ASCII banner — inner width 65 (ai-game-factory-pipeline)."""
from __future__ import annotations

from pathlib import Path

import pyfiglet

INNER = 65
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


def figlet_rows(text: str) -> list[str]:
    """Render block letters; center each row to INNER width."""
    rendered = pyfiglet.figlet_format(text, font=FONT)
    rows: list[str] = []
    for line in rendered.splitlines():
        stripped = line.rstrip()
        if not stripped:
            continue
        if len(stripped) > INNER:
            raise ValueError(f"{text!r} row too wide ({len(stripped)}): {stripped!r}")
        rows.append(stripped.center(INNER))
    if not rows:
        raise ValueError(f"empty figlet for {text!r}")
    return rows


def build_banner() -> str:
    lines = [border_top(), empty()]
    for word in ("BUG", "BOUNTY"):
        lines.extend(row(r) for r in figlet_rows(word))
    lines.append(empty())
    lines.extend(row(r) for r in figlet_rows("PIPELINE"))
    lines.extend(
        [
            empty(),
            row("  Bug bounty AI pipeline — dossiers → hunt / autopilot / submit "),
            row("     Cursor · memo-session-skill · goal-mode · interceptor       "),
            row("  /portfolio · /new · /sync · /hunt · /autopilot · /validate    "),
            row(" git clone https://github.com/shenwell/bug-bounty-ai-pipeline    "),
            empty(),
            border_bottom(),
        ]
    )
    return "```\n" + "\n".join(lines) + "\n```"


def main() -> None:
    readme = REPO_ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    start = text.index("```")
    end = text.index("```", start + 3) + 3
    readme.write_text(text[:start] + build_banner() + text[end:], encoding="utf-8")


if __name__ == "__main__":
    main()
