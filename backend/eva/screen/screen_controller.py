from __future__ import annotations

import os
import time
from typing import Any

from ..agent.action_model import AgentObservation
from .ui_locator import UiTarget


def _obs(action_id: str, success: bool, summary: str, raw: dict[str, Any] | None = None, error: str | None = None) -> AgentObservation:
    return AgentObservation(action_id=action_id, success=success, raw_observation=raw or {}, summary=summary, error=error)


def real_input_enabled() -> bool:
    """Real pyautogui-backed mouse/keyboard control is opt-in.

    Even with pyautogui installed, physical input is only performed when
    EVA_ENABLE_REAL_INPUT is truthy. This keeps the default (and the whole
    verifier/test suite) inert so nothing moves the real cursor unexpectedly;
    the operator opts in explicitly when they want Eva to have hands.
    """
    raw = os.environ.get("EVA_ENABLE_REAL_INPUT")
    if raw is None:
        return False
    # Empty string counts as off too: a physical-input gate must fail safe, so
    # only an explicit truthy value hands Eva the mouse and keyboard.
    return raw.strip().lower() not in {"", "0", "false", "no", "off"}


def _pyautogui():
    if not real_input_enabled():
        return None, "real input disabled (set EVA_ENABLE_REAL_INPUT=1 to enable pyautogui-backed control)"
    try:
        # Coordinates only line up if this process is DPI-aware (see dpi.py).
        from .dpi import ensure_dpi_aware

        ensure_dpi_aware()
        import pyautogui  # type: ignore

        # Slam the cursor into any screen corner to abort; small pause between actions.
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1
        return pyautogui, None
    except Exception as exc:
        return None, str(exc)


def click(x: int, y: int, reason: str, action_id: str = "screen.click") -> AgentObservation:
    if not str(reason or "").strip():
        return _obs(action_id, False, "Screen click refused because no active task reason was provided.", error="reason_required")
    gui, error = _pyautogui()
    if gui is None:
        return _obs(action_id, False, "Screen click unavailable because real input is disabled.", error=error)
    gui.click(int(x), int(y))
    return _obs(action_id, True, f"Clicked visible screen coordinate for reason: {reason}.", {"x": int(x), "y": int(y)})


def double_click(x: int, y: int, reason: str, action_id: str = "screen.double_click") -> AgentObservation:
    if not str(reason or "").strip():
        return _obs(action_id, False, "Screen double-click refused because no active task reason was provided.", error="reason_required")
    gui, error = _pyautogui()
    if gui is None:
        return _obs(action_id, False, "Screen double-click unavailable because real input is disabled.", error=error)
    gui.doubleClick(int(x), int(y))
    return _obs(action_id, True, f"Double-clicked visible screen coordinate for reason: {reason}.", {"x": int(x), "y": int(y)})


def _focused_value() -> str | None:
    """The text currently in the focused control, or None if it cannot be read.

    None means "unknown", never "empty" -- the two must not be conflated, or an
    unreadable field would look like a field that lost everything typed into it.
    """
    try:
        from .dpi import ensure_dpi_aware

        ensure_dpi_aware()
        import uiautomation as auto  # type: ignore

        element = auto.GetFocusedControl()
        if element is None:
            return None
        pattern = element.GetValuePattern()
        value = pattern.Value
        return "" if value is None else str(value)
    except Exception:
        # Not every control exposes a value pattern, and the tree read can fail
        # outright. Both are "cannot tell", which this reports honestly rather
        # than guessing.
        return None


# Phase 103: 0.01 dropped and REORDERED characters. Measured over six rounds of
# a 22-character string typed into Notepad and read back off the control: three
# were wrong -- one dropped a character and two TRANSPOSED a pair, which means
# the keystrokes were racing, not merely being lost. A slower interval reduces
# the rate; six rounds cannot show that it eliminates it, and nothing here
# claims it does. That is what the readback below is for.
_TYPE_INTERVAL = 0.03


def type_text(text: str, reason: str, action_id: str = "screen.type_text") -> AgentObservation:
    if not str(reason or "").strip():
        return _obs(action_id, False, "Typing refused because no active task reason was provided.", error="reason_required")
    gui, error = _pyautogui()
    if gui is None:
        return _obs(action_id, False, "Typing unavailable because real input is disabled.", error=error)
    payload = str(text)

    # Read the field BEFORE, so the check is "it gained exactly this text" rather
    # than "it contains something like it" -- a field with existing contents is
    # the normal case, and a substring test would pass on a corrupted retype.
    before = _focused_value()
    gui.write(payload, interval=_TYPE_INTERVAL)
    after = _focused_value()

    # Deliberately reports LENGTHS and a boolean, never the strings. `text` is a
    # declared sensitive argument and is masked everywhere else; a verification
    # failure must not become the one place the value gets echoed into a summary,
    # a log or an error (the Phase 68 lesson).
    raw: dict[str, Any] = {"chars": len(payload)}
    if before is None or after is None:
        # An unverifiable type is not a failed type. Saying otherwise would make
        # form_filler stop at the first field of any app without a value pattern,
        # which is most of them.
        raw["verified"] = False
        return _obs(action_id, True, f"Typed text for reason: {reason}. Could not read the field back to confirm it.", raw)

    raw["verified"] = True
    # Typing does not always APPEND. If the field had a selection -- which is the
    # normal state after a select-all, and after clicking into a field that
    # selects on focus -- the keystrokes REPLACE it. `after == before + payload`
    # is true only for the append case, and measuring it that way reported a
    # failure on eight consecutive rounds that had in fact typed perfectly.
    #
    # So: the payload must land intact at the caret, and whatever precedes it
    # must be something the field already held (all of `before` for an append,
    # a prefix of it when a selected tail was replaced). `after != before` keeps
    # "nothing arrived at all" from passing when the field already ended with
    # the same characters. The residual gap is named rather than papered over:
    # without knowing the selection, a short payload that duplicates the tail of
    # a short existing value can still pass with a character missing.
    head = after[: len(after) - len(payload)] if len(after) >= len(payload) else None
    if after.endswith(payload) and head is not None and before.startswith(head) and after != before:
        return _obs(action_id, True, f"Typed text for reason: {reason}. Verified against the field.", raw)

    raw["arrived_chars"] = max(len(after) - len(before), 0)
    return _obs(
        action_id,
        False,
        # No retype. Typing again into a field whose contents were only partly
        # readable is how one corrupted string becomes two, and a confident wrong
        # retry is worse than an honest failure.
        f"Typing did not arrive intact for reason: {reason}. "
        f"{raw['arrived_chars']} of {len(payload)} characters reached the field; it was NOT retyped.",
        raw,
        error="typed_text_mismatch",
    )


