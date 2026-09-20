"""Is the focused window actually ready to receive keystrokes yet?

Phase 114. Driving NOVA through real Chrome, "open calculator, type \"9*9=\" into
it" opened Calculator, typed, and left the display reading **0**. Every check
passed: the window existed (`app_window_open` verified), it was the foreground
window, and `screen.type_text` reported success. The keystrokes went nowhere.

Measured on a cold start (the app had just been launched):

    t=2.17s  foreground window  = Calculator, ApplicationFrameWindow, pid 13360
    t=2.78s  KEYBOARD focus     = pid 13360   <- the frame host, not the app
    t=3.57s  KEYBOARD focus     = pid 15172   <- CalculatorApp itself
    typing after that           -> "Display is 81"

A UWP window is hosted by `ApplicationFrameHost`, so for ~1.4s after it comes to
the front the frame owns the keyboard and anything typed is swallowed. Earlier
phases only ever typed into an app that was ALREADY running, which is why this
never showed up: warm, typing lands with zero delay (measured at 0.0s, 0.3s and
0.8s, all correct).

So the readiness signal is not "the window is in front" and not a sleep long
enough to look safe: it is **keyboard focus belonging to the process that draws
the window's content**. For an ordinary Win32 app that process is the window's
own, so this returns immediately; for a UWP app it is the child process inside
the frame. Bounded, and fail-closed: a caller that cannot establish readiness
must not type, because dropped keystrokes are invisible to everyone.
"""

from __future__ import annotations

import time

DEFAULT_TIMEOUT_SECONDS = 5.0
_POLL_SECONDS = 0.15
# Keyboard focus reaching the app's process is necessary but NOT sufficient:
# measured on a cold Calculator, focus was inside the app at 3.49s and the key
# pressed then was still swallowed, while the one at 3.95s landed. So this adds a
# settle after the focus signal.
#
# Phase 116 measured the threshold instead of guessing at it. Sweeping the delay
# between "the window is in front" and the first keystroke, on clean cold starts:
#
#     0.0s -> lost      1.0s -> landed      2.0s -> landed      3.0s -> landed
#
# Phase 114 had picked 0.6s, just under the cliff, which is why it still lost the
# keys; and its 1.2s attempt was measured during rapid relaunches (a kill 1.5s
# earlier) that made every timing worse, so the number was blamed when the test
# setup was at fault. At 1.5s: 5/5 clean cold starts, 4/4 rapid relaunches, and
# warm typing unchanged. It is still a measured margin over an observed cliff,
# not a guarantee -- which is why the readback in screen_controller stays.
_SETTLE_SECONDS = 1.5


def _content_process_id(automation, hwnd: int) -> int | None:
    """The pid that owns what is drawn inside `hwnd`.

    For a UWP window this is the child process inside the ApplicationFrameHost
    frame; for a normal window it is the window's own process.
    """
    window = automation.ControlFromHandle(hwnd)
    if window is None:
        return None
    for child in window.GetChildren():
        if child.ProcessId and child.ProcessId != window.ProcessId:
            return int(child.ProcessId)
    return int(window.ProcessId) if window.ProcessId else None


def wait_for_input_ready(hwnd: int, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> bool:
    """True once keyboard focus is inside `hwnd`'s content process.

    False on timeout or when the accessibility layer is unavailable -- the
    caller then declines to type rather than typing into a window that is not
    listening. Never raises.
    """
    try:
        import uiautomation as automation
    except Exception:
        return False

    try:
        from .dpi import ensure_dpi_aware

        ensure_dpi_aware()
    except Exception:
        pass

    deadline = time.monotonic() + max(0.0, float(timeout))
    try:
        content_pid = _content_process_id(automation, int(hwnd))
    except Exception:
        return False
    if not content_pid:
        return False

    while True:
        try:
            focused = automation.GetFocusedControl()
            if focused is not None and int(focused.ProcessId or 0) == content_pid:
                time.sleep(_SETTLE_SECONDS)
                return True
        except Exception:
            return False
        if time.monotonic() >= deadline:
            return False
        time.sleep(_POLL_SECONDS)
