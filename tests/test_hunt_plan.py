"""Tests for hunt plan generation."""

from pathlib import Path

from portfolio.common.models import Contract, DisclosedReport
from portfolio.discovery.hunt_plan import build_hunt_plan_markdown, write_hunt_plan


def test_build_hunt_plan_includes_scope_and_gaps():
    contract = Contract(
        program_id="demo",
        slug="demo",
        name="Demo",
        scope=["api.example.com", "admin.example.com"],
        out_of_scope=["staging.example.com"],
        target_vectors=["idor", "ssrf"],
        source_url="https://bugbounty.standoff365.com/en-US/programs/demo",
        tab_sections={
            "Description": (
                "## What we accept\n"
                "- Account takeover\n"
                "- Data exfiltration\n"
                "## What we do not accept\n"
                "- Self-XSS\n"
                "- Missing security headers\n"
            ),
        },
        dossier_refreshed_at="2026-07-23T12:00:00+00:00",
    )
    report = DisclosedReport(
        report_no="42",
        title="IDOR on api",
        program_slug="demo",
        hosts=["api.example.com"],
        vuln_classes=["idor"],
        severity="high",
        poc="GET /users/1 returns other user data",
    )
    md = build_hunt_plan_markdown(contract, [report])
    assert "api.example.com" in md
    assert "admin.example.com" in md
    assert "admin.example.com" in md and "приоритет разведки" in md
    assert "idor" in md.lower()
    assert "Self-XSS" in md or "self-xss" in md.lower()
    assert "#42" in md
    assert "Hunt checklist" in md or "checklist" in md.lower()


def test_write_hunt_plan_creates_file(config, tmp_path, monkeypatch):
    monkeypatch.setattr(config.data, "dossiers_dir", str(tmp_path / "dossiers"))
    contract = Contract(
        program_id="demo",
        slug="demo",
        name="Demo",
        scope=["api.example.com"],
        source_url="https://bugbounty.standoff365.com/en-US/programs/demo",
    )
    path = write_hunt_plan(config, contract, [])
    assert Path(path).exists()
    content = Path(path).read_text(encoding="utf-8")
    assert "План проверки" in content
    assert "hunt_plan.md" in path.replace("\\", "/")

