"""Per-contract landscape dossier — decision guide for hunt/recon."""

from __future__ import annotations

from pathlib import Path

from portfolio.common.config import AppConfig
from portfolio.common.models import Contract, DisclosedReport
from portfolio.discovery.coverage import bind_program_reports
from portfolio.discovery.scope_match import (
    DisclosedScopeBinding,
    bind_disclosed_to_scope,
    compute_scope_coverage,
)


def _tab_section_lines(tab_sections: dict[str, str], max_chars: int = 4000) -> list[str]:
    lines: list[str] = []
    for label, content in tab_sections.items():
        body = (content or "").strip()
        if not body:
            continue
        if len(body) > max_chars:
            body = body[: max_chars - 3] + "..."
        lines.append(f"### {label}\n\n{body}\n")
    return lines


def _binding_line(binding: DisclosedScopeBinding) -> str:
    report = binding.report
    classes = ", ".join(report.vuln_classes[:4]) or "—"
    hosts = ", ".join(binding.matched_hosts) or "—"
    line = f"- **#{report.report_no}** {report.title} ({report.severity}) — `{classes}`"
    if binding.matched_hosts:
        line += f" @ {hosts}"
    elif binding.unknown_hosts:
        line += f" — hosts unclear: {', '.join(binding.unknown_hosts[:3])}"
    if report.poc:
        preview = report.poc.replace("\n", " ").strip()
        if len(preview) > 160:
            preview = preview[:157] + "..."
        line += f"\n  - PoC: {preview}"
    return line


def _do_dont_lists(
    contract: Contract,
    bindings: list[DisclosedScopeBinding],
    avoid_hosts: list[str],
    avoid_vectors: list[str],
    gaps: list[str],
) -> tuple[list[str], list[str]]:
    do: list[str] = []
    dont: list[str] = []

    if not contract.is_paid:
        dont.append("Не охотиться — программа без выплат.")
    if contract.constraints.vpn_required:
        do.append("Подключить VPN до любых запросов в scope.")
    if contract.constraints.required_headers:
        hdr = ", ".join(f"{k}: {v}" for k, v in contract.constraints.required_headers.items())
        do.append(f"Добавить обязательные заголовки: {hdr}.")
    if contract.constraints.no_bulk_enumeration:
        dont.append("Массовая переборная разведка запрещена правилами.")
    if contract.out_of_scope:
        dont.append(f"Не трогать out-of-scope: {', '.join(contract.out_of_scope[:8])}.")

    for host in avoid_hosts[:15]:
        vectors = [
            ", ".join(b.report.vuln_classes[:3])
            for b in bindings
            if host in b.matched_hosts and b.report.vuln_classes
        ]
        vec = vectors[0] if vectors else "известные классы"
        dont.append(f"Не повторять disclosed на `{host}` ({vec}).")

    for vector in avoid_vectors[:10]:
        if vector.startswith("cwe-"):
            dont.append(f"Осторожно с {vector.upper()} — уже есть disclosed в программе.")
        else:
            dont.append(f"Не дублировать типичный {vector.upper()} без нового вектора/ассета.")

    if gaps:
        do.append(f"Приоритет scope без disclosed: {', '.join(gaps[:10])}.")
    elif contract.scope and not bindings:
        do.append("Disclosed пуст — разведка по всему scope с нуля.")
    if contract.tab_sections:
        tab_names = ", ".join(contract.tab_sections.keys())
        do.append(f"Учесть вкладки программы: {tab_names}.")

    if contract.is_paid and contract.reward_ranges:
        top = max(contract.reward_ranges, key=lambda r: r.max_amount, default=None)
        if top and top.max_amount:
            do.append(f"Фокус на high-impact: до {int(top.max_amount):,} ₽ за {top.severity}.")

    return do, dont


