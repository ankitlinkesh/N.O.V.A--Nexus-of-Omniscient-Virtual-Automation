"""Phase 107 -- vision clicking existed, and could not be reached or believed.

The fallback for apps that publish no accessibility tree shipped in Phase 98 and
was never driven against a real tree-less app. Driving it against a canvas page
whose buttons exist only as pixels found a chain of defects, and they are
different KINDS of defect, so the tests keep them apart:

  1. **Unreachable.** `gui: click the Kestrel button` came back "I don't see a
     Kestrel button among the available click targets" with `0/12 actions used`.
     The planner declined BEFORE calling `screen.click`, because the scaffolding
     presents the control list as exhaustive and tells it to say so rather than
     guess -- which is exactly wrong for the one case the fallback exists for.
     The tool was reachable by grep and unreachable in fact.
  2. **A confident success for an action that did not happen.** `screen.click`
     returned `ok: True` and "Clicked verified UI target Kestrel" while the page
     recorded no click at all. Nothing was verified: a vision target's
     coordinates are asserted by a model, not read from the OS.
  3. **A token cap that ate the answer.** `finishReason: MAX_TOKENS`,
     `thoughtsTokenCount: 861` of a 900 budget -- the reasoning consumed 96% and
     the JSON was cut mid-string, reported as `unparseable_reply`.
  4. **A greedy JSON span.** `re.search(r"\\{.*\\}", DOTALL)` runs from the first
     brace to the LAST one anywhere in a blob joined from five analyzer fields.
     Unlike the other three this one is demonstrated on the exact shapes rather
     than observed failing live -- the live parse failures were the truncation
     and, later, the normaliser that deleted any reply it could not classify.

Defect 2 is the load-bearing one here, and the only one testable without
spending vision quota on a real screen -- which is why it gets the most tests.

What these tests deliberately do NOT cover: the click still did not land. The
cause was measured afterwards, and it is not a defect in this file's subject --
the screenshot covers the PRIMARY monitor (1920x1080) while pyautogui clicks
across the whole virtual desktop (3286x1146), and the target window sat at
x=1912+ on the second display. The model was asked about an image the button was
not in, and asserted a location anyway. Fixing the capture is Phase 108. What
belongs here is that such a click no longer claims to have been verified.
"""

from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
GUI_PY = ROOT / "backend" / "eva" / "core" / "fast_command_gui.py"
VISION_PY = ROOT / "backend" / "eva" / "screen" / "vision_click.py"
SCREEN_VISION_PY = ROOT / "backend" / "eva" / "vision" / "screen_vision.py"


def _target(method: str, confidence: float = 1.0):
    from eva.screen.ui_locator import UiTarget

    return UiTarget(
        target_id=f"{method}:test",
        label="Kestrel",
        role=method,
        x=1125,
        y=349,
        width=0,
        height=0,
        confidence=confidence,
        method=method,
    )


# --------------------------------------------------------------------------
# A guessed click must not be reported as a verified one
# --------------------------------------------------------------------------


@pytest.fixture()
def clicking(monkeypatch):
    """The real click_target, with only the physical click replaced."""
    from eva.agent.action_model import AgentObservation
    from eva.screen import screen_controller

    seen: dict = {}

    def fake_click(x, y, reason, action_id="screen.click"):
        seen["xy"] = (x, y)
        return AgentObservation(action_id=action_id, success=True, raw_observation={}, summary="clicked", error=None)

    monkeypatch.setattr(screen_controller, "click", fake_click)
    return seen


def test_a_vision_click_does_not_claim_to_be_verified(clicking) -> None:
    """Measured live: ok=True and "Clicked verified UI target Kestrel" while the
    page recorded no click at all. Nothing was verified and nothing happened,
    and the reply asserted both."""
    from eva.screen import screen_controller

    obs = screen_controller.click_target(_target("vision"), "phase 107")
    assert obs.success, "a vision click that fired should still report success"
    assert obs.raw_observation["verified_target"] is False
    assert "verified" not in obs.summary.lower().replace("cannot confirm", ""), obs.summary
    assert "cannot confirm" in obs.summary.lower()


def test_a_tree_click_is_still_reported_as_verified(clicking) -> None:
    """The distinction has to cut both ways, or it is just a downgrade. A tree
    target's bounds ARE read from the OS."""
    from eva.screen import screen_controller

    obs = screen_controller.click_target(_target("grounding"), "phase 107")
    assert obs.success
    assert obs.raw_observation["verified_target"] is True
    assert "verified" in obs.summary.lower()


def test_the_vision_summary_says_where_the_location_came_from(clicking) -> None:
    from eva.screen import screen_controller

    obs = screen_controller.click_target(_target("vision"), "phase 107")
    assert "looking at the screen" in obs.summary.lower()


