"""The planner's JSON-schema constraint, the provider's safety net, and the one-retry on bad JSON."""

import asyncio
import json

import pytest

from backend.eva.agent import planner as planner_module
from backend.eva.agent import planner_schema as ps
from backend.eva.agent.tool_menu import select_specs
from backend.eva.tools.registry import ToolRegistry

jsonschema = pytest.importorskip("jsonschema")
SPECS = ToolRegistry().planner_specs()
MENU = select_specs("play a song on spotify", SPECS)


def _schema(mode="agent_step", specs=MENU):
    return ps.decision_schema(specs, mode=mode)


def test_a_well_formed_decision_validates():
    decision = {"reason": "play it", "type": "tool_calls", "tool_calls": [{"tool": "spotify_play_desktop", "args": {"query": "x"}}], "continue_after_tools": True}
    jsonschema.validate(decision, _schema())
    jsonschema.validate({"reason": "r", "type": "done", "final_response": "ok"}, _schema())


def test_unknown_tool_invented_args_and_bad_types_are_rejected():
    schema = _schema()
    for bad in (
        {"reason": "r", "type": "tool_calls", "tool_calls": [{"tool": "format_disk", "args": {}}]},
        {"reason": "r", "type": "tool_calls", "tool_calls": [{"tool": "spotify_play_desktop", "args": {"query": "x", "volume": 5}}]},
        {"reason": "r", "type": "teleport"},
        {"type": "answer", "final_response": "hi"},
        {"reason": "r", "type": "tool_calls", "tool_calls": [{"tool": "open_app", "args": {"app": "a"}}] * 3},
    ):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)


def test_reason_comes_first_and_single_turn_has_no_done():
    schema = _schema(mode="single_turn")
    assert list(schema["properties"])[0] == "reason" and "done" not in schema["properties"]["type"]["enum"]
    assert "done" in _schema(mode="agent_step")["properties"]["type"]["enum"]


def test_a_huge_menu_keeps_the_shape_but_not_the_tool_union():
    items = _schema(specs=SPECS)["properties"]["tool_calls"]["items"]
    assert "anyOf" not in items and items["properties"]["tool"] == {"type": "string"}


def test_switch(monkeypatch):
    monkeypatch.setenv("EVA_PLANNER_SCHEMA", "off")
    assert not ps.schema_enabled()
    monkeypatch.setenv("EVA_PLANNER_SCHEMA", "on")
    assert ps.schema_enabled()
    monkeypatch.setenv("EVA_PLANNER_SCHEMA", "auto")
    monkeypatch.setenv("EVA_LLM_MODE", "clod")
    monkeypatch.setenv("CLOD_BASE_URL", "http://127.0.0.1:8080/v1")
    assert ps.schema_enabled()
    monkeypatch.setenv("CLOD_BASE_URL", "https://api.example.com/v1")
    assert not ps.schema_enabled()


# --- provider -------------------------------------------------------------------------------

class _Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body, self.headers = status, body or {}, {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


def _provider(monkeypatch, responses):
    from backend.eva.llm.providers import _openai_compatible as oc

    sent = []

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None):
            sent.append(dict(json))
            return responses.pop(0)

    monkeypatch.setattr(oc.httpx, "AsyncClient", Client)

    class P(oc.OpenAICompatibleProvider):
        name, api_key_env, model_env, base_url_env = "t", "T_KEY", "T_MODEL", "T_URL"
        default_model, default_base_url = "m", "http://127.0.0.1:1/v1"
        supports_response_format = True

    monkeypatch.setenv("T_KEY", "k")
    provider = P(None)
    provider.response_format = {"type": "json_schema"}
    return provider, sent


GOOD = {"choices": [{"message": {"content": "{}"}}]}


def test_provider_sends_the_schema_and_retries_without_it_on_a_400(monkeypatch):
    provider, sent = _provider(monkeypatch, [_Resp(400, {"error": {"message": "grammar too big"}}), _Resp(200, GOOD)])
    result = asyncio.run(provider.complete([{"role": "user", "content": "hi"}]))
    assert result.ok and len(sent) == 2 and "response_format" in sent[0] and "response_format" not in sent[1]


def test_provider_does_not_send_a_schema_it_does_not_support(monkeypatch):
    provider, sent = _provider(monkeypatch, [_Resp(200, GOOD)])
    provider.supports_response_format = False
    asyncio.run(provider.complete([{"role": "user", "content": "hi"}]))
    assert "response_format" not in sent[0]


# --- planner retry --------------------------------------------------------------------------

class _Routed:
    def __init__(self, text):
        from backend.eva.llm.types import LLMResponse

        self.response, self.attempts, self.fallback_occurred = LLMResponse(provider="p", model="m", text=text, ok=True), [], False


def test_a_bad_reply_gets_one_retry_that_shows_the_error(monkeypatch):
    calls = []

    async def fake(messages, settings, **kw):
        calls.append(messages)
        return _Routed("not json at all" if len(calls) == 1 else json.dumps({"reason": "r", "type": "answer", "final_response": "hello"}))

    monkeypatch.setattr(planner_module, "complete_with_fallback", fake)
    planner = planner_module.ToolCallPlanner(None, ToolRegistry())
    decision = asyncio.run(planner.plan("hi", [], mode="single_turn"))
    assert decision.type == "answer" and decision.final_response == "hello"
    assert len(calls) == 2 and "rejected" in calls[1][-1]["content"] and calls[1][-2]["content"] == "not json at all"


def test_a_local_clod_endpoint_is_not_rate_limited_like_a_cloud_free_tier(monkeypatch):
    from backend.eva.llm.rate_limiter import provider_limits

    monkeypatch.setenv("CLOD_BASE_URL", "http://127.0.0.1:8080/v1")
    assert provider_limits("clod", "qwen3-vl-4b") == (None, None)
    monkeypatch.setenv("CLOD_BASE_URL", "https://api.clod.io/v1")
    assert provider_limits("clod", "x") == (10, 100)


def test_a_confirmation_request_that_names_nothing_is_rejected_in_agent_mode_only():
    planner = planner_module.ToolCallPlanner(None, ToolRegistry())
    empty = {"type": "confirmation_required", "reason": "Calculator app opened and 'Seven' button clicked successfully.", "tool_calls": []}
    with pytest.raises(planner_module.PlannerError, match="must name the `action`"):
        planner._validate(dict(empty), mode="agent_step")
    named = planner._validate({**empty, "action": "shutdown", "final_response": "Shut down the PC?"}, mode="agent_step")
    assert named.requires_confirmation and named.action == "shutdown"
    assert planner._validate(dict(empty), mode="single_turn").requires_confirmation  # old behaviour kept
