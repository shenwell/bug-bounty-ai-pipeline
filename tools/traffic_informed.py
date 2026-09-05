#!/usr/bin/env python3
"""Traffic-informed surface targeting — exercised endpoints as hunt ground truth."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from intel_engine import _load_traffic_hits, rank_surface  # noqa: E402

TRAFFIC_FILE = Path("recon/traffic-exercised.json")
MIN_TRAFFIC_ENDPOINTS = 5
TRAFFIC_SKIP_RE = re.compile(
    r"recon-skip\s*:\s*traffic-informed\b.*?policy\s*[:=]?\s*(?P<clause>\S+)",
    re.IGNORECASE,
)

AUTH_MARKERS = (
    "auth_accounts.md",
    "04-auth-session.json",
    "evidence/cabinet",
    "evidence/cabinet/01-tenant-inventory.json",
    "hunt/07-shared-sandbox-intel.md",
)


def traffic_path(root: Path) -> Path:
    return root / TRAFFIC_FILE


def traffic_skip_recorded(brain_content: str) -> bool:
    return bool(TRAFFIC_SKIP_RE.search(brain_content or ""))


def has_auth_context(root: Path) -> bool:
    for rel in AUTH_MARKERS:
        path = root / rel
        if path.exists() and path.stat().st_size > 0:
            return True
    for pattern in ("**/auth_accounts.md", "**/04-auth-session.json"):
        if any(p.stat().st_size > 0 for p in root.glob(pattern)):
            return True
    return False


def count_traffic_endpoints(root: Path) -> int:
    path = traffic_path(root)
    if not path.exists():
        return 0
    return len(_load_traffic_hits(path))


def load_traffic_endpoint_list(root: Path) -> list[str]:
    path = traffic_path(root)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out: list[str] = []
    if isinstance(data, list):
        for row in data:
            if isinstance(row, str):
                out.append(row)
            elif isinstance(row, dict):
                ep = str(row.get("endpoint") or row.get("url") or "").strip()
                if ep:
                    out.append(ep)
    elif isinstance(data, dict):
        out.extend(str(k) for k in data if k)
    return out


def validate_traffic_informed(root: Path, brain_content: str = "") -> tuple[bool, str]:
    """Return (ok, reason). Skip when no auth context or policy skip recorded."""
    if traffic_skip_recorded(brain_content):
        return True, "traffic-informed skipped via recon-skip policy"
    if not has_auth_context(root):
        return True, "no auth context — traffic file optional"
    count = count_traffic_endpoints(root)
    path = traffic_path(root)
    if not path.exists() or path.stat().st_size == 0:
        return (
            False,
            f"missing {TRAFFIC_FILE} — cabinet walk required when auth accounts exist; "
            "export browser network log or record `recon-skip:traffic-informed policy:<clause>`",
        )
    if count < MIN_TRAFFIC_ENDPOINTS:
        return (
            False,
            f"{TRAFFIC_FILE} has only {count} endpoint(s); need >= {MIN_TRAFFIC_ENDPOINTS} "
            "unique exercised URLs from cabinet/API mirror walk",
        )
    return True, f"traffic-informed ok ({count} endpoints)"


def expand_sibling_endpoints(endpoints: list[str], limit: int = 30) -> list[str]:
    """Same path prefix / host — sibling Rule expansion for hunter dispatch."""
    seen: set[str] = set()
    out: list[str] = []
    prefixes: set[str] = set()
    for ep in endpoints:
        ep = ep.strip()
        if not ep:
            continue
        parsed = urlparse(ep if "://" in ep else f"https://{ep}")
        path = parsed.path.rstrip("/") or "/"
        parts = [p for p in path.split("/") if p]
        if parts:
            prefixes.add(f"{parsed.scheme}://{parsed.netloc}/" + "/".join(parts[:-1]))
        prefixes.add(f"{parsed.scheme}://{parsed.netloc}{path}")

    for ep in endpoints:
        low = ep.lower().strip()
        if low and low not in seen:
            seen.add(low)
            out.append(ep)

    for prefix in sorted(prefixes):
        if len(out) >= limit:
            break
        for suffix in ("/export", "/delete", "/share", "/history", "/actions", "/permissions"):
            candidate = prefix.rstrip("/") + suffix
            low = candidate.lower()
            if low not in seen:
                seen.add(low)
                out.append(candidate)
    return out[:limit]


def load_fuzz_signals(root: Path, path: Path | None = None) -> list[dict]:
    """Load exported oracle+readback signals from recon/fuzz-signals.json."""
    p = path or (root / "recon" / "fuzz-signals.json")
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return [row for row in data if row.get("signal_tier") == "oracle+readback"]


def rank_with_traffic(
    root: Path,
    endpoints: list[str],
    *,
    tech_stack: str = "",
    output: Path | None = None,
    fuzz_signals: list[dict] | None = None,
) -> list[dict]:
    traffic_hits = _load_traffic_hits(traffic_path(root))
    signals = fuzz_signals if fuzz_signals is not None else load_fuzz_signals(root)
    fuzz_killed: set[str] = set()
    try:
        from intel_engine import _fuzz_boost_killed_from_brain

        fuzz_killed = _fuzz_boost_killed_from_brain(root / "brain")
    except Exception:
        pass
    ranked = rank_surface(
        endpoints,
        tech_stack=tech_stack,
        traffic_hits=traffic_hits,
        fuzz_signals=signals,
        fuzz_boost_killed=fuzz_killed,
    )
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Attack surface ranking (traffic-informed)\n"]
        for row in ranked:
            bucket = row.get("bucket", "?")
            lines.append(f"- [{bucket}] {row.get('endpoint')} (score={row.get('score')})")
            for reason in row.get("reasons") or []:
                lines.append(f"  - {reason}")
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ranked


def p1_endpoints_from_traffic_rank(ranked: list[dict]) -> list[str]:
    return [r["endpoint"] for r in ranked if r.get("bucket") == "P1"]


def cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.root)
    brain = ""
    if args.brain_file:
        p = Path(args.brain_file)
        if p.exists():
            brain = p.read_text(encoding="utf-8")
    ok, reason = validate_traffic_informed(root, brain)
    print("OK" if ok else "FAIL", reason)
    return 0 if ok else 1


def cmd_expand(args: argparse.Namespace) -> int:
    root = Path(args.root)
    eps = load_traffic_endpoint_list(root)
    if not eps and args.endpoints_file:
        eps = [
            ln.strip()
            for ln in Path(args.endpoints_file).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
    expanded = expand_sibling_endpoints(eps, limit=args.limit)
    print(json.dumps(expanded, indent=2))
    return 0


def cmd_rank(args: argparse.Namespace) -> int:
    root = Path(args.root)
    eps = []
    if args.endpoints_file:
        eps = [
            ln.strip()
            for ln in Path(args.endpoints_file).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
    traffic_eps = load_traffic_endpoint_list(root)
    merged = list(dict.fromkeys(eps + traffic_eps))
    out = Path(args.output) if args.output else None
    fuzz_path = Path(args.fuzz_signals_file) if getattr(args, "fuzz_signals_file", "") else None
    fuzz_signals = load_fuzz_signals(root, fuzz_path) if fuzz_path else load_fuzz_signals(root)
    ranked = rank_with_traffic(
        root,
        merged,
        tech_stack=args.tech_stack or "",
        output=out,
        fuzz_signals=fuzz_signals,
    )
    print(json.dumps(ranked, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Traffic-informed targeting utilities")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    val = sub.add_parser("validate", help="Validate traffic-exercised.json for auth contexts")
    val.add_argument("--brain-file", default="")
    val.set_defaults(func=cmd_validate)

    exp = sub.add_parser("expand-siblings", help="Expand exercised endpoints with sibling paths")
    exp.add_argument("--endpoints-file", default="recon/endpoints.txt")
    exp.add_argument("--limit", type=int, default=30)
    exp.set_defaults(func=cmd_expand)

    rk = sub.add_parser("rank", help="Rank endpoints with traffic + fuzz signal boosts")
    rk.add_argument("--endpoints-file", default="recon/endpoints.txt")
    rk.add_argument("--tech-stack", default="")
    rk.add_argument("--output", default="ATTACK_SURFACE_RANKING.md")
    rk.add_argument("--fuzz-signals-file", default="recon/fuzz-signals.json")
    rk.set_defaults(func=cmd_rank)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
