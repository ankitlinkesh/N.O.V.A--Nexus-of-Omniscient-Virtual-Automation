"""Standalone verifier for Phase 77 (live-validation harness).

Twice in this project a run was reported as "validated live" when in truth no
model had run: a bare `python -c ...` snippet never loaded `.env.local`, every
provider was therefore unconfigured, and `complete_with_fallback` returned its
`provider="none"` no-LLM sentinel -- which looked, to a hopeful reader, exactly
like a real answer. This harness makes that failure impossible to report as
success, and this verifier pins the reasons it cannot:

  1. LIVENESS IS STRUCTURAL. It is read from the router's own response --
     `ok` AND a real provider -- so the `none` sentinel can never read as live.
  2. THE GUARD ACTUALLY GUARDS. `assert_live` raises on a not-live verdict, so
     a script cannot print "validated live" over the sentinel.
  3. NO-PROVIDER IS A REFUSAL, NOT A FALSE LIVE. When nothing can run, the
     harness does not even call the router and reports refusal (exit 2) -- the
     one case it can prove, reported honestly, instead of an invented LIVE.
  4. ENV IS LOADED FIRST. The omitted step that caused the original bug runs
     before readiness is assessed or the router is called.
  5. THE REAL READINESS CHECK IS OFFLINE. `assess_readiness` decides from
     configuration alone (the LLM doctor's report), touching no network, so
     the verifier itself spends no quota.
  6. THE CLI IS WIRED to the harness's exit code.

Fully offline: the router is a fake; no provider is contacted.
"""

from __future__ import annotations

import ast
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


def main() -> int:
    from eva.diagnostics.live_drive import (
        EXIT_LIVE,
        EXIT_NOT_LIVE,
        EXIT_REFUSED,
        NotLiveError,
        Readiness,
        assert_live,
        assess_readiness,
        classify,
        run_and_report,
    )
    from eva.llm.types import LLMResponse, RoutedLLMResponse

    def routed(provider: str, ok: bool) -> RoutedLLMResponse:
        return RoutedLLMResponse(response=LLMResponse(provider=provider, model="m", text="ok", ok=ok))

    # ------------------------------------------------------------------ 1
    check(classify(routed("none", False)).llm_ran is False, "the `none` no-LLM sentinel was read as a live run")
    check(classify(routed("", False)).llm_ran is False, "an empty provider was read as a live run")
    check(classify(routed("groq", True)).llm_ran is True, "a real provider's ok response was not read as live")
    check(classify(routed("groq", False)).llm_ran is False, "a failed named-provider response was read as live")

    # ------------------------------------------------------------------ 2
    try:
        assert_live(classify(routed("none", False)))
    except NotLiveError:
        pass
    else:
        raise AssertionError("assert_live did not raise on a not-live verdict -- the guard does not guard")
    check(assert_live(classify(routed("groq", True))).llm_ran is True, "assert_live rejected a genuinely live verdict")

    # ------------------------------------------------------------------ 3
    router_calls = {"n": 0}

    async def exploding_router(*args, **kwargs):
        router_calls["n"] += 1
        raise AssertionError("router was called even though nothing could run")

    refused = run_and_report(
        env_loader=lambda root: None,
        readiness=lambda: Readiness(False, (), "no provider configured"),
        router=exploding_router,
    )
    check(refused.exit_code == EXIT_REFUSED, f"a no-provider run was not refused (exit {refused.exit_code})")
    check(router_calls["n"] == 0, "the router was called despite readiness=cannot-run")
    check(refused.verdict is None, "a refusal produced a liveness verdict it had no basis for")
    check("REFUSING" in refused.message, "the refusal does not announce itself")

    # ------------------------------------------------------------------ 3b
    async def none_router(*args, **kwargs):
        return routed("none", False)

    not_live = run_and_report(
        env_loader=lambda root: None,
        readiness=lambda: Readiness(True, ("groq",), "configured"),
        router=none_router,
    )
    check(not_live.exit_code == EXIT_NOT_LIVE, "a ready run that reached the sentinel was not reported NOT LIVE")

    async def ok_router(*args, **kwargs):
        return routed("groq", True)

    live = run_and_report(
        env_loader=lambda root: None,
        readiness=lambda: Readiness(True, ("groq",), "configured"),
        router=ok_router,
    )
    check(live.exit_code == EXIT_LIVE, "a real provider answer was not reported LIVE")

    # ------------------------------------------------------------------ 4
    order: list[str] = []

    def loader(root):
        order.append("env")

    def readiness():
        order.append("readiness")
        return Readiness(True, ("groq",), "configured")

    async def tracking_router(*args, **kwargs):
        order.append("router")
        return routed("groq", True)

    run_and_report(env_loader=loader, readiness=readiness, router=tracking_router)
    check(order == ["env", "readiness", "router"], f"env was not loaded before readiness/router; order was {order}")

    # ------------------------------------------------------------------ 5
    # The real readiness check must be a pure function of configuration, no
    # network. With no keys and no local mode it must refuse; with a key it
    # must be ready -- proving refusal is driven by config, not by luck.
    empty = assess_readiness(env={})
    check(empty.can_run is False, "assess_readiness reported ready with no provider configured and no local mode")
    ready = assess_readiness(env={"GROQ_API_KEY": "x" * 20})
    check(ready.can_run is True, "assess_readiness did not see a configured cloud key")
    check("groq" in ready.configured, "assess_readiness did not name the configured provider")
    local = assess_readiness(env={"EVA_LLM_MODE": "local"})
    check(local.can_run is True, "assess_readiness refused despite a local ollama mode being selected")

    # ------------------------------------------------------------------ 6
    cli = (ROOT / "scripts" / "live_drive.py").read_text(encoding="utf-8")
    tree = ast.parse(cli)
    returns_exit_code = any(
        isinstance(node, ast.Attribute) and node.attr == "exit_code"
        for node in ast.walk(tree)
    )
    check("run_and_report" in cli, "the CLI does not call the harness")
    check(returns_exit_code, "the CLI does not return the harness's exit code -- a refusal could exit 0")

    # ------------------------------------------------------------------ 7
    import verify_eva_all

    name = "verify_eva_phase77_live_drive.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 77 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 77 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 77 verifier")

    print(
        "PASS: Phase 77 live-validation harness. Twice in this project a run was reported as validated live when no "
        "model had actually run -- a bare harness never loaded `.env.local`, every provider was unconfigured, and the "
        "router's `provider=none` no-LLM sentinel looked like a real answer. That is now structurally impossible to "
        "report as success: liveness is read from the router's own response (ok AND a real provider), so the sentinel "
        "can never read as live; `assert_live` RAISES on a not-live verdict so a script cannot print 'validated live' "
        "over it; when nothing can run the harness REFUSES -- it does not even call the router and reports refusal "
        "(exit 2) rather than an invented LIVE; env is loaded FIRST, before readiness or the router; and the real "
        "readiness check is a pure offline function of configuration, spending no quota."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
