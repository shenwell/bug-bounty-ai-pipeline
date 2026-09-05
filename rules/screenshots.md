# Screenshot Evidence Rules

Reference for report/PoC agents and capture scripts. A screenshot is evidence only if
it shows the **right window**, the **right page state**, and the **claimed content**
— verified on disk, not assumed from Playwright DOM alone.

## When These Rules Apply

- Any screenshot attached to a bounty report, paste, or `evidence/` bundle
- Playwright/CDP capture from IDE terminal (Cursor, VS Code, etc.)
- Full-window captures that must include the **real browser address bar**

HTTP request/response JSON remains primary proof for API bugs; screenshots support
human triage (session, role, URL, visible impact).

---

## Rule 1: Real Chrome Window, Not IDE

`page.screenshot()` captures **viewport only** — no tabs, no address bar.

| Method | Address bar | Safe when IDE covers browser? |
|--------|-------------|-------------------------------|
| `page.screenshot()` | No | N/A |
| `ImageGrab` + `GetForegroundWindow()` | Yes | **No** — grabs Cursor if IDE is on top |
| `PrintWindow` + HWND matched to tab title | Yes | **Yes** |

**Do:**
1. Connect Playwright over CDP to a dedicated Chrome profile (`--remote-debugging-port`).
2. Maximize the page window via CDP `Browser.setWindowBounds` (`windowState: maximized`).
3. Fit viewport to window width (do not leave a 1440px page in a 1920px tab — gray borders).
4. Find Chrome HWND by **tab title** (`page.title()` + `Chrome_WidgetWin_*` class).
5. Capture with Win32 `PrintWindow(hwnd, …, PW_RENDERFULLCONTENT)`.

**Never:** `GetForegroundWindow()` + screen grab when the script runs inside an IDE.

**Never:** `Stop-Process chrome` / kill all Chrome windows to start CDP. If port 9222 is not listening, start a **second** Chrome with an isolated `user-data-dir` (see workflow below) — do not close the operator's session.

---

## Capture workflow (agent / operator)

Use this sequence for every UI evidence bundle. API bugs still need JSON/curl primary proof; screenshots are secondary but must follow the same gates.

### Step 1 — Chrome with CDP (isolated profile)

Chrome 136+ blocks CDP on the default profile. Use a dedicated directory:

```powershell
# Konsol (JWT inject in capture script — empty profile OK)
# Example: start CDP Chrome with a dedicated profile (adjust script name for your setup)
powershell -File scripts/start-chrome-cdp.ps1 -ForceNewProfile

# Other targets with cloned login (e.g. Profile 4) — see script; may copy profile once
powershell -File scripts/start-chrome-profile4-cdp.ps1
```

Wait until `http://127.0.0.1:9222/json/version` responds. **Do not** kill existing Chrome windows.

### Step 2 — Capture script

Per-lead script in bounty workspace (`scripts/capture_<lead>_screenshots.py`). Pattern:

1. `playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")`
2. Inject session token if needed (`localStorage` / cookies from `hunt/04-auth-session.json`)
3. Navigate to proof URL; `dismiss_all_overlays(page)`
4. DOM pre-gate (`must_contain`, `must_not_contain`, `url_contains`)
5. `capture_page_window(page, path)` → PrintWindow PNG + temp viewport for OCR
6. DOM post-gate; write `*.meta.json` and `screenshots-manifest.json`

```bash
# From repository root
uv run python scripts/capture_<lead>_screenshots.py
```

Library-only capture (no Playwright navigation) is **not** enough unless the operator already has the correct tab visible in the CDP Chrome window.

### Step 3 — Verify on disk (mandatory before paste/submit)

```bash
# From repository root
export PYTHONPATH=.
uv run --with pillow python tools/browser_screenshot.py verify path/to/evidence/<lead>/
```

Exit code 0 required. Re-read PNGs visually: address bar URL, proof payload, no banners.

### Step 4 — Cite in report

Only paths that exist on disk. Attach **window PNGs** to the platform form — not `*.meta.json`, not manifest, not probe JSON.

---

## Rule 2: No Playwright Automation Chrome

Report screenshots must not show automation UI:

- «Chrome is being controlled by automated test software» (grey infobar)
- **Playwright Extension** pink bar: `"Playwright Extension" started debugging this browser`

Both fail triage-style evidence gates.

**Do:**
- Start **normal Google Chrome** with `--remote-debugging-port` and a dedicated `user-data-dir`
  (see workflow + bounty `scripts/start-chrome-*-cdp.ps1`). Attach with `playwright.chromium.connect_over_cdp`.
- **Never** use `chromium.launch()`, bundled Chromium, or **Playwright Extension MCP** for
  evidence PNGs attached to triage. Extension + `PrintWindow` still shows the pink debugging
  banner while MCP is connected; clicking Cancel is not reliable across navigations.

**Do not recommend Extension as the primary capture path** — use isolated CDP Chrome + capture script.

**Shot spec defaults** — every `must_not_contain` list should include automation phrases
(or rely on `tools/browser_screenshot.py` banner gate):

- `automated test software`
- `Chrome is being controlled`
- `автоматизированное тестовое`
- `управляется автоматизирован`

Post-capture: `verify` runs OCR on the top chrome strip and fails if any phrase appears.

---

