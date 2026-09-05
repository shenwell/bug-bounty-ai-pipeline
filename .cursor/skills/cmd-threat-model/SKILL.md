---
name: threat-model
description: "Build threat model before hunting. Assets, trust boundaries, ranked threat classes, focus-area slices. Usage: /threat-model target.com"
---

Threat model for: $ARGUMENTS

## Phase 0: Setup

1. Read `scope.yaml` — verify target in scope: `uv run python3 tools/scope_check.py <target>`
2. Read `policy.md` — extract constraints for agent preamble
3. `uv run python3 tools/brain.py brief <target>`
4. Ensure recon exists (`recon/endpoints.txt` or run `/pipeline` first)

## Phase 1: Freshness check

```bash
uv run python3 tools/threat_model.py status <target>
```

If MISSING or STALE: true → continue. If fresh and not `--force`, show status and stop.

## Phase 2: Dispatch threat-modeler

Dispatch `threat-modeler` agent (model: inherit) with policy preamble and:

- Target: parsed from $ARGUMENTS
- Paths to read: scope, policy, hacktivity, recon, brain, ATTACK_SURFACE_RANKING.md
- Output paths: `brain/threat-model/<slug>.md` and `.json`

## Phase 3: Focus areas

After agent returns:

```bash
uv run python3 tools/focus_areas.py generate \
  --target <target> \
  --endpoints recon/endpoints.txt \
  --threat-model brain/threat-model/<slug>.md
```

## Complete

```
Threat model ready.

Artifacts:
  brain/threat-model/<slug>.md
  brain/threat-model/<slug>.json
  brain/focus-areas/<slug>.json

Next:
  /hunt <target>
  /autopilot <target> --waves 2
```
