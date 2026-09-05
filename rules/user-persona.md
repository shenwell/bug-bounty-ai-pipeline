# Researcher persona schema (user-proxy)

Reference for `tools/user_persona.py` and the `user-proxy` agent. The live profile is `brain/persona/profile.json` (per engagement workspace).

## Purpose

Autonomous hunts (`/autopilot --autonomous`, "без human gate") still need researcher-aligned steering: priority order, vetoes, rotation, chain pressure, language. The user-proxy layer encodes that from:

1. **Past Cursor dialogues** — user-role messages in `agent-transcripts/**/*.jsonl`
2. **Explicit feedback** — `user_persona.py record-feedback`
3. **Workspace defaults** — hunting rules and never-submit list (hard vetoes)

## Profile fields

| Field | Meaning |
|-------|---------|
| `language` | Response language for proxy rationale (default `ru`) |
| `autonomy` | `high` or `full` — suppress clarifying questions |
| `human_gate` | If true, proxy may emit `CHECKPOINT` for review points |
| `preferences` | Boolean flags (depth, chain-first, no auto-commit, API-first, …) |
| `priority_signals` | Tags extracted from transcripts (`P1-first`, `idor-priority`, …) |
| `vetoes` | Hard stops the proxy must never override |
| `corpus_samples` | Short user message excerpts for tone matching |
| `feedback` | Timestamped corrections and preferences |

## Verdicts

See `.cursor/agents/user-proxy.md` for the canonical verdict table.

## Hooks

Project hooks in `.cursor/hooks.json`:

- `subagentStop` → prepare pending brief + orchestrator follow-up
- `stop` → same on session end (`loop_limit: 3`)

Hook script: `.cursor/hooks/user_proxy_stop.py` (fail-open).

## Maintenance

```bash
uv run python3 tools/user_persona.py init
uv run python3 tools/user_persona.py ingest --max-files 100
uv run python3 tools/user_persona.py brief
```

Re-run `ingest` after significant hunting sessions so new corrections enter the corpus.
