"""Tests for pipeline v4 (outcome-first, session-intent, reach/auth)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.accounts_registry import (  # noqa: E402
    empty_accounts,
    save_accounts,
    validate_no_secrets,
)
from tools.focus_areas import generate_focus_areas  # noqa: E402
from tools.intel_engine import recommend_vuln_classes  # noqa: E402
from tools.pipeline_metrics import compare_snapshots, compute_metrics, save_snapshot  # noqa: E402
from tools.scaffold import scaffold  # noqa: E402
from tools.session_bridge import (  # noqa: E402
    active_role_session_count,
    role_exhaustion_requires_multi_session,
    save_role_session,
)
from tools.session_intent import (  # noqa: E402
    save_session_intent,
    session_intent_boosts,
    validate_session_intent,
)
from tools.threat_model import save_threat_model, threat_model_path  # noqa: E402


def test_session_intent_boosts_selected_classes(tmp_path: Path) -> None:
    target = "example.com"
    save_session_intent(
        tmp_path,
        {
            "version": 1,
            "target": target,
            "session_goal": "billing IDOR",
            "selected_slice_id": "",
            "selected_classes": ["idor", "business-logic"],
            "primary_crown_jewel_ref": "",
            "differential_axis": "role-A vs role-B",
        },
    )
    boosts = session_intent_boosts(tmp_path, target)
    assert boosts.get("idor", 0) > boosts.get("business-logic", 0)


def test_recommend_vuln_classes_respects_intent_boosts() -> None:
    ranked = recommend_vuln_classes(
        tech_stack="rails",
        intent_boosts={"idor": 40.0, "xss-reflected": 5.0},
        limit=5,
    )
    classes = [r["vuln_class"] for r in ranked]
    assert "idor" in classes
    idor_row = next(r for r in ranked if r["vuln_class"] == "idor")
    assert any("session-intent" in reason for reason in idor_row["reasons"])


def test_session_intent_validate_requires_goal_and_classes(tmp_path: Path) -> None:
    target = "example.com"
    save_session_intent(tmp_path, {"version": 1, "target": target, "selected_classes": []})
    ok, issues = validate_session_intent(tmp_path, target)
    assert not ok
    assert any("session_goal" in i or "selected_classes" in i for i in issues)


def test_session_intent_resolves_crown_jewel_ref(tmp_path: Path) -> None:
    target = "example.com"
    tm = {
        "version": 1,
        "target": target,
        "crown_jewels": ["billing_data — payment records"],
        "ranked_threat_classes": [],
        "assets": [],
        "trust_boundaries": [],
        "policy_constraints": [],
        "notes": "",
    }
    save_threat_model(threat_model_path(tmp_path, target, as_json=True), tm)
    save_session_intent(
        tmp_path,
        {
            "version": 1,
            "target": target,
            "session_goal": "billing",
            "primary_crown_jewel_ref": "billing_data",
            "selected_slice_id": "",
            "selected_classes": ["idor"],
            "differential_axis": "",
        },
    )
    ok, issues = validate_session_intent(tmp_path, target)
    assert ok, issues


def test_role_exhaustion_requires_two_sessions(tmp_path: Path) -> None:
    # No auth context — gate skipped
    ok, reason = role_exhaustion_requires_multi_session(tmp_path, "idor")
    assert ok, reason
    assert "skipped" in reason.lower() or "not a multi-role" in reason.lower()

    # Auth context via traffic file — requires 2 roles
    traffic = tmp_path / "recon" / "traffic-exercised.json"
    traffic.parent.mkdir(parents=True, exist_ok=True)
    traffic.write_text('["https://api.example.com/me"]\n', encoding="utf-8")
    ok, _ = role_exhaustion_requires_multi_session(tmp_path, "idor")
    assert not ok
    save_role_session(tmp_path, "low-priv-a", {"cookies": [{"name": "s", "value": "1"}]})
    ok, _ = role_exhaustion_requires_multi_session(tmp_path, "idor")
    assert not ok
    save_role_session(tmp_path, "low-priv-b", {"cookies": [{"name": "s", "value": "2"}]})
    ok, reason = role_exhaustion_requires_multi_session(tmp_path, "idor")
    assert ok, reason
    assert active_role_session_count(tmp_path) == 2


def test_accounts_registry_rejects_literal_secrets(tmp_path: Path) -> None:
    doc = empty_accounts("example.com")
    doc["roles"] = [{"role": "a", "email_env": "user@example.com", "status": "active"}]
    issues = validate_no_secrets(doc)
    assert issues


def test_accounts_registry_accepts_env_symbols(tmp_path: Path) -> None:
    doc = empty_accounts("example.com")
    doc["roles"] = [{"role": "a", "email_env": "${HACKERONE_EMAIL_ALIAS}", "status": "active"}]
    assert not validate_no_secrets(doc)
    path = save_accounts(tmp_path, doc)
    assert path.exists()


def test_pipeline_metrics_snapshot(tmp_path: Path) -> None:
    (tmp_path / "brain" / "sessions").mkdir(parents=True)
    (tmp_path / "brain" / "sessions" / "2026-08-10.md").write_text("# session\n", encoding="utf-8")
    (tmp_path / "response-history.json").write_text(
        json.dumps(
            {
                "reports": [
                    {"status": "accepted", "bounty": 500},
                    {"status": "informative", "bounty": 0},
                    {"status": "duplicate", "bounty": 0},
                ],
                "insights": {},
            }
        ),
        encoding="utf-8",
    )
    metrics = compute_metrics(tmp_path)
    assert metrics["platform"]["validity_ratio"] == 0.5
    assert abs(metrics["platform"]["dup_rate"] - (1 / 3)) < 0.001
    out = save_snapshot(tmp_path, "example.com", "baseline")
    assert out.exists()


def test_pipeline_metrics_compare_improved() -> None:
    baseline = {
        "platform": {"validity_ratio": 0.3, "dup_rate": 0.2},
        "sessions": {"judge_confirmed_per_session": 0.1},
        "findings": {"judge_confirmed": 1},
    }
    after = {
        "platform": {"validity_ratio": 0.5, "dup_rate": 0.1},
        "sessions": {"judge_confirmed_per_session": 0.2},
        "findings": {"judge_confirmed": 2},
    }
    cmp = compare_snapshots(baseline, after)
    assert cmp["improved"] is True


def test_scaffold_contains_session_mindset(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    workspace = tmp_path / "h1-demo"
    scaffold("hackerone", "demo", str(workspace))
    brief = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert "Session Mindset" in brief
    assert "brain/session-intent" in brief
    assert (workspace / "brain" / "session-intent").is_dir()
    assert (workspace / "brain" / "accounts").is_dir()
    assert (workspace / "brain" / "metrics").is_dir()


def test_session_intent_slice_subset_validation(tmp_path: Path) -> None:
    target = "example.com"
    endpoints = ["https://api.example.com/v1/users/1"]
    fa = generate_focus_areas(target, endpoints)
    fa_path = tmp_path / "brain" / "focus-areas" / "example-com.json"
    fa_path.parent.mkdir(parents=True, exist_ok=True)
    fa_path.write_text(json.dumps(fa), encoding="utf-8")
    save_session_intent(
        tmp_path,
        {
            "version": 1,
            "target": target,
            "session_goal": "api idor",
            "selected_slice_id": "api_core",
            "selected_classes": ["idor", "graphql"],
            "primary_crown_jewel_ref": "",
            "differential_axis": "own vs other user",
        },
    )
    ok, issues = validate_session_intent(tmp_path, target)
    assert ok, issues
