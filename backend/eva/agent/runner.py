from __future__ import annotations

import json
import re
import time
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

from ..core.config import ModelSettings
from ..core.web_context import remember_web_results
from ..observability.context import task_trace, trace_threat
from ..tools.registry import ToolRegistry
from .cognition import build_initial_plan, reflect_on_step
from .executor import ToolExecutor, ToolExecutionResult
from .planner import PlannedToolCall, PlannerError, ToolCallPlanner
from .policies import (
    POWER_TOOLS,
    agentic_goal,
    describe_tool_observation,
    explicitly_requests_screen,
    is_unsupported_capability,
    max_agent_steps,
    max_agent_steps_ceiling,
    max_consecutive_failures,
    max_screen_captures_per_task,
    max_steps_without_progress,
    max_tools_per_task,
    max_web_searches_per_task,
    tool_signature,
    user_asked_for_screenshot,
)
from ..screen.capture_grant import GRANTABLE_SCREEN_TOOLS, open_capture_grant
from ..screen.target_app import open_target_app_scope
from ..screen.type_grant import (
    DEFAULT_MAX_TYPES_PER_TASK,
    TYPE_TOOL,
    open_type_grant,
    open_typing_offer,
    text_is_from_user,
    user_asked_to_type,
)
from ..security.tool_gate import SCREEN_INPUT_TOOLS
from .paused_tasks import PausedTask, save_paused_task
from .state import AgentRunState
from .task import AgentStep, AgentTask, readable_observation as _readable_observation
from ..threat_defense.authorization import authorize_action
from ..threat_defense.taint import assess as assess_taint, source_type_for_tool, wrap_as_untrusted_data
from ..threat_defense.tool_scope import TaskToolScope
from .critic import DelegationContract, REVISE, honest_caveat, review_completion


def _is_interrupted(signal: Any) -> bool:
    """Phase 42 cooperative interruptibility: true if the caller asked the task
    to stop. Accepts a callable ``() -> bool``, a threading.Event-like object
    with ``is_set()``, or a plain truthy value. Fail-safe (never raises)."""
    if signal is None:
        return False
    try:
        if callable(signal):
            return bool(signal())
        is_set = getattr(signal, "is_set", None)
        if callable(is_set):
            return bool(is_set())
        return bool(signal)
    except Exception:
        return False


def _resolve_grounding(injected: Any) -> str:
    """Phase 44: the live situational grounding string for this task, or "".

    With no injection, auto-captures the situation only when perception is opted
    in (default off). A caller may inject a ready string or a ``Situation``
    (explicit intent, formatted regardless of the env gate) to drive the loop
    deterministically. Fail-safe: any error grounds nothing."""
    try:
        from ..perception.situational_model import ground_observation, perception_enabled

        if injected is not None:
            if isinstance(injected, str):
                return injected.strip()
            return ground_observation(injected)
        if not perception_enabled():
            return ""
        return ground_observation()
    except Exception:
        return ""


def _is_privileged_tool(registry: ToolRegistry, tool_name: str) -> bool:
    """A tool is privileged if the permission gate would gate it (confirm /
    override / hard_block) rather than let it run immediately."""
    try:
        from ..security import tool_gate

        spec = registry.get(tool_name)
        if spec is None:
            return False
        return tool_gate.classify_tool_call(spec) in {"confirm", "override", "hard_block"}
    except Exception:
        # Fail safe: if we cannot classify, treat it as privileged.
        return True


def _safe_log(memory: Any, session_id: str | None, kind: str, payload: dict[str, Any]) -> None:
    if memory is None or not session_id:
        return
    try:
        memory.log_event(session_id, kind, payload)
    except Exception:
        return


def _compact_tool_result(result: ToolExecutionResult) -> dict[str, Any]:
    payload = result.as_dict()
    raw = payload.get("result")
    if isinstance(raw, dict) and "results" in raw and isinstance(raw["results"], list):
        payload["result"] = {
            **raw,
            "results": raw["results"][:5],
        }
    return payload


_MAX_REPORTED_STEPS = 8


def summarize_progress(task: AgentTask, reason: str) -> str:
    """``reason`` plus what the loop actually gathered, when it stops early.

    Phase 93. Every early exit in this loop set a fixed sentence, logged
    ``task.observations`` to the event log, and showed the user none of them.
    The step-cap one even claimed to have kept the progress -- "I reached my
    maximum step limit, so I stopped with the progress I had." -- and then
    reported none of it.

    That was not academic. Driving "find the file that defines run_agentic_task
    and tell me what it does", ``code_search`` returned the correct file at STEP
    2; the loop spent four more steps, hit the cap, and returned the fixed
    sentence while six observations -- one of them the answer -- sat in the task.

    ``reason`` is kept verbatim rather than replaced, because *why* a run stopped
    is not the same fact as *what* it found, and the caller is the only thing
    that knows the first. Six exits share this helper and each keeps its own.

    Deliberately deterministic: no LLM call. This path is reached when a run has
    already gone wrong, and a summary that cannot fail, cannot cost quota and
    cannot invent anything is worth more here than a fluent one. It says plainly
    that the goal was NOT completed, so partial work is never mistaken for a
    finished answer.
    """
    performed = [step for step in task.steps if step.tool_name and (step.observation or "").strip()]
    if not performed:
        return f"{reason} I have nothing to show for it -- none of the steps returned anything usable."

    lines = [f"{reason} That is not a complete answer, but here is what I actually found:"]
    shown = performed[:_MAX_REPORTED_STEPS]
    for step in shown:
        text, untrusted = _readable_observation(step.observation)
        if not text:
            continue
        # "quoted output", not "external": the trust wrapper is applied to LOCAL
        # tool results too (the banner reads UNTRUSTED TRUSTED_TOOL CONTENT), so
        # calling a workspace search "external content" was itself a false claim
        # -- caught by reading a real reply rather than a test.
        marker = " (quoted output, unverified)" if untrusted else ""
        lines.append(f"- {step.tool_name}{marker}: {text}")
    remaining = len(performed) - len(shown)
    if remaining > 0:
        lines.append(f"- ...and {remaining} more step(s) not shown.")
    lines.append("Tell me which of those to follow up on and I can go further.")
    return "\n".join(lines)


def _provenance_suffix(verification: dict[str, Any] | None) -> str:
    """Short suffix so Eva never narrates an unproven action as plain done.

    Mirrors the provenance classes from ``postconditions.py``: only an
    ``independent`` + verified effect earns an unqualified "(verified)"; every
    weaker class says so plainly instead of upgrading into a false claim of
    success. The independent-and-NOT-verified case never reaches here — the
    executor already demotes ``ok`` to False for that, routing it to the
    failure branch in :func:`_observation_text` instead.
    """
    if not verification:
        return ""
    provenance = verification.get("provenance")
    if provenance == "independent" and verification.get("verified"):
        return " (verified)"
    if provenance == "self_reported":
        return " (self-reported)"
    if provenance == "observed":
        return " (unverified — please confirm the visible result)"
    if provenance == "unverified":
        return " (unverified)"
    return ""


