#!/usr/bin/env python3
"""
user_persona.py — Researcher persona profile for user-proxy decisions.

Builds a compact decision model from past Cursor transcripts and explicit
feedback, then prepares context whenever a subagent or session stops.

Usage:
    python3 tools/user_persona.py init
    python3 tools/user_persona.py ingest [--transcripts-dir PATH] [--max-files N]
    python3 tools/user_persona.py brief [--json]
    python3 tools/user_persona.py record-feedback "<text>" [--kind preference|veto|correction]
    python3 tools/user_persona.py on-stop --agent <name> [--target T] [--status ok|fail|unknown]
    python3 tools/user_persona.py decisions [--limit N]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from file_safety import atomic_write_text, locked_file  # noqa: E402
from workspace_paths import get_brain_dir, get_persona_dir  # noqa: E402

DEFAULT_PROFILE = {
    "version": 1,
    "updated": None,
    "language": "ru",
    "autonomy": "high",
    "human_gate": False,
    "preferences": {
        "depth_over_breadth": True,
        "chain_before_atomic_report": True,
        "kill_weak_fast": True,
        "no_auto_commit": True,
        "no_auto_submit": True,
        "respond_in_russian": True,
        "api_first_after_login": True,
        "parallel_track_when_blocked": True,
    },
    "priority_signals": [],
    "vetoes": [
        "submit without /validate PASS",
        "report theoretical impact without proof",
        "stop after WAF 403 without bypass ladder",
        "mark class exhausted before mutation matrix",
        "auto-commit without explicit request",
    ],
    "corpus_samples": [],
    "feedback": [],
}

HEURISTIC_RULES: list[tuple[re.Pattern[str], dict]] = [
    (re.compile(r"только\s+автоном", re.I), {"autonomy": "full", "human_gate": False}),
    (re.compile(r"без\s+human\s+gate", re.I), {"human_gate": False}),
    (re.compile(r"\bP1\b", re.I), {"tag": "P1-first"}),
    (re.compile(r"\bIDOR\b", re.I), {"tag": "idor-priority"}),
    (re.compile(r"workflow", re.I), {"tag": "workflow-priority"}),
    (re.compile(r"на\s+русск", re.I), {"preference": "respond_in_russian"}),
    (re.compile(r"без\s+коммит", re.I), {"preference": "no_auto_commit"}),
    (re.compile(r"не\s+коммит", re.I), {"preference": "no_auto_commit"}),
    (re.compile(r"chain|цепоч", re.I), {"preference": "chain_before_atomic_report"}),
    (re.compile(r"глубин|depth", re.I), {"preference": "depth_over_breadth"}),
    (re.compile(r"API[- ]?first|api\s+first", re.I), {"preference": "api_first_after_login"}),
]

CORRECTION_PREFIXES = (
    "нет", "не так", "стоп", "не делай", "не надо", "wrong", "stop", "don't",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _profile_path(persona_dir: Path) -> Path:
    return persona_dir / "profile.json"


def _decisions_path(persona_dir: Path) -> Path:
    return persona_dir / "decisions.jsonl"


def _pending_path(persona_dir: Path) -> Path:
    return persona_dir / "user-proxy-pending.md"


def _corpus_path(persona_dir: Path) -> Path:
    return persona_dir / "corpus.md"


def load_profile(persona_dir: Path) -> dict:
    path = _profile_path(persona_dir)
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_PROFILE))
    return json.loads(path.read_text(encoding="utf-8"))


def save_profile(persona_dir: Path, profile: dict) -> None:
    persona_dir.mkdir(parents=True, exist_ok=True)
    profile["updated"] = _now_iso()
    atomic_write_text(_profile_path(persona_dir), json.dumps(profile, ensure_ascii=False, indent=2) + "\n")


def init_persona(persona_dir: Path) -> None:
    persona_dir.mkdir(parents=True, exist_ok=True)
    if not _profile_path(persona_dir).exists():
        save_profile(persona_dir, json.loads(json.dumps(DEFAULT_PROFILE)))
    if not _corpus_path(persona_dir).exists():
        atomic_write_text(
            _corpus_path(persona_dir),
            "# Researcher corpus (auto-ingested user messages)\n\n",
        )
    print(f"Persona initialized at {persona_dir}")


def _default_transcripts_dirs() -> list[Path]:
    home = Path.home()
    candidates = [
        Path(os.environ.get("CURSOR_TRANSCRIPTS_DIR", "")),
        home / ".cursor" / "projects",
    ]
    out: list[Path] = []
    for c in candidates:
        if c and c.exists():
            out.append(c)
    return out


def _extract_user_text(line: str) -> str | None:
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None
    if row.get("role") != "user":
        return None
    parts = row.get("message", {}).get("content", [])
    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "text":
            texts.append(part.get("text", ""))
    if not texts:
        return None
    text = "\n".join(texts)
    text = re.sub(r"<user_query>\s*", "", text)
    text = re.sub(r"</user_query>", "", text)
    text = re.sub(r"<timestamp>.*?</timestamp>\s*", "", text, flags=re.S)
    text = text.strip()
    return text or None


def _iter_transcript_files(root: Path, max_files: int) -> list[Path]:
    files = sorted(root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    # Prefer parent conversation transcripts over subagent noise
    parent = [p for p in files if "subagents" not in p.parts]
    sub = [p for p in files if "subagents" in p.parts]
    ordered = parent + sub
    return ordered[:max_files]


def ingest_transcripts(persona_dir: Path, transcripts_dir: Path | None, max_files: int) -> None:
    init_persona(persona_dir)
    profile = load_profile(persona_dir)
    roots = [transcripts_dir] if transcripts_dir else _default_transcripts_dirs()
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".jsonl":
            files.append(root)
        elif root.is_dir():
            files.extend(_iter_transcript_files(root, max_files))

    # dedupe while preserving order
    seen: set[Path] = set()
    unique_files: list[Path] = []
    for f in files:
        rp = f.resolve()
        if rp not in seen:
            seen.add(rp)
            unique_files.append(f)
    unique_files = unique_files[:max_files]

    samples: list[str] = []
    tag_counter: Counter[str] = Counter()
    feedback: list[dict] = profile.get("feedback", [])

    for path in unique_files:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            text = _extract_user_text(line)
            if not text or len(text) < 8:
                continue
            if len(text) <= 400:
                samples.append(text)
            else:
                samples.append(text[:400] + "…")

            lowered = text.lower()
            if lowered.startswith(CORRECTION_PREFIXES):
                feedback.append(
                    {
                        "ts": _now_iso(),
                        "kind": "correction",
                        "text": text[:500],
                        "source": str(path.name),
                    }
                )

            for pattern, effects in HEURISTIC_RULES:
                if pattern.search(text):
                    if "tag" in effects:
                        tag_counter[effects["tag"]] += 1
                    if "preference" in effects:
                        profile["preferences"][effects["preference"]] = True
                    if "autonomy" in effects:
                        profile["autonomy"] = effects["autonomy"]
                    if "human_gate" in effects:
                        profile["human_gate"] = effects["human_gate"]

            if re.search(r"human\s+gate", text, re.I) and not re.search(
                r"без\s+human\s+gate", text, re.I
            ):
                profile["human_gate"] = True

    # Keep newest unique samples, cap size
    deduped_samples: list[str] = []
    seen_text: set[str] = set()
    for s in reversed(samples):
        key = s[:120]
        if key in seen_text:
            continue
        seen_text.add(key)
        deduped_samples.append(s)
    deduped_samples = list(reversed(deduped_samples))[-40:]

    profile["corpus_samples"] = deduped_samples
    profile["priority_signals"] = [t for t, _ in tag_counter.most_common(12)]
    profile["feedback"] = (feedback + profile.get("feedback", []))[-80:]
    save_profile(persona_dir, profile)

    corpus_lines = ["# Researcher corpus (auto-ingested user messages)\n"]
    corpus_lines.append(f"Updated: {_now_iso()}\n")
    corpus_lines.append(f"Sources scanned: {len(unique_files)} transcript files\n\n")
    for i, sample in enumerate(deduped_samples[-25:], 1):
        corpus_lines.append(f"## Sample {i}\n\n{sample}\n\n")
    atomic_write_text(_corpus_path(persona_dir), "".join(corpus_lines))

    print(
        f"Ingested {len(unique_files)} files -> "
        f"{len(deduped_samples)} samples, "
        f"{len(profile['priority_signals'])} priority signals"
    )


def record_feedback(persona_dir: Path, text: str, kind: str) -> None:
    init_persona(persona_dir)
    profile = load_profile(persona_dir)
    entry = {"ts": _now_iso(), "kind": kind, "text": text.strip()}
    profile.setdefault("feedback", []).append(entry)
    if kind == "veto":
        vetoes = profile.setdefault("vetoes", [])
        if text.strip() not in vetoes:
            vetoes.append(text.strip())
    save_profile(persona_dir, profile)
    print(f"Recorded {kind} feedback")


def brief_persona(persona_dir: Path, as_json: bool) -> None:
    init_persona(persona_dir)
    profile = load_profile(persona_dir)
    if as_json:
        print(json.dumps(profile, ensure_ascii=False, indent=2))
        return

    prefs = profile.get("preferences", {})
    lines = [
        "# User persona brief",
        f"updated: {profile.get('updated', 'never')}",
        f"language: {profile.get('language', 'ru')}",
        f"autonomy: {profile.get('autonomy', 'high')}",
        f"human_gate: {profile.get('human_gate', False)}",
        "",
        "## Priority signals",
    ]
    for sig in profile.get("priority_signals", [])[:10]:
        lines.append(f"- {sig}")
    lines.append("")
    lines.append("## Preferences")
    for key, val in prefs.items():
        if val:
            lines.append(f"- {key}")
    lines.append("")
    lines.append("## Vetoes")
    for v in profile.get("vetoes", [])[:15]:
        lines.append(f"- {v}")
    lines.append("")
    lines.append("## Recent feedback")
    for fb in profile.get("feedback", [])[-8:]:
        lines.append(f"- [{fb.get('kind', 'note')}] {fb.get('text', '')[:200]}")
    lines.append("")
    lines.append("## Corpus samples (voice)")
    for s in profile.get("corpus_samples", [])[-6:]:
        lines.append(f"- {s[:180]}")
    print("\n".join(lines))


def on_agent_stop(
    persona_dir: Path,
    agent: str,
    target: str,
    status: str,
    hook_event: str,
) -> Path:
    init_persona(persona_dir)
    profile = load_profile(persona_dir)
    ts = _now_iso()

    lines = [
        "# User-proxy pending decision",
        "",
        f"generated: {ts}",
        f"hook_event: {hook_event}",
        f"stopped_agent: {agent}",
        f"target: {target or '(unknown)'}",
        f"agent_status: {status}",
        "",
        "## Persona snapshot",
        f"- language: {profile.get('language', 'ru')}",
        f"- autonomy: {profile.get('autonomy', 'high')}",
        f"- human_gate: {profile.get('human_gate', False)}",
        f"- priority_signals: {', '.join(profile.get('priority_signals', [])[:8]) or 'none'}",
        "",
        "## Apply now",
        "Read `.cursor/agents/user-proxy.md` and emit exactly one block:",
        "",
        "```",
        "USER_PROXY_DECISION:",
        "  verdict: CONTINUE | DISPATCH_NEXT | DEEPEN | CHAIN_NOW | ROTATE | ESCALATE_HUMAN | CHECKPOINT",
        "  rationale: <1-3 sentences in researcher voice>",
        "  next_action: <single concrete command or dispatch>",
        "  confidence: high|medium|low",
        "```",
        "",
        "## Researcher vetoes (hard)",
    ]
    for v in profile.get("vetoes", [])[:12]:
        lines.append(f"- {v}")
    lines.append("")
    lines.append("## Recent voice samples")
    for s in profile.get("corpus_samples", [])[-4:]:
        lines.append(f"- {s[:220]}")

    pending = _pending_path(persona_dir)
    atomic_write_text(pending, "\n".join(lines) + "\n")

    entry = {
        "ts": ts,
        "hook_event": hook_event,
        "agent": agent,
        "target": target,
        "status": status,
    }
    dec_path = _decisions_path(persona_dir)
    with locked_file(dec_path):
        with open(dec_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return pending


def show_decisions(persona_dir: Path, limit: int) -> None:
    path = _decisions_path(persona_dir)
    if not path.exists():
        print("No proxy decisions logged yet.")
        return
    rows = path.read_text(encoding="utf-8").splitlines()
    for line in rows[-limit:]:
        if line.strip():
            print(line)


def main() -> None:
    parser = argparse.ArgumentParser(description="Researcher persona for user-proxy")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize persona directory")

    ingest_p = sub.add_parser("ingest", help="Ingest Cursor transcript user messages")
    ingest_p.add_argument("--transcripts-dir", type=Path, default=None)
    ingest_p.add_argument("--max-files", type=int, default=80)

    brief_p = sub.add_parser("brief", help="Print compact persona for prompts")
    brief_p.add_argument("--json", action="store_true")

    fb_p = sub.add_parser("record-feedback", help="Record explicit preference")
    fb_p.add_argument("text")
    fb_p.add_argument("--kind", choices=["preference", "veto", "correction"], default="preference")

    stop_p = sub.add_parser("on-stop", help="Write pending decision context after agent stop")
    stop_p.add_argument("--agent", required=True)
    stop_p.add_argument("--target", default="")
    stop_p.add_argument("--status", choices=["ok", "fail", "unknown"], default="unknown")
    stop_p.add_argument("--hook-event", default="subagentStop")

    dec_p = sub.add_parser("decisions", help="Show recent stop events")
    dec_p.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()
    persona_dir = get_persona_dir()

    if args.command == "init":
        init_persona(persona_dir)
    elif args.command == "ingest":
        ingest_transcripts(persona_dir, args.transcripts_dir, args.max_files)
    elif args.command == "brief":
        brief_persona(persona_dir, args.json)
    elif args.command == "record-feedback":
        record_feedback(persona_dir, args.text, args.kind)
    elif args.command == "on-stop":
        path = on_agent_stop(persona_dir, args.agent, args.target, args.status, args.hook_event)
        print(str(path))
    elif args.command == "decisions":
        show_decisions(persona_dir, args.limit)


if __name__ == "__main__":
    main()
