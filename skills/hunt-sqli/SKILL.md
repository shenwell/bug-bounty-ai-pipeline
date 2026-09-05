---
name: hunt-sqli
description: >-
  Hunting skill for SQL injection — error/boolean/time/union/OOB and second-order
  across query, JSON, GraphQL variables, cookies, headers. Requires read-back proof.
  Use with sqli-hunter agent.
generated_at: 2026-08-06
---

## Crown Jewel Targets

1. **Auth/login SQLi** — bypass authentication or extract password hashes.
2. **Search/filter endpoints** — reflected in JSON APIs (`?q=`, `filter=`, `sort=`).
3. **Second-order** — stored username/comment rendered in admin query later.
4. **GraphQL variables** — `variables.id` passed to raw SQL backend.
5. **ORDER BY / LIMIT injection** — less WAF coverage than WHERE clauses.

## Workflow

### Phase 1: Context map

For each parameter test: query string, JSON field, form, cookie, `X-*` header, GraphQL `variables`.

### Phase 2: Probe ladder

1. `'`, `"`, `\`, `;`, `--`, `#`, `')`
2. `' OR '1'='1` / `' AND '1'='2` differential
3. Time: `SLEEP(5)` / `pg_sleep(5)` / `WAITFOR DELAY`
4. Union: `' UNION SELECT NULL,NULL--` increment columns
5. OOB: `LOAD_FILE`, `xp_dirtree`, `UTL_HTTP` if in scope policy

### Phase 3: WAF exhaustion

Minimum 25 combinations per `intel_engine.py matrix sqli`. Apply `rules/waf-bypass-protocol.md` before declaring blocked.

### Phase 4: sqlmap (confirmed only)

```bash
sqlmap -u 'URL' -p param --batch --risk=1 --level=3 --technique=BEUSTQ
```

Manual PoC still required for report narrative.

## Kill Signals

- Parameterized queries with no string concat in source (SAST) + no oracle after full matrix
- ORM-only surface with typed IDs (int coercion blocks quotes)
- Single 500 without boolean/time confirmation

## Chain anchors

SQLi read → credential table → session forge → ATO. SQLi write → admin flag → PE.

## References

- `rules/payloads.md` SQLi section
- `skills/hunt-sqli/references/acs-sources.md`
