"""Standoff365 bug report form — canonical field layout."""

from __future__ import annotations

from portfolio.common.models import Contract, Finding, Report

SEVERITY_STANDOFF = {
    "critical": "Критический",
    "high": "Высокий",
    "medium": "Средний",
    "low": "Низкий",
    "none": "Отсутствует",
    "informational": "Отсутствует",
    "info": "Отсутствует",
    "unspecified": "Не указан",
}

VULN_CLASS_TO_CWE = {
    "ssrf": "CWE-918",
    "xss": "CWE-79",
    "sqli": "CWE-89",
    "sql injection": "CWE-89",
    "idor": "CWE-639",
    "rce": "CWE-94",
    "csrf": "CWE-352",
    "xxe": "CWE-611",
    "auth": "CWE-287",
    "lfi": "CWE-22",
    "rfi": "CWE-98",
    "open redirect": "CWE-601",
    "disclosure": "CWE-200",
}

DESCRIPTION_SECTIONS = (
    "Где обнаружено",
    "Описание уязвимости",
    "Шаги воспроизведения",
    "Влияние на безопасность",
    "Рекомендации",
    "Дополнительные ссылки",
)

# Applies only to reports/submit/*-paste.md description block — not drafts/EVIDENCE/hunt.
# See policy/submit.md and submit_text.py.


def severity_label(severity: str) -> str:
    return SEVERITY_STANDOFF.get(severity.lower().strip(), "Средний")


def infer_cwe(vulnerability_class: str, explicit: str = "") -> str:
    if explicit.strip():
        return explicit.strip()
    key = vulnerability_class.lower().strip()
    if key.startswith("cwe-"):
        return key.upper().replace("cwe-", "CWE-")
    return VULN_CLASS_TO_CWE.get(key, "")


def empty_description_template() -> str:
    return """## Где обнаружено



## Описание уязвимости



## Шаги воспроизведения

1. 
2. 
3. 

## Влияние на безопасность



## Рекомендации



## Дополнительные ссылки


"""


def format_reproduction_steps(steps: list[str]) -> str:
    if not steps:
        return "1. \n2. \n3. "
    return "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1))


def format_additional_links(links: list[str]) -> str:
    if not links:
        return ""
    return "\n".join(f"- {link}" for link in links)


def build_description_markdown(
    where_found: str,
    vulnerability_description: str,
    reproduction_steps: list[str],
    security_impact: str,
    additional_links: list[str],
    *,
    remediation: str = "",
) -> str:
    recommendations_block = remediation.strip()
    if not recommendations_block:
        recommendations_block = "—"

    return f"""## Где обнаружено

{where_found.strip()}

## Описание уязвимости

{vulnerability_description.strip()}

## Шаги воспроизведения

{format_reproduction_steps(reproduction_steps)}

## Влияние на безопасность

{security_impact.strip()}

## Рекомендации

{recommendations_block}

## Дополнительные ссылки

{format_additional_links(additional_links)}
""".strip() + "\n"


def resolve_scope_asset(finding: Finding, contract: Contract) -> str:
    meta = finding.metadata or {}
    if meta.get("scope_asset"):
        return str(meta["scope_asset"])
    for asset in contract.assets:
        if asset.id == finding.asset_id:
            return asset.identifier
    if contract.scope:
        return contract.scope[0]
    return ""


def build_report_from_finding(
    finding: Finding,
    contract: Contract,
    *,
    narrative: str = "",
    remediation: str = "",
) -> Report:
    meta = finding.metadata or {}
    evidence = finding.evidence

    where_found = str(meta.get("where_found") or meta.get("location") or resolve_scope_asset(finding, contract))
    if meta.get("url"):
        where_found = f"{where_found}\n\nURL: {meta['url']}"

    vulnerability_description = str(
        meta.get("vulnerability_description")
        or meta.get("description")
        or narrative
        or finding.title
    )
    reproduction_steps = list(evidence.reproduction_steps or meta.get("reproduction_steps") or [])
    if not reproduction_steps and evidence.request:
        reproduction_steps = [evidence.request]
        if evidence.response:
            reproduction_steps.append(f"Ответ сервера:\n```\n{evidence.response[:2000]}\n```")

    security_impact = str(
        meta.get("security_impact")
        or meta.get("impact")
        or "См. описание уязвимости и шаги воспроизведения."
    )
    remediation_text = str(
        meta.get("remediation")
        or remediation
        or ""
    )
    additional_links = list(meta.get("additional_links") or meta.get("links") or [])
    attachment_paths = list(meta.get("attachment_paths") or meta.get("files") or [])
    for path in evidence.raw_artifacts.values():
        if path and path not in attachment_paths:
            attachment_paths.append(path)

    description = build_description_markdown(
        where_found=where_found,
        vulnerability_description=vulnerability_description,
        reproduction_steps=reproduction_steps,
        security_impact=security_impact,
        additional_links=additional_links,
        remediation=remediation_text,
    )

    return Report(
        finding_id=finding.id,
        contract_id=contract.id,
        title=finding.title,
        severity=finding.severity,
        cve=str(meta.get("cve") or ""),
        cwe=infer_cwe(finding.vulnerability_class, str(meta.get("cwe") or "")),
        scope_asset=resolve_scope_asset(finding, contract),
        where_found=where_found,
        vulnerability_description=vulnerability_description,
        reproduction_steps=reproduction_steps,
        security_impact=security_impact,
        additional_links=additional_links,
        attachment_paths=attachment_paths,
        product_version=str(meta.get("product_version") or contract.name),
        poc=evidence.request,
        attack_scenario=narrative[:2000] if narrative else security_impact[:2000],
        remediation=remediation_text
        or remediation
        or "Применить принцип least privilege, валидацию входных данных и исправление корневой причины.",
        body_markdown=description,
        status="in_review",
    )


def standoff_form_payload(report: Report) -> dict[str, object]:
    """Fields aligned with Standoff365 submit form."""
    return {
        "title": report.title,
        "severity": report.severity,
        "severity_label": severity_label(report.severity),
        "cve": report.cve,
        "cwe": report.cwe,
        "scope_asset": report.scope_asset,
        "description": report.body_markdown,
        "files": report.attachment_paths,
        "sections": DESCRIPTION_SECTIONS,
    }
