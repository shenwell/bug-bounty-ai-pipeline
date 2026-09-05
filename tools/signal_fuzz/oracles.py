"""Differential oracle engine for signal_fuzz."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

SQL_ERROR_RE = re.compile(
    r"\b(sql syntax|mysql|postgresql|sqlite|ora-\d|unclosed quotation|sqlstate)",
    re.I,
)
INTERNAL_SSRF_RE = re.compile(
    r"\b(169\.254\.|127\.0\.0\.1|localhost|metadata|internal|private)",
    re.I,
)


def _json_fields(body: str) -> set[str]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return set()
    if isinstance(data, dict):
        return set(str(k) for k in data.keys())
    return set()


def _body_len(body: str) -> int:
    return len(body or "")


def evaluate_oracle(
    class_hint: str,
    baseline_resp: dict[str, Any],
    mutant_resp: dict[str, Any],
    pair_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate differential oracle — returns hit, signal_tier, metadata."""
    pair_meta = pair_meta or {}
    cls = (class_hint or "idor").lower()
    b_status = int(baseline_resp.get("status") or 0)
    m_status = int(mutant_resp.get("status") or 0)
    b_body = str(baseline_resp.get("body") or "")
    m_body = str(mutant_resp.get("body") or "")
    b_loc = str(baseline_resp.get("location") or "")
    m_loc = str(mutant_resp.get("location") or "")

    base = {
        "hit": False,
        "kind": "",
        "delta": "",
        "suggested_hunter": "",
        "readback_required": False,
        "readback_curl_template": "",
        "signal_tier": "trace-only",
        "suggested_class": cls,
    }

    # Latency oracle — trace-only, never export alone
    b_lat = float(baseline_resp.get("latency_ms") or 0)
    m_lat = float(mutant_resp.get("latency_ms") or 0)
    if b_lat > 0 and m_lat - b_lat > 500:
        base["hit"] = True
        base["kind"] = "latency-skew"
        base["delta"] = f"latency +{m_lat - b_lat:.0f}ms"
        base["signal_tier"] = "trace-only"
        return base

    if cls in {"idor", "bac", "privilege-escalation"}:
        if pair_meta.get("roles_available", 0) < 2:
            return base
        b_fields = _json_fields(b_body)
        m_fields = _json_fields(m_body)
        new_fields = m_fields - b_fields
        len_delta = abs(_body_len(m_body) - _body_len(b_body))
        if new_fields or (len_delta > max(50, _body_len(b_body) * 0.05) and m_status == b_status == 200):
            base["hit"] = True
            base["kind"] = "role-delta"
            base["delta"] = f"new_fields={sorted(new_fields)[:5]} len_delta={len_delta}"
            base["suggested_hunter"] = "idor-hunter"
            base["suggested_class"] = "idor"
            base["readback_required"] = True
            base["readback_curl_template"] = pair_meta.get("readback_template") or "session B GET same object_id"
            base["signal_tier"] = "oracle+readback"
            return base

    if cls == "sqli":
        if SQL_ERROR_RE.search(m_body) and not SQL_ERROR_RE.search(b_body):
            base["hit"] = True
            base["kind"] = "sqli-error-shape"
            base["delta"] = "SQL error in mutant only"
            base["suggested_hunter"] = "sqli-hunter"
            base["suggested_class"] = "sqli"
            base["signal_tier"] = "oracle+readback"
            return base

    if cls in {"business-logic", "race-condition"}:
        if m_status in (200, 201, 204) and pair_meta.get("write_mode") != "read-only":
            if b_body != m_body:
                base["hit"] = True
                base["kind"] = "state-delta"
                base["delta"] = "body changed after write mutation"
                base["suggested_hunter"] = "business-logic"
                base["suggested_class"] = "business-logic"
                base["readback_required"] = True
                base["readback_curl_template"] = pair_meta.get("readback_template") or "session C GET read-back"
                base["signal_tier"] = "oracle+readback"
                return base

    if cls == "ssrf":
        if INTERNAL_SSRF_RE.search(m_body) and not INTERNAL_SSRF_RE.search(b_body):
            base["hit"] = True
            base["kind"] = "ssrf-marker"
            base["delta"] = "internal marker in mutant body"
            base["suggested_hunter"] = "ssrf-hunter"
            base["suggested_class"] = "ssrf"
            base["signal_tier"] = "oracle+readback"
            return base

    if cls == "open-redirect":
        if m_loc and m_loc != b_loc and m_loc.startswith(("http://", "https://", "//")):
            base["hit"] = True
            base["kind"] = "redirect-delta"
            base["delta"] = f"Location: {m_loc[:120]}"
            base["suggested_hunter"] = "open-redirect"
            base["suggested_class"] = "open-redirect"
            base["signal_tier"] = "oracle+readback"
            return base

    # Unauth write 2xx marker for Rule 31 (record only)
    if pair_meta.get("unauth") and m_status in range(200, 300) and b_status in (401, 403):
        base["hit"] = True
        base["kind"] = "unauth-write"
        base["delta"] = f"unauth {m_status}"
        base["signal_tier"] = "trace-only"
        base["adversarial_battery_required"] = True
        return base

    # Trace novelty fallback
    if b_status != m_status or _body_len(b_body) != _body_len(m_body):
        base["hit"] = True
        base["kind"] = "response-delta"
        base["delta"] = f"status {b_status}->{m_status}"
        base["signal_tier"] = "trace-only"
    return base
