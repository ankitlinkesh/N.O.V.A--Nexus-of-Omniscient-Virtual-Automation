"""Real mouse/keyboard input (pyautogui) is opt-in and safe by default.

pyautogui is now installed, so the screen.* tools *could* drive the physical
cursor. These tests pin the safety contract: nothing performs real input unless
the operator explicitly sets EVA_ENABLE_REAL_INPUT, and even then the sensitive
input tools (type_text/hotkey/press) still route through the permission gate.
No test here calls a real screen action, so the suite never moves the cursor.
"""
from __future__ import annotations

from backend.eva.screen import screen_controller as sc
from backend.eva.tools.registry import ToolRegistry


def test_real_input_disabled_by_default(monkeypatch):
    monkeypatch.delenv("EVA_ENABLE_REAL_INPUT", raising=False)
    assert sc.real_input_enabled() is False
    gui, err = sc._pyautogui()
    assert gui is None, "pyautogui must not load real input while the flag is off"
    assert "disabled" in (err or "")


def test_flag_values_toggle_real_input(monkeypatch):
    for off in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("EVA_ENABLE_REAL_INPUT", off)
        assert sc.real_input_enabled() is False, f"{off!r} must read as off"
    for on in ("1", "true", "yes", "on"):
        monkeypatch.setenv("EVA_ENABLE_REAL_INPUT", on)
        assert sc.real_input_enabled() is True, f"{on!r} must read as on"


def test_screen_click_is_inert_without_flag(monkeypatch):
    """screen.click is allow-class (runs immediately), but with the flag off the
    handler must degrade to a disabled result rather than move the real cursor."""
    monkeypatch.delenv("EVA_ENABLE_REAL_INPUT", raising=False)
    obs = sc.click(5, 5, reason="unit-test-must-not-move-cursor")
    assert obs.success is False
    assert "disabled" in obs.summary.lower()


def test_type_text_still_gated_even_when_real_input_enabled(monkeypatch):
    """Enabling real input must NOT loosen the gate: screen.type_text stays
    confirm-class and never executes without ledger confirmation."""
    monkeypatch.setenv("EVA_ENABLE_REAL_INPUT", "1")
    registry = ToolRegistry()
    result = registry.run("screen.type_text", text="rm -rf important", reason="test")
    assert result.get("requires_confirmation") is True
    assert result.get("risk_class") == "confirm"
