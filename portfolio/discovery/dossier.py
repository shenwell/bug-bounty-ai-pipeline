"""Contract dossier — single project folder for all documents and artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from portfolio.common.config import AppConfig
from portfolio.common.logging import get_logger
from portfolio.common.models import Contract, DisclosedReport, Finding, Report
from portfolio.discovery.coverage import bind_program_reports

logger = get_logger(__name__)

SUBDIRS = ("raw", "external_refs", "findings", "reports", "recon")

STORE_RECON_SKIP_HOSTS = (
    "play.google.com",
    "apps.apple.com",
    "www.rustore.ru",
    "rustore.ru",
    "appgallery.huawei.com",
)


def _host_of_identifier(identifier: str) -> str:
    raw = identifier.strip()
    if "://" in raw:
        from urllib.parse import urlparse

        return (urlparse(raw).hostname or "").lower()
    return raw.split("/")[0].lstrip("*.").lower()


def should_recon_asset(identifier: str) -> bool:
    """Skip app-store listings that parsers often pull into scope by accident."""
    host = _host_of_identifier(identifier)
    if not host or "." not in host:
        return False
    return not any(host == skip or host.endswith(f".{skip}") for skip in STORE_RECON_SKIP_HOSTS)


def dossier_root(config: AppConfig, slug: str) -> Path:
    return Path(config.data.dossiers_dir) / slug


def ensure_dossier(config: AppConfig, slug: str) -> Path:
    root = dossier_root(config, slug)
    root.mkdir(parents=True, exist_ok=True)
    for name in SUBDIRS:
        (root / name).mkdir(exist_ok=True)
    return root


def dossier_path(config: AppConfig, slug: str, *parts: str) -> Path:
    return dossier_root(config, slug).joinpath(*parts)


def _rel(path: Path) -> str:
    return str(path).replace("\\", "/")


def bind_contract_dossier(config: AppConfig, contract: Contract) -> Contract:
    root = ensure_dossier(config, contract.slug)
    contract.dossier_dir = _rel(root)
    for name, field in (
        ("landscape.md", "landscape_file"),
        ("hunt_plan.md", "hunt_plan_file"),
    ):
        p = root / name
        if p.exists():
            setattr(contract, field, _rel(p))
    return contract


def save_contract_snapshot(config: AppConfig, contract: Contract) -> Path:
    root = ensure_dossier(config, contract.slug)
    path = root / "contract.json"
    payload = {
        "saved_at": datetime.now(UTC).isoformat(),
        "contract": contract.model_dump(mode="json"),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    contract.dossier_dir = _rel(root)
    return path


def save_disclosed_snapshot(
    config: AppConfig, contract: Contract, reports: list[DisclosedReport]
) -> Path:
    root = ensure_dossier(config, contract.slug)
    program_reports = bind_program_reports(contract, reports)
    path = root / "disclosed.json"
    path.write_text(
        json.dumps(
            {
                "saved_at": datetime.now(UTC).isoformat(),
                "program_slug": contract.slug,
                "count": len(program_reports),
                "reports": [r.model_dump(mode="json") for r in program_reports],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def save_surface(config: AppConfig, contract: Contract, surfaces: dict[str, Any]) -> Path:
    path = dossier_path(config, contract.slug, "surface.json")
    path.write_text(json.dumps(surfaces, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def save_finding_snapshot(config: AppConfig, contract: Contract, finding: Finding) -> Path:
    root = ensure_dossier(config, contract.slug)
    path = root / "findings" / f"finding_{finding.id}.json"
    path.write_text(
        json.dumps(finding.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def save_report_artifacts(config: AppConfig, contract: Contract, report: Report, form: dict) -> dict[str, str]:
    root = ensure_dossier(config, contract.slug)
    out_dir = root / "reports"
    out_dir.mkdir(exist_ok=True)

    paths = {
        "markdown": out_dir / f"report_{report.finding_id}.md",
        "form": out_dir / f"standoff_form_{report.finding_id}.json",
        "full": out_dir / f"report_full_{report.finding_id}.json",
    }
    paths["markdown"].write_text(report.body_markdown, encoding="utf-8")
    paths["form"].write_text(json.dumps(form, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["full"].write_text(
        json.dumps(
            {**report.model_dump(mode="json"), "standoff_form": form},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {k: _rel(v) for k, v in paths.items()}


def write_dossier_readme(
    config: AppConfig,
    contract: Contract,
    *,
    stage: str = "",
    session_id: str = "",
) -> Path:
    root = ensure_dossier(config, contract.slug)
    path = root / "README.md"
    stage_line = f"- **Стадия пайплайна:** {stage}\n" if stage else ""
    session_line = f"- **Cursor session:** `{session_id}`\n" if session_id else ""
    content = f"""# Досье — {contract.name} (`{contract.slug}`)

