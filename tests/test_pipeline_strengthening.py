"""Tests for pipeline strengthening tools (threat model, focus areas, waves, findings)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.focus_areas import generate_focus_areas, get_slice, slice_class_boosts  # noqa: E402
from tools.finding_record import (  # noqa: E402
    create_finding,
    empty_finding,
    gates_complete_for_confirm,
    update_gate,
)
from tools.intel_engine import rank_surface, recommend_vuln_classes  # noqa: E402
from tools.never_submit_filter import check_finding  # noqa: E402
from tools.threat_model import ranked_class_boosts, save_threat_model, slugify_target  # noqa: E402
from tools.wave_ledger import complete_slice, start_wave  # noqa: E402
from tools.witness import evaluate_witness  # noqa: E402
from tools.cvss_version_guard import validate_vector  # noqa: E402
from tools.cvss_calc import calculate_score  # noqa: E402


def test_slugify_target() -> None:
    assert slugify_target("api.Example.COM") == "api-example-com"


def test_focus_areas_generate() -> None:
    endpoints = [
        "https://auth.example.com/oauth/callback",
        "https://api.example.com/v1/users/1",
    ]
    tm = {
        "ranked_threat_classes": [{"class": "oauth", "priority": 1}, {"class": "idor", "priority": 2}],
    }
    doc = generate_focus_areas("example.com", endpoints, threat_model=tm)
    assert doc["slices"]
    auth = get_slice(doc, "auth_oauth")
    assert auth is not None
    assert "auth.example.com" in auth["hosts"][0]


def test_slice_class_boosts() -> None:
    row = {"priority_classes": ["oauth", "idor"]}
    boosts = slice_class_boosts(row)
    assert boosts["oauth"] > boosts["idor"]


def test_threat_model_boosts_ranking() -> None:
    tm = {"ranked_threat_classes": [{"class": "idor", "priority": 1}]}
    boosts = ranked_class_boosts(tm)
    ranked = recommend_vuln_classes("rails", threat_boosts=boosts, limit=5)
    classes = [r["vuln_class"] for r in ranked]
    assert "idor" in classes


def test_traffic_boost_rank_surface() -> None:
    hits = {"https://api.example.com/v1/users": 3}
    ranked = rank_surface(["https://api.example.com/v1/users"], traffic_hits=hits)
    assert ranked[0]["score"] > 14


def test_finding_record_gates() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rec = empty_finding(target="api.example.com", host="api.example.com", vuln_class="idor")
        rec["evidence"]["exploit_curl"] = "curl -s ..."
        rec["evidence"]["readback_curl"] = "curl -s ..."
        rec["evidence"]["marker"] = "email differs"
        path = create_finding(root, rec)
        witness = evaluate_witness(rec)
        assert witness["ok"] is True
        update_gate(root, path, "witness", witness)
        update_gate(root, path, "validator", {"decision": "PASS"})
        update_gate(root, path, "devils_advocate", {"verdict": "SURVIVES"})
        update_gate(root, path, "evidence_score", {"score": 80, "decision": "PASS"})
        record = json.loads(path.read_text())
        ok, missing = gates_complete_for_confirm(record)
        assert ok, missing


def test_witness_idor_fails_without_readback() -> None:
    rec = empty_finding(target="t", host="t", vuln_class="idor")
    rec["evidence"]["exploit_curl"] = "curl"
    result = evaluate_witness(rec)
    assert result["ok"] is False


def test_wave_ledger_start() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fa = {
            "target": "example.com",
            "slices": [
                {
                    "id": "auth_oauth",
                    "name": "Auth",
                    "hosts": ["auth.example.com"],
                    "endpoint_patterns": [],
                    "priority_classes": ["oauth"],
                    "status": "pending",
                }
            ],
        }
        fa_path = root / "brain" / "focus-areas" / "example-com.json"
        fa_path.parent.mkdir(parents=True)
        fa_path.write_text(json.dumps(fa))
        doc = start_wave(root, "example.com")
        assert doc["current_wave"] == 1


def test_never_submit_blocks_open_redirect() -> None:
    finding = {"title": "Open redirect in login", "class": "open-redirect"}
    result = check_finding(finding)
    assert result["block"] is True


def test_never_submit_allows_with_chain() -> None:
    finding = {"title": "Open redirect", "class": "open-redirect", "chain_id": "chain-1"}
    result = check_finding(finding)
    assert result["block"] is False


def test_cvss_version_guard_h1() -> None:
    ok = validate_vector("hackerone", "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N")
    assert ok["ok"] is True
    bad = validate_vector("hackerone", "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:N/SC:N/SI:N/SA:N")
    assert bad["ok"] is False


def test_cvss_calc_31() -> None:
    result = calculate_score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N")
    assert result["score"] is not None
    assert result["score"] > 0


def test_traffic_informed_validate_with_auth(tmp_path: Path) -> None:
    import tempfile
    from tools.traffic_informed import validate_traffic_informed, has_auth_context

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "auth_accounts.md").write_text("manager@test\n", encoding="utf-8")
        ok, _ = validate_traffic_informed(root)
        assert ok is False
        assert has_auth_context(root) is True
        recon = root / "recon"
        recon.mkdir()
        eps = [{"endpoint": f"https://api.example.com/v1/r{i}", "request_count": 1} for i in range(6)]
        (recon / "traffic-exercised.json").write_text(json.dumps(eps), encoding="utf-8")
        ok2, _ = validate_traffic_informed(root)
        assert ok2 is True


def test_session_bridge_exhaustion_block(tmp_path: Path) -> None:
    from tools.session_bridge import injection_exhaustion_requires_session

    (tmp_path / "brain" / "techniques").mkdir(parents=True)
    (tmp_path / "brain" / "techniques" / "waf-bypasses.md").write_text(
        "WAF: Cloudflare\nBlocked: alert\n", encoding="utf-8"
    )
    allowed, _ = injection_exhaustion_requires_session(tmp_path, "xss")
    assert allowed is False
    (tmp_path / "recon").mkdir()
    (tmp_path / "recon" / "session.json").write_text('{"cookies":[]}', encoding="utf-8")
    allowed2, _ = injection_exhaustion_requires_session(tmp_path, "xss")
    assert allowed2 is True


def test_evidence_score_readback_boost() -> None:
    from tools.evidence_score import score_finding

    rec = {
        "class": "idor",
        "title": "IDOR on users",
        "evidence": {
            "exploit_curl": "curl ...",
            "readback_curl": "curl ...",
            "marker": "other user email",
        },
        "gates": {"witness": {"ok": True}},
    }
    result = score_finding(rec)
    assert result["score"] >= 75
    assert result["decision"] == "PASS"


def test_finding_cluster_best_witness(tmp_path: Path) -> None:
    from tools.finding_cluster import cluster_findings
    from tools.finding_record import create_finding, empty_finding, update_gate

    host = "api.example.com"
    weak = empty_finding(target="example.com", host=host, vuln_class="idor", title="idor on users")
    weak["evidence"] = {"exploit_curl": "curl https://api.example.com/v1/users/1"}
    create_finding(tmp_path, weak)
    strong = empty_finding(target="example.com", host=host, vuln_class="idor", title="idor on users")
    strong["evidence"] = {
        "exploit_curl": "curl https://api.example.com/v1/users/1",
        "readback_curl": "curl readback",
        "marker": "delta",
    }
    p2 = create_finding(tmp_path, strong)
    update_gate(tmp_path, p2, "witness", {"ok": True})
    index = cluster_findings(tmp_path)
    assert index["total_findings"] == 2
    ranked = sorted(index["best"], key=lambda x: x["witness_rank"], reverse=True)
    assert ranked[0]["witness_ok"] is True
    assert ranked[0]["witness_rank"] > ranked[1]["witness_rank"]


def test_chain_plan_reads_structured_findings(tmp_path: Path) -> None:
    from tools.finding_record import create_finding, empty_finding, update_gate
    from tools.chain_plan import _read_structured_findings

    rec = empty_finding(
        target="example.com",
        host="api.example.com",
        vuln_class="open-redirect",
        title="Open redirect in login",
    )
    rec["evidence"]["exploit_curl"] = "curl 'https://api.example.com/login?next=https://evil.com'"
    path = create_finding(tmp_path, rec)
    update_gate(tmp_path, path, "witness", {"ok": True})
    found = _read_structured_findings(tmp_path)
    assert len(found) == 1
    assert found[0].get("class") == "open-redirect"


def test_detect_ai_infra_ollama_port(tmp_path: Path) -> None:
    from tools.intel_engine import detect_ai_infra

    rules = tmp_path / "rules"
    rules.mkdir()
    shutil.copy(
        Path(__file__).resolve().parents[1] / "rules" / "ai-infra-fingerprints.json",
        rules / "ai-infra-fingerprints.json",
    )
    (tmp_path / "recon").mkdir()
    (tmp_path / "recon" / "live-hosts.txt").write_text("http://127.0.0.1:11434\n", encoding="utf-8")
    result = detect_ai_infra(tmp_path)
    assert result["ai_surface"] is True
    assert any(m.get("component") == "ollama" for m in result["matches"])


def test_score_surface_endpoint_fuzz_boost() -> None:
    from tools.intel_engine import score_surface_endpoint

    signals = [
        {
            "endpoint": "https://api.example.com/v1/users/1",
            "signal_tier": "oracle+readback",
            "energy": 2.0,
        }
    ]
    base = score_surface_endpoint("https://api.example.com/v1/users/1")
    boosted = score_surface_endpoint(
        "https://api.example.com/v1/users/1",
        fuzz_signals=signals,
    )
    assert boosted["score"] > base["score"]


def test_signal_fuzz_export_tier_filter(tmp_path: Path) -> None:
    from tools.signal_fuzz.export import export_signals, save_run_state

    state = {
        "queued_signals": [
            {"id": "sf-001", "signal_tier": "oracle+readback", "endpoint": "https://api.example.com/x"},
            {"id": "sf-002", "signal_tier": "trace-only", "endpoint": "https://api.example.com/y"},
        ]
    }
    save_run_state(tmp_path, state)
    out, signals = export_signals(tmp_path)
    assert len(signals) == 1
    assert signals[0]["id"] == "sf-001"


def test_signal_fuzz_validate_compose(tmp_path: Path) -> None:
    from tools.signal_fuzz.corpus import build_corpus, save_corpus
    from tools.signal_fuzz.validate import validate_compose

    recon = tmp_path / "recon"
    recon.mkdir()
    (recon / "endpoints-auth.txt").write_text("https://api.example.com/v1/users\n", encoding="utf-8")
    (tmp_path / "scope.yaml").write_text(
        "in_scope:\n  - '*.example.com'\nout_of_scope: []\n",
        encoding="utf-8",
    )
    seeds = build_corpus(tmp_path)
    save_corpus(tmp_path, seeds)
    ok, messages = validate_compose(tmp_path)
    assert any("corpus" in m for m in messages)


def test_signal_fuzz_corpus_adapter_traffic(tmp_path: Path) -> None:
    from tools.signal_fuzz.corpus import adapter_traffic_exercised

    recon = tmp_path / "recon"
    recon.mkdir()
    eps = [{"endpoint": "https://api.example.com/v1/items", "request_count": 3}]
    (recon / "traffic-exercised.json").write_text(__import__("json").dumps(eps), encoding="utf-8")
    seeds = adapter_traffic_exercised(tmp_path)
    assert len(seeds) == 1
    assert seeds[0]["method"] == "GET"
