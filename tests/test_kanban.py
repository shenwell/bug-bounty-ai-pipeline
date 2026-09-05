"""Tests for portfolio Kanban board."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from portfolio.kanban import (
    KANBAN_COLUMNS,
    add_to_inbox,
    load_board_state,
    move_card,
)
from portfolio.review.api import create_app


def _seed_dossier(root: Path, slug: str, name: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "contract.json").write_text(
        json.dumps({"contract": {"slug": slug, "name": name, "score": 0.8}}),
        encoding="utf-8",
    )


def test_load_board_state_empty(config, tmp_path, monkeypatch):
    monkeypatch.setattr(config.data, "dossiers_dir", str(tmp_path / "dossiers"))
    state = load_board_state(config)
    assert state["total"] == 0
    assert len(state["columns"]) == len(KANBAN_COLUMNS)


def test_load_and_move_card(config, tmp_path, monkeypatch):
    dossiers = tmp_path / "dossiers"
    monkeypatch.setattr(config.data, "dossiers_dir", str(dossiers))
    _seed_dossier(dossiers / "alpha", "alpha", "Alpha")
    _seed_dossier(dossiers / "beta", "beta", "Beta")

    state = load_board_state(config)
    assert state["total"] == 2

    moved = move_card(config, slug="alpha", column_id="hunt", position=0)
    hunt_slugs = [c["slug"] for c in moved["cards"]["hunt"]]
    assert "alpha" in hunt_slugs

    status = json.loads((dossiers / "alpha" / "status.json").read_text(encoding="utf-8"))
    assert status["kanban_column"] == "hunt"
    assert status["overall"] == "active"


def test_move_unknown_column(config, tmp_path, monkeypatch):
    dossiers = tmp_path / "dossiers"
    monkeypatch.setattr(config.data, "dossiers_dir", str(dossiers))
    _seed_dossier(dossiers / "x", "x", "X")
    with pytest.raises(ValueError):
        move_card(config, slug="x", column_id="nope")


def test_board_api_routes(config, tmp_path, monkeypatch):
    dossiers = tmp_path / "dossiers"
    monkeypatch.setattr(config.data, "dossiers_dir", str(dossiers))
    _seed_dossier(dossiers / "demo", "demo", "Demo")

    app = create_app(config)
    client = TestClient(app)

    r = client.get("/board")
    assert r.status_code == 200
    assert "Портфель контрактов" in r.text

    r = client.get("/api/board")
    assert r.status_code == 200
    assert r.json()["total"] == 1

    r = client.post(
        "/api/board/move",
        json={"slug": "demo", "column_id": "report", "position": 0, "card_id": "demo"},
    )
    assert r.status_code == 200
    assert "demo" in [c["slug"] for c in r.json()["cards"]["report"]]


def test_new_column_from_monitor(config, tmp_path, monkeypatch):
    root = tmp_path
    dossiers = root / "dossiers"
    monitor = root / "data" / "monitor"
    monitor.mkdir(parents=True)
    monkeypatch.setattr(config.data, "dossiers_dir", str(dossiers))
    monkeypatch.setattr(config, "config_path", str(root / "config" / "config.yaml"))

    (monitor / "known-programs.json").write_text(
        json.dumps(
            {
                "version": 1,
                "programs": {
                    "fresh-prog": {
                        "slug": "fresh-prog",
                        "name": "Fresh Program",
                        "url": "https://example.com/fresh",
                        "first_seen_at": "2026-07-31T12:00:00Z",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    add_to_inbox(config, "standoff365", "fresh-prog")

    state = load_board_state(config)
    new_slugs = [c["slug"] for c in state["cards"]["new"]]
    assert "fresh-prog" in new_slugs
    assert state["new_count"] >= 1

    moved = move_card(
        config,
        slug="fresh-prog",
        platform="standoff365",
        column_id="backlog",
        position=0,
    )
    assert "fresh-prog" not in [c["slug"] for c in moved["cards"]["new"]]
    assert "fresh-prog" in [c["slug"] for c in moved["cards"]["backlog"]]

