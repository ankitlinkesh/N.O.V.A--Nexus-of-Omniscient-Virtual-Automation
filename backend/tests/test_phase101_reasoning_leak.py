"""Phase 101: NOVA answered with its own chain of thought instead of the time.

Seen in live use, one message after the server came back up on the model Phase 95
made primary::

    "what time is it"
    -> "Here's a thinking process:  1.  **Analyze User Input:**
        - User says: "what time is it" ..."

nemotron-3.5-lightning is a reasoning model. Asked to write ONE sentence from
tool results it spends its budget thinking. The same call shape sometimes
returns EMPTY content instead, which reads as a provider failure and falls
through to gemini -- two faces of one cause, one of them user-visible garbage.

`chat_template_kwargs={"thinking": False}` removes it: measured, reasoning drops
from 612 characters to 0 while content stays "It's 9:14 AM on Friday."

The load-bearing detail is the gate on `tools`. Measured on the identical
request: with thinking ON the model calls `system_time`; with it OFF it emits no
tool call and answers "The current time is 12:34 PM" -- **a time it invented**. A
planner that fabricates rather than reading the clock is far worse than a chatty
one, so the planner keeps its reasoning and only the tool-free synthesis calls
lose it.

This also corrects a claim made in Phase 92, which probed whether nemotron leaks
reasoning into `content` and concluded it does not. That held for a short prompt
and not for this one.
"""

from __future__ import annotations

from backend.eva.core.config import ModelSettings
from backend.eva.llm.providers._openai_compatible import OpenAICompatibleProvider
from backend.eva.llm.providers.nvidia_nim import NvidiaNIMProvider


TOOLS = [{"type": "function", "function": {"name": "system_time", "parameters": {}}}]


def _nim() -> NvidiaNIMProvider:
    return NvidiaNIMProvider(ModelSettings())


def test_thinking_is_disabled_when_there_are_no_tools():
    """A tool-free call is only writing a sentence; reasoning there is noise."""
    assert _nim().extra_payload(None) == {"chat_template_kwargs": {"thinking": False}}


def test_thinking_is_kept_whenever_tools_are_sent():
    """THE LOAD-BEARING HALF.

    With thinking off the model stopped calling `system_time` and answered "The
    current time is 12:34 PM" -- a time it made up. Fabricating beats chattiness
    only in the wrong direction, so a request carrying tools keeps its reasoning.
    """
    assert _nim().extra_payload(TOOLS) == {}


def test_a_generic_openai_backend_sends_nothing_extra():
    """The field is NVIDIA-specific and must not leak into other providers."""
    generic = OpenAICompatibleProvider(ModelSettings())
    assert generic.extra_payload(None) == {}
    assert generic.extra_payload(TOOLS) == {}


def test_the_extra_payload_reaches_the_request_body(monkeypatch):
    """Arrival: defining the hook is worthless if `complete` never calls it."""
    import asyncio

    captured: dict = {}

    class _Response:
        status_code = 200
        headers: dict = {}

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            captured.update(json or {})
            return _Response()

    monkeypatch.setattr("backend.eva.llm.providers._openai_compatible.httpx.AsyncClient", _Client)
    provider = _nim()
    monkeypatch.setattr(provider, "api_key", "test-key")

    asyncio.run(provider.complete([{"role": "user", "content": "hi"}], tools=None))
    assert captured.get("chat_template_kwargs") == {"thinking": False}, (
        "the hook must actually reach the request body, not merely exist"
    )

    captured.clear()
    asyncio.run(provider.complete([{"role": "user", "content": "hi"}], tools=TOOLS))
    assert "chat_template_kwargs" not in captured, "a request carrying tools must keep reasoning"
    assert captured.get("tools") == TOOLS
