"""Redact secrets from export artifacts and JSONL."""

from __future__ import annotations

import re
from typing import Any

REDACT_PATTERNS = (
    (re.compile(r"(Authorization:\s*)\S+", re.I), r"\1[REDACTED]"),
    (re.compile(r"(Cookie:\s*)\S+", re.I), r"\1[REDACTED]"),
    (re.compile(r'("(?:token|password|secret|api_key)"\s*:\s*")[^"]*"', re.I), r'\1[REDACTED]"'),
    (re.compile(r"(Bearer\s+)\S+", re.I), r"\1[REDACTED]"),
    (re.compile(r"(\+?\d{10,15})"), "[REDACTED-PHONE]"),
    (re.compile(r"[\w.+-]+@[\w.-]+\.\w+"), "[REDACTED-EMAIL]"),
)


def redact_text(text: str) -> str:
    out = text or ""
    for pattern, repl in REDACT_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def redact_dict(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: redact_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_dict(v) for v in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj
