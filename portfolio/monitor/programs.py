"""Detect newly published bug bounty programs and notify."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from portfolio.common.config import AppConfig
from portfolio.common.logging import get_logger
from portfolio.monitor.email import EmailNotifier
from portfolio.monitor.platforms import (
    DEFAULT_MONITOR_PLATFORM,
    get_monitor_platform,
    resolve_state_file,
)
from portfolio.monitor.telegram import TelegramProgramNotifier

logger = get_logger(__name__)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "updated_at": None, "programs": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid monitor state file: {path}")
    data.setdefault("programs", {})
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _utc_now()
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def diff_new_programs(
    current: list[dict[str, Any]],
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    known = state.get("programs") or {}
    return [program for program in current if program["slug"] not in known]


def merge_state(state: dict[str, Any], programs: list[dict[str, Any]], *, seen_at: str | None = None) -> dict[str, Any]:
    stamp = seen_at or _utc_now()
    known = dict(state.get("programs") or {})
    for program in programs:
        slug = program["slug"]
        if slug not in known:
            known[slug] = {
                "slug": slug,
                "name": program["name"],
                "url": program["url"],
                "first_seen_at": stamp,
                "published_at": program.get("published_at"),
            }
        else:
            entry = known[slug]
            entry["name"] = program["name"]
            entry["url"] = program["url"]
            if program.get("published_at"):
                entry["published_at"] = program["published_at"]
    state["programs"] = known
    return state


def run_programs_monitor(
    config: AppConfig,
    *,
    platform: str = DEFAULT_MONITOR_PLATFORM,
    init: bool = False,
    dry_run: bool = False,
    test_email: bool = False,
) -> dict[str, Any]:
    platform_spec = get_monitor_platform(platform)
    state_path = Path(resolve_state_file(platform_spec, config.monitor.state_file))
    if test_email:
        email_notifier = EmailNotifier(config.monitor)
        sample = [
            {
                "slug": "monitor-test",
                "name": "Monitor test",
                "url": platform_spec.test_url,
                "published_at": _utc_now(),
            }
        ]
        sent = email_notifier.send_new_programs(
            sample,
            subject_prefix=f"{platform_spec.email_subject_prefix} TEST",
            body_intro=platform_spec.email_body_intro,
        )
        return {
            "platform": platform_spec.id,
            "action": "test_email",
            "email_sent": sent,
            "notify_email": config.monitor.notify_email(),
        }

    current = platform_spec.list_programs(config)
    state = load_state(state_path)
    new_programs = diff_new_programs(current, state)

    result: dict[str, Any] = {
        "platform": platform_spec.id,
        "total_programs": len(current),
        "known_before": len(state.get("programs") or {}),
        "new_count": len(new_programs),
        "new_slugs": [p["slug"] for p in new_programs],
        "state_file": str(state_path),
        "init": init,
        "dry_run": dry_run,
        "email_sent": False,
        "telegram_sent": False,
    }

    if init or not state.get("programs"):
        merge_state(state, current)
        if not dry_run:
            save_state(state_path, state)
        result["action"] = "initialized"
        logger.info(
            "programs_monitor_initialized",
            platform=platform_spec.id,
            total=len(current),
            state_file=str(state_path),
        )
        return result

    if not new_programs:
        result["action"] = "no_changes"
        logger.info("programs_monitor_no_changes", platform=platform_spec.id, total=len(current))
        return result

    email_notifier = EmailNotifier(config.monitor)
    telegram_notifier = TelegramProgramNotifier(config)
    if dry_run:
        result["action"] = "dry_run_new_programs"
        logger.info("programs_monitor_dry_run", platform=platform_spec.id, new=result["new_slugs"])
        return result

    merge_state(state, new_programs)
    save_state(state_path, state)

    from portfolio.kanban import add_programs_to_inbox

    inbox_added = add_programs_to_inbox(config, platform_spec.id, new_programs)
    result["kanban_inbox_added"] = inbox_added

    if email_notifier.send_new_programs(
        new_programs,
        subject_prefix=platform_spec.email_subject_prefix,
        body_intro=platform_spec.email_body_intro,
    ):
        result["email_sent"] = True
    elif not email_notifier.is_configured():
        result["email_error"] = "smtp_not_configured"

    if telegram_notifier.send_new_programs(new_programs, heading=platform_spec.telegram_heading):
        result["telegram_sent"] = True
    elif not telegram_notifier.is_configured():
        result["telegram_error"] = "telegram_not_configured"

    notified = result["email_sent"] or result["telegram_sent"]
    if not notified:
        result["notify_error"] = "no_notification_channel_succeeded"
    result["action"] = "notified" if notified else "state_updated_without_notification"
    logger.info(
        "programs_monitor_new_programs",
        platform=platform_spec.id,
        new=result["new_slugs"],
        email_sent=result["email_sent"],
        telegram_sent=result["telegram_sent"],
    )
    return result
