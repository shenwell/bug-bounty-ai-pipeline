"""Configuration loader with env secret substitution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key_env: str = "LLM_API_KEY"
    max_tokens: int = 8192
    context_window: int = 110000

    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)


class StandoffConfig(BaseModel):
    base_url: str = "https://bugbounty.standoff365.com"
    auth_mode: str = "cookie"
    session_cookie_env: str = "STF_SESSION"
    username_env: str = "STF_USERNAME"
    password_env: str = "STF_PASSWORD"
    default_program_slug: str = "standoff-365"

    def session_cookie(self) -> str | None:
        return os.environ.get(self.session_cookie_env)

    def username(self) -> str | None:
        return os.environ.get(self.username_env)

    def password(self) -> str | None:
        return os.environ.get(self.password_env)


class ScopeConfig(BaseModel):
    hard_out_of_scope: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)


class ScoringWeights(BaseModel):
    reward: float = 0.35
    scope_size: float = 0.2
    competency_match: float = 0.3
    restrictions: float = 0.15


class ScoringConfig(BaseModel):
    min_score_to_hunt: float = 0.6
    min_reportable_severity: str = "medium"
    weights: ScoringWeights = Field(default_factory=ScoringWeights)


class ThresholdsConfig(BaseModel):
    hunt_iteration_cap: int = 40
    validate_confidence_min: float = 0.85
    validate_reproductions: int = 3


class LimitsConfig(BaseModel):
    rate_limit_rps: float = 2.0
    scan_time_budget_min: int = 120
    max_parallel_hunters: int = 5


class ReviewConfig(BaseModel):
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    dashboard_url_env: str = "DASHBOARD_URL"
    telegram_enabled: bool = True
    telegram_bot_token_env: str = "TG_BOT_TOKEN"
    telegram_chat_id_env: str = "TG_CHAT_ID"

    def dashboard_url(self) -> str:
        return os.environ.get(self.dashboard_url_env, f"http://localhost:{self.api_port}")

    def telegram_token(self) -> str | None:
        return os.environ.get(self.telegram_bot_token_env)

    def telegram_chat_id(self) -> str | None:
        return os.environ.get(self.telegram_chat_id_env)


class DatabaseConfig(BaseModel):
    url_env: str = "DATABASE_URL"
    default_url: str = "sqlite:///data/pipeline.db"

    def url(self) -> str:
        return os.environ.get(self.url_env, self.default_url)


class DataConfig(BaseModel):
    artifacts_dir: str = "data/artifacts"
    contracts_file: str = "data/contracts.yaml"
    disclosed_reports_file: str = "data/disclosed-reports.yaml"
    snapshots_dir: str = "data/snapshots"
    dossiers_dir: str = "data/dossiers"
    engagements_dir: str = "engagements"


class DiscoverConfig(BaseModel):
    max_program_pages: int = 50
    max_disclosed_pages: int = 100
    fetch_disclosed_details: bool = True
    disclosed_detail_delay_ms: int = 300


class ReconConfig(BaseModel):
    fetch_contract_links: bool = True
    max_contract_links: int = 25
    max_link_bytes: int = 2_000_000
    link_fetch_timeout_sec: int = 30


class PhantomConfig(BaseModel):
    enabled: bool = True
    vendor_path: str = "vendor/phantom"


class MonitorConfig(BaseModel):
    state_file: str = "data/monitor/known-programs.json"
    bizone_base_url: str = "https://bugbounty.bi.zone"
    max_pages: int = 50
    page_delay_sec: float = 0.25
    request_timeout_sec: float = 30.0
    smtp_host_env: str = "SMTP_HOST"
    smtp_port_env: str = "SMTP_PORT"
    smtp_port_default: int = 587
    smtp_user_env: str = "SMTP_USER"
    smtp_password_env: str = "SMTP_PASSWORD"
    smtp_from_env: str = "SMTP_FROM"
    notify_email_env: str = "MONITOR_NOTIFY_EMAIL"

    def smtp_host(self) -> str | None:
        return os.environ.get(self.smtp_host_env)

    def smtp_port(self) -> int:
        raw = os.environ.get(self.smtp_port_env)
        if raw:
            return int(raw)
        return self.smtp_port_default

    def smtp_user(self) -> str | None:
        return os.environ.get(self.smtp_user_env)

    def smtp_password(self) -> str | None:
        return os.environ.get(self.smtp_password_env)

    def from_email(self) -> str | None:
        return os.environ.get(self.smtp_from_env)

    def notify_email(self) -> str | None:
        return os.environ.get(self.notify_email_env)


class AppConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    standoff: StandoffConfig = Field(default_factory=StandoffConfig)
    scope: ScopeConfig = Field(default_factory=ScopeConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    discover: DiscoverConfig = Field(default_factory=DiscoverConfig)
    recon: ReconConfig = Field(default_factory=ReconConfig)
    phantom: PhantomConfig = Field(default_factory=PhantomConfig)
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    config_path: str = "config/portfolio.yaml"

    def redacted_dict(self) -> dict[str, Any]:
        d = self.model_dump()
        d["_secrets"] = {
            "llm_key_set": bool(self.llm.api_key()),
            "stf_session_set": bool(self.standoff.session_cookie()),
            "stf_credentials_set": bool(self.standoff.username() and self.standoff.password()),
            "telegram_set": bool(self.review.telegram_token() and self.review.telegram_chat_id()),
            "monitor_email_set": bool(
                self.monitor.smtp_host()
                and self.monitor.smtp_user()
                and self.monitor.smtp_password()
                and self.monitor.notify_email()
            ),
        }
        return d

    def ensure_data_dirs(self) -> None:
        for path in (
            self.data.artifacts_dir,
            self.data.snapshots_dir,
            self.data.dossiers_dir,
            Path(self.database.url().replace("sqlite:///", "")).parent,
        ):
            Path(path).mkdir(parents=True, exist_ok=True)


def _load_env_file() -> None:
    """Load config/.env into os.environ (no override of existing vars)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parents[2]
    for env_path in (root / "config" / ".env", root / ".env"):
        if env_path.is_file():
            load_dotenv(env_path, override=False)
            return


def load_config(path: str | None = None) -> AppConfig:
    _load_env_file()
    root = Path(__file__).resolve().parents[2]
    if path is None:
        path = os.environ.get("PORTFOLIO_CONFIG", "config/portfolio.yaml")
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = root / config_path
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with config_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    cfg = AppConfig(**raw, config_path=str(config_path))
    cfg.ensure_data_dirs()
    return cfg
