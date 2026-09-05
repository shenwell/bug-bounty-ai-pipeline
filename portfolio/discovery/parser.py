"""Parse Standoff365 program pages into Contract models."""

from __future__ import annotations

import re
from html import unescape

from portfolio.common.models import (
    Asset,
    AssetType,
    Contract,
    ProgramConstraints,
    ProgramFormat,
    RewardRange,
)
from portfolio.discovery.next_data_parser import enrich_from_next_data, extract_program_page_props
from portfolio.routing.classifier import classify_asset

UNPAID_MARKERS = [
    r"вознаграждени[ея]\s+не\s+выпла",
    r"не\s+выплачива(?:ется|ют)",
    r"без\s+вознагражден",
    r"не\s+предусмотрено\s+вознагражден",
    r"вознаграждение\s+отсутствует",
    r"no\s+reward(?:s)?\s+(?:paid|provided|offered)",
    r"without\s+(?:monetary\s+)?reward",
    r"unpaid\s+program",
    r"не\s+платят\s+за",
    r"деньги\s+не\s+плат",
]

TAB_LABELS = [
    "описание",
    "description",
    "scope",
    "область",
    "правила",
    "rules",
    "вознаграждение",
    "rewards",
    "reward",
    "ограничения",
    "restrictions",
    "критерии",
    "criteria",
    "принимается",
    "acceptance",
    "уязвимости",
    "vulnerabilities",
    "vulnerability",
    "рейтинг",
    "ranking",
    "версии",
    "versions",
    "version",
]