def test_the_click_still_lands_on_the_point_it_was_given(clicking) -> None:
    """Phase 60's double-centering bug must not come back through this path."""
    from eva.screen import screen_controller

    screen_controller.click_target(_target("vision"), "phase 107")
    assert clicking["xy"] == (1125, 349)


# --------------------------------------------------------------------------
# The planner has to be told the control list is not exhaustive
# --------------------------------------------------------------------------


def test_the_scaffolding_admits_the_list_may_be_incomplete() -> None:
    """With vision on, "clicking by label will not work here -- say so rather
    than guessing" is false, and it is what stopped the planner from ever
    calling screen.click on a canvas."""
    source = GUI_PY.read_text(encoding="utf-8")
    assert "vision_click_enabled" in source, "the scaffolding does not know whether vision is on"
    assert "is not always complete" in source
    assert "unlisted_note" in source


def test_the_scaffolding_keeps_its_old_wording_when_vision_is_off() -> None:
    """Without the fallback the old sentence is TRUE, and telling the planner to
    attempt a click that has no second chance would burn actions for nothing."""
    source = GUI_PY.read_text(encoding="utf-8")
    assert "clicking by label will not work here -- say so rather than guessing" in source


def test_the_scaffolding_avoids_screen_wording() -> None:
    """The planner's `_forced_decision` matches screen-request language in the
    GOAL TEXT before any tool list is consulted, so scaffolding that mentions the
    screen makes every GUI task force a cloud vision call."""
    source = GUI_PY.read_text(encoding="utf-8")
    note = source.split("unlisted_note = (", 1)[1].split("if vision_available", 1)[0]
    # The tool name is not screen-request language; the note must be able to say
    # which tool to call.
    note = note.lower().replace("screen.click", "<tool>")
    for word in ("screenshot", "screen"):
        assert word not in note, f"the injected note says {word!r}, which forces a vision call"


# --------------------------------------------------------------------------
# The reply parser
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "blob",
    [
        '```json\n{"found": true, "x": 725, "y": 330, "confidence": 1.0, "description": "Blue"}\n```',
        'summary ```json {"found": true, "x": 725, "y": 330, "confidence": 1.0, "description": "b"} ```  trailing }',
        '{"found": true, "x": 725, "y": 330, "confidence": 1.0, "description": "a"} and later } junk',
        '{"found": true, "x": 725, "y": 330, "confidence": 1.0, "description": "the } button"}',
    ],
)
def test_the_parser_finds_the_object_whatever_surrounds_it(blob: str) -> None:
    """`re.search(r"\\{.*\\}", DOTALL)` is greedy -- first brace to LAST brace --
    and the caller joins five analyzer fields, so one stray brace anywhere made a
    perfectly good reply unparseable."""
    from eva.screen.vision_click import parse_vision_reply

    resolution = parse_vision_reply(blob)
    assert resolution.found, resolution.reason
    assert (resolution.x, resolution.y) == (725, 330)


def test_a_truncated_reply_is_refused_not_salvaged() -> None:
    """The live failure: the model's JSON was cut at `"description":` because
    its own reasoning had eaten the token budget. Refusing is right -- half a
    coordinate pair must never become a click."""
    from eva.screen.vision_click import parse_vision_reply

    resolution = parse_vision_reply('{"found": true, "x": 785, "y": 270, "confidence": 1.0, "description": "Blue rect')
    assert not resolution.found
    assert resolution.reason == "unparseable_reply"


def test_a_reply_with_no_json_is_refused() -> None:
    from eva.screen.vision_click import parse_vision_reply

    assert parse_vision_reply("I cannot see that control anywhere.").reason == "unparseable_reply"


def test_a_negative_answer_is_not_a_parse_failure() -> None:
    """"I looked and it is not there" and "I could not read the reply" are
    different facts, and an operator debugging a refusal needs to know which."""
    from eva.screen.vision_click import parse_vision_reply

    resolution = parse_vision_reply('{"found": false, "confidence": 0, "description": "no such control"}')
    assert not resolution.found
    assert resolution.reason == "model_did_not_find_it"


# --------------------------------------------------------------------------
# The token budget
# --------------------------------------------------------------------------


def test_the_vision_budget_exceeds_the_measured_thinking_cost() -> None:
    """Measured: thoughtsTokenCount=861 of a 900 cap, leaving 35 for the answer,
    which cut the JSON mid-string. The cap bounds thinking PLUS answer, and 900
    was sized as though it bounded only the answer."""
    import re

    source = SCREEN_VISION_PY.read_text(encoding="utf-8")
    match = re.search(r'"maxOutputTokens":\s*(\d+)', source)
    assert match is not None, "the vision request has no output cap at all"
    assert int(match.group(1)) >= 1800, (
        f"maxOutputTokens is {match.group(1)}, which leaves too little after a measured "
        "861 tokens of reasoning; the reply gets cut mid-JSON and reads as a parse failure"
    )
