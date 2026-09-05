# Ported from Fuzzing Book ch.9 — stop conditions for greybox loop
"""Saturation gate for trace + probe ledger + budget."""

from __future__ import annotations


def should_stop(
    *,
    trace_saturated: bool,
    probe_ledger_saturated: bool,
    budget_remaining: int,
    min_budget: int = 0,
) -> bool:
    """Stop when budget exhausted OR both trace and probe ledger saturated."""
    if budget_remaining <= min_budget:
        return True
    return trace_saturated and probe_ledger_saturated
