# Cursor pipeline layout

Everything Cursor needs lives under `.cursor/` in the repo root.

## Subagents

`.cursor/agents/<name>.md` — 50 specialists. Cursor loads these automatically.

Dispatch: ask Agent to use the Task tool, or describe the task — Cursor matches `description` in frontmatter.

## Commands

`.cursor/skills/cmd-<name>/SKILL.md` — orchestration workflows (`/hunt`, `/validate`, `/autopilot`, …).

Invoke by name or natural language; Cursor injects the skill body as context.

## Rules

`.cursor/rules/pentest-agents-*.mdc` — derived from `rules/*.md`.

## MCP

`.cursor/mcp.json` — configure in Cursor Settings → MCP if not auto-detected.

## Brain (runtime)

`brain/` — created by scaffold in bounty workspaces; not in git.

```bash
uv run python3 tools/brain.py brief <target>
```

## Scaffold a bounty workspace

```bash
uv run python3 tools/scaffold.py hackerone tesla
cd ~/bounties/hackerone-tesla
# Open in Cursor → subagents + skills + MCP ready
```
