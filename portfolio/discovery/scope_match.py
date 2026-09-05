"""Match disclosed report hosts against contract scope."""

from __future__ import annotations

import re
from dataclasses import dataclass

from portfolio.common.models import Contract, DisclosedReport

DOMAIN_RE = re.compile(
    r"(?:\*\.|www\.)?[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+"
)


def normalize_host(host: str) -> str:
    return host.lower().strip().rstrip(".")


def host_matches_pattern(host: str, pattern: str) -> bool:
    host = normalize_host(host)
    pattern = pattern.lower().strip()
    if not host or not pattern:
        return False
    if pattern.startswith("*."):
        suffix = pattern[1:]
        return host.endswith(suffix) or host == suffix.lstrip(".")
    bare = pattern[4:] if pattern.startswith("www.") else pattern
    return host == pattern or host == bare or host.endswith("." + bare)


def is_out_of_scope(host: str, out_of_scope: list[str]) -> bool:
    return any(host_matches_pattern(host, entry) for entry in out_of_scope)


def is_in_scope(host: str, scope: list[str], out_of_scope: list[str]) -> bool:
    if is_out_of_scope(host, out_of_scope):
        return False
    if not scope:
        return False
    return any(host_matches_pattern(host, entry) for entry in scope)


def extract_scope_entries(scope: list[str]) -> list[str]:
    entries: list[str] = []
    for item in scope:
        for match in DOMAIN_RE.findall(item):
            if match not in entries:
                entries.append(match)
        if item not in entries:
            entries.append(item)
    return entries


def collect_report_hosts(report: DisclosedReport) -> list[str]:
    hosts = list(report.hosts)
    for source in (report.title, report.poc, report.description):
        for match in DOMAIN_RE.findall(source or ""):
            if match not in hosts:
                hosts.append(match)
    return hosts


@dataclass
class DisclosedScopeBinding:
    report: DisclosedReport
    matched_hosts: list[str]
    unknown_hosts: list[str]
    out_of_scope_hosts: list[str]

    @property
    def in_scope(self) -> bool:
        return bool(self.matched_hosts)


def bind_disclosed_to_scope(
    contract: Contract, reports: list[DisclosedReport]
) -> list[DisclosedScopeBinding]:
    scope = extract_scope_entries(contract.scope)
    bindings: list[DisclosedScopeBinding] = []
    for report in reports:
        matched: list[str] = []
        unknown: list[str] = []
        oos: list[str] = []
        for host in collect_report_hosts(report):
            if is_out_of_scope(host, contract.out_of_scope):
                oos.append(host)
            elif is_in_scope(host, scope, contract.out_of_scope):
                if host not in matched:
                    matched.append(host)
            else:
                if host not in unknown:
                    unknown.append(host)
        bindings.append(
            DisclosedScopeBinding(
                report=report,
                matched_hosts=matched,
                unknown_hosts=unknown,
                out_of_scope_hosts=oos,
            )
        )
    return bindings


def compute_scope_coverage(
    contract: Contract, bindings: list[DisclosedScopeBinding]
) -> tuple[list[str], list[str], list[str]]:
    """Return avoid_hosts, avoid_vectors, scope_gaps."""
    avoid_hosts: list[str] = []
    avoid_vectors: list[str] = []
    covered_scope: set[str] = set()

    for binding in bindings:
        for host in binding.matched_hosts:
            if host not in avoid_hosts:
                avoid_hosts.append(host)
            covered_scope.add(normalize_host(host))
        if binding.matched_hosts or not binding.report.hosts:
            for vector in binding.report.vuln_classes:
                if vector not in avoid_vectors:
                    avoid_vectors.append(vector)

    scope_entries = extract_scope_entries(contract.scope)
    gaps: list[str] = []
    for entry in scope_entries:
        entry_norm = normalize_host(entry.lstrip("*."))
        if entry.startswith("*."):
            prefix = entry[2:]
            if not any(h.endswith(prefix) or h == prefix for h in covered_scope):
                if entry not in gaps:
                    gaps.append(entry)
        elif entry_norm not in covered_scope and entry not in gaps:
            gaps.append(entry)
    return avoid_hosts, avoid_vectors, gaps
