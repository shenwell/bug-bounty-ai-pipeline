"""Parse disclosed reports list and detail pages."""

from __future__ import annotations

import json
import re
from html import unescape

from portfolio.common.models import DisclosedReport

VULN_PATTERNS = {
    "ssrf": re.compile(r"\bssrf\b", re.I),
    "xss": re.compile(r"\bxss\b", re.I),
    "sqli": re.compile(r"\bsql\s*inject", re.I),
    "idor": re.compile(r"\bidor\b", re.I),
    "rce": re.compile(r"\brce\b", re.I),
    "csrf": re.compile(r"\bcsrf\b", re.I),
    "xxe": re.compile(r"\bxxe\b", re.I),
    "auth": re.compile(r"\b(ato|auth|2fa|account takeover)\b", re.I),
}

HOST_RE = re.compile(
    r"(?:\*\.|www\.)?[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+"
)

STATUS_LABELS = {
    "fix_accepted": "Fix confirmed",
    "fixed": "Fixed",
    "disclosed": "Disclosed",
    "duplicate": "Duplicate",
    "informative": "Informative",
    "not_applicable": "Not applicable",
}


def _strip_tags(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "\n", text)
    return unescape(re.sub(r"\n+", "\n", text)).strip()


def _field(text: str, label: str) -> str:
    m = re.search(rf"{re.escape(label)}:\s*(.+)", text, re.I)
    return m.group(1).strip() if m else ""


def _parse_bounty(text: str) -> tuple[float, str]:
    m = re.search(r"₽\s*([\d.,]+)\s*([KkMm])?", text)
    if not m:
        m = re.search(r"([\d.,]+)\s*RUB", text, re.I)
    if not m:
        return 0.0, "RUB"
    amount = float(m.group(1).replace(",", "").replace(" ", ""))
    suffix = (m.group(2) or "").upper()
    if suffix == "K":
        amount *= 1_000
    elif suffix == "M":
        amount *= 1_000_000
    return amount, "RUB"


def extract_hosts(text: str) -> list[str]:
    hosts: list[str] = []
    for h in HOST_RE.findall(text):
        h = h.lower().rstrip(".")
        if h not in hosts and "." in h:
            hosts.append(h)
    return hosts


def extract_vuln_classes(text: str) -> list[str]:
    found: list[str] = []
    for name, pattern in VULN_PATTERNS.items():
        if pattern.search(text):
            found.append(name)
    cwe = re.search(r"CWE-\d+", text, re.I)
    if cwe and cwe.group(0).lower() not in found:
        found.append(cwe.group(0).lower())
    return found


def extract_next_data(html: str) -> dict | None:
    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return data.get("props", {}).get("pageProps")


def _merge_poc(description: str, hacker: str, vendor: str, comments: list[str]) -> str:
    parts: list[str] = []
    for block in (description, hacker, vendor):
        block = (block or "").strip()
        if block and block not in parts:
            parts.append(block)
    for comment in comments:
        comment = comment.strip()
        if comment and comment not in parts:
            parts.append(comment)
    return "\n\n".join(parts)


def _format_cwe(code: str | None, locale: dict | None) -> str:
    if not code:
        return ""
    label = ""
    if locale:
        label = (locale.get("en") or locale.get("ru") or "").strip()
    return f"{code} {label}".strip()


def _extract_history_comments(history_items: list[dict]) -> list[str]:
    comments: list[str] = []
    for item in history_items:
        if item.get("actionType") != "comment":
            continue
        body = item.get("body") or {}
        text = body.get("text")
        if text and str(text).strip():
            author = item.get("authorName") or body.get("authorType") or "unknown"
            comments.append(f"[{author}] {str(text).strip()}")
    return comments


