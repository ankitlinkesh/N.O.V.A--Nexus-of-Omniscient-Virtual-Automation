"""Standalone verifier for Phase 91 (a clock tool, and identity commands that stay in their lane).

Two findings from driving the running app, fixed together.

**The clock.** There was no time tool among 101, so "what time is it" -- the most
ordinary question a desktop assistant gets -- had no honest answer. The agent
spent a `status` call (OS, shell, cwd), found no time in it, and said so. In one
live run it opened a browser to a time website rather than read the clock on the
machine it was running on.

Wiring it exposed a real hole in Phase 66's reachability check, worth recording
because Phase 66's own docstring warns about exactly this shape. `system_time`
was registered, audited, count-pinned and *referenced by a production string* (a
`describe_tool_observation` branch), which satisfied Phase 66 -- and the model
still could not call it, because it was missing from `planner_specs()`'s
whitelist. Reachable-by-grep is not reachable-by-planner. Only live-driving
caught it, so this verifier asserts planner visibility by name.

**The identity matchers.** `_is_about_me_command` and the `ABOUT_EVA_COMMANDS`
check used `command in text`, so any message merely *containing* "about me",
"who are you" or "what are you" was answered with a canned summary instead of
being answered. Two consequences, both observed: a real question ("How do I like
my answers formatted? Answer from what you know about me") got the generic
about-me dump, and the `"what have you learned about me"` branch further down
was dead code, because "about me" matched first. Every other command in that
file matches with `normalized in {...}`; these two were the exceptions.

Fully offline: no network call, no LLM, no server.
"""

from __future__ import annotations

