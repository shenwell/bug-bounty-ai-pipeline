---
name: portfolio
description: "Phase 1 — discover, analyze, build portfolio dossiers. Usage: /portfolio discover|build|status|..."
---

Portfolio (Phase 1) — dossier discovery and build. **Do not mix with `/hunt` or `/autopilot`.**

Parse: `/portfolio <subcommand> [args]`

## Subcommands

| Command | CLI |
|---------|-----|
| `/portfolio discover [--platform standoff365\|bizone]` | `uv run python tools/portfolio.py discover --platform …` |
| `/portfolio candidates` | `uv run python tools/portfolio.py candidates` |
| `/portfolio analyze <slug>` | `uv run python tools/portfolio.py analyze <slug>` |
| `/portfolio select <slug>` | `uv run python tools/portfolio.py select <slug>` |
| `/portfolio build <slug> [--skip-recon] [--platform …]` | `uv run python tools/portfolio.py build <slug> …` |
| `/portfolio refresh <slug>` | `uv run python tools/portfolio.py refresh <slug>` |
| `/portfolio status [slug]` | `uv run python tools/portfolio.py status [slug]` |
| `/portfolio record finding\|report <slug> --file …` | `uv run python tools/portfolio.py record …` |
| `/portfolio monitor [--platform …]` | optional new-program alerts |

Config: `config/portfolio.yaml` (copy from `config/portfolio.yaml.example`) · Data: `data/dossiers/<slug>/`

## Human gates

- **SELECT:** show `candidates` — operator picks slug; agent does not auto-select paid target.
- **is_paid=false** or explicit no-pay → skip (never-submit).
- Read **all** `tab_sections` in contract, not only description.
- Check `disclosed.json` / `known_findings` — do not duplicate disclosed vectors.

## After dossier ready (Phase 2)

1. `/new <platform> <slug>` — scaffold seeds from `data/dossiers/<slug>/`
2. `/sync` / `/hunt` / `/autopilot` — **never** run portfolio build inside hunt
3. After hunt session: `uv run python tools/dossier_sync_from_engagement.py <slug>`

## Analysis rules (from cursor-pipeline)

1. Goal = paid impact; unpaid programs → skip.
2. Disclosed overlap → hunt_plan must note dup risk.
3. Scope/constraints before any offensive action in Phase 2.
