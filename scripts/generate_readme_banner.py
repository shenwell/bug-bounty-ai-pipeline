#!/usr/bin/env python3
"""Generate README ASCII banner — matches ai-software-factory-pipeline layout."""
from __future__ import annotations

from pathlib import Path

import pyfiglet

INNER = 88  # chars between ║ and ║ (border line length = INNER + 2)
REPO_ROOT = Path(__file__).resolve().parent.parent
FONT = "ansi_shadow"
BUG_BOUNTY_LETTER_GAP = 0
BUG_BOUNTY_WORD_GAP = 3
MAX_ART = INNER - 1  # pad_art adds one leading space


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


def letter_rows(ch: str) -> list[str]:
    rows = [ln.rstrip() for ln in pyfiglet.figlet_format(ch, font=FONT).splitlines() if ln.strip()]
    if len(rows) != 6:
        raise ValueError(f"expected 6 rows for letter {ch!r}, got {len(rows)}")
    return rows


def word_rows(word: str, letter_gap: int) -> list[str]:
    blocks = [letter_rows(c) for c in word]
    spacer = " " * letter_gap
    return [spacer.join(b[i] for b in blocks) for i in range(6)]


def merge_words_horizontal(words: list[str], letter_gap: int, word_gap: int) -> list[str]:
    """Two words on the same 6 rows — per-letter columns (not whole-word figlet join)."""
    parts = [word_rows(w, letter_gap) for w in words]
    wg = " " * word_gap
    merged = [wg.join(parts[j][i] for j in range(len(parts))) for i in range(6)]
    width = max(len(ln) for ln in merged)
    if width > MAX_ART:
        raise ValueError(f"merged art too wide ({width} > {MAX_ART})")
    return merged


def pick_bug_bounty_merge() -> list[str]:
    for letter_gap in (0, 1):
        for word_gap in range(6, 0, -1):
            try:
                return merge_words_horizontal(["BUG", "BOUNTY"], letter_gap, word_gap)
            except ValueError:
                continue
    raise RuntimeError("could not fit BUG BOUNTY in one 6-row block")


def pad_art(line: str) -> str:
    return (" " + line.rstrip()).ljust(INNER)[:INNER]


def single_block(text: str) -> list[str]:
    return [pad_art(ln) for ln in figlet_block(text)]


def bug_bounty_block() -> list[str]:
    return [pad_art(ln) for ln in pick_bug_bounty_merge()]


def build_banner() -> str:
    lines = [
        border_top(),
        empty(),
        *map(row, bug_bounty_block()),
        empty(),
        *map(row, single_block("PIPELINE")),
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