## Rule 3: Dismiss All Blocking Overlays Before Capture

Every modal, cookie banner, promo tooltip, or onboarding popup must be closed **before**
the shutter fires. A screenshot with a cookie banner over the proof table is a failed capture.

### Dismissal order (repeat until stable)

1. `Escape` (closes many dialogs)
2. Known consent buttons: `Я согласен`, `Принять`, `Accept`, `Got it`, `OK`, `Понятно`, `Закрыть`, `Close`, `Не сейчас`, `Пропустить`
3. ARIA close: `[aria-label="Close"]`, `[aria-label="Закрыть"]`, `button.close`, `.modal [data-dismiss]`
4. Re-check visibility — up to **3 rounds**

### Post-dismiss gate (DOM)

Before capture, assert **none** of these are visible:
- Cookie/consent primary buttons still on screen
- Modal backdrop blocking the proof region
- Login wall / `/login` redirect

Record dismissed controls in `*.meta.json` → `overlays_dismissed`.

---

## Rule 4: Pre-Capture Content Gate (DOM)

For each shot spec, define:

```yaml
must_contain:   # strings that MUST appear in page body (or locators)
must_not_contain: # strings that must NOT appear (login, wrong account, automation banner)
url_contains:   # optional substring of page.url
```

Fail the shot **before** saving PNG if any check fails. Store `body_snippet` in meta.

---

## Rule 5: Post-Capture Image Verification (Mandatory)

DOM checks prove the page **should** look right; image checks prove the PNG **does**
look right. Both are required.

### 5a. Structural checks (always, on **window PNG**)

| Check | Kill if |
|-------|---------|
| Min size | width < 800 or height < 500 |
| Mean brightness | < 55 (IDE/dark window) |
| Wrong app | top chrome strip overwhelmingly dark AND body mean dark |
| Automation banner | OCR/text on top strip matches Rule 2 phrases |

### 5b. Content checks (ephemeral viewport during capture)

During capture, write `page.screenshot()` to a **temp file**, run OCR/content checks,
then **delete** it. Do not keep `*.viewport.png` in `evidence/` — not for submit.

PrintWindow pixels ≠ viewport pixels — never correlate them as a hard gate.

| Check | When |
|-------|------|
| DOM pre-gate | `must_contain` / `must_not_contain` before shutter |
| DOM post-gate | same strings still in DOM after shutter (`dom_post_verified: true`) |
| OCR on temp viewport | every `must_contain` in OCR text (if `pytesseract` installed) |
| Re-verify on disk later | structural on window PNG + `dom_post_verified` in meta (no viewport file) |

Store in `*.meta.json`:

```json
{
  "verification": {
    "dom_pre": "pass",
    "image_structural": "pass",
    "automation_banner": "pass",
    "image_ocr": "pass|skipped|fail",
    "must_contain": ["-5000"],
    "found_in_image": ["-5000"]
  }
}
```

### 5c. Re-verify existing files

Before submit, run verification on **already saved** PNGs:

```bash
PYTHONPATH=. uv run python tools/browser_screenshot.py verify evidence/<lead>/
```

Do not reference screenshots in reports until verify exits 0.

---

## Rule 6: Artifacts Per Shot

For each `NN-description.png`:

| File | Purpose |
|------|---------|
| `NN-description.png` | Full Chrome window (PrintWindow) — **attach to report** |
| `NN-description.png.meta.json` | url, verification, `dom_post_verified`, overlays dismissed |

Do **not** persist `*.viewport.png` in evidence; use a temp file during capture only.

| `screenshots-manifest.json` | Index of all shots in the folder |

---

## Rule 7: Shot Spec Checklist (report writer)

Before citing a screenshot in a report:

- [ ] File exists (`ls` / verify command)
- [ ] `meta.json` → `dom_post_verified: true` and/or OCR `pass` at capture time
- [ ] No `*.viewport.png` files in evidence folder
- [ ] Address bar shows expected host/path
- [ ] No Playwright/automation banner in top strip
- [ ] Account / role visible matches narrative
- [ ] Proof payload visible (negative amount, renamed field, etc.)
- [ ] No cookie banner / modal covering proof
- [ ] Not login page, not landing, not WAF challenge

---

## Rule 8: Common Failures (from real sessions)

| Symptom | Cause | Fix |
|---------|-------|-----|
| Cursor IDE in screenshot | `GetForegroundWindow` | `PrintWindow` + HWND by title |
| Gray border inside tab | viewport 1440 in 1920 window | CDP maximize + set viewport to outer width |
| Synthetic/fake URL bar | PIL overlay | Real window capture |
| Playwright banner visible | Extension / `chromium.launch` | Rule 2 — CDP + real Chrome |
| Pink «Extension started debugging» bar | Playwright Extension MCP + PrintWindow | Isolated CDP Chrome; disconnect Extension |
| Cookie banner over table | dismiss not run | Rule 3 loops |
| `must_contain` in DOM but not in PNG | wrong window | correlation / re-capture |
| Black image | IDE or minimized Chrome | brightness gate |

---

## Reference Implementation

- Library: `tools/browser_screenshot.py`
- Example: bounty workspace `scripts/capture_*_screenshots.py`
- Chrome CDP: dedicated `user-data-dir` + port `9222` (Chrome 136+ blocks CDP on default profile)
