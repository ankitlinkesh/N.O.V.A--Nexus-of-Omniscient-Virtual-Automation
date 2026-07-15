"""Executable spec for Phase 42a's runner.py loop hooks: mid-task
interruptibility (``context["interrupt"]``) and confidence-aware escalation
(``context["min_action_confidence"]``).

Drives ``run_agentic_task`` with a deterministic ``ScriptedPlanner`` (the same
testability seam used by test_agent_reliability.py) so both contracts are
proven end to end with no live LLM, no network, and no real tool side effects
beyond the safe, allow-class ``workspace_status`` tool.

Fully offline and deterministic.
"""

from __future__ import annotations

import asyncio

from backend.eva.agent.planner import PlannedToolCall, PlannerDecision
from backend.eva.agent.runner import run_agentic_task
from backend.eva.tools.registry import ToolRegistry


class ScriptedPlanner:
    """Deterministic planner for driving the agent loop in tests. Returns queued
    PlannerDecisions in order; repeats the last one once exhausted."""

    def __init__(self, decisions):
        self._decisions = list(decisions)
        self.calls = 0

    async def plan(self, goal, history, mode="agent_step", task_context=None):
        decision = self._decisions[min(self.calls, len(self._decisions) - 1)]
        self.calls += 1
        return decision


WORKSPACE_STATUS_STEP = PlannerDecision(
    type="tool_calls",
    reason="check workspace status",
    tool_calls=[PlannedToolCall(tool="workspace_status", args={})],
    final_response="",
    continue_after_tools=True,
)

DONE_DECISION = PlannerDecision(
    type="done",
    reason="done",
    tool_calls=[],
    final_response="All set.",
    continue_after_tools=False,
)


def _run(planner: ScriptedPlanner, context_extra: dict | None = None) -> dict:
    context = {"planner": planner, "registry": ToolRegistry(), "execute_tools": True}
    context.update(context_extra or {})
    return asyncio.run(run_agentic_task("multi step goal", context))


# ---------------------------------------------------------------------------
# Mid-task interrupt.
# ---------------------------------------------------------------------------


def test_interrupt_true_stops_before_any_tool_executes():
    planner = ScriptedPlanner([WORKSPACE_STATUS_STEP])

    result = _run(planner, {"interrupt": lambda: True})

    assert result["status"] == "interrupted"
    assert result["ok"] is False
    assert "interrupted" in result["safety_stops"]
    assert result["tools_executed"] == []
    assert planner.calls == 0


def test_interrupt_false_does_not_stop_a_normal_run():
    planner = ScriptedPlanner([WORKSPACE_STATUS_STEP, DONE_DECISION])

    result = _run(planner, {"interrupt": lambda: False})

    assert result["status"] != "interrupted"
    assert "interrupted" not in result["safety_stops"]
    assert result["ok"] is True
    assert result["status"] == "done"


def test_interrupt_event_like_object_is_supported():
    class _FakeEvent:
        def is_set(self) -> bool:
            return True

    planner = ScriptedPlanner([WORKSPACE_STATUS_STEP])

    result = _run(planner, {"interrupt": _FakeEvent()})

    assert result["status"] == "interrupted"
    assert result["ok"] is False
    assert "interrupted" in result["safety_stops"]


# ---------------------------------------------------------------------------
# Confidence-aware escalation.
# ---------------------------------------------------------------------------


def test_low_min_confidence_escalates_the_next_action():
    # workspace_status reflections report confidence=0.84 (cognition.py). A
    # min_action_confidence above that must escalate the *next* planned action
    # instead of executing it -- state.last_confidence is only populated after
    # the first reflection, so the first workspace_status call always runs and
    # the escalation is observed on the second planned step.
    planner = ScriptedPlanner([WORKSPACE_STATUS_STEP])

    result = _run(planner, {"min_action_confidence": 0.99})

    assert result["status"] == "waiting_for_confirmation"
    assert result["requires_confirmation"] is True
    assert result["action"] == "workspace_status"
    assert "low_confidence_escalation" in result["safety_stops"]
    # The first call executed (it's in tools_executed); the second was
    # escalated, not executed a second time beyond what already ran.
    assert "workspace_status" in result["tools_executed"]


def test_no_min_confidence_never_escalates():
    planner = ScriptedPlanner([WORKSPACE_STATUS_STEP, DONE_DECISION])

    result = _run(planner)

    assert "low_confidence_escalation" not in result["safety_stops"]
    assert result["ok"] is True
    assert result["status"] == "done"


def test_min_confidence_below_actual_confidence_does_not_escalate():
    # 0.0 is below workspace_status's 0.84 reflection confidence, so the
    # threshold is never crossed and the run finishes normally.
    planner = ScriptedPlanner([WORKSPACE_STATUS_STEP, DONE_DECISION])

    result = _run(planner, {"min_action_confidence": 0.0})

    assert "low_confidence_escalation" not in result["safety_stops"]
    assert result["ok"] is True
    assert result["status"] == "done"
