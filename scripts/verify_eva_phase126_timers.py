"""Standalone verifier for Phase 126 (timers and one-off reminders, no LLM).

1. Closed-list phrasings parse to the right instant; non-schedules and substring
   look-alikes are refused so ordinary requests reach the planner.
2. Local time, tomorrow rollover, the 5s floor and the 7-day cap.
3. A one-shot never fires early, fires once at its instant, never twice, and a
   racing second claim loses.
4. Firing NOTIFIES (in-app + notifier) and never enqueues an executable task.
5. Fast commands create / list / cancel; rule creation stays off the planner.
6. The timer poll is fine-grained (<= 5s) versus the 60s scheduler cycle.
7. Both planner rule lists carry the "ask me to set a timer" guidance.
8. README records Phase 126.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
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
    tmp = Path(tempfile.mkdtemp(prefix="nova_p126_"))
    os.environ["EVA_PROACTIVITY_ENABLED"] = "1"
    os.environ["EVA_PROACTIVITY_PATH"] = str(tmp / "rules.sqlite3")
    os.environ["EVA_TOASTS"] = "0"

    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.proactivity.engine import ProactivityEngine
    from backend.eva.proactivity.store import ProactivityStore
    from backend.eva.proactivity.timers import parse_once_request
    from backend.eva.runtime.scheduler import run_timer_loop, timer_poll_interval
    from backend.eva.tasks.durable_queue import DurableTaskQueue

    PDT = timezone(timedelta(hours=-7))
    NOW = datetime(2026, 10, 1, 19, 0, tzinfo=timezone.utc)  # 12:00 PDT

    def P(text, now=NOW):
        return parse_once_request(text, now, PDT)

    matrix = [
        ("set a timer for 5 minutes", 300), ("timer 10 min", 600), ("5 minute timer", 300),
        ("remind me in 20 minutes to stretch", 1200), ("set a timer for 1 hour 30 minutes", 5400),
        ("set a timer for 2 seconds", 5),
    ]
    for text, secs in matrix:
        p = P(text)
        failures += emit(f"parses: {text}", p is not None and not p.error and p.seconds == secs,
                         seconds=getattr(p, "seconds", None))

    refused = ["remind me what I said earlier", "what time is it", "timer settings", "set the oven to 5 minutes",
               "reset a timer for 5 minutes", "I will set a timer for 5 minutes tomorrow", "set a timer for 2 days",
               "remind me every day at 9 to stretch"]
    for text in refused:
        failures += emit(f"refuses: {text}", P(text) is None)

    six = P("remind me at 6 pm to call mom")
    failures += emit("at 6 pm is LOCAL 6 pm today",
                     six.at_utc == datetime(2026, 10, 2, 1, 0, tzinfo=timezone.utc) and six.day_word == "today",
                     at=str(six.at_utc))
    late = P("remind me at 6 pm to call mom", now=datetime(2026, 10, 2, 2, 0, tzinfo=timezone.utc))
    failures += emit("6 pm when it is 7 pm goes to tomorrow", late.day_word == "tomorrow" and late.at_utc.day == 3)
    nine = P("remind me tomorrow at 9 to submit the form")
    failures += emit("tomorrow at 9",
                     nine.at_utc == datetime(2026, 10, 2, 16, 0, tzinfo=timezone.utc) and nine.text == "submit the form")
    failures += emit("cap: 169 hours is an error, not clamped", bool(P("set a timer for 169 hours").error))

    store = ProactivityStore(tmp / "engine.sqlite3")
    queue = DurableTaskQueue(tmp / "q.sqlite3")
    sent: list = []
    engine = ProactivityEngine(store, queue, notifier=lambda t, b: sent.append((t, b)))
    parsed = P("remind me in 5 minutes to delete my files")
    rule = store.add_rule(**parsed.as_add_rule_kwargs())
    early = engine.tick(parsed.at_utc - timedelta(seconds=1))
    failures += emit("never early", early["notified"] == [] and store.list_notifications() == [])
    first = engine.tick(parsed.at_utc)
    again = [engine.tick(parsed.at_utc + timedelta(seconds=s))["notified"] for s in (0, 1, 3600)]
    failures += emit("fires once at the instant, never twice",
                     len(first["notified"]) == 1 and again == [[], [], []]
                     and len(store.list_notifications()) == 1 and len(sent) == 1)
    failures += emit("notifies, enqueues nothing executable",
                     queue.list_tasks() == [] and first["proposed"] == []
                     and store.list_notifications()[0].message == "Reminder: delete my files")
    failures += emit("a stale second claim loses", engine._fire_once(rule, parsed.at_utc, "x") is None)

    def say(text):
        r = maybe_handle_fast_command(text, None, {})
        return r[0] if r and r[1] == "fast-command" else None

    created = say("set a timer for 5 minutes")
    failures += emit("creation reply",
                     bool(created) and created.startswith("Timer set for 5 minutes — I'll notify you at "),
                     reply=created)
    failures += emit("timers lists it", "5 minutes" in (say("timers") or "") and "5 minutes" in (say("my reminders") or ""))
    say("set a timer for 10 minutes")
    failures += emit("cancel with two active lists, cancels none",
                     "2 active timers" in (say("cancel my timer") or "") and "(2)" in (say("timers") or ""))
    say("cancel all timers")
    failures += emit("cancel all clears them", "No active timers" in (say("timers") or ""))
    say("set a timer for 5 minutes")
    failures += emit("cancel with exactly one cancels it",
                     (say("cancel the timer") or "").startswith("Cancelled:") and "No active timers" in (say("timers") or ""))

    from backend.eva.tools.registry import ToolRegistry

    names = " ".join(t["name"] for t in ToolRegistry().list_tools()).lower()
    failures += emit("not a planner tool", not any(w in names for w in ("timer", "remind", "add_rule", "schedule")))

    interval = timer_poll_interval({})
    store2 = ProactivityStore(tmp / "loop.sqlite3")
    past = datetime.now(timezone.utc) - timedelta(minutes=2)
    store2.add_rule(**parse_once_request("set a timer for 1 minute", past).as_add_rule_kwargs())
    eng2 = ProactivityEngine(store2, None)

    async def nap(_):
        return None

    asyncio.run(run_timer_loop(eng2, max_cycles=2, sleep=nap, interval=interval))
    failures += emit("timer poll is fine-grained and fires",
                     interval <= 5 and len(store2.list_notifications()) == 1, poll_seconds=interval)

    src = (ROOT / "backend/eva/agent/planner.py").read_text(encoding="utf-8")
    failures += emit("both planner lists mention timers", src.count("set a timer for 5 minutes") >= 2)

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 126", "| 126 |" in readme)
except Exception as exc:  # pragma: no cover
    failures += emit("checks ran", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
raise SystemExit(0 if failures == 0 else 1)
