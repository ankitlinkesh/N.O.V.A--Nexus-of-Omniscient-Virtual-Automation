"""Standalone verifier for Phase 136 (a fetching sandbox command's output is outside content).

In-process against an injected launcher (no real WSL):
1. fetches_external recognises network fetches and ignores ordinary box work.
2. "sandbox_download" is an untrusted source type.
3. Through the real run_agentic_task: after a curl, the next sandbox command asks
   first and does not run; a failed curl counts too; ordinary commands stay autonomous.
4. The approval message names the source in words.
5. README records the phase.
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


class FakeWsl:
    def __init__(self, returncode=0, stdout=b"ok\n"):
        self.returncode, self.stdout = returncode, stdout
        self.calls: list[list[str]] = []

    def __call__(self, argv, timeout, env):
        self.calls.append(list(argv))
        if "--list" in argv:
            return SimpleNamespace(returncode=0, stdout=b"nova\n", stderr=b"")
        n = len([c for c in self.calls if "--exec" in c])
        return SimpleNamespace(returncode=self.returncode, stdout=self.stdout + b"#%d\n" % n, stderr=b"")

    def execs(self):
        return [c for c in self.calls if "--exec" in c]


try:
    import backend.eva.shell.sandbox_terminal as st
    from backend.eva.agent import paused_tasks
    from backend.eva.agent.executor import ToolExecutor
    from backend.eva.agent.planner import PlannedToolCall, PlannerDecision
    from backend.eva.agent.runner import run_agentic_task
    from backend.eva.security import tool_gate
    from backend.eva.threat_defense.taint import UNTRUSTED_SOURCE_TYPES
    from backend.eva.tools.registry import ToolRegistry

    fetch = ["curl -s https://example.com", "wget x", "git clone https://github.com/a/b", "pip install requests", 'python3 -c "import urllib.request"', "ssh user@host"]
    plain = ["ls -la", 'python3 -c "print(2+2)"', "df -h", "echo curly braces", "git status", "pip list", "npm run build"]
    missed = [c for c in fetch if not st.fetches_external(c)]
    false_hits = [c for c in plain if st.fetches_external(c)]
    failures += emit("fetches_external: fetches recognised, ordinary box work not", not missed and not false_hits, missed=missed, false_hits=false_hits)
    failures += emit("sandbox_download is an untrusted source type", "sandbox_download" in UNTRUSTED_SOURCE_TYPES)

    def run(goal, commands, fake):
        decisions = [PlannerDecision(type="tool_calls", reason="s", tool_calls=[PlannedToolCall(tool="sandbox_run", args={"command": c})], final_response="", continue_after_tools=True) for c in commands]
        decisions.append(PlannerDecision(type="done", reason="d", tool_calls=[], final_response="ok", continue_after_tools=False))

        class Planner:
            n = 0

            async def plan(self, goal, history, mode="agent_step", task_context=None):
                d = decisions[min(Planner.n, len(decisions) - 1)]
                Planner.n += 1
                return d

        registry = ToolRegistry()
        tool_gate.reset_pending_calls()
        paused_tasks.clear_all()
        real = st._default_runner
        st._default_runner = fake
        try:
            return asyncio.run(run_agentic_task(goal, {"planner": Planner(), "registry": registry, "executor": ToolExecutor(registry), "execute_tools": True, "session_id": "v136"}))
        finally:
            st._default_runner = real

    fake = FakeWsl()
    r = run("use your box to fetch example.com", ["curl -s https://example.com", "ls"], fake)
    failures += emit("after a curl the next sandbox command asks and does not run", r.get("requires_confirmation") is True and len(fake.execs()) == 1, final=r.get("final_response"))
    failures += emit("the approval message names the source in words", "downloaded in my sandbox" in str(r.get("final_response")))
    fake = FakeWsl(returncode=6, stdout=b"<html>partial</html>")
    r = run("use your box to fetch it", ["curl -s https://example.com", "ls"], fake)
    failures += emit("a failed curl still counts", r.get("requires_confirmation") is True and len(fake.execs()) == 1)
    fake = FakeWsl()
    r = run("in your box do some work", ["ls -la", "python3 -c 'print(2+2)'", "pwd"], fake)
    failures += emit("ordinary box work stays autonomous", r.get("status") == "done" and not r.get("requires_confirmation") and len(fake.execs()) == 3)

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 136", "| 136 |" in readme)
except Exception as exc:  # a crash is a failure, never a pass
    failures += emit("verifier crashed", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
sys.exit(0 if failures == 0 else 1)
