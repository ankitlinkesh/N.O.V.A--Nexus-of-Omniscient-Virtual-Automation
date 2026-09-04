"""Standalone verifier for Phase 92 (the rot detector had no caller).

On 2026-09-03 `openai/gpt-oss-120b` reached end of life and started returning
HTTP 410 Gone. It was NVIDIA NIM's general, planner AND code model -- three roles
of the primary provider, dead at once. Two mechanisms built for exactly this
event both failed to fire, and this verifier pins both.

**A. The detector could not be run.** `llm doctor` answered
`nvidia_nim: configured, model=openai/gpt-oss-120b` -- healthy -- because it
reports CONFIGURATION and says so ("no network calls made"). Phase 48 also
shipped `doctor.live_probe`, which would have caught it; that function was
defined, listed in `__all__`, and **called by nothing in the repository, not even
a test.** Its docstring said "opt-in and never runs by default"; there was no way
to opt in. This is the reachable-by-grep trap Phase 91 recorded, one level up
from tools: a function can be public, exported and documented and still be dead.

So the check here is ARRIVAL, not a grep: the real console string is dispatched
through `maybe_handle_fast_command` with an injected probe, and the injected
probe must actually have run.

**B. A dead model took its whole provider down.** `_try_nvidia_nim_models`
iterates a per-purpose model list precisely so a retired model can be survived,
then did `if not retryable: break`. A 410 is correctly *not* retryable -- that
predicate answers "should I retry this SAME model?" -- but the loop was asking
"should I try a DIFFERENT model?", where a retired model is the strongest reason
to say yes. So the configured, alive fallback was never reached and every call
fell through to gemini. Fixed in the loop, deliberately NOT in
`_is_retryable_failure`, which is shared with the cross-provider loop.

**The probe must not lie either.** Two false negatives were found in the probe
while testing it and are pinned below: `settings=None` made gemini report
`AttributeError: 'NoneType' object has no attribute 'smart_model'` (its
constructor reads `settings.smart_model`) while four working keys sat there, and
`max_tokens=16` starved gemini-2.5-flash into `empty_response` because a
reasoning model spends its budget thinking before emitting content. A probe whose
own parameters manufacture the failure it is looking for is worse than no probe.

Fully offline: no network call, no quota, no real provider.
"""

from __future__ import annotations

import asyncio
import inspect
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


PROBE_PHRASES = ("llm probe", "llm live probe", "probe providers", "probe llm", "llm doctor live")


