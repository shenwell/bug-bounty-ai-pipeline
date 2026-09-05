"""Tests for scope matching and landscape dossiers."""

from pathlib import Path

from portfolio.common.models import Contract, DisclosedReport
from portfolio.discovery.landscape import build_landscape_markdown, enrich_contract_landscape
from portfolio.discovery.scope_match import (
    bind_disclosed_to_scope,
    compute_scope_coverage,
    host_matches_pattern,
)


def test_host_matches_wildcard_scope():
    assert host_matches_pattern("api.example.com", "*.example.com")
    assert host_matches_pattern("www.example.com", "example.com")
    assert not host_matches_pattern("evil.com", "*.example.com")


def test_bind_disclosed_to_scope():
    contract = Contract(
        program_id="demo",
        slug="demo",
        name="Demo",
        scope=["*.example.com", "app.example.com"],
        out_of_scope=["staging.example.com"],
    )
    report = DisclosedReport(
        report_no="100",
        title="SSRF on api.example.com",
        program_slug="demo",
        hosts=["api.example.com"],
        vuln_classes=["ssrf"],
        poc="Blind SSRF via webhook",
    )
    oos_report = DisclosedReport(
        report_no="101",
        title="XSS staging",
        program_slug="demo",
        hosts=["staging.example.com"],
        vuln_classes=["xss"],
    )
    bindings = bind_disclosed_to_scope(contract, [report, oos_report])
    assert bindings[0].in_scope
    assert "api.example.com" in bindings[0].matched_hosts
    assert not bindings[1].in_scope
    assert "staging.example.com" in bindings[1].out_of_scope_hosts


def test_compute_scope_gaps():
    contract = Contract(
        program_id="demo",
        slug="demo",
        name="Demo",
        scope=["api.example.com", "admin.example.com"],
    )
    report = DisclosedReport(
        report_no="1",
        program_slug="demo",
        hosts=["api.example.com"],
        vuln_classes=["idor"],
        title="IDOR",
    )
    bindings = bind_disclosed_to_scope(contract, [report])
    avoid_hosts, avoid_vectors, gaps = compute_scope_coverage(contract, bindings)
    assert "api.example.com" in avoid_hosts
    assert "idor" in avoid_vectors
    assert "admin.example.com" in gaps


def test_build_landscape_markdown():
    contract = Contract(
        program_id="demo",
        slug="demo",
        name="Demo Program",
        scope=["api.example.com"],
        is_paid=True,
        tab_sections={"Vulnerabilities": "Known XSS in editor"},
        source_url="https://bugbounty.standoff365.com/en-US/programs/demo",
    )
    report = DisclosedReport(
        report_no="42",
        title="SSRF",
        severity="High",
        program_slug="demo",
        hosts=["api.example.com"],
        vuln_classes=["ssrf"],
        poc="curl PoC",
    )
    bindings = bind_disclosed_to_scope(contract, [report])
    avoid_hosts, avoid_vectors, gaps = compute_scope_coverage(contract, bindings)
    md = build_landscape_markdown(contract, bindings, avoid_hosts, avoid_vectors, gaps)
    assert "## DO" in md
    assert "## DON'T" in md
    assert "api.example.com" in md
    assert "Vulnerabilities" in md
    assert "SSRF" in md


def test_enrich_contract_landscape_writes_file(tmp_path):
    from portfolio.common.config import AppConfig

    config = AppConfig()
    config.data.dossiers_dir = str(tmp_path / "dossiers")
    contract = Contract(
        program_id="demo",
        slug="demo",
        name="Demo",
        scope=["api.example.com"],
        source_url="https://example.com",
    )
    report = DisclosedReport(
        report_no="1",
        title="Test",
        program_slug="demo",
        hosts=["api.example.com"],
        vuln_classes=["xss"],
    )
    enriched = enrich_contract_landscape(config, contract, [report])
    assert enriched.landscape_file
    path = Path(enriched.landscape_file)
    assert path.exists()
    assert "landscape.md" in enriched.landscape_file
    assert enriched.avoid_hosts == ["api.example.com"]
    assert "in-scope@api.example.com" in enriched.known_findings[0]

