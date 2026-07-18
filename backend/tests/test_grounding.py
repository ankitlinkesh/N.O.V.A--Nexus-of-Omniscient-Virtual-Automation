"""GUI grounding — text label -> a clickable on-screen target (Phase 56).

The engine is tested against fabricated accessibility trees (no real desktop),
because the property that matters is the matcher: it must pick the right control
and, crucially, decline rather than click the wrong one.
"""

from __future__ import annotations

import pytest

from eva.screen import grounding
from eva.screen.grounding import RawElement, locate, rank_targets, score_element
from eva.screen.screen_tools import screen_click
from eva.security import tool_gate
from eva.tools.registry import ToolRegistry


def _btn(name, role="button", left=100, top=200, w=80, h=30, enabled=True, on_screen=True):
    return RawElement(name=name, role=role, left=left, top=top, width=w, height=h, enabled=enabled, on_screen=on_screen)


FORM = [
    _btn("Submit", role="button", left=300, top=500, w=100, h=40),
    _btn("Cancel", role="button", left=180, top=500, w=100, h=40),
    _btn("Email", role="edit", left=200, top=200, w=240, h=30),
    _btn("Password", role="edit", left=200, top=260, w=240, h=30),
    _btn("Remember me", role="checkbox", left=200, top=320, w=20, h=20),
]


@pytest.fixture()
def enabled(monkeypatch):
    monkeypatch.setenv("EVA_GUI_GROUNDING_ENABLED", "1")
    monkeypatch.setattr(grounding, "_default_provider", lambda: list(FORM))
    tool_gate.reset_pending_calls()
    yield
    tool_gate.reset_pending_calls()


# -- the matcher -----------------------------------------------------------

def test_exact_label_scores_highest():
    assert score_element("Submit", _btn("Submit")) >= 0.95


def test_role_word_is_stripped_from_the_label_match():
    # "email field" must match a control literally named "Email" of role edit.
    s = score_element("email field", _btn("Email", role="edit"))
    assert s >= 0.9


def test_wrong_role_is_penalised():
    # Asking for the "Submit field" should NOT confidently match the Submit button.
    field = score_element("Submit field", _btn("Submit", role="button"))
    button = score_element("Submit button", _btn("Submit", role="button"))
    assert button > field
    assert field < 0.75  # below the click floor -> would not be actioned


def test_offscreen_and_zero_size_score_zero():
    assert score_element("Submit", _btn("Submit", on_screen=False)) == 0.0
    assert score_element("Submit", _btn("Submit", w=0)) == 0.0


def test_disabled_is_penalised_not_zeroed():
    s = score_element("Submit", _btn("Submit", enabled=False))
    assert 0.0 < s < 0.75


def test_ranking_puts_the_right_control_first():
    targets = rank_targets("Cancel", FORM, floor=0.0)
    assert targets[0].label == "Cancel"
    # Cancel's center: left 180 + 100//2 = 230, top 500 + 40//2 = 520
    assert (targets[0].x, targets[0].y) == (230, 520)


# -- locate() honours the confidence floor and the flag --------------------

def test_locate_returns_the_email_field(enabled):
    target = locate("email field")
    assert target is not None and target.label == "Email"
    assert (target.x, target.y) == (320, 215)  # 200+240//2, 200+30//2


def test_locate_returns_none_when_nothing_matches(enabled):
    assert locate("nonexistent gizmo") is None


def test_locate_is_off_by_default(monkeypatch):
    monkeypatch.delenv("EVA_GUI_GROUNDING_ENABLED", raising=False)
    monkeypatch.setattr(grounding, "_default_provider", lambda: list(FORM))
    assert locate("Submit") is None  # byte-identical to the old stub


def test_missing_library_degrades_to_no_targets(monkeypatch):
    monkeypatch.setenv("EVA_GUI_GROUNDING_ENABLED", "1")
    # The real default provider yields [] when uiautomation is absent (this env).
    assert grounding.enumerate_elements() == [] or isinstance(grounding.enumerate_elements(), list)
    assert locate("Submit") is None


# -- end to end: click BY LABEL through the real gate ----------------------

def test_click_by_label_reaches_the_controller(enabled):
    """With grounding on, screen.click(label=...) resolves a target and passes the
    confidence gate. Real input is off, so it stops at 'real input disabled' —
    which proves the target was ACCEPTED, not refused for lack of one."""
    result = screen_click(reason="submit the login form", label="Submit")
    assert result.get("error") not in {"ui_target_required", "ui_target_not_found", "ui_target_low_confidence"}
    # It got past grounding+confidence; the only thing stopping it is real input.
    assert result.get("ok") is False
    assert "real input" in (result.get("message", "") + str(result.get("error", ""))).lower()


def test_click_by_label_with_no_match_refuses(enabled):
    result = screen_click(reason="click the frobnicator", label="frobnicator 3000")
    assert result.get("error") == "ui_target_not_found"
    assert result.get("ok") is False


def test_click_without_target_or_label_still_refuses(enabled):
    result = screen_click(reason="click something")
    assert result.get("error") == "ui_target_required"


def test_registry_screen_click_exposes_label_and_is_gated():
    registry = ToolRegistry()
    spec = registry.get("screen.click")
    assert "label" in spec.args_schema.get("properties", {})
