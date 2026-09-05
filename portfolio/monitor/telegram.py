"""Telegram notifications for new bug bounty programs."""

from __future__ import annotations

import httpx

from portfolio.common.config import AppConfig
from portfolio.common.logging import get_logger

logger = get_logger(__name__)


class TelegramProgramNotifier:
    def __init__(self, config: AppConfig):
        self._enabled = config.review.telegram_enabled
        self._token = config.review.telegram_token()
        self._chat_id = config.review.telegram_chat_id()

    def is_configured(self) -> bool:
        return bool(self._enabled and self._token and self._chat_id)

    def send_new_programs(self, programs: list[dict], *, heading: str = "🆕 Новые программы Standoff365:") -> bool:
        if not programs:
            return True
        if not self.is_configured():
            logger.warning("telegram_skipped", reason="not_configured")
            return False

        lines = [heading, ""]
        for program in programs:
            lines.append(f"• *{program['name']}* (`{program['slug']}`)")
            lines.append(f"  {program['url']}")
            if program.get("published_at"):
                lines.append(f"  published: {program['published_at']}")
            lines.append("")

        text = "\n".join(lines).strip()
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        try:
            response = httpx.post(url, json=payload, timeout=30)
            response.raise_for_status()
            logger.info("telegram_sent", count=len(programs))
            return True
        except Exception as exc:
            logger.warning("telegram_failed", error=str(exc))
            return False
