"""Pydantic domain models and SQLAlchemy ORM."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class ContractStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    SCORED = "scored"
    RECON = "recon"
    HUNTING = "hunting"
    VALIDATING = "validating"
    REPORTING = "reporting"
    IN_REVIEW = "in_review"
    SUBMITTED = "submitted"
    DISMISSED = "dismissed"


class FindingStatus(str, enum.Enum):
    NEW = "new"
    VALIDATING = "validating"
    VERIFIED = "verified"
    FALSE_POSITIVE = "false_positive"
    REPORTED = "reported"
    IN_REVIEW = "in_review"
    SUBMITTED = "submitted"
    DISMISSED = "dismissed"


class AssetType(str, enum.Enum):
    WEB_API = "web_api"
    MOBILE_ANDROID = "mobile_android"
    MOBILE_IOS = "mobile_ios"
    DESKTOP_SOFTWARE = "desktop_software"
    NETWORK_APPLIANCE = "network_appliance"
    OT_ICS = "ot_ics"
    CLOUD_CONTAINER = "cloud_container"
    BINARY_MALWARE = "binary_malware"
    UNKNOWN = "unknown"


class ProgramFormat(str, enum.Enum):
    CLASSIC = "classic"
    NTE = "nte"


# --- Pydantic schemas (API / YAML) ---


class ProgramConstraints(BaseModel):
    required_headers: dict[str, str] = Field(default_factory=dict)
    vpn_required: bool = False
    allowed_rce_commands: list[str] = Field(default_factory=list)
    allowed_file_reads: list[str] = Field(default_factory=list)
    internal_test_hosts: list[str] = Field(default_factory=list)
    stop_after_container_escape: bool = False
    no_bulk_enumeration: bool = False
    no_reverse_engineering_mobile: bool = False
    raw_rules: list[str] = Field(default_factory=list)


class Asset(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    identifier: str
    asset_type: AssetType = AssetType.UNKNOWN
    in_scope: bool = True
    engagement_profile: str | None = None
    worker_target: str | None = None
    status: str = "pending"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RewardRange(BaseModel):
    severity: str
    min_amount: float = 0
    max_amount: float = 0
    currency: str = "RUB"


class Contract(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    program_id: str
    slug: str
    name: str
    platform: str = "standoff365"
    client: str = ""
    scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)
    reward_ranges: list[RewardRange] = Field(default_factory=list)
    constraints: ProgramConstraints = Field(default_factory=ProgramConstraints)
    program_format: ProgramFormat = ProgramFormat.CLASSIC
    is_private: bool = False
    requires_accept_rules: bool = False
    accept_rules_pending: bool = False
    report_fields: list[str] = Field(default_factory=list)
    acceptance_criteria: str = ""
    is_paid: bool = True
    tab_sections: dict[str, str] = Field(default_factory=dict)
    score: float | None = None
    score_reason: str = ""
    target_vectors: list[str] = Field(default_factory=list)
    status: ContractStatus = ContractStatus.DISCOVERED
    source_url: str = ""
    disclosed_count: int = 0
    known_findings: list[str] = Field(default_factory=list)
    avoid_hosts: list[str] = Field(default_factory=list)
    avoid_vectors: list[str] = Field(default_factory=list)
    scope_gaps: list[str] = Field(default_factory=list)
    landscape_file: str = ""
    hunt_plan_file: str = ""
    dossier_dir: str = ""
    dossier_refreshed_at: str = ""
    external_refs: list["ExternalReference"] = Field(default_factory=list)


class ExternalReference(BaseModel):
    url: str
    source: str = ""
    ref_type: str = "generic"
    title: str = ""
    status_code: int = 0
    content_type: str = ""
    fetched_at: str = ""
    error: str = ""
    preview: str = ""
    file_path: str = ""
    in_scope: bool = False


class DisclosedReport(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    list_path: str = ""
    disclosed_id: str = ""
    report_no: str = ""
    title: str = ""
    program_name: str = ""
    program_slug: str = ""
    severity: str = ""
    cwe: str = ""
    status: str = ""
    bounty_amount: float = 0
    bounty_currency: str = "RUB"
    author: str = ""
    created_at: str = ""
    disclosed_at: str = ""
    description: str = ""
    hacker_description: str = ""
    vendor_description: str = ""
    poc: str = ""
    history_comments: list[str] = Field(default_factory=list)
    hosts: list[str] = Field(default_factory=list)
    vuln_classes: list[str] = Field(default_factory=list)
    source_url: str = ""


class FindingEvidence(BaseModel):
    request: str = ""
    response: str = ""
    diff: str = ""
    reproduction_steps: list[str] = Field(default_factory=list)
    raw_artifacts: dict[str, str] = Field(default_factory=dict)


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    contract_id: str
    asset_id: str
    title: str
    vulnerability_class: str
    severity: str = "medium"
    confidence: float = 0.0
    status: FindingStatus = FindingStatus.NEW
    evidence: FindingEvidence = Field(default_factory=FindingEvidence)
    hunter_id: str = ""
    validated_by: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class Report(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    finding_id: str
    contract_id: str
    title: str
    severity: str = "medium"
    cve: str = ""
    cwe: str = ""
    scope_asset: str = ""
    where_found: str = ""
    vulnerability_description: str = ""
    reproduction_steps: list[str] = Field(default_factory=list)
    security_impact: str = ""
    additional_links: list[str] = Field(default_factory=list)
    attachment_paths: list[str] = Field(default_factory=list)
    product_version: str = ""
    poc: str = ""
    attack_scenario: str = ""
    remediation: str = ""
    body_markdown: str = ""
    status: str = "draft"
    human_approved: bool = False
    submitted_at: datetime | None = None
    agent_version: str = "0.1.0"
    model_checkpoint: str = ""


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    actor: str
    action: str
    entity_type: str
    entity_id: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)


# --- SQLAlchemy ORM ---


class Base(DeclarativeBase):
    pass


class ContractRow(Base):
    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    program_id: Mapped[str] = mapped_column(String(128), index=True)
    slug: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(512))
    data: Mapped[dict] = mapped_column(JSON)
    status: Mapped[ContractStatus] = mapped_column(Enum(ContractStatus), default=ContractStatus.DISCOVERED)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    findings: Mapped[list["FindingRow"]] = relationship(back_populates="contract")


class FindingRow(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contract_id: Mapped[str] = mapped_column(String(36), ForeignKey("contracts.id"), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    status: Mapped[FindingStatus] = mapped_column(Enum(FindingStatus), default=FindingStatus.NEW)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contract: Mapped[ContractRow] = relationship(back_populates="findings")
    reports: Mapped[list["ReportRow"]] = relationship(back_populates="finding")


class ReportRow(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    finding_id: Mapped[str] = mapped_column(String(36), ForeignKey("findings.id"), index=True)
    contract_id: Mapped[str] = mapped_column(String(36), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    human_approved: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    finding: Mapped[FindingRow] = relationship(back_populates="reports")


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    input_data: Mapped[dict] = mapped_column(JSON, default=dict)
    output_data: Mapped[dict] = mapped_column(JSON, default=dict)


class PipelineStateRow(Base):
    __tablename__ = "pipeline_state"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def create_db_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def create_session_factory(database_url: str):
    engine = create_db_engine(database_url)
    return sessionmaker(bind=engine, expire_on_commit=False), engine
