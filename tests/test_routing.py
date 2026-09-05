"""Tests for routing and classifier."""

from portfolio.common.models import Asset, AssetType, Contract
from portfolio.routing.classifier import classify_asset
from portfolio.routing.profiles import route_asset
from portfolio.routing.router import route_contract


def test_classify_web():
    assert classify_asset("api.example.com") == AssetType.WEB_API


def test_classify_mobile():
    assert classify_asset("app.apk", "android application") == AssetType.MOBILE_ANDROID
    assert classify_asset("app.ipa", "ios app store") == AssetType.MOBILE_IOS


def test_classify_ot():
    assert classify_asset("sensor.local", "OT ICS modbus PLC") == AssetType.OT_ICS


def test_route_asset():
    asset = Asset(identifier="api.test.com", engagement_profile="web_api")
    profile, worker = route_asset(asset)
    assert profile == "web_api"
    assert worker == "worker-web"


def test_route_contract():
    contract = Contract(
        program_id="p1",
        slug="route-test",
        name="Route",
        assets=[
            Asset(identifier="api.test.com", engagement_profile="web_api"),
            Asset(identifier="plc.local", engagement_profile="ot_ics"),
        ],
    )
    result = route_contract(contract)
    assert result.assets[0].worker_target == "worker-web"
    assert result.assets[1].status == "human_queue"

