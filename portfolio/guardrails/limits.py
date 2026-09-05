"""Rate limiting and scan time budgets."""

from __future__ import annotations

import time
from collections import defaultdict

from portfolio.common.config import LimitsConfig


class RateLimiter:
    def __init__(self, config: LimitsConfig):
        self._rps = config.rate_limit_rps
        self._last_request: dict[str, float] = defaultdict(float)
        self._counters: dict[str, int] = defaultdict(int)
        self._min_interval = 1.0 / max(self._rps, 0.1)

    def acquire(self, key: str = "global") -> None:
        now = time.monotonic()
        elapsed = now - self._last_request[key]
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request[key] = time.monotonic()

    def request_count(self, target: str) -> int:
        return self._counters.get(target, 0)

    def record_request(self, target: str) -> int:
        self._counters[target] += 1
        return self._counters[target]


class ScanBudget:
    def __init__(self, budget_minutes: int):
        self._budget_sec = budget_minutes * 60
        self._start = time.monotonic()

    def elapsed_sec(self) -> float:
        return time.monotonic() - self._start

    def remaining_sec(self) -> float:
        return max(0, self._budget_sec - self.elapsed_sec())

    def is_exhausted(self) -> bool:
        return self.elapsed_sec() >= self._budget_sec

    def check(self) -> None:
        if self.is_exhausted():
            raise TimeoutError("Scan time budget exhausted")
