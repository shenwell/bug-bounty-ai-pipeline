"""Tests for gate ↔ intel_engine vuln taxonomy alignment."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import autopilot_gate, intel_engine  # noqa: E402
from tools.vuln_taxonomy import (  # noqa: E402
    GATE_TO_CANONICAL,
    MATRIX_ALIASES,
    REQUIRED_CLASSES,
    gate_to_canonical,
    resolve_matrix_key,
)


def test_required_classes_match_gate() -> None:
    assert autopilot_gate.REQUIRED_CLASSES == REQUIRED_CLASSES


def test_xss_subtypes_map_to_xss_canonical() -> None:
    for slot in ("xss-reflected", "xss-stored", "xss-dom"):
        assert gate_to_canonical(slot) == "xss"
        assert slot in GATE_TO_CANONICAL


def test_matrix_aliases_resolve_xss_and_upload() -> None:
    assert resolve_matrix_key("xss-reflected") == "xss"
    assert resolve_matrix_key("file-upload") == "upload"
    assert resolve_matrix_key("ssrf") == "ssrf"


def test_build_attack_matrix_accepts_gate_xss_subtype() -> None:
    combos = intel_engine.build_attack_matrix("xss-reflected", limit=5)
    assert combos
    assert combos[0]["vuln_class"] == "xss-reflected"


def test_canonicalize_coverage_gate_slots() -> None:
    assert intel_engine._canonicalize_vuln_label("xss-reflected") == "xss"
    assert intel_engine._canonicalize_vuln_label("cloud-misconfig") == "cloud-misconfig"
    assert intel_engine._canonicalize_vuln_label("mobile-api") == "mobile-api"


def test_new_gate_classes_in_canonical_set() -> None:
    for cls in ("cloud-misconfig", "mobile-api", "web3"):
        assert cls in REQUIRED_CLASSES
        assert cls in intel_engine.CANONICAL_VULN_CLASSES


def test_matrix_profiles_for_new_classes() -> None:
    for cls in ("auth-bypass", "cloud-misconfig", "mobile-api", "xxe"):
        assert intel_engine.build_attack_matrix(cls, limit=3)


def test_matrix_alias_keys_subset_of_profiles() -> None:
    profiles = set(intel_engine._default_attack_matrix())
    for alias, target in MATRIX_ALIASES.items():
        assert target in profiles, f"alias {alias} → missing profile {target}"
