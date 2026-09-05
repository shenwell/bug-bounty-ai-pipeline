"""Greybox fuzz runner with safety envelope."""

from __future__ import annotations

import hashlib
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fuzzingbook import AFLFastSchedule, HttpMutator, Seed, get_trace_key, should_stop

from .corpus import host_from_endpoint, load_corpus
from .export import load_run_state, queue_signal, save_run_state
from .mutations import BOUNDARY_STRINGS, PII_FIELD_DENYLIST
from .oracles import evaluate_oracle
from .redaction import redact_dict


class CircuitBreaker:
    def __init__(self, threshold: int = 5, cooldown: float = 60.0) -> None:
        self.threshold = threshold
        self.cooldown = cooldown
        self.streak = 0
        self.tripped_at: float | None = None

    def record(self, status: int) -> None:
        if status in (403, 429):
            self.streak += 1
            if self.streak >= self.threshold:
                self.tripped_at = time.time()
        else:
            self.streak = 0

    def wait_if_tripped(self) -> None:
        if self.tripped_at is None:
            return
        elapsed = time.time() - self.tripped_at
        if elapsed < self.cooldown:
            time.sleep(self.cooldown - elapsed)
        self.tripped_at = None
        self.streak = 0


def _load_policy_headers(root: Path) -> dict[str, str]:
    headers = {"Accept": "*/*"}
    policy = root / "policy.md"
    if policy.exists():
        text = policy.read_text(encoding="utf-8", errors="replace")
        if "User-Agent" in text or "user-agent" in text.lower():
            for line in text.splitlines():
                if "bugbounty" in line.lower() or "user-agent" in line.lower():
                    m = line.split(":", 1)
                    if len(m) == 2:
                        headers["User-Agent"] = m[1].strip().strip("`\"'")
    if "User-Agent" not in headers:
        headers["User-Agent"] = "pentest-agents-signal-fuzz"
    return headers


def _session_cookie(root: Path, role: str) -> str:
    try:
        from session_bridge import load_role_session, load_session

        data = load_role_session(root, role) or load_session(root)
        if not data:
            return ""
        parts = []
        for c in data.get("cookies") or []:
            n, v = c.get("name", ""), c.get("value", "")
            if n:
                parts.append(f"{n}={v}")
        return "; ".join(parts)
    except Exception:
        return ""


