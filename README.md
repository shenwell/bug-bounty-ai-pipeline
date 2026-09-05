```
╔════════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                        ║
║ ██████╗██╗   ██╗ ██████╗      ██████╗ ██████╗██╗   ██╗███╗   ██╗████████╗██╗   ██╗     ║
║ ██╔══██╗██║   ██║██╔════╝      ██╔══██╗██╔═══██╗██║   ██║████╗  ██║╚══██╔══╝╚██╗ ██╔╝  ║
║ ██████╔╝██║   ██║██║  ███╗      ██████╔╝██║   ██║██║   ██║██╔██╗ ██║   ██║ ╚████╔╝     ║
║ ██╔══██╗██║   ██║██║   ██║      ██╔══██╗██║   ██║██║   ██║██║╚██╗██║   ██║  ╚██╔╝      ║
║ ██████╔╝╚██████╔╝╚██████╔╝      ██████╔╝╚██████╔╝╚██████╔╝██║ ╚████║   ██║   ██║       ║
║ ╚═════╝ ╚═════╝ ╚═════╝      ╚═════╝ ╚═════╝ ╚═════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝             ║
║                                                                                        ║
║ ██████╗ ██╗██████╗ ███████╗██╗     ██╗███╗   ██╗███████╗                               ║
║ ██╔══██╗██║██╔══██╗██╔════╝██║     ██║████╗  ██║██╔════╝                               ║
║ ██████╔╝██║██████╔╝█████╗  ██║     ██║██╔██╗ ██║█████╗                                 ║
║ ██╔═══╝ ██║██╔═══╝ ██╔══╝  ██║     ██║██║╚██╗██║██╔══╝                                 ║
║ ██║     ██║██║     ███████╗███████╗██║██║ ╚████║███████╗                               ║
║ ╚═╝     ╚═╝╚═╝     ╚══════╝╚══════╝╚═╝╚═╝  ╚═══╝╚══════╝                               ║
║                                                                                        ║
║        Two-phase bug bounty pipeline for Cursor — dossiers to hunt / submit            ║
║          Cursor · memo-session-skill · goal-mode · interceptor                         ║
║       /portfolio · /new · /sync · /hunt · /autopilot · /validate · MIT                 ║
║     git clone https://github.com/shenwell/bug-bounty-ai-pipeline                       ║
║                                                                                        ║
╚════════════════════════════════════════════════════════════════════════════════════════╝
```

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Cursor](https://img.shields.io/badge/Cursor-native-000000)](https://cursor.com/)
[![MCP servers ×2](https://img.shields.io/badge/MCP-servers%20%C3%97%202-2ea043)](#mcp-servers)

# Bug Bounty AI Pipeline

Two-phase bug bounty framework for **Cursor** — portfolio dossiers (Phase 1) and autonomous hunting (Phase 2).

---

Public pipeline skeleton for **Cursor**: 50 native subagents, 26 command skills, portfolio discovery, dossier build, hunt/autopilot loops, 7-Question Gate validation, exploit chain building, brain state, and two MCP servers (bug-bounty platforms + BYO writeup search).

**This repo ships the framework only.** Runtime data (`data/dossiers/`, `engagements/`, agent memory) stays local and gitignored.

## Install

```bash
git clone https://github.com/shenwell/bug-bounty-ai-pipeline
cd bug-bounty-ai-pipeline
./install.sh          # Linux/macOS — checks Python 3.10+ and uv
# or
./install.ps1         # Windows
```

Open the folder in **Cursor** — subagents, skills, rules, and MCP config live under `.cursor/`.

| Asset | Location |
|-------|----------|
| **Subagents (50)** | `.cursor/agents/<name>.md` |
| **Commands (26)** | `.cursor/skills/cmd-<name>/SKILL.md` |
| **Methodology (14+)** | `.cursor/skills/pentest-agents-<name>/` |
| **Rules** | `.cursor/rules/pentest-agents-*.mdc` |
| **MCP** | `.cursor/mcp.json` |

### Update

```bash
git pull
./install.sh    # or install.ps1 — refreshes config examples if missing
```

Re-run scaffold on an **existing engagement** to refresh framework files (preserves `scope.yaml`, findings, brain, custom `AGENTS.md` notes):

```bash
uv run python3 tools/scaffold.py <platform> <program>
```

## Quick start — Phase 2 (hunt)

For a standalone bounty workspace outside this repo:

```bash
export HACKERONE_USERNAME=you HACKERONE_TOKEN=your_token
uv run python3 tools/scaffold.py hackerone tesla
cd ~/bounties/hackerone-tesla
# Open in Cursor, then:
/sync hackerone tesla
/brain init && /status
/hunt tesla.com
```

## Two-phase workflow (this repo)

```
Phase 1 — Portfolio:  /portfolio discover → candidates → /portfolio select <slug> → /portfolio build <slug>
Phase 2 — Hunt:       /new <platform> <slug> → /sync → /brain init → /analyze → /surface → /hunt | /autopilot
After finding:        /validate → /chain → /report → /dupcheck → /submit → /learn
Returning:            /resume <target> → /hunt or /autopilot
```

Copy `config/portfolio.yaml.example` → `config/portfolio.yaml` and
`config/.env.portfolio.example` → `config/.env.portfolio` before Phase 1.

### Human gates (operator decisions)

| Step | Gate |
|------|------|
| `/portfolio candidates` | **You** pick the slug — agent never auto-selects a paid target |
| Unpaid / no-pay programs | Skip (never-submit policy) |
| `/portfolio build` | Agent reads full contract tabs, disclosed findings, scope constraints |
| `/new` | Warn if program needs mobile device, OAuth app, sandbox tenant, etc. |
| `/submit` | **You** submit on the platform — agent prepares paste + evidence package |

See [AGENTS.md](AGENTS.md) and [memory/wiki/bug-bounty-dossier-bridge.md](memory/wiki/bug-bounty-dossier-bridge.md).

## First run checklist

Before your first `/portfolio` or `/hunt` session, prepare:

1. **Python 3.10+** and **[uv](https://docs.astral.sh/uv/)** (`install.sh` / `install.ps1` verify both).
2. **Platform credentials** in env (see `config/.env.portfolio.example` and MCP `forwardEnv` in `.cursor/mcp.json`).
3. **`config/portfolio.yaml`** — copy from example; set platforms, scoring, data dirs.
4. **Optional: memo-session-skill** — persistent memory across sessions (see Works with below).
5. **Phase 1:** `/portfolio discover` → review candidates → `/portfolio select <slug>` → `/portfolio build <slug>`.
6. **Phase 2:** `/new <platform> <slug>` when dossier exists → `/sync` → `/hunt` or `/autopilot`.

If you use **memo-session-skill**, its preflight will ask consent before changing `.gitignore` for memory paths, verify `GLOBAL_MEMORY_ROOT` in `AGENTS.md`, and bootstrap `MEMORY.md` / `memory/` scaffold on first run.

## MCP servers

### bounty-platforms

HackerOne, Bugcrowd, Intigriti, Immunefi, YesWeHack + stubs. Launched via:

```json
"command": "uv",
"args": ["run", "--with", "mcp", "mcp-bounty-server/server.py"]
```

Set platform tokens in your environment (see `.cursor/mcp.json` `forwardEnv`).

### writeup-search (BYO index)

Semantic/keyword search over **your** writeup corpus. Ships with local fallback to `rules/payloads.md`.

Build an index with [`rag-builder/`](rag-builder/) (always dry-run until `--execute`).

## Works with (optional companions)

Installed **separately** via [skills.sh](https://skills.sh) — this pipeline does not install them for you.

| Skill | Install | Role |
|-------|---------|------|
| **memo-session-skill** | `npx skills add shenwell/ai-agent-skills --skill memo-session-skill -g -a cursor -y` | Persistent memory: `MEMORY.md`, `memory/` HOT/WARM/COLD, wiki — pipeline reads this |
| **memo-session-mcp** | See [ai-agent-skills memo-session-mcp](https://github.com/shenwell/ai-agent-skills/tree/main/skills/memo-session-mcp) | Optional FTS search over portfolio + project memory |
| **goal-mode** | `npx skills add shenwell/ai-agent-skills --skill goal-mode -g -a cursor -y` | Optional checkpoints for long `/hunt` / `/autopilot` runs |
| **interceptor** / **interceptor-browser** | Install from your interceptor skill repo | Optional authenticated browser verification |

Recommended pair for long hunts:

```bash
npx skills add shenwell/ai-agent-skills --skill memo-session-skill -g -a cursor -y
npx skills add shenwell/ai-agent-skills --skill goal-mode -g -a cursor -y
```

## Tests

```bash
PYTHONPATH=. uv run --with pytest python -m pytest tests -q
```

Portfolio subset:

```bash
PYTHONPATH=. uv run --with pytest python -m pytest tests/test_dossier.py tests/test_discovery.py tests/test_scoring.py -q
```

## Runtime directories (gitignored)

| Path | Purpose |
|------|---------|
| `data/` | Portfolio output — see [data/README.md](data/README.md) |
| `engagements/` | Per-program hunt runtime — see [engagements/README.md](engagements/README.md) |
| `MEMORY.md`, most of `memory/` | Agent session memory (memo-session-skill) |
| `brain/`, `evidence/`, `recon/` | Hunt artifacts inside engagements |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Edit `.cursor/` directly — no render step.

## License

[MIT](LICENSE) — Copyright (c) 2026 shenwell
