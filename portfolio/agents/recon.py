"""Deterministic recon agent — subfinder/httpx/katana/nuclei toolchain."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from portfolio.common.config import AppConfig
from portfolio.common.logging import get_logger
from portfolio.common.models import Asset, Contract
from portfolio.discovery.dossier import dossier_path
from portfolio.discovery.test_accounts import _bb_headers
from portfolio.guardrails.constraints import ProgramConstraintsEngine
from portfolio.guardrails.kill_switch import KillSwitch
from portfolio.guardrails.limits import RateLimiter, ScanBudget
from portfolio.guardrails.scope import ScopeValidator

logger = get_logger(__name__)


class ReconAgent:
    def __init__(self, config: AppConfig):
        self._config = config
        self._scope = ScopeValidator(config)
        self._constraints = ProgramConstraintsEngine(self._scope)
        self._rate = RateLimiter(config.limits)
        self._kill = KillSwitch()

    async def _httpx_cli_usable(self) -> bool:
        if not shutil.which("httpx"):
            return False
        proc = await asyncio.create_subprocess_exec(
            "httpx",
            "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = f"{stdout.decode()}{stderr.decode()}".lower()
        if "pip install" in output or "could not run" in output:
            return False
        return "projectdiscovery" in output or proc.returncode == 0

    async def run(self, contract: Contract, asset: Asset) -> dict:
        self._kill.check()
        budget = ScanBudget(self._config.limits.scan_time_budget_min)
        surface: dict = {
            "asset_id": asset.id,
            "identifier": asset.identifier,
            "live_hosts": [],
            "endpoints": [],
            "technologies": [],
            "nuclei_leads": [],
        }

        target = asset.identifier
        if not target.startswith("http"):
            target = f"https://{target}"

        headers = _bb_headers(contract)
        self._constraints.validate_network_request(target, contract, headers=headers)
        self._rate.acquire(asset.id)

        if await self._httpx_cli_usable():
            surface["live_hosts"] = await self._run_timed(
                self._run_httpx(target, headers),
                35,
                fallback=None,
            )
            if surface["live_hosts"] is None:
                surface["live_hosts"] = await self._httpx_fallback(target, headers)
        else:
            surface["live_hosts"] = await self._httpx_fallback(target, headers)

        budget.check()
        if shutil.which("katana") and surface["live_hosts"]:
            surface["endpoints"] = await self._run_timed(
                self._run_katana(surface["live_hosts"][0]),
                45,
                fallback=[surface["live_hosts"][0]],
            )
        else:
            surface["endpoints"] = [surface["live_hosts"][0]] if surface["live_hosts"] else []

        if shutil.which("nuclei") and surface["live_hosts"]:
            surface["nuclei_leads"] = await self._run_timed(
                self._run_nuclei(surface["live_hosts"][0]),
                60,
                fallback=[],
            )
            logger.info("nuclei_leads_only", count=len(surface["nuclei_leads"]))

        out = dossier_path(self._config, contract.slug, "recon", f"recon_{asset.id}.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(surface, indent=2), encoding="utf-8")
        logger.info("recon_complete", asset=asset.identifier, hosts=len(surface["live_hosts"]))
        return surface

    async def _run_timed(self, coro, timeout_sec: int, *, fallback):
        try:
            return await asyncio.wait_for(coro, timeout=timeout_sec)
        except (TimeoutError, asyncio.TimeoutError) as exc:
            logger.warning("recon_tool_timeout", timeout_sec=timeout_sec, error=str(exc))
            return fallback

    async def _communicate(self, proc, timeout_sec: int) -> bytes:
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
            return stdout
        except (TimeoutError, asyncio.TimeoutError):
            proc.kill()
            try:
                await proc.wait()
            except Exception:
                pass
            raise

    async def _run_httpx(self, target: str, headers: dict[str, str] | None = None) -> list[str]:
        cmd = ["httpx", "-u", target, "-silent", "-json"]
        for name, value in (headers or {}).items():
            cmd.extend(["-H", f"{name}: {value}"])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout = await self._communicate(proc, 30)
        hosts = []
        for line in stdout.decode().splitlines():
            try:
                data = json.loads(line)
                url = data.get("url") or data.get("input")
                if url:
                    hosts.append(url)
            except json.JSONDecodeError:
                if line.strip():
                    hosts.append(line.strip())
        return hosts or [target]

    async def _httpx_fallback(self, target: str, headers: dict[str, str] | None = None) -> list[str]:
        import httpx as hx

        try:
            async with hx.AsyncClient(follow_redirects=True, timeout=15) as client:
                r = await client.get(target, headers=headers or {})
                return [str(r.url)]
        except Exception as e:
            logger.warning("httpx_fallback_failed", target=target, error=str(e))
            return [target]

    async def _run_katana(self, url: str) -> list[str]:
        proc = await asyncio.create_subprocess_exec(
            "katana", "-u", url, "-silent", "-jc", "-d", "2",
            stdout=asyncio.subprocess.PIPE,
        )
        stdout = await self._communicate(proc, 45)
        return [line.strip() for line in stdout.decode().splitlines() if line.strip()][:200]

    async def _run_nuclei(self, url: str) -> list[dict]:
        proc = await asyncio.create_subprocess_exec(
            "nuclei", "-u", url, "-silent", "-jsonl",
            stdout=asyncio.subprocess.PIPE,
        )
        stdout = await self._communicate(proc, 60)
        leads = []
        for line in stdout.decode().splitlines():
            try:
                leads.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return leads
