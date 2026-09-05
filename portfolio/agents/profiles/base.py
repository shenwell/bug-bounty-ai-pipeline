"""Engagement profile implementations — recon-only for portfolio build."""

from __future__ import annotations

from portfolio.agents.recon import ReconAgent
from portfolio.common.config import AppConfig
from portfolio.common.models import Asset, Contract


class WebApiProfile:
    name = "web_api"

    def __init__(self, config: AppConfig):
        self._recon = ReconAgent(config)

    async def recon(self, contract: Contract, asset: Asset) -> dict:
        return await self._recon.run(contract, asset)


def get_profile(name: str, config: AppConfig):
    from portfolio.agents.profiles.binary_malware import BinaryMalwareProfile
    from portfolio.agents.profiles.cloud_container import CloudContainerProfile
    from portfolio.agents.profiles.mobile import MobileProfile
    from portfolio.agents.profiles.ot_ics import OtIcsProfile
    from portfolio.agents.profiles.software_appliance import SoftwareApplianceProfile

    profiles = {
        "web_api": WebApiProfile,
        "mobile": MobileProfile,
        "software_appliance": SoftwareApplianceProfile,
        "cloud_container": CloudContainerProfile,
        "ot_ics": OtIcsProfile,
        "binary_malware": BinaryMalwareProfile,
    }
    cls = profiles.get(name, WebApiProfile)
    return cls(config)