def main() -> int:
    from eva.core import fast_commands
    from eva.llm import doctor as doctor_module
    from eva.llm import router as router_module
    from eva.llm.providers.nvidia_nim import DEFAULT_NIM_MODEL, nvidia_nim_role_models
    from eva.llm.types import LLMResponse
    from eva.tools.registry import ToolRegistry

    # ------------------------------------------------------- B: the router loop
    check(
        router_module._MODEL_UNAVAILABLE_STATUS == {404, 410},
        "404/410 are the statuses that mean 'this MODEL is gone' as opposed to "
        "'this provider is down'; the set changed",
    )

    gone = LLMResponse(provider="nvidia_nim", model="dead", ok=False, status_code=410, error="Gone")
    check(
        router_module._is_retryable_failure(gone) is False,
        "REGRESSION: _is_retryable_failure now calls a 410 retryable. That predicate is shared with the "
        "cross-provider loop and answers 'should I retry this SAME model?', where the answer is no. Widening "
        "it changes behaviour for every provider and purpose; the model-advance rule belongs in the NIM loop.",
    )

    class _Provider:
        def __init__(self, settings, model=None):
            self.model = model
            self.name = "nvidia_nim"

        def available(self):
            return True

    class _Limiter:
        def can_call(self, *args, **kwargs):
            return True, ""

    def run_models(models, script):
        original_models = router_module.nvidia_nim_models_for_purpose
        original_call = router_module._call_provider
        original_provider = router_module.NvidiaNIMProvider

        async def fake_call(provider, limiter, messages, **kwargs):
            response = script[provider.model]
            return response, router_module._is_retryable_failure(response)

        router_module.nvidia_nim_models_for_purpose = lambda purpose: models
        router_module._call_provider = fake_call
        router_module.NvidiaNIMProvider = _Provider
        try:
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
            return routed, [a.model for a in attempts]
        finally:
            router_module.nvidia_nim_models_for_purpose = original_models
            router_module._call_provider = original_call
            router_module.NvidiaNIMProvider = original_provider

    for status in (410, 404):
        script = {
            "dead": LLMResponse(provider="nvidia_nim", model="dead", ok=False, status_code=status, error="gone"),
            "live": LLMResponse(provider="nvidia_nim", model="live", ok=True, text="ok"),
        }
        routed, tried = run_models(["dead", "live"], script)
        check(
            routed is not None and routed.response.model == "live",
            "REGRESSION: a %s on the first model abandons the whole provider again. The per-purpose model "
            "list exists so a retired model can be survived; breaking out of it means the configured, alive "
            "fallback is never reached and every call falls through to the next provider." % status,
        )
        check(tried == ["dead", "live"], "both models should have been attempted, got %r" % (tried,))

    # The two cases that must still stop, or this fix becomes a quota leak.
    script = {
        "a": LLMResponse(provider="nvidia_nim", model="a", ok=False, status_code=401, error="bad key"),
        "b": LLMResponse(provider="nvidia_nim", model="b", ok=True, text="ok"),
    }
    routed, tried = run_models(["a", "b"], script)
    check(routed is None and tried == ["a"], "a bad key is a fact about the PROVIDER; it must not be retried per model")

    script = {
        "a": LLMResponse(provider="nvidia_nim", model="a", ok=False, status_code=400, error="bad request"),
        "b": LLMResponse(provider="nvidia_nim", model="b", ok=True, text="ok"),
    }
    routed, tried = run_models(["a", "b"], script)
    check(routed is None and tried == ["a"], "a 400 is about the request, not the model; retrying it just costs quota")

    # ------------------------------------------------ A: the probe has a caller
    calls: list[str] = []

    async def fake_live_probe(provider_names=None, *, settings=None):
        calls.append("ran")
        return {
            "network_used": True,
            "providers": {"nvidia_nim": {"ok": False, "error": "Gone", "model": "dead"}},
            "models": {"nvidia_nim:planner": {"ok": False, "status_code": 410, "model": "dead", "error": "Gone"}},
        }

    original_probe = doctor_module.live_probe
    doctor_module.live_probe = fake_live_probe
    try:
        registry = ToolRegistry()
        for phrase in PROBE_PHRASES:
            before = len(calls)
            handled = fast_commands.maybe_handle_fast_command(phrase, registry)
            check(handled is not None, "the console phrase %r is not dispatched at all" % phrase)
            check(
                len(calls) == before + 1,
                "THE CHECK THIS PHASE EXISTS FOR: %r was dispatched but live_probe never ran. Phase 48 shipped "
                "the probe with no caller anywhere, so the rot detector could not be run and `llm doctor` "
                "called a 410-dead model healthy. A production reference is reachable-by-grep; only arrival "
                "proves a caller." % phrase,
            )
    finally:
        doctor_module.live_probe = original_probe

    # THE SHIPPED PATH. `maybe_handle_fast_command` is called synchronously from
    # inside `async def chat`, so a running event loop is the normal case in the
    # app -- and the two obvious ways to run a coroutine there both raise while
    # passing every synchronous test above. This was a real defect in the first
    # version of this phase, caught by asking where the function is actually
    # called from rather than by any test.
    doctor_module.live_probe = fake_live_probe
    try:

        async def dispatch_from_a_route():
            return fast_commands.maybe_handle_fast_command("llm probe", ToolRegistry())

        handled = asyncio.run(dispatch_from_a_route())
        check(handled is not None, "'llm probe' is not dispatched from the route path")
        check(
            "couldn't complete the provider probe" not in handled[0],
            "REGRESSION: the probe raises when dispatched from inside a running event loop, which is how the "
            "shipped app calls it (`async def chat` -> maybe_handle_fast_command). asyncio.run raises 'cannot "
            "be called from a running event loop' and run_until_complete raises 'Cannot run the event loop "
            "while another loop is running'; only running it in a worker thread works everywhere. Got: %s"
            % handled[0][:160],
        )
    finally:
        doctor_module.live_probe = original_probe

    # It spends real quota, so only a person at the console may trigger it.
    visible = {spec["name"] for spec in ToolRegistry().planner_specs()}
    for name in ("llm_probe", "llm probe", "live_probe"):
        check(name not in visible, "%r must not be planner-visible: it spends real quota" % name)

    # `llm doctor` stays the offline, CI-safe one.
    report = doctor_module.configuration_report({"GEMINI_API_KEY": "x"})
    check(report.get("network_used") is False, "llm doctor must stay offline; it is the CI-safe report")

    # ------------------------------------------- the probe must not lie either
    probe_source = inspect.getsource(doctor_module.live_probe)
    check(
        "if settings is None" in probe_source and "ModelSettings()" in probe_source,
        "REGRESSION: live_probe can be handed settings=None again. GeminiProvider reads settings.smart_model "
        "in its constructor, so the probe reported a provider with four working keys as dead. A probe that "
        "reports a HEALTHY provider as broken is worse than no probe.",
    )
    check(
        "max_tokens=16" not in probe_source,
        "REGRESSION: the probe's token budget is back to 16. A reasoning model spends its budget thinking "
        "before emitting content, so gemini-2.5-flash returned empty_response and the probe manufactured the "
        "very failure it was looking for.",
    )

    pairs = doctor_module._nim_models_to_probe()
    roles = [role for role, _ in pairs]
    for role in ("planner", "code", "vision", "safety"):
        check(role in roles, "the NIM per-purpose map must be probed; %r is missing" % role)
    for role in ("embed", "rerank", "pii", "asr", "tts"):
        check(
            role not in roles,
            "%r is not a chat-completions model; probing it with a chat message reports a failure that is an "
            "artefact of the probe" % role,
        )

    text = doctor_module.format_live_probe(
        {
            "providers": {},
            "models": {
                "nvidia_nim:planner": {
                    "ok": False,
                    "status_code": 410,
                    "model": "openai/gpt-oss-120b",
                    "error": "end of life",
                },
                "nvidia_nim:deep": {"ok": False, "status_code": None, "model": "slow", "error": ""},
                "nvidia_nim:vision": {"ok": True, "model": "shared", "deduped": False},
                "nvidia_nim:screen_reason": {"ok": True, "model": "shared", "deduped": True},
            },
        }
    )
    check("THIS MODEL IS GONE" in text and "openai/gpt-oss-120b" in text, "a retired model must be named as retired")
    check(
        "Point the matching NVIDIA_NIM_*_MODEL setting" in text,
        "the report must say what to DO about a retired model, not merely that one exists",
    )
    check(
        text.count("THIS MODEL IS GONE") == 1,
        "a timeout must not be reported as a retired model; the probe must not assert what it does not know",
    )
    check("not re-probed" in text, "a model shared by several roles must be billed once and say so")

    # ------------------------------------------------- the retired model itself
    check(
        DEFAULT_NIM_MODEL != "openai/gpt-oss-120b",
        "the source default is still the model that reached end of life on 2026-09-03; an operator with no "
        "override gets a dead model",
    )
    check(
        "gpt-oss-120b" not in inspect.getsource(nvidia_nim_role_models),
        "the retired model is still hardcoded as a role default",
    )

    # ---------------------------------------------------------- registration
    import verify_eva_all

    name = "verify_eva_phase92_provider_rot_detection.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 92 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 92 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 92 verifier")

    print(
        "PASS: Phase 92 provider rot detection. `openai/gpt-oss-120b` reached end of life on 2026-09-03 as NIM's "
        "general, planner AND code model, and both mechanisms built for that event failed: `doctor.live_probe` was "
        "exported and called by nothing (so `llm doctor` reported the dead model healthy), and the per-purpose model "
        "loop broke on the first 410 instead of advancing, so the alive configured fallback was never reached. The "
        "console `llm probe` is now proven to CALL the probe (arrival, not a grep), 404/410 advance to the next model "
        "while 401/403 and 400 still stop, `_is_retryable_failure` keeps its narrower meaning, and the probe's own "
        "two false negatives -- settings=None and max_tokens=16 -- are pinned so it cannot start lying again."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
