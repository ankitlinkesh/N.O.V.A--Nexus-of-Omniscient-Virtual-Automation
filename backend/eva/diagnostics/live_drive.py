"""Phase 77: a harness that proves an LLM actually ran.

The recurring self-error this closes: a bare ``python -c ...`` harness never
loads ``.env.local``, so every provider is unconfigured, every call silently
routes to ``provider="none"``, and the run LOOKS live while no model ever ran.
Twice in this project a "live validation" was retroactively found to have used
no LLM at all -- the machinery answered from local fallbacks and the claim of
"I drove this live" was false without anyone noticing.

The fix is not a promise to remember; it is a structural guard:

  * env is loaded FIRST (``load_project_env``), the exact step the bare harness
    skips. The loader is recorded so a caller cannot forget it.
  * a run counts as LIVE iff the router returned ``response.ok`` AND a real
    provider -- not the ``"none"`` sentinel ``complete_with_fallback`` emits
    when every provider was unavailable (router.py returns
    ``LLMResponse(provider="none", ok=False)`` in that case).
  * when NO model can possibly run (no cloud key configured and not a local
    ollama mode), the harness REFUSES to drive and REFUSES to report LIVE. It
    cannot prove liveness against a machine that has no model, and printing
    "LIVE" there would recreate the precise bug this exists to kill.

Everything is injectable (``env_loader``, ``router``, ``readiness``) so the
verifier and unit tests exercise every branch fully offline, with no network
and no real quota spent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Sequence

from ..core.config import ModelSettings, load_project_env
from ..llm.router import complete_with_fallback
from ..llm.types import RoutedLLMResponse

# backend/eva/diagnostics/live_drive.py -> repo root is four parents up.
ROOT = Path(__file__).resolve().parents[3]

# The sentinel provider name complete_with_fallback uses when nothing ran.
_NO_PROVIDER = {"", "none"}

# Refusal exit code: reserved for "no model could possibly run". Kept distinct
# from a genuine NOT-LIVE result (1) so a caller can tell "you have no provider"
# apart from "a provider was tried and failed".
EXIT_LIVE = 0
EXIT_NOT_LIVE = 1
EXIT_REFUSED = 2


class NotLiveError(RuntimeError):
    """Raised by :func:`assert_live` when no model actually ran."""


@dataclass(frozen=True)
class LiveVerdict:
    """What the router actually did, decided structurally from its response."""

    llm_ran: bool
    provider: str
    model: str
    fallback_occurred: bool
    attempted_providers: tuple[str, ...]
    detail: str

    def as_line(self) -> str:
        if self.llm_ran:
            return f"LIVE — {self.provider}/{self.model} actually ran ({self.detail})."
        return f"NOT LIVE — router returned provider={self.provider!r}; no model ran ({self.detail})."


@dataclass(frozen=True)
class Readiness:
    """Whether a model could possibly run, decided offline from config alone."""

    can_run: bool
    configured: tuple[str, ...]
    reason: str


def classify(routed: RoutedLLMResponse) -> LiveVerdict:
    """Decide from the router's own response whether a model actually ran.

    The whole point: this reads structure, never a self-report. A run is live
    only when the response is ``ok`` AND its provider is a real one, so the
    ``provider="none"`` no-LLM fallback can never masquerade as a live run.
    """

    response = routed.response
    attempted = tuple(attempt.provider for attempt in routed.attempts)
    ran = bool(response.ok and response.provider not in _NO_PROVIDER)
    if ran:
        detail = "fell back across providers" if routed.fallback_occurred else "first provider answered"
    elif response.provider in _NO_PROVIDER:
        detail = response.error or "every provider was unavailable"
    else:
        detail = response.error or "provider returned no usable content"
    return LiveVerdict(
        llm_ran=ran,
        provider=response.provider,
        model=response.model,
        fallback_occurred=routed.fallback_occurred,
        attempted_providers=attempted,
        detail=detail,
    )


def assert_live(verdict: LiveVerdict) -> LiveVerdict:
    """Raise unless a model genuinely ran. The guard that stops a script from
    printing "validated live" when the router only reached its no-LLM sentinel."""

    if not verdict.llm_ran:
        raise NotLiveError(verdict.as_line())
    return verdict


def _cloud_providers_configured(env: dict | None = None) -> tuple[str, ...]:
    """Cloud providers that currently have a key -- computed offline, no
    network, by reusing the LLM doctor's configuration report."""

    from ..llm.doctor import configuration_report

    report = configuration_report(environ=env)
    providers = report.get("providers", {})
    return tuple(
        name
        for name, entry in providers.items()
        if name != "ollama" and entry.get("configured")
    )


