# Ported from Fuzzing Book ch.12 — IPO covering array for config dimensions
"""Pairwise (2-way) covering array generator."""

from __future__ import annotations

from itertools import product
from typing import Any


def pairwise_cover(dimensions: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Greedy pairwise cover — not full IPO but sufficient for HTTP config cells."""
    keys = list(dimensions.keys())
    if not keys:
        return []
    if len(keys) == 1:
        k = keys[0]
        return [{k: v} for v in dimensions[k]]

    pairs_needed: set[tuple[tuple[str, Any], tuple[str, Any]]] = set()
    for i, k1 in enumerate(keys):
        for k2 in keys[i + 1 :]:
            for v1 in dimensions[k1]:
                for v2 in dimensions[k2]:
                    pairs_needed.add(((k1, v1), (k2, v2)))

    rows: list[dict[str, Any]] = []
    all_values = [dimensions[k] for k in keys]

    for combo in product(*all_values):
        row = dict(zip(keys, combo))
        covered = set()
        for i, k1 in enumerate(keys):
            for k2 in keys[i + 1 :]:
                covered.add(((k1, row[k1]), (k2, row[k2])))
        if covered & pairs_needed:
            rows.append(row)
            pairs_needed -= covered
        if not pairs_needed:
            break

    if not rows and all_values:
        rows.append(dict(zip(keys, [vals[0] for vals in all_values])))
    return rows
