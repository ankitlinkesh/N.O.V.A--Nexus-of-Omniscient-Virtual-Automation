"""Tests for the optional native-function-calling planner path.

The flag EVA_NATIVE_FUNCTION_CALLING is default-off. When off, plan() must
behave exactly as before (JSON-prompt / local-fallback path). When on,
plan() asks the LLM with tool schemas and consumes structured tool_calls,
falling back to the existing path on any failure.

The planner's plan() (and _native_plan()) are async; this repo has no
pytest-asyncio, so we drive coroutines with asyncio.run(...) inside sync
test functions (see backend/tests/test_llm_function_calling.py).
"""

from __future__ import annotations

import asyncio

from backend.eva.agent import planner as planner_module
from backend.eva.agent.planner import PlannerDecision, ToolCallPlanner, _native_function_calling_enabled
from backend.eva.core.config import ModelSettings
from backend.eva.tools.registry import ToolRegistry


class _FakeLLMResponse:
    def __init__(self, *, ok: bool = True, text: str = "", tool_calls=None):
        self.ok = ok
        self.text = text
        self.tool_calls = tool_calls


class _FakeRouted:
    def __init__(self, response: _FakeLLMResponse):
        self.response = response
        self.attempts = []


def _make_planner() -> ToolCallPlanner:
    return ToolCallPlanner(ModelSettings(), ToolRegistry())


def test_flag_defaults_to_off(monkeypatch):
    monkeypatch.delenv("EVA_NATIVE_FUNCTION_CALLING", raising=False)
    assert _native_function_calling_enabled() is False


def test_flag_off_does_not_take_native_path(monkeypatch):
    monkeypatch.delenv("EVA_NATIVE_FUNCTION_CALLING", raising=False)

    async def fake_complete_with_fallback(*args, **kwargs):
        # If this were consumed as a native tool_call response it would
        # produce a "web_search" tool_calls decision; with the flag off,
        # the JSON-prompt path treats routed.response.text as the JSON body,
        # so make it a valid JSON "answer" to keep this test simple/robust.
        return _FakeRouted(
            _FakeLLMResponse(
                ok=True,
                text='{"type": "answer", "reason": "r", "tool_calls": [], "final_response": "hi there"}',
                tool_calls=None,
            )
        )

    monkeypatch.setattr(planner_module, "complete_with_fallback", fake_complete_with_fallback)

    planner = _make_planner()
    decision = asyncio.run(planner.plan("look up cats"))

    assert isinstance(decision, PlannerDecision)
    assert decision.type == "answer"
    assert decision.final_response == "hi there"


def test_flag_on_valid_tool_call_produces_tool_calls_decision(monkeypatch):
    monkeypatch.setenv("EVA_NATIVE_FUNCTION_CALLING", "1")

    async def fake_complete_with_fallback(*args, **kwargs):
        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "web_search", "arguments": '{"query":"cats"}'},
        }
        return _FakeRouted(_FakeLLMResponse(ok=True, text="", tool_calls=[tool_call]))

    monkeypatch.setattr(planner_module, "complete_with_fallback", fake_complete_with_fallback)

    planner = _make_planner()
    decision = asyncio.run(planner.plan("look up cats"))

    assert decision.type == "tool_calls"
    assert len(decision.tool_calls) == 1
    assert decision.tool_calls[0].tool == "web_search"
    assert decision.tool_calls[0].args == {"query": "cats"}


def test_flag_on_invalid_tool_name_falls_back_to_none(monkeypatch):
    monkeypatch.setenv("EVA_NATIVE_FUNCTION_CALLING", "1")

    async def fake_complete_with_fallback(*args, **kwargs):
        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "totally_made_up_tool", "arguments": "{}"},
        }
        return _FakeRouted(_FakeLLMResponse(ok=True, text="", tool_calls=[tool_call]))

    monkeypatch.setattr(planner_module, "complete_with_fallback", fake_complete_with_fallback)

    planner = _make_planner()
    result = asyncio.run(
        planner._native_plan("look up cats", [], mode="single_turn", task_context={})
    )

    assert result is None


def test_flag_on_text_only_produces_answer_decision(monkeypatch):
    monkeypatch.setenv("EVA_NATIVE_FUNCTION_CALLING", "1")

    async def fake_complete_with_fallback(*args, **kwargs):
        return _FakeRouted(_FakeLLMResponse(ok=True, text="Cats are great.", tool_calls=None))

    monkeypatch.setattr(planner_module, "complete_with_fallback", fake_complete_with_fallback)

    planner = _make_planner()
    result = asyncio.run(
        planner._native_plan("look up cats", [], mode="single_turn", task_context={})
    )

    assert result is not None
    assert result.type == "answer"
    assert result.final_response == "Cats are great."
