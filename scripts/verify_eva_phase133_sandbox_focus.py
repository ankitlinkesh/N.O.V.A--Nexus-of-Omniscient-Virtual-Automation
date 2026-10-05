"""Standalone verifier for Phase 133 ("your terminal/box" questions are about the box).

Runs the REAL run_agentic_task with a scripted planner and a fake WSL runner:
1. The matcher accepts "your terminal/box/sandbox" requests and rejects "my battery",
   "put it in the box", "check my inbox".
2. Outside a scope system_status/status are offered; inside they are removed.
3. A sandbox-focused task: the planner is never offered system_status, a forced
   system_status call is refused without reaching the executor, and sandbox_run runs.
4. A normal task still runs system_status.
5. The scope is closed after the task. README records the phase.
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
    import backend.eva.shell.sandbox_terminal as st
    from backend.eva.agent.executor import ToolExecutor
    from backend.eva.agent.planner import PlannedToolCall, PlannerDecision
    from backend.eva.agent.runner import run_agentic_task
    from backend.eva.shell.sandbox_focus import SANDBOX_FOCUS_HIDDEN, open_sandbox_focus, sandbox_focus_open, wants_sandbox_focus
    from backend.eva.tools.registry import ToolRegistry

    yes = ["use your terminal to check how much disk space you have", "in your box, how much memory is free", "what OS is your sandbox running"]
    no = ["how much disk space do I have", "check my battery", "put it in the box", "check my inbox"]
    failures += emit("matcher", all(wants_sandbox_focus(g) for g in yes) and not any(wants_sandbox_focus(g) for g in no))

    registry = ToolRegistry()
    before = {s["name"] for s in registry.planner_specs()}
    with open_sandbox_focus():
        inside = {s["name"] for s in registry.planner_specs()}
    failures += emit(
        "planner_specs hides only the status tools inside the scope",
        "system_status" in before and inside == before - SANDBOX_FOCUS_HIDDEN and not sandbox_focus_open(),
    )

    class Planner:
        def __init__(self, reg, decisions):
            self.reg, self.decisions, self.offered = reg, decisions, []

        async def plan(self, goal, history, mode="agent_step", task_context=None):
            self.offered.append({s["name"] for s in self.reg.planner_specs()})
            return self.decisions[min(len(self.offered) - 1, len(self.decisions) - 1)]

    def call(tool, **args):
        return PlannerDecision(type="tool_calls", reason="s", tool_calls=[PlannedToolCall(tool=tool, args=args)], final_response="", continue_after_tools=True)

    done = PlannerDecision(type="done", reason="f", tool_calls=[], final_response="ok", continue_after_tools=False)

    class FakeWsl:
        def __init__(self):
            self.execs = 0

        def __call__(self, argv, timeout, env):
            if "--list" in argv:
                return SimpleNamespace(returncode=0, stdout=b"nova\n", stderr=b"")
            self.execs += 1
            return SimpleNamespace(returncode=0, stdout=b"Filesystem Size\n", stderr=b"")

    def run(goal, decisions):
        reg = ToolRegistry()
        ex = ToolExecutor(reg)
        ran: list[str] = []
        real = ex.execute

        def spy(c, *a, **k):
            ran.append(c.tool)
            return real(c, *a, **k)

        ex.execute = spy  # type: ignore[method-assign]
        planner = Planner(reg, decisions)
        ctx = {"planner": planner, "registry": reg, "executor": ex, "execute_tools": True, "session_id": "v133", "goal_from_user": True}
        res = asyncio.run(run_agentic_task(goal, ctx))
        return res, planner, ran

    fake = FakeWsl()
    original = st._default_runner
    st._default_runner = fake
    try:
        res, planner, ran = run("use your terminal to check how much disk space you have", [call("system_status"), call("sandbox_run", command="df -h"), done])
        failures += emit(
            "focused task: status never offered, forced call refused, sandbox ran",
            all("system_status" not in o and "status" not in o for o in planner.offered) and ran == ["sandbox_run"] and fake.execs == 1 and res["status"] == "done",
            ran=ran,
        )
        res, planner, ran = run("how much disk space do I have", [call("system_status"), done])
        failures += emit("normal task still runs system_status", ran == ["system_status"] and fake.execs == 1 and res["status"] == "done", ran=ran)
    finally:
        st._default_runner = original
    failures += emit("scope closed after the task", not sandbox_focus_open())

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 133", "| 133 |" in readme)
except Exception as exc:  # a crash is a failure, never a pass
    failures += emit("verifier crashed", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
sys.exit(0 if failures == 0 else 1)
