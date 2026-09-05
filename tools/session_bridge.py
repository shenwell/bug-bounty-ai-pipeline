#!/usr/bin/env python3
"""WAF session bridge — persist browser cookies for curl-based hunters."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from file_safety import atomic_write_text  # noqa: E402

SESSION_FILE = Path("recon/session.json")
ROLE_SESSIONS_DIR = Path("recon/sessions")

INJECTION_WAF_CLASSES = frozenset(
    {
        "xss",
        "xss-reflected",
        "xss-stored",
        "sqli",
        "ssti",
        "rce",
        "command-injection",
        "xxe",
        "lfi",
        "path-traversal",
        "header-injection",
    }
)

ROLE_REQUIRED_CLASSES = frozenset(
    {
        "idor",
        "business-logic",
        "privilege-escalation",
        "auth-bypass",
        "bac",
    }
)

WAF_BLOCK_MARKERS = (
    "cloudflare",
    "cf-ray",
    "akamai",
    "imperva",
    "sucuri",
    "403",
    "challenge",
    "turnstile",
    "datadome",
    "perimeterx",
)


def session_path(root: Path) -> Path:
    return root / SESSION_FILE


def role_session_path(root: Path, role: str) -> Path:
    safe_role = re.sub(r"[^a-zA-Z0-9_-]+", "-", role.strip()).strip("-") or "default"
    return root / ROLE_SESSIONS_DIR / f"{safe_role}.json"


def list_role_sessions(root: Path) -> list[str]:
    sessions_dir = root / ROLE_SESSIONS_DIR
    if not sessions_dir.exists():
        return []
    roles: list[str] = []
    for path in sorted(sessions_dir.glob("*.json")):
        if path.stat().st_size > 0:
            roles.append(path.stem)
    return roles


def load_role_session(root: Path, role: str) -> dict[str, Any] | None:
    path = role_session_path(root, role)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save_role_session(root: Path, role: str, session: dict[str, Any]) -> Path:
    path = role_session_path(root, role)
    path.parent.mkdir(parents=True, exist_ok=True)
    session = dict(session)
    session.setdefault("role", role)
    session.setdefault("obtained_at", _utc_now_iso())
    atomic_write_text(path, json.dumps(session, indent=2) + "\n")
    return path


def active_role_session_count(root: Path) -> int:
    """Count role sessions with at least one cookie (authenticated)."""
    count = 0
    for role in list_role_sessions(root):
        data = load_role_session(root, role)
        if data and (data.get("cookies") or []):
            count += 1
    return count


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def empty_session(host: str = "", waf_vendor: str = "") -> dict[str, Any]:
    return {
        "host": host,
        "cookies": [],
        "user_agent": "",
        "obtained_at": _utc_now_iso(),
        "waf_vendor": waf_vendor,
    }


def save_session(root: Path, session: dict[str, Any]) -> Path:
    path = session_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    session = dict(session)
    session.setdefault("obtained_at", _utc_now_iso())
    atomic_write_text(path, json.dumps(session, indent=2) + "\n")
    return path


def load_session(root: Path) -> dict[str, Any] | None:
    path = session_path(root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def session_exists(root: Path) -> bool:
    path = session_path(root)
    return path.exists() and path.stat().st_size > 0


def cookies_to_curl_flag(cookies: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for c in cookies:
        if isinstance(c, dict):
            name = c.get("name", "")
            value = c.get("value", "")
            if name:
                parts.append(f"{name}={value}")
        elif isinstance(c, str) and "=" in c:
            parts.append(c)
    if not parts:
        return ""
    return "-b " + json.dumps("; ".join(parts))


def render_curl_preamble(root: Path, role: str | None = None) -> str:
    if role:
        session = load_role_session(root, role)
        label = f"role={role}"
    else:
        session = load_session(root)
        label = "WAF/unauth"
    if not session:
        return ""
    lines = [f"SESSION BRIDGE ({label} — from recon/session{'s/' + role if role else ''}.json):"]
    host = session.get("host") or ""
    if host:
        lines.append(f"  Host context: {host}")
    ua = session.get("user_agent") or ""
    if ua:
        lines.append(f'  User-Agent: curl ... -A "{ua}"')
    waf = session.get("waf_vendor") or ""
    if waf:
        lines.append(f"  WAF passed: {waf}")
    flag = cookies_to_curl_flag(session.get("cookies") or [])
    if flag:
        lines.append(f"  Cookies: curl ... {flag}")
    obtained = session.get("obtained_at") or ""
    if obtained:
        lines.append(f"  Obtained: {obtained}")
    return "\n".join(lines)


def waf_profile_indicates_block(root: Path) -> bool:
    paths = [
        root / "brain" / "techniques" / "waf-bypasses.md",
        root / "techniques" / "waf-bypasses.md",
    ]
    for path in paths:
        if not path.exists():
            continue
        lower = path.read_text(encoding="utf-8", errors="replace").lower()
        if any(m in lower for m in WAF_BLOCK_MARKERS):
            return True
    return False


def _has_auth_hunting_context(root: Path) -> bool:
    traffic = root / "recon" / "traffic-exercised.json"
    if traffic.exists() and traffic.stat().st_size > 0:
        return True
    if session_exists(root):
        return True
    return active_role_session_count(root) > 0


def role_exhaustion_requires_multi_session(root: Path, vuln_class: str) -> tuple[bool, str]:
    """BAC/IDOR/PE classes cannot be exhausted without >=2 authenticated role sessions."""
    cls = vuln_class.lower().replace("_", "-")
    if cls not in ROLE_REQUIRED_CLASSES:
        return True, "not a multi-role class"
    if not _has_auth_hunting_context(root):
        return True, "no auth hunting context — multi-role gate skipped"
    count = active_role_session_count(root)
    if count >= 2:
        return True, f"{count} role sessions present"
    return (
        False,
        f"reach-no-multi-role: {cls} requires >=2 authenticated role sessions in "
        f"recon/sessions/<role>.json (found {count}); register second role or "
        f"record reach blocker in brain/accounts/<slug>.json and ESCALATE_HUMAN",
    )


def injection_exhaustion_requires_session(root: Path, vuln_class: str) -> tuple[bool, str]:
    """Return (allowed, reason) for marking injection class exhausted."""
    cls = vuln_class.lower().replace("_", "-")
    if cls not in INJECTION_WAF_CLASSES:
        return True, "not an injection class"
    if not waf_profile_indicates_block(root):
        return True, "no WAF block profile recorded"
    if session_exists(root):
        return True, "session.json present"
    return (
        False,
        "waf-no-session: WAF profile indicates blocking but recon/session.json is missing; "
        "run browser-stealth-agent through challenge before exhausting injection classes",
    )


def cmd_write(args: argparse.Namespace) -> int:
    root = Path(args.root)
    cookies: list[dict[str, str]] = []
    if args.cookies_json:
        raw = json.loads(args.cookies_json)
        if isinstance(raw, list):
            cookies = raw
    session = empty_session(host=args.host or "", waf_vendor=args.waf_vendor or "")
    session["cookies"] = cookies
    if args.user_agent:
        session["user_agent"] = args.user_agent
    path = save_session(root, session)
    print(f"WROTE: {path}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    text = render_curl_preamble(Path(args.root), role=args.role or None)
    if not text:
        print("(no session)")
        return 0
    print(text)
    return 0


def cmd_list_roles(args: argparse.Namespace) -> int:
    root = Path(args.root)
    roles = list_role_sessions(root)
    if not roles:
        print("(no role sessions)")
        return 0
    for role in roles:
        data = load_role_session(root, role)
        cookies = len((data or {}).get("cookies") or [])
        print(f"{role}: cookies={cookies}")
    print(f"active_authenticated={active_role_session_count(root)}")
    return 0


def cmd_write_role(args: argparse.Namespace) -> int:
    root = Path(args.root)
    cookies: list[dict[str, str]] = []
    if args.cookies_json:
        raw = json.loads(args.cookies_json)
        if isinstance(raw, list):
            cookies = raw
    session = empty_session(host=args.host or "", waf_vendor=args.waf_vendor or "")
    session["cookies"] = cookies
    session["role"] = args.role
    if args.user_agent:
        session["user_agent"] = args.user_agent
    path = save_role_session(root, args.role, session)
    print(f"WROTE: {path}")
    return 0


def cmd_check_role_exhaustion(args: argparse.Namespace) -> int:
    ok, reason = role_exhaustion_requires_multi_session(Path(args.root), args.vuln_class)
    print("OK" if ok else "BLOCK", reason)
    return 0 if ok else 1


def cmd_check_exhaustion(args: argparse.Namespace) -> int:
    ok, reason = injection_exhaustion_requires_session(Path(args.root), args.vuln_class)
    print("OK" if ok else "BLOCK", reason)
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="WAF session bridge for hunters")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    wr = sub.add_parser("write", help="Write recon/session.json")
    wr.add_argument("--host", default="")
    wr.add_argument("--waf-vendor", default="")
    wr.add_argument("--user-agent", default="")
    wr.add_argument("--cookies-json", default="[]")
    wr.set_defaults(func=cmd_write)

    rd = sub.add_parser("render-preamble", help="Render curl preamble for hunter dispatch")
    rd.add_argument("--role", default="", help="Role name for recon/sessions/<role>.json")
    rd.set_defaults(func=cmd_render)

    lr = sub.add_parser("list-roles", help="List authenticated role sessions")
    lr.set_defaults(func=cmd_list_roles)

    wr_role = sub.add_parser("write-role", help="Write recon/sessions/<role>.json")
    wr_role.add_argument("--role", required=True)
    wr_role.add_argument("--host", default="")
    wr_role.add_argument("--waf-vendor", default="")
    wr_role.add_argument("--user-agent", default="")
    wr_role.add_argument("--cookies-json", default="[]")
    wr_role.set_defaults(func=cmd_write_role)

    chk_role = sub.add_parser("check-role-exhaustion", help="Check multi-role requirement for BAC/IDOR/PE")
    chk_role.add_argument("--vuln-class", required=True)
    chk_role.set_defaults(func=cmd_check_role_exhaustion)

    chk = sub.add_parser("check-exhaustion", help="Check if injection class can be exhausted")
    chk.add_argument("--vuln-class", required=True)
    chk.set_defaults(func=cmd_check_exhaustion)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
