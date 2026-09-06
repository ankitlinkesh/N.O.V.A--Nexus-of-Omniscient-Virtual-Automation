"""Phase 98: clicking by LOOKING, for apps with no accessibility tree.

Phases 56-60 click by walking the UIAutomation tree and matching a control's
accessible name -- exact, local, cheap, and blind to Electron apps, canvas UIs
and games, which expose no named controls. Those are also the apps where there is
no shell command to fall back on, which is why this exists.

It gives up two properties the GUI arc was built on, so the tests below are
mostly about keeping it boxed in:

  * a screenshot of the whole screen leaves the machine (Google Gemini), where
    the tree path sends nothing anywhere;
  * coordinates are ASSERTED by a model rather than measured from the OS, and a
    confident wrong guess looks exactly like a right one.

Hence: never first (tree declines before vision is consulted), never silent (two
independent switches, one of them a human typing `gui:`), never unbounded
(off-grid answers rejected rather than clamped), and it declines like the tree
does rather than guessing.
"""

from __future__ import annotations

import pytest

from backend.eva.screen.capture import CaptureRegion
from backend.eva.screen.vision_click import (
    DEFAULT_VISION_CONFIDENCE,
    build_prompt,
    locate_by_vision,
    parse_vision_reply,
    to_target,
    vision_click_enabled,
)


# Phase 108: to_target now takes the region an image came FROM, not just its
# size, because a position in an image only becomes a screen position with an
# origin. Origin (0,0) keeps these cases reading as they did.
_REGION = CaptureRegion(0, 0, 1920, 1080)


# --------------------------------------------------------------- the switches


def test_vision_is_off_by_default():
    assert vision_click_enabled({}) is False
    assert vision_click_enabled({"EVA_VISION_CLICK_ENABLED": ""}) is False
    for off in ("0", "false", "no", "off"):
        assert vision_click_enabled({"EVA_VISION_CLICK_ENABLED": off}) is False


def test_vision_turns_on_explicitly():
    for on in ("1", "true", "yes", "on"):
        assert vision_click_enabled({"EVA_VISION_CLICK_ENABLED": on}) is True


def test_the_click_path_requires_both_switches(monkeypatch):
    """The flag alone must not be enough.

    A persistent flag on its own would mean any planner-reachable path could
    eventually send a screenshot to Google. Requiring an open GUI scope means a
    person typed `gui:` for this specific task.
    """
    from backend.eva.screen import screen_tools

    monkeypatch.setenv("EVA_VISION_CLICK_ENABLED", "1")
    # Flag on, but no scope open.
    target, report = screen_tools._try_vision_fallback("Play", 0.75)
    assert target is None and report is None, "vision must not be consulted outside a GUI scope"


def test_vision_is_not_consulted_when_the_flag_is_off(monkeypatch):
    from backend.eva.screen import screen_tools
    from backend.eva.screen.gui_scope import open_gui_scope

    monkeypatch.delenv("EVA_VISION_CLICK_ENABLED", raising=False)
    with open_gui_scope("x"):
        target, report = screen_tools._try_vision_fallback("Play", 0.75)
    assert target is None and report is None


# ------------------------------------------------------ refusing, not guessing


def test_a_model_that_cannot_see_it_yields_no_target():
    resolution = parse_vision_reply('{"found": false, "description": "no such button"}')
    assert resolution.found is False
    assert resolution.reason == "model_did_not_find_it"
    assert to_target(resolution, query="q", region=_REGION) is None


@pytest.mark.parametrize(
    "reply", ["not json at all", "", "{broken", '{"found": true}', '{"found": true, "x": "left", "y": 3}']
)
def test_a_malformed_reply_is_a_refusal(reply):
    resolution = parse_vision_reply(reply)
    assert resolution.found is False
    assert to_target(resolution, query="q", region=_REGION) is None


def test_off_grid_coordinates_are_rejected_not_clamped():
    """Clamping would turn a model that misunderstood the question into a click."""
    resolution = parse_vision_reply('{"found": true, "x": 5000, "y": 20, "confidence": 1.0}')
    assert resolution.found is False
    assert resolution.reason == "coordinates_out_of_range"


def test_low_confidence_declines():
    resolution = parse_vision_reply('{"found": true, "x": 10, "y": 10, "confidence": 0.4}')
    assert resolution.found is True, "the model answered; it is the FLOOR that refuses"
    assert to_target(resolution, query="q", region=_REGION) is None


