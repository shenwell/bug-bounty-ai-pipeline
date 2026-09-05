"""Engagement profile registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from portfolio.common.models import Asset, Contract, Finding


@dataclass
class ProfileInfo:
    name: str
    worker: str
    autonomous: bool
    human_only: bool = False
    tools: list[str] = field(default_factory=list)


class EngagementProfile(Protocol):
    name: str

    async def recon(self, contract: Contract, asset: Asset) -> dict: ...
    async def hunt(self, contract: Contract, asset: Asset, surface: dict) -> list[Finding]: ...
    async def validate(self, finding: Finding, contract: Contract) -> Finding: ...


PROFILE_REGISTRY: dict[str, ProfileInfo] = {
    "web_api": ProfileInfo(
        name="web_api",
        worker="worker-web",
        autonomous=True,
        tools=["subfinder", "httpx", "katana", "nuclei", "playwright"],
    ),
    "mobile": ProfileInfo(
        name="mobile",
        worker="worker-mobile",
        autonomous=True,
        tools=["jadx", "apktool", "frida", "mobsf"],
    ),
    "software_appliance": ProfileInfo(
        name="software_appliance",
        worker="lab",
        autonomous=True,
        tools=["ghidra", "semgrep", "nmap"],
    ),
    "cloud_container": ProfileInfo(
        name="cloud_container",
        worker="lab",
        autonomous=True,
        tools=["docker", "kubectl"],
    ),
    "ot_ics": ProfileInfo(
        name="ot_ics",
        worker="human",
        autonomous=False,
        human_only=True,
        tools=["modbus", "s7", "opcua"],
    ),
    "binary_malware": ProfileInfo(
        name="binary_malware",
        worker="lab",
        autonomous=True,
        tools=["yara", "olevba", "pefile"],
    ),
}


def route_asset(asset: Asset) -> tuple[str, str]:
    profile_name = asset.engagement_profile or "web_api"
    info = PROFILE_REGISTRY.get(profile_name)
    if not info:
        return "web_api", "worker-web"
    if info.human_only:
        asset.status = "human_queue"
        return profile_name, "human"
    if not asset.in_scope:
        asset.status = "blocked_awaiting_env"
        return profile_name, "blocked"
    asset.worker_target = info.worker
    asset.status = "routed"
    return profile_name, info.worker