def assess_readiness(env: dict | None = None) -> Readiness:
    """Can a model possibly run, decided from configuration alone (offline)?

    True when any cloud provider has a key, OR a local ollama mode is selected
    (we cannot cheaply prove the local server is up without a call, so we do
    not refuse on its behalf -- if it is down the drive simply comes back NOT
    LIVE, which is the honest answer). Refusal is reserved for the one case we
    CAN prove: no cloud key and no local mode, i.e. nothing to run at all.
    """

    import os

    environ = env if env is not None else os.environ
    configured = _cloud_providers_configured(environ)
    mode = str(environ.get("EVA_LLM_MODE", "auto")).strip().lower()
    local_mode = mode in {"qwen", "llama", "local"}
    use_ollama_planner = str(environ.get("EVA_USE_OLLAMA_FOR_PLANNER", "")).strip().lower() in {"1", "true", "yes", "on"}
    if configured:
        return Readiness(True, configured, f"cloud providers configured: {', '.join(configured)}")
    if local_mode or use_ollama_planner:
        return Readiness(True, configured, "local ollama mode selected; liveness will be decided by the drive itself")
    return Readiness(False, configured, "no cloud provider has a key and no local ollama mode is selected")


# Injectable seams. The defaults are the real ones; tests and the verifier pass
# fakes so every branch runs offline.
RouterFn = Callable[..., Awaitable[RoutedLLMResponse]]
EnvLoader = Callable[[Path], None]
ReadinessFn = Callable[[], Readiness]


@dataclass
class DriveReport:
    exit_code: int
    message: str
    verdict: LiveVerdict | None = None
    readiness: Readiness | None = None
    env_loaded: bool = False
    router_called: bool = False
    trace: list[str] = field(default_factory=list)


def run_and_report(
    prompt: str = "Reply with exactly: ok",
    *,
    env_loader: EnvLoader = load_project_env,
    readiness: ReadinessFn | None = None,
    router: RouterFn = complete_with_fallback,
    purpose: str = "planner",
) -> DriveReport:
    """Load env, check readiness, drive one real turn, and report honestly.

    Order matters and is enforced: env is loaded before anything reads a key,
    because that is the step whose omission caused the original silent-no-LLM
    bug. If no model could possibly run, the router is never even called and
    the report REFUSES to claim liveness.
    """

    trace: list[str] = []
    env_loader(ROOT)
    trace.append("env_loaded")

    assess = readiness if readiness is not None else assess_readiness
    ready = assess()
    trace.append(f"readiness:{ready.can_run}")

    if not ready.can_run:
        return DriveReport(
            exit_code=EXIT_REFUSED,
            message=(
                "REFUSING to validate live: " + ready.reason + ". "
                "No model can run, so no run can be proven live -- reporting that "
                "instead of a false LIVE."
            ),
            readiness=ready,
            env_loaded=True,
            router_called=False,
            trace=trace,
        )

    from ..mcp.runner import run_async

    messages = [{"role": "user", "content": prompt}]
    routed = run_async(router(messages, ModelSettings(), purpose=purpose, temperature=0.0, max_tokens=32))
    trace.append("router_called")
    verdict = classify(routed)

    exit_code = EXIT_LIVE if verdict.llm_ran else EXIT_NOT_LIVE
    return DriveReport(
        exit_code=exit_code,
        message=verdict.as_line(),
        verdict=verdict,
        readiness=ready,
        env_loaded=True,
        router_called=True,
        trace=trace,
    )


def format_report(report: DriveReport) -> str:
    lines = [report.message]
    if report.readiness is not None:
        lines.append(f"  readiness: {report.readiness.reason}")
    if report.verdict is not None and report.verdict.attempted_providers:
        lines.append(f"  providers attempted: {', '.join(report.verdict.attempted_providers)}")
    return "\n".join(lines)


__all__ = [
    "LiveVerdict",
    "Readiness",
    "DriveReport",
    "NotLiveError",
    "classify",
    "assert_live",
    "assess_readiness",
    "run_and_report",
    "format_report",
    "EXIT_LIVE",
    "EXIT_NOT_LIVE",
    "EXIT_REFUSED",
    "ROOT",
]