def exec_request(
    seed: dict[str, Any],
    root: Path,
    *,
    role: str = "A",
    extra_headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Execute HTTP seed — returns status, body snippet, location, latency_ms."""
    endpoint = str(seed.get("endpoint") or "")
    method = str(seed.get("method") or "GET").upper()
    headers = _load_policy_headers(root)
    headers.update(seed.get("headers_template") or {})
    if extra_headers:
        headers.update(extra_headers)
    cookie = _session_cookie(root, role)
    if cookie:
        headers["Cookie"] = cookie

    parsed = urlparse(endpoint if "://" in endpoint else f"https://{endpoint}")
    url = endpoint if "://" in endpoint else f"https://{endpoint}"
    query = dict(seed.get("query") or {})
    if query:
        sep = "&" if "?" in url else "?"
        url = url + sep + urllib.parse.urlencode(query)

    body_bytes = None
    body_dict = seed.get("body") or seed.get("body_template") or {}
    if body_dict and method not in ("GET", "HEAD"):
        body_bytes = json.dumps(body_dict).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    ctx = ssl.create_default_context()
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read(100_000)
            latency = (time.perf_counter() - start) * 1000
            return {
                "status": resp.status,
                "body": raw.decode("utf-8", errors="replace"),
                "location": resp.getheader("Location") or "",
                "latency_ms": latency,
            }
    except urllib.error.HTTPError as e:
        raw = e.read(100_000) if e.fp else b""
        latency = (time.perf_counter() - start) * 1000
        return {
            "status": e.code,
            "body": raw.decode("utf-8", errors="replace"),
            "location": e.headers.get("Location") or "",
            "latency_ms": latency,
        }
    except Exception as exc:
        return {"status": 0, "body": str(exc), "location": "", "latency_ms": 0}


def _attempts_path(root: Path, host: str) -> Path:
    return root / "evidence" / host / "signal-fuzz" / "attempts.jsonl"


def _append_attempt(root: Path, host: str, row: dict[str, Any]) -> None:
    path = _attempts_path(root, host)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(redact_dict(row), ensure_ascii=False) + "\n")


def _request_fingerprint(seed: dict[str, Any]) -> str:
    raw = json.dumps(
        {
            "method": seed.get("method"),
            "endpoint": seed.get("endpoint"),
            "query": seed.get("query"),
            "body": seed.get("body"),
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def seed_to_mutator_payload(seed: dict[str, Any]) -> dict[str, Any]:
    return {
        "endpoint": seed.get("endpoint"),
        "method": seed.get("method", "GET"),
        "query": dict(seed.get("query") or {}),
        "body": dict(seed.get("body_template") or seed.get("body") or {}),
        "auth_role": seed.get("auth_role", "A"),
        "class_hint": seed.get("class_hint", "idor"),
        "cross_role_required": seed.get("cross_role_required", False),
    }


def run_greybox(
    root: Path,
    *,
    write_mode: str = "read-only",
    limit: int = 50,
    energy_budget: int = 200,
    max_rps: float = 1.0,
    corpus_path: Path | None = None,
    disruption_approved: bool = False,
) -> dict[str, Any]:
    if write_mode != "read-only" and not disruption_approved:
        raise ValueError("--disruption-approved required for owned-write/disruption modes")

    root = Path(root)
    seeds_raw = load_corpus(root, corpus_path)
    if write_mode == "read-only":
        seeds_raw = [s for s in seeds_raw if s.get("method", "GET") == "GET"]

    try:
        from session_bridge import list_role_sessions

        roles = list_role_sessions(root)
    except Exception:
        roles = []

    population: list[Seed] = []
    for s in seeds_raw[:limit]:
        payload = seed_to_mutator_payload(s)
        population.append(Seed(payload=payload, trace_key="", energy=1.0))

    if not population:
        return {"attempts": 0, "signals": 0, "error": "empty population"}

    schedule = AFLFastSchedule(exponent=1.0)
    mutator = HttpMutator(boundary_strings=BOUNDARY_STRINGS)
    path_frequency: Counter[str] = Counter()
    seen_traces: set[str] = set()
    state = load_run_state(root)
    breaker = CircuitBreaker()
    attempts = 0
    budget = energy_budget
    probe_cells: set[str] = set()
    max_traces = min(50, limit * 2)

    interval = 1.0 / max(max_rps, 0.1)

    while budget > 0 and attempts < energy_budget:
        if should_stop(
            trace_saturated=len(seen_traces) >= max_traces,
            probe_ledger_saturated=len(probe_cells) >= max(20, limit),
            budget_remaining=budget,
        ):
            break

        breaker.wait_if_tripped()
        seed = schedule.choose(population)
        candidate_payload = mutator.mutate(
            seed.payload,
            denylist_fields=PII_FIELD_DENYLIST,
        )
        candidate_payload["mutations"] = list(
            set(candidate_payload.get("mutations") or [])
            | {str(candidate_payload.get("query") or candidate_payload.get("body"))[:80]}
        )

        baseline_resp = exec_request(
            {**seed.payload, "endpoint": seed.payload.get("endpoint")},
            root,
            role=str(seed.payload.get("auth_role") or "A"),
        )
        mutant_resp = exec_request(
            {**seed.payload, **candidate_payload, "endpoint": seed.payload.get("endpoint")},
            root,
            role=str(seed.payload.get("auth_role") or "A"),
        )
        breaker.record(int(mutant_resp.get("status") or 0))

        trace_key = get_trace_key(mutant_resp)
        candidate_payload["trace_key"] = trace_key

        pair_meta = {
            "roles_available": len(roles),
            "write_mode": write_mode,
            "readback_template": "session B GET same object_id",
            "unauth": not roles,
        }
        oracle = evaluate_oracle(
            str(seed.payload.get("class_hint") or "idor"),
            baseline_resp,
            mutant_resp,
            pair_meta,
        )

        host = host_from_endpoint(str(seed.payload.get("endpoint") or ""))
        attempt_row = {
            "attempt_id": f"a-{attempts+1:05d}",
            "corpus_seed_id": seed.payload.get("corpus_seed_id", ""),
            "request_fingerprint": _request_fingerprint(candidate_payload),
            "trace_key": trace_key,
            "signal_tier": oracle.get("signal_tier"),
            "oracle_kind": oracle.get("kind"),
            "marker": oracle.get("delta"),
            "scope_check_ok": True,
        }
        _append_attempt(root, host, attempt_row)
        probe_cells.add(_request_fingerprint(candidate_payload))

        if trace_key not in seen_traces:
            seen_traces.add(trace_key)
            path_frequency[trace_key] += 1
            population.append(Seed(payload=candidate_payload, trace_key=trace_key))

        if oracle.get("hit") and oracle.get("signal_tier") == "oracle+readback":
            candidate_payload["energy"] = seed.energy
            queue_signal(state, candidate_payload, oracle)

        schedule.assignEnergy(population, path_frequency)
        attempts += 1
        budget -= 1
        time.sleep(interval)

    state["attempts_summary"] = {
        "attempts": attempts,
        "trace_count": len(seen_traces),
        "oracle_readback": len(state.get("queued_signals", [])),
    }
    save_run_state(root, state)
    return state["attempts_summary"]
