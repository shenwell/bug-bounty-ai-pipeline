"""Tests for contract dossier folder layout."""

import json
from pathlib import Path

from portfolio.common.models import Contract, DisclosedReport
from portfolio.discovery.dossier import (
    dossier_layout,
    ensure_dossier,
    init_selected_dossier,
    save_contract_snapshot,
    save_disclosed_snapshot,
)


def test_ensure_dossier_creates_structure(config, tmp_path, monkeypatch):
    monkeypatch.setattr(config.data, "dossiers_dir", str(tmp_path / "dossiers"))
    root = ensure_dossier(config, "demo")
    assert root.exists()
    for sub in ("raw", "external_refs", "findings", "reports", "recon"):
        assert (root / sub).is_dir()


def test_init_selected_dossier(config, tmp_path, monkeypatch):
    monkeypatch.setattr(config.data, "dossiers_dir", str(tmp_path / "dossiers"))
    contract = Contract(
        program_id="demo",
        slug="demo",
        name="Demo",
        scope=["api.example.com"],
        source_url="https://bugbounty.standoff365.com/en-US/programs/demo",
    )
    reports = [
        DisclosedReport(report_no="1", title="XSS", program_slug="demo", hosts=["api.example.com"])
    ]
    result = init_selected_dossier(config, contract, reports, stage="select", session_id="abc")
    root = Path(result.dossier_dir)
    assert (root / "README.md").exists()
    assert (root / "STATUS.md").exists()
    assert (root / "contract.json").exists()
    assert (root / "disclosed.json").exists()
    disclosed = json.loads((root / "disclosed.json").read_text(encoding="utf-8"))
    assert disclosed["count"] == 1
    assert result.dossier_dir.endswith("dossiers/demo".replace("/", "\\")) or "dossiers/demo" in result.dossier_dir


def test_should_recon_asset_skips_storefronts():
    from portfolio.discovery.dossier import should_recon_asset

    assert should_recon_asset("hh.ru") is True
    assert should_recon_asset("api.setka.ru") is True
    assert should_recon_asset("https://play.google.com/store/apps/details?id=com.setka") is False
    assert should_recon_asset("apps.apple.com") is False
    assert should_recon_asset("user1") is False


def test_write_hunt_bootstrap(config, tmp_path, monkeypatch):
    from portfolio.discovery.dossier import write_hunt_bootstrap, write_workspace_pointer

    monkeypatch.setattr(config.data, "dossiers_dir", str(tmp_path / "dossiers"))
    contract = Contract(
        program_id="demo",
        slug="demo",
        name="Demo",
        scope=["api.example.com"],
        source_url="https://bugbounty.standoff365.com/en-US/programs/demo",
    )
    write_workspace_pointer(config, contract)
    write_hunt_bootstrap(config, contract, recon_note="test recon")
    root = tmp_path / "dossiers" / "demo"
    assert (root / "WORKSPACE.md").exists()
    assert (root / "hunt" / "00-pipeline-phases.md").exists()
    assert (root / "hunt" / "03-leads.md").exists()
    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    assert status["kanban_column"] == "recon"
    assert status["phases"]["recon"] == "done"


def test_dossier_layout(config, tmp_path, monkeypatch):
    monkeypatch.setattr(config.data, "dossiers_dir", str(tmp_path / "dossiers"))
    contract = Contract(program_id="demo", slug="demo", name="Demo")
    save_contract_snapshot(config, contract)
    layout = dossier_layout(config, "demo")
    assert layout["root"]
    assert layout["contract"]

