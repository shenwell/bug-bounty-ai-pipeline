"""Workspace path helpers for Cursor-only pentest workspaces."""
from __future__ import annotations

import os
from pathlib import Path

BRAIN_DIR = Path("brain")
ENGAGEMENTS_DIR = Path("engagements")
ACTIVE_ENGAGEMENT_FILE = ENGAGEMENTS_DIR / ".active"

LEGACY_BRAIN_DIRS = (
    Path(".claude/agent-memory-local/brain"),
    Path(".claude/agent-memory/brain"),
    Path("brain-memory"),
)


def get_engagement_slug() -> str | None:
    """Active per-target hunt folder under engagements/ (e.g. acme-corp)."""
    env_slug = os.environ.get("PENTEST_ENGAGEMENT", "").strip()
    if env_slug and (ENGAGEMENTS_DIR / env_slug).is_dir():
        return env_slug
    if ACTIVE_ENGAGEMENT_FILE.is_file():
        slug = ACTIVE_ENGAGEMENT_FILE.read_text(encoding="utf-8").strip()
        if slug and (ENGAGEMENTS_DIR / slug).is_dir():
            return slug
    return None


def get_engagement_dir() -> Path | None:
    slug = get_engagement_slug()
    if not slug:
        return None
    return ENGAGEMENTS_DIR / slug


def get_workspace_root() -> Path:
    """Repo root or active engagements/<slug> when hunting a single program."""
    eng = get_engagement_dir()
    return eng if eng is not None else Path(".")


def get_brain_dir() -> Path:
    """Return the active brain directory for the current engagement."""
    eng = get_engagement_dir()
    if eng is not None:
        eng_brain = eng / "brain"
        if eng_brain.is_dir():
            return eng_brain
    if BRAIN_DIR.exists():
        return BRAIN_DIR
    for legacy in LEGACY_BRAIN_DIRS:
        if legacy.exists():
            return legacy
    return BRAIN_DIR


def chain_pending_file() -> Path:
    """chain-pending.md at workspace root (new) or under agent-memory-local (legacy)."""
    root = get_workspace_root()
    if get_engagement_dir() is not None:
        return root / "chain-pending.md"
    brain = get_brain_dir()
    if brain == BRAIN_DIR:
        return Path("chain-pending.md")
    return brain.parent / "chain-pending.md"


def get_persona_dir() -> Path:
    """Researcher persona files for user-proxy (under active brain dir)."""
    return get_brain_dir() / "persona"


def user_proxy_pending_file() -> Path:
    """Pending user-proxy decision brief after subagent/session stop."""
    return get_persona_dir() / "user-proxy-pending.md"
