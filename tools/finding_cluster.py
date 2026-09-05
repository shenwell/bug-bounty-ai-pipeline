#!/usr/bin/env python3
"""Cluster structured finding records across waves — pick best witness per cluster."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from file_safety import atomic_write_text  # noqa: E402
from finding_record import load_finding  # noqa: E402


def _normalize_path(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.netloc.lower()}{path.lower()}"


def _capability_hash(record: dict[str, Any]) -> str:
    marker = str((record.get("evidence") or {}).get("marker", "")).lower()[:80]
    title = str(record.get("title", "")).lower()[:80]
    raw = f"{record.get('class', '')}|{marker}|{title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def fingerprint(record: dict[str, Any], path: Path) -> str:
    host = str(record.get("host") or record.get("target") or "").lower()
    exploit = str((record.get("evidence") or {}).get("exploit_curl", ""))
    path_key = _normalize_path(exploit)
    if not path_key:
        path_key = str(record.get("title", "")).lower()[:60]
    cls = str(record.get("class", "")).lower()
    cap = _capability_hash(record)
    raw = f"{host}|{path_key}|{cls}|{cap}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _witness_rank(record: dict[str, Any]) -> int:
    gates = record.get("gates") or {}
    score = 0
    witness = gates.get("witness") or {}
    if witness.get("ok"):
        score += 100
    evidence = record.get("evidence") or {}
    if evidence.get("readback_curl"):
        score += 50
    if evidence.get("marker"):
        score += 25
    ev = gates.get("evidence_score") or {}
    score += int(ev.get("score", 0) or 0) // 2
    validator = gates.get("validator") or {}
    if validator.get("decision") == "PASS":
        score += 30
    judge = gates.get("judge") or {}
    if judge.get("verdict") == "CONFIRM":
        score += 40
    return score


def scan_findings(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    out: list[tuple[Path, dict[str, Any]]] = []
    evidence = root / "evidence"
    if not evidence.exists():
        return out
    for path in evidence.glob("**/findings/*.json"):
        record = load_finding(path)
        if record and record.get("status") not in {"killed"}:
            out.append((path, record))
    return out


def cluster_findings(root: Path) -> dict[str, Any]:
    items = scan_findings(root)
    clusters: dict[str, list[dict[str, Any]]] = {}
    for path, record in items:
        fp = fingerprint(record, path)
        rel = path.relative_to(root).as_posix()
        gates = record.get("gates") or {}
        witness = gates.get("witness") or {}
        entry = {
            "path": rel,
            "id": record.get("id"),
            "class": record.get("class"),
            "status": record.get("status"),
            "title": record.get("title"),
            "witness_rank": _witness_rank(record),
            "witness_ok": witness.get("ok"),
        }
        clusters.setdefault(fp, []).append(entry)

    best_per_cluster: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for fp, members in clusters.items():
        members.sort(key=lambda m: m["witness_rank"], reverse=True)
        best = dict(members[0])
        best["fingerprint"] = fp
        best["cluster_size"] = len(members)
        best_per_cluster.append(best)
        if len(members) > 1:
            duplicates.append(
                {
                    "fingerprint": fp,
                    "best": members[0]["path"],
                    "duplicates": [m["path"] for m in members[1:]],
                }
            )

    return {
        "version": 1,
        "total_findings": len(items),
        "clusters": len(clusters),
        "best": best_per_cluster,
        "duplicate_groups": duplicates,
    }


def render_markdown(index: dict[str, Any]) -> str:
    lines = [
        "# Findings cluster index",
        "",
        f"Total findings: {index.get('total_findings', 0)}",
        f"Clusters: {index.get('clusters', 0)}",
        "",
        "## Best per cluster (triage these)",
        "",
    ]
    for row in index.get("best") or []:
        lines.append(
            f"- [{row.get('status')}] {row.get('class')} — {row.get('title')} "
            f"(rank={row.get('witness_rank')}, size={row.get('cluster_size')}) "
            f"`{row.get('path')}`"
        )
    dups = index.get("duplicate_groups") or []
    if dups:
        lines.extend(["", "## Duplicate groups (skip inferior copies)", ""])
        for g in dups:
            lines.append(f"- best: `{g['best']}` — dupes: {', '.join(f'`{d}`' for d in g['duplicates'])}")
    return "\n".join(lines) + "\n"


def cmd_cluster(args: argparse.Namespace) -> int:
    root = Path(args.root)
    index = cluster_findings(root)
    out_json = root / "brain" / "findings-index.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_json, json.dumps(index, indent=2) + "\n")
    md_path = root / "brain" / "findings-cluster.md"
    atomic_write_text(md_path, render_markdown(index))
    print(f"WROTE: {out_json}")
    print(f"WROTE: {md_path}")
    print(json.dumps({"clusters": index["clusters"], "total": index["total_findings"]}))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Cluster finding_record JSON files")
    parser.add_argument("--root", default=".")
    parser.set_defaults(func=cmd_cluster)
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
