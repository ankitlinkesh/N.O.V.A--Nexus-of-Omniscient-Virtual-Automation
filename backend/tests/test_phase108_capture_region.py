"""Phase 108 -- the vision click took TWO screenshots and mixed up their geometry.

Phase 107 shipped a row saying the click missed because the capture covered only
the primary monitor, so "the target was never in the picture". Re-measured, that
was **wrong**, and this phase retires it. The target WAS in the picture and the
model located it correctly. What went wrong was arithmetic:

  * `screen/capture.py` grabbed `mss().monitors[1]` -- the image sent to Gemini;
  * `locate_by_vision` separately called a bare `ImageGrab.grab()` purely to ask
    "how big is the screen", and handed THOSE dimensions to `to_target`;
  * `to_target` scaled the model's 0-1000 grid onto them and added no origin.

Two grabs, two different regions, one's coordinates applied to the other. On the
machine this was measured on, `monitors[1]` is 1366x768 at (1920, 378) while
`ImageGrab.grab()` is 1920x1080 at (0, 0), so a correct answer about a window on
the second display was converted into a point on the first one.

`monitors[1]` is also not the primary monitor. mss enumerates in
EnumDisplayMonitors order: here `monitors[1]` reports `is_primary: False` and the
real primary is `monitors[2]`. The function was named `capture_primary_screen_jpeg`.

The fix is that a screenshot now carries the region it came from, so a position
inside an image can be turned back into a position on screen by the only code
that knows both. The second grab is gone.

A size alone cannot do this -- that is the whole point, and it is why
`CaptureRegion` exists rather than a `(width, height)` tuple.
"""

from __future__ import annotations

import pytest

from backend.eva.screen.capture import CaptureRegion
from backend.eva.screen.vision_click import VisionResolution, locate_by_vision, to_target


# --------------------------------------------------------------------------
# A position in an image only becomes a position on screen with an origin
# --------------------------------------------------------------------------


def test_the_origin_is_applied_to_the_click_point() -> None:
    """The Phase 107 failure, in one assertion. A control in the middle of a
    window on the second display is at that window's coordinates, not at the
    same offset from (0, 0)."""
    region = CaptureRegion(left=1920, top=378, width=1366, height=768)
    resolution = VisionResolution(found=True, x=500, y=500, confidence=1.0, description="button")

    target = to_target(resolution, query="button", region=region)

    assert target is not None
    assert target.x == 1920 + 683, "the region's left edge was not added"
    assert target.y == 378 + 384, "the region's top edge was not added"


def test_a_grid_answer_scales_to_the_region_not_to_the_screen() -> None:
    """The model answers about the IMAGE it was shown. A 1366-wide image and a
    1920-wide screen give different pixels for the same grid position, and the
    image is the one that is true."""
    narrow = to_target(
        VisionResolution(found=True, x=250, y=0, confidence=1.0),
        query="q",
        region=CaptureRegion(0, 0, 1366, 768),
    )
    wide = to_target(
        VisionResolution(found=True, x=250, y=0, confidence=1.0),
        query="q",
        region=CaptureRegion(0, 0, 1920, 1080),
    )
    assert narrow is not None and wide is not None
    assert narrow.x == 341
    assert wide.x == 480


def test_the_origin_is_not_folded_into_the_bounds_check() -> None:
    """An answer at the far edge of the image is in-bounds; the same NUMBER
    treated as a screen coordinate might not be. The check has to run in image
    space, before the offset."""
    region = CaptureRegion(left=1920, top=378, width=1366, height=768)
    target = to_target(
        VisionResolution(found=True, x=999, y=999, confidence=1.0), query="q", region=region
    )
    assert target is not None
    assert target.x == 1920 + 1364
    assert target.y == 378 + 767


@pytest.mark.parametrize("region", [CaptureRegion(0, 0, 0, 0), CaptureRegion(10, 10, 0, 500), None])
def test_a_region_with_no_area_yields_no_target(region) -> None:
    """Degenerate geometry must decline, not divide by zero and not click (0,0)."""
    resolution = VisionResolution(found=True, x=500, y=500, confidence=1.0)
    assert to_target(resolution, query="q", region=region) is None


# --------------------------------------------------------------------------
# The region must come from the capture that produced the image
# --------------------------------------------------------------------------