def test_the_vision_floor_is_higher_than_the_tree_floor():
    """A tree match at 0.75 is a real control that scored imperfectly.

    A vision match at 0.75 is a model unsure where something is -- a different
    and worse kind of uncertain, so it does not get the same floor.
    """
    assert DEFAULT_VISION_CONFIDENCE > 0.75


# --------------------------------------------------------------- the geometry


def test_normalised_coordinates_scale_to_the_screen():
    resolution = parse_vision_reply('{"found": true, "x": 500, "y": 250, "confidence": 0.9}')
    target = to_target(resolution, query="play", region=_REGION)
    assert target is not None
    assert (target.x, target.y) == (960, 270)


def test_a_degenerate_screen_size_yields_no_target():
    resolution = parse_vision_reply('{"found": true, "x": 500, "y": 500, "confidence": 0.9}')
    assert to_target(resolution, query="q", region=CaptureRegion(0, 0, 0, 0)) is None


def test_a_vision_target_is_labelled_as_seen_not_measured():
    """Nothing downstream may mistake a model's guess for a measured control."""
    resolution = parse_vision_reply('{"found": true, "x": 1, "y": 1, "confidence": 0.99, "description": "blue Play"}')
    target = to_target(resolution, query="play", region=CaptureRegion(0, 0, 100, 100))
    assert target is not None
    assert target.method == "vision"
    assert target.role == "vision"
    assert "seen" in target.label


# ------------------------------------------------------------- the prompt


def test_the_prompt_offers_an_explicit_refusal():
    """A model asked only "where is X" will invent a location for an absent X."""
    prompt = build_prompt("the Play button")
    assert '"found": false' in prompt
    assert "rather than guess" in prompt
    assert "centre" in prompt.lower()


def test_the_prompt_does_not_ask_for_the_screen_contents():
    """It is a locator, not a reader: it must not invite transcription."""
    assert "beyond the control asked for" in build_prompt("x")


# ------------------------------------------------- end to end, injected


def test_locate_by_vision_returns_a_target_without_touching_a_screen():
    def analyzer(prompt, _):
        assert "Find: the Play button" in prompt
        return {"ok": True, "summary": '{"found": true, "x": 250, "y": 500, "confidence": 0.95, "description": "Play"}'}

    target, report = locate_by_vision(
        "the Play button", analyzer=analyzer, region=CaptureRegion(0, 0, 800, 600)
    )
    assert report.found is True
    assert target is not None and (target.x, target.y) == (200, 300)


def test_a_failing_analyzer_declines_rather_than_raising():
    def analyzer(prompt, _):
        raise RuntimeError("network down")

    target, report = locate_by_vision("x", analyzer=analyzer, region=CaptureRegion(0, 0, 800, 600))
    assert target is None
    assert report.found is False
    assert "vision_error" in report.reason


def test_an_analyzer_reporting_failure_declines():
    target, report = locate_by_vision(
        "x", analyzer=lambda p, _: {"ok": False, "error": "gemini_vision_http_429"},
        region=CaptureRegion(0, 0, 800, 600),
    )
    assert target is None and report.reason == "gemini_vision_http_429"


# ------------------------------------------------------ typing safe data only


def test_typing_refuses_a_live_secret(monkeypatch):
    """Secrets have their own route; this tool types safe data only."""
    from backend.eva.screen import screen_tools

    monkeypatch.setenv("EVA_TEST_FAKE_SECRET", "sk-live-abcdef123456")
    monkeypatch.setattr(
        "backend.eva.privacy.secrets_broker.contains_secret_leak",
        lambda text, environ=None: "sk-live-abcdef123456" in str(text),
    )
    result = screen_tools.screen_type_text("my key is sk-live-abcdef123456", reason="test")
    assert result["ok"] is False
    assert result["error"] == "secret_value_refused"
    # The refusal must not echo the secret back.
    assert "sk-live-abcdef123456" not in str(result)


def test_typing_ordinary_text_is_not_blocked(monkeypatch):
    from backend.eva.screen import screen_tools

    monkeypatch.setattr(
        "backend.eva.privacy.secrets_broker.contains_secret_leak", lambda text, environ=None: False
    )
    captured = {}

    class _Obs:
        success = True

        def as_dict(self):
            return {"action": "type"}

    monkeypatch.setattr(
        screen_tools.screen_controller,
        "type_text_visible",
        lambda text, reason: captured.update(text=text) or _Obs(),
    )
    result = screen_tools.screen_type_text("hello world", reason="test")
    assert result["ok"] is True
    assert captured["text"] == "hello world"
