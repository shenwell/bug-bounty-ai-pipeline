---
name: hunt-ssrf
description: >-
  Hunting skill for Server-Side Request Forgery. Covers blind/full SSRF, cloud
  metadata (AWS/GCP/Azure), internal service pivot, Gopher/redis, DNS rebinding,
  and open-redirect chains. DNS-only callback alone is never-submit — require
  data exfil or internal access proof. Use with ssrf-hunter agent.
sources: hackerone_public, intigriti, bugcrowd, nvd_verified
generated_at: 2026-08-06
---

## Crown Jewel Targets

1. **Cloud metadata → IAM credentials** — `169.254.169.254` (AWS), `metadata.google.internal` (GCP), Azure IMDS. Chain to S3/console access. Pays critical when role has `s3:ListBucket` or secrets.
2. **Internal admin panels** — SSRF to `localhost:8080/admin`, Redis (`6379`), Elasticsearch (`9200`), Kubernetes API (`6443`).
3. **PDF/image renderers** — Headless Chrome, wkhtmltopdf, Gotenberg — URL param on report/export features.
4. **Webhook / import URL** — Slack/Teams integrations, "fetch from URL" importers.
5. **OAuth token endpoints via SSRF** — rare but high impact when SSRF reaches internal auth services.

## Attack Surface Signals

```bash
rg -ni '(webhook|callback|fetch|import|preview|url|avatar|screenshot|pdf|unfurl|proxy)' --type js --type py
rg -ni 'https?://.*\$\{|new URL\(|requests\.(get|post)\(|httpx?\.|axios\.get' --type py --type js
```

Parameter names: `url`, `uri`, `link`, `src`, `dest`, `redirect`, `callback`, `webhook`, `feed`, `path`, `file`, `document`, `image`, `target`, `endpoint`, `host`.

## Workflow

### Phase 1: OOB confirmation (mandatory first)

1. Submit collaborator/interactsh URL in every URL-accepting parameter.
2. DNS-only hit = **lead**, not finding. Record and continue.
3. HTTP callback = confirmed outbound SSRF surface.

### Phase 2: Filter mapping

Test in order: `http`, `https`, `file`, `gopher`, `dict`, `ftp`.
IP forms: `127.0.0.1`, `2130706433`, `0x7f000001`, `0177.0.0.1`, `[::1]`, `0.0.0.0`, `127.1`.
Host tricks: `localhost`, `localtest.me`, `spoofed.burpcollaborator.net` (DNS rebinding setup).

### Phase 3: Impact proof (required for report)

| Target | Proof |
|--------|-------|
| AWS metadata | `GET /latest/meta-data/iam/security-credentials/` returns role name + keys |
| GCP | Service account token in metadata response |
| Internal HTTP | Distinct response body/headers vs external probe |
| File | `file:///etc/passwd` content in response (full SSRF) |

Use **differential pairs**: same request with allowed external URL vs blocked internal URL — timing and body length matter for blind SSRF.

### Phase 4: Bypass ladder

Apply `rules/waf-bypass-protocol.md` when blocked. SSRF-specific:
- Open redirect hop: `https://target.com/redirect?url=http://169.254.169.254/`
- URL parser differential: `http://evil@169.254.169.254`, `http://169.254.169.254#@evil.com`
- IPv6 mapped: `http://[::ffff:169.254.169.254]/`
- Double encoding: `%32%31%37...`

### Phase 5: Chain anchors (mandatory on PASS)

From `rules/chain-table.md` — SSRF capability → cloud creds, internal admin, Redis RCE (Gopher), OAuth token theft.

Minimum 3 chain attempts or 20 minutes before atomic submit.

## When to escalate to `cloud-misconfig`

| Signal | Owner class |
|--------|-------------|
| SSRF required to reach metadata | **ssrf** (primary) |
| Public S3 bucket / open GCP bucket without SSRF | **cloud-misconfig** |
| SSRF + leaked keys used on cloud API | Chain in report |

## Kill Signals

- DNS-only callback, no HTTP, no timing oracle, no follow-up data → **KILL** (never-submit alone)
- All URL params validated with strict allowlist and no redirect follow → document evidence
- `file://` blocked and no alternative protocol → continue matrix before exhausted

## Anti-Targets

- SSRF to external internet only (returns same as curl from your machine) — no internal access
- Metadata endpoint returns 401 without IMDSv2 token when instance requires token — try `PUT` hop or alternate headers per AWS IMDSv2
- Reporting "could access metadata" without redacted credential proof

## References

- Payloads: `rules/payloads.md` SSRF + Cloud Metadata sections
- ACS audit-only: `skills/hunt-ssrf/references/acs-sources.md`
