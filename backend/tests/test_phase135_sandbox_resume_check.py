"""Phase 135: a sandbox task keeps its scope across an approval, and checks the box before answering.

(a) `resume_agentic_task` did not reopen the Phase 133 sandbox focus, so a task that paused on a
    confirm (e.g. share.to_box) and was approved could be offered system_status again.
(b) Live, "what OS is your sandbox running" was answered from general knowledge. In a focused task a
    finish with no sandbox_run attempted is sent back ONCE.

Both go through the real `run_agentic_task` / `handle_confirmation_command`, never the unit.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.eva.shell.sandbox_terminal as st
import backend.eva.tools.share_bridge as sb
from backend.eva.agent import paused_tasks as paused_tasks_mod
from backend.eva.agent.executor import ToolExecutor
from backend.eva.agent.planner import PlannedToolCall, PlannerDecision
from backend.eva.agent.runner import SANDBOX_CHECK_FEEDBACK, run_agentic_task
from backend.eva.permissions.confirmation import handle_confirmation_command
from backend.eva.security import tool_gate
from backend.eva.shell.sandbox_focus import sandbox_focus_open
from backend.eva.tools.registry import ToolRegistry

GOAL = "what OS is your sandbox running"


class RecordingPlanner:
    def __init__(self, registry, decisions):
        self.registry = registry
        self.decisions = list(decisions)
        self.offered: list[set[str]] = []
        self.seen: list[list[str]] = []

    async def plan(self, goal, history, mode="agent_step", task_context=None):
        self.offered.append({s["name"] for s in self.registry.planner_specs()})
        self.seen.append(list((task_context or {}).get("observations") or []))
        return self.decisions[min(len(self.offered) - 1, len(self.decisions) - 1)]


def _call(tool, **args):
    return PlannerDecision(type="tool_calls", reason="step", tool_calls=[PlannedToolCall(tool=tool, args=args)], final_response="", continue_after_tools=True)


def _done(text="Ubuntu, I assume."):
    return PlannerDecision(type="done", reason="finished", tool_calls=[], final_response=text, continue_after_tools=False)


class FakeWsl:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, timeout, env):
        self.calls.append(list(argv))
        if "--list" in argv:
            return SimpleNamespace(returncode=0, stdout=b"nova\n", stderr=b"")
        return SimpleNamespace(returncode=0, stdout=b"Ubuntu 24.04\n", stderr=b"")

    @property
    def exec_calls(self):
        return [c for c in self.calls if "--exec" in c]


@pytest.fixture
def wsl(monkeypatch):
    fake = FakeWsl()
    monkeypatch.setattr(st, "_default_runner", fake)
    tool_gate.reset_pending_calls()
    paused_tasks_mod.clear_all()
    yield fake
    tool_gate.reset_pending_calls()
    paused_tasks_mod.clear_all()


def _run(goal, decisions, from_user=True, session_id="s135"):
    registry = ToolRegistry()
    ran: list[str] = []
    executor = ToolExecutor(registry)
    real = executor.execute

    def spy(call, *a, **k):
        ran.append(call.tool)
        return real(call, *a, **k)

    executor.execute = spy  # type: ignore[method-assign]
    planner = RecordingPlanner(registry, decisions)
    context = {"planner": planner, "registry": registry, "executor": executor, "execute_tools": True, "session_id": session_id}
    if from_user:
        context["goal_from_user"] = True
    result = asyncio.run(run_agentic_task(goal, context))
    return result, planner, ran


# ------------------------------------------------------------------ (b) check before answering
def test_focused_done_first_is_sent_back_once_then_runs_sandbox(wsl):
    result, planner, ran = _run(GOAL, [_done(), _call("sandbox_run", command="cat /etc/os-release"), _done("Ubuntu 24.04")])
    assert ran == ["sandbox_run"]
    assert len(wsl.exec_calls) == 1
    assert SANDBOX_CHECK_FEEDBACK in planner.seen[1]
    assert result["status"] == "done" and "Ubuntu 24.04" in result["final_response"]


def test_done_twice_without_running_is_accepted_the_second_time(wsl):
    result, planner, ran = _run(GOAL, [_done("first guess"), _done("second guess")])
    assert ran == [] and wsl.exec_calls == []
    assert len(planner.offered) == 2, "sent back exactly once, then accepted"
    assert result["status"] == "done" and result["final_response"] == "second guess"
    assert sum(SANDBOX_CHECK_FEEDBACK in o for o in planner.seen[-1:]) == 1


def test_a_non_focused_task_is_never_sent_back(wsl):
    result, planner, _ran = _run("tell me a joke", [_done("a joke")])
    assert len(planner.offered) == 1 and result["final_response"] == "a joke"
    # focus words but not typed by the user: no scope, no send-back
    result, planner, _ran = _run(GOAL, [_done("x")], from_user=False)
    assert len(planner.offered) == 1


def test_a_focused_task_that_already_ran_sandbox_is_accepted_at_once(wsl):
    result, planner, ran = _run(GOAL, [_call("sandbox_run", command="uname -a"), _done("Linux")])
    assert ran == ["sandbox_run"]
    assert len(planner.offered) == 2, "no extra send-back"
    assert all(SANDBOX_CHECK_FEEDBACK not in obs for obs in planner.seen)
    assert result["final_response"] == "Linux"


# ------------------------------------------------------------------ (a) resume keeps the focus
@pytest.fixture
def share_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    for name in ("Documents", "Desktop", "Downloads"):
        (home / name).mkdir(parents=True)
    share = tmp_path / "nova-share"
    share.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(sb, "SHARE_ROOT", str(share))
    (home / "Documents" / "report.txt").write_text("hello", encoding="utf-8")
    return SimpleNamespace(home=home, share=share)


def test_resumed_sandbox_task_keeps_its_focus(wsl, share_env):
    src = str(share_env.home / "Documents" / "report.txt")
    goal = "use your sandbox to count the words in my report"
    registry = ToolRegistry()
    ran: list[str] = []
    executor = ToolExecutor(registry)
    real = executor.execute

    def spy(call, *a, **k):
        ran.append(call.tool)
        return real(call, *a, **k)

    executor.execute = spy  # type: ignore[method-assign]
    planner = RecordingPlanner(registry, [_call("share.to_box", path=src), _call("system_status"), _call("sandbox_run", command="wc -w /mnt/share/report.txt"), _done("5 words")])
    context = {"planner": planner, "registry": registry, "executor": executor, "execute_tools": True, "session_id": "s135", "goal_from_user": True}
    paused = asyncio.run(run_agentic_task(goal, context))
    assert paused["requires_confirmation"] is True
    assert len(planner.offered) == 1 and not sandbox_focus_open()
    assert list(share_env.share.iterdir()) == []

    reply = handle_confirmation_command(f"confirm {paused['action']}", session_id="s135")
    assert (share_env.share / "report.txt").exists()
    assert len(planner.offered) >= 2, "the task must have resumed"
    for offered in planner.offered:
        assert "system_status" not in offered and "status" not in offered, "focus must survive the approval"
        assert "sandbox_run" in offered
    assert "system_status" not in ran, "a forced host-status call after the resume is refused"
    assert ran.count("sandbox_run") == 1
    assert "5 words" in reply
    assert not sandbox_focus_open()


def test_resume_of_a_normal_task_opens_no_focus(wsl, share_env):
    src = str(share_env.home / "Documents" / "report.txt")
    registry = ToolRegistry()
    planner = RecordingPlanner(registry, [_call("share.to_box", path=src), _call("system_status"), _done("ok")])
    context = {"planner": planner, "registry": registry, "executor": ToolExecutor(registry), "execute_tools": True, "session_id": "s135", "goal_from_user": True}
    paused = asyncio.run(run_agentic_task("copy my report to the share", context))
    handle_confirmation_command(f"confirm {paused['action']}", session_id="s135")
    assert all("system_status" in o for o in planner.offered)
