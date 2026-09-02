"""Phase 89: the native function-calling planner must SEE its own tool results.

`_native_plan` accepted a `task_context` carrying `steps`/`observations` and
never read it, so every iteration of the agent loop rebuilt the same
`[system, goal]` message pair. The model re-issued the tool it had already run
because nothing in the prompt said it had -- the observation was stored on
`task.steps[i].observation` and never arrived at the model.

These tests assert arrival at the outbound message list. Storage is not enough:
that is the distinction this project keeps re-learning.
"""

from __future__ import annotations

import asyncio

from backend.eva.agent import planner as planner_module
from backend.eva.agent.planner import ToolCallPlanner, _clean_args, _spec_schema
from backend.eva.core.config import ModelSettings
from backend.eva.tools.registry import ToolRegistry


OBSERVATION = "window_active observed Calculator. (self-reported)"

CONTEXT_WITH_PROGRESS = {
    "goal": "what app is in the foreground?",
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


class _Response:
    def __init__(self, *, ok=True, text="", tool_calls=None):
        self.ok = ok
        self.text = text
        self.tool_calls = tool_calls


class _Routed:
    def __init__(self, response):
        self.response = response
        self.attempts = []


def _capture(monkeypatch, *, tool_calls=None, text="Calculator."):
    """Drive _native_plan and return (decision, outbound_messages)."""
    seen: list[list[dict]] = []

    async def spy(messages, settings, **kwargs):
        seen.append([dict(m) for m in messages])
        return _Routed(_Response(ok=True, text=text, tool_calls=tool_calls))

    monkeypatch.setattr(planner_module, "complete_with_fallback", spy)
    monkeypatch.setenv("EVA_NATIVE_FUNCTION_CALLING", "1")
    planner = ToolCallPlanner(ModelSettings(), ToolRegistry())

    def run(task_context, mode="agent_step"):
        seen.clear()
        decision = asyncio.run(
            planner._native_plan("what app is in the foreground?", [], mode=mode, task_context=task_context)
        )
        return decision, seen[-1]

    return run


def _blob(messages) -> str:
    return "\n".join(str(m.get("content") or "") for m in messages)


def test_prior_observation_reaches_the_outbound_messages(monkeypatch):
    run = _capture(monkeypatch)
    _, messages = run(CONTEXT_WITH_PROGRESS)
    assert OBSERVATION in _blob(messages)
    assert "window_active" in _blob(messages)


def test_first_step_prompt_is_unchanged(monkeypatch):
    """No progress yet must build exactly the pre-Phase-89 two-message prompt."""
    run = _capture(monkeypatch)
    _, messages = run({"goal": "g", "steps": [], "observations": []})
    assert [m["role"] for m in messages] == ["system", "user"]


def test_single_turn_prompt_is_unchanged(monkeypatch):
    run = _capture(monkeypatch)
    _, messages = run(CONTEXT_WITH_PROGRESS, mode="single_turn")
    assert [m["role"] for m in messages] == ["system", "user"]
    assert OBSERVATION not in _blob(messages)


def test_step_without_an_observation_is_not_reported_as_a_result(monkeypatch):
    run = _capture(monkeypatch)
    _, messages = run({"steps": [{"tool_name": "window_active", "tool_args": {}, "observation": ""}]})
    assert [m["role"] for m in messages] == ["system", "user"]


def test_progress_messages_stay_portable_across_providers(monkeypatch):
    """No role='tool', no tool_calls key, no empty content.

    gemini._gemini_contents converts messages by text only and SKIPS any message
    whose content is empty, so a protocol-shaped tool message would silently
    vanish on the fallback provider -- reintroducing the very bug this fixes.
    """
    run = _capture(monkeypatch)
    _, messages = run(CONTEXT_WITH_PROGRESS)
    for item in messages:
        assert item.get("role") in {"system", "user", "assistant"}
        assert "tool_calls" not in item
        assert str(item.get("content") or "").strip()


def test_tool_output_stays_in_the_user_turn(monkeypatch):
    """Untrusted tool output must never be voiced as the assistant's own words."""
    run = _capture(monkeypatch)
    _, messages = run(CONTEXT_WITH_PROGRESS)
    recap, feedback = messages[-2], messages[-1]
    assert recap["role"] == "assistant"
    assert feedback["role"] == "user"
    assert OBSERVATION in str(feedback["content"])
    assert OBSERVATION not in str(recap["content"])


def test_agent_step_mode_is_told_not_to_repeat_a_finished_call(monkeypatch):
    run = _capture(monkeypatch)
    _, messages = run(CONTEXT_WITH_PROGRESS)
    lowered = _blob(messages).lower()
    assert "do not repeat" in lowered
    assert "plain text" in lowered


def test_invented_argument_for_a_no_argument_tool_is_dropped(monkeypatch):
    """The live failure: window_active(include_windows=False) -> "Unknown arguments"."""
    call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "window_active", "arguments": '{"include_windows": false}'},
    }
    run = _capture(monkeypatch, tool_calls=[call])
    decision, _ = run(CONTEXT_WITH_PROGRESS)
    assert decision is not None
    assert decision.type == "tool_calls"
    assert decision.tool_calls[0].args == {}


def test_real_arguments_survive_cleaning(monkeypatch):
    call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "web_search", "arguments": '{"query": "cats"}'},
    }
    run = _capture(monkeypatch, tool_calls=[call])
    decision, _ = run(CONTEXT_WITH_PROGRESS)
    assert decision.tool_calls[0].args == {"query": "cats"}


def test_clean_args_only_strips_what_a_closed_schema_cannot_accept():
    closed = {"properties": {}, "additionalProperties": False}
    assert _clean_args(closed, {"include_windows": False}) == {}
    assert _clean_args(closed, {"": {}}) == {}

    query = {"properties": {"query": {"type": "string"}}, "additionalProperties": False}
    assert _clean_args(query, {"query": "cats", "junk": 1}) == {"query": "cats"}
    assert _clean_args(query, {"query": "cats"}) == {"query": "cats"}

    # An OPEN schema means extra keys are legitimate; cleaning must not touch them.
    opened = {"properties": {"query": {"type": "string"}}}
    assert _clean_args(opened, {"query": "cats", "extra": 1}) == {"query": "cats", "extra": 1}

    assert _clean_args({}, "not-a-dict") == {}


def test_window_active_schema_is_still_closed():
    """The fix assumes this schema is closed; pin it so a later change is visible."""
    spec = ToolRegistry().get("window_active")
    assert spec is not None
    assert _spec_schema(spec).get("additionalProperties") is False


def test_executor_validation_remains_the_guard_for_direct_calls():
    """Cleaning happens at plan time; /api/tools calls never pass through the
    planner, so the executor's own check must stay in place."""
    from backend.eva.agent.executor import ToolExecutor

    closed = {"properties": {}, "additionalProperties": False}
    assert ToolExecutor._validate_args(None, closed, {"include_windows": False}) is not None
