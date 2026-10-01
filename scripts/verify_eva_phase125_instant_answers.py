"""Standalone verifier for Phase 125 (instant answers, no LLM).

Every tool is faked and the LLM is rigged to raise if called.

1. Each closed-list phrasing hits its one tool and answers from a template.
2. Near-misses and compound requests decline (reach the planner untouched).
3. The templates only state what the tool result contains.
4. A single successful call to a templated tool skips the synthesis LLM call; web_search, failures and multi-call keep it.
5. README records Phase 125.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
failures = 0


def emit(case: str, ok: bool, **extra: object) -> int:
    payload = {"case": case, "pass": bool(ok)}
    payload.update(extra)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if ok else 1


try:
    import backend.eva.api.routes as routes
    import backend.eva.llm.router as llm_router
    from backend.eva.agent.executor import ToolExecutionResult
    from backend.eva.core.fast_commands import maybe_handle_fast_command

    llm_calls: list = []

    async def rigged(*a, **k):
        llm_calls.append(1)
        return SimpleNamespace(response=SimpleNamespace(ok=True, text="LLM sentence", provider="p", model="m"))

    llm_router.complete_with_fallback = rigged
    routes.complete_with_fallback = rigged

    TIME = {"ok": True, "local_time_12h": "2:05 PM", "local_date": "2026-10-01", "weekday": "Thursday", "timezone": "UTC"}
    STATUS = {"battery_present": True, "battery_percent": 81, "plugged_in": True, "memory_percent_used": 47,
              "memory_total_gb": 15.8, "disks": [{"drive": "C:", "free_gb": 5.1, "total_gb": 237.0}]}
    WINDOWS = {"ok": True, "windows": [{"title": "Notes - Notepad", "process_name": "Notepad.exe"},
                                        {"title": "Program Manager", "process_name": "explorer.exe"}]}
    LISTING = {"ok": True, "path": "C:/Users/X/Downloads", "items": ["a"], "total": 48}
    DATA = {"system_time": TIME, "system_status": STATUS, "window_list": WINDOWS, "file.list_dir": LISTING}

    class Tools:
        def __init__(self):
            self.calls = []

        def run(self, name, **kw):
            self.calls.append(name)
            return DATA[name]

    cases = [
        ("what time is it", "system_time", "2:05 PM"),
        ("what's today's date", "system_time", "October 1, 2026"),
        ("what's my battery level?", "system_status", "81%"),
        ("how much free space is on my C drive?", "system_status", "C: has 5.1 GB free of 237.0 GB"),
        ("memory usage", "system_status", "47%"),
        ("which windows are open", "window_list", "Notes - Notepad"),
        ("how many files are in my Downloads folder?", "file.list_dir", "48 items"),
    ]
    for text, tool, needle in cases:
        t = Tools()
        reply = maybe_handle_fast_command(text, t, {})
        failures += emit(f"instant: {text}", bool(reply) and needle in reply[0] and t.calls == [tool] and not llm_calls,
                         reply=reply, calls=t.calls)

    for text in ("what time is the meeting tomorrow", "is the battery in my car good", "what time is it in Tokyo",
                 "how much free space does Google Drive give", "what time is it and open chrome"):
        t = Tools()
        failures += emit(f"declines: {text}", maybe_handle_fast_command(text, t, {}) is None and not t.calls)

    t = Tools()
    reply = maybe_handle_fast_command("which windows are open", t, {})
    failures += emit("system/overlay windows are hidden", "Program Manager" not in reply[0])

    def run(msg, results):
        return asyncio.run(routes._synthesize_tool_response(msg, results, [], SimpleNamespace(models=None)))

    R = ToolExecutionResult
    reply, source = run("time", [R(ok=True, tool="system_time", result=TIME)])
    failures += emit("single templated call skips synthesis LLM", source == "tool-template" and not llm_calls, reply=reply)

    run("search", [R(ok=True, tool="web_search", result={"ok": True})])
    run("time", [R(ok=False, tool="system_time", result={}, error="boom")])
    run("both", [R(ok=True, tool="system_time", result=TIME), R(ok=True, tool="system_status", result=STATUS)])
    failures += emit("web_search, failure and multi-call keep the LLM", len(llm_calls) == 3, llm_calls=len(llm_calls))

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 125", "| 125 |" in readme)
except Exception as exc:  # pragma: no cover
    failures += emit("checks ran", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
raise SystemExit(0 if failures == 0 else 1)
