"""Standalone verifier for Phase 135 (sandbox tasks keep their scope after an approval, and check before answering).

Runs the REAL run_agentic_task / confirmation round-trip with a scripted planner and a fake WSL runner:
1. A focused task whose planner says "done" first is sent back ONCE with the check observation, then runs
   sandbox_run and finishes.
2. A planner that says "done" twice without running anything is accepted the second time (no loop).
3. A non-focused task is never sent back; a focused task that already ran sandbox_run is accepted at once.
4. A sandbox-focused task that paused on a confirm (share.to_box) keeps the focus after `confirm`: the
   planner is never offered system_status again and a forced call is refused.
5. README records the phase.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
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


_real_home = Path.home
try:
    import backend.eva.shell.sandbox_terminal as st
    import backend.eva.tools.share_bridge as sb
    from backend.eva.agent import paused_tasks as paused
    from backend.eva.agent.executor import ToolExecutor
    from backend.eva.agent.planner import PlannedToolCall, PlannerDecision
    from backend.eva.agent.runner import SANDBOX_CHECK_FEEDBACK, run_agentic_task
    from backend.eva.permissions.confirmation import handle_confirmation_command
    from backend.eva.security import tool_gate
    from backend.eva.shell.sandbox_focus import sandbox_focus_open
    from backend.eva.tools.registry import ToolRegistry

    class Planner:
        def __init__(self, reg, decisions):
            self.reg, self.decisions, self.offered, self.seen = reg, decisions, [], []

        async def plan(self, goal, history, mode="agent_step", task_context=None):
            self.offered.append({s["name"] for s in self.reg.planner_specs()})
            self.seen.append(list((task_context or {}).get("observations") or []))
            return self.decisions[min(len(self.offered) - 1, len(self.decisions) - 1)]

    def call(tool, **args):
        return PlannerDecision(type="tool_calls", reason="s", tool_calls=[PlannedToolCall(tool=tool, args=args)], final_response="", continue_after_tools=True)

    def done(text="guess"):
        return PlannerDecision(type="done", reason="f", tool_calls=[], final_response=text, continue_after_tools=False)

    class FakeWsl:
        def __init__(self):
            self.execs = 0

        def __call__(self, argv, timeout, env):
            if "--list" in argv:
                return SimpleNamespace(returncode=0, stdout=b"nova\n", stderr=b"")
            self.execs += 1
            return SimpleNamespace(returncode=0, stdout=b"Ubuntu 24.04\n", stderr=b"")

    def run(goal, decisions, from_user=True):
        reg = ToolRegistry()
        ex = ToolExecutor(reg)
        ran: list[str] = []
        real = ex.execute

        def spy(c, *a, **k):
            ran.append(c.tool)
            return real(c, *a, **k)

        ex.execute = spy  # type: ignore[method-assign]
        planner = Planner(reg, decisions)
        ctx = {"planner": planner, "registry": reg, "executor": ex, "execute_tools": True, "session_id": "v135"}
        if from_user:
            ctx["goal_from_user"] = True
        return asyncio.run(run_agentic_task(goal, ctx)), planner, ran

    fake = FakeWsl()
    original = st._default_runner
    st._default_runner = fake
    GOAL = "what OS is your sandbox running"
    try:
        res, planner, ran = run(GOAL, [done(), call("sandbox_run", command="cat /etc/os-release"), done("Ubuntu 24.04")])
        failures += emit(
            "done first: sent back once, then sandbox_run runs",
            ran == ["sandbox_run"] and fake.execs == 1 and SANDBOX_CHECK_FEEDBACK in planner.seen[1] and res["status"] == "done",
            ran=ran,
        )
        before = fake.execs
        res, planner, ran = run(GOAL, [done("a"), done("b")])
        failures += emit("done twice: accepted the second time", ran == [] and fake.execs == before and len(planner.offered) == 2 and res["final_response"] == "b")
        res, planner, ran = run("tell me a joke", [done("joke")])
        failures += emit("non-focused task never sent back", len(planner.offered) == 1)
        res, planner, ran = run(GOAL, [call("sandbox_run", command="uname -a"), done("Linux")])
        failures += emit("focused task that already ran sandbox_run is accepted at once", len(planner.offered) == 2 and all(SANDBOX_CHECK_FEEDBACK not in o for o in planner.seen))

        tmp = Path(tempfile.mkdtemp(prefix="nova_v135_"))
        home = tmp / "home"
        for name in ("Documents", "Desktop", "Downloads"):
            (home / name).mkdir(parents=True)
        share = tmp / "nova-share"
        share.mkdir()
        Path.home = classmethod(lambda cls: home)  # type: ignore[method-assign,assignment]
        sb.SHARE_ROOT = str(share)
        (home / "Documents" / "report.txt").write_text("hello", encoding="utf-8")
        tool_gate.reset_pending_calls()
        paused.clear_all()
        reg = ToolRegistry()
        ex = ToolExecutor(reg)
        ran2: list[str] = []
        real2 = ex.execute

        def spy2(c, *a, **k):
            ran2.append(c.tool)
            return real2(c, *a, **k)

        ex.execute = spy2  # type: ignore[method-assign]
        planner = Planner(reg, [call("share.to_box", path=str(home / "Documents" / "report.txt")), call("system_status"), call("sandbox_run", command="wc -w /mnt/share/report.txt"), done("5 words")])
        ctx = {"planner": planner, "registry": reg, "executor": ex, "execute_tools": True, "session_id": "v135", "goal_from_user": True}
        res = asyncio.run(run_agentic_task("use your sandbox to count the words in my report", ctx))
        reply = handle_confirmation_command(f"confirm {res.get('action')}", session_id="v135")
        failures += emit(
            "resume keeps the sandbox focus after an approval",
            res.get("requires_confirmation") is True
            and len(planner.offered) >= 2
            and all("system_status" not in o and "status" not in o for o in planner.offered)
            and "system_status" not in ran2
            and "5 words" in reply
            and not sandbox_focus_open(),
            ran=ran2,
        )
        tool_gate.reset_pending_calls()
        paused.clear_all()
    finally:
        st._default_runner = original

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 135", "| 135 |" in readme)
except Exception as exc:  # a crash is a failure, never a pass
    failures += emit("verifier crashed", False, error=f"{type(exc).__name__}: {exc}")
finally:
    Path.home = _real_home  # type: ignore[method-assign]

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
sys.exit(0 if failures == 0 else 1)
