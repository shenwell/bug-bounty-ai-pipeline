"""SMTP email notifications for portfolio monitor."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from portfolio.common.config import MonitorConfig
from portfolio.common.logging import get_logger

logger = get_logger(__name__)


class EmailNotifier:
    def __init__(self, config: MonitorConfig):
        self._config = config

    def is_configured(self) -> bool:
        return bool(
            self._config.smtp_host()
            and self._config.smtp_user()
            and self._config.smtp_password()
            and self._config.notify_email()
        )

    def send_new_programs(
        self,
        programs: list[dict],
        *,
        subject_prefix: str = "[Standoff365]",
        body_intro: str = "На Standoff365 появились новые программы багбаунти:",
    ) -> bool:
        if not programs:
            return True
        if not self.is_configured():
            logger.warning("email_skipped", reason="smtp_not_configured")
            return False

        to_addr = self._config.notify_email()
        assert to_addr is not None

        lines = [body_intro, ""]
        for program in programs:
            lines.append(f"- {program['name']} ({program['slug']})")
            lines.append(f"  {program['url']}")
            if program.get("published_at"):
                lines.append(f"  published: {program['published_at']}")
            lines.append("")

        body = "\n".join(lines).strip()
        subject = f"{subject_prefix} {len(programs)} new program(s): {', '.join(p['slug'] for p in programs[:3])}"
        if len(programs) > 3:
            subject += ", ..."

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._config.from_email() or self._config.smtp_user()
        msg["To"] = to_addr
        msg.set_content(body)

        host = self._config.smtp_host()
        assert host is not None
        port = self._config.smtp_port()
        user = self._config.smtp_user()
        password = self._config.smtp_password()
        assert user is not None and password is not None

        attempts: list[tuple[int, str]] = [(port, "primary")]
        if port == 587:
            attempts.append((465, "ssl_fallback"))
        elif port == 465:
            attempts.append((587, "starttls_fallback"))

        last_error: Exception | None = None
        for attempt_port, label in attempts:
            try:
                if attempt_port == 465:
                    with smtplib.SMTP_SSL(host, attempt_port, timeout=30) as smtp:
                        smtp.login(user, password)
                        smtp.send_message(msg)
                else:
                    with smtplib.SMTP(host, attempt_port, timeout=30) as smtp:
                        smtp.starttls()
                        smtp.login(user, password)
                        smtp.send_message(msg)
                logger.info("email_sent", to=to_addr, count=len(programs), smtp_port=attempt_port, mode=label)
                return True
            except smtplib.SMTPException as exc:
                logger.warning("email_failed_after_send", smtp_port=attempt_port, mode=label, error=str(exc))
                return False
            except Exception as exc:
                last_error = exc
                logger.warning("email_attempt_failed", smtp_port=attempt_port, mode=label, error=str(exc))

        logger.warning("email_failed", error=str(last_error))
        return False
