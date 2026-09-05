"""Bug bounty platform definitions for the programs monitor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from portfolio.common.config import AppConfig
from portfolio.discovery.bizone_companies_list import DEFAULT_BASE_URL as BIZONE_DEFAULT_BASE_URL
from portfolio.discovery.bizone_companies_list import list_all_companies
from portfolio.discovery.programs_list import list_all_programs

ListProgramsFn = Callable[[AppConfig], list[dict[str, Any]]]


@dataclass(frozen=True)
class MonitorPlatform:
    id: str
    label: str
    state_file: str
    email_subject_prefix: str
    email_body_intro: str
    telegram_heading: str
    list_programs: ListProgramsFn
    test_url: str


def _list_standoff_programs(config: AppConfig) -> list[dict[str, Any]]:
    return list_all_programs(
        base_url=config.standoff.base_url,
        max_pages=config.monitor.max_pages,
        delay_sec=config.monitor.page_delay_sec,
        timeout_sec=config.monitor.request_timeout_sec,
    )


def _list_bizone_companies(config: AppConfig) -> list[dict[str, Any]]:
    base_url = config.monitor.bizone_base_url or BIZONE_DEFAULT_BASE_URL
    return list_all_companies(
        base_url=base_url,
        max_pages=config.monitor.max_pages,
        delay_sec=config.monitor.page_delay_sec,
        timeout_sec=config.monitor.request_timeout_sec,
    )


MONITOR_PLATFORMS: dict[str, MonitorPlatform] = {
    "standoff365": MonitorPlatform(
        id="standoff365",
        label="Standoff365",
        state_file="data/monitor/known-programs.json",
        email_subject_prefix="[Standoff365]",
        email_body_intro="На Standoff365 появились новые программы багбаунти:",
        telegram_heading="🆕 Новые программы Standoff365:",
        list_programs=_list_standoff_programs,
        test_url="https://bugbounty.standoff365.com/en-US/programs/",
    ),
    "bizone": MonitorPlatform(
        id="bizone",
        label="BI.ZONE Bug Bounty",
        state_file="data/monitor/known-programs-bizone.json",
        email_subject_prefix="[BI.ZONE]",
        email_body_intro="На BI.ZONE Bug Bounty появились новые программы:",
        telegram_heading="🆕 Новые программы BI.ZONE:",
        list_programs=_list_bizone_companies,
        test_url="https://bugbounty.bi.zone/companies",
    ),
}

DEFAULT_MONITOR_PLATFORM = "standoff365"
LEGACY_STANDOFF_STATE_FILE = "data/monitor/known-programs.json"


def get_monitor_platform(platform_id: str) -> MonitorPlatform:
    try:
        return MONITOR_PLATFORMS[platform_id]
    except KeyError as exc:
        supported = ", ".join(sorted(MONITOR_PLATFORMS))
        raise ValueError(f"Unknown monitor platform {platform_id!r}; supported: {supported}") from exc


def resolve_state_file(platform: MonitorPlatform, config_state_file: str | None = None) -> str:
    """Prefer per-platform state file; keep legacy Standoff path when configured."""
    if platform.id == "standoff365" and config_state_file == LEGACY_STANDOFF_STATE_FILE:
        return LEGACY_STANDOFF_STATE_FILE
    return platform.state_file
