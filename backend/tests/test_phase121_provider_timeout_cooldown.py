"""Phase 121: a model that times out is skipped for a while, not re-waited on.

Live through the chat UI, "what time is it" took 49s: 35s of it was the primary
NIM model (nemotron-3.5-lightning) running out its timeout before the router fell
back to Gemini, and nothing remembered that, so every request paid it again.
"""
from __future__ import annotations

import asyncio

import backend.eva.llm.router as router
from backend.eva.llm.rate_limiter import LLMRateLimiter
from backend.eva.llm.types import LLMResponse, Message


class _FakeProvider:
    name = "nvidia_nim"
    model = "fake/slow-model"
    request_timeout = 12

    def __init__(self, response: LLMResponse) -> None:
        self._response = response
        self.calls = 0

    async def complete(self, messages, temperature, max_tokens, tools=None):
        self.calls += 1
        return self._response


def _run(provider, limiter):
    return asyncio.run(
        router._call_provider(provider, limiter, [Message(role="user", content="hi")], purpose="chat", temperature=0.2, max_tokens=50)
    )


def test_a_timed_out_model_is_blocked_for_the_cooldown(tmp_path):
    limiter = LLMRateLimiter(path=tmp_path / "usage.json")
    timeout = LLMResponse(provider="nvidia_nim", model="fake/slow-model", ok=False, error="ReadTimeout: no response within 12s")
    _run(_FakeProvider(timeout), limiter)
    allowed, reason = limiter.can_call("nvidia_nim", "fake/slow-model")
    assert allowed is False and reason.startswith("blocked_until:")


def test_an_ordinary_failure_does_not_block_the_model(tmp_path):
    limiter = LLMRateLimiter(path=tmp_path / "usage.json")
    bad = LLMResponse(provider="nvidia_nim", model="fake/slow-model", ok=False, error="invalid_request", status_code=400)
    _run(_FakeProvider(bad), limiter)
    allowed, _ = limiter.can_call("nvidia_nim", "fake/slow-model")
    assert allowed is True


def test_the_default_nim_model_is_the_one_measured_to_answer():
    from backend.eva.llm.providers import nvidia_nim

    assert nvidia_nim.DEFAULT_NIM_MODEL == "nvidia/nemotron-3-super-120b-a12b"
    assert "lightning" in nvidia_nim.DEFAULT_NIM_FALLBACKS


# --- "open ... result" no longer swallows errands -------------------------

def test_open_result_matches_whole_words_only():
    from backend.eva.core.web_context import wants_previous_result

    assert wants_previous_result("open the second one")
    assert wants_previous_result("open that result")
    assert wants_previous_result("open my github")
    # "one" inside "done"/"phone", and an errand that mentions a result.
    assert not wants_previous_result("open the phone app")
    assert not wants_previous_result("open calculator and tell me the result of 9 times 9")
    assert not wants_previous_result("open calculator then tell me when you are done")


def test_an_unreachable_nim_endpoint_is_not_retried_with_the_next_model(monkeypatch, tmp_path):
    from backend.eva.core.config import ModelSettings

    calls: list[str] = []

    async def fake_call(provider, limiter, messages, **kwargs):
        calls.append(provider.model)
        return LLMResponse(provider="nvidia_nim", model=provider.model, ok=False, error="ConnectTimeout: no response within 12s"), True

    monkeypatch.setattr(router, "_call_provider", fake_call)
    monkeypatch.setattr(router, "nvidia_nim_models_for_purpose", lambda purpose: ["m/one", "m/two"])
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-key")
    limiter = LLMRateLimiter(path=tmp_path / "usage.json")
    out = asyncio.run(
        router._try_nvidia_nim_models(
            ModelSettings(), limiter, [], [Message(role="user", content="hi")],
            purpose="chat", temperature=0.2, max_tokens=50, estimated_tokens=10,
        )
    )
    assert out is None and calls == ["m/one"]
