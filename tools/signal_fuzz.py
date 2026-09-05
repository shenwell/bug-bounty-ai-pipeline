#!/usr/bin/env python3
"""Signal-fuzz layer — seeds → mutations → oracles → trace-hash schedule."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from fuzzingbook import DeltaDebuggingReducer  # noqa: E402
from signal_fuzz.corpus import (  # noqa: E402
    CORPUS_DEFAULT,
    build_corpus,
    load_corpus,
    save_corpus,
)
from signal_fuzz.export import export_signals, load_fuzz_signals, load_run_state, save_run_state  # noqa: E402
from signal_fuzz.runner import exec_request, run_greybox  # noqa: E402
from signal_fuzz.validate import validate_compose  # noqa: E402


def cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.root)
    ok, messages = validate_compose(root)
    for msg in messages:
        print(msg)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


def cmd_build_corpus(args: argparse.Namespace) -> int:
    root = Path(args.root)
    merge = Path(args.merge) if args.merge else None
    seeds = build_corpus(root, write_mode=args.write_mode, merge_existing=merge)
    out_arg = Path(args.output) if args.output else None
    if out_arg and not out_arg.is_absolute():
        out_arg = root / out_arg
    out = save_corpus(root, seeds, out_arg)
    print(f"WROTE {len(seeds)} seeds -> {out}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    root = Path(args.root)
    summary = run_greybox(
        root,
        write_mode=args.write_mode,
        limit=args.limit,
        energy_budget=args.energy_budget,
        max_rps=args.max_rps,
        corpus_path=Path(args.corpus) if args.corpus else None,
        disruption_approved=args.disruption_approved,
    )
    print(json.dumps(summary, indent=2))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    root = Path(args.root)
    out_arg = Path(args.output) if args.output else None
    if out_arg and not out_arg.is_absolute():
        out_arg = root / out_arg
    out, signals = export_signals(
        root,
        output=out_arg,
        target=args.target or "",
    )
    print(f"EXPORTED {len(signals)} oracle+readback signals -> {out}")
    return 0


def cmd_reduce(args: argparse.Namespace) -> int:
    root = Path(args.root)
    state = load_run_state(root)
    signals = state.get("queued_signals") or load_fuzz_signals(root)
    target = None
    for sig in signals:
        if sig.get("id") == args.signal_id:
            target = sig
            break
    if not target:
        print(f"signal not found: {args.signal_id}")
        return 1

    def test(pair_bundle: dict) -> bool:
        template = pair_bundle.get("repro_template") or {}
        seed = {
            "endpoint": template.get("path") or target.get("endpoint"),
            "method": template.get("method", "GET"),
            "auth_role": template.get("session_role", "A"),
            "query": {},
            "body_template": {},
        }
        baseline = exec_request(seed, root, role=str(template.get("session_role", "A")))
        mutant = dict(seed)
        mutant["query"] = {"_m": "1"}
        resp = exec_request(mutant, root, role=str(template.get("session_role", "A")))
        return baseline.get("status") != resp.get("status") or baseline.get("body") != resp.get("body")

    reducer = DeltaDebuggingReducer(test, max_reruns=args.max_reruns)
    reduced = reducer.reduce({"repro_template": target.get("repro_template") or {}})
    template = reduced.get("repro_template") or {}
    reduced["readback_curl_template"] = target.get("readback_curl_template") or ""
    reduced["minimal_repro"] = {
        "exploit_curl": (
            f"curl -s -X {template.get('method', 'GET')} "
            f"'{template.get('path')}' # session_role={template.get('session_role', 'A')}"
        ),
        "readback_curl": target.get("readback_curl_template") or "",
    }
    out_path = root / "brain" / "fuzz-corpus" / f"reduced-{args.signal_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(reduced, indent=2) + "\n", encoding="utf-8")
    if args.finding:
        try:
            from finding_record import load_finding, save_finding

            rec_path = Path(args.finding)
            rec = load_finding(rec_path)
            if rec:
                rec.setdefault("evidence", {})
                rec["evidence"]["exploit_curl"] = reduced["minimal_repro"]["exploit_curl"]
                rec["evidence"]["readback_curl"] = reduced["minimal_repro"]["readback_curl"]
                save_finding(rec_path, rec)
                print(f"UPDATED finding: {rec_path}")
        except Exception as exc:
            print(f"WARN finding update failed: {exc}")
    print(f"REDUCED -> {out_path} (reruns={reducer.reruns})")
    return 0


def cmd_coverage_status(args: argparse.Namespace) -> int:
    root = Path(args.root)
    host = args.host or ""
    pattern = f"evidence/{host}/signal-fuzz/attempts.jsonl" if host else "evidence/**/signal-fuzz/attempts.jsonl"
    paths = list(root.glob(pattern))
    total = 0
    tiers: dict[str, int] = {}
    for p in paths:
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            total += 1
            try:
                row = json.loads(line)
                t = row.get("signal_tier") or "unknown"
                tiers[t] = tiers.get(t, 0) + 1
            except json.JSONDecodeError:
                pass
    pct = min(100, int(total / max(1, args.target_cells) * 100))
    print(json.dumps({"attempts": total, "tiers": tiers, "coverage_pct": pct}, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Signal-fuzz pipeline layer")
    parser.add_argument("--root", default=".")
    sub = parser.add_sub_parser = parser.add_subparsers(dest="command", required=True)

    val = sub.add_parser("validate")
    val.set_defaults(func=cmd_validate)

    bc = sub.add_parser("build-corpus")
    bc.add_argument("--output", default=str(CORPUS_DEFAULT))
    bc.add_argument("--write-mode", default="read-only", choices=["read-only", "owned-write", "disruption"])
    bc.add_argument("--merge", default="", help="Merge with existing corpus file")
    bc.set_defaults(func=cmd_build_corpus)

    run = sub.add_parser("run")
    run.add_argument("--write-mode", default="read-only", choices=["read-only", "owned-write", "disruption"])
    run.add_argument("--limit", type=int, default=50)
    run.add_argument("--energy-budget", type=int, default=200)
    run.add_argument("--max-rps", type=float, default=1.0)
    run.add_argument("--max-inflight", type=int, default=1)
    run.add_argument("--corpus", default="")
    run.add_argument("--disruption-approved", action="store_true")
    run.set_defaults(func=cmd_run)

    exp = sub.add_parser("export")
    exp.add_argument("--output", default="recon/fuzz-signals.json")
    exp.add_argument("--target", default="")
    exp.set_defaults(func=cmd_export)

    red = sub.add_parser("reduce")
    red.add_argument("--signal-id", required=True)
    red.add_argument("--max-reruns", type=int, default=20)
    red.add_argument("--finding", default="", help="Optional finding JSON to patch exploit/readback curls")
    red.set_defaults(func=cmd_reduce)

    cov = sub.add_parser("coverage-status")
    cov.add_argument("--endpoint", default="")
    cov.add_argument("--host", default="")
    cov.add_argument("--target-cells", type=int, default=25)
    cov.set_defaults(func=cmd_coverage_status)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