def build_landscape_markdown(
    contract: Contract,
    bindings: list[DisclosedScopeBinding],
    avoid_hosts: list[str],
    avoid_vectors: list[str],
    gaps: list[str],
) -> str:
    in_scope = [b for b in bindings if b.in_scope]
    unclear = [b for b in bindings if not b.in_scope and b.unknown_hosts]
    oos = [b for b in bindings if b.out_of_scope_hosts and not b.in_scope]

    do, dont = _do_dont_lists(contract, bindings, avoid_hosts, avoid_vectors, gaps)

    lines = [
        f"# {contract.name} (`{contract.slug}`)",
        "",
        "> Ландшафт для принятия решений: что уже закрыто disclosed, куда идти, куда не идти.",
        "",
        "## Решение",
        "",
        f"- **Платная программа:** {'да' if contract.is_paid else 'нет'}",
        f"- **Disclosed отчётов:** {contract.disclosed_count}",
        f"- **Scope (in):** {len(contract.scope)} | **out-of-scope:** {len(contract.out_of_scope)}",
        f"- **Не трогать (hosts):** {', '.join(avoid_hosts[:12]) or '—'}",
        f"- **Не дублировать (классы):** {', '.join(avoid_vectors[:12]) or '—'}",
        f"- **Потенциальные gaps:** {', '.join(gaps[:12]) or '—'}",
        "",
        "## DO",
        "",
    ]
    if do:
        lines.extend(f"- {item}" for item in do)
    else:
        lines.append("- —")
    lines.extend(["", "## DON'T", ""])
    if dont:
        lines.extend(f"- {item}" for item in dont)
    else:
        lines.append("- —")

    lines.extend(["", "## Scope (in)", ""])
    if contract.scope:
        lines.extend(f"- `{s}`" for s in contract.scope[:40])
    else:
        lines.append("- _не распознан автоматически — см. вкладку Scope_")

    lines.extend(["", "## Out of scope", ""])
    if contract.out_of_scope:
        lines.extend(f"- `{s}`" for s in contract.out_of_scope[:40])
    else:
        lines.append("- —")

    if contract.reward_ranges:
        lines.extend(["", "## Rewards", ""])
        for reward in contract.reward_ranges:
            lines.append(
                f"- **{reward.severity}:** до {int(reward.max_amount):,} {reward.currency}"
            )

    if contract.constraints.raw_rules or contract.constraints.vpn_required:
        lines.extend(["", "## Ограничения", ""])
        if contract.constraints.vpn_required:
            lines.append("- VPN обязателен")
        if contract.constraints.required_headers:
            for key, val in contract.constraints.required_headers.items():
                lines.append(f"- Заголовок `{key}`: `{val}`")
        for rule in contract.constraints.raw_rules[:8]:
            lines.append(f"- {rule[:200]}")

    if contract.tab_sections:
        lines.extend(["", "## Вкладки программы", ""])
        lines.extend(_tab_section_lines(contract.tab_sections))

    lines.extend(["", "## Disclosed — in scope", ""])
    if in_scope:
        lines.extend(_binding_line(b) for b in in_scope)
    else:
        lines.append("- —")

    lines.extend(["", "## Disclosed — hosts неясны", ""])
    if unclear:
        lines.extend(_binding_line(b) for b in unclear)
    else:
        lines.append("- —")

    if oos:
        lines.extend(["", "## Disclosed — out of scope hosts", ""])
        lines.extend(_binding_line(b) for b in oos)

    lines.extend(["", "## Источник", "", f"- Программа: {contract.source_url}", ""])
    if contract.landscape_file:
        lines.append(f"- Досье: `{contract.landscape_file}`")

    return "\n".join(lines).strip() + "\n"


from portfolio.discovery.dossier import ensure_dossier


def write_landscape(config: AppConfig, contract: Contract, content: str) -> Path:
    out_dir = ensure_dossier(config, contract.slug)
    path = out_dir / "landscape.md"
    path.write_text(content, encoding="utf-8")
    return path


def enrich_contract_landscape(
    config: AppConfig, contract: Contract, reports: list[DisclosedReport]
) -> Contract:
    program_reports = bind_program_reports(contract, reports)
    bindings = bind_disclosed_to_scope(contract, program_reports)
    avoid_hosts, avoid_vectors, gaps = compute_scope_coverage(contract, bindings)

    contract.avoid_hosts = avoid_hosts
    contract.avoid_vectors = avoid_vectors
    contract.scope_gaps = gaps
    contract.disclosed_count = len(program_reports)
    contract.known_findings = [_scoped_finding_summary(b) for b in bindings[:30]]

    content = build_landscape_markdown(
        contract, bindings, avoid_hosts, avoid_vectors, gaps
    )
    path = write_landscape(config, contract, content)
    contract.landscape_file = str(path).replace("\\", "/")
    contract.dossier_dir = str(path.parent).replace("\\", "/")
    return contract


def enrich_all_landscapes(
    config: AppConfig, contracts: list[Contract], reports: list[DisclosedReport]
) -> list[Contract]:
    return [enrich_contract_landscape(config, c, reports) for c in contracts]


def _scoped_finding_summary(binding: DisclosedScopeBinding) -> str:
    report = binding.report
    classes = ", ".join(report.vuln_classes[:3])
    scope_tag = "in-scope" if binding.in_scope else "unclear"
    if binding.matched_hosts:
        scope_tag = f"in-scope@{','.join(binding.matched_hosts[:2])}"
    line = f"#{report.report_no} {report.title} ({report.severity}) [{classes}] ({scope_tag})"
    if report.poc:
        preview = report.poc.replace("\n", " ").strip()
        if len(preview) > 100:
            preview = preview[:97] + "..."
        line = f"{line} — {preview}"
    return line
