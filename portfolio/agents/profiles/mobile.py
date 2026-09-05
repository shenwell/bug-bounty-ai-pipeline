"""Mobile engagement profile — static analysis for dossier recon."""

from __future__ import annotations

import asyncio
import shutil

from portfolio.common.config import AppConfig
from portfolio.common.logging import get_logger
from portfolio.common.models import Asset, Contract

logger = get_logger(__name__)


class MobileProfile:
    name = "mobile"

    def __init__(self, config: AppConfig):
        self._config = config

    async def recon(self, contract: Contract, asset: Asset) -> dict:
        surface = {"asset_id": asset.id, "identifier": asset.identifier, "mobile_analysis": {}}
        identifier = asset.identifier.lower()

        if identifier.endswith(".apk") and shutil.which("jadx"):
            proc = await asyncio.create_subprocess_exec(
                "jadx",
                "-d",
                f"/tmp/jadx_{asset.id}",
                asset.identifier,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            surface["mobile_analysis"]["jadx"] = "completed"

        if identifier.endswith(".apk") and shutil.which("apktool"):
            proc = await asyncio.create_subprocess_exec(
                "apktool",
                "d",
                asset.identifier,
                "-o",
                f"/tmp/apktool_{asset.id}",
                stdout=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            surface["mobile_analysis"]["apktool"] = "completed"

        api_assets = [a for a in contract.assets if a.asset_type.value.startswith("web")]
        surface["backend_apis"] = [a.identifier for a in api_assets]
        logger.info("mobile_recon_complete", asset=asset.identifier)
        return surface
