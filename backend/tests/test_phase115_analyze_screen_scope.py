"""Phase 115: `analyze_screen` uploads the window in front, not every display.

The user's decision (2026-09-20). Phase 108 had widened this tool to the whole
desktop for a good reason -- it had been photographing one arbitrary non-primary
monitor -- but the cost was that "what's on my screen?" sent every other app and
display to Google. Measured on this machine: the foreground window is 1129x502
against a 3286x1146 desktop, about 15% of the pixels.

Rules pinned here:
  * with no caller-supplied region, the capture is the foreground window;
  * no window established means REFUSE, never quietly widen to the desktop;
  * the reply names the window that was photographed, so a description of one
    window is not read as a description of the whole screen;
  * a trusted in-process caller (the vision click) still passes its own region.

Nothing is photographed here: the capture and the vision call are both faked.
"""

from __future__ import annotations

import pytest

from backend.eva.screen.capture import CaptureRegion
from backend.eva.tools import registry as registry_module

WINDOW = CaptureRegion(left=100, top=50, width=800, height=600)
DESKTOP = CaptureRegion(left=0, top=0, width=3286, height=1146)


@pytest.fixture()
def fakes(monkeypatch):
    seen: dict = {}

    def fake_capture(region=None):
        seen["region"] = region
        return {
            "ok": True,
            "image_path": "fake.jpg",
            "bytes": 123,
            "region": None if region is None else {"left": region.left, "top": region.top, "width": region.width, "height": region.height},
            "captured_at": "now",
            "note": "fake",
        }

    monkeypatch.setattr(registry_module, "_capture_screen", fake_capture)
    monkeypatch.setattr(registry_module, "analyze_screen_image_sync", lambda path, user_question=None: {"ok": True, "summary": "a description"})
    return seen


def _set_foreground(monkeypatch, region, title="Calculator"):
    import backend.eva.screen.capture as capture_module
    import backend.eva.desktop.windows as windows_module

    monkeypatch.setattr(capture_module, "foreground_window_region", lambda: region)
    monkeypatch.setattr(windows_module, "get_active_window", lambda: type("W", (), {"title": title})())


def test_it_uploads_the_foreground_window_not_the_desktop(fakes, monkeypatch):
    _set_foreground(monkeypatch, WINDOW)
    result = registry_module._analyze_screen(question="what is this?")
    assert fakes["region"] == WINDOW, "the whole desktop must not be sent"
    assert result["capture"]["scope"] == "foreground_window"
    assert result["capture"]["region"]["width"] == 800


def test_the_reply_names_the_window_it_looked_at(fakes, monkeypatch):
    _set_foreground(monkeypatch, WINDOW, title="Calculator")
    result = registry_module._analyze_screen(question="what is this?")
    assert "Calculator" in result["summary"]
    assert result["capture"]["window_title"] == "Calculator"


def test_no_foreground_window_refuses_instead_of_widening(fakes, monkeypatch):
    _set_foreground(monkeypatch, None)
    result = registry_module._analyze_screen(question="what is this?")
    assert result["ok"] is False
    assert result["error"] == "no_foreground_window"
    assert "region" not in fakes, "nothing may be captured when the scope cannot be established"


def test_a_trusted_caller_may_still_pass_its_own_region(fakes, monkeypatch):
    """The vision click scopes to the window it is clicking in (Phase 108)."""
    _set_foreground(monkeypatch, DESKTOP)
    registry_module._analyze_screen(question="where is the button?", region=WINDOW)
    assert fakes["region"] == WINDOW


def test_region_is_still_not_a_planner_argument():
    """A planner must not be able to widen what leaves the machine."""
    from backend.eva.tools.registry import ToolRegistry

    schema = ToolRegistry().get("analyze_screen").args_schema or {}
    assert "region" not in (schema.get("properties") or {})
