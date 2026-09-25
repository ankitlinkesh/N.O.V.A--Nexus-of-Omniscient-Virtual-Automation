"""Executable spec for Phase 119 (adaptive step budget).

Before this phase, the agent loop's step budget was one fixed number,
`task.max_steps` (`max_agent_steps()`, default 6), used up or not. A real
multi-step errand -- "open X, type Y, check the screen, tell me Z" -- could
run out of steps a step or two short of the answer even while every step it
had taken was landing.

This phase makes that budget adaptive, but still bounded:

  * the loop STARTS with the same base budget as always (6) -- a task that
    never earns an extension behaves byte-identically to before;
  * reaching the current budget grants exactly ONE more step, and only when
    the step that just ran made VERIFIED progress (an independently verified
    post-condition, or a genuinely NEW observation -- not a repeat of
    something this task already knows). Anything else -- a failure, a
    refusal, a gate pause, a repeat -- earns nothing;
  * this can repeat, but never past a hard ceiling (`EVA_AGENT_MAX_STEPS_CEILING`,
    default 12, hard-capped at 20 regardless of the env override) -- never
    unbounded;
  * two EXECUTED steps in a row that earn no progress stop the errand early,
    with the same honest partial answer the step cap already produces
    (`summarize_progress`), not a new failure mode;
  * a Phase 117 pause/resume carries its earned budget across the pause
    untouched, because resume reuses the exact same `_RunEnv`/`AgentTask`/
    `AgentRunState` objects by reference (`PausedTask.env`) rather than
    rebuilding them -- there is nothing to reset.

This drives the REAL loop (`run_agentic_task`/`resume_agentic_task`) with a
scripted planner and a fake executor, the same pattern
`test_phase117_resume_after_approval.py` and `test_phase93_loop_exits.py`
use. No real tools, no real gate, no real disk -- the fake executor stands
in for `ToolExecutor` entirely, so the pause/resume test controls exactly
when a call is "gated" without touching the real permission machinery.
"""

from __future__ import annotations

import asyncio

import backend.eva.agent.runner as runner_module
from backend.eva.agent import paused_tasks as paused_tasks_mod
from backend.eva.agent.executor import ToolExecutionResult
from backend.eva.agent.planner import PlannedToolCall, PlannerDecision
from backend.eva.agent.policies import max_agent_steps, max_agent_steps_ceiling
from backend.eva.agent.runner import resume_agentic_task, run_agentic_task
from backend.eva.tools.registry import ToolRegistry


class ScriptedPlanner:
    """Deterministic planner: returns queued decisions in order, repeats the
    last one once exhausted (matches test_phase117/test_phase39's pattern)."""

    def __init__(self, decisions):
        self._decisions = list(decisions)
        self.calls = 0

    async def plan(self, goal, history, mode="agent_step", task_context=None):
        decision = self._decisions[min(self.calls, len(self._decisions) - 1)]
        self.calls += 1
        return decision


class ProgressExecutor:
    """A fake `ToolExecutor` whose `progress_tool` calls always succeed with
    a result that VARIES by an explicit `i` argument (so each one is a
    genuinely new observation), and whose `gated_tool` calls pause exactly
    like a real gated tool-registry call -- `requires_confirmation=True` with
    an `action` matching the pending-id shape `_pause_and_return` checks for
    -- so a pause/resume can be driven directly, with no real permission
    gate or ToolRegistry involved.
    """

    def __init__(self):
        self.executed: list[tuple[str, dict]] = []

    def execute(self, call: PlannedToolCall) -> ToolExecutionResult:
        self.executed.append((call.tool, dict(call.args)))
        if call.tool == "gated_tool":
            return ToolExecutionResult(
                ok=False,
                tool=call.tool,
                result={"requires_confirmation": True},
                error="This action requires confirmation.",
                requires_confirmation=True,
                action="act_phase119test0001",
            )
        return ToolExecutionResult(ok=True, tool=call.tool, result={"i": call.args.get("i")})

    def execute_all(self, calls):
        return [self.execute(c) for c in calls]

    def execute_approved(self, tool: str, args: dict, executed_result) -> ToolExecutionResult:
        return ToolExecutionResult(ok=True, tool=tool, result=executed_result)


def _progress(i) -> PlannerDecision:
    return PlannerDecision(
        type="tool_calls",
        reason="step",
        tool_calls=[PlannedToolCall(tool="progress_tool", args={"i": i})],
        final_response="",
        continue_after_tools=True,
    )


