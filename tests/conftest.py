"""Test configuration for portfolio pipeline."""

import pytest


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setattr("portfolio.common.config.AppConfig.ensure_data_dirs", lambda self: None)
    monkeypatch.chdir(tmp_path)
    cfg_src = __import__("pathlib").Path(__file__).resolve().parents[1] / "config" / "portfolio.yaml"
    cfg_dst = tmp_path / "config" / "portfolio.yaml"
    cfg_dst.parent.mkdir(parents=True, exist_ok=True)
    cfg_dst.write_text(cfg_src.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("PORTFOLIO_CONFIG", str(cfg_dst))
    from portfolio.common.config import load_config

    cfg = load_config(str(cfg_dst))
    cfg.data.dossiers_dir = str(tmp_path / "dossiers")
    cfg.data.contracts_file = str(tmp_path / "contracts.yaml")
    cfg.data.disclosed_reports_file = str(tmp_path / "disclosed-reports.yaml")
    cfg.data.snapshots_dir = str(tmp_path / "snapshots")
    cfg.data.engagements_dir = str(tmp_path / "engagements")
    return cfg


@pytest.fixture
def tmp_db_config(config, tmp_path):
    return config