def _observation_text(call: PlannedToolCall, result: ToolExecutionResult) -> str:
    if result.requires_confirmation:
        return f"{call.tool} requires confirmation before {result.action or 'continuing'}."
    if not result.ok:
        return f"{call.tool} failed: {result.error or 'unknown error'}"
    return describe_tool_observation(call.tool, result.result) + _provenance_suffix(result.verification)


def _step_made_progress(task: AgentTask, observation: str, *, ok: bool, verified: bool) -> bool:
    """Phase 119: did this EXECUTED step earn the adaptive loop one more step?

    A failed call, a refusal, or a gate pause (``ok`` is False for all three
    -- ``ToolExecutor._finalize`` demotes ``requires_confirmation`` to
    ``ok=False`` the same way an independently-failed post-condition is)
    never counts, matching the brief's "repeated identical calls, failures,
    refusals, gate pauses... do not count." An independently verified
    post-condition always counts. Otherwise, progress means the observation
    text is genuinely NEW -- not one this task has already seen, which is
    what "not a repeat of the same tool and args with the same result"
    actually cashes out to once results are compared by what the model reads
    rather than by the call shape: two calls with different args that both
    come back with the identical formatted text taught the loop nothing new
    the second time. Checked against ``task.observations`` AFTER this
    observation was appended, so a first-ever occurrence is a count of 1.
    """
    if not ok:
        return False
    if verified:
        return True
    text = (observation or "").strip()
    if not text:
        return False
    return task.observations.count(observation) <= 1


def _planned_tools(task: AgentTask) -> list[str]:
    return [step.tool_name for step in task.steps if step.tool_name]


def _executed_tools(task: AgentTask) -> list[str]:
    return [step.tool_name for step in task.steps if step.tool_name and step.status == "done"]


def _final_result(task: AgentTask, *, ok: bool, requires_confirmation: bool = False, action: str | None = None, events: list[dict[str, Any]] | None = None, safety_stops: list[str] | None = None, critic: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": ok,
        "task_id": task.id,
        "status": task.status,
        "final_response": task.final_response,
        "requires_confirmation": requires_confirmation,
        "action": action,
        "steps_count": len(task.steps),
        "tools_planned": _planned_tools(task),
        "tools_executed": _executed_tools(task),
        "safety_stops": safety_stops or [],
        "critic": critic,
        "task": task.as_dict(),
        "events": events or [],
        # Phase 119: honest reporting of the adaptive step budget -- how many
        # steps this task actually took, the budget it started with, the
        # budget it finished with (>= base only if it earned extensions),
        # the hard ceiling it could never pass, and whether it extended at
        # all. `steps_count` above is the authoritative "steps used" (it is
        # `len(task.steps)`, not a loop-iteration count, so a resumed task's
        # steps are counted exactly once).
        "step_budget": {
            "steps_used": len(task.steps),
            "base_budget": task.base_max_steps,
            "final_budget": task.max_steps,
            "ceiling": task.step_ceiling,
            "extended": task.step_extensions > 0,
            "extensions": task.step_extensions,
        },
    }


def _finalize_success(task, state, contract, session_context, *, events, safety_stops, memory, session_id):
    """Phase 41: gate a would-be "done" through the independent critic.

    The critic re-derives satisfaction from the run's real evidence (observations
    + Phase 38 verification counts) against the delegation contract. With no
    enforcing contract it accepts (advisory), so single-shot behavior is
    unchanged. With an enforcing contract that the evidence does not satisfy, the
    task is reported honestly (ok=False + a truthful caveat) rather than claiming
    a false completion. The permission/verification gates remain the hard
    boundaries; this is a quality gate on top of them.
    """
    verdict = review_completion(
        goal=task.user_goal,
        final_response=task.final_response,
        observations=list(task.observations),
        verified_successes=state.verified_successes,
        failures=state.failures,
        contract=contract,
        revisions_used=state.critic_revisions,
    )
    events.append({"type": "agent_critic", "task_id": task.id, "message": ", ".join(verdict.reasons), "satisfied": verdict.satisfied})
    from ..observability.context import trace_critic

    trace_critic(verdict.as_dict())
    _safe_log(memory, session_id, "agent_critic_review", {"task_id": task.id, "verdict": verdict.as_dict()})

    ok = True
    stops = list(safety_stops)
    if contract is not None and contract.enforcing and not verdict.satisfied:
        task.final_response = f"{task.final_response}{honest_caveat(verdict)}"
        task.status = "attempted"
        ok = False
        stops.append("critic_rejected")
    return _return_task(task, session_context, ok=ok, events=events, safety_stops=stops, critic=verdict.as_dict())


def _store_task_state(session_context: Any, result: dict[str, Any]) -> None:
    if not isinstance(session_context, dict):
        return
    session_context["last_agent_task"] = {
        "task_id": result.get("task_id"),
        "status": result.get("status"),
        "steps_count": result.get("steps_count"),
        "tools_planned": result.get("tools_planned"),
        "tools_executed": result.get("tools_executed"),
        "last_observation": (result.get("task") or {}).get("observations", [])[-1:] if isinstance(result.get("task"), dict) else [],
        "final_response": result.get("final_response"),
        "requires_confirmation": result.get("requires_confirmation"),
        "action": result.get("action"),
        "safety_stops": result.get("safety_stops"),
        "step_budget": result.get("step_budget"),
    }
    session_context["active_task_status"] = result.get("status")


def _target_in_front(target: str) -> bool:
    """Is the app this task opened the foreground window? Focus it once if not.

    Checked immediately before a granted keystroke, so a window that lost focus
    between steps (a notification, the user clicking elsewhere) gets typing only
    after it is verifiably back in front. Fails closed: any error means no grant.
    """
    try:
        from ..desktop.verifier import verify_window_focused
        from ..desktop.windows import focus_window

        if verify_window_focused(target, retries=2).get("verified"):
            return True
        focus_window(target)
        return bool(verify_window_focused(target, retries=4).get("verified"))
    except Exception:
        return False


def _return_task(task: AgentTask, session_context: Any, **kwargs: Any) -> dict[str, Any]:
    result = _final_result(task, **kwargs)
    _store_task_state(session_context, result)
    return result


