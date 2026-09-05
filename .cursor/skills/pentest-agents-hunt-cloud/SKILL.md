---
name: hunt-cloud
description: >-
  Hunting skill for cloud misconfiguration — public S3/GCP/Azure buckets, IAM
  overpermission, K8s RBAC gaps. Audit-only; no destructive writes. Distinct from
  SSRF-to-metadata (see hunt-ssrf). Use with cloud-hunter agent.
generated_at: 2026-08-06
---

## Scope boundary vs ssrf-hunter

| cloud-misconfig | ssrf |
|-----------------|------|
| Direct public bucket/blob URL | SSRF reaches metadata/internal |
| IAM policy readable anonymously | Gopher/redis via SSRF |
| K8s API exposed with weak auth | Open redirect hop to internal |

## Crown Jewel Targets

1. **Public S3 list + sensitive objects** — backups, `.env`, credentials JSON.
2. **Anonymous write bucket** — poison static assets → XSS/supply chain.
3. **GCP/Azure public containers** — same patterns as S3.
4. **Exposed Elasticsearch/Mongo/Redis** — no auth on cloud IP.
5. **Leaked CI artifacts** in public buckets — tokens, kubeconfig.

## Workflow (read-only)

### S3
```bash
curl -sI "https://{bucket}.s3.amazonaws.com/"
aws s3 ls s3://{bucket} --no-sign-request 2>/dev/null
```

### GCP
```bash
curl -s "https://storage.googleapis.com/{bucket}/"
```

### Azure
```bash
curl -s "https://{account}.blob.core.windows.net/{container}?restype=container&comp=list"
```

### K8s (if API in scope)
```bash
curl -sk https://{host}:6443/api/v1/namespaces
```

## Chain anchors

Public bucket → secrets → OAuth client_secret → ATO. Never-submit: empty bucket listing alone without sensitive object proof.

## Skip criteria

`scope.yaml` has no cloud assets (no AWS/GCP/Azure/K8s in scope) → `not-applicable` with scope citation.

## ACS references

`skills/hunt-cloud/references/acs-sources.md`
