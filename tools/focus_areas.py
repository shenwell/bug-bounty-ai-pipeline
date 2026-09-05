#!/usr/bin/env python3
"""Focus-area partitioning for autonomous hunt dispatch."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from file_safety import atomic_write_text  # noqa: E402
from threat_model import load_threat_model, ranked_class_boosts, slugify_target, threat_model_path  # noqa: E402

SLICE_TEMPLATES = [
    {
        "id": "auth_oauth",
        "name": "Auth and OAuth",
        "host_hints": ("auth.", "login.", "sso.", "oauth", "id."),
        "endpoint_patterns": ["/oauth/*", "/login*", "/auth/*", "/callback*"],
        "priority_classes": ["oauth", "auth-bypass", "open-redirect", "csrf"],
    },
    {
        "id": "billing_wallet",
        "name": "Billing and Wallet",
        "host_hints": ("billing.", "pay.", "wallet.", "checkout."),
        "endpoint_patterns": ["/billing/*", "/payment*", "/wallet*", "/checkout*"],
        "priority_classes": ["business-logic", "race-condition", "idor", "privilege-escalation"],
    },
    {
        "id": "api_core",
        "name": "Core API",
        "host_hints": ("api.",),
        "endpoint_patterns": ["/api/*", "/v1/*", "/v2/*"],
        "priority_classes": ["idor", "graphql", "sqli", "ssrf", "auth-bypass"],
    },
    {
        "id": "upload_media",
        "name": "Upload and Media",
        "host_hints": ("upload.", "media.", "cdn."),
        "endpoint_patterns": ["/upload*", "/import*", "/avatar*", "/file*"],
        "priority_classes": ["file-upload", "xxe", "rce", "ssrf"],
    },
    {
        "id": "admin_ops",
        "name": "Admin and Operations",
        "host_hints": ("admin.", "manage.", "ops."),
        "endpoint_patterns": ["/admin/*", "/manage/*", "/internal/*"],
        "priority_classes": ["privilege-escalation", "idor", "info-disclosure"],
    },
]


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def focus_areas_path(root: Path, target: str) -> Path:
    return root / "brain" / "focus-areas" / f"{slugify_target(target)}.json"


def _load_endpoints(path: Path) -> list[str]:
    if not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            out.append(value.split()[0])
    return out


def _host_from_endpoint(endpoint: str) -> str:
    ep = endpoint.strip()
    if ep.startswith("http://") or ep.startswith("https://"):
        return re.sub(r"^https?://", "", ep).split("/")[0].lower()
    return ep.split("/")[0].lower()


def _match_slice(endpoint: str, template: dict) -> bool:
    host = _host_from_endpoint(endpoint)
    ep_lower = endpoint.lower()
    for hint in template.get("host_hints", ()):
        if hint in host:
            return True
    for pattern in template.get("endpoint_patterns", []):
        if fnmatch.fnmatch(ep_lower, pattern.lower()):
            return True
    return False


def generate_focus_areas(
    target: str,
    endpoints: list[str],
    threat_model: dict | None = None,
) -> dict:
    slices: list[dict] = []
    assigned: set[str] = set()
    for template in SLICE_TEMPLATES:
        hosts: set[str] = set()
        matched_eps: list[str] = []
        for ep in endpoints:
            if not _match_slice(ep, template):
                continue
            matched_eps.append(ep)
            assigned.add(ep)
            hosts.add(_host_from_endpoint(ep))
        if not matched_eps:
            continue
        priority_classes = list(template["priority_classes"])
        boosts = ranked_class_boosts(threat_model)
        if boosts:
            priority_classes.sort(
                key=lambda c: boosts.get(c.replace("_", "-"), 0.0),
                reverse=True,
            )
        slices.append(
            {
                "id": template["id"],
                "name": template["name"],
                "hosts": sorted(hosts),
                "endpoint_patterns": template["endpoint_patterns"],
                "endpoints": matched_eps[:50],
                "priority_classes": priority_classes,
                "status": "pending",
            }
        )
    leftovers = [ep for ep in endpoints if ep not in assigned]
    if leftovers:
        slices.append(
            {
                "id": "misc_surface",
                "name": "Miscellaneous Surface",
                "hosts": sorted({_host_from_endpoint(ep) for ep in leftovers}),
                "endpoint_patterns": ["*"],
                "endpoints": leftovers[:50],
                "priority_classes": ["idor", "info-disclosure", "xss-reflected"],
                "status": "pending",
            }
        )
    return {
        "version": 1,
        "target": target,
        "updated_at": _utc_now_iso(),
        "slices": slices,
    }


def load_focus_areas(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def get_slice(doc: dict, slice_id: str) -> dict | None:
    for row in doc.get("slices") or []:
        if row.get("id") == slice_id:
            return row
    return None


def next_pending_slice(doc: dict) -> dict | None:
    for row in doc.get("slices") or []:
        if row.get("status") in (None, "pending", "in_progress"):
            return row
    return None


def update_slice_status(doc: dict, slice_id: str, status: str) -> dict:
    doc = dict(doc)
    slices = []
    for row in doc.get("slices") or []:
        row = dict(row)
        if row.get("id") == slice_id:
            row["status"] = status
        slices.append(row)
    doc["slices"] = slices
    doc["updated_at"] = _utc_now_iso()
    return doc


def slice_class_boosts(slice_row: dict | None) -> dict[str, float]:
    if not slice_row:
        return {}
    boosts: dict[str, float] = {}
    for idx, cls in enumerate(slice_row.get("priority_classes") or []):
        boosts[str(cls).lower()] = max(boosts.get(str(cls).lower(), 0.0), 35.0 - idx * 4.0)
    return boosts


def endpoint_in_slice(endpoint: str, slice_row: dict) -> bool:
    ep_lower = endpoint.lower()
    host = _host_from_endpoint(endpoint)
    for h in slice_row.get("hosts") or []:
        if h and h in host:
            return True
    for pattern in slice_row.get("endpoint_patterns") or []:
        if fnmatch.fnmatch(ep_lower, pattern.lower()):
            return True
    for ep in slice_row.get("endpoints") or []:
        if ep.lower() == ep_lower:
            return True
    return False


def cmd_generate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    endpoints = _load_endpoints(Path(args.endpoints))
    tm_path = Path(args.threat_model) if args.threat_model else threat_model_path(root, args.target)
    threat_model = load_threat_model(tm_path) if tm_path.exists() else None
    doc = generate_focus_areas(args.target, endpoints, threat_model=threat_model)
    out = Path(args.output) if args.output else focus_areas_path(root, args.target)
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out, json.dumps(doc, indent=2) + "\n")
    print(f"Wrote {len(doc['slices'])} slices to {out}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    path = Path(args.focus_areas)
    doc = load_focus_areas(path)
    if not doc:
        print(f"MISSING: {path}")
        return 1
    for row in doc.get("slices") or []:
        print(f"{row.get('id')}: {row.get('status')} hosts={len(row.get('hosts') or [])}")
    nxt = next_pending_slice(doc)
    if nxt:
        print(f"NEXT: {nxt.get('id')}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Focus-area partition utilities")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate focus_areas.json from endpoints + threat model")
    gen.add_argument("--target", required=True)
    gen.add_argument("--endpoints", default="recon/endpoints.txt")
    gen.add_argument("--threat-model", default=None)
    gen.add_argument("--output", default=None)
    gen.set_defaults(func=cmd_generate)

    status = sub.add_parser("status", help="Show slice statuses")
    status.add_argument("--focus-areas", required=True)
    status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