def parse_disclosed_from_next_data(
    page_props: dict,
    url: str,
    base: DisclosedReport | None = None,
) -> DisclosedReport:
    report = base.model_copy() if base else DisclosedReport(source_url=url)
    dr = page_props.get("disclosedReport") or {}
    history = page_props.get("historyItems") or []

    report.disclosed_id = str(dr.get("id") or report.disclosed_id or "")
    report.report_no = str(dr.get("originReportId") or report.report_no or "")
    report.title = (dr.get("name") or report.title or "").strip()
    report.severity = (dr.get("severity") or report.severity or "").capitalize()
    report.cwe = _format_cwe(dr.get("cwe"), dr.get("cweLocale"))
    raw_status = dr.get("status") or ""
    report.status = STATUS_LABELS.get(raw_status, raw_status.replace("_", " ").title())
    report.created_at = dr.get("originCreatedAt") or report.created_at
    report.disclosed_at = dr.get("createdAt") or report.disclosed_at

    amount = dr.get("amount")
    if amount is not None:
        report.bounty_amount = float(amount)
    currency = (dr.get("currency") or "").upper()
    if currency:
        report.bounty_currency = "RUB" if currency == "RUB" else currency

    author = dr.get("author") or {}
    if author.get("username"):
        report.author = author["username"]

    program = dr.get("program") or {}
    if program.get("name"):
        report.program_name = program["name"]
    if program.get("slug"):
        report.program_slug = program["slug"]

    report.description = (dr.get("description") or "").strip()
    report.hacker_description = (dr.get("hackerDescription") or "").strip()
    report.vendor_description = (dr.get("vendorDescription") or "").strip()
    report.history_comments = _extract_history_comments(history)
    report.poc = _merge_poc(
        report.description,
        report.hacker_description,
        report.vendor_description,
        report.history_comments,
    )

    merged = f"{report.title} {report.cwe} {report.poc}"
    report.hosts = list(dict.fromkeys(report.hosts + extract_hosts(merged)))
    report.vuln_classes = list(
        dict.fromkeys(report.vuln_classes + extract_vuln_classes(merged))
    )
    report.source_url = url
    return report


def parse_disclosed_list_item(path: str, link_text: str, url: str) -> DisclosedReport:
    lines = [ln.strip() for ln in link_text.split("\n") if ln.strip()]
    title = lines[0] if lines else ""
    report_no = ""
    disclosed_id = ""
    m = re.match(r"^(\d+)\s+", title)
    if m:
        report_no = m.group(1)
        title = title[m.end() :].strip()
    path_m = re.search(r"/disclosed-reports/(\d+)$", path)
    if path_m:
        disclosed_id = path_m.group(1)
    program_name = lines[1] if len(lines) > 1 else ""
    severity = ""
    author = ""
    for ln in lines[2:]:
        if ln in ("Low", "Medium", "High", "Critical"):
            severity = ln
        elif not ln.startswith("₽") and not re.search(r"\d{4}", ln):
            author = ln
    bounty, currency = _parse_bounty(link_text)
    hosts = extract_hosts(title)
    vuln_classes = extract_vuln_classes(title)
    return DisclosedReport(
        list_path=path,
        disclosed_id=disclosed_id,
        report_no=report_no,
        title=title,
        program_name=program_name,
        severity=severity,
        bounty_amount=bounty,
        bounty_currency=currency,
        author=author,
        hosts=hosts,
        vuln_classes=vuln_classes,
        source_url=url,
    )


def parse_disclosed_detail(
    html: str,
    url: str,
    program_href: str | None,
    base: DisclosedReport | None = None,
) -> DisclosedReport:
    page_props = extract_next_data(html)
    if page_props and page_props.get("disclosedReport"):
        report = parse_disclosed_from_next_data(page_props, url, base)
        if program_href and "/programs/" in program_href and not report.program_slug:
            report.program_slug = program_href.split("/programs/")[-1].strip("/").split("?")[0]
        return report

    text = _strip_tags(html)
    report = base.model_copy() if base else DisclosedReport(source_url=url)

    report.report_no = _field(text, "Report No") or report.report_no
    if not report.report_no:
        m = re.search(r"Report No\.?:\s*(\d+)", text, re.I)
        if m:
            report.report_no = m.group(1)
    report.created_at = _field(text, "Created") or report.created_at
    report.disclosed_at = _field(text, "Disclosed") or report.disclosed_at
    report.status = _field(text, "Status") or report.status

    sev = re.search(r"Severity:\s*\n?\s*(Low|Medium|High|Critical)", text, re.I)
    if sev:
        report.severity = sev.group(1)

    cwe = re.search(r"CWE:\s*(CWE-\d+[^\\n]*)", text, re.I)
    if cwe:
        report.cwe = cwe.group(1).strip()

    author = re.search(r"Author:\s*\n?\s*([^\n]+)", text, re.I)
    if author:
        report.author = author.group(1).strip()

    reward = _parse_bounty(text)
    if reward[0]:
        report.bounty_amount, report.bounty_currency = reward

    if program_href and "/programs/" in program_href:
        report.program_slug = program_href.split("/programs/")[-1].strip("/").split("?")[0]

    merged = f"{report.title} {report.cwe} {text[:2000]}"
    report.hosts = list(dict.fromkeys(report.hosts + extract_hosts(merged)))
    report.vuln_classes = list(dict.fromkeys(report.vuln_classes + extract_vuln_classes(merged)))
    report.source_url = url
    return report
