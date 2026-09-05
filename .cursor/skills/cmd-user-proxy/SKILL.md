---
name: user-proxy
description: "Build and refresh researcher persona from past Cursor dialogues; simulate hunter decisions when agents stop. Usage: /user-proxy init|ingest|brief|feedback \"text\"|decisions. Auto-runs via subagentStop/stop hooks."
---

Researcher persona proxy: $ARGUMENTS

The **user-proxy** role simulates your hunting decisions using `brain/persona/` (built from agent transcripts + explicit feedback). It fires automatically on every **subagentStop** and **stop** via `.cursor/hooks.json`.

## Quick commands

```bash
# First-time setup
uv run python3 tools/user_persona.py init
uv run python3 tools/user_persona.py ingest --max-files 100

# Inspect persona
uv run python3 tools/user_persona.py brief

# Record a correction from chat (updates future proxy decisions)
uv run python3 tools/user_persona.py record-feedback "не останавливайся на WAF 403" --kind correction

# Audit hook triggers
uv run python3 tools/user_persona.py decisions --limit 30
```

## When it runs automatically

1. Any **Task subagent** completes → `subagentStop` hook → `brain/persona/user-proxy-pending.md` + `followup_message` to orchestrator
2. Main agent **stop** → same hook (`loop_limit: 3` on session end)

Orchestrator (`/hunt`, `/autopilot`) must then:

1. Read `brain/persona/user-proxy-pending.md`
2. Apply `.cursor/agents/user-proxy.md` (or dispatch `user-proxy` agent for full simulation)
3. Emit `USER_PROXY_DECISION` before next hunter dispatch

## Manual full simulation

When you want a dedicated subagent pass (not just hook follow-up):

```
Dispatch user-proxy agent (model: inherit) with:
- stopped_agent: <name>
- target: <target>
- last_output_summary: <paste>
Instruction: output USER_PROXY_DECISION per agent file.
```

## Persona sources

| Source | Path |
|--------|------|
| Structured profile | `brain/persona/profile.json` |
| Voice samples | `brain/persona/corpus.md` |
| Hook log | `brain/persona/decisions.jsonl` |
| Pending brief | `brain/persona/user-proxy-pending.md` |
| Schema reference | `rules/user-persona.md` |

## Refresh after long sessions

Run at session wrap or when your preferences shift:

```bash
uv run python3 tools/user_persona.py ingest --max-files 150
uv run python3 tools/global_brain.py sync-from-local
```

## Integration points

- `/autopilot` step 23.5 — USER PROXY CHECK after chain-pressure
- `/hunt` — after each hunter return
- `/resume` — read persona brief for priority alignment
- `/status` — show last 3 proxy decisions

## Non-goals

- Does **not** auto-submit reports or git commit (persona hard veto)
- Does **not** replace `/validate` or human `/submit`
- Does **not** read secrets from transcripts (only user-role message text)
