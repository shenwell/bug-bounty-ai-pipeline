"""Hunt plan — structured what/where/how instruction after contract selection."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from portfolio.common.config import AppConfig
from portfolio.common.models import Contract, DisclosedReport
from portfolio.discovery.coverage import bind_program_reports
from portfolio.discovery.dossier import dossier_path, ensure_dossier
from portfolio.discovery.scope_match import bind_disclosed_to_scope, compute_scope_coverage

ACCEPT_MARKERS = (
    "what we accept",
    "что принимаем",
    "что мы принимаем",
    "a report may be accepted",
)
REJECT_MARKERS = (
    "what we do not accept",
    "что не принимаем",
    "что мы не принимаем",
    "not accepted",
)
SAFE_TEST_MARKERS = (
    "safe testing",
    "безопасн",
    "testing requirements",
    "report requirements",
)


def _extract_markdown_section(text: str, start_markers: tuple[str, ...]) -> str:
    lower = text.lower()
    best_idx = -1
    for marker in start_markers:
        idx = lower.find(marker.lower())
        if idx >= 0 and (best_idx < 0 or idx < best_idx):
            best_idx = idx
    if best_idx < 0:
        return ""
    chunk = text[best_idx:]
    stop = re.search(r"\n#{1,3}\s+\d+\.", chunk[50:])
    if stop:
        chunk = chunk[: 50 + stop.start()]
    return chunk.strip()[:6000]


def _extract_bullet_lines(section: str, limit: int = 20) -> list[str]:
    lines: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "• ")):
            lines.append(stripped.lstrip("-*• ").strip())
        elif re.match(r"^\d+\.\s+", stripped):
            lines.append(re.sub(r"^\d+\.\s+", "", stripped))
        if len(lines) >= limit:
            break
    return lines


def _external_urls(contract: Contract) -> list[str]:
    urls: list[str] = []
    for ref in contract.external_refs:
        if ref.url and ref.url not in urls:
            urls.append(ref.url)
    description = contract.tab_sections.get("Description", "")
    for url in re.findall(r"https?://[^\s\]`\)\"']+", description):
        url = url.rstrip(".,;)")
        if url not in urls:
            urls.append(url)
    return urls


def _auth_accounts_section(contract: Contract) -> list[str]:
    if contract.dossier_dir:
        auth_path = Path(contract.dossier_dir) / "auth_accounts.json"
    else:
        auth_path = Path("data/dossiers") / contract.slug / "auth_accounts.json"
    if not auth_path.exists():
        return []
    try:
        payload = json.loads(auth_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    summary = payload.get("summary") or {}
    lines = [
        f"- **Статус:** `{summary.get('status', 'unknown')}`",
        f"- **Готов к auth-hunt:** {'да' if summary.get('ready_for_auth_hunt') else 'нет'}",
        f"- Подробности: `auth_accounts.md`",
    ]
    blockers = summary.get("blockers") or []
    if blockers:
        lines.append(f"- **Блокеры:** {', '.join(blockers)}")
    accounts = payload.get("accounts") or []
    if accounts:
        phones = accounts[0].get("phones") or []
        if phones:
            lines.append(f"- Демо-телефон: `{phones[0]}`")
    return lines


def build_hunt_plan_markdown(
    contract: Contract,
    reports: list[DisclosedReport],
    *,
    surfaces: dict[str, Any] | None = None,
) -> str:
    program_reports = bind_program_reports(contract, reports)
    bindings = bind_disclosed_to_scope(contract, program_reports)
    avoid_hosts, avoid_vectors, gaps = compute_scope_coverage(contract, bindings)

    description = contract.tab_sections.get("Description", "")
    accept_section = _extract_markdown_section(description, ACCEPT_MARKERS)
    reject_section = _extract_markdown_section(description, REJECT_MARKERS)
    safe_section = _extract_markdown_section(description, SAFE_TEST_MARKERS)
    accept_bullets = _extract_bullet_lines(accept_section, 15)
    reject_bullets = _extract_bullet_lines(reject_section, 15)

    lines = [
        f"# План проверки — {contract.name} (`{contract.slug}`)",
        "",
        "> Инструкция: что, где и как проверять. Сгенерировано после выбора контракта.",
        "",
        f"- **Источник:** {contract.source_url}",
        f"- **Score:** {contract.score} | **Платная:** {'да' if contract.is_paid else 'нет'}",
        f"- **Обновлено досье:** {contract.dossier_refreshed_at or '—'}",
        "",
        "## 1. Что проверяем (scope)",
        "",
    ]
    if contract.scope:
        lines.extend(f"- `{host}`" for host in contract.scope)
    else:
        lines.append("- _Scope не распознан — см. Description в raw/_")

    lines.extend(["", "## 2. Куда идти в первую очередь", ""])
    if gaps:
        lines.extend(f"- `{gap}` — нет disclosed, приоритет разведки" for gap in gaps[:12])
    else:
        lines.append("- Равномерно по всем in-scope активам")

    lines.extend(["", "## 3. Что НЕ проверять / не дублировать", ""])
    if contract.out_of_scope:
        lines.append("**Out of scope:**")
        lines.extend(f"- `{host}`" for host in contract.out_of_scope[:15])
    if avoid_hosts:
        lines.append("")
        lines.append("**Disclosed — не повторять на хостах:**")
        lines.extend(f"- `{host}`" for host in avoid_hosts[:15])
    if avoid_vectors:
        lines.append("")
        lines.append("**Disclosed — не дублировать классы:**")
        lines.extend(f"- `{vector}`" for vector in avoid_vectors[:12])
    if reject_bullets:
        lines.append("")
        lines.append("**Из правил программы (не принимается):**")
        lines.extend(f"- {item[:200]}" for item in reject_bullets[:10])
    if not (contract.out_of_scope or avoid_hosts or avoid_vectors or reject_bullets):
        lines.append("- Явных ограничений нет — см. полное Description")

    lines.extend(["", "## 4. Векторы и фокус hunt", ""])
    if contract.target_vectors:
        lines.extend(f"- `{vector}`" for vector in contract.target_vectors)
    if accept_bullets:
        lines.append("")
        lines.append("**Программа явно принимает (impact):**")
        lines.extend(f"- {item[:200]}" for item in accept_bullets[:12])
    elif accept_section:
        lines.append(accept_section[:1500])

    lines.extend(["", "## 5. Ограничения тестирования", ""])
    constraints = contract.constraints
    if constraints.vpn_required:
        lines.append("- VPN обязателен")
    if constraints.required_headers:
        for key, val in constraints.required_headers.items():
            lines.append(f"- Заголовок `{key}`: `{val}`")
    if constraints.no_bulk_enumeration:
        lines.append("- Без массовой переборной разведки")
    if constraints.internal_test_hosts:
        lines.append(f"- Разрешённые internal test hosts: {', '.join(constraints.internal_test_hosts)}")
    if constraints.allowed_file_reads:
        lines.append(f"- Разрешённые file read: {', '.join(constraints.allowed_file_reads)}")
    if safe_section:
        lines.append("")
        lines.append(safe_section[:2000])
    if not any(
        [
            constraints.vpn_required,
            constraints.required_headers,
            constraints.no_bulk_enumeration,
            constraints.internal_test_hosts,
            safe_section,
        ]
    ):
        lines.append("- См. раздел Report requirements в Description")

    lines.extend(["", "## 6. Внешние ресурсы", ""])
    urls = _external_urls(contract)
    if urls:
        for url in urls[:15]:
            ref = next((r for r in contract.external_refs if r.url == url), None)
            tag = f" ({ref.ref_type}, HTTP {ref.status_code})" if ref and ref.status_code else ""
            file_note = f" → `{ref.file_path}`" if ref and ref.file_path else ""
            lines.append(f"- [{url}]({url}){tag}{file_note}")
    else:
        lines.append("- Нет загруженных внешних ссылок (после refresh проверьте api-docs в Description)")

    lines.extend(["", "## 7. Disclosed по программе", ""])
    if bindings:
        for binding in bindings[:20]:
            report = binding.report
            tag = f" @ {', '.join(binding.matched_hosts)}" if binding.matched_hosts else ""
            lines.append(f"- #{report.report_no} **{report.title}** ({report.severity}){tag}")
            if report.poc:
                preview = report.poc.replace("\n", " ")[:150]
                lines.append(f"  - {preview}...")
    else:
        lines.append("- Disclosed для программы не найдены")

    auth_section = _auth_accounts_section(contract)
    if auth_section:
        lines.extend(["", "## 7.1 Тестовые аккаунты", ""])
        lines.extend(auth_section)

    lines.extend(["", "## 8. Recon checklist", ""])
    lines.extend(
        [
            "- [ ] Прочитать `landscape.md` и `raw/page_props.json`",
            "- [ ] Проверить `auth_accounts.md` — демо-креды / блокеры auth-hunt",
            "- [ ] Проверить scope guardrails перед запросами",
            "- [ ] Открыть/изучить API docs и внешние refs",
            "- [ ] Сверить live hosts/endpoints в `surface.json`",
            "- [ ] Составить список endpoints/параметров для hunt",
        ]
    )
    for asset in contract.assets[:10]:
        lines.append(f"- [ ] Asset `{asset.identifier}` ({asset.engagement_profile})")

    lines.extend(["", "## 9. Hunt checklist", ""])
    lines.extend(
        [
            "- [ ] Только in-scope хосты и разрешённые действия",
            "- [ ] Приоритет: gaps + high-impact векторы из правил",
            "- [ ] Не дублировать disclosed hosts/классы",
            "- [ ] Severity ≥ medium перед подготовкой отчёта",
            "- [ ] PoC + 3 воспроизведения перед report",
        ]
    )

    if surfaces:
        lines.extend(["", "## 10. Recon surface (live)", ""])
        for asset_id, surface in list(surfaces.items())[:8]:
            lines.append(f"### `{asset_id}`")
            if isinstance(surface, dict):
                hosts = surface.get("live_hosts") or []
                endpoints = surface.get("endpoints") or []
                if hosts:
                    lines.append(f"- live_hosts: {hosts[:5]}")
                if endpoints:
                    lines.append(f"- endpoints ({len(endpoints)}): {endpoints[:8]}")
            else:
                lines.append(f"- {str(surface)[:300]}")

    lines.extend(["", "## 11. Артефакты", ""])
    dossier = Path(contract.dossier_dir) if contract.dossier_dir else (
        Path(contract.landscape_file).parent if contract.landscape_file else Path("data/dossiers") / contract.slug
    )
    lines.extend(
        [
            f"- `{dossier / 'README.md'}` — индекс рабочей папки",
            f"- `{dossier / 'landscape.md'}` — ландшафт DO/DON'T",
            f"- `{dossier / 'hunt_plan.md'}` — этот файл",
            f"- `{dossier / 'contract.json'}` — снимок контракта",
            f"- `{dossier / 'disclosed.json'}` — disclosed по программе",
            f"- `{dossier / 'raw' / 'page_props.json'}` — сырой JSON с сайта",
            f"- `{dossier / 'raw' / 'page.html'}` — HTML снапшот",
            f"- `{dossier / 'surface.json'}` — recon",
            f"- `{dossier / 'auth_accounts.md'}` — тестовые аккаунты",
            f"- `{dossier / 'references.json'}` — внешние ссылки",
            f"- `{dossier / 'findings'}/` — находки",
            f"- `{dossier / 'reports'}/` — отчёты",
        ]
    )
    if contract.tab_sections:
        lines.append("")
        lines.append("**Вкладки (из __NEXT_DATA__):** " + ", ".join(contract.tab_sections.keys()))

    return "\n".join(lines).strip() + "\n"


def write_hunt_plan(
    config: AppConfig,
    contract: Contract,
    reports: list[DisclosedReport],
    *,
    surfaces: dict[str, Any] | None = None,
) -> str:
    ensure_dossier(config, contract.slug)
    path = dossier_path(config, contract.slug, "hunt_plan.md")
    path.write_text(build_hunt_plan_markdown(contract, reports, surfaces=surfaces), encoding="utf-8")
    return str(path).replace("\\", "/")


def update_hunt_plan_surfaces(
    config: AppConfig,
    contract: Contract,
    surfaces: dict[str, Any],
    reports: list[DisclosedReport] | None = None,
) -> str:
    from portfolio.discovery.disclosed_runner import load_disclosed_reports

    report_list = reports if reports is not None else load_disclosed_reports(config)
    return write_hunt_plan(config, contract, report_list, surfaces=surfaces)
