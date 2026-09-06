"""Standalone verifier for Phase 104 (a model that could never answer).

`deep_reasoning` sat on the open-issues list for several sessions as "times
out". It did not time out occasionally. Every provider call used a hardcoded
12-second read timeout -- for every model, every provider and every purpose --
and `deepseek-ai/deepseek-v4-pro-0813`, the configured deep_reasoning model,
answers correctly in a MEASURED 164 seconds: HTTP 200, content "ok". The model
was never broken and was never usable. Impossible by a factor of fourteen.

A reasoning model spends minutes thinking; that is what it is for. A chat-shaped
timeout is not a tight margin for it, it is a guarantee of failure -- so the
budget now follows the PURPOSE, set in the router, which is the only place that
knows both the purpose and the provider. The default stays 12s deliberately: an
interactive request must not hang for four minutes because a provider is slow,
and turning the default up would trade this bug for a worse one.

Underneath it, the reason nobody could tell what was wrong:

    str(httpx.ReadTimeout(...)) == ""

and the handler passed it through unchanged. So a timeout surfaced as
`ok=False, status_code=None, error=""` -- byte-identical to a retired model, a
DNS failure, a refused connection or a missing key. **`llm probe` -- the tool
Phase 92 built precisely to make provider rot visible -- reported
`nvidia/nemotron-3.5-content-safety` as dead on that evidence while the same
code path answered in 0.6 seconds.** A diagnostic with false negatives it cannot
explain is worse than no diagnostic: it sends you to fix something that works.

Three properties carry the fix, and the third is the one that would have been
missed:

  * **No transport failure is ever reported blank.** The exception class name is
    always present, and a timeout says how long it waited.
  * **The budget follows the purpose**, and the deep purposes are pinned to the
    roles that actually select the deep model -- if those drift, a request gets
    routed to a model it is then refused the time to wait for, which is exactly
    the combination that produced this bug.
  * **Every provider, not just the first one.** The 12s literal was written down
    twice: in the shared OpenAI-compatible base and in Gemini, which is the
    FALLBACK nvidia_nim fails over to. Fixing only the base would have left a
    deep request cut off the instant it failed over -- the same "one rule written
    in two places, and the unwatched copy decides" shape as Phases 102 and 103.

The source checks are mutation-tested against an in-memory copy. The behavioural
checks are driven: a real provider is pointed at a capturing transport, so the
timeout is observed where it is actually applied rather than where it is
declared, and the resulting failure is read for its reason.
Fully offline: no network, no LLM, no provider, no browser.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

COMPAT_PY = BACKEND / "eva" / "llm" / "providers" / "_openai_compatible.py"
GEMINI_PY = BACKEND / "eva" / "llm" / "providers" / "gemini.py"
OLLAMA_PY = BACKEND / "eva" / "llm" / "providers" / "ollama.py"
ROUTER_PY = BACKEND / "eva" / "llm" / "router.py"
DOCTOR_PY = BACKEND / "eva" / "llm" / "doctor.py"

# Measured 2026-09-06 against the live endpoint: HTTP 200, content "ok".
MEASURED_DEEP_SECONDS = 164.3


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def check_raises(fn, message: str) -> None:
    """A check that cannot fail is not a check -- so prove this one can."""
    try:
        fn()
    except AssertionError:
        return
    raise AssertionError("MUTATION SURVIVED: " + message)


# ------------------------------------------------- the checks, over sources


def assert_no_hardcoded_timeout(compat: str, gemini: str) -> None:
    for label, source in (("_openai_compatible.py", compat), ("gemini.py", gemini)):
        check(
            "httpx.Timeout(12.0" not in source,
            f"{label} still hardcodes a 12s read timeout, which no configuration can reach",
        )
        check(
            "request_timeout" in source,
            f"{label} does not read a per-call timeout, so the purpose cannot change it",
        )


def assert_no_blank_failure_path(compat: str, gemini: str, ollama: str) -> None:
    for label, source in (("_openai_compatible.py", compat), ("gemini.py", gemini), ("ollama.py", ollama)):
        check(
            "error=str(exc)" not in source,
            f"{label} can still report a transport failure with no reason at all -- "
            "str(httpx.ReadTimeout(...)) is the empty string",
        )
    check(
        "describe_transport_error" in gemini,
        "gemini does not describe its transport failures, and it also RECORDS the reason "
        "into the rate limiter, so a blank one is persisted",
    )


def assert_router_binds_timeout_to_purpose(router: str) -> None:
    check(
        "provider.request_timeout = timeout_for_purpose(purpose)" in router,
        "nothing connects the purpose to the request budget, so every call gets one number",
    )


def assert_probe_uses_each_role(doctor: str) -> None:
    check("for role, model in _nim_models_to_probe()" in doctor, "the NIM per-role probe is gone")
    block = doctor.split("for role, model in _nim_models_to_probe()", 1)[1].split("return results", 1)[0]
    check(
        "purpose=role" in block and 'purpose="chat"' not in block,
        "the probe still asks every model as generic chat, so it gives the deep model 12 "
        "seconds for a job that takes 164 and then reports the model dead -- the probe "
        "manufacturing the failure it is looking for, which this file already warns about "
        "one line up regarding max_tokens",
    )


# ------------------------------------------------------ the driven checks


def drive_blank_error_is_impossible() -> None:
    from eva.llm.providers._openai_compatible import describe_transport_error

    for exc in (
        httpx.ReadTimeout(""),
        httpx.ConnectTimeout(""),
        httpx.PoolTimeout(""),
        httpx.ConnectError(""),
        httpx.HTTPError(""),
    ):
        check(
            str(exc) == "",
            f"{type(exc).__name__} no longer stringifies to empty -- this check has stopped "
            "measuring the condition that caused the bug",
        )
        described = describe_transport_error(exc, 12.0)
        check(described.strip(), f"{type(exc).__name__} was still described with nothing at all")
        check(type(exc).__name__ in described, f"{type(exc).__name__} is not named in its own description")

    waited = describe_transport_error(httpx.ReadTimeout(""), MEASURED_DEEP_SECONDS)
    check(str(int(MEASURED_DEEP_SECONDS)) in waited, "a timeout does not say how long it waited")
    kept = describe_transport_error(httpx.ConnectError("name resolution failed"), 12.0)
    check("name resolution failed" in kept, "an exception that HAS a message lost it")


def drive_purpose_budgets() -> None:
    from eva.llm.providers._openai_compatible import (
        DEEP_PURPOSES,
        DEEP_REQUEST_TIMEOUT,
        DEFAULT_REQUEST_TIMEOUT,
        timeout_for_purpose,
    )
    from eva.llm.providers.nvidia_nim import nvidia_nim_models_for_purpose, nvidia_nim_role_models

    check(
        DEEP_REQUEST_TIMEOUT > MEASURED_DEEP_SECONDS,
        f"the deep budget ({DEEP_REQUEST_TIMEOUT:g}s) is shorter than a measured successful "
        f"call ({MEASURED_DEEP_SECONDS:g}s) -- a fix that cannot work is worse than none, "
        "because it looks like one",
    )
    check(
        DEFAULT_REQUEST_TIMEOUT < DEEP_REQUEST_TIMEOUT,
        "the default budget was raised to the deep one, which trades this bug for an "
        "interactive request that hangs for minutes",
    )
    for purpose in ("chat", "planner", "code", "vision", "", None):
        check(
            timeout_for_purpose(purpose) == DEFAULT_REQUEST_TIMEOUT,
            f"purpose {purpose!r} was quietly granted the long budget",
        )
    deep_model = nvidia_nim_role_models()["deep_reasoning"]
    for purpose in DEEP_PURPOSES:
        check(
            timeout_for_purpose(purpose) == DEEP_REQUEST_TIMEOUT,
            f"purpose {purpose!r} is listed as deep but does not get the deep budget",
        )
        check(
            nvidia_nim_models_for_purpose(purpose)[0] == deep_model,
            f"purpose {purpose!r} gets the long budget but does not select the deep model -- "
            "if these drift a request is routed to a model it is refused the time to await",
        )


class _CapturingClient:
    """The real request path, with the transport replaced. Nothing leaves the box."""

    seen: list[float] = []

    def __init__(self, timeout=None, **_kwargs):
        _CapturingClient.seen.append(float(getattr(timeout, "read", timeout) or 0))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def post(self, *_args, **_kwargs):
        raise httpx.ReadTimeout("")


def drive_timeout_reaches_the_request() -> None:
    """Observed where it is APPLIED, not where it is declared.

    The old code passed a literal into httpx, so a setting could have existed
    anywhere and changed nothing.
    """
    import os

    from eva.core.config import ModelSettings
    from eva.llm.providers import _openai_compatible
    from eva.llm.providers.nvidia_nim import NvidiaNIMProvider

    real_client = _openai_compatible.httpx.AsyncClient
    had_key = os.environ.get("NVIDIA_NIM_API_KEY")
    os.environ["NVIDIA_NIM_API_KEY"] = had_key or "verifier-placeholder-not-a-real-key"
    _openai_compatible.httpx.AsyncClient = _CapturingClient
    _CapturingClient.seen.clear()
    try:
        provider = NvidiaNIMProvider(ModelSettings(), model="deepseek-ai/deepseek-v4-pro-0813")
        provider.request_timeout = 240.0
        response = asyncio.run(provider.complete([{"role": "user", "content": "hi"}], max_tokens=8))
    finally:
        _openai_compatible.httpx.AsyncClient = real_client
        if had_key is None:
            os.environ.pop("NVIDIA_NIM_API_KEY", None)

    check(
        _CapturingClient.seen == [240.0],
        f"the request did not use the timeout it was given: {_CapturingClient.seen!r}",
    )
    check(not response.ok, "a timed-out request reported success")
    check("ReadTimeout" in str(response.error), "the timeout did not name itself in the failure")
    check("240" in str(response.error), "the failure does not say how long it waited")


def main() -> int:
    compat = COMPAT_PY.read_text(encoding="utf-8")
    gemini = GEMINI_PY.read_text(encoding="utf-8")
    ollama = OLLAMA_PY.read_text(encoding="utf-8")
    router = ROUTER_PY.read_text(encoding="utf-8")
    doctor = DOCTOR_PY.read_text(encoding="utf-8")

    # ------------------------------------------------------- source checks
    assert_no_hardcoded_timeout(compat, gemini)
    check_raises(
        lambda: assert_no_hardcoded_timeout(
            compat.replace("httpx.Timeout(timeout, connect=CONNECT_TIMEOUT)", "httpx.Timeout(12.0, connect=4.0)"),
            gemini,
        ),
        "the base provider going back to a hardcoded 12s survives the check",
    )
    # The load-bearing mutation: the literal was written down TWICE, and Gemini
    # is the provider nvidia_nim fails over to. A check that only reads the base
    # is green while a deep request is still cut off the moment it falls back.
    check_raises(
        lambda: assert_no_hardcoded_timeout(
            compat,
            gemini.replace("httpx.Timeout(timeout, connect=CONNECT_TIMEOUT)", "httpx.Timeout(12.0, connect=4.0)"),
        ),
        "the FALLBACK provider keeping a hardcoded 12s survives the check",
    )

    assert_no_blank_failure_path(compat, gemini, ollama)
    check_raises(
        lambda: assert_no_blank_failure_path(
            compat.replace("error=describe_transport_error(exc, timeout),", "error=str(exc),"), gemini, ollama
        ),
        "restoring the blank-error path in the base provider survives the check",
    )
    check_raises(
        lambda: assert_no_blank_failure_path(
            compat, gemini.replace("describe_transport_error", "str"), ollama
        ),
        "gemini losing its failure description survives the check",
    )

    assert_router_binds_timeout_to_purpose(router)
    check_raises(
        lambda: assert_router_binds_timeout_to_purpose(
            router.replace("provider.request_timeout = timeout_for_purpose(purpose)", "pass")
        ),
        "the router no longer binding the budget to the purpose survives the check",
    )

    assert_probe_uses_each_role(doctor)
    check_raises(
        lambda: assert_probe_uses_each_role(doctor.replace("purpose=role,", 'purpose="chat",')),
        "the probe going back to asking every model as generic chat survives the check",
    )

    # ----------------------------------------------------- driven checks
    drive_blank_error_is_impossible()
    drive_purpose_budgets()
    drive_timeout_reaches_the_request()

    # ---------------------------------------------------------- registration
    import verify_eva_all

    name = "verify_eva_phase104_timeout_truth.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 104 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 104 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 104 verifier")

    print(
        "PASS: Phase 104 timeout truth. `deep_reasoning` was on the open-issues list as "
        "\"times out\" for several sessions; it never timed out occasionally. Every provider "
        "call used a hardcoded 12-second read timeout for every model and every purpose, and "
        "deepseek-v4-pro answers correctly in a measured 164 seconds -- the model was never "
        "broken and was never usable, impossible by a factor of fourteen. The budget now "
        "follows the purpose, set in the router where both are known, with the deep purposes "
        "pinned to the roles that actually select the deep model so the two cannot drift; the "
        "default stays 12s so an interactive request never hangs for minutes. Underneath it, "
        "the reason nobody could tell: str(httpx.ReadTimeout(...)) is the EMPTY STRING and the "
        "handler passed it through, so a timeout arrived as ok=False/status=None/error='' -- "
        "byte-identical to a retired model or a missing key. `llm probe`, built in Phase 92 to "
        "make provider rot visible, reported a healthy content-safety model as dead on exactly "
        "that evidence while the same code path answered in 0.6s. No transport failure can be "
        "blank now, a timeout says how long it waited, the fix reaches Gemini and Ollama too "
        "(the 12s literal was written down twice, and Gemini is the fallback), and the probe "
        "asks each model under its own role instead of manufacturing the failure it looks for. "
        "Source checks mutation-tested, including the fallback-provider copy; the blank-error "
        "guarantee, the purpose budgets and the timeout actually reaching httpx are driven."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
