"""Replay real routing failures through NOVA and score the behaviour.

    .venv/Scripts/python.exe scripts/eval_routing.py                      # rules-only, deterministic, no LLM
    .venv/Scripts/python.exe scripts/eval_routing.py --mode llm_first_offline
    .venv/Scripts/python.exe scripts/eval_routing.py --llm                # needs llama-server already running on :8080
    .venv/Scripts/python.exe scripts/eval_routing.py --case wa_say_hi_to_kutty --verbose

Nothing is sent and no app is touched: every handler, the WhatsApp sender, Chrome, key input,
subprocess and non-loopback network are stubbed. Data goes to a temp dir, never to data/.

Exit code: 0 clean; 1 when a must-be-zero metric is violated (unconfirmed executions, invented
sends in rules mode) or a case that should pass fails (regression); 2 for usage errors.
XFAIL (known bug still present) and XPASS (known bug fixed) do not fail the run unless
--strict-xpass is given.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=("rules", "llm_first_offline", "llm"), default="rules",
                        help="rules = EVA_ROUTING=rules_first, no LLM (default); llm_first_offline = production order with no LLM; llm = real local model")
    parser.add_argument("--llm", action="store_true", help="shorthand for --mode llm (only if the llama server is already up)")
    parser.add_argument("--case", action="append", default=[], help="run only this case id (repeatable)")
    parser.add_argument("--tag", action="append", default=[], help="run only cases with this tag (repeatable)")
    parser.add_argument("--cases-module", action="append", default=[], help="dotted module with a CASES list to add")
    parser.add_argument("--out", help="JSON report path (default: a temp file; never data/)")
    parser.add_argument("--json", action="store_true", help="print the JSON summary only")
    parser.add_argument("--verbose", "-v", action="store_true", help="show each turn's reply")
    parser.add_argument("--strict-xpass", action="store_true", help="fail when a known_failing case now passes")
    args = parser.parse_args(argv)
    mode = "llm" if args.llm else args.mode

    from backend.eva.evals.cases import load_cases
    from backend.eva.evals.runner import LLM_URL, llm_server_up, run_cases
    from backend.eva.evals import scoring

    if mode == "llm" and not llm_server_up():
        print(f"LLM mode requested but nothing answers {LLM_URL}/health. The harness never starts the model server; start it yourself and re-run.")
        return 0

    cases = load_cases(args.cases_module)
    if args.case:
        unknown = sorted(set(args.case) - {case.id for case in cases})
        if unknown:
            print("unknown case id(s): " + ", ".join(unknown), file=sys.stderr)
            return 2
        cases = [case for case in cases if case.id in set(args.case)]
    if args.tag:
        cases = [case for case in cases if set(args.tag) & set(case.tags)]
    if not cases:
        print("no cases selected", file=sys.stderr)
        return 2

    from backend.eva.core.data_paths import live_data_changes, live_data_snapshot

    live_before = live_data_snapshot()
    runs = run_cases(cases, mode)
    results = [scoring.evaluate(run) for run in runs]
    summary = scoring.aggregate(results, mode)
    live_changed = live_data_changes(live_before)
    summary["live_data_changed_paths"] = len(live_changed)  # informational: the NOVA server may be running and writing
    report = scoring.to_report(results, summary)

    out = Path(args.out) if args.out else Path(tempfile.gettempdir()) / "eva_eval_routing_report.json"
    if _in_live_data(out):
        print("refusing to write the report under a live data directory; pick another --out", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(scoring.format_table(results))
        if args.verbose:
            for run, result in zip(runs, results):
                print(f"\n[{result.case.id}] {result.case.description}")
                for turn in run.turns:
                    print(f"  user:  {turn.message!r}  (route={turn.route}, source={turn.source})")
                    print(f"  reply: {turn.reply[:300]!r}")
                for check in result.failures:
                    print(f"  FAILED CHECK {check.name}: {check.detail}")
        print()
        print(scoring.format_metrics(summary))
        print(f"\nJSON report: {out}")
        if live_changed:
            print(f"note: {len(live_changed)} path(s) under the live data dirs changed while this ran (is the NOVA server running?); the harness itself writes only to a temp dir.")

    problems = scoring.violations(summary, strict_xpass=args.strict_xpass)
    if problems:
        print("\nFAILED: " + "; ".join(problems), file=sys.stderr)
        return 1
    if summary["xpass"]:
        print("\nnote: known_failing cases now pass, flip the flag: " + ", ".join(summary["xpass"]))
    return 0


def _in_live_data(path: Path) -> bool:
    from backend.eva.core.data_paths import LIVE_DATA_ROOTS

    resolved = path.resolve()
    for live in LIVE_DATA_ROOTS:
        try:
            resolved.relative_to(live.resolve())
            return True
        except ValueError:
            continue
    return False


if __name__ == "__main__":
    raise SystemExit(main())
