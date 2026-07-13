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


def type_text(text: str, reason: str, action_id: str = "screen.type_text") -> AgentObservation:
    if not str(reason or "").strip():
        return _obs(action_id, False, "Typing refused because no active task reason was provided.", error="reason_required")
    gui, error = _pyautogui()
    if gui is None:
        return _obs(action_id, False, "Typing unavailable because real input is disabled.", error=error)
    gui.write(str(text), interval=0.01)
    return _obs(action_id, True, f"Typed text for reason: {reason}.", {"chars": len(str(text))})


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
    center_x = int(target.x + target.width / 2)
    center_y = int(target.y + target.height / 2)
    obs = click(center_x, center_y, reason, action_id=action_id)
    if obs.success:
        return _obs(
            action_id,
            True,
            f"Clicked verified UI target {target.label} for reason: {reason}.",
            {"target": target.as_dict(), "x": center_x, "y": center_y},
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
