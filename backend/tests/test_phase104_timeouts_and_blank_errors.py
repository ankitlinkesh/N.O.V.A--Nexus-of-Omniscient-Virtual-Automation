"""Phase 104 -- a model that could never answer, and a failure with no reason.

`deep_reasoning` was recorded as "times out" for several sessions. It did not
time out occasionally: every provider call used a hardcoded 12-second read
timeout, for every model and every purpose, and `deepseek-v4-pro` answers
correctly in a measured **164 seconds**. HTTP 200, content "ok". The model was
never the problem and was never usable -- impossible by a factor of fourteen.

Underneath it, the reason nobody could tell: `str(httpx.ReadTimeout(...))` is
the EMPTY STRING, and the handler passed it straight through. A timeout surfaced
as `ok=False, status_code=None, error=""` -- identical to a retired model, a
network blip or a missing key. `llm probe`, the tool Phase 92 built to make
provider rot visible, reported `nemotron-3.5-content-safety` as dead on exactly
that evidence while the same code path answered in 0.6 seconds.

So the checks here are about a failure being ABLE TO EXPLAIN ITSELF, and about
the timeout following the purpose rather than being one number for everything.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]
COMPAT_PY = ROOT / "backend" / "eva" / "llm" / "providers" / "_openai_compatible.py"
GEMINI_PY = ROOT / "backend" / "eva" / "llm" / "providers" / "gemini.py"
ROUTER_PY = ROOT / "backend" / "eva" / "llm" / "router.py"
DOCTOR_PY = ROOT / "backend" / "eva" / "llm" / "doctor.py"


# --------------------------------------------------------------------------
# A failure must say what happened
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ReadTimeout(""),
        httpx.ConnectTimeout(""),
        httpx.PoolTimeout(""),
        httpx.ConnectError(""),
        httpx.HTTPError(""),
    ],
)
def test_no_transport_failure_is_ever_reported_blank(exc: Exception) -> None:
    """The bug in one line: every one of these stringifies to "".

    A caller cannot distinguish "the model is gone" from "we gave up waiting"
    from "the network hiccuped" when all three arrive as the empty string.
    """
    from eva.llm.providers._openai_compatible import describe_transport_error

    described = describe_transport_error(exc, 12.0)
    assert described.strip(), "a transport failure was described with nothing at all"
    assert type(exc).__name__ in described


def test_a_timeout_says_how_long_it_waited() -> None:
    """"No response within 12s" is actionable -- it says the budget was the
    binding constraint. "" says nothing, and cost this project several sessions
    of treating a healthy model as broken."""
    from eva.llm.providers._openai_compatible import describe_transport_error

    described = describe_transport_error(httpx.ReadTimeout(""), 164.0)
    assert "164" in described
    assert "ReadTimeout" in described


def test_a_message_carrying_exception_keeps_its_message() -> None:
    from eva.llm.providers._openai_compatible import describe_transport_error

    described = describe_transport_error(httpx.ConnectError("name resolution failed"), 12.0)
    assert "name resolution failed" in described


# --------------------------------------------------------------------------
# The timeout follows the purpose
# --------------------------------------------------------------------------


@pytest.mark.parametrize("purpose", ["deep_reasoning", "debug", "DEEP_REASONING"])
def test_thinking_purposes_get_the_long_budget(purpose: str) -> None:
    from eva.llm.providers._openai_compatible import DEEP_REQUEST_TIMEOUT, timeout_for_purpose

    assert timeout_for_purpose(purpose) == DEEP_REQUEST_TIMEOUT


@pytest.mark.parametrize("purpose", ["chat", "planner", "code", "vision", "", None])
def test_interactive_purposes_keep_the_short_budget(purpose) -> None:
    """The default must NOT become the long one. An interactive request that
    hangs for four minutes because a provider is slow is a different bug, not a
    fix -- so the long budget is granted only to the purposes that exist to
    think."""
    from eva.llm.providers._openai_compatible import DEFAULT_REQUEST_TIMEOUT, timeout_for_purpose

    assert timeout_for_purpose(purpose) == DEFAULT_REQUEST_TIMEOUT


def test_the_deep_budget_is_long_enough_for_the_measured_model() -> None:
    """deepseek-v4-pro answered in 164s. A budget under that is a fix that
    cannot work, which is worse than no fix because it looks like one."""
    from eva.llm.providers._openai_compatible import DEEP_REQUEST_TIMEOUT

    assert DEEP_REQUEST_TIMEOUT > 164, "the deep budget is shorter than a measured successful call"


def test_deep_purposes_match_the_roles_that_select_the_deep_model() -> None:
    """If these drift, a request is routed to the deep model and then refused the
    time to wait for it -- the exact combination that produced this bug."""
    from eva.llm.providers._openai_compatible import DEEP_PURPOSES
    from eva.llm.providers.nvidia_nim import nvidia_nim_role_models

    deep_model = nvidia_nim_role_models()["deep_reasoning"]
    from eva.llm.providers.nvidia_nim import nvidia_nim_models_for_purpose

    for purpose in DEEP_PURPOSES:
        assert nvidia_nim_models_for_purpose(purpose)[0] == deep_model, (
            f"purpose {purpose!r} gets the long timeout but does not select the deep model"
        )


# --------------------------------------------------------------------------
# The timeout actually reaches the request
# --------------------------------------------------------------------------


class _CapturingClient:
    """Stands in for httpx.AsyncClient and records the timeout it was built with."""

    seen: list[float] = []

    def __init__(self, timeout=None, **_kwargs):
        _CapturingClient.seen.append(float(getattr(timeout, "read", timeout) or 0))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def post(self, *_args, **_kwargs):
        raise httpx.ReadTimeout("")


def test_the_timeout_reaches_the_actual_request(monkeypatch) -> None:
    """A setting that never gets to httpx is a setting that does nothing.

    The old code passed a literal 12.0 here, so no configuration anywhere could
    have changed it.
    """
    from eva.core.config import ModelSettings
    from eva.llm.providers import _openai_compatible
    from eva.llm.providers.nvidia_nim import NvidiaNIMProvider

    monkeypatch.setattr(_openai_compatible.httpx, "AsyncClient", _CapturingClient)
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-key-not-a-real-one")
    _CapturingClient.seen.clear()

    provider = NvidiaNIMProvider(ModelSettings(), model="deepseek-ai/deepseek-v4-pro-0813")
    provider.request_timeout = 240.0
    response = asyncio.run(provider.complete([{"role": "user", "content": "hi"}], max_tokens=8))

    assert _CapturingClient.seen == [240.0], "the request did not use the timeout it was given"
    # And the resulting failure explains itself rather than arriving blank.
    assert not response.ok
    assert "ReadTimeout" in str(response.error)
    assert "240" in str(response.error)


def test_the_router_sets_the_timeout_from_the_purpose() -> None:
    source = ROUTER_PY.read_text(encoding="utf-8")
    assert "provider.request_timeout = timeout_for_purpose(purpose)" in source, (
        "nothing connects the purpose to the request budget, so every call gets the same one"
    )


def test_no_provider_keeps_a_hardcoded_twelve_second_timeout() -> None:
    """It was written down twice -- once in the shared OpenAI-compatible base and
    once in Gemini, which is the FALLBACK nvidia_nim fails over to. Fixing only
    the first would have left a deep request cut off the moment it failed over."""
    for path in (COMPAT_PY, GEMINI_PY):
        source = path.read_text(encoding="utf-8")
        assert "httpx.Timeout(12.0" not in source, f"{path.name} still hardcodes a 12s timeout"
        assert "error=str(exc)" not in source, f"{path.name} can still report a failure with no reason"


def test_the_probe_asks_each_model_under_its_own_role() -> None:
    """The probe called every model with purpose="chat", so it gave the deep
    model 12 seconds for a job that takes 164 and then reported it dead. This
    file's own comment about max_tokens says it: the probe's parameters must not
    manufacture the failure it is looking for."""
    source = DOCTOR_PY.read_text(encoding="utf-8")
    block = source.split("for role, model in _nim_models_to_probe()", 1)[1].split("return results", 1)[0]
    assert "purpose=role" in block, "the probe still asks every model as generic chat"
    assert 'purpose="chat"' not in block