Рабочая папка проекта. Все документы и артефакты hunt/report — здесь.

> **Статус программы:** см. [`STATUS.md`](STATUS.md) (дашборд фаз, блокеры, leads).

## Мета

- **Источник:** {contract.source_url or "—"}
- **Score:** {contract.score if contract.score is not None else "—"}
- **Обновлено досье:** {contract.dossier_refreshed_at or "—"}
{stage_line}{session_line}
## Структура

| Путь | Назначение |
|------|------------|
| `STATUS.md` | **Дашборд статуса** — фазы, блокеры, leads, findings |
| `status.json` | Ручные поля для STATUS (blocker, next_step) |
| `contract.json` | Снимок контракта (scope, rewards, constraints) |
| `disclosed.json` | Disclosed-отчёты по программе |
| `landscape.md` | DO/DON'T ландшафт для решений |
| `hunt_plan.md` | Что / где / как проверять |
| `references.json` / `references.md` | Внешние ссылки из описания |
| `surface.json` | Результат recon (live hosts, endpoints) |
| `auth_accounts.json` / `auth_accounts.md` | Тестовые аккаунты, демо-креды, готовность к auth-hunt |
| `raw/` | Сырой HTML и `__NEXT_DATA__` с Standoff |
| `external_refs/` | Скачанные API docs и прочие ссылки |
| `findings/` | Записанные находки (`cursor finding`) |
| `reports/` | Черновики отчётов Standoff (`cursor report`) |
| `recon/` | Per-asset recon (httpx/katana/nuclei) |

## Workflow

1. Прочитать `hunt_plan.md` и `landscape.md`
2. Изучить `raw/page_props.json` и `external_refs/`
3. Сверить `surface.json` с live-целями
4. Hunt → `python -m pipeline cursor finding --file <json>`
5. Validate → report → `python -m pipeline cursor report --file <json>`

Перед auth-hunt: прочитать `auth_accounts.md` (демо-креды / блокеры captcha).

## Scope

