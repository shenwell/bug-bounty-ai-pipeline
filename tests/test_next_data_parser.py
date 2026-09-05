"""Tests for NEXT_DATA program parser and scope/reward fixes."""

from pathlib import Path

from portfolio.discovery.next_data_parser import enrich_from_next_data, extract_program_page_props
from portfolio.discovery.parser import parse_program, parse_rewards, parse_scope_items
from portfolio.routing.classifier import classify_asset
from portfolio.common.models import AssetType

MYREVIEWS_HTML = Path("data/snapshots/MyReviews.html")


def test_scope_filters_section_numbers():
    text = "Scope 3.1 Observations 3.2 Auth *.example.com api.example.com"
    in_scope, _ = parse_scope_items(f"<html>{text}</html>")
    assert "3.1" not in in_scope
    assert "3.2" not in in_scope
    assert any("example.com" in item for item in in_scope)


def test_parse_rewards_up_to_50k():
    rewards = parse_rewards("Reward for vulnerabilities up to в‚Ѕ50K Excl. tax")
    assert rewards
    assert rewards[0].max_amount == 50_000


def test_classify_domain_not_ot_ics():
    ctx = "statistics and specifics about policies and practices"
    assert classify_asset("myreviews.ru", ctx) == AssetType.WEB_API


def test_myreviews_next_data_from_snapshot():
    if not MYREVIEWS_HTML.exists():
        return
    html = MYREVIEWS_HTML.read_text(encoding="utf-8")
    page_props = extract_program_page_props(html)
    assert page_props is not None
    tabs, rewards, scope, name = enrich_from_next_data(page_props)
    assert "Description" in tabs
    assert len(tabs["Description"]) > 1000
    assert scope
    assert "myreviews.ru" in scope
    assert "3.1" not in scope
    assert rewards
    assert max(r.max_amount for r in rewards) == 50_000
    assert name


def test_parse_program_myreviews_snapshot():
    if not MYREVIEWS_HTML.exists():
        return
    html = MYREVIEWS_HTML.read_text(encoding="utf-8")
    contract = parse_program("MyReviews", "Craftum", html, "https://example.com")
    assert contract.tab_sections.get("Description")
    assert contract.reward_ranges
    assert contract.reward_ranges[0].max_amount == 50_000
    assert contract.assets[0].asset_type == AssetType.WEB_API
    assert "3.1" not in contract.scope

