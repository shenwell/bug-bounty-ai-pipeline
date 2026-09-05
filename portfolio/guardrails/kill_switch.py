"""Emergency kill-switch."""

from __future__ import annotations

import threading

from portfolio.common.logging import get_logger

logger = get_logger(__name__)


class KillSwitch:
    _instance: "KillSwitch | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "KillSwitch":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._active = False
                cls._instance._reason = ""
            return cls._instance

    @property
    def active(self) -> bool:
        return self._active

    @property
    def reason(self) -> str:
        return self._reason

    def activate(self, reason: str = "manual") -> None:
        self._active = True
        self._reason = reason
        logger.warning("kill_switch_activated", reason=reason)

    def deactivate(self) -> None:
        self._active = False
        self._reason = ""
        logger.info("kill_switch_deactivated")

    def check(self) -> None:
        if self._active:
            raise RuntimeError(f"Kill switch active: {self._reason}")
