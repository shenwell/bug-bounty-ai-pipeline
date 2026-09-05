"""OT/ICS profile — human-assisted routing."""

from __future__ import annotations

from portfolio.common.config import AppConfig
from portfolio.common.logging import get_logger
from portfolio.common.models import Asset, Contract

logger = get_logger(__name__)


class OtIcsProfile:
    name = "ot_ics"
    human_only = True

    def __init__(self, config: AppConfig):
        self._config = config

    async def recon(self, contract: Contract, asset: Asset) -> dict:
        asset.status = "human_queue"
        logger.info("ot_ics_human_queue", asset=asset.identifier)
        return {
            "asset_id": asset.id,
            "status": "human_queue",
            "protocols": ["modbus", "s7", "iec104", "opcua"],
            "message": "OT/ICS targets require human-assisted testing",
        }
