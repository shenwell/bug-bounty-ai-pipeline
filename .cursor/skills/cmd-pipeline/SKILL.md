---
name: pipeline
description: "Prepare the battlefield — recon, scanning, and surface ranking. Stops before hunting. Run /hunt or /autopilot after. Usage: /pipeline or /pipeline <target>"
---

Prepare the battlefield for: $ARGUMENTS

This command runs recon, scanning, and surface ranking — everything needed BEFORE hunting.
It does NOT hunt, validate, or report. Use `/hunt` or `/autopilot` for that.

## Phase 0: SETUP

1. Read `scope.yaml` — resolve and verify targets
   - If `$ARGUMENTS` is empty: `uv run python3 tools/scope_check.py --list`
   - If `$ARGUMENTS` is a domain: `uv run python3 tools/scope_check.py $ARGUMENTS`
2. Read `policy.md` — extract policy preamble for all agent dispatches
3. Brain init or brief:
   - If no brain exists: `uv run python3 tools/brain.py init`
   - If brain exists: `uv run python3 tools/brain.py brief <target>`

## Phase 1: RECON

4. Dispatch `recon` agent (model: inherit) with policy preamble and scope
5. After recon: dispatch `config-auditor` agent (model: inherit) for header/TLS/cookie review
6. After config: dispatch `js-analyzer` agent (model: inherit) for JavaScript analysis
7. Brain update: `uv run python3 tools/brain.py record <target> recon "<results summary>"`

## Phase 2: SCANNING (parallel, max 3)

8. Dispatch in parallel (all model: inherit, all with policy preamble):
   - `vuln-scanner` agent with nuclei on discovered hosts
   - `waf-profiler` agent on primary targets
9. Brain update with scan results

## Phase 3: RANK

10. Dispatch `recon-ranker` agent (model: inherit) with recon data + brain knowledge
11. Traffic-informed rank (when `recon/traffic-exercised.json` exists):
    ```bash
    uv run python3 tools/traffic_informed.py rank \
      --endpoints-file recon/endpoints.txt \
      --output ATTACK_SURFACE_RANKING.md
    uv run python3 tools/traffic_informed.py expand-siblings --limit 30 > recon/sibling-candidates.json
    ```
12. Output P1/P2/Kill list — **hunters target P1 from traffic-boosted rank first**

## Phase 3.4: CABINET WALK + TRAFFIC (mandatory when auth exists)

When dossier has `auth_accounts.md`, `04-auth-session.json`, or any logged-in account:

1. Browser cabinet walk per `rules/hunt-progression-ladder.md` §2 — every menu section once; capture API mirror from network tab.
2. Export exercised endpoints to `recon/traffic-exercised.json`:
   ```json
   [{"endpoint": "https://api.target.com/v1/users", "request_count": 12, "observed_in_ui": true}]
   ```
3. Validate before rank:
   ```bash
   uv run python3 tools/traffic_informed.py validate --root .
   ```
4. If WAF challenge during walk — dispatch `browser-stealth-agent`, then write `recon/session.json`:
   ```bash
   uv run python3 tools/session_bridge.py write --host <host> --waf-vendor cloudflare \
     --user-agent "<ua>" --cookies-json '[{"name":"cf_clearance","value":"..."}]'
   ```

Skip only with brain entry: `recon-skip:traffic-informed policy:<exact-clause>`.

4. Build fuzz corpus (no run — `/pipeline` stops here; `/hunt` and `/autopilot` run the full layer):
   ```bash
   uv run python3 tools/signal_fuzz.py build-corpus --root .
   ```

## Phase 3.5: THREAT MODEL (mandatory before hunt)

12. Check freshness:
    ```bash
    uv run python3 tools/threat_model.py status <target>
    ```
13. If MISSING or STALE → run `/threat-model <target>` (dispatch `threat-modeler`, then `focus_areas.py generate`)
14. If fresh → read `brain/threat-model/<slug>.md` and `brain/focus-areas/<slug>.json` for hunt planning
15. **AI surface detect** (conditional boost):
    ```bash
    uv run python3 tools/intel_engine.py detect-ai-infra --root . --output recon/ai-infra-detect.json
    ```
    If `ai_surface: true` → prioritize `llm-ai-hunter`, read `rules/mcp-threats.md`

## Complete

```
Battlefield ready.

P1 targets: [list]
P2 targets: [list]
Kill list:  [list]

Next steps:
  /hunt <target>     — manual hunting on a specific target
  /autopilot         — autonomous hunting across all P1 targets
  /surface           — re-rank surface with current brain knowledge
```

Sync brain: `uv run python3 tools/global_brain.py sync-from-local`

## Top-Tier Pipeline Standard

The pipeline prepares a battlefield, not a folder of scan files.

1. Scope first: every generated target must be in-scope or tagged `out-of-scope` with reason.
2. Normalize assets into stable inventories: hosts, endpoints, JS files, APIs, auth flows, cloud buckets, repos, mobile packages, and third-party integrations.
3. Rank during collection. Do not wait until the end to identify crown jewels.
4. Preserve raw evidence and parsed summaries. A hunter should be able to replay the exact source of every target.
5. End with `P1`, `P2`, and `Kill` lists plus the best first vuln class for each P1. If no P1 exists, say why and recommend monitoring or a different program.
