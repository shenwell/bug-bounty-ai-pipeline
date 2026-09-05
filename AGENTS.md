# bug-bounty-ai-pipeline — Cursor maintenance

Framework for authorized bug bounty work in **Cursor only**.

## Agent memory

**Project:** `MEMORY.md` → `memory/hot-cache.md` → as needed `warm-cache`, `open-loops`, `decisions` → `memory/wiki/`.

Install [memo-session-skill](https://github.com/shenwell/ai-agent-skills) separately — the pipeline reads memory layers but does not install companions.

Optional portfolio memory: set `GLOBAL_MEMORY_ROOT:` in this file to a user-defined path (never a maintainer machine path).

## What matters for the pipeline

```
.cursor/agents/     ← 50 native subagents (Cursor reads these)
.cursor/skills/     ← cmd-* commands + pentest-agents-* methodology
.cursor/rules/      ← always-on hunting rules (.mdc)
.cursor/mcp.json    ← bounty-platforms + writeup-search MCP
portfolio/          ← Phase 1: discover, score, build dossier (NOT hunt)
config/portfolio.yaml
data/dossiers/      ← contract dossiers (Phase 1 output, Phase 2 input)
rules/              ← methodology source (payloads, hunting, hunt-progression-ladder, …)
skills/             ← hunt-rce, hunt-xss, … source bundles
tools/              ← brain.py, scaffold.py, portfolio.py, autopilot_gate.py, …
engagements/        ← per-slug hunt runtime (gitignored)
mcp-*-server/       ← MCP server implementations
```

## Two phases (one repo)

| Phase | Skills | Purpose |
|-------|--------|---------|
| **1 — Portfolio** | `/portfolio` | `discover` → human `select` → `build` → `data/dossiers/<slug>/` |
| **2 — Hunt** | `/hunt`, `/autopilot`, `/new`, `/sync` | Vuln hunting **after** dossier exists; never runs portfolio build |

Precondition for Phase 2: `uv run python tools/dossier_precondition.py <slug>`  
Post-session sync: `uv run python tools/dossier_sync_from_engagement.py <slug>`

Bridge: [memory/wiki/bug-bounty-dossier-bridge.md](memory/wiki/bug-bounty-dossier-bridge.md).

## Verification

```bash
# Portfolio tests (recommended: project venv)
uv venv .venv-portfolio
uv pip install --python .venv-portfolio/Scripts/python.exe -e ".[portfolio,portfolio-board]"
export PYTHONPATH=.
.venv-portfolio/Scripts/python.exe -m pytest tests/test_dossier.py tests/test_discovery.py tests/test_scoring.py -q

# Full suite
PYTHONPATH=. uv run --with pytest python -m pytest tests -q
```
