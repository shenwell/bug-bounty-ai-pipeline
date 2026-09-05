---
name: hunt-mobile
description: >-
  Hunting skill for mobile API security — APK/IPA endpoint diff vs web, hardcoded
  secrets, deep links, WebView bridges. Requires recon/mobile/*.endpoints.txt.
  Use with mobile-hunter agent.
generated_at: 2026-08-06
---

## Prerequisites

- `recon/mobile/<package>.endpoints.txt` from autopilot decompile phase
- `scope.yaml` lists mobile package / app in scope

## Crown Jewel Targets

1. **Mobile-only API** — endpoints not in web JS bundles.
2. **Hardcoded API keys / secrets** — strings.xml, smali, Info.plist.
3. **Deep link injection** — `intent://`, custom scheme → WebView loadURL.
4. **addJavascriptInterface** — JS→Java bridge without `@JavascriptInterface` guards.
5. **Certificate pinning bypass** — only if policy allows; then test API authz.

## Workflow

1. Diff `recon/mobile/*.endpoints.txt` against web API inventory.
2. For each mobile-only path → dispatch idor-hunter with mobile base URL.
3. Grep decompiled sources for `http://`, `api_key`, `Bearer`, `secret`.
4. Test deep links: `adb shell am start -a android.intent.action.VIEW -d "app://host/path?url=https://evil"`

## Skip criteria

No mobile asset in `scope.yaml` → `not-applicable: no mobile in program scope`.

## ACS references

`skills/hunt-mobile/references/acs-sources.md`
