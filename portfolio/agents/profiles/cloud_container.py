"""Cloud container escape profile — recon surface for dossier."""

from __future__ import annotations

import asyncio

from portfolio.common.config import AppConfig
from portfolio.common.models import Asset, Contract


class CloudContainerProfile:
    name = "cloud_container"

    def __init__(self, config: AppConfig):
        self._config = config

    async def recon(self, contract: Contract, asset: Asset) -> dict:
        surface = {
            "asset_id": asset.id,
            "identifier": asset.identifier,
            "container_checks": [],
        }
        if await self._docker_available():
            surface["container_checks"].append("docker_available")
        surface["escape_vectors"] = ["privileged_container", "docker_socket", "kubelet_api"]
        return surface

    async def _docker_available(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "info",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode == 0
        except FileNotFoundError:
            return False
