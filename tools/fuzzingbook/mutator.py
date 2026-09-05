# Ported from Fuzzing Book ch.8 — adapted for HTTP slot mutation
"""HTTP request slot mutator with stacked encoding."""

from __future__ import annotations

import copy
import random
import urllib.parse
from typing import Any


def _url_encode(s: str) -> str:
    return urllib.parse.quote(s, safe="")


def _double_url_encode(s: str) -> str:
    return _url_encode(_url_encode(s))


def _html_entity_url(s: str) -> str:
    mapped = s.replace("<", "&lt;").replace(">", "&gt;")
    return _url_encode(mapped)


ENCODING_OPS = {
    "raw": lambda s: s,
    "url": _url_encode,
    "double-url": _double_url_encode,
    "html-entity+url": _html_entity_url,
}


class HttpMutator:
    """Mutate query/body/header slots on HTTP seed dicts."""

    def __init__(self, boundary_strings: list[str] | None = None, rng: random.Random | None = None) -> None:
        self.boundary_strings = boundary_strings or []
        self._rng = rng or random.Random()

    def mutate(
        self,
        seed: dict[str, Any],
        *,
        min_m: int = 2,
        max_m: int = 5,
        denylist_fields: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        deny = denylist_fields or frozenset({"email", "phone", "password", "token"})
        out = copy.deepcopy(seed)
        slots: list[tuple[str, str]] = []
        for key, val in (out.get("query") or {}).items():
            if key.lower() not in deny:
                slots.append(("query", key))
        for key, val in (out.get("body") or {}).items():
            if key.lower() not in deny:
                slots.append(("body", key))
        if not slots and self.boundary_strings:
            out.setdefault("query", {})["_fuzz"] = self._rng.choice(self.boundary_strings)
            return out
        if not slots:
            return out

        n_ops = self._rng.randint(min_m, max(max_m, min_m))
        for _ in range(n_ops):
            slot_type, key = self._rng.choice(slots)
            base = str((out.get(slot_type) or {}).get(key, ""))
            mutant = self._apply_op(base)
            out.setdefault(slot_type, {})[key] = mutant
        return out

    def _apply_op(self, value: str) -> str:
        ops = ["boundary", "truncate", "append", "encoding"]
        op = self._rng.choice(ops)
        if op == "boundary" and self.boundary_strings:
            return self._rng.choice(self.boundary_strings)
        if op == "truncate" and value:
            return value[: max(0, len(value) // 2)]
        if op == "append":
            return value + self._rng.choice(["'", '"', "\x00", "%00", "%%"])
        enc = self._rng.choice(list(ENCODING_OPS.keys()))
        return ENCODING_OPS[enc](value or "x")
