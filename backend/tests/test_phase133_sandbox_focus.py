"""Phase 133: a "your terminal/box" question must never be answered with the PC's status.

The Phase 130 prompt rules did not change the model's choice live, so the fix is a
scope (like the GUI scope): host-status tools are removed from the planner's view
and, if emitted anyway, refused by the runner. The scope is opened in
`run_agentic_task` and read on the same coroutine -- these tests go through that
real entry point, not the unit, because a scope that only works in a direct call is
the Phase 103 failure.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import backend.eva.shell.sandbox_terminal as st
from backend.eva.agent.executor import ToolExecutor
from backend.eva.agent.planner import PlannedToolCall, PlannerDecision
from backend.eva.agent.runner import run_agentic_task
from backend.eva.shell.sandbox_focus import (
    SANDBOX_FOCUS_HIDDEN,
    open_sandbox_focus,
    sandbox_focus_open,
    wants_sandbox_focus,
)
from backend.eva.tools.registry import ToolRegistry

GOAL = "use your terminal to check how much disk space you have"


@pytest.mark.parametrize(
    "goal",
    [
        GOAL,
        "in your box, how much memory is free",
        "what OS is your sandbox running",
        "run uname using your linux box",
    ],
)
def test_wants_focus_true(goal):
    assert wants_sandbox_focus(goal)


@pytest.mark.parametrize(
    "goal",
    ["how much disk space do I have", "check my battery", "put it in the box", "check my inbox", ""],
)
def test_wants_focus_false(goal):
    assert not wants_sandbox_focus(goal)


def test_spec_filter_only_inside_the_scope():
    registry = ToolRegistry()
    before = {s["name"] for s in registry.planner_specs()}
    assert SANDBOX_FOCUS_HIDDEN <= before | {"status"} and "system_status" in before
    with open_sandbox_focus():
        assert sandbox_focus_open()
        inside = {s["name"] for s in registry.planner_specs()}
    assert not sandbox_focus_open()
    assert inside == before - SANDBOX_FOCUS_HIDDEN
    assert "sandbox_run" in inside and "file.read_text" in inside
    assert {s["name"] for s in registry.planner_specs()} == before


class RecordingPlanner:
    def __init__(self, registry, decisions):
        self.registry = registry
        self.decisions = list(decisions)
        self.offered: list[set[str]] = []
        self.seen_observations: list[list[str]] = []

    async def plan(self, goal, history, mode="agent_step", task_context=None):
        self.offered.append({s["name"] for s in self.registry.planner_specs()})
        self.seen_observations.append(list((task_context or {}).get("observations") or []))
        return self.decisions[min(len(self.offered) - 1, len(self.decisions) - 1)]


def _call(tool, **args):
    return PlannerDecision(type="tool_calls", reason="step", tool_calls=[PlannedToolCall(tool=tool, args=args)], final_response="", continue_after_tools=True)


def _done():
    return PlannerDecision(type="done", reason="finished", tool_calls=[], final_response="ok", continue_after_tools=False)


class FakeWsl:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, timeout, env):
        self.calls.append(list(argv))
        if "--list" in argv:
            return SimpleNamespace(returncode=0, stdout=b"nova\n", stderr=b"")
        return SimpleNamespace(returncode=0, stdout=b"Filesystem Size\n", stderr=b"")

    @property
    def exec_calls(self):
        return [c for c in self.calls if "--exec" in c]


@pytest.fixture
def wsl(monkeypatch):
    fake = FakeWsl()
    monkeypatch.setattr(st, "_default_runner", fake)
    return fake


def _run(goal, decisions, from_user=True):
    registry = ToolRegistry()
    ran: list[str] = []
    executor = ToolExecutor(registry)
    real_execute = executor.execute

    def spy(call, *a, **k):
        ran.append(call.tool)
        return real_execute(call, *a, **k)

    executor.execute = spy  # type: ignore[method-assign]
    planner = RecordingPlanner(registry, decisions)
    context = {"planner": planner, "registry": registry, "executor": executor, "execute_tools": True, "session_id": "s133"}
    if from_user:
        context["goal_from_user"] = True
    result = asyncio.run(run_agentic_task(goal, context))
    return result, planner, ran


def test_focused_goal_hides_status_and_refuses_a_forced_call(wsl):
    result, planner, ran = _run(GOAL, [_call("system_status"), _call("sandbox_run", command="df -h"), _done()])
    assert planner.offered, "planner must have been consulted"
    for offered in planner.offered:
        assert "system_status" not in offered and "status" not in offered
        assert "sandbox_run" in offered
    assert "system_status" not in ran, "the refused host tool must never reach the executor"
    assert ran == ["sandbox_run"]
    assert len(wsl.exec_calls) == 1
    # the planner was told why, on its next turn
    assert any("sandbox_run" in o and "user's PC" in o for o in planner.seen_observations[1])
    assert result["status"] == "done"


def test_normal_goal_still_runs_system_status(wsl):
    result, planner, ran = _run("how much disk space do I have", [_call("system_status"), _done()])
    assert all("system_status" in offered for offered in planner.offered)
    assert ran == ["system_status"]
    assert wsl.exec_calls == []
    assert result["status"] == "done"


def test_scope_needs_a_user_typed_goal(wsl):
    # a goal that did not come from the user's own typing never opens the scope
    _, planner, ran = _run(GOAL, [_call("system_status"), _done()], from_user=False)
    assert "system_status" in planner.offered[0] and ran == ["system_status"]


def test_scope_is_closed_after_the_task(wsl):
    _run(GOAL, [_done()])
    assert not sandbox_focus_open()


@pytest.mark.parametrize("empty", ["", None, "   "])
def test_a_done_with_no_text_never_reaches_the_user_as_nothing(wsl, empty):
    # Live: a refused step then a "done" with no text reached the chat as "None".
    done = PlannerDecision(type="done", reason="d", tool_calls=[], final_response=empty, continue_after_tools=False)
    result, _planner, _ran = _run(GOAL, [_call("system_status"), done])
    final = result.get("final_response")
    assert isinstance(final, str) and final.strip() and final != "None"
    assert "without writing an answer" in final