async def run_agentic_task(user_message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    # Phase 110: a task whose user-typed goal asks to type may SEE
    # screen.type_text for its whole run. Visibility only; each call still needs
    # a type grant (opened per call below) or it stays confirm-class. Opened here,
    # around the whole run, on the coroutine that plans -- the planner reads the
    # offer when it builds its tool list.
    goal = agentic_goal(user_message)
    if context.get("goal_from_user") is True and user_asked_to_type(goal):
        with open_typing_offer(goal):
            return await _run_agentic_task(user_message, context)
    return await _run_agentic_task(user_message, context)


@dataclass
class _RunEnv:
    """Phase 117. Everything one step of the plan->act->observe loop needs,
    bundled so the loop body can be shared between a fresh run
    (`_run_agentic_task`) and a resumed one (`resume_agentic_task`) instead of
    existing twice. `loop_vars` holds the two fields later steps mutate and
    earlier steps read (`typing_target`, `types_used`) in a plain dict rather
    than as separate locals, because a resumed run reconstructs this bundle
    from a snapshot and needs somewhere to put their restored values.
    """

    task: AgentTask
    state: AgentRunState
    goal: str
    context: dict[str, Any]
    registry: ToolRegistry
    executor: ToolExecutor
    memory: Any
    session_id: Any
    session_context: Any
    history: list
    planner: ToolCallPlanner
    max_failures: int
    max_no_progress: int
    tool_scope: TaskToolScope
    contract: DelegationContract | None
    grounding: str
    events: list[dict[str, Any]]
    safety_stops: list[str]
    loop_vars: dict[str, Any]
    execute_tools: bool


# A tool-gate pending id, exactly as `permissions/pending_actions.py::EvaPendingAction.new`
# mints it (`act_` + 12 hex chars). Used to double-check, before snapshotting a
# pause, that `result.action` really is a pending id and not one of the other
# strings this loop puts in that field (a tool name, a power-action name) --
# see `_pause_and_return`.
_PENDING_ID_RE = re.compile(r"^act_[a-zA-Z0-9_-]+$")


def _pause_and_return(
    env: _RunEnv,
    *,
    index: int,
    call: PlannedToolCall,
    step: AgentStep,
    continue_after_tools: bool,
    result: ToolExecutionResult,
) -> dict[str, Any]:
    """The task is stopping because `result.requires_confirmation` is true.

    This is reached from exactly two places in `_process_executed_call`, and
    both are reached only AFTER `executor.execute`/`execute_approved` has
    actually run the call through `ToolRegistry.run` -- which is the ONLY
    place that ever sets `requires_confirmation` on a result, always together
    with a real `pending_id` (see `_create_gated_pending` in registry.py and
    `ToolExecutionResult`'s `action` field in executor.py). Every OTHER
    confirmation-shaped stop in this loop -- injection escalation, a power
    action, low-confidence escalation, the planner's own
    `confirmation_required` -- returns earlier, before a call is ever
    executed, so none of them can reach this function. That is what makes a
    snapshot safe to save here unconditionally-when-reached: this function
    being called IS the proof that a real tool-gate pending action exists to
    key it by. The regex check is a second, defensive belt on that same
    buckle, not the load-bearing part.

    Also captures the CURRENT delegated-role stack (`role_context.active_roles()`)
    into the snapshot. Whether this call is executing on the original,
    role-scoped coroutine (a fresh pause: `run_delegated`'s `with
    role_scope(role):` is still open around the whole `await
    run_agentic_task(...)`) or on an already-resumed one that is pausing a
    SECOND time (`resume_agentic_task` already reopened the stack before
    driving the loop further), `active_roles()` here reads whatever role
    containment is actually in force for this exact step -- which is exactly
    what must be restored the next time this task resumes. An ordinary,
    never-delegated task reads `()`, so nothing changes for it.
    """
    from ..agents.role_context import active_roles

    action_id = str(result.action or "")
    if _PENDING_ID_RE.match(action_id):
        save_paused_task(
            PausedTask(
                pending_id=action_id,
                session_id=env.session_id,
                env=env,
                index=index,
                call=call,
                step=step,
                continue_after_tools=continue_after_tools,
                created_at=time.monotonic(),
                role_stack=active_roles(),
            )
        )
    env.task.status = "waiting_for_confirmation"
    env.task.final_response = result.error or "This action requires confirmation."
    return _return_task(
        env.task,
        env.session_context,
        ok=False,
        requires_confirmation=True,
        action=result.action,
        events=env.events,
        safety_stops=env.safety_stops,
    )


def _process_executed_call(
    env: _RunEnv,
    *,
    index: int,
    call: PlannedToolCall,
    step: AgentStep,
    result: ToolExecutionResult,
    continue_after_tools: bool,
) -> dict[str, Any] | None:
    """Everything the loop does once it has a tool result: taint tracking,
    the observation/reflection record, recovery, and every completion branch.
    Returns a final result dict when the task should stop, or None to keep
    looping.

    Shared verbatim between a step that just ran (`_run_step`) and a step
    that is the approved replay of one that paused the task earlier
    (`resume_agentic_task`) -- Phase 117's whole point is that those two
    cases are indistinguishable from here on: identical taint handling,
    identical budgets, identical reflection. The only thing that differs
    between them happened BEFORE this function, in how `result` was obtained.
    """
    task, state, goal = env.task, env.state, env.goal
    memory, session_id, session_context = env.memory, env.session_id, env.session_context
    events, safety_stops, contract = env.events, env.safety_stops, env.contract

    if call.tool in {"web_search", "browser_search"} and result.ok:
        remember_web_results(session_context, result.result)
    observation = _observation_text(call, result)
    # Phase 40 taint-tracking: if this tool's result is untrusted external
    # content carrying injection markers, fence it as data, flag the task
    # context, and record the threat so a later privileged step escalates.
    source_type = source_type_for_tool(call.tool)
    if result.ok and result.result is not None:
        verdict = assess_taint(result.result, source_type)
        if verdict.injection_detected:
            state.record_injection(source_type)
            observation = wrap_as_untrusted_data(observation, source_type)
            events.append({"type": "agent_threat", "task_id": task.id, "step": index, "message": verdict.summary})
            trace_threat({"tool": call.tool, "action": "taint", **verdict.as_dict()})
            _safe_log(memory, session_id, "agent_untrusted_content_flagged", {"task_id": task.id, "step": index, "tool": call.tool, "verdict": verdict.as_dict()})
    step.observation = observation
    step.status = "done" if result.ok else "failed"
    step.error = result.error
    task.add_observation(observation)
    events.append({"type": "agent_observation", "task_id": task.id, "step": index, "message": observation})
    # Phase 39/119: whether the post-condition was *independently* verified,
    # computed once here so both the reliability bookkeeping below and the
    # Phase 119 adaptive step budget read the same signal.
    verified = bool(
        result.ok
        and result.verification
        and result.verification.get("independent")
        and result.verification.get("verified")
    )
    task.status = "reflecting"
    reflection = reflect_on_step(goal, task, step, result)
    task.add_reflection(reflection)
    state.last_confidence = reflection.confidence
    events.append(
        {
            "type": "agent_reflection",
            "task_id": task.id,
            "step": index,
            "message": reflection.summary,
            "status": reflection.status,
            "confidence": reflection.confidence,
            "next_focus": reflection.next_focus,
        }
    )
    _safe_log(memory, session_id, "agent_tool_executed", {"task_id": task.id, "step": index, "tool": call.tool, "args": call.args, "result": _compact_tool_result(result)})
    _safe_log(memory, session_id, "agent_step_reflection", {"task_id": task.id, "step": index, "reflection": reflection.as_dict()})

    # Phase 119: a gate pause is not "no progress" -- it is not a completed
    # step at all yet (the call has not run; `_pause_and_return`, reached
    # below, ends this function before anything else happens). Recorded only
    # for the step's real conclusion, so the SAME gated call is never counted
    # twice against the no-progress streak: once as the pause, once again as
    # the resumed execution.
    if reflection.status != "needs_confirmation":
        state.record_step_progress(_step_made_progress(task, observation, ok=result.ok, verified=verified))

    # Phase 39: track reliability. A successful step resets the failure
    # streak; a step whose post-condition was independently verified
    # (Phase 38) counts as proven progress.
    if result.ok:
        state.record_success(verified)

    # Phase 39: a failed step no longer kills the task outright. Record
    # the failure, feed it back as an observation, and attempt bounded
    # recovery — the loop replans until the consecutive-failure budget or
    # a stall guard is hit, then stops honestly instead of burning every
    # step or over-claiming success.
    if reflection.status == "blocked":
        state.record_failure(result.error)
        recovery = f"Attempt at step {index} failed: {result.error or observation}. I'll try a different safe approach."
        task.add_observation(recovery)
        events.append({"type": "agent_recovery", "task_id": task.id, "step": index, "message": recovery})
        _safe_log(
            memory,
            session_id,
            "agent_step_failed_recovering",
            {"task_id": task.id, "step": index, "error": result.error, "consecutive_failures": state.consecutive_failures},
        )
        if state.failure_budget_exceeded(env.max_failures):
            task.status = "failed"
            task.final_response = (
                f"I couldn't complete this after {state.consecutive_failures} failed attempts. "
                f"Last issue: {result.error or observation}"
            )
            safety_stops.append("failure_budget_exceeded")
            _safe_log(memory, session_id, "agent_task_failed", {"task_id": task.id, "reason": "failure_budget_exceeded", "observation": observation})
            return _return_task(task, session_context, ok=False, events=events, safety_stops=safety_stops)
        if state.stalled(env.max_no_progress):
            task.status = "failed"
            task.final_response = summarize_progress(task, "I stopped because I wasn't making progress toward the goal.")
            safety_stops.append("no_progress")
            _safe_log(memory, session_id, "agent_task_failed", {"task_id": task.id, "reason": "no_progress", "observation": observation})
            return _return_task(task, session_context, ok=False, events=events, safety_stops=safety_stops)
        return None

    if reflection.status == "needs_confirmation":
        return _pause_and_return(env, index=index, call=call, step=step, continue_after_tools=continue_after_tools, result=result)

    if call.tool in {"web_search", "research_web", "browser_search"} and result.ok and _web_summary_goal_without_open(goal):
        task.status = "done"
        task.final_response = observation
        _safe_log(memory, session_id, "agent_task_done", {"task_id": task.id, "reason": "web_summary_complete", "final_response": task.final_response})
        return _finalize_success(task, state, contract, session_context, events=events, safety_stops=safety_stops, memory=memory, session_id=session_id)

    if result.requires_confirmation:
        return _pause_and_return(env, index=index, call=call, step=step, continue_after_tools=continue_after_tools, result=result)

    if call.tool in {"capture_screen", "analyze_screen"} and not result.ok:
        task.status = "failed"
        task.final_response = observation
        safety_stops.append("screen_tool_failed")
        _safe_log(memory, session_id, "agent_task_failed", {"task_id": task.id, "reason": "screen_tool_failed", "observation": observation})
        return _return_task(task, session_context, ok=False, events=events, safety_stops=safety_stops)

    if call.tool == "analyze_screen" and isinstance(result.result, dict) and not result.result.get("ok", True):
        task.status = "failed"
        task.final_response = observation
        safety_stops.append("screen_analysis_failed")
        _safe_log(memory, session_id, "agent_task_failed", {"task_id": task.id, "reason": "screen_analysis_failed", "observation": observation})
        return _return_task(task, session_context, ok=False, events=events, safety_stops=safety_stops)

    if not continue_after_tools:
        task.status = "done"
        task.final_response = observation
        _safe_log(memory, session_id, "agent_task_done", {"task_id": task.id, "final_response": task.final_response})
        return _finalize_success(task, state, contract, session_context, events=events, safety_stops=safety_stops, memory=memory, session_id=session_id)

    return None


async def _run_step(
    env: _RunEnv,
    index: int,
    *,
    forced: tuple[PlannedToolCall, AgentStep, ToolExecutionResult, bool] | None = None,
) -> dict[str, Any] | None:
    """One iteration of the plan->act->observe loop.

    `forced`, when given, is `(call, step, result, continue_after_tools)` for
    a call that has ALREADY been executed -- the approved replay of a call
    that paused the task (Phase 117 resume). In that case planning, every
    gate/budget/escalation check, and grant handling are all skipped: they
    already ran once, before the pause, and none of them should run twice --
    re-running the confidence/injection/scope checks on resume would let a
    task that was fine to pause be re-evaluated against a DIFFERENT (later)
    state.last_confidence or state.injection_flagged than the one the pause
    itself was judged against, which is not a rerun, it is a second and
    different decision. `forced=None` is the ordinary path: plan, gate,
    execute.
    """
    task, state, goal, context = env.task, env.state, env.goal, env.context
    registry, executor = env.registry, env.executor
    memory, session_id, session_context = env.memory, env.session_id, env.session_context
    history, planner = env.history, env.planner
    tool_scope, contract, grounding = env.tool_scope, env.contract, env.grounding
    events, safety_stops, loop_vars = env.events, env.safety_stops, env.loop_vars
    execute_tools = env.execute_tools

    if forced is not None:
        call, step, result, continue_after_tools = forced
        if result.ok and call.tool in {"open_app", "window_focus"}:
            target = str(call.args.get("app") or call.args.get("query") or "").strip()
            verification = result.verification or {}
            payload = result.result if isinstance(result.result, dict) else {}
            if target and (verification.get("verified") or payload.get("verified")):
                loop_vars["typing_target"] = target
        return _process_executed_call(env, index=index, call=call, step=step, result=result, continue_after_tools=continue_after_tools)

    # Phase 42 mid-task interruptibility: the caller can ask the task to
    # stop between steps (context["interrupt"] callable/Event/flag). Eva
    # stops gracefully with whatever progress it had, no partial action.
    if _is_interrupted(context.get("interrupt")):
        task.status = "interrupted"
        task.final_response = "I stopped because you interrupted the task."
        safety_stops.append("interrupted")
        _safe_log(memory, session_id, "agent_task_interrupted", {"task_id": task.id, "step": index})
        return _return_task(task, session_context, ok=False, events=events, safety_stops=safety_stops)
    task.status = "planning"
    events.append({"type": "agent_step", "task_id": task.id, "step": index, "message": f"Step {index}: planning"})
    task_context = {
        "goal": goal,
        "plan": list(task.plan),
        "observations": list(task.observations),
        "reflections": [reflection.as_dict() for reflection in task.reflections[-4:]],
        "steps": [step.as_dict() for step in task.steps],
        "limits": {
            "max_steps": task.max_steps,
            "max_tool_calls": task.max_tool_calls,
            "max_web_searches": task.max_web_searches,
            "max_screen_captures": task.max_screen_captures,
            "tool_calls_used": state.tool_calls,
            "web_searches_used": state.web_searches,
            "screen_captures_used": state.screen_captures,
        },
    }
    if grounding:
        task_context["situation"] = grounding

    try:
        decision = await planner.plan(goal, history, mode="agent_step", task_context=task_context)
    except PlannerError as exc:
        state.record_invalid_json()
        _safe_log(memory, session_id, "agent_planner_error", {"task_id": task.id, "step": index, "error": str(exc)})
        if state.invalid_json_errors >= 2:
            task.status = "failed"
            task.final_response = "I could not plan this safely after two attempts. Try a simpler task."
            safety_stops.append("planner_invalid_json_twice")
            return _return_task(task, session_context, ok=False, events=events, safety_stops=safety_stops)
        # Phase 119: a planner retry executed no step, so it must not inherit
        # the previous real step's `last_step_progress` -- otherwise, landing
        # on the budget boundary right after a retry would grant an
        # extension for doing nothing. Deliberately NOT routed through
        # `record_step_progress`: the no-progress streak counts only
        # executed steps (this already has its own bounded 2-attempt retry,
        # just above).
        state.last_step_progress = False
        return None

    _safe_log(
        memory,
        session_id,
        "agent_step_planned",
        {
            "task_id": task.id,
            "step": index,
            "decision": {
                "type": decision.type,
                "reason": decision.reason,
                "tool_calls": [{"tool": call.tool, "args": call.args} for call in decision.tool_calls],
                "continue_after_tools": decision.continue_after_tools,
            },
        },
    )

    if decision.type in {"answer", "done"}:
        # Phase 41: the critic reviews the planner's "done" against the
        # contract BEFORE accepting it. If an enforcing contract isn't
        # satisfied yet and the revision budget allows, send the task
        # back for another attempt (critic -> revise) with feedback
        # instead of accepting a premature completion.
        if contract is not None and contract.enforcing:
            pre_verdict = review_completion(
                goal=goal,
                final_response=decision.final_response,
                observations=list(task.observations),
                verified_successes=state.verified_successes,
                failures=state.failures,
                contract=contract,
                revisions_used=state.critic_revisions,
            )
            if not pre_verdict.satisfied and pre_verdict.recommendation == REVISE:
                state.record_critic_revision()
                feedback = f"Critic sent this back (revision {state.critic_revisions}): {', '.join(pre_verdict.reasons)} Address the unmet criteria before finishing."
                task.add_observation(feedback)
                events.append({"type": "agent_critic", "task_id": task.id, "step": index, "message": feedback, "satisfied": False})
                _safe_log(memory, session_id, "agent_critic_revision", {"task_id": task.id, "step": index, "reasons": list(pre_verdict.reasons)})
                # Phase 119: same reasoning as the planner-retry branch above --
                # a revision executed no step and must not inherit stale
                # progress from an earlier real step.
                state.last_step_progress = False
                return None
        step = AgentStep(index=index, thought_summary=decision.reason, planned_action=decision.type, observation=decision.final_response, status="done")
        task.add_step(step)
        task.status = "done"
        task.final_response = decision.final_response
        events.append({"type": "agent_step", "task_id": task.id, "step": index, "message": f"Step {index}: done"})
        _safe_log(memory, session_id, "agent_task_done", {"task_id": task.id, "final_response": task.final_response})
        return _finalize_success(task, state, contract, session_context, events=events, safety_stops=safety_stops, memory=memory, session_id=session_id)

    if decision.type == "confirmation_required":
        step = AgentStep(index=index, thought_summary=decision.reason, planned_action="confirmation_required", observation=decision.final_response, status="skipped")
        task.add_step(step)
        task.status = "waiting_for_confirmation"
        task.final_response = decision.final_response
        events.append({"type": "agent_step", "task_id": task.id, "step": index, "message": f"Step {index}: confirmation required"})
        _safe_log(memory, session_id, "agent_task_waiting_for_confirmation", {"task_id": task.id, "action": decision.action, "message": decision.final_response})
        return _return_task(task, session_context, ok=False, requires_confirmation=True, action=decision.action, events=events, safety_stops=safety_stops)

    call = decision.tool_calls[0]
    step = AgentStep(index=index, thought_summary=decision.reason, planned_action="tool_calls", tool_name=call.tool, tool_args=call.args, status="running")
    task.add_step(step)
    events.append({"type": "agent_step", "task_id": task.id, "step": index, "message": f"Step {index}: tool {call.tool}"})

    if state.tool_calls >= task.max_tool_calls:
        step.status = "failed"
        step.error = "tool_limit_reached"
        task.status = "failed"
        task.final_response = summarize_progress(task, "I stopped because the tool-call limit was reached.")
        safety_stops.append("tool_limit_reached")
        return _return_task(task, session_context, ok=False, events=events, safety_stops=safety_stops)

    if call.tool in {"web_search", "research_web", "browser_search"} and state.web_searches >= task.max_web_searches:
        step.status = "failed"
        step.error = "web_search_limit_reached"
        task.status = "failed"
        task.final_response = summarize_progress(task, "I stopped because the web-search limit was reached.")
        safety_stops.append("web_search_limit_reached")
        return _return_task(task, session_context, ok=False, events=events, safety_stops=safety_stops)

    if call.tool in {"capture_screen", "analyze_screen"} or (call.tool == "desktop_observe" and bool(call.args.get("include_screen"))):
        if not explicitly_requests_screen(goal):
            step.status = "failed"
            step.error = "screen_capture_not_explicit"
            task.status = "failed"
            task.final_response = "I did not capture the screen because you did not explicitly ask me to inspect it."
            safety_stops.append("screen_capture_not_explicit")
            return _return_task(task, session_context, ok=False, events=events, safety_stops=safety_stops)
        if state.screen_captures >= task.max_screen_captures:
            step.status = "failed"
            step.error = "screen_capture_limit_reached"
            task.status = "failed"
            task.final_response = summarize_progress(task, "I stopped because the screen-capture limit was reached.")
            safety_stops.append("screen_capture_limit_reached")
            return _return_task(task, session_context, ok=False, events=events, safety_stops=safety_stops)

    if call.tool in POWER_TOOLS:
        step.status = "skipped"
        step.observation = "Power actions require confirmation."
        task.add_observation(step.observation)
        task.status = "waiting_for_confirmation"
        task.final_response = "This power action requires confirmation before I can continue."
        events.append({"type": "agent_observation", "task_id": task.id, "step": index, "message": step.observation})
        # Deliberately NOT snapshotted (Phase 117): `action` here is a power-action
        # NAME ("shutdown", ...), never a pending_id -- POWER_TOOLS is intercepted
        # before `executor.execute` ever runs, so no gate call and no pending
        # action exist for this to resume. See `_pause_and_return`'s docstring.
        return _return_task(task, session_context, ok=False, requires_confirmation=True, action=str(call.args.get("action") or "power_action"), events=events, safety_stops=safety_stops)

    if state.repeated_without_progress(call):
        step.status = "failed"
        step.error = "repeated_action_without_progress"
        task.status = "failed"
        task.final_response = summarize_progress(task, "I stopped because the same action repeated without a new observation.")
        safety_stops.append(f"repeated_action:{tool_signature(call)}")
        return _return_task(task, session_context, ok=False, events=events, safety_stops=safety_stops)

    state.record_tool(call)

    if not execute_tools:
        step.status = "skipped"
        step.observation = f"Dry run: planned {call.tool} with args {json.dumps(call.args, ensure_ascii=False)}."
        task.add_observation(step.observation)
        task.status = "done"
        task.final_response = step.observation
        events.append({"type": "agent_observation", "task_id": task.id, "step": index, "message": step.observation})
        _safe_log(memory, session_id, "agent_tool_dry_run", {"task_id": task.id, "step": index, "tool": call.tool, "args": call.args})
        return _return_task(task, session_context, ok=True, events=events, safety_stops=safety_stops)

    # Phase 40c least-privilege: if this task was handed a tool scope, a
    # planned tool outside it is denied before it runs — no matter what
    # the planner proposed. Unscoped tasks stay unrestricted.
    if not tool_scope.is_allowed(call.tool):
        denial = f"`{call.tool}` is outside this task's allowed tool scope, so I won't run it."
        step.status = "skipped"
        step.observation = denial
        task.add_observation(denial)
        task.status = "failed"
        task.final_response = denial
        safety_stops.append(f"out_of_scope:{call.tool}")
        events.append({"type": "agent_threat", "task_id": task.id, "step": index, "message": denial})
        _safe_log(memory, session_id, "agent_out_of_scope", {"task_id": task.id, "step": index, "tool": call.tool})
        return _return_task(task, session_context, ok=False, events=events, safety_stops=safety_stops)

    # Phase 40 moat: untrusted content proposes, it never authorizes. If
    # injected/untrusted content has entered the task context and the
    # next action is privileged, it cannot run on that content's say-so —
    # escalate to explicit user confirmation carrying an injection
    # warning. The permission gate still governs it too.
    privileged = _is_privileged_tool(registry, call.tool)
    auth = authorize_action(
        tool_privileged=privileged,
        context_tainted=state.injection_flagged,
        injection_detected=state.injection_flagged,
    )
    if auth.escalate:
        warning = (
            f"WARNING - possible prompt injection: `{call.tool}` was proposed after untrusted "
            f"content ({', '.join(state.tainted_sources) or 'external source'}) entered the "
            f"conversation. Untrusted content can suggest actions but cannot authorize them. "
            f"Confirm explicitly if you want me to run this."
        )
        step.status = "skipped"
        step.observation = warning
        task.add_observation(warning)
        task.status = "waiting_for_confirmation"
        task.final_response = warning
        safety_stops.append("injection_authorization_blocked")
        events.append({"type": "agent_threat", "task_id": task.id, "step": index, "message": warning})
        trace_threat({"tool": call.tool, "action": "escalate", **auth.as_dict(), "sources": list(state.tainted_sources)})
        _safe_log(memory, session_id, "agent_injection_escalation", {"task_id": task.id, "step": index, "tool": call.tool, "reason": auth.reason})
        # Deliberately NOT snapshotted (Phase 117): `action` here is `call.tool`,
        # not a pending_id -- this branch also returns before `executor.execute`
        # ever runs. A tainted task must never be laundered by a confirm, so this
        # is not an oversight to fix, it is the boundary the hard safety rule
        # names explicitly.
        return _return_task(task, session_context, ok=False, requires_confirmation=True, action=call.tool, events=events, safety_stops=safety_stops)

    # Phase 42 confidence-aware escalation: when the caller sets a minimum
    # action confidence and the agent's recent confidence is below it, an
    # otherwise-auto (allow-class) action asks for confirmation first.
    # Escalation only ever ADDS friction, so it is always safe.
    min_action_confidence = context.get("min_action_confidence")
    if (
        min_action_confidence is not None
        and not privileged
        and state.last_confidence is not None
        and state.last_confidence < float(min_action_confidence)
    ):
        message = (
            f"I'm not confident enough ({state.last_confidence:.2f} < {float(min_action_confidence):.2f}) to run "
            f"`{call.tool}` on my own — confirm if you'd like me to proceed."
        )
        step.status = "skipped"
        step.observation = message
        task.add_observation(message)
        task.status = "waiting_for_confirmation"
        task.final_response = message
        safety_stops.append("low_confidence_escalation")
        events.append({"type": "agent_calibration", "task_id": task.id, "step": index, "message": message})
        _safe_log(memory, session_id, "agent_low_confidence_escalation", {"task_id": task.id, "step": index, "tool": call.tool, "confidence": state.last_confidence})
        # Deliberately NOT snapshotted (Phase 117), same reason as above: no
        # gate call happened, so `call.tool` here is not a pending_id.
        return _return_task(task, session_context, ok=False, requires_confirmation=True, action=call.tool, events=events, safety_stops=safety_stops)

    # Phase 109: a screenshot the user asked for in their own words runs
    # without an override phrase. Every condition is checked HERE, on the
    # thread that executes the call (a grant opened around a thread hop
    # is a silent no-op -- Phase 103): the goal was typed by the user
    # (only the chat routes set goal_from_user), it explicitly asks for
    # the screen, no injected content has tainted the task, and the
    # capture cap was already enforced above. Anything else keeps the
    # ordinary override prompt.
    # Phase 117 round 4: for a screen-input tool, expose the TASK-VERIFIED
    # target app (if any) to the gate, so a pending action created from this
    # call records that app's window rather than "whatever is foreground" --
    # the exact bug round 3 fixed at approval time and round 4 found moved to
    # gate-creation time (foreground was Chrome; the task's verified app was
    # Calculator). Opened here, around the whole execute call, on THIS
    # coroutine -- the Phase 103 rule again: no thread hop happens between
    # here and `_create_gated_pending` reading it, so this is safe by
    # construction. `loop_vars["typing_target"]` is `None` until an
    # `open_app`/`window_focus` call's result independently verifies an app,
    # which is exactly the scope `open_target_app_scope` is meant to carry.
    #
    # Round 5: opened ONLY when `typing_target` is actually set. A `gui:`
    # task (`fast_command_gui.py::_run_task_in_scope`) may already have an
    # OUTER `open_target_app_scope` in force, set from its own console-side
    # verified focus, before this loop's planner ever calls `open_app`/
    # `window_focus` itself. Unconditionally opening a scope here with
    # `None` would REPLACE that outer value for the duration of this call --
    # ContextVar.set has no notion of "leave it alone" -- so this call site
    # opens nothing at all when there is no inner (in-loop-verified) app,
    # letting whatever outer scope is already active (gui:'s, or none) keep
    # applying. The inner value, when present, always wins: it is a MORE
    # specific verification (this exact task, this exact step) than the
    # outer one (the console's pre-focus, done once before the loop started).
    inner_target_app = loop_vars["typing_target"]
    target_app_scope = open_target_app_scope(inner_target_app) if (call.tool in SCREEN_INPUT_TOOLS and inner_target_app is not None) else nullcontext()
    with target_app_scope:
        if (
            call.tool in GRANTABLE_SCREEN_TOOLS
            and context.get("goal_from_user") is True
            and user_asked_for_screenshot(goal)
            and not state.injection_flagged
        ):
            with open_capture_grant(goal):
                result = executor.execute(call)
        elif (
            call.tool == TYPE_TOOL
            and context.get("goal_from_user") is True
            and user_asked_to_type(goal)
            and text_is_from_user(str(call.args.get("text") or ""), goal)
            and not state.injection_flagged
            and loop_vars["types_used"] < DEFAULT_MAX_TYPES_PER_TASK
            and loop_vars["typing_target"] is not None
            and _target_in_front(loop_vars["typing_target"])
        ):
            # Phase 110: the user's own words, into the app this task opened,
            # with that app verified in front immediately before typing.
            loop_vars["types_used"] += 1
            with open_type_grant(str(call.args.get("text") or "")):
                result = executor.execute(call)
        else:
            result = executor.execute(call)
    if result.ok and call.tool in {"open_app", "window_focus"}:
        target = str(call.args.get("app") or call.args.get("query") or "").strip()
        verification = result.verification or {}
        payload = result.result if isinstance(result.result, dict) else {}
        if target and (verification.get("verified") or payload.get("verified")):
            loop_vars["typing_target"] = target

    return _process_executed_call(env, index=index, call=call, step=step, result=result, continue_after_tools=decision.continue_after_tools)


async def _drive_loop(
    env: _RunEnv,
    *,
    start_index: int,
    forced: tuple[PlannedToolCall, AgentStep, ToolExecutionResult, bool] | None = None,
) -> dict[str, Any]:
    """Runs the plan->act->observe loop from `start_index` while `task.max_steps`
    -- the current adaptive budget, Phase 119 -- allows. `forced` supplies the
    FIRST step's already-executed call/result instead of planning it (Phase
    117 resume: the just-approved action); every step after that plans
    normally. A fresh run calls this with `start_index=1, forced=None`;
    `resume_agentic_task` calls it with the paused step's own index and the
    approved result, reusing the SAME `env` (so the SAME `state` and the
    SAME, possibly-already-grown, `task.max_steps`) -- a resumed task's step
    budget is never reset and never loses extensions it already earned.

    `task.max_steps` is deliberately re-read every iteration (a `while`, not
    the `range()` this replaced) because Phase 119 grows it in place: a fixed
    `range` is computed once and would never see the growth.
    """
    task, state = env.task, env.state
    index = start_index
    while index <= task.max_steps:
        outcome = await _run_step(env, index, forced=forced if index == start_index else None)
        if outcome is not None:
            return outcome

        # Phase 119 stall detection: two EXECUTED steps in a row that earned
        # no progress (not two mere loop iterations -- a planner-JSON retry
        # or a critic revision never touches this streak, see `_run_step`)
        # stop the errand early rather than burning the rest of the budget.
        # This is the loosely-related-but-distinct sibling of the exact
        # tool+args repeat guard above (`state.repeated_without_progress`),
        # which still fires first and separately for that narrower case.
        if state.no_progress_stalled(2):
            task.status = "failed"
            task.final_response = summarize_progress(task, "I stopped because two steps in a row made no verified progress.")
            env.safety_stops.append("stall_detected")
            _safe_log(env.memory, env.session_id, "agent_task_failed", {"task_id": task.id, "reason": "stall_detected", "observations": task.observations})
            return _return_task(task, env.session_context, ok=False, events=env.events, safety_stops=env.safety_stops)

        if index == task.max_steps:
            # At the budget boundary: extend by exactly one step, and only
            # one, if the step that just ran earned it and there is still
            # ceiling room -- never unconditionally (that would make the cap
            # meaningless) and never past the hard ceiling (never unbounded).
            if state.last_step_progress and task.max_steps < task.step_ceiling:
                task.max_steps += 1
                task.step_extensions += 1
            else:
                break
        index += 1

    task.status = "failed"
    # Phase 93: this used to be a fixed sentence claiming "I stopped with the
    # progress I had", while every observation went to the event log and none
    # of it to the user. The run still FAILED -- status and safety_stops are
    # unchanged -- but failing is not a reason to withhold work already done.
    task.final_response = summarize_progress(task, f"I hit my {task.max_steps}-step limit before finishing.")
    env.safety_stops.append("max_steps_reached")
    _safe_log(env.memory, env.session_id, "agent_task_failed", {"task_id": task.id, "reason": "max_steps_reached", "observations": task.observations})
    return _return_task(task, env.session_context, ok=False, events=env.events, safety_stops=env.safety_stops)


async def resume_agentic_task(snapshot: PausedTask, executed_result: Any) -> dict[str, Any]:
    """Phase 117: continue a task after the ONE pending action that paused it
    has been approved and actually run (via `ToolRegistry.run_approved`).

    `snapshot` must already have been popped from the paused-task store
    (`paused_tasks.take_paused_task` is single-use) -- this function trusts
    it the same way `run_approved` trusts ITS caller: reachable only after a
    real ledger confirmation of this exact pending_id, checked by
    `confirmation.py` before this is ever called. It does not re-check
    approval, re-run the gate, or re-open a Phase 109/110 screen/typing
    grant for the already-executed step -- those already happened (or
    correctly didn't) the first time. Grants for any LATER step in this
    resumed run are opened exactly as they always are, fresh, inside
    `_run_step`, on this coroutine -- never smuggled through the snapshot
    (the Phase 103 lesson: a ContextVar scope only holds on the thread that
    opens it, so grants cannot be pre-opened before the hop into `run_async`
    and carried across).

    `executed_result` is whatever `run_approved` returned for the tool --
    success or failure. It is wrapped through `ToolExecutor.execute_approved`
    the same way a normal call's result is wrapped, so a FAILED approved
    action still resumes the task: it becomes this step's observation and
    feeds the loop's ordinary recovery logic (retry budget, stall guard),
    exactly like an unpaused step failing mid-run. Stopping outright on a
    failed approval was the alternative; feeding it back was chosen because
    the loop already has tested, honest failure handling for "the last thing
    I tried didn't work" and a second special case would just be a worse
    copy of it.

    Role containment (review fix, Phase 117): `run_delegated`'s `with
    role_scope(role): await run_agentic_task(...)` closes the moment a pause
    RETURNS -- a pause is exactly that, a return -- so without this, every
    step planned AFTER a resume would run with `active_roles() == ()`, and a
    delegated `research` sub-task that paused and got confirmed would come
    back with the free run of every tool its role forbids. `role_stack_scope`
    is opened HERE, on the coroutine `run_async` actually executes (the
    Phase 103 rule again: a scope opened around the thread hop is a silent
    no-op), and reopens the EXACT stack `_pause_and_return` captured --
    `()` for a task that was never delegated, so nothing changes for the
    common case.
    """
    from ..agents.role_context import role_stack_scope

    env: _RunEnv = snapshot.env
    result = env.executor.execute_approved(snapshot.call.tool, snapshot.call.args, executed_result)
    forced = (snapshot.call, snapshot.step, result, snapshot.continue_after_tools)
    with role_stack_scope(snapshot.role_stack):
        return await _drive_loop(env, start_index=snapshot.index, forced=forced)


async def _run_agentic_task(user_message: str, context: dict[str, Any]) -> dict[str, Any]:
    raw_settings = context.get("settings")
    settings = getattr(raw_settings, "models", raw_settings) or ModelSettings()
    registry: ToolRegistry = context.get("registry") or ToolRegistry()
    executor: ToolExecutor = context.get("executor") or ToolExecutor(registry)
    memory = context.get("memory")
    session_id = context.get("session_id")
    session_context = context.get("session_context")
    history = context.get("history") or []
    execute_tools = bool(context.get("execute_tools", True))

    goal = agentic_goal(user_message)
    with task_trace(str(session_id or "").strip() or "agent-task", goal) as _trace_id:
        task = AgentTask(
            user_goal=goal,
            max_steps=max_agent_steps(),
            max_tool_calls=max_tools_per_task(),
            max_web_searches=max_web_searches_per_task(),
            max_screen_captures=max_screen_captures_per_task(),
        )
        task.plan = build_initial_plan(goal)
        # Phase 119: the adaptive step budget's fixed points for this task,
        # set once here and never touched again (a Phase 117 resume reuses
        # this same `task` object by reference via `PausedTask.env`, so
        # nothing needs to be re-derived or re-snapshotted on resume).
        task.base_max_steps = task.max_steps
        task.step_ceiling = max_agent_steps_ceiling()
        state = AgentRunState()
        # Injectable planner is the testability seam that lets the reliability of
        # the plan->act->observe->reflect loop be driven deterministically (P39).
        planner = context.get("planner") or ToolCallPlanner(settings, registry)
        max_failures = max_consecutive_failures()
        max_no_progress = max_steps_without_progress()
        # Phase 40c least-privilege: an optional per-task allowlist. Unset =
        # unrestricted (backward compatible); a caller passes context["tool_scope"]
        # (list/set of tool names or "prefix*" wildcards) to lock the task down.
        tool_scope = TaskToolScope.of(context.get("tool_scope"))
        # Phase 41: an optional delegation contract (goal + success criteria +
        # require_verified + max_revisions). The critic gates completion against
        # it. None = advisory critic (backward compatible single-shot behavior).
        contract = DelegationContract.of(context.get("contract"))
        # Phase 44 perception & grounding: an opt-in, metadata-only situational
        # snapshot (foreground app + open apps from window metadata — never
        # pixels) captured once at dispatch so every planning step is grounded in
        # live state. "" when perception is off or nothing is observable, so the
        # planner prompt stays byte-identical. A caller may inject
        # context["situation"] (a Situation or a ready string) to drive it
        # deterministically.
        grounding = _resolve_grounding(context.get("situation"))
        # Phase 110: the app this task opened or focused and VERIFIED -- the only
        # window a type grant may type into -- and how many grants were spent.
        # Phase 117: moved into a dict (`loop_vars`) rather than two locals so a
        # resumed run can restore them onto a fresh `_RunEnv`.
        loop_vars: dict[str, Any] = {"typing_target": None, "types_used": 0}
        events: list[dict[str, Any]] = [
            {"type": "agent_task", "task_id": task.id, "message": "Agent task started"},
            {"type": "agent_plan", "task_id": task.id, "plan": list(task.plan), "message": "Plan ready"},
        ]
        if grounding:
            events.append({"type": "grounding", "task_id": task.id, "message": grounding})
        safety_stops: list[str] = []

        _safe_log(memory, session_id, "agent_task_started", {"task_id": task.id, "goal": goal, "plan": list(task.plan)})

        if is_unsupported_capability(goal):
            task.status = "failed"
            task.final_response = "I cannot complete that safely yet because the needed module is not available."
            safety_stops.append("unsupported_capability")
            _safe_log(memory, session_id, "agent_task_failed", {"task_id": task.id, "reason": "unsupported_capability"})
            return _return_task(task, session_context, ok=False, events=events, safety_stops=safety_stops)

        env = _RunEnv(
            task=task,
            state=state,
            goal=goal,
            context=context,
            registry=registry,
            executor=executor,
            memory=memory,
            session_id=session_id,
            session_context=session_context,
            history=history,
            planner=planner,
            max_failures=max_failures,
            max_no_progress=max_no_progress,
            tool_scope=tool_scope,
            contract=contract,
            grounding=grounding,
            events=events,
            safety_stops=safety_stops,
            loop_vars=loop_vars,
            execute_tools=execute_tools,
        )
        return await _drive_loop(env, start_index=1)


def _web_summary_goal_without_open(goal: str) -> bool:
    text = " ".join(goal.lower().split())
    wants_web_summary = any(marker in text for marker in ("find", "summarize", "research", "compare", "search", "best"))
    explicitly_opens = any(marker in text for marker in ("open result", "open the", "open first", "open chrome", "open browser", "open url"))
    return wants_web_summary and not explicitly_opens