def test_the_region_is_read_from_the_analyzer_result() -> None:
    """This is the structural fix. The region travels WITH the image, reported by
    the same call that captured it, so there is no second grab to disagree with."""
    def analyzer(_prompt: str, _ctx: str) -> dict:
        return {
            "ok": True,
            "summary": '{"found": true, "x": 500, "y": 500, "confidence": 1.0, "description": "b"}',
            "capture": {"region": {"left": 1920, "top": 378, "width": 1366, "height": 768}},
        }

    target, report = locate_by_vision("button", analyzer=analyzer)

    assert report.found, report.reason
    assert target is not None
    assert (target.x, target.y) == (1920 + 683, 378 + 384)


def test_a_reply_without_a_region_is_refused_not_guessed() -> None:
    """Guessing a geometry does not fail loudly -- it clicks somewhere else. That
    is the entire failure mode of this phase, so the absence of a region has to
    be a refusal."""
    def analyzer(_prompt: str, _ctx: str) -> dict:
        return {
            "ok": True,
            "summary": '{"found": true, "x": 500, "y": 500, "confidence": 1.0, "description": "b"}',
        }

    target, report = locate_by_vision("button", analyzer=analyzer)

    assert target is None
    assert report.reason == "no_capture_region"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        {},
        {"left": 0, "top": 0, "width": 0, "height": 0},
        {"left": 0, "top": 0, "width": "wide", "height": 10},
        {"top": 0, "width": 10, "height": 10},
        "1920x1080",
    ],
)
def test_an_unusable_region_payload_is_rejected(raw) -> None:
    assert CaptureRegion.from_dict(raw) is None


def test_a_usable_region_payload_round_trips() -> None:
    region = CaptureRegion(1920, 378, 1366, 768)
    assert CaptureRegion.from_dict(region.as_dict()) == region


# --------------------------------------------------------------------------
# Scope: only the window being automated is photographed
# --------------------------------------------------------------------------


def test_an_off_screen_region_is_trimmed_to_what_exists(monkeypatch) -> None:
    """A window can hang off the edge of the desktop. Grabbing the requested rect
    and REPORTING it would put the origin arithmetic back out by the overhang, in
    exactly the case the origin is there to handle."""
    from backend.eva.screen import capture as capture_mod

    monkeypatch.setattr(capture_mod, "virtual_desktop_region", lambda: CaptureRegion(0, 0, 3286, 1146))
    clamped = capture_mod.clamp_to_desktop(CaptureRegion(left=1912, top=370, width=1382, height=784))

    assert clamped == CaptureRegion(1912, 370, 1374, 776), "measured live: the window overhangs by 8px"


def test_a_region_entirely_off_screen_is_none(monkeypatch) -> None:
    from backend.eva.screen import capture as capture_mod

    monkeypatch.setattr(capture_mod, "virtual_desktop_region", lambda: CaptureRegion(0, 0, 1920, 1080))
    assert capture_mod.clamp_to_desktop(CaptureRegion(left=5000, top=0, width=100, height=100)) is None


def test_the_vision_path_refuses_rather_than_photographing_everything(monkeypatch) -> None:
    """If the foreground window cannot be established, widening to the whole
    desktop would send every open window to a cloud API to find one button.
    Phase 108 measured that cost live -- a desktop-wide grab taken during this
    phase's own validation swept up an unrelated video call -- so the fallback is
    refusal, not a bigger screenshot."""
    from backend.eva.screen import vision_click as vision_mod

    monkeypatch.setattr(vision_mod, "foreground_window_region", lambda: None)

    target, report = locate_by_vision("button", analyzer=None)

    assert target is None
    assert report.reason == "no_window_region"


def test_the_capture_scope_is_not_a_planner_argument() -> None:
    """`region` narrows what leaves the machine, so it is set by trusted
    in-process callers only. If it were in the tool's args_schema a planner --
    steered by untrusted content -- could widen the shot."""
    from backend.eva.tools.registry import ToolRegistry

    spec = ToolRegistry()._tools["analyze_screen"]
    schema = spec.args_schema or {}
    assert "region" not in (schema.get("properties") or {})
    assert schema.get("additionalProperties") is not True
