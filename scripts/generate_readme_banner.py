#!/usr/bin/env python3
"""Generate README ASCII banner — inner width 65 (ai-game-factory-pipeline)."""
from pathlib import Path

INNER = 65
REPO_ROOT = Path(__file__).resolve().parent.parent

BOUNTY = [
    "██████╗  ██████╗ ██╗   ██╗███╗   ██╗████████╗██╗   ██╗          ",
    "██╔══██╗██╔═══██╗██║   ██║████╗  ██║╚══██╔══╝╚██╗ ██╔╝          ",
    "██████╔╝██║   ██║██║   ██║██╔██╗ ██║   ██║    ╚████╔╝           ",
    "██╔══██╗██║   ██║██║   ██║██║╚██╗██║   ██║     ╚██╔╝            ",
    "██████╔╝╚██████╔╝╚██████╔╝██║ ╚████║   ██║      ██║             ",
    "╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝   ╚═╝      ╚═╝             ",
]

PIPELINE = [
    " ██████╗ ██╗██████╗ ███████╗██╗     ██╗███╗   ██╗███████╗        ",
    " ██╔══██╗██║██╔══██╗██╔════╝██║     ██║████╗  ██║██╔════╝        ",
    " ██████╔╝██║██████╔╝█████╗  ██║     ██║██╔██╗ ██║█████╗          ",
    " ██╔═══╝ ██║██╔═══╝ ██╔══╝  ██║     ██║██║╚██╗██║██╔══╝          ",
    " ██║     ██║██║     ███████╗███████╗██║██║ ╚████║███████╗        ",
    " ╚═╝     ╚═╝╚═╝     ╚══════╝╚══════╝╚═╝╚═╝  ╚═══╝╚══════╝        ",
]


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


def build_banner() -> str:
    lines = [border_top(), empty()]
    for art in BOUNTY:
        lines.append(row(art))
    lines.append(empty())
    for art in PIPELINE:
        lines.append(row(art))
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
