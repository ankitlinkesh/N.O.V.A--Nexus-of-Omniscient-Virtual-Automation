"""Phase 92: the rot detector had no caller, and a dead model killed its provider.

On 2026-09-03 `openai/gpt-oss-120b` reached end of life and began returning HTTP
410 Gone. It was NVIDIA NIM's general, planner AND code model. Two mechanisms
built for exactly this event both failed to fire:

  A. `llm doctor` reported `nvidia_nim: configured, model=openai/gpt-oss-120b`,
     i.e. healthy, because it reports CONFIGURATION and makes no network call.
     `doctor.live_probe` -- the function that would have caught it -- was defined
     and exported and called by nothing in the repository, not even a test. Its
     docstring said "opt-in"; there was no way to opt in.

  B. `_try_nvidia_nim_models` iterates a per-purpose model list so a retired
     model can be survived. It broke out of that loop on the first 410, so the
     alive, configured fallback was never reached and NIM was abandoned.

Everything here is offline: no network call, no quota, no real provider.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from backend.eva.llm import doctor as doctor_module
from backend.eva.llm import router as router_module
from backend.eva.llm.types import LLMResponse


# --------------------------------------------------------------- B: the router


def test_a_retired_model_is_still_not_worth_retrying():
    """The shared predicate must keep meaning what it says.

    `_is_retryable_failure` answers "should I retry this SAME model?", and for a
    410 the answer is correctly no. The fix must not widen it -- it is shared
    with the cross-provider loop, where a blanket "410 is retryable" would change
    behaviour for every provider and purpose.
    """
    gone = LLMResponse(provider="nvidia_nim", model="dead", ok=False, status_code=410, error="Gone")
    assert router_module._is_retryable_failure(gone) is False
    missing = LLMResponse(provider="nvidia_nim", model="dead", ok=False, status_code=404, error="Not Found")
    assert router_module._is_retryable_failure(missing) is False


def test_model_unavailable_statuses_are_the_two_that_mean_gone():
    assert router_module._MODEL_UNAVAILABLE_STATUS == {404, 410}


def _fake_call_provider(script: dict[str, LLMResponse]):
    """Return a _call_provider stand-in that answers per model id."""

    async def fake(provider, limiter, messages, **kwargs):
        response = script[provider.model]
        return response, router_module._is_retryable_failure(response)

    return fake


def _run_nim(monkeypatch, models: list[str], script: dict[str, LLMResponse]):
    monkeypatch.setattr(router_module, "nvidia_nim_models_for_purpose", lambda purpose: models)
    monkeypatch.setattr(router_module, "_call_provider", _fake_call_provider(script))

    class _Provider:
        def __init__(self, settings, model=None):
            self.model = model
            self.name = "nvidia_nim"

        def available(self):
            return True

    monkeypatch.setattr(router_module, "NvidiaNIMProvider", _Provider)

    class _Limiter:
        def can_call(self, *args, **kwargs):
            return True, ""

    attempts: list = []
    routed = asyncio.run(
        router_module._try_nvidia_nim_models(
            None,
            _Limiter(),
            attempts,
            [{"role": "user", "content": "hi"}],
            purpose="planner",
            temperature=0.0,
            max_tokens=64,
            estimated_tokens=10,
        )
    )
    return routed, attempts


def test_a_retired_model_no_longer_takes_the_provider_down_with_it(monkeypatch):
    """The bug, exactly as it happened: model 1 is gone, model 2 is alive."""
    script = {
        "dead-model": LLMResponse(provider="nvidia_nim", model="dead-model", ok=False, status_code=410, error="Gone"),
        "live-model": LLMResponse(provider="nvidia_nim", model="live-model", ok=True, text="ok"),
    }
    routed, attempts = _run_nim(monkeypatch, ["dead-model", "live-model"], script)

    assert routed is not None, (
        "a 410 on the first model abandoned the whole provider; the configured fallback was never tried"
    )
    assert routed.response.model == "live-model"
    assert routed.response.ok is True
    assert [a.model for a in attempts] == ["dead-model", "live-model"]


def test_a_404_advances_to_the_next_model_too(monkeypatch):
    script = {
        "typo-model": LLMResponse(provider="nvidia_nim", model="typo-model", ok=False, status_code=404, error="nope"),
        "live-model": LLMResponse(provider="nvidia_nim", model="live-model", ok=True, text="ok"),
    }
    routed, _ = _run_nim(monkeypatch, ["typo-model", "live-model"], script)
    assert routed is not None and routed.response.model == "live-model"


def test_a_bad_key_still_stops_immediately(monkeypatch):
    """401/403 is a fact about the PROVIDER, so trying more models just burns time."""
    script = {
        "model-a": LLMResponse(provider="nvidia_nim", model="model-a", ok=False, status_code=401, error="bad key"),
        "model-b": LLMResponse(provider="nvidia_nim", model="model-b", ok=True, text="ok"),
    }
    routed, attempts = _run_nim(monkeypatch, ["model-a", "model-b"], script)
    assert routed is None
    assert [a.model for a in attempts] == ["model-a"], "a bad key must not be retried against every model"


def test_a_non_retryable_non_model_error_still_stops(monkeypatch):
    """A 400 applies to the request, not the model; trying again just costs quota."""
    script = {
        "model-a": LLMResponse(provider="nvidia_nim", model="model-a", ok=False, status_code=400, error="bad request"),
        "model-b": LLMResponse(provider="nvidia_nim", model="model-b", ok=True, text="ok"),
    }
    routed, attempts = _run_nim(monkeypatch, ["model-a", "model-b"], script)
    assert routed is None
    assert [a.model for a in attempts] == ["model-a"]


# ---------------------------------------------------------------- A: the probe


def test_the_console_command_actually_runs_the_probe(monkeypatch):
    """Arrival, not a grep.

    Phase 91's lesson: a production string reference proves nothing about whether
    anything calls the thing. So dispatch the REAL console string and assert the
    injected probe ran.
    """
    from backend.eva.core import fast_commands
    from backend.eva.tools.registry import ToolRegistry

    called: list[bool] = []

    async def fake_live_probe(provider_names=None, *, settings=None):
        called.append(True)
        return {
            "network_used": True,
            "providers": {"nvidia_nim": {"ok": False, "error": "Gone", "model": "dead"}},
            "models": {"nvidia_nim:planner": {"ok": False, "status_code": 410, "model": "dead", "error": "Gone"}},
        }

    monkeypatch.setattr(doctor_module, "live_probe", fake_live_probe)

    handled = fast_commands.maybe_handle_fast_command("llm probe", ToolRegistry())
    assert handled is not None, "'llm probe' is not dispatched at all"
    assert called == [True], "the console command did not call live_probe"
    assert "dead" in handled[0]


@pytest.mark.parametrize(
    "phrase", ["llm probe", "llm live probe", "probe providers", "probe llm", "llm doctor live"]
)
def test_every_documented_phrase_reaches_the_probe(monkeypatch, phrase):
    from backend.eva.core import fast_commands
    from backend.eva.tools.registry import ToolRegistry

    called: list[str] = []

    async def fake_live_probe(provider_names=None, *, settings=None):
        called.append(phrase)
        return {"network_used": True, "providers": {}, "models": {}}

    monkeypatch.setattr(doctor_module, "live_probe", fake_live_probe)
    assert fast_commands.maybe_handle_fast_command(phrase, ToolRegistry()) is not None
    assert called == [phrase]


def test_the_probe_works_from_inside_a_running_event_loop(monkeypatch):
    """The shipped path, which a synchronous test does not exercise.

    `maybe_handle_fast_command` is called synchronously from inside
    `async def chat`, so a running loop is the NORMAL case in the app. Both
    obvious spellings raise exactly there while passing every test above:
    `asyncio.run` -> "cannot be called from a running event loop", and
    `run_until_complete` on a fresh loop -> "Cannot run the event loop while
    another loop is running".
    """
    from backend.eva.core import fast_commands
    from backend.eva.tools.registry import ToolRegistry

    async def fake_live_probe(provider_names=None, *, settings=None):
        return {
            "network_used": True,
            "providers": {"nvidia_nim": {"ok": True, "model": "live-model"}},
            "models": {},
        }

    monkeypatch.setattr(doctor_module, "live_probe", fake_live_probe)

    async def dispatch_from_a_route():
        return fast_commands.maybe_handle_fast_command("llm probe", ToolRegistry())

    handled = asyncio.run(dispatch_from_a_route())
    assert handled is not None
    assert "live-model" in handled[0]
    assert "couldn't complete the provider probe" not in handled[0], handled[0]


def test_the_probe_is_not_reachable_by_the_planner():
    """It spends real quota, so only a person at the console may trigger it."""
    from backend.eva.tools.registry import ToolRegistry

    registry = ToolRegistry()
    visible = {spec["name"] for spec in registry.planner_specs()}
    for name in ("llm_probe", "llm probe", "live_probe"):
        assert name not in visible
        assert name not in registry._tools


def test_the_offline_doctor_is_still_offline():
    """`llm doctor` must keep making no network call -- it is the CI-safe one."""
    source = inspect.getsource(doctor_module.configuration_report)
    assert "network_used" in source
    report = doctor_module.configuration_report({"GEMINI_API_KEY": "x"})
    assert report["network_used"] is False


# ----------------------------------------------- the probe must not lie either


def test_the_probe_defaults_to_real_settings_not_none():
    """Passing settings=None made gemini report a false failure.

    GeminiProvider reads settings.smart_model in its constructor, so the probe
    returned "AttributeError: 'NoneType' object has no attribute 'smart_model'"
    for a provider with four working keys. A probe that reports a healthy
    provider as dead is worse than no probe.
    """
    source = inspect.getsource(doctor_module.live_probe)
    assert "ModelSettings()" in source
    assert "if settings is None" in source


def test_the_probe_does_not_starve_a_reasoning_model():
    """max_tokens=16 made gemini-2.5-flash return empty_response.

    A reasoning model spends its budget thinking before emitting content, so a
    tight cap manufactures the very failure the probe is looking for.
    """
    source = inspect.getsource(doctor_module.live_probe)
    assert "max_tokens=16" not in source
    assert doctor_module.live_probe.__code__.co_consts is not None
    assert "probe_max_tokens = 256" in source


def test_the_nim_purpose_map_is_probed_not_just_one_model(monkeypatch):
    """gpt-oss-120b filled three roles; a single chat probe would miss two."""
    monkeypatch.setenv("NVIDIA_NIM_MODEL", "general-model")
    monkeypatch.setenv("NVIDIA_NIM_PLANNER_MODEL", "planner-model")
    monkeypatch.setenv("NVIDIA_NIM_CODE_MODEL", "code-model")
    pairs = doctor_module._nim_models_to_probe()
    roles = [role for role, _ in pairs]
    assert "general" in roles and "planner" in roles and "code" in roles
    # Not chat-completions models: probing them with a chat message would report
    # a failure that is an artefact of the probe.
    assert "embed" not in roles and "asr" not in roles and "tts" not in roles


def test_a_model_shared_by_several_roles_is_billed_once():
    report = {
        "providers": {},
        "models": {
            "nvidia_nim:vision": {"ok": True, "model": "shared", "deduped": False},
            "nvidia_nim:screen_reason": {"ok": True, "model": "shared", "deduped": True},
        },
    }
    text = doctor_module.format_live_probe(report)
    assert "not re-probed" in text


def test_a_retired_model_is_named_as_retired():
    report = {
        "providers": {},
        "models": {
            "nvidia_nim:planner": {
                "ok": False,
                "status_code": 410,
                "model": "openai/gpt-oss-120b",
                "error": "end of life",
            }
        },
    }
    text = doctor_module.format_live_probe(report)
    assert "THIS MODEL IS GONE" in text
    assert "openai/gpt-oss-120b" in text
    assert "Point the matching NVIDIA_NIM_*_MODEL setting" in text


def test_a_timeout_is_not_reported_as_a_retired_model():
    """The probe must not assert what it does not know."""
    report = {
        "providers": {},
        "models": {"nvidia_nim:deep_reasoning": {"ok": False, "status_code": None, "model": "slow", "error": ""}},
    }
    text = doctor_module.format_live_probe(report)
    assert "THIS MODEL IS GONE" not in text
    assert "may be fine" in text


def test_the_default_nim_model_is_not_the_retired_one():
    from backend.eva.llm.providers.nvidia_nim import DEFAULT_NIM_MODEL, nvidia_nim_role_models

    assert DEFAULT_NIM_MODEL != "openai/gpt-oss-120b"
    # And the code role must not hardcode it past the default either.
    source = inspect.getsource(nvidia_nim_role_models)
    assert "gpt-oss-120b" not in source


def test_the_offline_report_names_the_command_that_now_exists():
    """The advice used to point at a probe with no caller, so it could not be followed."""
    text = doctor_module.format_configuration_report(doctor_module.configuration_report({"GEMINI_API_KEY": "x"}))
    assert "llm probe" in text
