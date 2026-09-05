---
name: hunt-graphql
description: >-
  Hunting skill for GraphQL security — auth bypass on mutations, IDOR via node(),
  field-level authorization gaps, batching abuse, alias-based rate-limit bypass.
  Introspection alone is never-submit. Use with graphql-audit agent.
sources: hackerone_public, intigriti, github_advisories
generated_at: 2026-08-06
---

## Crown Jewel Targets

1. **Mutation IDOR** — change `id` / `certificationId` / `nodeId` in mutations (H1 $12,500 pattern).
2. **Field-level authz** — `organization { projects { webhooks { secret } } }` returns data UI hides.
3. **Unauthenticated sensitive queries** — `user(username:"admin")` without auth header.
4. **Batching / alias abuse** — 50 mutations in one HTTP request bypassing per-op rate limits.
5. **Persisted queries / APQ** — weak hash allowlist → arbitrary query execution.

## Attack Surface Signals

```bash
rg -ni '/graphql|graphiql|/api/gql|apollo' .
rg -ni '__schema|__type|node\(|mutation |subscription ' --type js --type ts
```

Paths: `/graphql`, `/api/graphql`, `/v1/graphql`, `/query`, GraphiQL UI.

## Workflow

### Phase 1: Recon (introspection = lead only)

```json
{"query":"{ __schema { queryType { name } mutationType { name } } }"}
```

If introspection works → map mutations with `id`/`userId`/`orgId` args. **Do not report introspection alone.**

### Phase 2: Auth differential

For each mutation/query:
- Request as User A with User B's object ID
- Request without `Authorization`
- Compare: status, errors array, `data` presence, field count

### Phase 3: Field-level pivot

Start from `viewer` / `me` / `currentUser`. Walk nested fields:
`viewer { organization { members { email role } } }`
Toggle IDs in `node(id: "base64")` — classic IDOR.

### Phase 4: Batching

```json
[
  {"query":"mutation { deleteItem(id:1) { ok } }"},
  {"query":"mutation { deleteItem(id:2) { ok } }"}
]
```

### Phase 5: Read-back

Every write mutation: independent GET/list from **second session** confirms persistence (Rule 23).

## Chain anchors

GraphQL IDOR → token/secret fields → OAuth redirect → ATO. See `rules/chain-table.md`.

Cross-dispatch `idor-hunter` when REST and GraphQL share object IDs.

## Kill Signals

- Introspection disabled + no auth bypass on known mutations from JS bundle
- All mutations return `UNAUTHENTICATED` without token — test with valid low-priv token
- `node()` global ID is opaque and server validates ownership on all tested IDs

## Anti-Targets

- GraphQL introspection enabled in staging only
- Query depth limit blocks nested pivot — document limit before exhausted
- Duplicate of REST IDOR on same object — merge findings

## References

- `rules/payloads.md` GraphQL sections
- `skills/hunt-idor/SKILL.md` for BOLA patterns on `node()`
- ACS: `skills/hunt-graphql/references/acs-sources.md`
