---
name: hunt-xxe
description: >-
  Hunting skill for XML External Entity — SOAP, SAML, SVG, DOCX, RSS, API XML bodies.
  OOB DTD for blind cases. Use with xxe-hunter agent.
generated_at: 2026-08-06
---

## Crown Jewel Targets

1. **SAML assertion** — dispatch oauth-hunter for XSW; XXE in assertion XML.
2. **SOAP endpoints** — legacy enterprise APIs.
3. **SVG upload** — inline entity expansion.
4. **DOCX/XLSX import** — unzip, inject `[Content_Types].xml` / `word/document.xml`.
5. **PDF/XML metadata** converters.

## Workflow

### In-band
```xml
<?xml version="1.0"?>
<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<root>&xxe;</root>
```

### OOB blind
External DTD on collaborator; parameter entities for exfil.

### Content-Type fuzz
Send XML body to endpoints accepting `application/json` — parser differential.

## Kill signals

- `DOCTYPE` stripped server-side on all variants
- Error messages show `FEATURE_SECURE_PROCESSING` / external entities disabled
- Client-side XML parse only

## Chain

XXE file read → config with DB creds → SSRF via entity to metadata.

## References

- `rules/payloads.md` XXE Advanced
- `oauth-hunter` for SAML-specific flows
