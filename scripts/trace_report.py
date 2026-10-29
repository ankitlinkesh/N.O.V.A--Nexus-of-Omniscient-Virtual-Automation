"""Summarize NOVA's flight-recorder traces: how agent tasks actually went.

    .venv/Scripts/python.exe scripts/trace_report.py [--dir PATH] [--last N] [--json]

Reads the JSONL traces the agent loop writes when ``EVA_TRACING_ENABLED=1`` (default folder:
``<data root>/traces``; ``EVA_DATA_DIR`` moves it) and reports, per trace and in total:

  * how many tool calls ran, how many results were independently verified, and how many
    were blocked or paused by the permission gate;
  * how the critic judged each task (accepted or not) and how many tasks ended
    "unsupported claim" (reported done with no step matching what the goal asked for);
  * tool usage by name and the slowest and most failure-prone tools.

This is the measurement base for changes to the planner, the tool menu and the grounding:
run a scorecard (``scripts/pc_scorecard.py``) before and after with tracing on, and compare
these numbers instead of trusting one run. Read-only; it never writes or deletes a trace.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def default_dir() -> Path:
    base = os.environ.get("EVA_DATA_DIR")
    if base:
        return Path(base) / "backend" / "eva" / "data" / "traces"
    return ROOT / "backend" / "eva" / "data" / "traces"


def read_events(path: Path) -> list[dict]:
    events: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                events.append(event)
    except OSError:
        pass
    return events


def summarize(events: list[dict]) -> dict:
    kinds = Counter(str(event.get("type")) for event in events)
    tools = Counter()
    gate = Counter()
    verified = unverified = 0
    request = ""
    critic = None
    unsupported = False
    for event in events:
        payload = event.get("payload") or {}
        kind = event.get("type")
        if kind == "trace_started":
            request = str(payload.get("user_request") or "")[:100]
        elif kind == "tool_call":
            tools[str(payload.get("tool_name"))] += 1
        elif kind == "permission":
            gate[str(payload.get("decision"))] += 1
        elif kind == "verification":
            if payload.get("verified"):
                verified += 1
            else:
                unverified += 1
        elif kind == "critic":
            critic = payload
            unsupported = unsupported or "unsupported_claim" in (payload.get("reasons") or [])
    return {
        "request": request,
        "events": len(events),
        "tool_calls": sum(tools.values()),
        "tools": dict(tools),
        "gate": dict(gate),
        "verified": verified,
        "unverified": unverified,
        "critic_satisfied": None if critic is None else bool(critic.get("satisfied")),
        "unsupported_claim": unsupported,
        "threats": kinds.get("threat", 0),
        "ended": kinds.get("trace_ended", 0) > 0,
    }


def aggregate(rows: list[dict]) -> dict:
    tools = Counter()
    gate = Counter()
    for row in rows:
        tools.update(row["tools"])
        gate.update(row["gate"])
    judged = [row for row in rows if row["critic_satisfied"] is not None]
    return {
        "traces": len(rows),
        "tool_calls": sum(row["tool_calls"] for row in rows),
        "avg_tool_calls": round(sum(row["tool_calls"] for row in rows) / len(rows), 2) if rows else 0,
        "verified_effects": sum(row["verified"] for row in rows),
        "unverified_effects": sum(row["unverified"] for row in rows),
        "unsupported_claims": sum(1 for row in rows if row["unsupported_claim"]),
        "tasks_with_threat_markers": sum(1 for row in rows if row["threats"]),
        "critic_accepted": sum(1 for row in judged if row["critic_satisfied"]),
        "critic_judged": len(judged),
        "gate_decisions": dict(gate),
        "top_tools": tools.most_common(10),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dir", type=Path, default=None, help="trace folder (default: the data root's traces)")
    parser.add_argument("--last", type=int, default=50, help="newest N traces to read (default 50)")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)
    folder = args.dir or default_dir()
    files = sorted((p for p in folder.glob("*.jsonl")), key=lambda p: p.stat().st_mtime, reverse=True)[: max(1, args.last)] if folder.is_dir() else []
    if not files:
        print(f"No traces in {folder}. Turn them on with EVA_TRACING_ENABLED=1 and run some tasks.", file=sys.stderr)
        return 1
    rows = [summarize(read_events(path)) for path in files]
    total = aggregate(rows)
    if args.json:
        print(json.dumps({"total": total, "traces": rows}, ensure_ascii=False, indent=2))
        return 0
    print(f"{total['traces']} trace(s) from {folder}")
    print(f"  tool calls: {total['tool_calls']} (avg {total['avg_tool_calls']} per trace)")
    print(f"  effects independently verified: {total['verified_effects']}, not verified: {total['unverified_effects']}")
    print(f"  critic accepted {total['critic_accepted']} of {total['critic_judged']} judged task(s); reported done without evidence of the goal: {total['unsupported_claims']}; tasks with threat markers: {total['tasks_with_threat_markers']}")
    print(f"  gate decisions: {total['gate_decisions'] or 'none recorded'}")
    print("  most used tools: " + (", ".join(f"{name} x{count}" for name, count in total["top_tools"]) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
