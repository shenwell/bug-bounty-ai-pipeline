#!/usr/bin/env python3
"""Outcome metrics for pipeline v4 — validity, dup-rate, CONFIRMED/session, severity mix.

Aggregates platform responses (response-history.json) and brain/finding artifacts.
Use snapshot/compare to measure whether pipeline changes improve bug yield.

Usage:
    python3 tools/pipeline_metrics.py snapshot --target example.com --label baseline
    python3 tools/pipeline_metrics.py compare --baseline brain/metrics/example-com-baseline.json \\
        --after brain/metrics/example-com-after.json
    python3 tools/pipeline_metrics.py report --root .
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from file_safety import atomic_write_text  # noqa: E402
from threat_model import slugify_target  # noqa: E402

ACCEPTED_STATUSES = frozenset({"accepted", "triaged", "resolved"})
REJECTED_STATUSES = frozenset({"informative", "not-applicable"})
DUPLICATE_STATUS = "duplicate"

SEVERITY_ORDER = ("critical", "high", "medium", "low", "info", "informational", "unknown")

CONFIRMED_BRAIN_RE = re.compile(r"\[CONFIRMED\]", re.IGNORECASE)
DA_KILLED_RE = re.compile(r"\[DA KILLED\]", re.IGNORECASE)
BROWSER_REJECTED_RE = re.compile(r"\[BROWSER REJECTED\]", re.IGNORECASE)
POTENTIAL_RE = re.compile(r"\[POTENTIAL\]|Status:\s*POTENTIAL", re.IGNORECASE)


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def metrics_dir(root: Path) -> Path:
    return root / "brain" / "metrics"


def metrics_path(root: Path, target: str, label: str) -> Path:
    slug = slugify_target(target)
    safe_label = re.sub(r"[^a-z0-9_-]+", "-", label.lower()).strip("-")
    return metrics_dir(root) / f"{slug}-{safe_label}.json"


def load_response_history(root: Path) -> dict:
    path = root / "response-history.json"
    if not path.exists():
        return {"reports": [], "insights": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"reports": [], "insights": {}}
    return data if isinstance(data, dict) else {"reports": [], "insights": {}}


def _scan_brain_targets(brain_dir: Path, target_filter: str = "") -> dict[str, int]:
    counts: dict[str, int] = {
        "confirmed": 0,
        "da_killed": 0,
        "browser_rejected": 0,
        "potential": 0,
    }
    targets_dir = brain_dir / "targets"
    if not targets_dir.exists():
        return counts

    slug_filter = slugify_target(target_filter) if target_filter else ""
    for path in targets_dir.glob("*.md"):
        if slug_filter and slug_filter not in path.stem:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        counts["confirmed"] += len(CONFIRMED_BRAIN_RE.findall(text))
        counts["da_killed"] += len(DA_KILLED_RE.findall(text))
        counts["browser_rejected"] += len(BROWSER_REJECTED_RE.findall(text))
        counts["potential"] += len(POTENTIAL_RE.findall(text))
    return counts


def _scan_findings(evidence_dir: Path) -> dict:
    severity_mix: Counter[str] = Counter()
    judge_confirmed = 0
    total_findings = 0
    if not evidence_dir.exists():
        return {
            "total_findings": 0,
            "judge_confirmed": 0,
            "severity_mix": {},
        }
    for path in evidence_dir.rglob("findings/*.json"):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(rec, dict):
            continue
        total_findings += 1
        sev = str(rec.get("severity_claimed") or rec.get("severity") or "unknown").lower()
        severity_mix[sev] += 1
        gates = rec.get("gates") or {}
        judge = gates.get("judge") or {}
        if isinstance(judge, dict) and str(judge.get("verdict", "")).upper() == "CONFIRM":
            judge_confirmed += 1
    return {
        "total_findings": total_findings,
        "judge_confirmed": judge_confirmed,
        "severity_mix": dict(severity_mix),
    }


def _count_sessions(brain_dir: Path) -> int:
    sessions_dir = brain_dir / "sessions"
    if not sessions_dir.exists():
        return 0
    return len(list(sessions_dir.glob("*.md")))


def _scan_signal_fuzz(root: Path) -> dict:
    """Scan signal-fuzz attempts JSONL and exported fuzz-signals.json."""
    attempts = 0
    trace_only = 0
    exports_oracle_readback = 0
    for path in root.glob("evidence/**/signal-fuzz/attempts.jsonl"):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            attempts += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("signal_tier") == "trace-only":
                trace_only += 1
    signals_path = root / "recon" / "fuzz-signals.json"
    if signals_path.exists():
        try:
            data = json.loads(signals_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                exports_oracle_readback = sum(
                    1 for row in data if row.get("signal_tier") == "oracle+readback"
                )
        except json.JSONDecodeError:
            pass
    witness_pass_rate = None
    if exports_oracle_readback:
        witness_pass_rate = round(
            max(0.0, (exports_oracle_readback - trace_only) / exports_oracle_readback),
            4,
        )
    return {
        "attempts": attempts,
        "exports_oracle_readback": exports_oracle_readback,
        "trace_only": trace_only,
        "hunter_dispatches": exports_oracle_readback,
        "witness_pass_rate": witness_pass_rate,
        "confirmed_with_disruption_axis": 0,
    }


def compute_metrics(root: Path, target: str = "") -> dict:
    """Aggregate outcome metrics from response history, brain, and findings."""
    root = Path(root)
    history = load_response_history(root)
    reports = history.get("reports") or []

    if target:
        slug = slugify_target(target)
        filtered = [
            r
            for r in reports
            if slug in slugify_target(str(r.get("program", "")))
            or slug in slugify_target(str(r.get("report_id", "")))
        ]
        if filtered:
            reports = filtered

    accepted = sum(1 for r in reports if r.get("status") in ACCEPTED_STATUSES)
    rejected = sum(1 for r in reports if r.get("status") in REJECTED_STATUSES)
    duplicates = sum(1 for r in reports if r.get("status") == DUPLICATE_STATUS)
    total_submitted = len(reports)

    validity_denominator = accepted + rejected
    validity_ratio = (accepted / validity_denominator) if validity_denominator else None
    dup_rate = (duplicates / total_submitted) if total_submitted else None

    brain_counts = _scan_brain_targets(root / "brain", target_filter=target)
    findings_stats = _scan_findings(root / "evidence")
    session_count = max(1, _count_sessions(root / "brain"))

    judge_confirmed = findings_stats["judge_confirmed"]
    confirmed_per_session = judge_confirmed / session_count

    signal_fuzz_stats = _scan_signal_fuzz(root)

    return {
        "version": 1,
        "target": target or "(all)",
        "captured_at": _utc_now_iso(),
        "platform": {
            "total_submitted": total_submitted,
            "accepted": accepted,
            "rejected": rejected,
            "duplicates": duplicates,
            "validity_ratio": round(validity_ratio, 4) if validity_ratio is not None else None,
            "dup_rate": round(dup_rate, 4) if dup_rate is not None else None,
            "total_bounty": sum(float(r.get("bounty") or 0) for r in reports),
        },
        "brain": brain_counts,
        "findings": findings_stats,
        "sessions": {
            "count": session_count,
            "judge_confirmed_per_session": round(confirmed_per_session, 4),
        },
        "signal_fuzz": signal_fuzz_stats,
    }


def save_snapshot(root: Path, target: str, label: str) -> Path:
    metrics_dir(root).mkdir(parents=True, exist_ok=True)
    doc = compute_metrics(root, target=target)
    doc["label"] = label
    out = metrics_path(root, target or "global", label)
    atomic_write_text(out, json.dumps(doc, indent=2) + "\n")
    return out


def compare_snapshots(baseline: dict, after: dict) -> dict:
    """Compare two metric snapshots; positive delta on validity/confirmed is good."""

    def _delta(key_path: list[str]) -> float | None:
        b = baseline
        a = after
        for key in key_path:
            b = (b or {}).get(key) if isinstance(b, dict) else None
            a = (a or {}).get(key) if isinstance(a, dict) else None
        if b is None or a is None:
            return None
        try:
            return float(a) - float(b)
        except (TypeError, ValueError):
            return None

    validity_delta = _delta(["platform", "validity_ratio"])
    dup_delta = _delta(["platform", "dup_rate"])
    cps_delta = _delta(["sessions", "judge_confirmed_per_session"])
    confirmed_delta = _delta(["findings", "judge_confirmed"])
    accepted_delta = _delta(["platform", "accepted"])

    signals: list[bool] = []
    if validity_delta is not None:
        signals.append(validity_delta > 0)
    if cps_delta is not None:
        signals.append(cps_delta > 0)
    if confirmed_delta is not None:
        signals.append(confirmed_delta > 0)
    if accepted_delta is not None:
        signals.append(accepted_delta > 0)
    if dup_delta is not None:
        signals.append(dup_delta <= 0)
    improved: bool | None = None
    if signals:
        improved = all(signals)

    return {
        "validity_ratio_delta": validity_delta,
        "dup_rate_delta": dup_delta,
        "confirmed_per_session_delta": cps_delta,
        "judge_confirmed_delta": confirmed_delta,
        "accepted_delta": accepted_delta,
        "improved": improved,
    }


def _is_improved(baseline: dict, after: dict) -> bool | None:
    return compare_snapshots(baseline, after).get("improved")


def print_report(metrics: dict) -> None:
    plat = metrics.get("platform") or {}
    brain = metrics.get("brain") or {}
    findings = metrics.get("findings") or {}
    sessions = metrics.get("sessions") or {}

    print(f"\n📊 Pipeline outcome metrics — {metrics.get('target', '(all)')}")
    print(f"   Captured: {metrics.get('captured_at', '?')}")
    if metrics.get("label"):
        print(f"   Label: {metrics['label']}")
    print("\n  Platform:")
    print(f"    Submitted: {plat.get('total_submitted', 0)}")
    vr = plat.get("validity_ratio")
    print(f"    Validity ratio: {vr:.2%}" if vr is not None else "    Validity ratio: n/a")
    dr = plat.get("dup_rate")
    print(f"    Dup rate: {dr:.2%}" if dr is not None else "    Dup rate: n/a")
    print(f"    Accepted: {plat.get('accepted', 0)} | Rejected: {plat.get('rejected', 0)}")
    print("\n  Brain:")
    print(f"    CONFIRMED: {brain.get('confirmed', 0)} | DA killed: {brain.get('da_killed', 0)}")
    print(f"    Browser rejected: {brain.get('browser_rejected', 0)} | Potential: {brain.get('potential', 0)}")
    print("\n  Findings:")
    print(f"    Total JSON: {findings.get('total_findings', 0)} | Judge CONFIRM: {findings.get('judge_confirmed', 0)}")
    mix = findings.get("severity_mix") or {}
    if mix:
        print(f"    Severity mix: {mix}")
    print("\n  Sessions:")
    print(f"    Count: {sessions.get('count', 0)}")
    cps = sessions.get("judge_confirmed_per_session")
    print(f"    CONFIRM/session: {cps:.3f}" if cps is not None else "    CONFIRM/session: n/a")


def cmd_snapshot(args: argparse.Namespace) -> int:
    out = save_snapshot(Path(args.root), args.target or "", args.label)
    doc = json.loads(out.read_text(encoding="utf-8"))
    print_report(doc)
    print(f"\nWROTE: {out}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    cmp = compare_snapshots(baseline, after)
    print("\n📈 Baseline vs after")
    for key, val in cmp.items():
        if key == "improved":
            continue
        if val is None:
            print(f"  {key}: n/a")
        else:
            sign = "+" if val > 0 else ""
            print(f"  {key}: {sign}{val:.4f}")
    improved = cmp.get("improved")
    if improved is True:
        print("\n  Verdict: IMPROVED")
    elif improved is False:
        print("\n  Verdict: NOT IMPROVED (review before expanding Tier 0)")
    else:
        print("\n  Verdict: INSUFFICIENT DATA")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    print_report(compute_metrics(Path(args.root), target=args.target or ""))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline outcome metrics (v4)")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot", help="Capture metrics snapshot to brain/metrics/")
    snap.add_argument("--target", default="", help="Target slug filter")
    snap.add_argument("--label", default="baseline", help="Snapshot label (baseline|after|...)")
    snap.set_defaults(func=cmd_snapshot)

    cmp_p = sub.add_parser("compare", help="Compare two snapshot files")
    cmp_p.add_argument("--baseline", required=True)
    cmp_p.add_argument("--after", required=True)
    cmp_p.set_defaults(func=cmd_compare)

    rep = sub.add_parser("report", help="Print current metrics without saving")
    rep.add_argument("--target", default="")
    rep.set_defaults(func=cmd_report)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
