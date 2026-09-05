# Hunt Progression Ladder

**What this is:** a **session progression** checklist — not a payload/WAF ladder (`waf-bypass-protocol.md`, `payloads.md`). It answers: *given current access, what approaches exist to keep testing without spinning?*

**What this is not:** a substitute for vuln-class hunting rules. Run it when **access or role** is the bottleneck.

---

## When to invoke (analysis hooks)

Run the ladder **proactively** at these moments — not only when the user says "we're stuck":

| Moment | Action |
|--------|--------|
| **`/status`**, **`/resume`**, session start on dossier | Read `auth_accounts.md`, `04-auth-setup.md`, open-loops; flag missing roles before picking vuln class |
| **After auth probe fails** (401, captcha, registration error) | §1→§5 + record `evidence/.../NN-access-blocker.json` |
| **Before declaring "authz untestable"** | Confirm §2 (tenant mining) and §5 (parallel track) ran on **current** role |
| **`/analyze`**, triage of blockers | Classify: fixable pivot vs structural prerequisite vs platform escalation (§7) |
| **20-minute rotation** (Rule 12) | If stuck on same account path → next § step, not same login |
| **Session wrap / memo-session** | Update open-loops; if §7 criteria met → draft platform request for human submit |

**Agent contract:** Log attempts in brain (`recon-progression-<target>`) or `hunt/evidence/`. Ask the user only after §1–§6 are documented — except captcha pass (immediate human step).

---

## Rule P0: Stuck = rotate approach, not repeat

| Anti-pattern | Do instead |
|--------------|------------|
| Retry same login 3× | Next §1 pivot or §2 mine tenant |
| "Can't test without role B" | §5 parallel on role A; §7 if role B structurally unreachable |
| UI failed once | §3 API replay from network tab |
| Vendor support during active hunt | §7 platform comment (Standoff), not sales chat |

---

## §1 Identity & session pivots

When the **wrong role** or **no session**:

1. **Refresh JWT** from live browser profile (disk session files go stale after logout).
2. **Accounts in dossier** — manager / contractor / admin / user B; triager grants in `auth_accounts.md`.
3. **UI role switch ≠ impersonation** — same `user_id`, different `platform_role` in client storage is not another person's account.
4. **Entry path** — invite/join URL vs self-registration vs SSO vs magic link; each binds different tenant context.
5. **Browser profile matrix** — automation profile with live session vs clean profile vs CDP; sessions are not shared.
6. **Auth header shape** — cookie vs `x-api-token` vs Bearer; probe once per target.
7. **Unauth surface** — public registration info, discovery docs (scope only).

**Soft human gates:** captcha, OTP → user passes once; agent captures token. Continue §2–§5 while waiting.

---

## §2 Cabinet intelligence (post-access)

**When to run:** immediately after **first successful login** or token capture — **before** picking a vuln class. This is the main way to learn an unknown platform; not only a fallback when the second role is blocked.

Goal: build a **tenant map** (IDs, roles, objects, gaps) from what the cabinet already shows.

### 2.1 Session capture (5 min)

1. Save JWT/session → dossier `04-auth-session.json` (probe `GET /users/current`, company context).
2. Record: `user_id`, `company_id`, `platform_role`, auth header name.
3. Browser network tab: note base API host and recurring path prefixes.

### 2.2 UI cabinet walk (parallel with API)

Walk every sidebar section once; do not deep-hunt yet — **inventory**:

| Capture | Why |
|---------|-----|
| Menu sections enabled/disabled | Feature surface per role |
| Lists with filters (invites, users, tasks, docs, billing) | Export/filter API in network tab |
| Objects with numeric IDs in URL or table | IDOR candidates later |
| Other users' names/phones in shared sandbox | Cross-hunter artifacts |
| Actions greyed out vs available | Permission drift vs API |
| Balance, limits, nominal account | Crown jewels / money path |

Save screenshot or `innerText` snippets only if needed; prefer API evidence.

### 2.3 API inventory from the live session

Mirror UI with list endpoints (from network tab or JS):

