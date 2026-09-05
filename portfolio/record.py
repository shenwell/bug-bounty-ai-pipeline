"""Record findings and reports into dossier without hunt FSM."""

from __future__ import annotations

import json
from pathlib import Path

from portfolio.common.config import AppConfig
from portfolio.common.models import Contract, Finding, Report
from portfolio.discovery.dossier import save_finding_snapshot, save_report_artifacts
from portfolio.discover_ops import load_contracts
from portfolio.review.standoff_format import standoff_form_payload
from portfolio.scoring.severity import assess_report_severity


def _contract_for_slug(config: AppConfig, slug: str) -> Contract:
    for contract in load_contracts(config):
        if contract.slug == slug:
            return contract
    dossier_path = Path(config.data.dossiers_dir)
    if not dossier_path.is_absolute():
        dossier_path = Path(__file__).resolve().parents[2] / dossier_path
    dossier_contract = dossier_path / slug / "contract.json"
    if dossier_contract.exists():
        payload = json.loads(dossier_contract.read_text(encoding="utf-8"))
        return Contract(**payload["contract"])
    raise FileNotFoundError(f"No contract for slug {slug}")


def record_finding(config: AppConfig, slug: str, data: dict) -> Path:
    contract = _contract_for_slug(config, slug)
    finding = Finding(**data)
    return save_finding_snapshot(config, contract, finding)


def record_report(config: AppConfig, slug: str, data: dict) -> Path:
    contract = _contract_for_slug(config, slug)
    report = Report(**data)
    assessment = assess_report_severity(
        vulnerability_class=data.get("vulnerability_class", report.title),
        title=report.title,
        declared_severity=report.severity,
        security_impact=report.security_impact,
        vulnerability_description=report.vulnerability_description,
        contract=contract,
        config=config,
    )
    if not assessment.reportable:
        raise ValueError(assessment.reason)
    form = standoff_form_payload(report, contract)
    paths = save_report_artifacts(config, contract, report, form)
    return Path(paths["markdown"])
