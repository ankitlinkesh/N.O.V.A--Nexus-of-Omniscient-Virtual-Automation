"""Grounding disambiguation (Phase 59).

The matcher's rule is "decline rather than click the wrong thing." That has to
hold at the ambiguity level too: if a label matches two controls about equally,
grounding must refuse and surface both, not silently click the first.
"""

from __future__ import annotations

import pytest

from eva.screen import grounding
from eva.screen.grounding import RawElement, locate, resolve
from eva.screen.screen_tools import screen_click


def _el(name, role="button", left=100, top=100, w=80, h=30):
    return RawElement(name=name, role=role, left=left, top=top, width=w, height=h)


@pytest.fixture()
def enabled(monkeypatch):
    monkeypatch.setenv("EVA_GUI_GROUNDING_ENABLED", "1")
    yield monkeypatch


def _use(monkeypatch, elements):
    monkeypatch.setattr(grounding, "_default_provider", lambda: list(elements))


# -- resolve() classifies found / none / ambiguous -------------------------

def test_one_clear_match_is_found(enabled):
    _use(enabled, [_el("Submit", "button"), _el("Cancel", "button")])
    r = resolve("Submit")
    assert r.status == "found"
    assert r.target.label == "Submit"


def test_two_equal_matches_are_ambiguous(enabled):
    # Two identically-named buttons in different places.
    _use(enabled, [_el("OK", "button", left=100), _el("OK", "button", left=400)])
    r = resolve("OK")
    assert r.status == "ambiguous"
    assert r.target is None
    assert len(r.candidates) == 2
    assert "specific" in r.reason


def test_a_clear_winner_over_a_weak_second_is_not_ambiguous(enabled):
    # "Save" exact vs "Save As" partial — far enough apart to be unambiguous.
    _use(enabled, [_el("Save", "button"), _el("Save As", "button")])
    r = resolve("Save")
    assert r.status == "found"
    assert r.target.label == "Save"


def test_nothing_above_floor_is_none(enabled):
    _use(enabled, [_el("Frobnicate", "button")])
    r = resolve("totally different label")
    assert r.status == "none"
    assert r.target is None


def test_locate_returns_none_for_ambiguous(enabled):
    _use(enabled, [_el("OK", "button", left=100), _el("OK", "button", left=400)])
    assert locate("OK") is None  # safer: no target rather than a coin-flip click


def test_specific_label_resolves_an_otherwise_ambiguous_pair(enabled):
    _use(enabled, [_el("Save", "button"), _el("Save and Close", "button")])
    # "Save and Close" targets exactly one.
    r = resolve("Save and Close")
    assert r.status == "found"
    assert r.target.label == "Save and Close"


# -- screen.click refuses an ambiguous label -------------------------------

def test_click_by_ambiguous_label_refuses_with_candidates(enabled):
    _use(enabled, [_el("OK", "button", left=100), _el("OK", "button", left=400)])
    result = screen_click(reason="confirm the dialog", label="OK")
    assert result.get("error") == "ambiguous_target"
    assert result.get("ok") is False
    assert "several controls" in result.get("message", "")


def test_click_by_unique_label_still_reaches_the_controller(enabled):
    _use(enabled, [_el("Submit", "button"), _el("Cancel", "button")])
    result = screen_click(reason="submit", label="Submit")
    # Unambiguous -> accepted -> only real-input gate stops it.
    assert result.get("error") not in {"ambiguous_target", "ui_target_not_found"}
    assert "real input" in (result.get("message", "") + str(result.get("error", ""))).lower()
