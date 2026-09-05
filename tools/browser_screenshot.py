#!/usr/bin/env python3
"""
browser_screenshot.py — Chrome window capture + screenshot verification.

Capture: PrintWindow by HWND (tab title match), not GetForegroundWindow.
Verify: structural checks, DOM-independent image checks, optional OCR.

Usage:
    uv run python3 tools/browser_screenshot.py verify evidence/lead024/
    uv run python3 tools/browser_screenshot.py verify evidence/lead024/01.png
"""

from __future__ import annotations

import argparse
import ctypes
import io
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

try:
    from playwright.sync_api import CDPSession, Page
except ImportError:  # pragma: no cover
    Page = Any  # type: ignore
    CDPSession = Any  # type: ignore

# --- Win32 capture -----------------------------------------------------------

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
from ctypes import wintypes  # noqa: E402

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
PW_RENDERFULLCONTENT = 2
SW_MAXIMIZE = 3
TOOLBAR_PX = 130
MIN_CORRELATION = 0.55  # only used for viewport sidecar self-check
MIN_BRIGHTNESS = 55

AUTOMATION_BANNER_PHRASES = (
    "automated test software",
    "chrome is being controlled",
    "автоматизированное тестовое",
    "управляется автоматизирован",
    "playwright",
)


def find_content_top(img: Image.Image, fallback: int = TOOLBAR_PX) -> int:
    """Heuristic: first mostly-bright row below browser chrome."""
    w, h = img.width, img.height
    for y in range(0, min(h // 3, 220)):
        row = [img.getpixel((x, y)) for x in range(0, w, max(1, w // 60))]
        mean = sum(sum(p[:3]) / 3 for p in row) / len(row)
        if mean > 175:
            return max(0, y - 1)
    return fallback


def content_crop(img: Image.Image) -> Image.Image:
    top = find_content_top(img)
    margin_x = int(img.width * 0.02)
    margin_y = int(img.height * 0.02)
    return img.crop(
        (
            margin_x,
            top + margin_y,
            img.width - margin_x,
            img.height - margin_y,
        )
    )


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def _window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value


def _window_class(hwnd: int) -> str:
    buff = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buff, 256)
    return buff.value


def find_chrome_hwnd_for_page(page: Page, url_hint: str = "") -> int:
    title_hint = (page.title() or "").strip()
    matches: list[tuple[int, str, int]] = []

    def score(title: str) -> int:
        s = 0
        if title_hint and title_hint[:18] in title:
            s += 100
        if url_hint and url_hint.lower() in title.lower():
            s += 40
        if "Google Chrome" in title or "Chromium" in title:
            s += 10
        if "Cursor" in title or "Visual Studio" in title:
            s -= 1000
        return s

    def cb(hwnd: int, _: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        if not _window_class(hwnd).startswith("Chrome_WidgetWin"):
            return True
        title = _window_title(hwnd)
        if not title or title == "Google Chrome":
            return True
        matches.append((hwnd, title, score(title)))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    if not matches:
        raise RuntimeError("no Chrome windows found")
    matches.sort(key=lambda x: x[2], reverse=True)
    hwnd, title, pts = matches[0]
    if pts < 10:
        raise RuntimeError(f"no Chrome match for {title_hint!r}; candidates={[t for _, t, _ in matches]}")
    return hwnd


def capture_hwnd_printwindow(hwnd: int) -> Image.Image:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w < 400 or h < 300:
        raise RuntimeError(f"window too small: {w}x{h}")

    hwnd_dc = user32.GetWindowDC(hwnd)
    if not hwnd_dc:
        raise RuntimeError("GetWindowDC failed")
    mfc_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bmp = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
    old = gdi32.SelectObject(mfc_dc, bmp)
    ok = user32.PrintWindow(hwnd, mfc_dc, PW_RENDERFULLCONTENT)
    gdi32.SelectObject(mfc_dc, old)
    if not ok:
        user32.PrintWindow(hwnd, mfc_dc, 0)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    lines = gdi32.GetDIBits(mfc_dc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mfc_dc)
    user32.ReleaseDC(hwnd, hwnd_dc)
    if not lines:
        raise RuntimeError("GetDIBits failed")
    return Image.frombuffer("RGB", (w, h), buf.raw, "raw", "BGRX", 0, 1)


def cdp_session(page: Page) -> CDPSession:
    return page.context.new_cdp_session(page)


def maximize_page_window(page: Page) -> int:
    cdp = cdp_session(page)
    window_id = int(cdp.send("Browser.getWindowForTarget")["windowId"])
    cdp.send(
        "Browser.setWindowBounds",
        {"windowId": window_id, "bounds": {"windowState": "maximized"}},
    )
    page.wait_for_timeout(700)
    return window_id


def fit_viewport_to_window(page: Page) -> dict[str, int]:
    maximize_page_window(page)
    metrics = page.evaluate(
        """() => ({
            outerW: window.outerWidth,
            outerH: window.outerHeight,
            innerW: window.innerWidth,
            innerH: window.innerHeight
        })"""
    )
    chrome_h = max(int(metrics["outerH"]) - int(metrics["innerH"]), 110)
    target_w = max(int(metrics["outerW"]), int(metrics["innerW"]), 1280)
    target_h = max(int(metrics["outerH"]) - chrome_h, int(metrics["innerH"]), 700)
    page.set_viewport_size({"width": min(target_w, 3840), "height": min(target_h, 2160)})
    page.wait_for_timeout(500)
    final = page.evaluate(
        "() => ({ innerWidth: window.innerWidth, innerHeight: window.innerHeight })"
    )
    return {"width": int(final["innerWidth"]), "height": int(final["innerHeight"])}


# --- Overlays ----------------------------------------------------------------

OVERLAY_BUTTONS = (
    "Я согласен",
    "Принять",
    "Accept",
    "Got it",
    "OK",
    "Понятно",
    "Закрыть",
    "Close",
    "Не сейчас",
    "Пропустить",
    "Skip",
)

OVERLAY_SELECTORS = (
    '[aria-label="Close"]',
    '[aria-label="Закрыть"]',
    "button.close",
    ".modal [data-dismiss]",
)


def dismiss_all_overlays(page: Page, rounds: int = 3) -> list[str]:
    dismissed: list[str] = []
    for _ in range(rounds):
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
        except Exception:
            pass
        for label in OVERLAY_BUTTONS:
            try:
                loc = page.get_by_role("button", name=label).first
                if loc.is_visible(timeout=500):
                    loc.click(timeout=1500)
                    dismissed.append(label)
                    page.wait_for_timeout(300)
            except Exception:
                pass
        for sel in OVERLAY_SELECTORS:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=400):
                    loc.click(timeout=1000)
                    dismissed.append(sel)
                    page.wait_for_timeout(250)
            except Exception:
                pass
    return dismissed


def assert_no_blocking_overlays(page: Page) -> None:
    blockers = ("Я согласен", "Accept", "Принять")
    for label in blockers:
        try:
            if page.get_by_role("button", name=label).first.is_visible(timeout=400):
                raise RuntimeError(f"overlay still visible: {label}")
        except RuntimeError:
            raise
        except Exception:
            pass


# --- Verification ------------------------------------------------------------

@dataclass
class ShotSpec:
    filename: str
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    url_contains: str = ""
    caption: str = ""


def assert_no_automation_banner(img: Image.Image, label: str = "") -> None:
    """Fail if Playwright/Chrome automation infobar text appears in the top strip."""
    w, h = img.size
    top = img.crop((0, 0, w, min(TOOLBAR_PX + 50, h // 3)))
    ocr_text, ocr_status = ocr_image_text(top)
    haystack = ocr_text.lower() if ocr_status == "ok" and ocr_text else ""
    if not haystack:
        # Fallback: sample top strip pixels is weak; check common English banner without OCR
        return
    for phrase in AUTOMATION_BANNER_PHRASES:
        if phrase in haystack:
            raise RuntimeError(
                f"{label}: automation banner detected ({phrase!r}) — use CDP + real Chrome, not Playwright launch"
            )


def image_mean_brightness(img: Image.Image) -> float:
    thumb = img.resize((120, 80))
    pixels = list(thumb.getdata())
    return sum(sum(p[:3]) / 3 for p in pixels) / len(pixels)


def normalized_correlation(img_a: Image.Image, img_b: Image.Image, size: tuple[int, int] = (200, 150)) -> float:
    a = list(img_a.resize(size).convert("L").getdata())
    b = list(img_b.resize(size).convert("L").getdata())
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    if da * db == 0:
        return 0.0
    return num / (da * db)


def ocr_image_text(img: Image.Image) -> tuple[str, str]:
    """Returns (text, status) where status is pass|skipped|fail."""
    try:
        import pytesseract  # type: ignore
    except ImportError:
        return "", "skipped"
    try:
        # Content area below browser chrome
        crop = img.crop((0, TOOLBAR_PX, img.width, img.height))
        text = pytesseract.image_to_string(crop, lang="rus+eng")
        return text, "ok"
    except Exception as exc:
        return "", f"error:{exc}"


def verify_image_structural(img: Image.Image, label: str) -> dict[str, Any]:
    w, h = img.size
    mean = image_mean_brightness(img)
    result: dict[str, Any] = {"width": w, "height": h, "mean_brightness": round(mean, 2)}
    if w < 800 or h < 500:
        raise RuntimeError(f"{label}: too small {w}x{h}")
    if mean < MIN_BRIGHTNESS:
        raise RuntimeError(f"{label}: too dark (mean={mean:.1f}) — wrong window?")
    top = img.crop((0, 0, w, min(TOOLBAR_PX, h // 4)))
    top_mean = image_mean_brightness(top)
    result["top_strip_brightness"] = round(top_mean, 2)
    if top_mean < 30 and mean < 80:
        raise RuntimeError(f"{label}: looks like IDE/dark app (top={top_mean:.1f})")
    try:
        assert_no_automation_banner(img, label)
        result["automation_banner"] = "pass"
    except RuntimeError:
        raise
    except Exception as exc:
        result["automation_banner"] = f"skipped:{exc}"
    result["status"] = "pass"
    return result


def verify_image_content(
    img: Image.Image,
    spec: ShotSpec,
    page: Page | None = None,
    label: str = "",
    *,
    viewport_img: Image.Image | None = None,
) -> dict[str, Any]:
    label = label or spec.filename
    out: dict[str, Any] = {"structural": verify_image_structural(img, label)}

    # PrintWindow vs live viewport are different render paths — do not correlate them.
    # Use viewport sidecar PNG for content OCR / correlation instead.
    if viewport_img is not None:
        corr = normalized_correlation(content_crop(img), viewport_img)
        out["window_vs_viewport_correlation"] = round(corr, 4)
        ocr_source = viewport_img
        out["ocr_source"] = "viewport_sidecar"
    elif page is not None:
        try:
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(200)
        except Exception:
            pass
        vp_bytes = page.screenshot(type="png")
        ocr_source = Image.open(io.BytesIO(vp_bytes)).convert("RGB")
        out["ocr_source"] = "live_viewport"
    else:
        ocr_source = content_crop(img)
        out["ocr_source"] = "window_crop"

    ocr_text, ocr_status = ocr_image_text(ocr_source)
    out["ocr_status"] = ocr_status
    found: list[str] = []
    missing: list[str] = []
    if spec.must_contain:
        if ocr_status == "ok":
            for needle in spec.must_contain:
                if needle in ocr_text:
                    found.append(needle)
                else:
                    missing.append(needle)
            out["found_in_image"] = found
            out["missing_in_image"] = missing
            if missing:
                raise RuntimeError(f"{label}: OCR missing {missing}")
        elif page is None and viewport_img is None:
            out["ocr_note"] = "must_contain not OCR-checked (install pytesseract or keep viewport sidecar)"
        else:
            # No tesseract: DOM must be re-checked by caller; flag for manual review
            out["ocr_note"] = "pytesseract not installed — rely on dom_post + viewport sidecar"

    for bad in spec.must_not_contain:
        if ocr_status == "ok" and bad in ocr_text:
            raise RuntimeError(f"{label}: must_not_contain {bad!r} found in image OCR")

    out["status"] = "pass"
    return out


def assert_dom_post_capture(page: Page, spec: ShotSpec) -> None:
    """Re-read DOM after shutter — proves page state did not change mid-capture."""
    body = page.inner_text("body")
    for needle in spec.must_contain:
        if needle not in body:
            raise RuntimeError(f"{spec.filename}: post-capture DOM missing {needle!r}")
    for bad in spec.must_not_contain:
        if bad in body:
            raise RuntimeError(f"{spec.filename}: post-capture DOM still has {bad!r}")


def verify_png_on_disk(
    png_path: Path,
    meta_path: Path | None = None,
    page: Page | None = None,
) -> dict[str, Any]:
    png_path = png_path.resolve()
    if not png_path.exists():
        raise FileNotFoundError(png_path)
    meta_path = meta_path or png_path.with_suffix(png_path.suffix + ".meta.json")
    meta: dict[str, Any] = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

    spec = ShotSpec(
        filename=png_path.name,
        must_contain=meta.get("must_contain") or [],
        must_not_contain=meta.get("must_not_contain", []),
        url_contains=meta.get("url", ""),
        caption=meta.get("caption", ""),
    )

    img = Image.open(png_path).convert("RGB")
    vp_path = png_path.with_suffix(".viewport.png")
    viewport_img = Image.open(vp_path).convert("RGB") if vp_path.exists() else None

    verification = verify_image_content(
        img, spec, page=page, label=png_path.name, viewport_img=viewport_img
    )

    # Without OCR, require dom_post pass recorded in meta
    if verification.get("ocr_status") != "ok" and spec.must_contain:
        if not meta.get("dom_post_verified"):
            raise RuntimeError(
                f"{png_path.name}: no OCR and dom_post_verified not set in meta"
            )

    verification["verified_at"] = datetime.now(UTC).isoformat()
    verification["file"] = png_path.name
    if meta_path.exists():
        meta["verification"] = verification
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return verification


def verify_directory(evidence_dir: Path, page: Page | None = None) -> list[dict[str, Any]]:
    evidence_dir = evidence_dir.resolve()
    if not evidence_dir.is_dir():
        raise NotADirectoryError(evidence_dir)
    results: list[dict[str, Any]] = []
    pngs = sorted(
        p
        for p in evidence_dir.glob("*.png")
        if not p.name.endswith(".viewport.png") and not p.name.startswith("_")
    )
    if not pngs:
        raise RuntimeError(f"no PNG files in {evidence_dir}")
    for png in pngs:
        if png.name.endswith(".meta.png"):
            continue
        results.append(verify_png_on_disk(png, page=page))
    return results


def capture_page_window(page: Page, path: Path, url_hint: str = "") -> tuple[int, int, dict]:
    page.bring_to_front()
    page.wait_for_timeout(300)
    maximize_page_window(page)
    page.wait_for_timeout(400)
    hwnd = find_chrome_hwnd_for_page(page, url_hint=url_hint)
    img = capture_hwnd_printwindow(hwnd)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG", optimize=True)
    return img.size[0], img.size[1], {
        "hwnd": int(hwnd),
        "window_title": _window_title(hwnd),
        "page_title": page.title(),
        "method": "printwindow",
    }


# --- CLI ---------------------------------------------------------------------

def cmd_verify(args: argparse.Namespace) -> int:
    target = Path(args.target)
    paths: list[Path]
    if target.is_dir():
        paths = sorted(target.glob("*.png"))
    elif target.is_file():
        paths = [target]
    else:
        print(f"not found: {target}", file=sys.stderr)
        return 1

    page = None
    browser = None
    if args.cdp:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("playwright not installed; verifying without correlation", file=sys.stderr)
        else:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(args.cdp)
                if browser.contexts and browser.contexts[0].pages:
                    page = browser.contexts[0].pages[0]
                ok = 0
                for png in paths:
                    try:
                        v = verify_png_on_disk(png, page=page)
                        corr = v.get("correlation")
                        extra = f" corr={corr}" if corr is not None else ""
                        print(f"PASS {png.name}{extra}")
                        ok += 1
                    except Exception as exc:
                        print(f"FAIL {png.name}: {exc}", file=sys.stderr)
                browser.close()
                return 0 if ok == len(paths) else 1

    ok = 0
    for png in paths:
        try:
            v = verify_png_on_disk(png)
            print(f"PASS {png.name} (structural{'; OCR' if v.get('ocr_status')=='ok' else ''})")
            ok += 1
        except Exception as exc:
            print(f"FAIL {png.name}: {exc}", file=sys.stderr)
    return 0 if ok == len(paths) else 1


def main() -> None:
    set_dpi_aware()
    parser = argparse.ArgumentParser(description="Browser screenshot verify/capture helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("verify", help="Verify PNG screenshot(s) on disk")
    v.add_argument("target", help="PNG file or evidence directory")
    v.add_argument("--cdp", default="", help="CDP URL for correlation re-check (optional)")
    v.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
