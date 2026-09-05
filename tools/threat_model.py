#!/usr/bin/env python3
"""Threat model artifact helpers for /threat-model and pipeline integration."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from file_safety import atomic_write_text  # noqa: E402

DEFAULT_MAX_AGE_DAYS = 7
SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_target(target: str) -> str:
    return SLUG_RE.sub("-", target.strip().lower()).strip("-")


def threat_model_path(root: Path, target: str, *, as_json: bool = False) -> Path:
    slug = slugify_target(target)
    ext = "json" if as_json else "md"
    return root / "brain" / "threat-model" / f"{slug}.{ext}"


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def empty_threat_model(target: str) -> dict:
    return {
        "version": 1,
        "target": target,
        "updated_at": _utc_now_iso(),
        "assets": [],
        "trust_boundaries": [],
        "crown_jewels": [],
        "ranked_threat_classes": [],
        "policy_constraints": [],
        "notes": "",
    }


def load_threat_model(path: Path) -> dict | None:
    if not path.exists():
        return None
    if path.suffix == ".json":
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    text = path.read_text(encoding="utf-8")
    return parse_threat_model_markdown(text, target=path.stem)


def parse_threat_model_markdown(text: str, target: str = "") -> dict:
    """Parse a minimal structured threat model from markdown sections."""
    model = empty_threat_model(target)
    model["notes"] = text.strip()
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            section = stripped[3:].strip().lower()
            continue
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        if section.startswith("assets"):
            model["assets"].append(value)
        elif section.startswith("crown jewels"):
            model["crown_jewels"].append(value)
        elif section.startswith("ranked threat classes"):
            cls_match = re.match(r"`?([a-z0-9-]+)`?", value, re.I)
            if cls_match:
                model["ranked_threat_classes"].append(
                    {"class": cls_match.group(1).lower(), "priority": len(model["ranked_threat_classes"]) + 1}
                )
        elif section.startswith("policy constraints"):
            model["policy_constraints"].append(value)
    return model


def save_threat_model(path: Path, model: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    model = dict(model)
    model["updated_at"] = _utc_now_iso()
    if path.suffix == ".json":
        atomic_write_text(path, json.dumps(model, indent=2) + "\n")
        return
    lines = [
        f"# Threat Model: {model.get('target', path.stem)}",
        "",
        f"_Updated: {model['updated_at']}_",
        "",
        "## Assets",
    ]
    for item in model.get("assets") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Crown Jewels"])
    for item in model.get("crown_jewels") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Ranked Threat Classes"])
    for row in model.get("ranked_threat_classes") or []:
        if isinstance(row, dict):
            cls = row.get("class", "")
            prio = row.get("priority", "")
            pre = row.get("preconditions", "")
            suffix = f" (priority {prio})" if prio else ""
            if pre:
                suffix += f" — preconditions: {pre}"
            lines.append(f"- `{cls}`{suffix}")
        else:
            lines.append(f"- `{row}`")
    lines.extend(["", "## Policy Constraints"])
    for item in model.get("policy_constraints") or []:
        lines.append(f"- {item}")
    if model.get("notes") and not model["notes"].startswith("# Threat Model"):
        lines.extend(["", "## Notes", model["notes"]])
    atomic_write_text(path, "\n".join(lines) + "\n")


def is_stale(path: Path, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> bool:
    if not path.exists():
        return True
    age = datetime.now(tz=timezone.utc) - datetime.fromtimestamp(
        path.stat().st_mtime, tz=timezone.utc
    )
    return age.days >= max_age_days


def ranked_class_boosts(model: dict | None) -> dict[str, float]:
    if not model:
        return {}
    boosts: dict[str, float] = {}
    rows = model.get("ranked_threat_classes") or []
    for idx, row in enumerate(rows):
        if isinstance(row, str):
            cls = row.lower()
            prio = idx + 1
        else:
            cls = str(row.get("class", "")).lower()
            prio = int(row.get("priority", idx + 1) or (idx + 1))
        if not cls:
            continue
        boosts[cls] = max(boosts.get(cls, 0.0), 40.0 - (prio - 1) * 5.0)
    return boosts


def cmd_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path = threat_model_path(root, args.target, as_json=args.json)
    if not path.exists():
        print(f"MISSING: {path}")
        return 1
    stale = is_stale(path, max_age_days=args.max_age_days)
    print(f"PATH: {path}")
    print(f"STALE: {stale}")
    model = load_threat_model(path)
    if model:
        classes = [
            r.get("class") if isinstance(r, dict) else r
            for r in (model.get("ranked_threat_classes") or [])
        ]
        print(f"CLASSES: {', '.join(str(c) for c in classes if c)}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Threat model artifact utilities")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    status_p = sub.add_parser("status", help="Check threat model presence and freshness")
    status_p.add_argument("target")
    status_p.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    status_p.add_argument("--json", action="store_true", help="Look for .json artifact")
    status_p.set_defaults(func=cmd_status)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
