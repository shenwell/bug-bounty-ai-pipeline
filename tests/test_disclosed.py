"""Tests for disclosed reports parser and coverage."""

from portfolio.discovery.coverage import attach_disclosed_to_contracts, hunt_overlap
from portfolio.discovery.disclosed_parser import (
    extract_hosts,
    extract_vuln_classes,
    parse_disclosed_detail,
    parse_disclosed_from_next_data,
    parse_disclosed_list_item,
)
from portfolio.common.models import Contract, DisclosedReport

LIST_TEXT = """3338 ssrf blind
РќРѕРІР°СЏ РїРµСЂРµРІРѕР·РѕС‡РЅР°СЏ РєРѕРјРїР°РЅРёСЏ
October 28, 2023
High
в‚Ѕ10K
AlexShev"""

DETAIL_HTML = """
<html><body>
<h1>ssrf blind</h1>
<a href="/en-US/programs/npk">РќРѕРІР°СЏ РїРµСЂРµРІРѕР·РѕС‡РЅР°СЏ РєРѕРјРїР°РЅРёСЏ</a>
<p>Report No.: 3338</p>
<p>Created: October 28, 2023, 18:41</p>
<p>Disclosed: August 2, 2024, 12:04</p>
<p>Status: Fix confirmed</p>
<p>Severity: High</p>
<p>CWE: CWE-918 Server-Side Request Forgery (SSRF)</p>
<p>Author: AlexShev</p>
</body></html>
"""

NEXT_DATA_HTML = """
<html><body>
<script id="__NEXT_DATA__" type="application/json">{
  "props": {
    "pageProps": {
      "disclosedReport": {
        "originReportId": 1345,
        "originCreatedAt": "2023-03-29T12:00:00Z",
        "name": "SSRF in markdown image loader",
        "description": "Blind SSRF via api.standoff365.com prefix bypass in seller.ozon.ru editor.",
        "programId": 1,
        "cwe": "CWE-918",
        "severity": "high",
        "id": 1,
        "status": "fix_accepted",
        "createdAt": "2024-01-01T00:00:00Z",
        "cweLocale": {"en": "Server-Side Request Forgery (SSRF)"},
        "vendorDescription": "",
        "hackerDescription": "",
        "amount": 5000,
        "currency": "rub",
        "program": {"slug": "standoff", "name": "Standoff365"},
        "author": {"username": "dingobongo"}
      },
      "historyItems": [
        {
          "actionType": "comment",
          "authorName": "reviewer",
          "body": {"text": "Confirmed with curl PoC against internal metadata."}
        }
      ]
    }
  }
}</script>
</body></html>
"""


def test_parse_disclosed_list_item():
    r = parse_disclosed_list_item("/en-US/disclosed-reports/3", LIST_TEXT, "https://x/3")
    assert r.report_no == "3338"
    assert r.disclosed_id == "3"
    assert "ssrf" in r.title.lower()
    assert r.severity == "High"
    assert r.author == "AlexShev"


def test_parse_disclosed_detail_html_fallback():
    base = parse_disclosed_list_item("/en-US/disclosed-reports/3", LIST_TEXT, "https://x/3")
    r = parse_disclosed_detail(
        DETAIL_HTML,
        "https://x/3",
        "https://bugbounty.standoff365.com/en-US/programs/npk",
        base,
    )
    assert r.program_slug == "npk"
    assert r.cwe.startswith("CWE-918")
    assert r.status == "Fix confirmed"
    assert "ssrf" in r.vuln_classes


def test_parse_disclosed_detail_from_next_data():
    base = parse_disclosed_list_item("/en-US/disclosed-reports/1", "1345 SSRF", "https://x/1")
    r = parse_disclosed_detail(
        NEXT_DATA_HTML,
        "https://x/1",
        None,
        base,
    )
    assert r.report_no == "1345"
    assert r.disclosed_id == "1"
    assert r.program_slug == "standoff"
    assert r.status == "Fix confirmed"
    assert "seller.ozon.ru" in r.hosts
    assert "ssrf" in r.vuln_classes
    assert "prefix bypass" in r.poc
    assert r.history_comments
    assert r.bounty_amount == 5000


def test_parse_disclosed_from_next_data_direct():
    page_props = {
        "disclosedReport": {
            "originReportId": 9,
            "name": "XSS",
            "description": "",
            "vendorDescription": "Stored XSS on profile page at profile.example.com",
            "hackerDescription": "",
            "cwe": "CWE-79",
            "severity": "medium",
            "id": 4,
            "status": "fix_accepted",
            "program": {"slug": "demo", "name": "Demo"},
            "author": {"username": "hunter"},
        },
        "historyItems": [],
    }
    r = parse_disclosed_from_next_data(page_props, "https://x/4")
    assert "profile.example.com" in r.hosts
    assert r.poc.startswith("Stored XSS")
    assert "xss" in r.vuln_classes


def test_extract_hosts_and_classes():
    assert "seller.ozon.ru" in extract_hosts("Blind SSRF [seller.ozon.ru]")
    assert "ssrf" in extract_vuln_classes("blind SSRF on api.example.com")


def test_attach_disclosed_to_contracts():
    contract = Contract(program_id="npk", slug="npk", name="NPK")
    report = DisclosedReport(
        report_no="3338",
        title="ssrf blind",
        program_slug="npk",
        vuln_classes=["ssrf"],
        hosts=["api.npktrans.ru"],
        poc="SSRF via webhook callback to api.npktrans.ru/internal",
    )
    out = attach_disclosed_to_contracts([contract], [report])
    assert out[0].disclosed_count == 1
    assert out[0].known_findings
    assert "api.npktrans.ru" in out[0].known_findings[0]


def test_hunt_overlap():
    report = DisclosedReport(
        report_no="1",
        title="SSRF",
        program_slug="npk",
        vuln_classes=["ssrf"],
        hosts=["api.npktrans.ru"],
    )
    warnings = hunt_overlap("npk", ["api.npktrans.ru"], ["ssrf"], [report])
    assert warnings