def _gated() -> PlannerDecision:
    return PlannerDecision(
        type="tool_calls",
        reason="step",
        tool_calls=[PlannedToolCall(tool="gated_tool", args={})],
        final_response="",
        continue_after_tools=True,
    )


def _done(text: str = "done") -> PlannerDecision:
    return PlannerDecision(type="done", reason="finished", tool_calls=[], final_response=text, continue_after_tools=False)


def _run(decisions, *, executor=None, session_id="s1", **context):
    return asyncio.run(
        run_agentic_task(
            "run an adaptive-budget errand",
            {
                "planner": ScriptedPlanner(decisions),
                "registry": ToolRegistry(),
                "executor": executor or ProgressExecutor(),
                "execute_tools": True,
                "session_id": session_id,
                **context,
            },
        )
    )


def setup_function(_fn=None):
    paused_tasks_mod.clear_all()


def teardown_function(_fn=None):
    paused_tasks_mod.clear_all()


# --- base budget is unchanged when nothing earns an extension ---------------


def test_base_budget_matches_the_unchanged_default():
    assert max_agent_steps() == 6


def test_default_ceiling_is_twelve_and_never_below_base(monkeypatch):
    assert max_agent_steps_ceiling() == 12
    monkeypatch.setenv("EVA_AGENT_MAX_STEPS_CEILING", "9999")
    assert max_agent_steps_ceiling() == 20, "the ceiling must stay hard-capped regardless of the env override"
    monkeypatch.setenv("MAX_AGENT_STEPS", "15")
    monkeypatch.setenv("EVA_AGENT_MAX_STEPS_CEILING", "10")
    assert max_agent_steps_ceiling() == 15, "the ceiling must never sit below the base budget"


# --- steady progress runs past 6 and finishes before the ceiling ------------


def test_steady_progress_runs_past_six_and_finishes_before_the_ceiling():
    decisions = [_progress(i) for i in range(1, 8)] + [_done("finished after seven real steps")]
    result = _run(decisions)

    assert result["ok"] is True
    assert result["status"] == "done"
    assert result["final_response"] == "finished after seven real steps"
    budget = result["step_budget"]
    assert budget["steps_used"] == 8, "seven tool steps plus the done step"
    assert budget["base_budget"] == 6
    assert budget["ceiling"] == 12
    assert budget["extended"] is True
    assert budget["extensions"] == 2, "the budget grew 6 -> 7 -> 8 to fit the seventh progressing step"
    assert budget["final_budget"] == 8
    assert budget["final_budget"] < budget["ceiling"], "it must finish comfortably under the ceiling"


# --- progress forever stops at the ceiling, never past it -------------------


def test_progress_forever_still_stops_at_the_ceiling(monkeypatch):
    # A generous tool-call cap so the tool-call budget (10 by default) is not
    # what actually stops this run -- the ceiling must be what does.
    monkeypatch.setattr(runner_module, "max_tools_per_task", lambda: 50)
    monkeypatch.setattr(runner_module, "max_agent_steps_ceiling", lambda: 9)
    decisions = [_progress(i) for i in range(1, 40)]  # far more than the ceiling allows
    result = _run(decisions)

    assert result["ok"] is False
    assert "max_steps_reached" in result["safety_stops"]
    assert "tool_limit_reached" not in result["safety_stops"], "the ceiling, not the tool cap, must be what stops this"
    budget = result["step_budget"]
    assert budget["ceiling"] == 9
    assert budget["final_budget"] == 9
    assert budget["steps_used"] == 9, "it must stop AT the ceiling, never one step past it"
    assert budget["extensions"] == 3, "6 -> 7 -> 8 -> 9"


# --- no progress at all stops at the (unextended) base budget ---------------


def test_no_progress_stops_at_the_base_budget():
    # Steps 1-5 each progress (a new `i` every time); step 6 repeats step 5's
    # exact call, so its result is not new information -- no progress, and
    # specifically at the one step that decides whether to extend.
    decisions = [_progress(1), _progress(2), _progress(3), _progress(4), _progress(5), _progress(5)]
    result = _run(decisions)

    assert result["ok"] is False
    assert "max_steps_reached" in result["safety_stops"]
    budget = result["step_budget"]
    assert budget["extended"] is False
    assert budget["extensions"] == 0
    assert budget["final_budget"] == 6, "the base budget, never grown"
    assert budget["steps_used"] == 6


# --- stall detection: two no-progress steps in a row stop early -------------


