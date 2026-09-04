"""Tests for optional native function-calling (tool-calling) plumbing.

Covers:
  * backend.eva.llm.tool_schema.to_openai_tools -- pure spec converter.
  * backend.eva.llm.providers._openai_compatible.OpenAICompatibleProvider.complete
    parsing tool_calls out of the response when `tools` is passed.
  * Backward compatibility: calling complete() with no `tools` arg is
    byte-identical to today (no "tools"/"tool_choice" keys in the payload,
    tool_calls is None on the response).
"""

from __future__ import annotations

import asyncio

import pytest

from backend.eva.core.config import ModelSettings
from backend.eva.llm.providers.groq import GroqProvider
from backend.eva.llm.tool_schema import to_openai_tools


def test_to_openai_tools_converts_specs():
    specs = [
        {
            "name": "web.open_url",
            "description": "Open a URL in the browser.",
            "args_schema": {"type": "object", "properties": {"url": {"type": "string"}}},
        },
        {
            # No name -- must be skipped.
            "description": "Should be skipped.",
            "args_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "no.schema",
            "description": "Has no args_schema.",
        },
    ]

    tools = to_openai_tools(specs)

    assert len(tools) == 2

    first = tools[0]
    assert first["type"] == "function"
    # Phase 95: the wire name is sanitized. This line used to assert
    # "web.open_url", i.e. it pinned the exact defect -- one dotted name in the
    # payload makes NVIDIA NIM reject the WHOLE request with HTTP 400, so the
    # planner could never use NIM. The tool's real name is unchanged; only what
    # goes on the wire is, and the planner resolves it back on the way in.
    assert first["function"]["name"] == "web_open_url"
    assert first["function"]["description"] == "Open a URL in the browser."
    assert first["function"]["parameters"] == {
        "type": "object",
        "properties": {"url": {"type": "string"}},
    }

    second = tools[1]
    assert second["function"]["name"] == "no_schema"
    assert second["function"]["description"] == "Has no args_schema."
    assert second["function"]["parameters"] == {"type": "object", "properties": {}}


class _FakeResponse:
    def __init__(self, payload: dict):
        self.status_code = 200
        self.headers: dict[str, str] = {}
        self._payload = payload

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Fake replacement for httpx.AsyncClient used to intercept .post(...)."""

    captured_payloads: list[dict] = []
    response_payload: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        type(self).captured_payloads.append(json)
        return _FakeResponse(type(self).response_payload)


@pytest.fixture
def groq_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    return GroqProvider(ModelSettings())


@pytest.fixture(autouse=True)
def _reset_fake_client():
    _FakeAsyncClient.captured_payloads = []
    _FakeAsyncClient.response_payload = {}
    yield
    _FakeAsyncClient.captured_payloads = []
    _FakeAsyncClient.response_payload = {}


def test_complete_with_tools_parses_tool_calls(monkeypatch, groq_provider):
    from backend.eva.llm.providers import _openai_compatible

    monkeypatch.setattr(_openai_compatible.httpx, "AsyncClient", _FakeAsyncClient)

    tool_call = {
        "id": "c1",
        "type": "function",
        "function": {"name": "web.open_url", "arguments": '{"url": "https://x.com"}'},
    }
    _FakeAsyncClient.response_payload = {
        "choices": [{"message": {"content": "", "tool_calls": [tool_call]}}]
    }

    tools = [
        {
            "type": "function",
            "function": {
                "name": "web.open_url",
                "description": "Open a URL",
                "parameters": {"type": "object", "properties": {"url": {"type": "string"}}},
            },
        }
    ]

    response = asyncio.run(
        groq_provider.complete([{"role": "user", "content": "open x.com"}], tools=tools)
    )

    assert response.ok is True
    assert response.text == ""
    assert response.tool_calls == [tool_call]

    assert len(_FakeAsyncClient.captured_payloads) == 1
    payload = _FakeAsyncClient.captured_payloads[0]
    assert payload["tools"] == tools
    assert payload["tool_choice"] == "auto"


def test_complete_without_tools_is_backward_compatible(monkeypatch, groq_provider):
    from backend.eva.llm.providers import _openai_compatible

    monkeypatch.setattr(_openai_compatible.httpx, "AsyncClient", _FakeAsyncClient)

    _FakeAsyncClient.response_payload = {
        "choices": [{"message": {"content": "hello there"}}]
    }

    response = asyncio.run(groq_provider.complete([{"role": "user", "content": "hi"}]))

    assert response.ok is True
    assert response.text == "hello there"
    assert response.tool_calls is None

    assert len(_FakeAsyncClient.captured_payloads) == 1
    payload = _FakeAsyncClient.captured_payloads[0]
    assert "tools" not in payload
    assert "tool_choice" not in payload
