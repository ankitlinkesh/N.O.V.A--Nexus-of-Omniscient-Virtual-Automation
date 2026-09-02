"""Standalone verifier for Phase 89 (the native planner sees its own tool results).

Live-driving the agent loop with EVA_NATIVE_FUNCTION_CALLING=1 found that a
single-tool goal ("what app is in the foreground right now?") could not
complete: the model planned `window_active` four times and the task died on
`failure_budget_exceeded`. Dumping the messages actually handed to the provider
showed iteration 2's list byte-identical to iteration 1's -- `[system, user]`,
with no record of the call just made or what it returned.

`_native_plan` accepted a `task_context` (which carries `steps` and
`observations`) and never read it. The observation was *stored* on
`task.steps[i].observation` and never *arrived* at the model, so the model
re-issued the same tool because it had no way to know it had already run.
This is the project's recurring defect: a green suite proves storage, never
arrival -- so this verifier asserts arrival at the outbound MESSAGE LIST, not
that a field was read.

Two provider-shape invariants are pinned with it, because getting them wrong
would silently reintroduce the bug on the fallback provider:
  * no message may carry `role: "tool"` or a `tool_calls` key, and none may have
    empty content -- `llm/providers/gemini.py::_gemini_contents` converts by
    text only and SKIPS empty-content messages, so protocol-shaped tool messages
    would vanish there;
  * tool OUTPUT stays in a `user` turn (it may carry untrusted content the
    runner wrapped) while the recap of actions is the assistant's own turn.

Also covers the argument cleaning that shared the failure: models invent
arguments for no-argument tools (`window_active(include_windows=False)` was seen
live) and some providers emit a malformed empty key, both of which made
`executor._validate_args` reject the whole step with "Unknown arguments: ...".

Fully offline: `complete_with_fallback` is replaced with a spy, so no network
call is made and no provider quota is spent.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


class _Response:
    def __init__(self, *, ok=True, text="", tool_calls=None):
        self.ok = ok
        self.text = text
        self.tool_calls = tool_calls


class _Routed:
    def __init__(self, response):
        self.response = response
        self.attempts = []


OBSERVATION = "window_active observed Calculator. (self-reported)"

TASK_CONTEXT = {
    "goal": "what app is in the foreground right now?",
    "steps": [
        {
            "index": 1,
            "tool_name": "window_active",
            "tool_args": {},
            "observation": OBSERVATION,
            "status": "done",
        }
    ],
    "observations": [OBSERVATION],
}


def main() -> int:
    import eva.agent.planner as planner_module
    from eva.agent.planner import ToolCallPlanner, _clean_args, _spec_schema
    from eva.core.config import ModelSettings
    from eva.tools.registry import ToolRegistry

    captured: list[list[dict]] = []

    async def spy(messages, settings, **kwargs):
        captured.append([dict(m) for m in messages])
        return _Routed(_Response(ok=True, text="Calculator is in the foreground."))

    planner_module.complete_with_fallback = spy
    registry = ToolRegistry()
    planner = ToolCallPlanner(ModelSettings(), registry)

    def run(task_context, *, mode="agent_step", message="what app is in the foreground right now?"):
        captured.clear()
        decision = asyncio.run(planner._native_plan(message, [], mode=mode, task_context=task_context))
        check(captured, "the planner never called the router")
        return decision, captured[-1]

    # ---------------------------------------------------------------- ARRIVAL
    _, messages = run(TASK_CONTEXT)
    blob = "\n".join(str(m.get("content") or "") for m in messages)
    check(OBSERVATION in blob, "REGRESSION: the tool observation never reached the outbound messages")
    check("window_active" in blob, "the tool already called is not named in the outbound messages")
    check(len(messages) > 2, "expected progress messages to be appended, got %d" % len(messages))

    # The steering that turns "I can see the result" into "so answer, don't re-call".
    lowered = blob.lower()
    check("do not repeat" in lowered, "no instruction against repeating an already-answered call")
    check("plain text" in lowered, "no instruction to answer in plain text once the goal is met")

    # ----------------------------------------------------- PROVIDER-SHAPE SAFETY
    for item in messages:
        check(
            item.get("role") in {"system", "user", "assistant"},
            "message role %r is not portable across providers" % item.get("role"),
        )
        check(
            "tool_calls" not in item,
            "a tool_calls message would be dropped by the Gemini provider (text-only conversion)",
        )
        check(
            str(item.get("content") or "").strip(),
            "an empty-content message would be SKIPPED by gemini._gemini_contents",
        )

    tail = messages[-2:]
    roles = [m["role"] for m in tail]
    check(roles == ["assistant", "user"], "progress messages must alternate assistant->user, got %r" % roles)
    check(
        OBSERVATION in str(tail[1]["content"]),
        "tool OUTPUT must sit in the user turn (it can carry untrusted content), not be voiced as the assistant",
    )
    check(
        OBSERVATION not in str(tail[0]["content"]),
        "the assistant recap must state the ACTION only, never replay untrusted tool output as its own words",
    )

    # ------------------------------------------------- NO PROGRESS => UNCHANGED
    _, first_step = run({"goal": "g", "steps": [], "observations": []})
    check(
        len(first_step) == 2 and [m["role"] for m in first_step] == ["system", "user"],
        "the first step of a task must build the pre-Phase-89 prompt, got %r" % [m["role"] for m in first_step],
    )
    # single_turn is the one-shot chat planner: no loop, so no progress -- even
    # when a caller hands it a context that has some.
    _, single = run(TASK_CONTEXT, mode="single_turn")
    check(len(single) == 2, "single_turn prompts must be unchanged")
    check(OBSERVATION not in str(single[-1]["content"]), "single_turn must not receive agent-loop progress")
    check(
        "bounded agent-step planner" not in str(single[0]["content"]),
        "single_turn must not receive the agent-step system prompt",
    )
    check(
        "bounded agent-step planner" in str(first_step[0]["content"]),
        "agent_step mode must receive the agent-step system prompt",
    )

    # A step that ran but produced no observation yet is not progress to report.
    _, pending = run({"steps": [{"tool_name": "window_active", "tool_args": {}, "observation": ""}]})
    check(len(pending) == 2, "a step with no observation must not be reported as a result")

    # -------------------------------------------------- MUTATION: does this bite?
    original = planner_module.ToolCallPlanner._native_progress_messages
    try:
        planner_module.ToolCallPlanner._native_progress_messages = lambda self, ctx: []
        _, mutated = run(TASK_CONTEXT)
        mutated_blob = "\n".join(str(m.get("content") or "") for m in mutated)
        check(
            OBSERVATION not in mutated_blob,
            "MUTATION ESCAPED: dropping the progress messages still left the observation in the prompt, "
            "so the arrival check above cannot fail and proves nothing",
        )
    finally:
        planner_module.ToolCallPlanner._native_progress_messages = original

    # ------------------------------------------------------------ ARGUMENT CLEANING
    closed = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    check(
        _clean_args(closed, {"include_windows": False}) == {},
        "an invented argument for a no-argument tool must be dropped, not passed on to fail validation",
    )
    check(_clean_args(closed, {"": {}}) == {}, "a malformed empty argument key must be dropped")
    query = {"type": "object", "properties": {"query": {"type": "string"}}, "additionalProperties": False}
    check(
        _clean_args(query, {"query": "cats", "junk": 1}) == {"query": "cats"},
        "cleaning must keep the real argument and drop only what the schema cannot accept",
    )
    check(
        _clean_args(query, {"query": "cats"}) == {"query": "cats"},
        "a well-formed call must be passed through unchanged",
    )
    opened = {"type": "object", "properties": {"query": {"type": "string"}}}
    check(
        _clean_args(opened, {"query": "cats", "extra": 1}) == {"query": "cats", "extra": 1},
        "an OPEN schema accepts extra keys -- cleaning must not silently strip them",
    )
    check(_clean_args({}, "not-a-dict") == {}, "non-dict args must degrade to {}")

    spec = registry.get("window_active")
    check(spec is not None, "window_active is not registered")
    check(
        _spec_schema(spec).get("additionalProperties") is False,
        "window_active's schema is no longer closed; the live failure this fixes assumed it was",
    )

    # The executor's own guard stays in place: /api/tools calls never pass
    # through the planner, so it remains the last-resort check rather than dead code.
    from eva.agent.executor import ToolExecutor

    check(
        hasattr(ToolExecutor, "_validate_args"),
        "executor._validate_args was removed; it is still the guard for direct /api/tools calls",
    )
    validate = ToolExecutor._validate_args
    check(
        validate(None, closed, {"include_windows": False}) is not None,
        "executor validation must still reject unknown args that reach it by another path",
    )

    # -------------------------------------------------------------- registration
    import verify_eva_all

    name = "verify_eva_phase89_native_planner_observation_arrival.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 89 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 89 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 89 verifier")

    print(
        "PASS: Phase 89 native-planner observation arrival. _native_plan took a task_context and never read it, so "
        "every agent-loop iteration rebuilt the same [system, goal] pair and the model re-issued the tool it had "
        "already run until the failure budget stopped the task. Progress now arrives IN THE MESSAGE LIST (asserted "
        "here, not merely stored), as plain assistant/user text -- never role='tool' or empty content, which "
        "gemini._gemini_contents would silently drop -- with tool output kept in the user turn because it may carry "
        "untrusted content. A mutation that drops the progress messages is proven to fail this check. Arguments a "
        "closed schema cannot accept are dropped at plan time instead of failing the step, while "
        "executor._validate_args stays as the guard for direct /api/tools calls."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
