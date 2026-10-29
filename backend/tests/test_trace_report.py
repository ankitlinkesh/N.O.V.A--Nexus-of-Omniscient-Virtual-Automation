"""scripts/trace_report.py summarizes real flight-recorder traces and never writes."""

import importlib.util
import json
from pathlib import Path

from backend.eva.observability.local_trace_store import LocalTraceStore

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "trace_report.py"
spec = importlib.util.spec_from_file_location("trace_report", SCRIPT)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def _write(store, trace, request, calls, verified, critic):
    store.append(trace, "trace_started", {"request_id": trace, "user_request": request})
    for tool in calls:
        store.append(trace, "permission", {"tool_name": tool, "decision": "allow"})
        store.append(trace, "tool_call", {"tool_name": tool, "args": {}, "result_summary": "ok"})
    for flag in verified:
        store.append(trace, "verification", {"tool_name": "x", "verified": flag})
    store.append(trace, "critic", critic)
    store.append(trace, "trace_ended", {"final_summary": "done"})


def test_report_counts_tools_verification_and_unsupported_claims(tmp_path, capsys):
    store = LocalTraceStore(tmp_path)
    _write(store, "a", "open calculator", ["open_app"], [True], {"satisfied": True, "reasons": []})
    _write(store, "b", "open calculator and click seven", ["open_app", "open_app"], [True, False], {"satisfied": False, "reasons": ["unsupported_claim"]})
    rows = [report.summarize(report.read_events(p)) for p in sorted(tmp_path.glob("*.jsonl"))]
    total = report.aggregate(rows)
    assert total["traces"] == 2 and total["tool_calls"] == 3 and total["verified_effects"] == 2 and total["unverified_effects"] == 1
    assert total["unsupported_claims"] == 1 and total["critic_accepted"] == 1 and total["critic_judged"] == 2
    assert total["top_tools"][0] == ("open_app", 3) and total["gate_decisions"] == {"allow": 3}

    assert report.main(["--dir", str(tmp_path)]) == 0
    assert "reported done without evidence of the goal: 1" in capsys.readouterr().out
    assert report.main(["--dir", str(tmp_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["total"]["traces"] == 2


def test_report_survives_missing_folder_and_garbage_lines(tmp_path, capsys):
    assert report.main(["--dir", str(tmp_path / "nope")]) == 1
    (tmp_path / "bad.jsonl").write_text("not json\n{\"type\": \"tool_call\", \"payload\": {\"tool_name\": \"t\"}}\n[]\n", encoding="utf-8")
    assert report.summarize(report.read_events(tmp_path / "bad.jsonl"))["tool_calls"] == 1
    assert (tmp_path / "bad.jsonl").read_text(encoding="utf-8").startswith("not json")
