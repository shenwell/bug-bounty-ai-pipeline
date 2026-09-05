"""Bug Magnet canonical strings + mutation helpers."""

from __future__ import annotations

# Non-PII boundary strings for string-field probes (Bug Magnet subset)
BOUNDARY_STRINGS: list[str] = [
    "",
    " ",
    "\x00",
    "%00",
    "'",
    '"',
    "\\",
    "../",
    "..\\",
    "<script>alert(1)</script>",
    "{{7*7}}",
    "${7*7}",
    "🙂" * 50,
    "A" * 256,
    "A" * 4097,
    "-1",
    "0",
    "2147483647",
    "2147483648",
    "NaN",
    "null",
    "undefined",
    "true",
    "false",
    "1e999",
    "%n",
    "%s",
]

PII_FIELD_DENYLIST = frozenset(
    {
        "email",
        "phone",
        "password",
        "token",
        "authorization",
        "cookie",
        "ssn",
        "credit_card",
    }
)
