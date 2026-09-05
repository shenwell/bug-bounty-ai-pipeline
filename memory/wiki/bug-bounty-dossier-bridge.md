# Portfolio dossier ↔ hunt engagement (single repo)

How Phase 1 (portfolio) and Phase 2 (hunt) connect in this repository.

## Separation

| | Phase 1 — Portfolio | Phase 2 — Hunt |
|--|---------------------|----------------|
| **Purpose** | Discover, score, build dossier | `/hunt`, `/autopilot`, brain, evidence |
| **Skill** | `/portfolio` | `/hunt`, `/autopilot`, `/new`, `/sync` |
| **CLI** | `tools/portfolio.py` | `brain`, `autopilot_gate`, `scaffold` |
| **Data** | `data/dossiers/<slug>/` | `engagements/<slug>/` |

## Hunt runtime flow

1. Dossier ready: `data/dossiers/<slug>/contract.json` (after `/portfolio build`).
2. Create or update engagement workspace:
   ```bash
   /new <platform> <slug>
   # uv run python tools/scaffold.py <platform> <slug> --dir engagements/<slug>
   ```
3. Scaffold seeds from dossier: `hunt_plan.md`, `landscape.md`, `hunt/03-leads.md`, `scope.yaml`.
4. Precondition before hunt:
   ```bash
   uv run python tools/dossier_precondition.py <slug>
   ```
5. `/sync` → `/autopilot` or `/hunt`.
6. After session — sync back to dossier:
   ```bash
   uv run python tools/dossier_sync_from_engagement.py <slug>
   uv run python tools/portfolio.py status <slug>
   ```

## Where artifacts live

**Engagement workspace only:** `evidence/`, `brain/`, session JSON under `hunt/`, `recon/traffic-exercised.json`.

**Dossier only:** `contract.json`, `STATUS.md`, `reports/submit/`, `leads/<id>/`, `surface.json`.

Path hint also written to `data/dossiers/<slug>/WORKSPACE.md` when the dossier is built.

## Wiki

- [standoff-account-access-request.md](standoff-account-access-request.md) — §7 progress report template (Standoff365)
