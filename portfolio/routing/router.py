"""Route all assets in a contract to engagement profiles."""

from __future__ import annotations

from portfolio.common.models import Contract
from portfolio.routing.profiles import route_asset


def route_contract(contract: Contract) -> Contract:
    for asset in contract.assets:
        profile, worker = route_asset(asset)
        asset.engagement_profile = profile
        asset.worker_target = worker
    return contract
