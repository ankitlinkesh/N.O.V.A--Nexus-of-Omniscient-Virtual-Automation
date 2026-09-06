"""Standalone verifier for Phase 106 (the deep model finally has a caller).

Phase 104 fixed the request timeout that made `deep_reasoning` impossible to
use: every provider call had a hardcoded 12-second budget and `deepseek-v4-pro`
needs a measured 164 seconds. Then a grep for callers found there were none. The
role was configured in `.env.local`, mapped in `nvidia_nim_role_models`, probed
by `llm probe`, reachable through `nvidia_nim_models_for_purpose` -- and
requested by nothing, ever.

That is the reachable-by-grep trap, and this project has now hit it four times:
`doctor.live_probe` was exported and documented and called by nothing (92),
`listen_once` existed for two phases before anything invoked it (61), `app.focus`
was orphaned (64), and now this. **A capability nothing invokes is not a
capability**, so the load-bearing check here drives the real console dispatcher
and reads the purpose the ROUTER was actually handed. Asserting that a
`_run_deep` function exists would pass against a build nothing calls -- which is
precisely the state Phase 104 shipped in.

Console-only, and the reason is worth keeping straight because it is NOT the one
the other console boundaries use. `gui:`, `delegate`, `fill form:` and `$ ` are
console-only over AUTHORITY: they can act, and untrusted content must never be
able to choose them. This one carries no tool power at all -- it answers, it
cannot act. It is console-only over LATENCY: the call blocks for two to four
minutes, so a planner able to reach it could spend an entire errand's wall clock
on one step, and untrusted content that steers a planner there is a cheap denial
of service. No authorization is gained; the agent simply stops responding.

Two further properties, both earned rather than assumed:

  * **The prefix is colon-terminated and matched case-insensitively.** "think
    about it" is ordinary prose and must not be captured -- a refactor that
    STARTS handling a phrase is as much a regression as one that stops. But
    `think:` is the first word of a sentence, so a person capitalises it, and
    matching the raw text meant `Think: why does...` was silently handed to the
    LLM instead. Located case-insensitively, sliced from the original so the
    question's own casing survives.
  * **A failure names its reason.** Phase 104 exists because a failure on this
    path arrived as the empty string; reporting "it didn't work" without the
    reason would put that straight back.

Source checks are mutation-tested against an in-memory copy. The routing check
is driven -- a fake router records the purpose it was asked for -- because no
reading of the source can show that a typed message reaches it.
Fully offline: no network, no LLM, no provider, no browser.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

THINK_PY = BACKEND / "eva" / "core" / "fast_command_think.py"
FAST_PY = BACKEND / "eva" / "core" / "fast_commands.py"

# Measured 2026-09-06: 164.3s for a one-line prompt, 200s for a real question
# driven through the console handler.
MEASURED_SECONDS = 200


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


def assert_dispatched_from_the_console(fast: str) -> None:
    check(
        "from .fast_command_think import maybe_handle_think_command" in fast,
        "the console does not import the deep-reasoning handler",
    )
    check(
        "think = maybe_handle_think_command(" in fast,
        "the console never calls the deep-reasoning handler, so the role stays uncalled -- "
        "which is the entire defect this phase exists to fix",
    )


def assert_prefix_cannot_swallow_prose(think: str) -> None:
    check('"think: "' in think, "the colon-terminated prefix is gone")
    check(
        '"think "' not in think and '"deep "' not in think,
        "a bare `think `/`deep ` prefix would capture ordinary prose like 'think about it'",
    )
    check(
        "normalized.startswith(prefix)" in think,
        "the prefix is matched against the raw text, so a capitalised `Think:` -- the natural "
        "way to type the first word of a sentence -- is silently handed to the LLM instead",
    )
    check(
        "original[len(prefix) :]" in think,
        "the question is sliced from the normalized text, so it would lose its own casing",
    )


def assert_failures_name_their_reason(think: str) -> None:
    body = think.split("def _run_deep", 1)[1].split("\ndef ", 1)[0]
    check(
        'getattr(response, "error", "")' in body,
        "a failed deep call does not report the provider's reason -- the blank-failure mode "
        "Phase 104 removed, reintroduced one layer up",
    )
    check("no reason reported" in body, "a missing reason is not named as missing")


def assert_duration_is_stated_up_front(think: str) -> None:
    check(
        str(164) in think,
        "nothing states the measured duration, so the first use of a three-minute call is "
        "indistinguishable from a hang",
    )


# ------------------------------------------------------- the driven checks


def drive_purpose_reaches_the_router() -> tuple[str | None, str]:
    """Does a typed console message actually request the deep model?

    Driven, not read: the gap this phase fixes was a function that existed and
    was never called, which no source check can distinguish from one that is.
    """
    import eva.llm.router as router_module
    from eva.core import fast_commands

    seen: dict = {}
    real = router_module.complete_with_fallback

    async def fake_complete(messages, settings, *, purpose="planner", **kwargs):
        seen["purpose"] = purpose

        class _R:
            ok = True
            text = "a considered answer"
            model = "deepseek-ai/deepseek-v4-pro-0813"
            error = None

        return _R()

    router_module.complete_with_fallback = fake_complete
    try:
        handled = fast_commands.maybe_handle_fast_command(
            "think: why would this deadlock only under load?", object()
        )
    finally:
        router_module.complete_with_fallback = real
    return seen.get("purpose"), (handled[0] if handled else "")


def drive_prose_is_not_captured() -> None:
    from eva.core.fast_command_think import maybe_handle_think_command

    for message in (
        "think about it",
        "i think we should refactor this",
        "what do you think",
        "thinking out loud here",
        "rethink: the plan",
    ):
        check(
            maybe_handle_think_command(message, message) is None,
            f"ordinary prose {message!r} was captured by the deep-reasoning command",
        )
    for message in ("Think: why", "THINK: why", "deep: why"):
        check(
            maybe_handle_think_command(message.lower(), message) is not None,
            f"{message!r} was NOT captured, so a capitalised first word goes to the LLM instead",
        )


def drive_not_planner_reachable() -> None:
    from eva.tools.registry import ToolRegistry

    names = {spec["name"] for spec in ToolRegistry().planner_specs()}
    for forbidden in ("think", "deep_reasoning", "deep_think"):
        check(
            forbidden not in names,
            f"`{forbidden}` is planner-reachable; a planner able to start a three-minute call "
            "can have an entire errand's wall clock spent for it by untrusted content",
        )


def drive_budget_outlasts_the_measurement() -> None:
    from eva.llm.providers._openai_compatible import timeout_for_purpose
    from eva.llm.providers.nvidia_nim import nvidia_nim_models_for_purpose, nvidia_nim_role_models

    check(
        timeout_for_purpose("deep_reasoning") > MEASURED_SECONDS,
        f"the deep budget is not longer than the measured {MEASURED_SECONDS}s call, so the "
        "caller wired here would be cut off exactly as Phase 104's was",
    )
    check(
        nvidia_nim_models_for_purpose("deep_reasoning")[0] == nvidia_nim_role_models()["deep_reasoning"],
        "requesting the deep purpose no longer selects the deep model",
    )


def main() -> int:
    think = THINK_PY.read_text(encoding="utf-8")
    fast = FAST_PY.read_text(encoding="utf-8")

    # ------------------------------------------------------- source checks
    assert_dispatched_from_the_console(fast)
    # The load-bearing mutation: the handler still EXISTS and still imports, it
    # is simply never called -- which is byte-for-byte the state Phase 104
    # shipped in, and what a check for "the module is present" would miss.
    check_raises(
        lambda: assert_dispatched_from_the_console(fast.replace("think = maybe_handle_think_command(", "unused = (")),
        "the console no longer calling the handler survives the check -- an orphaned capability "
        "is exactly the defect this phase fixes",
    )

    assert_prefix_cannot_swallow_prose(think)
    check_raises(
        lambda: assert_prefix_cannot_swallow_prose(think.replace('"think: "', '"think "')),
        "a bare `think ` prefix survives the check",
    )
    check_raises(
        lambda: assert_prefix_cannot_swallow_prose(
            think.replace("normalized.startswith(prefix)", "original.startswith(prefix)")
        ),
        "matching the raw text survives the check, so a capitalised `Think:` would be missed",
    )

    assert_failures_name_their_reason(think)
    check_raises(
        lambda: assert_failures_name_their_reason(
            think.replace('reason = str(getattr(response, "error", "") or "").strip() or "no reason reported"', 'reason = ""')
        ),
        "a deep-call failure reporting no reason survives the check",
    )

    assert_duration_is_stated_up_front(think)
    check_raises(
        lambda: assert_duration_is_stated_up_front(think.replace("164", "0")),
        "removing the measured duration survives the check",
    )

    # ----------------------------------------------------- driven checks
    purpose, reply = drive_purpose_reaches_the_router()
    check(
        purpose == "deep_reasoning",
        f"a typed `think:` did not request the deep model; the router was asked for {purpose!r}. "
        "The role stayed configured, probed, routable and uncalled.",
    )
    check("a considered answer" in reply, "the deep model's answer did not reach the reply")

    drive_prose_is_not_captured()
    drive_not_planner_reachable()
    drive_budget_outlasts_the_measurement()

    # ---------------------------------------------------------- registration
    import verify_eva_all

    name = "verify_eva_phase106_deep_caller.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 106 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 106 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 106 verifier")

    print(
        "PASS: Phase 106 deep-reasoning caller. Phase 104 made the deep model usable and a grep "
        "for callers then found there were none -- configured, mapped, probed, routable and "
        "requested by nothing, the reachable-by-grep trap for the fourth time in this project "
        "(live_probe, listen_once, app.focus, and this). A typed `think: <question>` now reaches "
        "the router with purpose=deep_reasoning, proven by driving the real console dispatcher "
        "and reading the purpose the router was handed rather than by checking that a function "
        "exists -- which would pass against the build that shipped. Console-only over LATENCY "
        "rather than authority: it answers and cannot act, but it blocks for minutes, so a "
        "planner able to reach it could have an entire errand's wall clock spent for it by "
        "untrusted content. The prefix is colon-terminated so 'think about it' stays prose, and "
        "matched case-insensitively so a capitalised first word is not silently handed to the "
        "LLM; a failed call names the provider's reason, because a blank one is what Phase 104 "
        "existed to remove. Source checks mutation-tested, including the mutation that leaves "
        "the handler present and merely uncalled."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
