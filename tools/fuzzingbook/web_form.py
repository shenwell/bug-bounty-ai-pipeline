# Ported from Fuzzing Book ch.15 — adapted for cabinet HTML form grammar
"""Extract form fields from cabinet HTML snippets."""

from __future__ import annotations

import re
from typing import Any


INPUT_RE = re.compile(
    r'<input[^>]+name=["\']([^"\']+)["\'][^>]*>',
    re.I,
)
TEXTAREA_RE = re.compile(
    r'<textarea[^>]+name=["\']([^"\']+)["\']',
    re.I,
)
SELECT_RE = re.compile(
    r'<select[^>]+name=["\']([^"\']+)["\']',
    re.I,
)
MAXLEN_RE = re.compile(r'maxlength=["\']?(\d+)', re.I)
TYPE_RE = re.compile(r'type=["\']([^"\']+)["\']', re.I)


def extract_form_fields(html: str) -> list[dict[str, Any]]:
    """Return form field descriptors from HTML fragment."""
    fields: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern, default_type in (
        (INPUT_RE, "text"),
        (TEXTAREA_RE, "textarea"),
        (SELECT_RE, "select"),
    ):
        for m in pattern.finditer(html or ""):
            name = m.group(1)
            if name in seen:
                continue
            seen.add(name)
            tag = m.group(0)
            ftype = default_type
            tm = TYPE_RE.search(tag)
            if tm:
                ftype = tm.group(1).lower()
            ml = MAXLEN_RE.search(tag)
            fields.append(
                {
                    "name": name,
                    "type": ftype,
                    "maxlength": int(ml.group(1)) if ml else None,
                }
            )
    return fields
