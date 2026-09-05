# Ported from Fuzzing Book ch.13 — adapted for HTTP pair-bundle reduction
"""Delta debugging reducer with pair-bundle test function."""

from __future__ import annotations

from typing import Any, Callable


class DeltaDebuggingReducer:
    """Minimize repro candidate while pair_bundle test stays passing."""

    def __init__(
        self,
        test: Callable[[dict[str, Any]], bool],
        *,
        max_reruns: int = 50,
    ) -> None:
        self.test = test
        self.max_reruns = max_reruns
        self.reruns = 0

    def reduce(self, pair_bundle: dict[str, Any]) -> dict[str, Any]:
        """Shrink mutations list in repro_template until test fails."""
        if not self.test(pair_bundle):
            return pair_bundle
        template = dict(pair_bundle.get("repro_template") or {})
        mutations = list(template.get("mutations") or [])
        if len(mutations) <= 1:
            return pair_bundle

        reduced = list(mutations)
        while len(reduced) > 1 and self.reruns < self.max_reruns:
            half = len(reduced) // 2
            for subset in (reduced[:half], reduced[half:]):
                trial = dict(pair_bundle)
                trial_template = dict(template)
                trial_template["mutations"] = subset
                trial["repro_template"] = trial_template
                self.reruns += 1
                if self.test(trial):
                    reduced = subset
                    pair_bundle = trial
                    break
            else:
                break
        return pair_bundle
