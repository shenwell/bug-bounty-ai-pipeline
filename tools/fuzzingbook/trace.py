# Ported from Fuzzing Book ch.9 — adapted for HTTP BB trace species ID
"""Canonical trace tuple for greybox energy scheduling."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def _status_class(code: int) -> str:
    if 200 <= code < 300:
        return "2xx"
    if 300 <= code < 400:
        return "3xx"
    if 400 <= code < 500:
        return "4xx"
    if 500 <= code < 600:
        return "5xx"
    return "other"


def _error_class(body: str, status: int) -> str:
    low = (body or "")[:4000].lower()
    if status in (401, 403):
        return "auth"
    if status == 422 or "validation" in low or "invalid" in low:
        return "validation"
    if status >= 500 or "stack" in low or "traceback" in low or "exception" in low:
        return "server"
    if re.search(r"\b(sql|syntax error|mysql|postgres|sqlite|ora-\d)", low):
        return "sqli-shape"
    return "generic"


def _json_top_keys(body: str) -> tuple[str, ...]:
    text = (body or "").strip()
    if not text.startswith("{") and not text.startswith("["):
        return tuple()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return tuple()
    if isinstance(data, dict):
        return tuple(sorted(str(k) for k in data.keys()))
    return tuple()


def response_tuple(response: dict[str, Any]) -> tuple[str, str, tuple[str, ...]]:
    """Build canonical trace tuple — latency excluded."""
    status = int(response.get("status") or 0)
    body = str(response.get("body") or "")
    return (_status_class(status), _error_class(body, status), _json_top_keys(body))


def get_trace_key(response: dict[str, Any]) -> str:
    """Stable hash of status_class, error_class, sorted_json_top_keys."""
    parts = response_tuple(response)
    raw = "|".join((parts[0], parts[1], ",".join(parts[2])))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
