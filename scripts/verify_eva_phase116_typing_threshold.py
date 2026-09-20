"""Standalone verifier for Phase 116 (the cold-start typing loss, closed).

Phase 114 found the cause -- a just-launched window is the foreground window
~1.4s before its own process owns the keyboard -- and shipped a 0.6s settle that
did not close it. Phase 116 measured the cliff instead of guessing:

    delay between "window in front" and first keystroke, clean cold starts
    0.0s -> lost      1.0s -> landed      2.0s -> landed      3.0s -> landed

0.6s sat just under it. 114's 1.2s attempt was measured while relaunching the app
1.5s after killing it, which made every timing worse and got the number blamed
for a bad test setup.

Measured at 1.5s through the real `type_text`: 5/5 clean cold starts, 4/4 rapid
relaunches, warm typing unchanged. End to end through the chat route: "open
calculator, type \"9*9=\" into it, then take a screenshot to check it shows 81"
-> "The calculator shows 81", with Calculator's own display read back as 81.

No real desktop here: the accessibility layer is faked.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

MEASURED_CLIFF_SECONDS = 1.0
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

    def GetChildren(self):
        return list(self._children)


try:
    from eva.screen import input_ready

    failures += emit(
        "the settle clears the measured cliff",
        input_ready._SETTLE_SECONDS >= MEASURED_CLIFF_SECONDS,
        settle=input_ready._SETTLE_SECONDS,
        cliff=MEASURED_CLIFF_SECONDS,
    )

    saved = sys.modules.get("uiautomation")
    real_sleep = input_ready.time.sleep
    slept: list[float] = []
    try:
        frame = FakeControl(13360, [FakeControl(15172)])
        focus = iter([FakeControl(13360), FakeControl(15172)])
        sys.modules["uiautomation"] = types.SimpleNamespace(
            ControlFromHandle=lambda handle: frame, GetFocusedControl=lambda: next(focus)
        )
        input_ready.time.sleep = lambda seconds: slept.append(seconds)
        ready = input_ready.wait_for_input_ready(1234)
        failures += emit(
            "ARRIVAL: the settle is waited once focus is inside the app, not merely declared",
            ready is True and input_ready._SETTLE_SECONDS in slept,
            slept=slept,
        )

        slept.clear()
        window = FakeControl(4242, [FakeControl(4242)])
        sys.modules["uiautomation"] = types.SimpleNamespace(
            ControlFromHandle=lambda handle: window, GetFocusedControl=lambda: FakeControl(999)
        )
        never = input_ready.wait_for_input_ready(1234, timeout=0.4)
        failures += emit(
            "a window that never takes focus fails without paying the settle",
            never is False and input_ready._SETTLE_SECONDS not in slept,
        )
    finally:
        input_ready.time.sleep = real_sleep
        if saved is not None:
            sys.modules["uiautomation"] = saved
        else:
            sys.modules.pop("uiautomation", None)

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    row_114 = readme.split("| 114 |", 1)[1].split("\n", 1)[0] if "| 114 |" in readme else ""
    failures += emit(
        "README records Phase 116 and retires Phase 114's 'not fixed' claim",
        "| 116 |" in readme and "not fixed" not in row_114.lower() and "phase 116" in row_114.lower(),
    )
except Exception as exc:  # pragma: no cover
    failures += emit("behavioural checks ran", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
raise SystemExit(0 if failures == 0 else 1)
