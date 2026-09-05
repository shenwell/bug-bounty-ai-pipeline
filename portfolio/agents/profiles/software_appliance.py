"""Software/appliance profile — lab provisioning + service recon."""

from __future__ import annotations

from portfolio.agents.recon import ReconAgent
from portfolio.common.config import AppConfig
from portfolio.common.logging import get_logger
from portfolio.common.models import Asset, Contract

logger = get_logger(__name__)


class SoftwareApplianceProfile:
    name = "software_appliance"

    def __init__(self, config: AppConfig):
        self._recon = ReconAgent(config)

    async def recon(self, contract: Contract, asset: Asset) -> dict:
        if not asset.metadata.get("lab_provisioned"):
            asset.status = "blocked_awaiting_env"
            logger.warning("software_appliance_awaiting_lab", asset=asset.identifier)
            return {"status": "blocked_awaiting_env", "asset_id": asset.id}

        surface = await self._recon.run(contract, asset)
        surface["lab"] = {"provisioned": True, "artifact": asset.identifier}
        return surface
