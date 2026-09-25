"""Standalone verifier for Phase 119 (adaptive step budget).

Before this phase, the agent loop's step budget was one fixed number
(`task.max_steps`, from `max_agent_steps()`, default 6) -- used or not. A
real multi-step errand ("open X, type Y, check the screen, tell me Z") could
run out of steps a step or two short of the answer even while every step it
had taken was landing.

This phase makes the budget adaptive but still bounded:

  * it STARTS at the same base (6) -- a task that never earns an extension
    behaves exactly as it always has;
  * reaching the current budget grants exactly ONE more step, only when the
    step that just ran made VERIFIED progress (an independently verified
    post-condition, or a genuinely NEW observation -- not a repeat of
    something this task already knows). A failure, a refusal, a gate pause,
    or a repeat earns nothing;
  * this can repeat, but never past a hard ceiling
    (`EVA_AGENT_MAX_STEPS_CEILING`, default 12, hard-capped at 20 regardless
    of the env override) -- the loop must never become effectively
    unbounded;
  * two EXECUTED steps in a row that earn no progress stop the errand early
    with the same honest partial answer the step cap already produces
    (`summarize_progress`) -- not a new failure mode;
  * a Phase 117 pause/resume carries its earned budget across the pause
    untouched, because resume reuses the same `_RunEnv`/`AgentTask`/
    `AgentRunState` objects by reference (`PausedTask.env`) rather than
    rebuilding them.

Drives the REAL loop (`run_agentic_task`/`resume_agentic_task`) with a
scripted planner and a fake executor -- no real tools, no real permission
gate, no real disk, matching `verify_eva_phase117_resume_after_approval.py`'s
and `verify_eva_phase93_loop_exit_honesty.py`'s pattern of driving the loop
directly rather than only unit-testing a helper.

Mutation notes (see the accompanying report for the actual runs, not
re-derived here): removing the progress condition at the budget boundary in
`runner.py::_drive_loop` (always extending), removing the ceiling clamp
(`task.max_steps < task.step_ceiling`), or resetting `task.max_steps` at the
top of `resume_agentic_task`, each independently fails one of pytest's
`test_phase119_adaptive_step_budget.py` cases when reverted by hand.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

failures = 0


def emit(case: str, ok: bool, **extra: object) -> None:
    global failures
    payload = {"case": case, "pass": bool(ok)}
    payload.update(extra)
    print(json.dumps(payload, indent=2, default=str))
    if not ok:
        failures += 1


try:
    import backend.eva.agent.runner as runner_module
    from backend.eva.agent import paused_tasks as paused_tasks_mod
    from backend.eva.agent.executor import ToolExecutionResult
    from backend.eva.agent.planner import PlannedToolCall, PlannerDecision
    from backend.eva.agent.policies import max_agent_steps, max_agent_steps_ceiling
    from backend.eva.agent.runner import resume_agentic_task, run_agentic_task
    from backend.eva.tools.registry import ToolRegistry

    class ScriptedPlanner:
        def __init__(self, decisions):
            self._decisions = list(decisions)
            self.calls = 0

        async def plan(self, goal, history, mode="agent_step", task_context=None):
            decision = self._decisions[min(self.calls, len(self._decisions) - 1)]
            self.calls += 1
            return decision

    class ProgressExecutor:
        """`progress_tool` always succeeds with a result that varies by its
        `i` arg (a genuinely new observation each time); `gated_tool` pauses
        like a real gated call, with an `action` matching the pending-id
        shape `_pause_and_return` requires."""

        def execute(self, call: PlannedToolCall) -> ToolExecutionResult:
            if call.tool == "gated_tool":
                return ToolExecutionResult(
                    ok=False, tool=call.tool, result={"requires_confirmation": True},
                    error="This action requires confirmation.", requires_confirmation=True,
                    action="act_phase119verify001",
                )
            return ToolExecutionResult(ok=True, tool=call.tool, result={"i": call.args.get("i")})

        def execute_all(self, calls):
            return [self.execute(c) for c in calls]

        def execute_approved(self, tool, args, executed_result):
            return ToolExecutionResult(ok=True, tool=tool, result=executed_result)

    def _progress(i) -> PlannerDecision:
        return PlannerDecision(type="tool_calls", reason="step", tool_calls=[PlannedToolCall(tool="progress_tool", args={"i": i})], final_response="", continue_after_tools=True)

    def _gated() -> PlannerDecision:
        return PlannerDecision(type="tool_calls", reason="step", tool_calls=[PlannedToolCall(tool="gated_tool", args={})], final_response="", continue_after_tools=True)

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

    def _reset():
        paused_tasks_mod.clear_all()

    # --- 1. base budget and default ceiling are the documented numbers ------
    _reset()
    emit("the base budget default is unchanged (6)", max_agent_steps() == 6, base=max_agent_steps())
    emit("the default ceiling is 12", max_agent_steps_ceiling() == 12, ceiling=max_agent_steps_ceiling())

    # --- 2. steady progress runs past 6, finishes before the ceiling --------
    _reset()
    decisions = [_progress(i) for i in range(1, 8)] + [_done("finished after seven real steps")]
    result = _run(decisions)
    budget = result.get("step_budget") or {}
    emit(
        "steady verified progress runs past the base budget and finishes before the ceiling",
        result.get("ok") is True
        and result.get("final_response") == "finished after seven real steps"
        and budget.get("extended") is True
        and budget.get("extensions") == 2
        and budget.get("final_budget") == 8
        and budget.get("final_budget") < budget.get("ceiling", 0),
        result_status=result.get("status"),
        step_budget=budget,
    )

    # --- 3. progress forever stops AT the ceiling, never past it ------------
    _reset()
    original_ceiling_fn = runner_module.max_agent_steps_ceiling
    original_tools_fn = runner_module.max_tools_per_task
    try:
        runner_module.max_tools_per_task = lambda: 50
        runner_module.max_agent_steps_ceiling = lambda: 9
        decisions = [_progress(i) for i in range(1, 40)]
        result = _run(decisions)
    finally:
        runner_module.max_agent_steps_ceiling = original_ceiling_fn
        runner_module.max_tools_per_task = original_tools_fn
    budget = result.get("step_budget") or {}
    emit(
        "progress forever still stops at the ceiling, never past it",
        result.get("ok") is False
        and "max_steps_reached" in (result.get("safety_stops") or [])
        and "tool_limit_reached" not in (result.get("safety_stops") or [])
        and budget.get("final_budget") == 9
        and budget.get("steps_used") == 9
        and budget.get("extensions") == 3,
        safety_stops=result.get("safety_stops"),
        step_budget=budget,
    )

    # --- 4. no progress at all stops at the (unextended) base budget --------
    _reset()
    decisions = [_progress(1), _progress(2), _progress(3), _progress(4), _progress(5), _progress(5)]
    result = _run(decisions)
    budget = result.get("step_budget") or {}
    emit(
        "no progress at the budget boundary stops at the unextended base budget",
        result.get("ok") is False
        and "max_steps_reached" in (result.get("safety_stops") or [])
        and budget.get("extended") is False
        and budget.get("final_budget") == 6
        and budget.get("steps_used") == 6,
        safety_stops=result.get("safety_stops"),
        step_budget=budget,
    )

    # --- 5. two consecutive no-progress steps stop early ---------------------
    _reset()

    class RepeatingExecutor:
        def execute(self, call: PlannedToolCall) -> ToolExecutionResult:
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
    budget = result.get("step_budget") or {}
    stops = result.get("safety_stops") or []
    emit(
        "two consecutive no-progress steps (different args, identical results) stop early via the new stall detector",
        result.get("ok") is False
        and "stall_detected" in stops
        and "max_steps_reached" not in stops
        and not any("repeated_action" in s for s in stops)
        and budget.get("steps_used") == 3
        and "not a complete answer" in (result.get("final_response") or ""),
        safety_stops=stops,
        step_budget=budget,
    )

    # --- 6. the pre-existing exact tool+args repeat guard still fires first -
    _reset()
    decisions = [PlannerDecision(type="tool_calls", reason="x", tool_calls=[PlannedToolCall(tool="progress_tool", args={"i": 1})], final_response="", continue_after_tools=True)]
    result = _run(decisions)
    stops = result.get("safety_stops") or []
    emit(
        "an identical repeated call still trips the older exact-repeat guard, not the new stall detector",
        result.get("ok") is False and any("repeated_action" in s for s in stops) and "stall_detected" not in stops,
        safety_stops=stops,
    )

    # --- 7. a paused-then-resumed task keeps its earned budget --------------
    _reset()
    decisions = [_progress(i) for i in range(1, 7)] + [_gated(), _done("resumed and finished")]
    result = _run(decisions, session_id="s1")
    pre_budget = result.get("step_budget") or {}
    pid = result.get("action")
    snapshot = paused_tasks_mod.take_paused_task(pid, "s1") if pid else None
    outcome = asyncio.run(resume_agentic_task(snapshot, {"ok": True, "confirmed": True})) if snapshot else {}
    post_budget = outcome.get("step_budget") or {}
    emit(
        "a paused-then-resumed task keeps its earned budget (no reset, no lost extensions)",
        result.get("status") == "waiting_for_confirmation"
        and pid == "act_phase119verify001"
        and pre_budget.get("extensions") == 1
        and pre_budget.get("final_budget") == 7
        and snapshot is not None
        and outcome.get("ok") is True
        and outcome.get("status") == "done"
        and outcome.get("final_response") == "resumed and finished"
        and post_budget.get("extensions", 0) >= 2
        and post_budget.get("final_budget", 0) >= 8
        and post_budget.get("steps_used", 0) >= 8,
        pre_pause_budget=pre_budget,
        post_resume_status=outcome.get("status"),
        post_resume_budget=post_budget,
    )

    # --- 8. the ceiling is clamped and never below the base -----------------
    import os

    _prior_env = os.environ.get("EVA_AGENT_MAX_STEPS_CEILING")
    _prior_base_env = os.environ.get("MAX_AGENT_STEPS")
    try:
        os.environ["EVA_AGENT_MAX_STEPS_CEILING"] = "9999"
        clamped = max_agent_steps_ceiling()
        os.environ["MAX_AGENT_STEPS"] = "15"
        os.environ["EVA_AGENT_MAX_STEPS_CEILING"] = "10"
        never_below_base = max_agent_steps_ceiling()
    finally:
        if _prior_env is None:
            os.environ.pop("EVA_AGENT_MAX_STEPS_CEILING", None)
        else:
            os.environ["EVA_AGENT_MAX_STEPS_CEILING"] = _prior_env
        if _prior_base_env is None:
            os.environ.pop("MAX_AGENT_STEPS", None)
        else:
            os.environ["MAX_AGENT_STEPS"] = _prior_base_env
    emit(
        "the ceiling is hard-capped at 20 regardless of env override, and never sits below the base budget",
        clamped == 20 and never_below_base == 15,
        clamped=clamped,
        never_below_base=never_below_base,
    )

    # --- 9. README documents Phase 119 ---------------------------------------
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    row_start = readme.find("| 119 |")
    row_119 = readme[row_start:].split("\n", 1)[0] if row_start != -1 else ""
    emit(
        "README documents Phase 119",
        row_start != -1 and "119" in row_119,
        row=row_119,
    )

except Exception as exc:  # pragma: no cover
    emit("behavioural checks ran", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
raise SystemExit(0 if failures == 0 else 1)
