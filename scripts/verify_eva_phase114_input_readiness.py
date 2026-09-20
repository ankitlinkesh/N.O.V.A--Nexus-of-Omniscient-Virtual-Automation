"""Standalone verifier for Phase 114 (typing into a just-launched app is lost).

Driving NOVA through real Chrome: "open calculator, type \"9*9=\" into it, then
take a screenshot to check it shows 81" opened Calculator, reported
`screen.type_text` success, and left the display reading 0.

Measured: a UWP window is the FOREGROUND window ~1.4s before its own process
owns the keyboard (frame host pid 13360 at t=2.78s, CalculatorApp pid 15172 at
t=3.57s), and everything typed in between is swallowed silently.

Shipped here: wait for keyboard focus to reach the window's CONTENT process
before typing, and record whether it arrived.

NOT FIXED, and the README says so: readiness is necessary but not sufficient. A
key pressed at 3.49s with focus already inside the app was still swallowed; the
one at 3.95s landed. With the wait in place, a cold start still lost the
keystrokes on 3 of 4 rapid relaunches, and `screen.type_text` still reports
success in that case because Calculator exposes no value pattern to read back.

The accessibility layer is faked here, so this runs with no real desktop.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

failures = 0


def emit(case: str, ok: bool, **extra: object) -> int:
    payload = {"case": case, "pass": bool(ok)}
    payload.update(extra)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if ok else 1


class FakeControl:
    def __init__(self, pid, children=None):
        self.ProcessId = pid
        self._children = children or []
        self.NativeWindowHandle = 0

    def GetChildren(self):
        return list(self._children)


try:
    from eva.screen import input_ready, screen_controller

    real_sleep = input_ready.time.sleep
    input_ready.time.sleep = lambda seconds: None

    def with_fake(window, focus_sequence):
        state = {"i": 0}

        def get_focused():
            control = focus_sequence[min(state["i"], len(focus_sequence) - 1)]
            state["i"] += 1
            return control

        sys.modules["uiautomation"] = types.SimpleNamespace(
            ControlFromHandle=lambda handle: window, GetFocusedControl=get_focused
        )
        return state

    saved_module = sys.modules.get("uiautomation")
    try:
        frame = FakeControl(13360, [FakeControl(15172)])
        state = with_fake(frame, [FakeControl(13360), FakeControl(13360), FakeControl(15172)])
        uwp_ready = input_ready.wait_for_input_ready(1234)
        failures += emit(
            "a UWP window waits for its content process, not the frame host that fronts it",
            uwp_ready is True and state["i"] == 3,
            polls=state["i"],
        )

        plain = FakeControl(4242, [FakeControl(4242)])
        state = with_fake(plain, [FakeControl(4242)])
        failures += emit("an ordinary window is ready as soon as focus is inside it", input_ready.wait_for_input_ready(1234) is True and state["i"] == 1)

        with_fake(plain, [FakeControl(999)])
        failures += emit("focus that never arrives times out rather than hanging", input_ready.wait_for_input_ready(1234, timeout=0.3) is False)

        sys.modules["uiautomation"] = None
        failures += emit("a missing accessibility layer is False, never an exception", input_ready.wait_for_input_ready(1234) is False)
    finally:
        input_ready.time.sleep = real_sleep
        if saved_module is not None:
            sys.modules["uiautomation"] = saved_module
        else:
            sys.modules.pop("uiautomation", None)

    # ARRIVAL: the wait must be on the typing path, before the keystrokes.
    order: list[str] = []

    class FakeGui:
        FAILSAFE = True
        PAUSE = 0.1

        def write(self, payload, interval=0):
            order.append("write")

    originals = (screen_controller._pyautogui, screen_controller._foreground_handle, screen_controller._focused_value, screen_controller._wait_for_focused_window_ready)
    screen_controller._pyautogui = lambda: (FakeGui(), None)
    screen_controller._foreground_handle = lambda: 77
    screen_controller._focused_value = lambda: None
    screen_controller._wait_for_focused_window_ready = lambda handle: order.append("wait") or True
    try:
        observation = screen_controller.type_text("hello", "phase 114 verifier")
    finally:
        (
            screen_controller._pyautogui,
            screen_controller._foreground_handle,
            screen_controller._focused_value,
            screen_controller._wait_for_focused_window_ready,
        ) = originals
    failures += emit(
        "ARRIVAL: typing waits for readiness first and records whether it arrived",
        order == ["wait", "write"] and observation.raw_observation.get("input_ready") is True,
        order=order,
    )

    from eva.tools.registry import ToolRegistry

    description = ToolRegistry().get("capture_screen").description.lower()
    failures += emit(
        "capture_screen tells a text-only planner it cannot read the image",
        "cannot read" in description and "analyze_screen" in description,
    )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    row = readme.split("| 114 |", 1)[1].split("\n", 1)[0] if "| 114 |" in readme else ""
    failures += emit(
        "README records Phase 114 AND that the defect is only mitigated",
        bool(row) and "not fixed" in row.lower(),
    )
except Exception as exc:  # pragma: no cover
    failures += emit("behavioural checks ran", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
raise SystemExit(0 if failures == 0 else 1)
