# Differential Oracles — canonical reference (pipeline v4)

Materializes Hunting Rules 25–26 into reusable oracles for hunter dispatch preambles.
A single HTTP 200 is a lead, not a finding. Impact requires a **delta** between controlled pairs.

## Core principle

> Compare request pairs/triples, not single responses.

Every hunter dispatch must declare at least one differential pair and the oracle that decides signal vs noise.

## Standard pairs

| Pair | When to use | Signal |
|------|-------------|--------|
| unauth vs auth | Any protected resource | Status/body/field delta proves auth boundary |
| role A vs role B | BAC, IDOR, PE | Same object ID, different data or actions |
| parser A vs parser B | Injection, mass-assignment | Same semantic payload, different content-type or encoding |
| before vs after mutation | Write endpoints | Independent read-back from separate session confirms persistence |
| own vs other-user ID | IDOR | Cross-tenant field leak, not status-code asymmetry alone |

## §A Security oracle catalog

Per-class pass conditions for `signal_fuzz` export tier `oracle+readback` and hunter witness gates.

| Class | Oracle pass |
|-------|-------------|
| idor / bac | Field delta role-A vs role-B on same `object_id` + independent read-back; skip if roles < 2 |
| sqli | SQL/DB error shape in body vs baseline; payloads filtered by engagement `policy.md` SQL section |
| business-logic | Invariant violation after write + read-back from session C (not status alone) |
| ssrf | Internal/metadata marker in body vs baseline; not single-response string match |
| open-redirect | `Location` / final URL delta vs baseline on redirect parameter |

Single-response detectors (status asymmetry, reflection without execution) are pre-filters only — not export oracle hits.

## §B Workflow Disruption Matrix

Split by executability. Pass only with read-back (Rule 23).

| Axis | Auto `signal_fuzz` (HTTP pair variants) | Hunter-only (browser / multi-client) |
|------|----------------------------------------|--------------------------------------|
| `skip-step` | Omit required prior step in API sequence | — |
| `double-submit` | Repeat POST without idempotency guard | Idempotency-Key rotation (Rule 31 id-collision) |
| `stale-session` | Replay token after logout / role change | — |
| `degraded` | Drop optional headers / partial body | — |
| `back-refresh` | — | business-logic / race-condition + browser MCP |
| `logout-mid-flow` | — | business-logic + browser MCP |
| `parallel-plane` | — | race-condition + two clients / SSE split |

Brain marker (business-logic / race exhaustion v1.5):

```
workflow-disruption:<path> axes:skip-step,double-submit evidence:evidence/<host>/signal-fuzz/attempts.jsonl
```

Preambles mandatory in `.cursor/agents/business-logic.md` and `.cursor/agents/race-condition.md`.

## §C Trace tuple (web greybox species ID)

Used by `tools/fuzzingbook/trace.py` and `signal_fuzz` energy schedule — not security oracles.

```text
trace_key = stable_hash(
  status_class,           # 2xx / 4xx / 5xx bucket
  error_class,            # generic | validation | auth | server | ...
  sorted_json_top_keys,   # top-level JSON keys only
)
```

**Not in trace_key:** latency bucket, sibling path 405, full body hash.

Latency is a separate boolean oracle (2-of-3 repeat). Never export alone (`trace-only` tier, no rank boost).

## Oracle signals (not just status code)

Interesting deltas beyond `200 vs 403`:

- **Body length** shift > 5% with same endpoint
- **JSON field presence** — admin-only keys, PII fields, `role`, `balance`
- **Latency** — blind boolean/time oracle (>500ms skew repeatable)
- **Headers** — `Set-Cookie`, `Location`, `X-Request-Id`, cache keys
- **Downstream effects** — email, webhook, audit log, async callback (OOB)
- **Error shape** — stack trace vs generic 404 (routing reached query layer)

## Anti-patterns (instant kill)

| Trap | Why it fails |
|------|--------------|
| Status asymmetry only | 403 on other-user ≠ leak; need data read-back |
| Mass-assignment 400 vs 406 | Field parsed ≠ persisted; read it back |
| Reflection without execution | Curl reflection ≠ XSS; browser-verify client-side |
| Single payload family | Rule 24: exhaustion needs ≥30 meaningful combinations |

## Hunter preamble template

```
DIFFERENTIAL ORACLE (mandatory):
  Pair: [e.g. role-A vs role-B on GET /api/users/{id}]
  Baseline: [known-benign request + expected marker]
  Exploit:  [mutated request]
  Pass if:  [concrete field/value/timing delta — not status alone]
  Read-back: [independent session confirms state change]
```

## Integration

- `/hunt` Phase 0: read `brain/session-intent/<slug>.json` → `differential_axis` seeds the pair
- `/autopilot` HUNT LOOP step 22c: every hunter prompt includes one pair from this file
- `coverage_record.py`: set `--differential-evidence` only when oracle pass is documented in evidence JSONL

## References

- `rules/hunting.md` Rule 23 (HTTP 200 ≠ impact), Rule 25 (differential testing), Rule 26 (browser + API parity)
- `tools/session_intent.py` — `differential_axis` field
- `tools/witness.py` — programmatic read-back gate
