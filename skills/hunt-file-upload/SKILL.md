---
name: hunt-file-upload
description: >-
  Hunting skill for unrestricted/dangerous file upload — extension/MIME bypass,
  polyglot, SVG XSS, path traversal filenames, presigned URL abuse, zip-slip.
  Use with file-upload agent.
generated_at: 2026-08-06
---

## Crown Jewel Targets

1. **Web shell** — `.php`, `.jsp`, `.aspx` served as executable from upload URL.
2. **Stored XSS via SVG/HTML** — rendered inline without `Content-Disposition: attachment`.
3. **SSRF via image processor** — upload triggers server fetch of attacker URL.
4. **Zip-slip** — archive import writes outside intended directory.
5. **Presigned S3 abuse** — overwrite or upload to wrong tenant prefix.

## Workflow

1. Map pipeline: client check → server ext → MIME → magic bytes → AV → storage path → CDN.
2. Test: double ext, null byte, case, `.php5`, `Content-Type: image/png` on PHP.
3. Polyglot: GIF89a + `<?php ...?>`
4. Path: `../../../shell.php` in filename
5. **Read-back**: fetch uploaded URL — check `Content-Type`, execution, cross-user access

## Chain anchors

Upload → RCE → lateral. Upload → stored XSS → session theft. See `rules/chain-table.md`.

## Kill signals

- File stored but never accessible (404) or forced download only
- Extension blocked on all 30+ matrix combos
- Image-only CDN strips metadata and re-encodes — no parser sink

## References

- `rules/payloads.md` File Upload section
- Matrix: `intel_engine.py matrix file-upload`
