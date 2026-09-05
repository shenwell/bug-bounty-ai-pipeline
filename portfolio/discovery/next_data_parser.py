"""Parse Standoff365 program pages from __NEXT_DATA__ JSON."""

from __future__ import annotations

import json
import re

from portfolio.common.models import RewardRange

SCOPE_SECTION_RE = re.compile(
    r"(?:#{1,3}\s*)?(?:scope|скоуп)\b.*?(?=(?:#{1,3}\s|\Z))",
    re.IGNORECASE | re.DOTALL,
)


def extract_program_page_props(html: str) -> dict | None:
    match = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return data.get("props", {}).get("pageProps")


def parse_rewards_from_next(reward: dict | None) -> list[RewardRange]:
    if not reward:
        return []
    currency = (reward.get("currency") or "rub").upper()
    if currency == "RUB":
        currency = "RUB"
    rewards: list[RewardRange] = []
    for severity in ("critical", "high", "medium", "low"):
        block = reward.get(severity) or {}
        max_amount = float(block.get("maxReward") or 0)
        min_amount = float(block.get("minReward") or 0)
        amount = max_amount or min_amount
        if amount > 0:
            rewards.append(
                RewardRange(
                    severity=severity,
                    min_amount=min_amount,
                    max_amount=max_amount or min_amount,
                    currency=currency,
                )
            )
    return rewards


def parse_scope_from_description(description: str) -> list[str]:
    if not description:
        return []
    match = SCOPE_SECTION_RE.search(description)
    section = match.group(0) if match else description[:4000]
    entries: list[str] = []
    for raw in re.findall(r"`([^`]+)`", section):
        item = raw.strip().rstrip(".,;")
        if item and item not in entries:
            entries.append(item)
    for wild in re.findall(r"\*\.[a-zA-Z0-9][\w.-]+", section):
        if wild not in entries:
            entries.append(wild)
    domain_re = re.compile(
        r"(?:\*\.|www\.)?[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
        r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+"
    )
    for domain in domain_re.findall(section):
        if domain not in entries:
            entries.append(domain)
    for ip in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", section):
        if ip not in entries:
            entries.append(ip)
    for url in re.findall(r"https?://[^\s\]`\)\"']+", section):
        url = url.rstrip(".,;)")
        if url not in entries:
            entries.append(url)
    return entries


def parse_tab_sections_from_next(page_props: dict) -> dict[str, str]:
    sections: dict[str, str] = {}
    program = page_props.get("program") or {}
    description = (program.get("description") or "").strip()
    if description:
        sections["Description"] = description
    special_rules = (program.get("specialRules") or "").strip()
    if special_rules:
        sections["Rules"] = special_rules
    short_description = (program.get("shortDescription") or "").strip()
    if short_description:
        sections["Summary"] = short_description

    risks = page_props.get("risks") or []
    if risks:
        lines = []
        for risk in risks[:50]:
            if isinstance(risk, dict):
                title = risk.get("title") or risk.get("name") or ""
                body = risk.get("description") or ""
                lines.append(f"{title}\n{body}".strip())
            else:
                lines.append(str(risk))
        sections["Vulnerabilities"] = "\n\n".join(line for line in lines if line)

    versions = page_props.get("verionsDiffs") or page_props.get("verionsDiff")
    if versions:
        sections["Versions"] = json.dumps(versions, ensure_ascii=False, indent=2)[:8000]

    widget = page_props.get("widgetScoring")
    if widget:
        sections["Ranking"] = json.dumps(widget, ensure_ascii=False, indent=2)[:8000]

    scopes = page_props.get("scopes") or []
    if scopes:
        scope_lines = []
        for item in scopes:
            if isinstance(item, dict):
                scope_lines.append(
                    item.get("name")
                    or item.get("host")
                    or item.get("value")
                    or json.dumps(item, ensure_ascii=False)
                )
            else:
                scope_lines.append(str(item))
        sections["Scope"] = "\n".join(line for line in scope_lines if line)

    return sections


def enrich_from_next_data(page_props: dict) -> tuple[dict[str, str], list[RewardRange], list[str], str]:
    program = page_props.get("program") or {}
    tab_sections = parse_tab_sections_from_next(page_props)
    rewards = parse_rewards_from_next(page_props.get("reward"))
    description = (program.get("description") or "").strip()
    scope = parse_scope_from_description(description)
    if not scope and "Scope" in tab_sections:
        from portfolio.discovery.parser import parse_scope_items

        scope, _ = parse_scope_items("", {"Scope": tab_sections["Scope"]})
    name = (program.get("name") or "").strip()
    return tab_sections, rewards, scope, name
