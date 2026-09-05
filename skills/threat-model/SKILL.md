# Threat model methodology

Build a threat model **before** the first hunt dispatch on a new target.

## Artifact locations

| File | Purpose |
|------|---------|
| `brain/threat-model/<slug>.md` | Human-readable model |
| `brain/threat-model/<slug>.json` | Machine input for intel_engine / focus_areas |
| `brain/focus-areas/<slug>.json` | Partitioned hunt slices |

## CLI

```bash
uv run python3 tools/threat_model.py status example.com
uv run python3 tools/focus_areas.py generate --target example.com --endpoints recon/endpoints.txt
```

## Integration

- `/pipeline` Phase 3.5 — auto-run if stale (>7 days)
- `/hunt` Phase 1 — mandatory read
- `/autopilot` SETUP — mandatory read before surface probe
- `intel_engine classes` — boosts from `ranked_threat_classes`

## Distinction

| Threat | Vulnerability |
|--------|---------------|
| "Attacker abuses OAuth redirect" | "`/callback` open redirect on line 42" |
| Survives patching | Fixed when line patched |

Rank threats, hunt vulnerabilities.
