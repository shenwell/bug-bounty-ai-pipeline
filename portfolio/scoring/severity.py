"""Severity assessment — gate low/none findings before report submission."""

from __future__ import annotations

import re
from dataclasses import dataclass

from portfolio.common.config import AppConfig
from portfolio.common.models import Contract, Finding

SEVERITY_RANK: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "none": 0,
    "informational": 0,
    "info": 0,
    "unspecified": 0,
}

VULN_CLASS_BASELINE: dict[str, str] = {
    "rce": "critical",
    "sqli": "high",
    "sql injection": "high",
    "ssrf": "high",
    "idor": "medium",
    "auth": "high",
    "authz": "high",
    "jwt": "medium",
    "xss": "medium",
    "csrf": "low",
    "xxe": "high",
    "lfi": "high",
    "rfi": "high",
    "disclosure": "low",
    "open redirect": "low",
    "misconfiguration": "low",
}

HIGH_IMPACT_MARKERS = re.compile(
    r"\b(rce|remote code|account takeover|ato|privilege escalation|"
    r"admin access|payment|credential|password|token leak|pii|personal data)\b",
    re.I,
)
LOW_IMPACT_MARKERS = re.compile(
    r"\b(self[- ]xss|reflected only|missing header|clickjacking|"
    r"version disclosure|banner|informational|best practice|low impact)\b",
    re.I,
)


@dataclass
class SeverityAssessment:
    severity: str
    declared_severity: str
    reportable: bool
    estimated_payout_rub: float
    reason: str
    min_required: str = "medium"


def normalize_severity(value: str) -> str:
    key = (value or "medium").lower().strip()
    aliases = {
        "критический": "critical",
        "высокий": "high",
        "средний": "medium",
        "низкий": "low",
        "отсутствует": "none",
        "не указан": "unspecified",
    }
    return aliases.get(key, key)


def severity_rank(severity: str) -> int:
    return SEVERITY_RANK.get(normalize_severity(severity), 0)


def is_reportable_severity(severity: str, min_severity: str = "medium") -> bool:
    return severity_rank(severity) >= severity_rank(min_severity)


def estimate_payout_rub(contract: Contract, severity: str) -> float:
    target = normalize_severity(severity)
    amount = 0.0
    for reward in contract.reward_ranges:
        if normalize_severity(reward.severity) == target:
            amount = max(amount, reward.max_amount)
    if amount:
        return amount
    fallback = {
        "critical": 500_000,
        "high": 100_000,
        "medium": 30_000,
        "low": 5_000,
        "none": 0,
    }
    return fallback.get(target, 0.0)


def _baseline_from_class(vulnerability_class: str) -> str:
    key = vulnerability_class.lower().strip()
    if key.startswith("cwe-"):
        return "medium"
    return VULN_CLASS_BASELINE.get(key, "medium")


def _impact_adjustment(finding: Finding) -> int:
    text = " ".join(
        [
            finding.title,
            finding.metadata.get("security_impact", ""),
            finding.metadata.get("vulnerability_description", ""),
            finding.metadata.get("description", ""),
            finding.evidence.request,
            finding.evidence.response,
        ]
    )
    if LOW_IMPACT_MARKERS.search(text):
        return -1
    if HIGH_IMPACT_MARKERS.search(text):
        return 1
    return 0


def _rank_to_severity(rank: int) -> str:
    for name, value in sorted(SEVERITY_RANK.items(), key=lambda item: item[1], reverse=True):
        if value == rank:
            return name
    return "medium"


def assess_finding_severity(
    finding: Finding,
    contract: Contract,
    config: AppConfig | None = None,
) -> SeverityAssessment:
    min_required = "medium"
    if config is not None:
        min_required = normalize_severity(config.scoring.min_reportable_severity)

    declared = normalize_severity(finding.severity)
    baseline_rank = severity_rank(_baseline_from_class(finding.vulnerability_class))
    impact_adj = _impact_adjustment(finding)
    rank = baseline_rank + impact_adj
    if impact_adj > 0 and severity_rank(declared) > rank:
        rank = severity_rank(declared)
    rank = max(0, min(4, rank))
    assessed = _rank_to_severity(rank)

    payout = estimate_payout_rub(contract, assessed)
    reportable = is_reportable_severity(assessed, min_required)

    reasons: list[str] = [
        f"class={finding.vulnerability_class}→baseline {_baseline_from_class(finding.vulnerability_class)}",
        f"declared={declared}",
    ]
    if impact_adj > 0:
        reasons.append("high-impact markers")
    if impact_adj < 0:
        reasons.append("low-impact markers")
    if not reportable:
        reasons.append(f"below min {min_required} (low/none not worth submitting)")
    elif payout and payout < 10_000 and assessed == "medium":
        reasons.append(f"estimated payout ~{int(payout):,} RUB")

    return SeverityAssessment(
        severity=assessed,
        declared_severity=declared,
        reportable=reportable,
        estimated_payout_rub=payout,
        reason="; ".join(reasons),
        min_required=min_required,
    )


def apply_severity_gate(
    finding: Finding,
    contract: Contract,
    config: AppConfig,
) -> SeverityAssessment:
    assessment = assess_finding_severity(finding, contract, config)
    finding.severity = assessment.severity
    finding.metadata["severity_assessment"] = {
        "severity": assessment.severity,
        "declared_severity": assessment.declared_severity,
        "reportable": assessment.reportable,
        "estimated_payout_rub": assessment.estimated_payout_rub,
        "reason": assessment.reason,
        "min_required": assessment.min_required,
    }
    return assessment


def assess_report_severity(
    *,
    vulnerability_class: str,
    title: str,
    declared_severity: str,
    security_impact: str,
    vulnerability_description: str,
    contract: Contract,
    config: AppConfig,
) -> SeverityAssessment:
    finding = Finding(
        contract_id=contract.id,
        asset_id="assessment",
        title=title,
        vulnerability_class=vulnerability_class,
        severity=declared_severity,
        metadata={
            "security_impact": security_impact,
            "vulnerability_description": vulnerability_description,
        },
    )
    return assess_finding_severity(finding, contract, config)