1. **Permissions / capabilities** — what this role cannot do (`multi_pay: false` → hunt elsewhere or need owner).
2. **Filter endpoints** — `POST .../filter`, pagination, summary fields (e.g. negative totals = prior hunters' data).
3. **GET by ID** from list rows — task, invite, contractor, document; note `actions[]` on each object.
4. **Embedded tokens** — `file_url?token=`, signed links; scope for IDOR read tests.
5. **History / audit** — `.../history`, events on entities.
6. **Company profile** — members list, roles, nominal account (who is owner vs manager).

Export exercised endpoints from the browser network log to `recon/traffic-exercised.json` (list of URLs or `{"endpoint": "...", "request_count": N}`). Feed into surface ranking:

```bash
uv run python3 tools/intel_engine.py rank-surface \
  --endpoints-file recon/endpoints.txt \
  --traffic-file recon/traffic-exercised.json \
  --output ATTACK_SURFACE_RANKING.md
```

Write `hunt/07-shared-sandbox-intel.md` or `evidence/cabinet/01-tenant-inventory.json`.

### 2.3.1 Field BVA (from UI-walk)

After §2.2–2.3, capture boundary-value probes per form field. Limits from 422/400 responses, HTML `maxlength`, API schema, pagination meta.

| Field | Endpoint | Type | Limits known | BVA probes |
|-------|----------|------|--------------|------------|
| (example) page | GET /api/items | numeric | max=100 from 422 | 0, -1, 99, 100, 101 |
| (example) name | POST /api/profile | text | maxlength=255 | empty, 1 char, max, max+1, unicode flood |

| Type | Standard probes |
|------|-----------------|
| text / textarea | empty, 1 char, max, max+1, special chars, unicode/emoji |
| numeric | non-numeric, 0, -1, min-1, max+1, string coercion `"5"` |
| date range | start > end, boundary inclusive/exclusive, timezone edge |
| file | wrong MIME, empty, oversize (policy-safe) |
| pagination | page 0, last, last+1, size=0 |

Append table to `hunt/07-shared-sandbox-intel.md` under `## Field BVA`. Generate hints via `tools/boundary_probe.py`. Feed rows into `signal_fuzz build-corpus`.

### 2.4 Traffic-informed ranking

Export exercised endpoints from the browser network log to `recon/traffic-exercised.json`:

```json
[
  {"endpoint": "https://api.target.com/v1/users", "request_count": 12, "observed_in_ui": true}
]
```

Pass to surface ranking:

```bash
uv run python3 tools/intel_engine.py rank-surface \
  --endpoints-file recon/endpoints.txt \
  --traffic-file recon/traffic-exercised.json \
  --output ATTACK_SURFACE_RANKING.md
```

### 2.4 Turn inventory into hunt plan (10 min)

From cabinet data, tag each item:

| Tag | Next step |
|-----|-----------|
| **P1 object** | IDOR/BAC on GET/PATCH with sibling IDs from list |
| **Transition gap** | `actions: []` but state suggests next step → need other role (§1/§4) |
| **Permission gap** | UI hidden but API might accept → Rule 26 browser/API parity |
| **Foreign artifact** | Another hunter's task/user → differential only; note in intel |
| **Money path** | pay, sign, acts, limits → business-logic priority |

Update brain: `recon-cabinet-<target>` with section list + key IDs.

### 2.5 When second role is still missing

§2 is **not** idle work — it feeds §5 (company-side) and §7 (Standoff request: "we already tested X on manager; need contractor for Y").

### Cold-start Konsol (example)

With only manager access, cabinet analysis would surface early:

- Shared sandbox «Багбаунти», balance 10M, demo invites list
- Tasks `7040162` / `7040263` (other hunters), workflow states
- Permissions: `pay: false` on manager → do not waste time on multi_pay
- Invites API field names before UI invite mistakes (+7700 country)
- Contractor on task but accept needs contractor JWT → §4/§7, not PATCH spam

---

## §3 API-first when UI is slow or blocked

1. Replay UI requests from network tab (field names in JSON often differ from form labels).
2. **Sibling Rule** on state transitions discovered in JS.
3. **Differential pairs** + GET read-back (Rule 23).
4. Writable objects: PATCH invites, tasks, profiles — validate persistence.
5. Tokens embedded in list responses (document URLs, signed links) — IDOR only if in scope.

---

## §4 Registration & onboarding (general approach)

When the **needed role does not exist** and self-service registration is blocked or incomplete:

### 4.1 Map prerequisites (read errors, don't brute)

Document **why** registration stops — this drives §5 vs §7:

| Blocker class | Examples | Typical pivot |
|---------------|----------|---------------|
| Legal status | self-employed (СМЗ), IE, LLC, tax registry | Cannot fix in UI; §7 or alternate role |
| KYC / government | FNS, "Мой налог", bank binding | Demo bypass vs real gate |
| Invite-only | no public signup; join link required | Manager creates invite (§4.2) |
| Phone/email rules | format, country, disposable blocked | Fix input; API may differ from UI |
| Captcha / OTP | SmartCaptcha, SMS, vendor demo-code | Human once; API needs token |
| Role already exists | "phone already invited" | Reuse sandbox user (§4.3) |

Capture: HTTP status, error body, UI message → `evidence/.../registration-blocker.json`.

### 4.2 Create path via existing privileged session

If **any** higher role works:

1. Map create-user flows: invite API, admin panel, bulk import, SCIM (if in scope).
2. **Discover required fields** from 4xx responses — treat validation messages as API spec; compare UI payload vs API (missing renamed fields is common).
3. Prefer **invite/join chain** over bare `/login` when product is B2B (company binding).
4. Record successful create body in evidence for reproducibility.

### 4.3 Reuse before create

1. List existing users in tenant (filters, invites, demo accounts in dossier).
2. Shared sandbox: use **already onboarded** test identities instead of new registration.
3. Distinguish "login as demo user X" from "impersonate user X" (admin features vary).

### 4.4 API registration surface

Probe (scope-safe): `GET /registration`, cancel/restart join, step endpoints, fiscal/tax status — map state machine without completing real KYC if blocked.

**Stop §4** when prerequisite is **structural** (real СМЗ, real company, unreleased demo-code) → §5 parallel + §7 platform request.

---

## §5 Parallel track while blocked

| Blocked on | Continue with (current access) |
|------------|--------------------------------|
| Second role JWT | First role: IDOR, logic, tenant mining, unauth |
| Sign/pay demo gate | PATCH, permissions, workflow on writable states |
| Captcha | API + §2 without new session |
| Region hardened | Other region hosts (Rule 30) |

---

## §6 Escalation to human (operational)

After §1–§5 logged:

- User passed captcha / pasted OTP → agent saves session file.
- User submits platform request (§7) — agent drafts, human posts.

Open-loop template:

```
[TARGET] ACCESS BLOCKED: <structural gate>
Tried: §1 … §5 (evidence: <path>)
Parallel: <what still runs>
Next: §7 draft ready / waiting triager
```

---

## §7 Platform escalation — test accounts (Standoff365)

When **self-service cannot yield required role(s)** after §4 — e.g. СМЗ/company required, invite-only + undeliverable OTP, demo-code only via vendor manager, second role impossible in shared sandbox:

### Criteria (all should be true)

1. §1–§5 documented with evidence paths.
2. Scope allows the missing tests (authz / IDOR / billing).
3. Program rules mention test accounts **by agreement** OR unauth phase is exhausted with summary.
4. **Not** contacting vendor support/chat during active hunt if program forbids it — use **platform report comments** instead.

### What to file

**Not a vulnerability report.** File a **preliminary progress / access request** report:

1. Short recon summary (scope, `X-Bug-Bounty` header, rate limits respected).
2. What was tested without the missing role.
3. **Blocker paragraph** — factual: what registration step fails and why (СМЗ, captcha+undelivered OTP, etc.).
4. **Explicit table** of requested accounts (role, purpose, ideally same tenant).
5. Ask triager to reply **in report comments**.

### Where templates live (this repository)

| Artifact | Path |
|----------|------|
| Process canon | `memory/wiki/standoff-account-access-request.md` |
| Example paste | `data/dossiers/<slug>/reports/submit/standoff365-preliminary-progress-paste.md` |
| Program feedback | `data/dossiers/<slug>/program-feedback.md` |
| Agent drafts | `data/dossiers/<slug>/reports/preliminary-progress-report.md` |

Human gate: **submit** on Standoff — agent prepares paste only.

### After triager responds

- Update `auth_accounts.md`, `program-feedback.md`, open-loops.
- Re-run `/resume` — do not repeat §7 unless new role still missing.

---

## Quick checklist

```
[ ] Invoked at status/resume/auth-fail?
[ ] §1 identity pivots exhausted?
[ ] §2 tenant mined on current role?
[ ] §4 prerequisites classified (fixable vs structural)?
[ ] §5 parallel track active?
[ ] Blocker evidence file written?
[ ] §7 draft if structural — human submit pending?
```

---

## Appendix: Konsol mapping (2026-08-05)

Target-specific detail only — do not generalize from this table.

| Approach | Outcome |
|----------|---------|
| Preliminary Standoff report | Manager UZ +79116675727 granted |
| Mine tenant | Tasks 7040162, shared demo contractors |
| Invite API (manager) | New demo invite OK |
| Join + self-reg | Captcha + demo-code (structural) |
| UI switch-to-contractor | Same user_id, not invitee |
| Company-side without contractor | Transitions need contractor accept |

Dossier: `data/dossiers/<slug>/hunt/07-shared-sandbox-intel.md`.
