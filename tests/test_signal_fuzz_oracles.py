"""Oracle engine unit tests for signal_fuzz."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from signal_fuzz.oracles import evaluate_oracle  # noqa: E402


def test_idor_oracle_skips_single_role() -> None:
    base = {"status": 200, "body": '{"id":1}'}
    mutant = {"status": 200, "body": '{"id":1,"email":"x@y.com"}'}
    out = evaluate_oracle("idor", base, mutant, {"roles_available": 1})
    assert out["signal_tier"] == "trace-only"
    assert out["hit"] is False


def test_idor_oracle_pass_with_role_delta() -> None:
    base = {"status": 200, "body": '{"id":1}'}
    mutant = {"status": 200, "body": '{"id":1,"email":"victim@example.com","role":"admin"}'}
    out = evaluate_oracle("idor", base, mutant, {"roles_available": 2})
    assert out["hit"] is True
    assert out["signal_tier"] == "oracle+readback"


def test_sqli_oracle_pass() -> None:
    base = {"status": 400, "body": "bad request"}
    mutant = {"status": 500, "body": "You have an error in your SQL syntax"}
    out = evaluate_oracle("sqli", base, mutant, {})
    assert out["hit"] is True
    assert out["signal_tier"] == "oracle+readback"


def test_open_redirect_oracle_pass() -> None:
    base = {"status": 302, "body": "", "location": "https://example.com/login"}
    mutant = {"status": 302, "body": "", "location": "https://evil.com/steal"}
    out = evaluate_oracle("open-redirect", base, mutant, {})
    assert out["hit"] is True
    assert out["signal_tier"] == "oracle+readback"


def test_latency_oracle_trace_only() -> None:
    base = {"status": 200, "body": "{}", "latency_ms": 100}
    mutant = {"status": 200, "body": "{}", "latency_ms": 800}
    out = evaluate_oracle("idor", base, mutant, {"roles_available": 2})
    assert out["hit"] is True
    assert out["signal_tier"] == "trace-only"
