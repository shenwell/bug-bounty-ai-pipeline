"""STATUS.md dashboard for contract dossiers."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from portfolio.common.config import AppConfig
from portfolio.discovery.dossier import dossier_root

PHASE_ORDER = ("select", "recon", "hunt", "validate", "report", "submit")
PHASE_LABELS = {
    "select": "SELECT",
    "recon": "RECON",
    "hunt": "HUNT",
    "validate": "VALIDATE",
    "report": "REPORT",
    "submit": "SUBMIT",
}

OVERALL_ICONS = {
    "active": "🟢",
    "blocked": "🟡",
    "waiting_human": "👤",
    "paused": "⏸️",
    "complete": "✅",
    "not_started": "⚪",
}

STATUS_ICONS = {
    "done": "✅",
    "complete": "✅",
    "in_progress": "🔄",
    "blocked": "🟡",
    "draft": "📝",
    "draft_ready": "📝",
    "waiting_human": "👤",
    "paused": "⏸️",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _parse_phases_table(text: str) -> dict[str, dict[str, str]]:
    phases: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not line.startswith("|") or line.startswith("|------") or "Фаза" in line:
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) < 2:
            continue
        key = parts[0].strip().lower()
        if key not in PHASE_ORDER:
            continue
        phases[key] = {"status": parts[1], "note": parts[2] if len(parts) > 2 else ""}
    return phases


def _count_leads(text: str) -> dict[str, int]:
    counts = {"total": 0, "open": 0, "in_progress": 0, "closed": 0, "deferred": 0}
    blocks = re.split(r"^## LEAD-", text, flags=re.MULTILINE)
    for block in blocks[1:]:
        counts["total"] += 1
        match = re.search(r"\| Статус \| \*\*([^*]+)\*\*", block) or re.search(
            r"\| Статус \| ([^\n|]+)", block
        )
        status = (match.group(1) if match else "").lower()
        if any(x in status for x in ("закрыт", "closed", "kill", "n/a", "exhausted")):
            counts["closed"] += 1
        elif "in progress" in status or "в работе" in status:
            counts["in_progress"] += 1
        elif "defer" in status:
            counts["deferred"] += 1
        elif "open" in status:
            counts["open"] += 1
    return counts


def _count_findings(findings_dir: Path) -> dict[str, int]:
    counts = {"total": 0, "verified": 0, "other": 0}
    if not findings_dir.is_dir():
        return counts
    for path in findings_dir.glob("finding_*.json"):
        counts["total"] += 1
        data = _read_json(path) or {}
        status = str(data.get("status", "")).lower()
        if status in ("verified", "in_review", "submitted"):
            counts["verified"] += 1
        else:
            counts["other"] += 1
    return counts


def _count_reports(reports_dir: Path) -> dict[str, int]:
    counts = {"drafts": 0, "submit_ready": 0}
    if not reports_dir.is_dir():
        return counts
    counts["drafts"] = len(list(reports_dir.glob("report_*.md")))
    submit_dir = reports_dir / "submit"
    if submit_dir.is_dir():
        counts["submit_ready"] = len(list(submit_dir.glob("*-paste.md")))
    return counts


def _strip_md(text: str) -> str:
    return re.sub(r"\*\*([^*]+)\*\*", r"\1", text).replace("`", "").strip()


def _status_icon(raw: str) -> str:
    normalized = _strip_md(raw).lower()
    for key, icon in STATUS_ICONS.items():
        if key in normalized:
            return icon
    if normalized in ("—", "-", ""):
        return "—"
    return "•"


def _infer_overall(
    phases: dict[str, dict[str, str]],
    *,
    blocker: str = "",
    session_status: str = "",
) -> tuple[str, str]:
    if blocker:
        return "blocked", blocker

    flat = " ".join(p.get("status", "") for p in phases.values()).lower()
    if "waiting_human" in flat or "human gate" in flat:
        return "waiting_human", "Ожидает действия человека"
    if "blocked" in flat:
        return "blocked", "Есть блокер — см. таблицу фаз"
    if session_status == "waiting_human":
        return "waiting_human", "Ожидает действия человека"
    if session_status == "blocked":
        return "blocked", "Сессия заблокирована"
    if session_status == "complete":
        return "complete", "Пайплайн завершён"

    hunt = phases.get("hunt", {}).get("status", "").lower()
    if hunt and "done" not in hunt and hunt not in ("—", "-"):
        return "active", "Hunt в работе"
    if phases.get("recon", {}).get("status", "").lower() in ("in_progress", "🔄"):
        return "active", "Recon в работе"
    if not phases:
        return "not_started", "Досье создано, hunt не начат"
    return "active", "В работе"


def collect_dossier_status(root: Path) -> dict[str, Any]:
    """Aggregate status from dossier artifacts."""
    slug = root.name
    overrides = _read_json(root / "status.json") or {}

    contract_payload = _read_json(root / "contract.json") or {}
    contract = contract_payload.get("contract") or {}
    session = _read_json(root / "cursor-session.json") or {}
    auth_accounts = _read_json(root / "auth_accounts.json") or {}

    phases: dict[str, dict[str, str]] = {}
    phases_path = root / "hunt" / "00-pipeline-phases.md"
    if phases_path.exists():
        phases = _parse_phases_table(phases_path.read_text(encoding="utf-8"))

    override_phases = overrides.get("phases") or {}
    override_notes = overrides.get("phase_notes") or {}
    for phase in PHASE_ORDER:
        if phase in override_phases:
            entry = phases.setdefault(phase, {"status": "—", "note": ""})
            entry["status"] = override_phases[phase]
        if phase in override_notes:
            phases.setdefault(phase, {"status": "—", "note": ""})["note"] = override_notes[phase]

    if not phases and session.get("stage"):
        stage = str(session["stage"]).lower()
        for phase in PHASE_ORDER:
            if phase == stage:
                phases[phase] = {"status": "in_progress", "note": ""}
            elif PHASE_ORDER.index(phase) < PHASE_ORDER.index(stage):
                phases[phase] = {"status": "done", "note": ""}

    leads_path = root / "hunt" / "03-leads.md"
    leads = _count_leads(leads_path.read_text(encoding="utf-8")) if leads_path.exists() else {}

    findings = _count_findings(root / "findings")
    reports = _count_reports(root / "reports")

    blocker = overrides.get("blocker", "")
    next_step = overrides.get("next_step", "")
    overall = overrides.get("overall", "")
    overall_label = overrides.get("overall_label", "")

    if not overall or not overall_label:
        inferred, inferred_label = _infer_overall(
            phases,
            blocker=blocker,
            session_status=str(session.get("status", "")),
        )
        overall = overall or inferred
        overall_label = overall_label or inferred_label

    links: list[str] = []
    for name, label in (
        ("hunt_plan.md", "hunt_plan"),
        ("landscape.md", "landscape"),
        ("hunt/03-leads.md", "leads"),
        ("hunt/00-pipeline-phases.md", "phases"),
        ("program-feedback.md", "feedback"),
        ("auth_accounts.md", "auth"),
    ):
        if (root / name).exists():
            links.append(f"[{label}]({name})")

    return {
        "slug": slug,
        "name": contract.get("name") or slug,
        "generated_at": datetime.now(UTC).isoformat(),
        "score": contract.get("score"),
        "source_url": contract.get("source_url") or "",
        "dossier_refreshed_at": contract.get("dossier_refreshed_at") or contract_payload.get("saved_at"),
        "session_id": session.get("session_id", ""),
        "session_stage": session.get("stage", ""),
        "session_status": session.get("status", ""),
        "overall": overall,
        "overall_label": overall_label,
        "blocker": blocker,
        "next_step": next_step,
        "phases": phases,
        "leads": leads,
        "findings": findings,
        "reports": reports,
        "auth_status": (auth_accounts.get("summary") or {}).get("status", ""),
        "links": links,
        "has_hunt": (root / "hunt").is_dir(),
        "has_program_feedback": (root / "program-feedback.md").exists(),
    }


def render_status_md(status: dict[str, Any]) -> str:
    icon = OVERALL_ICONS.get(status["overall"], "•")
    lines = [
        f"# Статус — {status['name']} (`{status['slug']}`)",
        "",
        f"**Обновлено:** {status['generated_at'][:10]}  ",
        f"**Сводка:** {icon} **{status['overall_label']}**",
        "",
    ]

    if status.get("blocker"):
        lines.append(f"> **Блокер:** {status['blocker']}")
        lines.append("")
    if status.get("next_step"):
        lines.append(f"> **Следующий шаг:** {status['next_step']}")
        lines.append("")

    lines.extend(["## Пайплайн", "", "| Фаза | Статус | Примечание |", "|------|--------|------------|"])
    for phase in PHASE_ORDER:
        entry = status["phases"].get(phase, {})
        raw_status = entry.get("status", "—")
        note = entry.get("note", "")
        stripped = _strip_md(raw_status)
        if stripped in ("—", "-", ""):
            cell = "—"
        else:
            icon = _status_icon(raw_status)
            cell = f"{icon} {stripped}" if icon not in ("•", "—") else stripped
        lines.append(f"| {PHASE_LABELS[phase]} | {cell} | {note} |")
    lines.append("")

    lines.extend(["## Счётчики", ""])
    findings = status.get("findings") or {}
    leads = status.get("leads") or {}
    reports = status.get("reports") or {}
    lines.append(f"- **Findings:** {findings.get('total', 0)} всего"
                 f" ({findings.get('verified', 0)} verified/in_review)")
    if leads:
        lines.append(
            f"- **Leads:** {leads.get('total', 0)} всего — "
            f"{leads.get('in_progress', 0)} in progress, "
            f"{leads.get('open', 0)} open, "
            f"{leads.get('closed', 0)} closed"
        )
    lines.append(
        f"- **Reports:** {reports.get('drafts', 0)} черновиков, "
        f"{reports.get('submit_ready', 0)} paste для submit"
    )
    if status.get("auth_status"):
        lines.append(f"- **Auth accounts:** `{status['auth_status']}`")

    meta_bits = []
    if status.get("score") is not None:
        meta_bits.append(f"score {status['score']}")
    if status.get("session_id"):
        meta_bits.append(f"session `{status['session_id']}`")
    if status.get("dossier_refreshed_at"):
        meta_bits.append(f"досье {str(status['dossier_refreshed_at'])[:10]}")
    if meta_bits:
        lines.extend(["", f"_{' · '.join(meta_bits)}_"])

    if status.get("links"):
        lines.extend(["", "## Быстрые ссылки", "", " · ".join(status["links"])])

    lines.extend(
        [
            "",
            "---",
            "_Автообновление: `python -m pipeline cursor dossier-status "
            f"{status['slug']}` · ручные поля: `status.json`_",
        ]
    )
    return "\n".join(lines) + "\n"


def render_portfolio_md(statuses: list[dict[str, Any]]) -> str:
    generated = datetime.now(UTC).isoformat()[:10]
    lines = [
        "# Портфель программ",
        "",
        f"**Обновлено:** {generated}  ",
        f"**Программ:** {len(statuses)}",
        "",
        "| Программа | Статус | Фаза | Блокер / следующий шаг | F | Submit |",
        "|-----------|--------|------|------------------------|---|--------|",
    ]

    for status in sorted(statuses, key=lambda s: s["slug"].lower()):
        icon = OVERALL_ICONS.get(status["overall"], "•")
        slug = status["slug"]
        name = status["name"]
        link = f"[{name}]({slug}/STATUS.md)"

        phase = _current_phase(status)
        blocker = status.get("blocker") or status.get("next_step") or "—"
        if len(blocker) > 80:
            blocker = blocker[:77] + "..."

        findings = (status.get("findings") or {}).get("total", 0)
        submit = (status.get("reports") or {}).get("submit_ready", 0)

        lines.append(
            f"| {link} (`{slug}`) | {icon} {status['overall_label']} | {phase} | {blocker} | {findings} | {submit} |"
        )

    lines.extend(
        [
            "",
            "## По программам",
            "",
        ]
    )
    for status in sorted(statuses, key=lambda s: s["slug"].lower()):
        icon = OVERALL_ICONS.get(status["overall"], "•")
        slug = status["slug"]
        lines.append(f"- {icon} **[{status['name']}]({slug}/STATUS.md)** (`{slug}`) — {status['overall_label']}")
        if status.get("blocker"):
            lines.append(f"  - Блокер: {status['blocker']}")
        if status.get("next_step"):
            lines.append(f"  - Далее: {status['next_step']}")

    lines.extend(
        [
            "",
            "---",
            "_Автообновление: `python -m pipeline cursor dossier-status`_",
        ]
    )
    return "\n".join(lines) + "\n"


def _current_phase(status: dict[str, Any]) -> str:
    if status.get("overall") == "complete":
        return "COMPLETE"
    phases = status.get("phases") or {}
    for phase in reversed(PHASE_ORDER):
        entry = phases.get(phase, {})
        raw = _strip_md(entry.get("status", "")).lower()
        if raw in ("—", "-", "", "done"):
            continue
        if "done" in raw and "in_progress" not in raw:
            continue
        return PHASE_LABELS[phase]
    if status.get("session_stage"):
        return str(status["session_stage"]).upper()
    return "—"


def write_portfolio_status(config: AppConfig) -> Path:
    root_dir = Path(config.data.dossiers_dir)
    statuses: list[dict[str, Any]] = []
    if root_dir.is_dir():
        for child in sorted(root_dir.iterdir()):
            if child.is_dir() and (child / "contract.json").exists():
                statuses.append(collect_dossier_status(child))
    path = root_dir / "STATUS.md"
    path.write_text(render_portfolio_md(statuses), encoding="utf-8")
    return path


def write_dossier_status(config: AppConfig, slug: str) -> Path:
    root = dossier_root(config, slug)
    if not root.exists():
        raise FileNotFoundError(f"Dossier not found: {root}")
    status = collect_dossier_status(root)
    path = root / "STATUS.md"
    path.write_text(render_status_md(status), encoding="utf-8")
    return path


def write_all_dossier_statuses(config: AppConfig) -> list[Path]:
    root_dir = Path(config.data.dossiers_dir)
    paths: list[Path] = []
    if not root_dir.is_dir():
        return paths
    for child in sorted(root_dir.iterdir()):
        if child.is_dir() and (child / "contract.json").exists():
            paths.append(write_dossier_status(config, child.name))
    paths.append(write_portfolio_status(config))
    return paths
