"""Shared vuln-class taxonomy for autopilot gate and intel_engine.

REQUIRED_CLASSES is the single source of truth for the /autopilot exhaustion
contract. intel_engine uses GATE_TO_CANONICAL for ranking/exhaustion penalties
and MATRIX_ALIASES for depth-matrix CLI lookups.
"""

from __future__ import annotations

# Mirror of autopilot gate exhaustion contract (26 base + optional extensions).
REQUIRED_CLASSES: list[str] = [
    "idor",
    "xss-reflected",
    "xss-stored",
    "xss-dom",
    "ssrf",
    "sqli",
    "ssti",
    "rce",
    "oauth",
    "open-redirect",
    "csrf",
    "cors",
    "info-disclosure",
    "race-condition",
    "business-logic",
    "privilege-escalation",
    "file-upload",
    "xxe",
    "graphql",
    "subdomain-takeover",
    "llm-ai",
    "auth-bypass",
    "cache-deception",
    "header-injection",
    "h2-desync",
    "method-confusion",
    "cloud-misconfig",
    "mobile-api",
    "web3",
]

GATE_VULN_CLASSES: frozenset[str] = frozenset(REQUIRED_CLASSES)

# Gate slot → canonical label for ranking / exhaustion penalties.
GATE_TO_CANONICAL: dict[str, str] = {
    "xss-reflected": "xss",
    "xss-stored": "xss",
    "xss-dom": "xss",
    "file-upload": "file-upload",
    "privilege-escalation": "privilege-escalation",
    "subdomain-takeover": "subdomain-takeover",
    "info-disclosure": "info-disclosure",
    "race-condition": "race-condition",
    "business-logic": "business-logic",
    "open-redirect": "open-redirect",
    "auth-bypass": "auth-bypass",
    "cache-deception": "cache-deception",
    "header-injection": "header-injection",
    "h2-desync": "h2-desync",
    "method-confusion": "method-confusion",
    "llm-ai": "llm-ai",
    "cloud-misconfig": "cloud-misconfig",
    "mobile-api": "mobile-api",
    "web3": "web3",
}

# Matrix profile keys (intel_engine._default_attack_matrix).
MATRIX_ALIASES: dict[str, str] = {
    "xss-reflected": "xss",
    "xss-stored": "xss",
    "xss-dom": "xss",
    "file-upload": "upload",
}

SURFACE_DRIVEN_CLASSES: dict[str, str] = {
    "cache-deception": "C",
    "header-injection": "D",
    "h2-desync": "F",
    "method-confusion": "B",
}

SCOPE_SKIPPABLE_CLASSES: frozenset[str] = frozenset(
    {"cloud-misconfig", "mobile-api", "web3"}
)


def gate_to_canonical(gate_class: str) -> str:
    """Map a gate exhaustion slot to its canonical ranking label."""
    key = gate_class.strip().lower()
    return GATE_TO_CANONICAL.get(key, key)


def resolve_matrix_key(vuln_class: str) -> str:
    """Resolve gate or canonical class name to attack-matrix profile key."""
    key = vuln_class.strip().lower()
    return MATRIX_ALIASES.get(key, key)


def build_canonical_set() -> frozenset[str]:
    """All canonical labels used by intel_engine ranking."""
    base = {
        "idor",
        "xss",
        "ssrf",
        "sqli",
        "csrf",
        "rce",
        "ssti",
        "auth-bypass",
        "open-redirect",
        "graphql",
        "race-condition",
        "xxe",
        "file-upload",
        "info-disclosure",
        "cors",
        "oauth",
        "business-logic",
        "prototype-pollution",
        "deserialization",
        "lfi",
        "privilege-escalation",
        "subdomain-takeover",
        "llm-ai",
        "cache-deception",
        "header-injection",
        "h2-desync",
        "method-confusion",
        "cloud-misconfig",
        "mobile-api",
        "web3",
    }
    return frozenset(base)