def test_two_consecutive_no_progress_steps_stop_early():
    """Three calls to the SAME tool with DIFFERENT args -- so the older,
    narrower `repeated_without_progress` guard (which keys on exact tool+args
    repeats) never fires -- but the fake executor ignores the args and
    reports the identical text every time, so only the FIRST call is
    genuinely new information. The new, looser stall detector must catch
    what the exact-repeat guard structurally cannot.
    """

    class RepeatingExecutor:
        def execute(self, call: PlannedToolCall) -> ToolExecutionResult:
            # Every call reports the identical result regardless of its
            # args, so the args differing does not make the OBSERVATION new.
            return ToolExecutionResult(ok=True, tool=call.tool, result={"fixed": "same every time"})

        def execute_all(self, calls):
            return [self.execute(c) for c in calls]

        def execute_approved(self, tool, args, executed_result):
            return ToolExecutionResult(ok=True, tool=tool, result=executed_result)

    decisions = [
        PlannerDecision(type="tool_calls", reason="a", tool_calls=[PlannedToolCall(tool="same_tool", args={"x": 1})], final_response="", continue_after_tools=True),
        PlannerDecision(type="tool_calls", reason="b", tool_calls=[PlannedToolCall(tool="same_tool", args={"x": 2})], final_response="", continue_after_tools=True),
        PlannerDecision(type="tool_calls", reason="c", tool_calls=[PlannedToolCall(tool="same_tool", args={"x": 3})], final_response="", continue_after_tools=True),
    ]
    result = _run(decisions, executor=RepeatingExecutor())

    assert result["ok"] is False
    assert not any("repeated_action" in stop for stop in result["safety_stops"]), "different args must not trip the exact-repeat guard"
    assert "stall_detected" in result["safety_stops"]
    assert "max_steps_reached" not in result["safety_stops"], "it must stop EARLY, before the cap, not at it"
    budget = result["step_budget"]
    assert budget["steps_used"] == 3, "step 1 (new), step 2 (repeat), step 3 (repeat) -> stop after the 2nd repeat"
    assert budget["extended"] is False
    reply = result["final_response"]
    assert "not a complete answer" in reply
    assert "same_tool" in reply, "the one genuinely new finding must still reach the user"


def test_an_identical_repeated_call_is_its_own_earlier_stall_guard():
    """The pre-existing exact tool+args repeat guard (`repeated_without_progress`)
    still fires -- and fires FIRST, before Phase 119's newer, looser
    two-in-a-row check would even get a chance to (an exact repeat is
    always a subset of "no new information").
    """
    decisions = [
        PlannerDecision(type="tool_calls", reason="x", tool_calls=[PlannedToolCall(tool="progress_tool", args={"i": 1})], final_response="", continue_after_tools=True)
    ]
    result = _run(decisions)

    assert result["ok"] is False
    assert any("repeated_action" in stop for stop in result["safety_stops"])
    assert result["step_budget"]["steps_used"] == 3, "stops on the 3rd identical call, well before the base budget"


# --- a paused-then-resumed task keeps its earned budget ----------------------


def test_a_paused_then_resumed_task_keeps_its_earned_budget():
    """Six progressing steps earn one extension (6 -> 7) before step 7 pauses
    on a gated call. Resuming must continue from the GROWN budget, not a
    fresh one -- the mutation this guards against is `task.max_steps`
    (or the ceiling/extensions bookkeeping) resetting across the pause,
    which would make `index=7` already exceed a reset `max_steps=6` and the
    resumed loop would never even take one more step.
    """
    decisions = [_progress(i) for i in range(1, 7)] + [_gated(), _done("resumed and finished")]
    executor = ProgressExecutor()
    result = _run(decisions, executor=executor, session_id="s1")

    assert result["status"] == "waiting_for_confirmation"
    pid = result["action"]
    assert pid == "act_phase119test0001"
    pre_resume_budget = result["step_budget"]
    assert pre_resume_budget["extensions"] == 1, "steps 1-6 earned exactly one extension (6 -> 7) before the pause"
    assert pre_resume_budget["final_budget"] == 7

    snapshot = paused_tasks_mod.take_paused_task(pid, "s1")
    assert snapshot is not None

    executed_result = {"ok": True, "confirmed": True}
    outcome = asyncio.run(resume_agentic_task(snapshot, executed_result))

    assert outcome["ok"] is True
    assert outcome["status"] == "done"
    assert outcome["final_response"] == "resumed and finished"
    budget = outcome["step_budget"]
    assert budget["extensions"] >= 2, "the resumed step (7) itself progressed and earned a SECOND extension (7 -> 8)"
    assert budget["final_budget"] >= 8
    assert budget["steps_used"] >= 8, "the pre-pause steps must not be recounted or lost"
