"""Unit tests for fuzzingbook port."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fuzzingbook import (  # noqa: E402
    AFLFastSchedule,
    DeltaDebuggingReducer,
    HttpMutator,
    Seed,
    get_trace_key,
    pairwise_cover,
    should_stop,
)


def test_trace_key_excludes_latency() -> None:
    base = {"status": 200, "body": '{"a":1}', "latency_ms": 100}
    slow = {"status": 200, "body": '{"a":1}', "latency_ms": 900}
    assert get_trace_key(base) == get_trace_key(slow)


def test_trace_key_status_change() -> None:
    a = {"status": 200, "body": "{}"}
    b = {"status": 403, "body": "{}"}
    assert get_trace_key(a) != get_trace_key(b)


def test_assign_energy_rare_trace_gets_more() -> None:
    schedule = AFLFastSchedule(exponent=1.0)
    pop = [
        Seed(payload={"x": 1}, trace_key="common"),
        Seed(payload={"x": 2}, trace_key="rare"),
    ]
    freq = Counter({"common": 10, "rare": 1})
    schedule.assignEnergy(pop, freq)
    assert pop[1].energy > pop[0].energy


def test_reducer_pair_bundle() -> None:
    calls: list[int] = []

    def test(bundle: dict) -> bool:
        mutations = (bundle.get("repro_template") or {}).get("mutations") or []
        calls.append(len(mutations))
        return len(mutations) >= 2

    reducer = DeltaDebuggingReducer(test, max_reruns=20)
    out = reducer.reduce({"repro_template": {"mutations": ["a", "b", "c", "d"]}})
    assert len(out["repro_template"]["mutations"]) <= 4
    assert calls


def test_saturation_stop_on_budget() -> None:
    assert should_stop(trace_saturated=False, probe_ledger_saturated=False, budget_remaining=0)


def test_saturation_stop_when_both_saturated() -> None:
    assert should_stop(trace_saturated=True, probe_ledger_saturated=True, budget_remaining=10)


def test_pairwise_cover() -> None:
    dims = {"ct": ["json", "form"], "accept": ["*/*", "text/html"]}
    rows = pairwise_cover(dims)
    assert rows
    assert all("ct" in r and "accept" in r for r in rows)


def test_mutator_produces_candidate() -> None:
    mut = HttpMutator(boundary_strings=["'", ""])
    seed = {"endpoint": "https://example.com", "query": {"q": "test"}, "body": {}}
    out = mut.mutate(seed)
    assert out.get("query") or out.get("body")
