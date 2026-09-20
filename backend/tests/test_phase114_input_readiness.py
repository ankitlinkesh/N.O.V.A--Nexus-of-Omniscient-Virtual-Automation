"""Phase 114: typing into a just-launched app can be silently lost.

Found by driving NOVA through real Chrome: "open calculator, type \"9*9=\" into
it, then take a screenshot to check it shows 81" opened Calculator, reported
`screen.type_text` success, and left the display reading **0**.

Measured cause: a UWP window is hosted by ApplicationFrameHost, so it is the
FOREGROUND window ~1.4s before its own process owns the keyboard, and everything
typed in between is swallowed with no error anywhere.

    t=2.17s  foreground = Calculator (ApplicationFrameWindow, pid 13360)
    t=2.78s  keyboard focus  pid 13360   <- frame host
    t=3.57s  keyboard focus  pid 15172   <- CalculatorApp

This ships the part that is measured and safe: wait for keyboard focus to reach
the window's CONTENT process before typing, and record whether it arrived.

WHAT THIS DOES NOT FIX, measured and stated rather than implied: readiness is
necessary but not sufficient. A key pressed at 3.49s (focus already inside the
app) was still swallowed while the one at 3.95s landed, and with the wait in
place a cold start still lost the keystrokes on 3 of 4 rapid relaunches. The
remaining gap is open; see the README row.

No real desktop here: the accessibility layer is faked, so these run anywhere.
"""

from __future__ import annotations

import sys
import types

import pytest

from backend.eva.screen import input_ready


class FakeControl:
    def __init__(self, pid, children=None, handle=0):
        self.ProcessId = pid
        self._children = children or []
        self.NativeWindowHandle = handle

    def GetChildren(self):
        return list(self._children)


def _fake_automation(monkeypatch, *, window, focus_sequence):
    calls = {"focus": 0}

    def get_focused():
        index = min(calls["focus"], len(focus_sequence) - 1)
        calls["focus"] += 1
        return focus_sequence[index]

    module = types.SimpleNamespace(
        ControlFromHandle=lambda handle: window,
        GetFocusedControl=get_focused,
    )
    monkeypatch.setitem(sys.modules, "uiautomation", module)
    monkeypatch.setattr(input_ready.time, "sleep", lambda seconds: None)
    return calls


def test_a_uwp_window_waits_for_its_content_process_to_own_the_keyboard(monkeypatch):
    """The frame host holding focus is NOT readiness, even though it is the window."""
    frame = FakeControl(pid=13360, children=[FakeControl(pid=15172)])
    focus = [FakeControl(pid=13360), FakeControl(pid=13360), FakeControl(pid=15172)]
    calls = _fake_automation(monkeypatch, window=frame, focus_sequence=focus)

    assert input_ready.wait_for_input_ready(1234) is True
    assert calls["focus"] == 3, "it must keep waiting while the frame host holds focus"


def test_an_ordinary_window_is_ready_as_soon_as_focus_is_in_it(monkeypatch):
    window = FakeControl(pid=4242, children=[FakeControl(pid=4242)])
    calls = _fake_automation(monkeypatch, window=window, focus_sequence=[FakeControl(pid=4242)])

    assert input_ready.wait_for_input_ready(1234) is True
    assert calls["focus"] == 1


def test_focus_that_never_arrives_times_out_instead_of_hanging(monkeypatch):
    window = FakeControl(pid=4242, children=[FakeControl(pid=4242)])
    _fake_automation(monkeypatch, window=window, focus_sequence=[FakeControl(pid=999)])

    assert input_ready.wait_for_input_ready(1234, timeout=0.3) is False


def test_it_never_raises_when_the_accessibility_layer_is_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "uiautomation", None)
    assert input_ready.wait_for_input_ready(1234) is False


def test_type_text_waits_for_readiness_and_records_it(monkeypatch):
    """The wait must be ON the typing path, not merely available beside it."""
    from backend.eva.screen import screen_controller

    order: list[str] = []

    class FakeGui:
        FAILSAFE = True
        PAUSE = 0.1

        def write(self, payload, interval=0):
            order.append(f"write:{payload}")

    monkeypatch.setattr(screen_controller, "_pyautogui", lambda: (FakeGui(), None))
    monkeypatch.setattr(screen_controller, "_foreground_handle", lambda: 77)
    monkeypatch.setattr(screen_controller, "_focused_value", lambda: None)

    def fake_wait(handle):
        assert handle == 77
        order.append("wait_ready")
        return True

    monkeypatch.setattr(screen_controller, "_wait_for_focused_window_ready", fake_wait)

    observation = screen_controller.type_text("hello", "phase 114 test")
    assert order == ["wait_ready", "write:hello"], "readiness must be established BEFORE typing"
    assert observation.raw_observation.get("input_ready") is True


def test_capture_screen_tells_the_planner_it_cannot_read_the_image():
    """A text-only planner took a blind capture_screen, learned nothing, then
    spent the rest of the task's screen budget on analyze_screen."""
    from backend.eva.tools.registry import ToolRegistry

    description = ToolRegistry().get("capture_screen").description.lower()
    assert "cannot read" in description
    assert "analyze_screen" in description
