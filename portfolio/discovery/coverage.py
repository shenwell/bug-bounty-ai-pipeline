"""Coverage index from disclosed reports — avoid re-hunting known areas."""

from __future__ import annotations

from collections import defaultdict

from portfolio.common.models import Contract, DisclosedReport


def index_by_program(reports: list[DisclosedReport]) -> dict[str, list[DisclosedReport]]:
    out: dict[str, list[DisclosedReport]] = defaultdict(list)
    for r in reports:
        key = r.program_slug or r.program_name.lower()
        if key:
            out[key].append(r)
    return dict(out)


def bind_program_reports(
    contract: Contract, reports: list[DisclosedReport]
) -> list[DisclosedReport]:
    by_slug = index_by_program(reports)
    items = list(by_slug.get(contract.slug, []))
    if not items:
        for r in reports:
            if r.program_name and r.program_name.lower() in contract.name.lower():
                items.append(r)
    return items


def attach_disclosed_to_contracts(
    contracts: list[Contract], reports: list[DisclosedReport]
) -> list[Contract]:
    for contract in contracts:
        items = bind_program_reports(contract, reports)
        contract.disclosed_count = len(items)
        contract.known_findings = [_finding_summary(r) for r in items[:30]]
    return contracts


def _finding_summary(report: DisclosedReport) -> str:
    classes = ", ".join(report.vuln_classes[:3])
    line = f"#{report.report_no} {report.title} ({report.severity}) [{classes}]"
    if report.poc:
        preview = report.poc.replace("\n", " ").strip()
        if len(preview) > 120:
            preview = preview[:117] + "..."
        line = f"{line} — {preview}"
    return line


def hunt_overlap(
    program_slug: str,
    hosts: list[str],
    vectors: list[str],
    reports: list[DisclosedReport],
) -> list[str]:
    """Return human-readable warnings for likely duplicate hunt targets."""
    warnings: list[str] = []
    program_reports = [r for r in reports if r.program_slug == program_slug]
    if not program_reports:
        return warnings

    host_set = {h.lower() for h in hosts}
    vector_set = {v.lower() for v in vectors}
    for r in program_reports:
        overlap_hosts = host_set.intersection({h.lower() for h in r.hosts})
        overlap_vectors = vector_set.intersection({v.lower() for v in r.vuln_classes})
        if overlap_hosts or overlap_vectors:
            warnings.append(
                f"disclosed #{r.report_no}: {r.title} — hosts={list(overlap_hosts) or '-'}, "
                f"classes={list(overlap_vectors) or r.vuln_classes[:2]}"
            )
    return warnings[:20]
