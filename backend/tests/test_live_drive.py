"""Executable spec for the live-validation harness (Phase 77).

The harness exists to kill one specific, twice-committed self-error: claiming
"I validated this live" when a bare harness never loaded `.env.local`, so no
provider was configured, the router fell through to its `provider="none"`
sentinel, and no model actually ran. The properties worth pinning:

  1. Liveness is decided STRUCTURALLY from the router's response -- the
     `provider="none"` no-LLM fallback can never read as live.
  2. `assert_live` RAISES on a not-live verdict, so a script cannot print
     "validated live" over a run that only reached the sentinel.
  3. When no model can possibly run, the harness REFUSES: it does not even
     call the router, and it reports refusal (exit 2) rather than a false LIVE.
  4. Env is loaded BEFORE anything reads a key -- the omitted step that caused
     the original bug -- and before the router is ever called.

Every branch runs offline: the router, env loader, and readiness check are all
injected, so no network and no real quota are touched.
"""

from __future__ import annotations

import pytest

from eva.diagnostics.live_drive import (
    EXIT_LIVE,
    EXIT_NOT_LIVE,
    EXIT_REFUSED,
    NotLiveError,
    Readiness,
    assert_live,
    classify,
    run_and_report,
)
from eva.llm.types import LLMAttempt, LLMResponse, RoutedLLMResponse


def _routed(provider: str, ok: bool, *, text: str = "ok", attempts=None, fallback=False) -> RoutedLLMResponse:
    return RoutedLLMResponse(
        response=LLMResponse(provider=provider, model=f"{provider}-model", text=text, ok=ok),
        attempts=attempts or [],
        fallback_occurred=fallback,
    )


class TestClassifyIsStructural:
    def test_none_sentinel_is_never_live(self) -> None:
        verdict = classify(_routed("none", ok=False))
        assert verdict.llm_ran is False
        assert verdict.provider == "none"

    def test_empty_provider_is_never_live(self) -> None:
        assert classify(_routed("", ok=False)).llm_ran is False

    def test_ok_from_real_provider_is_live(self) -> None:
        verdict = classify(_routed("groq", ok=True))
        assert verdict.llm_ran is True
        assert verdict.provider == "groq"

    def test_provider_that_answered_but_not_ok_is_not_live(self) -> None:
        """A named provider that failed is still not a live run."""
        assert classify(_routed("gemini", ok=False)).llm_ran is False

    def test_attempted_providers_are_reported(self) -> None:
        attempts = [
            LLMAttempt(provider="nvidia_nim", model="m", purpose="planner", ok=False, error="missing_api_key"),
            LLMAttempt(provider="groq", model="m", purpose="planner", ok=True, selected_provider="groq"),
        ]
        verdict = classify(_routed("groq", ok=True, attempts=attempts, fallback=True))
        assert verdict.attempted_providers == ("nvidia_nim", "groq")
        assert verdict.fallback_occurred is True


class TestAssertLiveIsAGuard:
    def test_raises_on_not_live(self) -> None:
        with pytest.raises(NotLiveError):
            assert_live(classify(_routed("none", ok=False)))

    def test_passes_through_a_live_verdict(self) -> None:
        verdict = classify(_routed("groq", ok=True))
        assert assert_live(verdict) is verdict


class TestRunAndReportRefusesWhenNothingCanRun:
    def test_refuses_and_never_calls_the_router(self) -> None:
        called = {"router": False}

        async def exploding_router(*args, **kwargs):  # pragma: no cover - must not run
            called["router"] = True
            raise AssertionError("router was called despite nothing being able to run")

        report = run_and_report(
            env_loader=lambda root: None,
            readiness=lambda: Readiness(False, (), "no provider configured"),
            router=exploding_router,
        )
        assert report.exit_code == EXIT_REFUSED
        assert report.router_called is False
        assert called["router"] is False
        assert "REFUSING" in report.message


class TestRunAndReportDrivesWhenReady:
    def test_reports_not_live_when_router_returns_the_sentinel(self) -> None:
        async def none_router(*args, **kwargs):
            return _routed("none", ok=False)

        report = run_and_report(
            env_loader=lambda root: None,
            readiness=lambda: Readiness(True, ("groq",), "configured"),
            router=none_router,
        )
        assert report.exit_code == EXIT_NOT_LIVE
        assert report.verdict is not None and report.verdict.llm_ran is False

    def test_reports_live_when_a_real_provider_answers(self) -> None:
        async def ok_router(*args, **kwargs):
            return _routed("groq", ok=True)

        report = run_and_report(
            env_loader=lambda root: None,
            readiness=lambda: Readiness(True, ("groq",), "configured"),
            router=ok_router,
        )
        assert report.exit_code == EXIT_LIVE
        assert "LIVE" in report.message and report.router_called is True


class TestEnvIsLoadedBeforeAnythingReadsAKey:
    def test_env_load_precedes_readiness_and_router(self) -> None:
        order: list[str] = []

        def loader(root):
            order.append("env")

        def readiness():
            order.append("readiness")
            return Readiness(True, ("groq",), "configured")

        async def router(*args, **kwargs):
            order.append("router")
            return _routed("groq", ok=True)

        report = run_and_report(env_loader=loader, readiness=readiness, router=router)
        assert order == ["env", "readiness", "router"]
        assert report.env_loaded is True
