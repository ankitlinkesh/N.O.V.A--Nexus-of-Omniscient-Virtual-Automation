"""Phase 106 -- the deep model finally has a caller.

Phase 104 fixed the 12-second request timeout that made `deep_reasoning`
impossible to use, then a grep for callers found there were none: the role was
configured, probed, routable, and requested by nothing. That is the
reachable-by-grep trap this project has now hit four times -- `doctor.live_probe`
(92), `listen_once` (61), `app.focus` (64), and now this. A capability nothing
invokes is not a capability, so the check that matters is that a real console
message reaches the deep purpose, not that a function exists.

Console-only, and for a reason worth keeping straight: LATENCY, not authority.
The call blocks for minutes and carries no tool power at all, so what is kept
away from the planner is the ability to burn an entire errand's wall clock -- and
to be steered into doing so by untrusted content -- not a permission.
"""

from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
THINK_PY = ROOT / "backend" / "eva" / "core" / "fast_command_think.py"


# --------------------------------------------------------------------------
# The purpose actually reaches the router
# --------------------------------------------------------------------------


def test_a_typed_think_command_routes_with_the_deep_purpose(monkeypatch) -> None:
    """The check that would have caught the gap.

    "the module defines _run_deep" passes against a build nothing calls. This
    drives the console dispatcher and reads the purpose the ROUTER was handed.
    """
    from eva.core import fast_commands

    seen: dict = {}

    async def fake_complete(messages, settings, *, purpose="planner", **kwargs):
        seen["purpose"] = purpose
        seen["max_tokens"] = kwargs.get("max_tokens")

        class _R:
            ok = True
            text = "a considered answer"
            model = "deepseek-ai/deepseek-v4-pro-0813"
            error = None

        return _R()

    monkeypatch.setattr("eva.llm.router.complete_with_fallback", fake_complete)
    handled = fast_commands.maybe_handle_fast_command(
        "think: why would this deadlock only under load?", object()
    )
    assert handled is not None, "the console did not route `think:` anywhere"
    assert seen.get("purpose") == "deep_reasoning", (
        f"the deep model was not requested; purpose was {seen.get('purpose')!r}"
    )
    assert "a considered answer" in handled[0]


def test_the_deep_purpose_selects_the_deep_model() -> None:
    """Requesting the purpose is only useful if the purpose picks the model."""
    from eva.llm.providers.nvidia_nim import nvidia_nim_models_for_purpose, nvidia_nim_role_models

    assert nvidia_nim_models_for_purpose("deep_reasoning")[0] == nvidia_nim_role_models()["deep_reasoning"]


def test_the_deep_purpose_gets_a_budget_long_enough_to_finish() -> None:
    """Measured: 164s for a one-line prompt, 200s for a real question. A caller
    wired to a budget shorter than that would be Phase 104 all over again."""
    from eva.llm.providers._openai_compatible import timeout_for_purpose

    assert timeout_for_purpose("deep_reasoning") > 200


# --------------------------------------------------------------------------
# It must not start swallowing ordinary prose
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "think about it",
        "i think we should refactor this",
        "what do you think",
        "rethink: the plan",
        "thinking out loud here",
    ],
)
def test_ordinary_prose_is_not_captured(message: str) -> None:
    """A refactor that STARTS handling a phrase is as much a regression as one
    that stops. "think about it" is something a person types."""
    from eva.core.fast_command_think import maybe_handle_think_command

    assert maybe_handle_think_command(message, message) is None


@pytest.mark.parametrize("message", ["think: why", "deep: why", "think : why", "THINK: why"])
def test_the_colon_form_is_captured(message: str, monkeypatch) -> None:
    from eva.core import fast_command_think

    monkeypatch.setattr(fast_command_think, "_run_deep", lambda question: f"answered:{question}")
    handled = fast_command_think.maybe_handle_think_command(message.lower(), message)
    assert handled is not None
    assert handled[1] == "fast-command"


def test_an_empty_question_asks_rather_than_calling(monkeypatch) -> None:
    from eva.core import fast_command_think

    called: list[str] = []
    monkeypatch.setattr(fast_command_think, "_run_deep", lambda question: called.append(question) or "x")
    handled = fast_command_think.maybe_handle_think_command("think:", "think:")
    assert not called, "an empty question started a three-minute call"


# --------------------------------------------------------------------------
# Not planner-reachable, and honest about what it costs
# --------------------------------------------------------------------------


def test_the_deep_model_is_not_a_planner_tool() -> None:
    """Not a permission boundary -- a latency one. A planner able to reach this
    could spend an entire errand's wall clock on one step, and untrusted content
    that steers it there is a cheap denial of service."""
    from eva.tools.registry import ToolRegistry

    names = {spec["name"] for spec in ToolRegistry().planner_specs()}
    for forbidden in ("think", "deep_reasoning", "deep_think"):
        assert forbidden not in names


def test_status_states_the_measured_duration() -> None:
    """The first use of a three-minute call is indistinguishable from a hang
    unless something said so first."""
    from eva.core.fast_command_think import maybe_handle_think_command

    report = maybe_handle_think_command("think status", "think status")[0]
    assert "164" in report
    assert "deepseek" in report.lower()


def test_a_failure_names_its_reason(monkeypatch) -> None:
    """Phase 104 exists because a failure here arrived as the empty string.
    Reporting "it didn't work" without the reason would put that straight back."""
    from eva.core import fast_command_think

    async def failing(messages, settings, *, purpose="planner", **kwargs):
        class _R:
            ok = False
            text = ""
            model = "deepseek-ai/deepseek-v4-pro-0813"
            error = "ReadTimeout: no response within 240s"

        return _R()

    monkeypatch.setattr("eva.llm.router.complete_with_fallback", failing)
    reply = fast_command_think._run_deep("why?")
    assert "ReadTimeout" in reply
    assert "240s" in reply


def test_the_console_prefix_is_colon_terminated() -> None:
    source = THINK_PY.read_text(encoding="utf-8")
    assert '"think: "' in source
    assert '"think "' not in source, (
        "a bare `think ` prefix would swallow ordinary prose like 'think about it'"
    )
