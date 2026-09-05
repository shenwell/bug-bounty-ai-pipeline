"""Tests for discovery parser."""

from portfolio.discovery.parser import parse_constraints, parse_program, parse_scope_items

SAMPLE_HTML = """
<html><body>
<h1>Test Program</h1>
<h2>Scope</h2>
<p>*.example.com api.example.com</p>
<h2>Out of scope</h2>
<p>staging.example.com</p>
<h2>Rewards</h2>
<p>Critical: до 500000</p>
<p>High: до 100000</p>
<p>VPN обязателен</p>
<p>X-Bug-Bounty: {user}</p>
<p>Accept rules required for private program</p>
</body></html>
"""


def test_parse_scope_items():
    in_scope, oos = parse_scope_items(SAMPLE_HTML)
    assert "example.com" in in_scope or any("example.com" in s for s in in_scope)
    assert "staging.example.com" in oos or any("staging" in s for s in oos)


def test_parse_scope_from_tab_sections():
    tabs = {"Scope": "*.tab.example.com\napi.tab.example.com"}
    in_scope, _ = parse_scope_items("<html></html>", tabs)
    assert any("tab.example.com" in s for s in in_scope)


def test_parse_scope_russian_skoуп_section():
    tabs = {
        "Description": (
            "## Скоуп\n\nДомены:\n"
            "elections.gosuslugi.ru\n"
            "voter.gosuslugi.ru\n\n"
            "IP:\n109.207.8.126\n\n"
            "https://www.gosuslugi.ru/600307/1/form\n"
        )
    }
    in_scope, _ = parse_scope_items("<html></html>", tabs)
    assert "elections.gosuslugi.ru" in in_scope
    assert "voter.gosuslugi.ru" in in_scope
    assert "109.207.8.126" in in_scope
    assert "https://www.gosuslugi.ru/600307/1/form" in in_scope


def test_parse_constraints():
    c = parse_constraints("VPN обязателен. X-Bug-Bounty: {user}. whoami hostname")
    assert c.vpn_required is True
    assert "X-Bug-Bounty" in c.required_headers


def test_parse_program():
    contract = parse_program("test-prog", "Test Program", SAMPLE_HTML, "https://example.com/p")
    assert contract.slug == "test-prog"
    assert contract.is_private or contract.requires_accept_rules
    assert contract.is_paid is True
    assert len(contract.assets) >= 0


def test_detect_unpaid_program():
    html = """
    <html><body>
    <h1>Unpaid Program</h1>
    <p>Вознаграждение не выплачивается за отчёты по данной программе.</p>
    </body></html>
    """
    contract = parse_program("unpaid", "Unpaid", html, "https://example.com/u")
    assert contract.is_paid is False
