"""Tests for bug bounty programs monitor."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from portfolio.discovery.bizone_companies_list import normalize_company
from portfolio.discovery.programs_list import (
    fetch_program_html,
    normalize_program,
    parse_programs_page,
)
from portfolio.monitor.platforms import get_monitor_platform
from portfolio.monitor.programs import diff_new_programs, load_state, merge_state, run_programs_monitor

SAMPLE_NEXT_DATA = """
<html><body>
<script id="__NEXT_DATA__" type="application/json">{
  "props": {
    "pageProps": {
      "programs": [
        {
          "id": 1,
          "slug": "alpha",
          "name": "Alpha Program",
          "publishedAt": "2026-01-01T00:00:00.000Z",
          "visibility": "public"
        },
        {
          "id": 2,
          "slug": "beta",
          "name": "Beta Program",
          "publishedAt": "2026-02-01T00:00:00.000Z",
          "visibility": "public"
        }
      ],
      "total": 2
    }
  }
}</script>
</body></html>
"""

SAMPLE_BIZONE_PAYLOAD = {
    "count": 2,
    "next": None,
    "previous": None,
    "results": [
        {
            "id": "alpha",
            "slug": "alpha",
            "name": "Alpha Company",
            "public": True,
            "isActive": True,
            "registrationDate": "2026-01-01T00:00:00.000Z",
        },
        {
            "id": "beta",
            "slug": "beta",
            "name": "Beta Company",
            "public": False,
            "isActive": True,
            "registrationDate": "2026-02-01T00:00:00.000Z",
        },
    ],
}


def parse_bizone_companies_payload(payload: dict) -> list[dict]:
    from portfolio.discovery.bizone_companies_list import _parse_results, normalize_company

    return [normalize_company(item) for item in _parse_results(payload)]


def test_parse_programs_page():
    programs = parse_programs_page(SAMPLE_NEXT_DATA)
    assert len(programs) == 2
    assert programs[0]["slug"] == "alpha"


def test_normalize_program():
    program = normalize_program(
        {"slug": "alpha", "name": "Alpha", "publishedAt": "2026-01-01T00:00:00.000Z"},
        base_url="https://bugbounty.standoff365.com",
    )
    assert program["slug"] == "alpha"
    assert program["url"].endswith("/en-US/programs/alpha/")


def test_parse_bizone_companies_payload():
    companies = parse_bizone_companies_payload(SAMPLE_BIZONE_PAYLOAD)
    assert len(companies) == 2
    assert companies[0]["slug"] == "alpha"


def test_normalize_bizone_company():
    company = normalize_company(
        {
            "id": "alpha",
            "slug": "alpha",
            "name": "Alpha",
            "registrationDate": "2026-01-01T00:00:00.000Z",
            "public": True,
        },
        base_url="https://bugbounty.bi.zone",
    )
    assert company["slug"] == "alpha"
    assert company["url"] == "https://bugbounty.bi.zone/companies/alpha"
    assert company["published_at"] == "2026-01-01T00:00:00.000Z"


def test_get_monitor_platform_bizone():
    platform = get_monitor_platform("bizone")
    assert platform.state_file.endswith("known-programs-bizone.json")


def test_diff_new_programs():
    state = {"programs": {"alpha": {"slug": "alpha"}}}
    current = [
        {"slug": "alpha", "name": "Alpha", "url": "https://example.com/alpha"},
        {"slug": "beta", "name": "Beta", "url": "https://example.com/beta"},
    ]
    new = diff_new_programs(current, state)
    assert [p["slug"] for p in new] == ["beta"]


def test_merge_state_adds_first_seen():
    state = {"programs": {}}
    programs = [{"slug": "gamma", "name": "Gamma", "url": "https://example.com/gamma", "published_at": None}]
    merge_state(state, programs, seen_at="2026-07-30T08:00:00Z")
    assert state["programs"]["gamma"]["first_seen_at"] == "2026-07-30T08:00:00Z"


def test_run_programs_monitor_init(tmp_path: Path, config, monkeypatch: pytest.MonkeyPatch):
    state_file = tmp_path / "known-programs.json"
    monkeypatch.setattr(config.monitor, "state_file", str(state_file))
    fake_programs = [
        {"slug": "alpha", "name": "Alpha", "url": "https://example.com/alpha", "published_at": None},
    ]

    with patch("portfolio.monitor.programs.get_monitor_platform") as get_platform:
        platform = MagicMock()
        platform.id = "standoff365"
        platform.state_file = str(state_file)
        platform.list_programs.return_value = fake_programs
        get_platform.return_value = platform
        with patch("portfolio.monitor.programs.resolve_state_file", return_value=str(state_file)):
            result = run_programs_monitor(config, platform="standoff365", init=True)

    assert result["action"] == "initialized"
    assert result["platform"] == "standoff365"
    assert state_file.exists()
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert "alpha" in saved["programs"]


def test_run_programs_monitor_notifies_on_new(tmp_path: Path, config, monkeypatch: pytest.MonkeyPatch):
    state_file = tmp_path / "known-programs-bizone.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps({"programs": {"alpha": {"slug": "alpha", "name": "Alpha"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config.monitor, "state_file", str(state_file))

    fake_programs = [
        {"slug": "alpha", "name": "Alpha", "url": "https://example.com/alpha", "published_at": None},
        {"slug": "beta", "name": "Beta", "url": "https://example.com/beta", "published_at": "2026-02-01"},
    ]

    with (
        patch("portfolio.monitor.programs.get_monitor_platform") as get_platform,
        patch("portfolio.monitor.programs.resolve_state_file", return_value=str(state_file)),
        patch("portfolio.monitor.programs.EmailNotifier") as email_cls,
        patch("portfolio.monitor.programs.TelegramProgramNotifier") as tg_cls,
    ):
        platform = MagicMock()
        platform.id = "bizone"
        platform.email_subject_prefix = "[BI.ZONE]"
        platform.email_body_intro = "intro"
        platform.telegram_heading = "heading"
        platform.list_programs.return_value = fake_programs
        get_platform.return_value = platform

        email_cls.return_value.is_configured.return_value = True
        email_cls.return_value.send_new_programs.return_value = True
        tg_cls.return_value.is_configured.return_value = False
        result = run_programs_monitor(config, platform="bizone")

    assert result["action"] == "notified"
    assert result["platform"] == "bizone"
    assert result["new_slugs"] == ["beta"]
    email_cls.return_value.send_new_programs.assert_called_once()
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert "beta" in saved["programs"]


class _FakeResponse:
    def __init__(self, url: str, text: str, status_code: int = 200):
        self.url = url
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_fetch_program_html_by_slug():
    html = "<html><body>hh program</body></html>"
    fake = MagicMock()
    fake.get.return_value = _FakeResponse(
        "https://bugbounty.standoff365.com/en-US/programs/hh/",
        html,
    )
    url, body = fetch_program_html("hh", client=fake, timeout_sec=5)
    assert url.endswith("/programs/hh/")
    assert "hh program" in body
    fake.get.assert_called_once()
    assert "/en-US/programs/hh/" in fake.get.call_args.args[0]

