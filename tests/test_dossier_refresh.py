"""Tests for post-select dossier refresh."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from portfolio.common.models import Contract, ContractStatus
from portfolio.discovery.dossier_refresh import apply_program_html, refresh_contract_dossier, save_raw_dossier
from portfolio.discovery.next_data_parser import extract_program_page_props

SAMPLE_HTML = """
<html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"program":{"id":"1","name":"Demo","slug":"demo"},"reward":{"critical":{"maxReward":50000},"currency":"rub"}}}}
</script>
<h2>Scope</h2><p>api.example.com</p>
</body></html>
"""


def test_save_raw_dossier_archives_html_and_props(config, tmp_path, monkeypatch):
    monkeypatch.setattr(config.data, "dossiers_dir", str(tmp_path / "dossiers"))
    page_props = extract_program_page_props(SAMPLE_HTML)
    raw_dir = save_raw_dossier(
        config,
        "demo",
        html=SAMPLE_HTML,
        page_props=page_props,
        source_url="https://bugbounty.standoff365.com/en-US/programs/demo/",
    )
    assert (raw_dir / "page.html").exists()
    assert (raw_dir / "page_props.json").exists()
    assert (raw_dir / "program.json").exists()
    assert (raw_dir / "reward.json").exists()
    meta = json.loads((raw_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["has_page_props"] is True


@pytest.mark.asyncio
async def test_refresh_contract_dossier_updates_contract(config, tmp_path, monkeypatch):
    monkeypatch.setattr(config.data, "dossiers_dir", str(tmp_path / "dossiers"))
    contract = Contract(
        id="existing-id",
        program_id="prog-1",
        slug="demo",
        name="Demo",
        score=0.5,
        score_reason="old",
        source_url="https://bugbounty.standoff365.com/en-US/programs/demo/",
        status=ContractStatus.SCORED,
    )
    scraper = AsyncMock()
    scraper.fetch_program_page = AsyncMock(
        return_value=(
            "https://bugbounty.standoff365.com/en-US/programs/demo/",
            SAMPLE_HTML,
            {"Description": "Test description", "Scope": "api.example.com"},
        )
    )
    refreshed, page_props = await refresh_contract_dossier(config, contract, scraper)
    scraper.fetch_program_page.assert_awaited_once()
    call_kwargs = scraper.fetch_program_page.await_args.kwargs
    assert call_kwargs.get("next_data_only") is True
    assert refreshed.id == "existing-id"
    assert refreshed.program_id == "prog-1"
    assert refreshed.score == 0.5
    assert refreshed.dossier_refreshed_at
    assert refreshed.hunt_plan_file
    assert Path(refreshed.hunt_plan_file).exists()
    assert Path(refreshed.landscape_file).exists()
    assert page_props is not None


def test_apply_program_html_rebuilds_landscape(config, tmp_path, monkeypatch):
    monkeypatch.setattr(config.data, "dossiers_dir", str(tmp_path / "dossiers"))
    contract = Contract(
        id="existing-id",
        program_id="prog-1",
        slug="demo",
        name="Demo",
        score=0.5,
        source_url="https://bugbounty.standoff365.com/en-US/programs/demo/",
        status=ContractStatus.SCORED,
    )
    refreshed, page_props = apply_program_html(
        config,
        contract,
        html=SAMPLE_HTML,
        url="https://bugbounty.standoff365.com/en-US/programs/demo/",
        tab_sections={"Description": "Test", "Scope": "api.example.com"},
        disclosed_reports=[],
    )
    assert refreshed.id == "existing-id"
    assert refreshed.score == 0.5
    assert Path(refreshed.hunt_plan_file).exists()
    assert Path(refreshed.landscape_file).exists()
    assert page_props is not None

