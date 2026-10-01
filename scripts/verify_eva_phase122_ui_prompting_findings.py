"""Standalone verifier for Phase 122 (found by prompting NOVA through its chat UI).

1. No planner prompt carried today's date: "search the web for who won the 2026
   FIFA World Cup" answered "it has not happened yet" in October 2026.
2. "list my rules" went through the planner (26.7s).
3. Daily rules compared "at 09:00" against UTC and fired at 04:36 Pacific.
4. The model copied an old approval prompt, id included, out of the history;
   confirming it said "Confirmed ... Ready to execute" and ran nothing.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
failures = 0


def emit(case: str, ok: bool, **extra: object) -> int:
    payload = {"case": case, "pass": bool(ok)}
    payload.update(extra)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if ok else 1


try:
    from backend.eva.agent import planner as planner_mod
    from backend.eva.agent.planner import PlannerDecision
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.proactivity import triggers
    from backend.eva.proactivity.models import ProactiveRule

    rule_text = planner_mod._freshness_rule()
    failures += emit("planner prompts carry today's date", str(datetime.now().year) in rule_text and "web_search" in rule_text)

    reply = maybe_handle_fast_command("list my rules", None, {})
    failures += emit("'list my rules' is answered without the planner", bool(reply) and reply[1] == "fast-command")

    saved = triggers._local_tz
    try:
        triggers._local_tz = lambda: timezone(timedelta(hours=-7))
        rule = ProactiveRule.__new__(ProactiveRule)
        for key, value in {"id": "r", "name": "r", "kind": "daily", "spec": {"at": "09:00"}, "enabled": True, "state": {}, "last_fired_at": None}.items():
            object.__setattr__(rule, key, value)
        early = triggers.should_fire(rule, datetime(2026, 10, 1, 11, 36, tzinfo=timezone.utc))[0]
        on_time = triggers.should_fire(rule, datetime(2026, 10, 1, 16, 1, tzinfo=timezone.utc))[0]
        failures += emit("a daily rule fires at the LOCAL time", early is False and on_time is True, early=early, on_time=on_time)
    finally:
        triggers._local_tz = saved

    masked = planner_mod._mask_action_ids([{"role": "assistant", "content": "confirm override act_343dbee85b5f"}])
    imitated = planner_mod._refuse_imitated_approval(
        PlannerDecision(type="answer", reason="", tool_calls=[], final_response="Say `confirm act_0123456789ab`")
    )
    failures += emit(
        "the planner cannot replay an approval prompt",
        "act_343dbee85b5f" not in masked[0]["content"] and "act_" not in imitated.final_response,
    )

    from backend.eva.core.operator_commands import _url_from_message
    from backend.eva.tools.power_info import _PowerStatus, battery_from_status

    failures += emit(
        "a link is opened only when asked to open it",
        _url_from_message("open https://example.com") == "https://example.com"
        and _url_from_message("summarize the page at https://example.com") is None,
    )
    battery = battery_from_status(_PowerStatus(ACLineStatus=1, BatteryFlag=1, BatteryLifePercent=80, BatteryLifeTime=0xFFFFFFFF))
    failures += emit("battery is read, not disclaimed", battery.get("battery_percent") == 80, battery=battery)
    piper_src = (ROOT / "backend" / "eva" / "voice" / "piper.py").read_text(encoding="utf-8")
    failures += emit("Piper is fed UTF-8", 'encoding="utf-8"' in piper_src)

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 122", "| 122 |" in readme)
except Exception as exc:  # pragma: no cover
    failures += emit("checks ran", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
raise SystemExit(0 if failures == 0 else 1)
