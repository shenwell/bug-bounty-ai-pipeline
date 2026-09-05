"""Target-type classifier for engagement profile routing."""

from __future__ import annotations

import re

from portfolio.common.models import AssetType


def classify_asset(identifier: str, context: str = "") -> AssetType:
    lower = identifier.lower()
    ctx = context.lower()

    if lower.endswith(".apk") or "android" in lower or "android" in ctx:
        return AssetType.MOBILE_ANDROID
    if lower.endswith(".ipa") or "ios" in lower or "app store" in ctx:
        return AssetType.MOBILE_IOS
    if any(k in lower for k in (".iso", ".ova", ".deb", ".rpm", ".msi")):
        return AssetType.DESKTOP_SOFTWARE
    if re.search(r"\b(ot|ics|modbus|plc|opc ua|iec)\b", ctx, re.IGNORECASE):
        return AssetType.OT_ICS
    if re.match(r"^(\*\.)?[\w-]+\.[\w.-]+$", lower):
        return AssetType.WEB_API
    if any(k in ctx for k in ("ngfw", "appliance", "firewall", "siem", "isim", "sandbox")):
        if "sandbox" in ctx and ("malware" in ctx or "обход детекта" in ctx):
            return AssetType.BINARY_MALWARE
        return AssetType.NETWORK_APPLIANCE
    if "container" in ctx or "kubernetes" in ctx or "k8s" in ctx:
        return AssetType.CLOUD_CONTAINER
    if re.match(r"^\d+\.\d+\.\d+\.\d+", lower):
        return AssetType.NETWORK_APPLIANCE
    if any(k in lower for k in (".exe", ".elf", ".dll", ".so")):
        return AssetType.BINARY_MALWARE
    return AssetType.WEB_API


def classify_with_llm_hint(identifier: str, context: str, llm_type: str | None) -> AssetType:
    base = classify_asset(identifier, context)
    if llm_type and llm_type in AssetType.__members__.values():
        return AssetType(llm_type)
    return base
