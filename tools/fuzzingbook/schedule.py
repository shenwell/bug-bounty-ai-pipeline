# Ported from Fuzzing Book ch.9 — adapted for HTTP BB energy schedule
"""AFLFast-style energy assignment for seed population."""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Seed:
    payload: dict[str, Any]
    trace_key: str = ""
    energy: float = 1.0
    field_rarity_boost: float = 1.0


class AFLFastSchedule:
    """Greybox schedule — assignEnergy from path frequency, not energy += 1."""

    def __init__(self, exponent: float = 1.0) -> None:
        self.exponent = exponent
        self._rng = random.Random()

    def choose(self, population: list[Seed]) -> Seed:
        if not population:
            raise ValueError("empty population")
        weights = [max(0.01, s.energy * s.field_rarity_boost) for s in population]
        total = sum(weights)
        pick = self._rng.uniform(0, total)
        acc = 0.0
        for seed, w in zip(population, weights):
            acc += w
            if pick <= acc:
                return seed
        return population[-1]

    def assignEnergy(
        self,
        population: list[Seed],
        path_frequency: Counter[str],
    ) -> None:
        """Recompute energy from inverse path frequency (rare traces get more)."""
        if not population:
            return
        max_freq = max(path_frequency.values()) if path_frequency else 1
        for seed in population:
            freq = path_frequency.get(seed.trace_key, 1)
            rarity = (max_freq / max(freq, 1)) ** self.exponent
            seed.energy = max(0.1, rarity)
            seed.field_rarity_boost = getattr(seed, "field_rarity_boost", 1.0)
