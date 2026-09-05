"""Tests for test account detection during dossier build."""

from portfolio.common.models import Contract, ExternalReference
from portfolio.discovery.test_accounts import (
    build_auth_accounts_markdown,
    scan_contract_for_test_accounts,
    write_auth_accounts,
)


def test_scan_finds_on_request_mention():
    contract = Contract(
        program_id="demo",
        slug="konsol",
        name="Konsol",
        scope=["app.konsol.pro"],
        tab_sections={
            "Description": (
                "РџСЂРё РЅРµРѕР±С…РѕРґРёРјРѕСЃС‚Рё РјС‹ РјРѕР¶РµРј РїСЂРµРґРѕСЃС‚Р°РІРёС‚СЊ С‚РµСЃС‚РѕРІСѓСЋ СѓС‡С‘С‚РЅСѓСЋ Р·Р°РїРёСЃСЊ "
                "РґР»СЏ РїСЂРѕРІРµСЂРѕРє РїРѕ РїСЂРµРґРІР°СЂРёС‚РµР»СЊРЅРѕРјСѓ СЃРѕРіР»Р°СЃРѕРІР°РЅРёСЋ."
            ),
        },
    )
    check = scan_contract_for_test_accounts(contract)
    assert check.summary["status"] == "on_request_only"
    assert check.summary["on_request_available"] is True
    assert any(m["kind"] == "on_request" for m in check.mentions)


def test_scan_finds_demo_credentials_in_tab():
    contract = Contract(
        program_id="demo",
        slug="konsol",
        name="Konsol",
        scope=["app.konsol.pro"],
        tab_sections={
            "Description": (
                "Р”РµРјРѕ-РєР°Р±РёРЅРµС‚: https://app.konsol.pro/login\n"
                "| РџРѕР»Рµ | Р—РЅР°С‡РµРЅРёРµ |\n"
                "| РўРµР»РµС„РѕРЅ | +7-000-999-78-56 |\n"
                "| РџР°СЂРѕР»СЊ | DemoAccount23 |\n"
            ),
        },
    )
    check = scan_contract_for_test_accounts(contract)
    assert check.summary["self_service_demo"] is True
    assert check.accounts
    assert "+70009997856" in check.accounts[0]["phones"]
    assert check.accounts[0]["has_password"] is True
    assert any("app.konsol.pro/login" in item["url"] for item in check.login_urls)


def test_scan_reads_external_ref_preview():
    contract = Contract(
        program_id="demo",
        slug="demo",
        name="Demo",
        scope=["app.example.com"],
        external_refs=[
            ExternalReference(
                url="https://support.example.com/access-to-demo-account",
                preview="Demo login phone +7-000-111-22-33 password: SecretDemo1",
            )
        ],
    )
    check = scan_contract_for_test_accounts(contract)
    assert check.accounts
    assert "+70001112233" in check.accounts[0]["phones"]


def test_write_auth_accounts_creates_files(config, tmp_path, monkeypatch):
    monkeypatch.setattr(config.data, "dossiers_dir", str(tmp_path / "dossiers"))
    contract = Contract(program_id="demo", slug="demo", name="Demo", scope=["api.example.com"])
    check = scan_contract_for_test_accounts(contract)
    json_path, md_path = write_auth_accounts(config, contract, check)
    assert json_path.endswith("auth_accounts.json")
    assert md_path.endswith("auth_accounts.md")
    content = build_auth_accounts_markdown(check, contract)
    assert "РўРµСЃС‚РѕРІС‹Рµ Р°РєРєР°СѓРЅС‚С‹" in content

