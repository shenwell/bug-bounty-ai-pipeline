"""Tests for dossier STATUS.md dashboard."""

import json
from pathlib import Path

from portfolio.discovery.dossier_status import (
    collect_dossier_status,
    render_portfolio_md,
    render_status_md,
    write_dossier_status,
)


def test_collect_and_render_status(config, tmp_path, monkeypatch):
    root = tmp_path / "dossiers" / "demo"
    root.mkdir(parents=True)
    (root / "contract.json").write_text(
        json.dumps(
            {
                "saved_at": "2026-07-31T10:00:00+00:00",
                "contract": {
                    "slug": "demo",
                    "name": "Demo Program",
                    "score": 0.9,
                    "source_url": "https://example.com/demo",
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "status.json").write_text(
        json.dumps(
            {
                "overall": "blocked",
                "overall_label": "Test blocker",
                "blocker": "No accounts",
                "next_step": "Request creds",
            }
        ),
        encoding="utf-8",
    )
    (root / "hunt").mkdir()
    (root / "hunt" / "00-pipeline-phases.md").write_text(
        "| Р¤Р°Р·Р° | РЎС‚Р°С‚СѓСЃ | РџСЂРёРјРµС‡Р°РЅРёРµ |\n|------|--------|------------|\n"
        "| SELECT | done | ok |\n| HUNT | blocked | no auth |\n",
        encoding="utf-8",
    )

    status = collect_dossier_status(root)
    assert status["overall"] == "blocked"
    assert status["blocker"] == "No accounts"
    assert "select" in status["phases"]

    md = render_status_md(status)
    assert "Demo Program" in md
    assert "No accounts" in md
    assert "SELECT" in md


def test_write_dossier_status(config, tmp_path, monkeypatch):
    monkeypatch.setattr(config.data, "dossiers_dir", str(tmp_path / "dossiers"))
    root = tmp_path / "dossiers" / "demo"
    root.mkdir(parents=True)
    (root / "contract.json").write_text(
        json.dumps({"contract": {"slug": "demo", "name": "Demo"}}),
        encoding="utf-8",
    )

    path = write_dossier_status(config, "demo")
    assert path.exists()
    assert "Статус — Demo" in path.read_text(encoding="utf-8")


def test_render_portfolio_md():
    md = render_portfolio_md(
        [
            {
                "slug": "alpha",
                "name": "Alpha",
                "overall": "active",
                "overall_label": "В работе",
                "blocker": "",
                "next_step": "Hunt API",
                "phases": {"hunt": {"status": "in_progress", "note": ""}},
                "findings": {"total": 1},
                "reports": {"submit_ready": 0},
            }
        ]
    )
    assert "Портфель программ" in md
    assert "Alpha" in md
    assert "alpha/STATUS.md" in md

