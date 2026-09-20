"""Phase 116: the cold-start typing loss, closed by measuring the cliff.

Phase 114 found the cause (a just-launched window is in front ~1.4s before its
own process owns the keyboard) and shipped a 0.6s settle that did NOT close it.
Phase 116 measured the threshold instead of guessing, sweeping the delay between
"the window is in front" and the first keystroke on clean cold starts:

    0.0s -> lost      1.0s -> landed      2.0s -> landed      3.0s -> landed

0.6s sat just under the cliff. 114's 1.2s attempt was measured while relaunching
the app 1.5s after killing it, which made every timing worse and got the number
blamed for a bad test setup.

At 1.5s, measured through the real `type_text`: 5/5 clean cold starts, 4/4 rapid
relaunches, warm typing unchanged and still correct. End to end through the chat
route, the errand that started all of this -- "open calculator, type \"9*9=\"
into it, then take a screenshot to check it shows 81" -- now answers "The
calculator shows 81" with Calculator's own display reading 81.

These tests pin the margin and that the wait actually happens before the keys.
"""

from __future__ import annotations

import sys
import types

import pytest

from backend.eva.screen import input_ready

# The measured cliff: below this, a cold-started window swallowed the keystrokes.
MEASURED_CLIFF_SECONDS = 1.0


def test_the_settle_clears_the_measured_cliff():
    assert input_ready._SETTLE_SECONDS >= MEASURED_CLIFF_SECONDS, (
        "0.6s sat under the measured cliff and lost keystrokes; the settle must clear it"
    )


def test_the_settle_is_actually_waited_after_focus_arrives(monkeypatch):
    """The margin must be spent on the typing path, not merely declared."""
    slept: list[float] = []

    class FakeControl:
        def __init__(self, pid, children=None):
            self.ProcessId = pid
            self._children = children or []

        def GetChildren(self):
            return list(self._children)

    frame = FakeControl(13360, [FakeControl(15172)])
    focus = iter([FakeControl(13360), FakeControl(15172)])
    monkeypatch.setitem(
        sys.modules,
        "uiautomation",
        types.SimpleNamespace(ControlFromHandle=lambda handle: frame, GetFocusedControl=lambda: next(focus)),
    )
    monkeypatch.setattr(input_ready.time, "sleep", lambda seconds: slept.append(seconds))

    assert input_ready.wait_for_input_ready(1234) is True
    assert input_ready._SETTLE_SECONDS in slept, "the settle must be waited once focus is inside the app"


def test_a_window_that_never_takes_focus_does_not_get_the_settle(monkeypatch):
    """Waiting the margin on a window that never becomes ready would only delay
    an honest failure."""
    slept: list[float] = []

    class FakeControl:
        def __init__(self, pid, children=None):
            self.ProcessId = pid
            self._children = children or []

        def GetChildren(self):
            return list(self._children)

    window = FakeControl(4242, [FakeControl(4242)])
    monkeypatch.setitem(
        sys.modules,
        "uiautomation",
        types.SimpleNamespace(ControlFromHandle=lambda handle: window, GetFocusedControl=lambda: FakeControl(999)),
    )
    monkeypatch.setattr(input_ready.time, "sleep", lambda seconds: slept.append(seconds))

    assert input_ready.wait_for_input_ready(1234, timeout=0.4) is False
    assert input_ready._SETTLE_SECONDS not in slept