def hotkey(keys: list[str], reason: str, action_id: str = "screen.hotkey") -> AgentObservation:
    if not str(reason or "").strip():
        return _obs(action_id, False, "Hotkey refused because no active task reason was provided.", error="reason_required")
    gui, error = _pyautogui()
    if gui is None:
        return _obs(action_id, False, "Hotkey unavailable because real input is disabled.", error=error)
    clean = [str(key).strip().lower() for key in keys if str(key).strip()]
    gui.hotkey(*clean)
    return _obs(action_id, True, f"Pressed hotkey for reason: {reason}.", {"keys": clean})


def press(key: str, reason: str, action_id: str = "screen.press") -> AgentObservation:
    if not str(reason or "").strip():
        return _obs(action_id, False, "Key press refused because no active task reason was provided.", error="reason_required")
    gui, error = _pyautogui()
    if gui is None:
        return _obs(action_id, False, "Key press unavailable because real input is disabled.", error=error)
    gui.press(str(key).strip().lower())
    return _obs(action_id, True, f"Pressed key for reason: {reason}.", {"key": key})


def scroll(amount: int, reason: str, action_id: str = "screen.scroll") -> AgentObservation:
    if not str(reason or "").strip():
        return _obs(action_id, False, "Scroll refused because no active task reason was provided.", error="reason_required")
    gui, error = _pyautogui()
    if gui is None:
        return _obs(action_id, False, "Scroll unavailable because real input is disabled.", error=error)
    gui.scroll(int(amount))
    return _obs(action_id, True, f"Scrolled for reason: {reason}.", {"amount": int(amount)})


def wait(seconds: float, reason: str, action_id: str = "screen.wait") -> AgentObservation:
    duration = max(0.0, min(float(seconds), 10.0))
    time.sleep(duration)
    return _obs(action_id, True, f"Waited {duration:.2f}s for reason: {reason}.", {"seconds": duration})


def click_target(target: UiTarget, reason: str, action_id: str = "screen.click") -> AgentObservation:
    if target.confidence < 0.75:
        return _obs(
            action_id,
            False,
            f"Target {target.label} was too low confidence to click safely.",
            raw={"target": target.as_dict()},
            error="ui_target_low_confidence",
        )
    # UiTarget.x,y is the CLICK POINT (grounding provides the element's center).
    # Do NOT add width/2 here or the click lands half a control away — a bug that
    # only surfaced under live validation, since every UiTarget producer emits a
    # center point.
    click_x = int(target.x)
    click_y = int(target.y)
    obs = click(click_x, click_y, reason, action_id=action_id)
    if obs.success:
        return _obs(
            action_id,
            True,
            f"Clicked verified UI target {target.label} for reason: {reason}.",
            {"target": target.as_dict(), "x": click_x, "y": click_y},
        )
    return obs


def type_text_visible(text: str, reason: str, action_id: str = "screen.type_text") -> AgentObservation:
    return type_text(text, reason, action_id=action_id)


def press_key_bounded(key: str, reason: str, action_id: str = "screen.press") -> AgentObservation:
    allowed = {"enter", "tab", "escape", "space", "backspace", "delete", "up", "down", "left", "right"}
    clean = str(key or "").strip().lower()
    if clean not in allowed:
        return _obs(action_id, False, f"Key {key} is not in the bounded visible-control allowlist.", error="unsupported_key")
    return press(clean, reason, action_id=action_id)


def hotkey_bounded(keys: list[str], reason: str, action_id: str = "screen.hotkey") -> AgentObservation:
    clean = [str(key).strip().lower() for key in keys if str(key).strip()]
    allowed = {
        ("ctrl", "l"),
        ("ctrl", "t"),
        ("ctrl", "w"),
        ("ctrl", "f"),
        ("ctrl", "a"),
        ("alt", "left"),
        ("alt", "right"),
    }
    if tuple(clean) not in allowed:
        return _obs(action_id, False, "Hotkey is not in the bounded visible-control allowlist.", {"keys": clean}, "unsupported_hotkey")
    return hotkey(clean, reason, action_id=action_id)