"""
    if contract.scope:
        content += "\n".join(f"- `{host}`" for host in contract.scope)
    else:
        content += "- _не распознан — см. raw/_"
    content += "\n"
    path.write_text(content, encoding="utf-8")
    return path


def write_workspace_pointer(config: AppConfig, contract: Contract) -> Path:
    """Link dossier to engagement workspace under engagements/. Do not overwrite existing."""
    root = ensure_dossier(config, contract.slug)
    path = root / "WORKSPACE.md"
    if path.exists():
        return path
    engagements = Path(config.data.engagements_dir)
    if not engagements.is_absolute():
        root_repo = Path(__file__).resolve().parents[2]
        engagements = root_repo / engagements
    hunt_runtime = engagements / contract.slug
    platform = contract.platform or "standoff365"
    content = (
        f"# Hunt workspace — {contract.name}\n\n"
        f"**Портфель:** `{_rel(root)}`  \n"
        f"**Hunt runtime:** `{_rel(hunt_runtime)}`\n\n"
        f"Evidence и brain — в hunt-workspace. Scaffold: `/new {platform} {contract.slug}`.\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def write_hunt_bootstrap(config: AppConfig, contract: Contract, *, recon_note: str = "") -> None:
    """Create hunt phase/leads stubs if missing so STATUS.md can show recon done."""
    root = ensure_dossier(config, contract.slug)
    hunt = root / "hunt"
    hunt.mkdir(exist_ok=True)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    note = recon_note or f"`build_dossier.py {contract.slug}`"
    phases_path = hunt / "00-pipeline-phases.md"
    if not phases_path.exists():
        phases_path.write_text(
            f"# Pipeline phases — {contract.name} (`{contract.slug}`)\n\n"
            "| Фаза | Статус | Примечание |\n"
            "|------|--------|------------|\n"
            f"| SELECT | done | {today} |\n"
            f"| RECON | done | {note} |\n"
            "| HUNT | — | не начат |\n"
            "| VALIDATE | — | |\n"
            "| REPORT | — | |\n"
            "| SUBMIT | — | |\n",
            encoding="utf-8",
        )
    leads_path = hunt / "03-leads.md"
    if not leads_path.exists():
        hosts = "\n".join(f"- `{h}`" for h in contract.scope[:12]) or "- _см. hunt_plan.md_"
        leads_path.write_text(
            f"# Hunt leads — {contract.name} (не findings)\n\n"
            "Leads появятся после первой hunt-сессии. Стартовая поверхность:\n\n"
            f"{hosts}\n",
            encoding="utf-8",
        )
    status_path = root / "status.json"
    payload: dict[str, Any] = {}
    if status_path.exists():
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
    payload.setdefault("kanban_column", "recon")
    payload.setdefault("overall", "not_started")
    payload.setdefault("overall_label", "Досье собрано, hunt не начат")
    payload.setdefault("next_step", "Run Phase 2 hunt per hunt_plan.md (/new, /sync, /hunt)")
    phases = payload.setdefault("phases", {})
    phases.setdefault("select", "done")
    phases.setdefault("recon", "done")
    notes = payload.setdefault("phase_notes", {})
    notes.setdefault("select", today)
    notes.setdefault("recon", note)
    status_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def init_selected_dossier(
    config: AppConfig,
    contract: Contract,
    reports: list[DisclosedReport] | None = None,
    *,
    stage: str = "",
    session_id: str = "",
) -> Contract:
    """Create dossier folder on human select — before full RECON refresh."""
    from portfolio.discovery.disclosed_runner import load_disclosed_reports

    contract = bind_contract_dossier(config, contract)
    save_contract_snapshot(config, contract)
    report_list = reports if reports is not None else load_disclosed_reports(config)
    save_disclosed_snapshot(config, contract, report_list)
    write_dossier_readme(config, contract, stage=stage, session_id=session_id)
    from portfolio.discovery.dossier_status import write_dossier_status

    write_dossier_status(config, contract.slug)
    logger.info("dossier_initialized", slug=contract.slug, dir=contract.dossier_dir)
    return contract


def finalize_recon_dossier(
    config: AppConfig,
    contract: Contract,
    surfaces: dict[str, Any],
    reports: list[DisclosedReport] | None = None,
    *,
    stage: str = "hunt",
    session_id: str = "",
) -> Contract:
    """Persist recon outputs and refresh dossier index after RECON."""
    from portfolio.discovery.disclosed_runner import load_disclosed_reports

    contract = bind_contract_dossier(config, contract)
    save_contract_snapshot(config, contract)
    report_list = reports if reports is not None else load_disclosed_reports(config)
    save_disclosed_snapshot(config, contract, report_list)
    save_surface(config, contract, surfaces)
    write_dossier_readme(config, contract, stage=stage, session_id=session_id)
    from portfolio.discovery.dossier_status import write_dossier_status

    write_dossier_status(config, contract.slug)
    return contract


def dossier_layout(config: AppConfig, slug: str) -> dict[str, str | None]:
    """Map of dossier paths for agent context."""
    root = dossier_root(config, slug)

    def _p(name: str) -> str | None:
        path = root / name
        return _rel(path) if path.exists() else None

    return {
        "root": _rel(root) if root.exists() else _rel(root),
        "readme": _p("README.md"),
        "status": _p("STATUS.md"),
        "status_json": _p("status.json"),
        "contract": _p("contract.json"),
        "disclosed": _p("disclosed.json"),
        "landscape": _p("landscape.md"),
        "hunt_plan": _p("hunt_plan.md"),
        "references_json": _p("references.json"),
        "references_md": _p("references.md"),
        "surface": _p("surface.json"),
        "auth_accounts_json": _p("auth_accounts.json"),
        "auth_accounts_md": _p("auth_accounts.md"),
        "raw": _rel(root / "raw") if (root / "raw").exists() else None,
        "external_refs": _rel(root / "external_refs") if (root / "external_refs").exists() else None,
        "findings": _rel(root / "findings") if (root / "findings").exists() else None,
        "reports": _rel(root / "reports") if (root / "reports").exists() else None,
    }


def save_session_pointer(config: AppConfig, slug: str, session_data: dict[str, Any]) -> Path:
    path = dossier_path(config, slug, "cursor-session.json")
    path.write_text(json.dumps(session_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