def _strip_tags(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return unescape(re.sub(r"\s+", " ", text)).strip()


def _extract_section(text: str, markers: list[str]) -> str:
    lower = text.lower()
    for marker in markers:
        idx = lower.find(marker.lower())
        if idx >= 0:
            return text[idx : idx + 3000]
    return ""


def parse_constraints(text: str) -> ProgramConstraints:
    constraints = ProgramConstraints()
    lower = text.lower()

    if "vpn" in lower and ("обязател" in lower or "required" in lower):
        constraints.vpn_required = True

    header_match = re.search(
        r"X-Bug-Bounty[:\s]+(\{?user\}?|[^\s,]+)", text, re.IGNORECASE
    )
    if header_match:
        val = header_match.group(1)
        if "user" in val.lower():
            constraints.required_headers["X-Bug-Bounty"] = "{user}"
        else:
            constraints.required_headers["X-Bug-Bounty"] = val

    if "whoami" in lower or "hostname" in lower:
        constraints.allowed_rce_commands = ["whoami", "hostname", "ifconfig"]

    if "/etc/passwd" in lower:
        constraints.allowed_file_reads.append("/etc/passwd")
    if "/etc/ufw/user6.rules" in lower:
        constraints.allowed_file_reads = ["/etc/ufw/user6.rules"]

    for ip in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b", text):
        if ip.startswith(("192.168.", "10.", "172.")):
            constraints.internal_test_hosts.append(ip)

    if "container escape" in lower or "контейнер" in lower:
        constraints.stop_after_container_escape = True
    if "bulk" in lower or "массов" in lower:
        constraints.no_bulk_enumeration = True
    if "reverse engineering" in lower or "реверс" in lower:
        constraints.no_reverse_engineering_mobile = True

    constraints.raw_rules = [line.strip() for line in text.split("\n") if len(line.strip()) > 20][:50]
    return constraints


def _is_valid_scope_entry(entry: str) -> bool:
    entry = entry.strip().rstrip(".,;")
    if not entry:
        return False
    if re.match(r"^\d+(\.\d+)+$", entry):
        return False
    if entry.replace(".", "").isdigit():
        return False
    if entry.startswith("*."):
        return len(entry) > 2 and "." in entry[2:]
    if "." in entry:
        return bool(re.match(r"^[\w.*-]+\.[a-zA-Z]{2,}$", entry))
    return False


def _extract_scope_markdown_section(content: str) -> str:
    match = re.search(
        r"(?:#{1,3}\s*)?(?:scope|скоуп)\b.*?(?=(?:#{1,3}\s|\Z))",
        content,
        re.IGNORECASE | re.DOTALL,
    )
    return match.group(0) if match else ""


def parse_scope_items(
    html: str, tab_sections: dict[str, str] | None = None
) -> tuple[list[str], list[str]]:
    text = _strip_tags(html)
    scope_section = ""
    oos_section = ""
    for label, content in (tab_sections or {}).items():
        norm = label.lower()
        if "out of scope" in norm or "вне scope" in norm:
            oos_section += "\n" + content
        elif any(m in norm for m in ("scope", "область", "скоуп")):
            scope_section += "\n" + content
        elif norm in ("description", "описание"):
            scope_section += "\n" + _extract_scope_markdown_section(content)

    if not scope_section:
        scope_section = _extract_section(text, ["scope", "скоуп", "область", "в scope", "цели"])
    if not oos_section:
        oos_section = _extract_section(text, ["out of scope", "вне scope", "не входит"])

    in_scope: list[str] = []
    out_of_scope: list[str] = []

    domain_re = re.compile(
        r"(?:\*\.|www\.)?[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
        r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+"
    )
    wildcard_re = re.compile(r"\*\.[^\s,;]+")
    ip_re = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    url_re = re.compile(r"https?://[^\s\]`\)\"']+")

    def _collect(section: str, target: list[str]) -> None:
        for entry in wildcard_re.findall(section):
            if _is_valid_scope_entry(entry) and entry not in target:
                target.append(entry)
        for domain in domain_re.findall(section):
            if _is_valid_scope_entry(domain) and domain not in target:
                target.append(domain)
        for ip in ip_re.findall(section):
            if ip not in target:
                target.append(ip)
        for url in url_re.findall(section):
            url = url.rstrip(".,;)")
            if url not in target:
                target.append(url)

    _collect(scope_section, in_scope)
    _collect(oos_section, out_of_scope)

    return in_scope, out_of_scope


def _parse_amount(value: str, suffix: str = "") -> float:
    amount = float(re.sub(r"[\s,]", "", value) or "0")
    suffix = (suffix or "").upper()
    if suffix == "K":
        amount *= 1_000
    elif suffix == "M":
        amount *= 1_000_000
    return amount


def parse_rewards(text: str) -> list[RewardRange]:
    rewards: list[RewardRange] = []
    patterns = [
        (r"critical[:\s]+(?:до\s+)?([\d\s]+)", "critical", ""),
        (r"high[:\s]+(?:до\s+)?([\d\s]+)", "high", ""),
        (r"medium[:\s]+(?:до\s+)?([\d\s]+)", "medium", ""),
        (r"low[:\s]+(?:до\s+)?([\d\s]+)", "low", ""),
        (r"критич[^\d]*([\d\s]+)", "critical", ""),
        (r"высок[^\d]*([\d\s]+)", "high", ""),
        (r"средн[^\d]*([\d\s]+)", "medium", ""),
        (r"низк[^\d]*([\d\s]+)", "low", ""),
        (r"up\s+to\s+₽\s*([\d.,]+)\s*([KkMm])?", "critical", "suffix"),
        (r"до\s+₽\s*([\d.,]+)\s*([KkMm])?", "critical", "suffix"),
        (r"₽\s*([\d.,]+)\s*([KkMm])\b", "high", "suffix"),
    ]
    for pattern, severity, mode in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        suffix = match.group(2) if mode == "suffix" and match.lastindex and match.lastindex >= 2 else ""
        amount = _parse_amount(match.group(1), suffix)
        if amount > 0 and not any(r.severity == severity for r in rewards):
            rewards.append(RewardRange(severity=severity, max_amount=amount))
    return rewards


def detect_is_paid(text: str, rewards: list[RewardRange]) -> bool:
    lower = text.lower()
    for pattern in UNPAID_MARKERS:
        if re.search(pattern, lower):
            return False
    if rewards and max((r.max_amount for r in rewards), default=0) > 0:
        return True
    if re.search(r"вознагражден|reward|bounty|руб\.?|₽|\d+\s*000", lower):
        return True
    return True


def merge_tab_sections(tab_sections: dict[str, str] | None) -> str:
    if not tab_sections:
        return ""
    parts: list[str] = []
    for label, content in tab_sections.items():
        if content.strip():
            parts.append(f"=== {label} ===\n{content}")
    return "\n\n".join(parts)


def parse_program(
    slug: str,
    name: str,
    html: str,
    url: str,
    program_id: str | None = None,
    tab_sections: dict[str, str] | None = None,
) -> Contract:
    tab_sections = tab_sections or {}
    page_props = extract_program_page_props(html)
    nd_rewards: list[RewardRange] = []
    nd_scope: list[str] = []
    if page_props:
        nd_tabs, nd_rewards, nd_scope, nd_name = enrich_from_next_data(page_props)
        tab_sections = {**nd_tabs, **tab_sections}
        if nd_name and (not name or name == slug):
            name = nd_name

    tab_text = merge_tab_sections(tab_sections)
    text = _strip_tags(html)
    if tab_text:
        text = f"{text}\n\n{tab_text}"
    in_scope, out_of_scope = parse_scope_items(html, tab_sections)
    if nd_scope:
        in_scope = nd_scope
    constraints = parse_constraints(text)
    rewards = parse_rewards(text)
    if nd_rewards:
        rewards = nd_rewards
    is_paid = detect_is_paid(text, rewards)

    is_private = "private" in text.lower() or "приватн" in text.lower()
    requires_accept = "accept rules" in text.lower() or "принять правила" in text.lower()
    is_nte = "недопустим" in text.lower() or "nte" in text.lower() or "non-tolerable" in text.lower()

    assets: list[Asset] = []
    for item in in_scope:
        asset_type = classify_asset(item, tab_text or text[:5000])
        assets.append(
            Asset(
                identifier=item,
                asset_type=asset_type,
                engagement_profile=_profile_for_type(asset_type),
            )
        )

    acceptance = _extract_section(text, ["принимается", "accept", "к рассмотрению"])

    return Contract(
        program_id=program_id or slug,
        slug=slug,
        name=name,
        scope=in_scope,
        out_of_scope=out_of_scope,
        assets=assets,
        reward_ranges=rewards,
        constraints=constraints,
        program_format=ProgramFormat.NTE if is_nte else ProgramFormat.CLASSIC,
        is_private=is_private,
        requires_accept_rules=requires_accept,
        accept_rules_pending=requires_accept,
        acceptance_criteria=acceptance[:5000],
        is_paid=is_paid,
        tab_sections=tab_sections,
        source_url=url,
        report_fields=[
            "title",
            "severity",
            "cve",
            "cwe",
            "scope_asset",
            "description",
            "files",
        ],
    )


def _profile_for_type(asset_type: AssetType) -> str:
    mapping = {
        AssetType.WEB_API: "web_api",
        AssetType.MOBILE_ANDROID: "mobile",
        AssetType.MOBILE_IOS: "mobile",
        AssetType.DESKTOP_SOFTWARE: "software_appliance",
        AssetType.NETWORK_APPLIANCE: "software_appliance",
        AssetType.OT_ICS: "ot_ics",
        AssetType.CLOUD_CONTAINER: "cloud_container",
        AssetType.BINARY_MALWARE: "binary_malware",
    }
    return mapping.get(asset_type, "web_api")
