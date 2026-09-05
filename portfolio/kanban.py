"""Kanban board state for contract dossiers (Trello-style)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from portfolio.common.config import AppConfig
from portfolio.discovery.dossier_status import (
    PHASE_ORDER,
    collect_dossier_status,
    write_all_dossier_statuses,
    write_dossier_status,
    write_portfolio_status,
)
from portfolio.monitor.platforms import MONITOR_PLATFORMS

KANBAN_COLUMNS: list[dict[str, str]] = [
    {
        "id": "new",
        "step": "1",
        "title": "Новые",
        "hint": "Monitor только что нашёл программу на Standoff / BI.ZONE",
        "color": "#ff6bcb",
    },
    {
        "id": "backlog",
        "step": "2",
        "title": "В очереди",
        "hint": "Интересно, но работу ещё не начали",
        "color": "#8b949e",
    },
    {
        "id": "select",
        "step": "3",
        "title": "Выбор цели",
        "hint": "Scope, выплаты, disclosed — брать в работу или нет",
        "color": "#bc8cff",
    },
    {
        "id": "recon",
        "step": "4",
        "title": "Разведка",
        "hint": "Домены, API, auth, hunt_plan",
        "color": "#79c0ff",
    },
    {
        "id": "hunt",
        "step": "5",
        "title": "Поиск багов",
        "hint": "Активное тестирование по leads",
        "color": "#3fb950",
    },
    {
        "id": "validate",
        "step": "6",
        "title": "Проверка",
        "hint": "PoC, impact, adversarial validation",
        "color": "#ffa657",
    },
    {
        "id": "report",
        "step": "7",
        "title": "Отчёт",
        "hint": "Черновик и paste для Standoff",
        "color": "#e3b341",
    },
    {
        "id": "submit",
        "step": "8",
        "title": "На отправку",
        "hint": "Human gate — финальный submit",
        "color": "#ff7b72",
    },
    {
        "id": "blocked",
        "step": "⏸",
        "title": "Заблокировано",
        "hint": "Нет УЗ, scope, backend лежит",
        "color": "#f85149",
    },
    {
        "id": "done",
        "step": "✓",
        "title": "Закрыто",
        "hint": "Отработано или снято с работы",
        "color": "#56d364",
    },
]

COLUMN_IDS = {c["id"] for c in KANBAN_COLUMNS}

COLUMN_DEFAULTS: dict[str, dict[str, Any]] = {
    "new": {"overall": "not_started", "overall_label": "Новая программа"},
    "backlog": {"overall": "not_started", "overall_label": "В очереди"},
    "select": {"overall": "active", "overall_label": "Выбор цели"},
    "recon": {"overall": "active", "overall_label": "Разведка"},
    "hunt": {"overall": "active", "overall_label": "Поиск багов"},
    "validate": {"overall": "active", "overall_label": "Проверка находки"},
    "report": {"overall": "active", "overall_label": "Подготовка отчёта"},
    "submit": {"overall": "waiting_human", "overall_label": "На отправку"},
    "blocked": {"overall": "blocked", "overall_label": "Заблокировано"},
    "done": {"overall": "complete", "overall_label": "Закрыто"},
}

PHASE_FOR_COLUMN = {
    "select": "select",
    "recon": "recon",
    "hunt": "hunt",
    "validate": "validate",
    "report": "report",
    "submit": "submit",
}

PLATFORM_LABELS = {
    "standoff365": "Standoff365",
    "bizone": "BI.ZONE",
}


def board_state_path(config: AppConfig) -> Path:
    return Path(config.data.dossiers_dir) / "portfolio-board.json"


def _load_board_meta(config: AppConfig) -> dict[str, Any]:
    return _read_json(board_state_path(config))


def _save_board_meta(config: AppConfig, meta: dict[str, Any]) -> None:
    meta["updated_at"] = datetime.now(UTC).isoformat()
    _write_json(board_state_path(config), meta)


def add_to_inbox(config: AppConfig, platform: str, slug: str) -> None:
    """Add a newly detected monitor program to the Kanban «Новые» inbox."""
    if slug in _list_dossier_slugs(config):
        return
    cid = card_id(slug, platform)
    meta = _load_board_meta(config)
    inbox: list[str] = list(meta.get("inbox") or [])
    dismissed: set[str] = set(meta.get("dismissed_new") or [])
    if cid not in inbox and cid not in dismissed:
        inbox.append(cid)
        meta["inbox"] = inbox
        _save_board_meta(config, meta)


def add_programs_to_inbox(config: AppConfig, platform: str, programs: list[dict[str, Any]]) -> int:
    added = 0
    for program in programs:
        slug = program.get("slug")
        if not slug:
            continue
        before = _load_board_meta(config).get("inbox") or []
        add_to_inbox(config, platform, slug)
        after = _load_board_meta(config).get("inbox") or []
        if len(after) > len(before):
            added += 1
    return added


def card_id(slug: str, platform: str | None = None) -> str:
    if platform:
        return f"{platform}:{slug}"
    return slug


def parse_card_id(raw: str) -> tuple[str, str | None]:
    if ":" in raw:
        platform, slug = raw.split(":", 1)
        if platform in MONITOR_PLATFORMS:
            return slug, platform
    return raw, None


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _list_dossier_slugs(config: AppConfig) -> set[str]:
    root = Path(config.data.dossiers_dir)
    if not root.is_dir():
        return set()
    return {
        child.name
        for child in root.iterdir()
        if child.is_dir() and (child / "contract.json").exists()
    }


def _collect_monitor_programs(config: AppConfig) -> dict[str, dict[str, Any]]:
    """Programs from monitor state without an existing dossier."""
    dossier_slugs = _list_dossier_slugs(config)
    programs: dict[str, dict[str, Any]] = {}

    for platform_id, platform in MONITOR_PLATFORMS.items():
        state_path = Path(platform.state_file)
        if not state_path.is_absolute():
            root = Path(config.config_path).parent.parent
            state_path = root / state_path
        state = _read_json(state_path)
        for slug, entry in (state.get("programs") or {}).items():
            if slug in dossier_slugs:
                continue
            cid = card_id(slug, platform_id)
            programs[cid] = {
                "id": cid,
                "slug": slug,
                "platform": platform_id,
                "platform_label": PLATFORM_LABELS.get(platform_id, platform_id),
                "name": entry.get("name") or slug,
                "source_url": entry.get("url") or "",
                "first_seen_at": entry.get("first_seen_at") or "",
                "published_at": entry.get("published_at") or "",
                "is_monitor": True,
            }
    return programs


def _infer_column(status: dict[str, Any]) -> str:
    overrides = status.get("_status_json") or {}
    saved = overrides.get("kanban_column")
    if saved in COLUMN_IDS and saved != "new":
        return saved

    overall = status.get("overall", "")
    if overall == "complete":
        return "done"
    if overall == "blocked":
        return "blocked"
    if overall == "waiting_human":
        return "submit"
    if overall == "not_started":
        return "backlog"
    if overall == "paused":
        return "blocked"

    phases = status.get("phases") or {}
    for phase in reversed(PHASE_ORDER):
        entry = phases.get(phase, {})
        raw = str(entry.get("status", "")).lower()
        if raw in ("—", "-", "", "done"):
            continue
        if "done" in raw and "in_progress" not in raw and "blocked" not in raw:
            continue
        if phase in PHASE_FOR_COLUMN:
            return phase
    return "backlog"


def _card_from_status(status: dict[str, Any]) -> dict[str, Any]:
    findings = status.get("findings") or {}
    reports = status.get("reports") or {}
    leads = status.get("leads") or {}
    slug = status["slug"]
    return {
        "id": slug,
        "slug": slug,
        "name": status["name"],
        "score": status.get("score"),
        "overall": status.get("overall"),
        "overall_label": status.get("overall_label"),
        "blocker": status.get("blocker") or "",
        "next_step": status.get("next_step") or "",
        "source_url": status.get("source_url") or "",
        "findings_total": findings.get("total", 0),
        "submit_ready": reports.get("submit_ready", 0),
        "leads_open": leads.get("open", 0) + leads.get("in_progress", 0),
        "session_stage": status.get("session_stage") or "",
        "is_monitor": False,
    }


def _load_status_json(root: Path) -> dict[str, Any]:
    return _read_json(root / "status.json")


def _monitor_card_entry(card: dict[str, Any], column_id: str) -> dict[str, Any]:
    out = dict(card)
    out["column"] = column_id
    return out


def load_board_state(config: AppConfig) -> dict[str, Any]:
    """Build full board JSON from dossiers, monitor inbox, and saved column order."""
    dossier_slugs = _list_dossier_slugs(config)
    monitor_cards = _collect_monitor_programs(config)
    saved = _load_board_meta(config)
    saved_columns: dict[str, list[str]] = saved.get("columns") or {}
    dismissed_new: set[str] = set(saved.get("dismissed_new") or [])
    inbox: list[str] = list(saved.get("inbox") or [])

    cards_by_id: dict[str, dict[str, Any]] = {}
    inferred: dict[str, str] = {}

    for slug in sorted(dossier_slugs):
        root = Path(config.data.dossiers_dir) / slug
        status = collect_dossier_status(root)
        status["_status_json"] = _load_status_json(root)
        cards_by_id[slug] = _card_from_status(status)
        inferred[slug] = _infer_column(status)

    for cid, card in monitor_cards.items():
        cards_by_id[cid] = card

    columns: dict[str, list[dict[str, Any]]] = {c["id"]: [] for c in KANBAN_COLUMNS}
    placed: set[str] = set()

    for col_id, order in saved_columns.items():
        if col_id not in columns:
            continue
        for raw_id in order:
            if raw_id not in cards_by_id or raw_id in placed:
                continue
            card = dict(cards_by_id[raw_id])
            card["column"] = col_id
            columns[col_id].append(card)
            placed.add(raw_id)

    for slug in sorted(dossier_slugs):
        if slug in placed:
            continue
        col_id = inferred[slug]
        card = dict(cards_by_id[slug])
        card["column"] = col_id
        columns[col_id].append(card)
        placed.add(slug)

    for cid, card in monitor_cards.items():
        if cid in placed:
            continue
        if cid in dismissed_new:
            continue
        if cid not in inbox:
            continue
        columns["new"].append(_monitor_card_entry(card, "new"))
        placed.add(cid)

    new_count = len(columns["new"])
    return {
        "columns": KANBAN_COLUMNS,
        "cards": columns,
        "updated_at": saved.get("updated_at") or datetime.now(UTC).isoformat(),
        "total": len(dossier_slugs),
        "new_count": new_count,
        "monitor_count": len(monitor_cards),
    }


def _phase_overrides_for_column(column_id: str) -> dict[str, str]:
    if column_id not in PHASE_FOR_COLUMN:
        return {}
    active_phase = PHASE_FOR_COLUMN[column_id]
    overrides: dict[str, str] = {}
    for phase in PHASE_ORDER:
        idx = PHASE_ORDER.index(phase)
        active_idx = PHASE_ORDER.index(active_phase)
        if idx < active_idx:
            overrides[phase] = "done"
        elif phase == active_phase:
            overrides[phase] = "in_progress"
    return overrides


def _is_monitor_card(config: AppConfig, cid: str) -> bool:
    return cid in _collect_monitor_programs(config)


def _update_dossier_for_column(config: AppConfig, slug: str, column_id: str) -> None:
    root = Path(config.data.dossiers_dir) / slug
    status_path = root / "status.json"
    status_data = _read_json(status_path)
    defaults = COLUMN_DEFAULTS[column_id]
    status_data["kanban_column"] = column_id
    status_data["overall"] = defaults["overall"]
    status_data["overall_label"] = defaults["overall_label"]

    phase_overrides = _phase_overrides_for_column(column_id)
    if phase_overrides:
        status_data["phases"] = phase_overrides
    elif column_id == "done":
        status_data["phases"] = {p: "done" for p in PHASE_ORDER}
    elif column_id in ("backlog", "new"):
        status_data.pop("phases", None)

    if column_id == "blocked" and not status_data.get("blocker"):
        status_data.setdefault("blocker", "Перемещено на колонку «Блокер»")
    if column_id != "blocked" and status_data.get("blocker") == "Перемещено на колонку «Блокер»":
        status_data.pop("blocker", None)

    _write_json(status_path, status_data)
    write_dossier_status(config, slug)
    write_portfolio_status(config)


def move_card(
    config: AppConfig,
    *,
    slug: str,
    column_id: str,
    position: int = -1,
    platform: str | None = None,
    card_id_override: str | None = None,
    refresh_status_md: bool = True,
) -> dict[str, Any]:
    """Move a contract card to a column and persist order + status.json."""
    if column_id not in COLUMN_IDS:
        raise ValueError(f"Unknown column: {column_id}")

    cid = card_id_override or card_id(slug, platform)
    _, card_platform = parse_card_id(cid)
    dossier_slugs = _list_dossier_slugs(config)
    has_dossier = card_platform is None and slug in dossier_slugs

    if has_dossier:
        root = Path(config.data.dossiers_dir) / slug
        if not (root / "contract.json").exists():
            raise FileNotFoundError(f"Dossier not found: {slug}")
    elif column_id not in ("new", "backlog", "select", "done") and not has_dossier:
        raise ValueError(
            f"Программа «{slug}» без досье — сначала переместите в Бэклог или SELECT, "
            "затем соберите досье: python scripts/build_dossier.py <slug>"
        )

    board = load_board_state(config)
    saved = _load_board_meta(config)
    dismissed_new: list[str] = list(saved.get("dismissed_new") or [])
    inbox: list[str] = list(saved.get("inbox") or [])

    new_columns: dict[str, list[str]] = {}
    for col in KANBAN_COLUMNS:
        col_cid = col["id"]
        new_columns[col_cid] = [
            c["id"] for c in board["cards"].get(col_cid, []) if c["id"] != cid
        ]

    target = new_columns[column_id]
    insert_at = len(target) if position < 0 else min(max(0, position), len(target))
    target.insert(insert_at, cid)

    if column_id != "new" and _is_monitor_card(config, cid):
        if cid not in dismissed_new:
            dismissed_new.append(cid)
        if cid in inbox:
            inbox = [x for x in inbox if x != cid]
    elif column_id == "new":
        if cid in dismissed_new:
            dismissed_new = [x for x in dismissed_new if x != cid]
        if cid not in inbox and _is_monitor_card(config, cid):
            inbox.append(cid)

    board_payload: dict[str, Any] = {
        "columns": new_columns,
        "dismissed_new": dismissed_new,
        "inbox": inbox,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _write_json(board_state_path(config), board_payload)

    if has_dossier and refresh_status_md:
        _update_dossier_for_column(config, slug, column_id)

    return load_board_state(config)


def sync_board_from_dossiers(config: AppConfig) -> dict[str, Any]:
    """Rebuild board order from inferred columns; refresh monitor «new» column."""
    board = load_board_state(config)
    saved = _load_board_meta(config)
    new_columns: dict[str, list[str]] = {c["id"]: [] for c in KANBAN_COLUMNS}
    for col in KANBAN_COLUMNS:
        cid = col["id"]
        new_columns[cid] = [c["id"] for c in board["cards"].get(cid, [])]

    payload = {
        "columns": new_columns,
        "dismissed_new": saved.get("dismissed_new") or [],
        "inbox": saved.get("inbox") or [],
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _write_json(board_state_path(config), payload)
    write_all_dossier_statuses(config)
    return load_board_state(config)
