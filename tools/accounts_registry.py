#!/usr/bin/env python3
"""Test account registry — role metadata without secrets in repo.

Credentials are env-var symbols only (${VAR_NAME}), per pentest-agents-identities.mdc.

Usage:
    python3 tools/accounts_registry.py init --target example.com
    python3 tools/accounts_registry.py add-role --target example.com --role low-priv-a \\
        --email-env HACKERONE_EMAIL_ALIAS --status active
    python3 tools/accounts_registry.py status --target example.com
"""

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
from threat_model import slugify_target  # noqa: E402

ENV_SYMBOL_RE = re.compile(r"^\$\{[A-Z][A-Z0-9_]*\}$")
SECRET_PATTERNS = (
    re.compile(r"password\s*[:=]\s*['\"]?.+['\"]?", re.I),
    re.compile(r"Bearer\s+eyJ", re.I),
    re.compile(r"@[a-z0-9.-]+\.[a-z]{2,}", re.I),
)


def accounts_path(root: Path, target: str) -> Path:
    return root / "brain" / "accounts" / f"{slugify_target(target)}.json"


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def empty_accounts(target: str) -> dict:
    return {
        "version": 1,
        "target": target,
        "updated_at": _utc_now_iso(),
        "roles": [],
        "reach_blockers": [],
    }


def load_accounts(root: Path, target: str) -> dict | None:
    path = accounts_path(root, target)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save_accounts(root: Path, doc: dict) -> Path:
    target = doc.get("target") or "unknown"
    path = accounts_path(root, target)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = dict(doc)
    doc["updated_at"] = _utc_now_iso()
    atomic_write_text(path, json.dumps(doc, indent=2) + "\n")
    return path


def validate_no_secrets(doc: dict) -> list[str]:
    """Reject documents that contain literal secrets instead of env symbols."""
    issues: list[str] = []
    raw = json.dumps(doc)
    for pattern in SECRET_PATTERNS:
        if pattern.search(raw):
            issues.append(f"possible secret detected by pattern {pattern.pattern}")
    for role in doc.get("roles") or []:
        for field in ("email_env", "password_env", "username_env", "token_env"):
            val = role.get(field) or ""
            if val and not ENV_SYMBOL_RE.match(val):
                issues.append(f"role {role.get('role')}: {field} must be ${{ENV_VAR}} form, got {val!r}")
    return issues


def active_role_count(root: Path, target: str) -> int:
    doc = load_accounts(root, target)
    if not doc:
        return 0
    return sum(1 for r in doc.get("roles") or [] if r.get("status") == "active")


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root)
    doc = empty_accounts(args.target)
    path = save_accounts(root, doc)
    print(f"WROTE: {path}")
    return 0


def cmd_add_role(args: argparse.Namespace) -> int:
    root = Path(args.root)
    doc = load_accounts(root, args.target) or empty_accounts(args.target)
    roles = list(doc.get("roles") or [])
    entry = {
        "role": args.role,
        "status": args.status or "pending",
        "email_env": args.email_env or "",
        "username_env": args.username_env or "",
        "password_env": args.password_env or "",
        "notes": args.notes or "",
    }
    roles = [r for r in roles if r.get("role") != args.role]
    roles.append(entry)
    doc["roles"] = roles
    issues = validate_no_secrets(doc)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}", file=sys.stderr)
        return 1
    path = save_accounts(root, doc)
    print(f"WROTE: {path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    doc = load_accounts(Path(args.root), args.target)
    if not doc:
        print("MISSING accounts registry — run init")
        return 1
    print(json.dumps(doc, indent=2))
    active = sum(1 for r in doc.get("roles") or [] if r.get("status") == "active")
    print(f"\nActive roles: {active}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Test account registry (env symbols only)")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--target", required=True)
    init.set_defaults(func=cmd_init)

    add = sub.add_parser("add-role")
    add.add_argument("--target", required=True)
    add.add_argument("--role", required=True)
    add.add_argument("--status", default="pending", choices=["pending", "active", "blocked"])
    add.add_argument("--email-env", default="")
    add.add_argument("--username-env", default="")
    add.add_argument("--password-env", default="")
    add.add_argument("--notes", default="")
    add.set_defaults(func=cmd_add_role)

    st = sub.add_parser("status")
    st.add_argument("--target", required=True)
    st.set_defaults(func=cmd_status)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