import inspect
import sys
from datetime import datetime
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
    from eva.agent import planner as planner_module
    from eva.agent.policies import describe_tool_observation
    from eva.core import fast_commands
    from eva.core.fast_commands import (
        ABOUT_EVA_COMMANDS,
        ABOUT_ME_COMMANDS,
        _is_about_me_command,
        _is_whole_utterance,
    )
    from eva.security.action_audit import AUDITED_SAFE_LOCAL_READ, unaudited_safe_local_reads
    from eva.security.action_types import ActionType
    from eva.tools.registry import ToolRegistry

    registry = ToolRegistry()

    # ------------------------------------------------------------- the clock
    check("system_time" in registry._tools, "system_time is not registered")
    result = registry.run("system_time")
    check(result.get("ok") is True, "system_time did not report ok")
    for key in ("local_time", "local_time_12h", "local_date", "weekday", "timezone", "iso", "utc_iso"):
        check(str(result.get(key) or "").strip(), "system_time returned no %s" % key)
    check(
        result["local_date"] == datetime.now().astimezone().strftime("%Y-%m-%d"),
        "system_time reported %r, which is not today -- a frozen or epoch value" % result["local_date"],
    )

    # THE CHECK THAT LIVE-DRIVING EARNED. Registered, audited and referenced from
    # production source was NOT enough: the planner could not see it.
    planner_visible = {spec["name"] for spec in registry.planner_specs()}
    check(
        "system_time" in planner_visible,
        "system_time is registered but NOT planner-visible, so the model cannot call it and will keep "
        "answering time questions from nothing. Phase 66 passes on a production string reference alone; "
        "that is reachable-by-grep, not reachable-by-planner.",
    )

    spec = registry._tools["system_time"]
    check(
        spec.action_type == ActionType.SAFE_LOCAL_READ.value,
        "system_time must declare SAFE_LOCAL_READ explicitly, not inherit the dangerous default",
    )
    check(spec.requires_confirmation is False, "reading a clock must not need confirmation")
    check(
        "system_time" in AUDITED_SAFE_LOCAL_READ,
        "an auto-allowed tool must appear on the reviewed list (Phase 51)",
    )
    check(unaudited_safe_local_reads(registry._tools) == [], "an unreviewed auto-allow tool slipped in")
    schema = spec.args_schema
    check(
        schema.get("properties") == {} and schema.get("additionalProperties") is False,
        "system_time should take no arguments and say so with a closed schema",
    )

    # The Phase 89 lesson forward: a result the model cannot read is a re-call.
    text = describe_tool_observation("system_time", result)
    now = datetime.now().astimezone()
    check(now.strftime("%A") in text, "the observation drops the weekday")
    check(now.strftime("%Y-%m-%d") in text, "the observation drops the date")
    check(":" in text, "the observation carries no actual clock reading")

    planner_source = inspect.getsource(planner_module)
    check(
        planner_source.count("Use system_time for the current time") == 2,
        "both planner rule lists (single-turn AND bounded agent-step) must mention the clock, or the "
        "agent loop keeps guessing; found %d" % planner_source.count("Use system_time for the current time"),
    )

    # -------------------------------------------------- the identity matchers
    for phrase in ABOUT_ME_COMMANDS:
        check(_is_about_me_command(phrase), "about-me stopped matching its own command %r" % phrase)
    check(_is_about_me_command("hey eva, what do you know about me?"), "leading filler broke the match")
    check(_is_about_me_command("Okay, who am I?"), "trailing punctuation broke the match")

    swallowed = [
        "how do i like my answers formatted? answer from what you know about me",
        "write a paragraph about me for my resume",
        "summarise what the reviewer said about me",
    ]
    for phrase in swallowed:
        check(
            not _is_about_me_command(phrase),
            "REGRESSION: the about-me fast command swallows an ordinary request again: %r" % phrase,
        )

    check(
        not _is_about_me_command("what have you learned about me"),
        "'what have you learned about me' has its own branch further down; matching it here makes that "
        "branch dead code, which is how the durable user-model summary became unreachable by its own phrase",
    )

    for phrase in ABOUT_EVA_COMMANDS:
        check(_is_whole_utterance(phrase, ABOUT_EVA_COMMANDS), "about-eva stopped matching %r" % phrase)
    check(_is_whole_utterance("hey, who are you?", ABOUT_EVA_COMMANDS), "leading filler broke about-eva")
    for phrase in (
        "who are you calling in this api",
        "explain what are you doing in this function",
        "tell me what are you going to change in the config",
    ):
        check(
            not _is_whole_utterance(phrase, ABOUT_EVA_COMMANDS),
            "REGRESSION: the about-eva fast command swallows an ordinary request again: %r" % phrase,
        )

    # Filler is allowed; arbitrary leading CONTENT is not -- else this is just
    # substring matching again with extra steps.
    check(_is_whole_utterance("hey nova who am i", ABOUT_ME_COMMANDS), "filler stripping stopped working")
    for phrase in ("in the report who am i", "who am i in this org chart"):
        check(
            not _is_whole_utterance(phrase, ABOUT_ME_COMMANDS),
            "filler stripping has reopened substring matching: %r" % phrase,
        )

    # Neither matcher may go back to substring matching.
    fc_source = inspect.getsource(fast_commands)
    for needle in ("command in text for command in ABOUT_ME_COMMANDS", "command in normalized for command in ABOUT_EVA_COMMANDS"):
        check(
            needle not in fc_source,
            "REGRESSION: substring matching is back (%r). These sets contain 'about me', 'who are you' and "
            "'what are you', which are substrings of countless ordinary requests." % needle,
        )

    # ---------------------------------------------------------- registration
    import verify_eva_all

    name = "verify_eva_phase91_clock_and_identity_scope.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 91 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 91 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 91 verifier")

    print(
        "PASS: Phase 91 clock and identity scope. `system_time` reads the local clock (allow-class, explicitly "
        "SAFE_LOCAL_READ, on the reviewed auto-allow list, no arguments) and is asserted PLANNER-VISIBLE by name -- "
        "it was registered, audited and referenced from production source while still unreachable by the model, "
        "which Phase 66 could not catch because a string reference is reachable-by-grep, not reachable-by-planner. "
        "Its observation carries the actual reading. Both identity fast commands now match whole utterances instead "
        "of substrings, so 'about me' / 'who are you' / 'what are you' can no longer swallow an ordinary request, "
        "and the 'what have you learned about me' branch they used to shadow is reachable again."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
