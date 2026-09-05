# Contributing — Cursor-only fork

## Source of truth

| What | Where |
|------|--------|
| Subagents (50) | `.cursor/agents/*.md` — edit directly |
| Commands (/hunt, …) | `.cursor/skills/cmd-*/SKILL.md` |
| Methodology skills | `skills/` → copied into `.cursor/skills/pentest-agents-*/` |
| Rules | `rules/` → `.cursor/rules/pentest-agents-*.mdc` (sync manually or via script) |
| MCP | `.cursor/mcp.json` |
| Brain runtime | `brain/` (gitignored in workspaces) |
| Tools | `tools/` |

**Do not** maintain `.claude/` — it is not used by Cursor.

## After editing agents or commands

Edit files in `.cursor/` directly. No render step.

If you change `rules/` or top-level `skills/`, update matching `.cursor/rules/` and `.cursor/skills/pentest-agents-*` copies.

## Scaffold

```bash
uv run python3 tools/scaffold.py hackerone tesla
```

Copies `.cursor/`, `tools/`, `rules/`, `skills/`, MCP servers into a bounty workspace.

## Tests

```bash
PYTHONPATH=. uv run --with pytest python -m pytest tests -q
```
