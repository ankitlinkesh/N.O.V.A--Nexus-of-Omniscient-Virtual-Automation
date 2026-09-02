"""Phase 91: a clock tool, and two identity commands that stopped swallowing requests.

Two findings from driving the running app.

1. There was no clock among 101 tools, so "what time is it" -- the most ordinary
   question a desktop assistant gets -- had no honest answer. The agent spent a
   `status` call (OS, shell, cwd), found no time in it, and said so; in one live
   run it opened a browser to a time website instead of reading the clock.

2. `_is_about_me_command` and the `ABOUT_EVA_COMMANDS` check matched with
   `command in text`, so any message merely *containing* "about me", "who are
   you" or "what are you" was answered with a canned summary. Every other
   command in that file matches with `normalized in {...}`; these two were the
   exceptions.
"""

from __future__ import annotations

from datetime import datetime

from backend.eva.agent.policies import describe_tool_observation
from backend.eva.core.fast_commands import (
    ABOUT_EVA_COMMANDS,
    ABOUT_ME_COMMANDS,
    _is_about_me_command,
    _is_whole_utterance,
)
from backend.eva.security.action_audit import AUDITED_SAFE_LOCAL_READ, unaudited_safe_local_reads
from backend.eva.security.action_types import ActionType
from backend.eva.tools.registry import ToolRegistry


# --------------------------------------------------------------- the clock tool


def test_system_time_is_registered_and_returns_a_usable_clock():
    result = ToolRegistry().run("system_time")
    assert result["ok"] is True
    for key in ("local_time", "local_time_12h", "local_date", "weekday", "timezone", "iso", "utc_iso"):
        assert str(result.get(key) or "").strip(), key
    # Sanity: the date it reports is today's, not a frozen or epoch value.
    assert result["local_date"] == datetime.now().astimezone().strftime("%Y-%m-%d")


def test_system_time_is_planner_visible():
    """The tool has to be reachable BY THE PLANNER, not merely registered.

    It was registered, audited and referenced from production source -- and the
    model still could not call it, because it was missing from the planner
    whitelist. Live-driving caught that; nothing else did.
    """
    registry = ToolRegistry()
    assert "system_time" in {spec["name"] for spec in registry.planner_specs()}


def test_system_time_is_allow_class_and_explicitly_audited():
    registry = ToolRegistry()
    spec = registry._tools["system_time"]
    assert spec.action_type == ActionType.SAFE_LOCAL_READ.value
    assert spec.requires_confirmation is False
    # Phase 51: SAFE_LOCAL_READ is the dangerous default, so the tool must appear
    # on the explicitly reviewed list rather than inherit auto-allow silently.
    assert "system_time" in AUDITED_SAFE_LOCAL_READ
    assert unaudited_safe_local_reads(registry._tools) == []


def test_system_time_takes_no_arguments():
    schema = ToolRegistry()._tools["system_time"].args_schema
    assert schema.get("properties") == {}
    assert schema.get("additionalProperties") is False


def test_the_observation_carries_the_actual_time():
    """The Phase 89 lesson forward: a result the model cannot read is a re-call."""
    text = describe_tool_observation("system_time", ToolRegistry().run("system_time"))
    now = datetime.now().astimezone()
    assert now.strftime("%A") in text
    assert now.strftime("%Y-%m-%d") in text
    assert ":" in text  # an actual clock reading, not just a date


def test_both_planner_rule_lists_mention_the_clock():
    """Guidance in one prompt only means the agent loop still guesses."""
    import inspect

    from backend.eva.agent import planner

    source = inspect.getsource(planner)
    assert source.count("Use system_time for the current time") == 2


# ------------------------------------------------------- the identity matchers


def test_about_me_still_matches_the_real_question():
    for text in ABOUT_ME_COMMANDS:
        assert _is_about_me_command(text), text
    assert _is_about_me_command("hey eva, what do you know about me?")
    assert _is_about_me_command("Okay, who am I?")


def test_about_me_no_longer_swallows_an_ordinary_request():
    """The live failure: a specific question got the generic about-me dump."""
    assert not _is_about_me_command(
        "how do i like my answers formatted? answer from what you know about me"
    )
    assert not _is_about_me_command("write a paragraph about me for my resume")
    assert not _is_about_me_command("summarise what the reviewer said about me")


def test_the_user_model_phrase_is_reachable_again():
    """"what have you learned about me" has its own branch further down.

    It was dead: "about me" matched as a substring first, so the durable
    user-model summary could never be reached by its own documented phrase.
    """
    assert not _is_about_me_command("what have you learned about me")


def test_about_eva_still_matches_the_real_question():
    for text in ABOUT_EVA_COMMANDS:
        assert _is_whole_utterance(text, ABOUT_EVA_COMMANDS), text
    assert _is_whole_utterance("hey, who are you?", ABOUT_EVA_COMMANDS)


def test_about_eva_no_longer_swallows_an_ordinary_request():
    for text in (
        "who are you calling in this api",
        "explain what are you doing in this function",
        "tell me what are you going to change in the config",
    ):
        assert not _is_whole_utterance(text, ABOUT_EVA_COMMANDS), text


def test_filler_stripping_does_not_reopen_substring_matching():
    """Leading filler is allowed; arbitrary leading CONTENT is not."""
    assert _is_whole_utterance("hey nova who am i", ABOUT_ME_COMMANDS)
    assert not _is_whole_utterance("in the report who am i", ABOUT_ME_COMMANDS)
    assert not _is_whole_utterance("who am i in this org chart", ABOUT_ME_COMMANDS)
