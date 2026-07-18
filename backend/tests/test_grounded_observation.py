"""Grounded screen observation (Phase 57).

screen.observe used to return the window title and nothing else — ui_targets was
always []. Now it reports the clickable controls on screen (from the same
accessibility tree Phase 56 clicks through), so NOVA can answer "what's on my
screen?" and discover a target before acting. Reading the UI tree stays inside
the existing override-class screen.observe gate — no new lowered-friction path.
"""

from __future__ import annotations

import pytest

from eva.screen import grounding, screen_observer
from eva.screen.grounding import RawElement, describe_visible


FORM = [
    RawElement("Submit", "button", 300, 500, 100, 40),
    RawElement("Email", "edit", 200, 200, 240, 30),
    RawElement("Password", "edit", 200, 260, 240, 30),
    RawElement("", "text", 0, 0, 0, 0),                        # unnamed/zero -> skipped
    RawElement("Offscreen", "button", 10, 10, 40, 20, on_screen=False),  # skipped
]


@pytest.fixture()
def enabled(monkeypatch):
    monkeypatch.setenv("EVA_GUI_GROUNDING_ENABLED", "1")
    monkeypatch.setattr(grounding, "_default_provider", lambda: list(FORM))
    yield


# -- describe_visible (pure) -----------------------------------------------

def test_describe_lists_only_real_clickable_controls(enabled):
    report = describe_visible()
    labels = [t["label"] for t in report["ui_targets"]]
    assert labels == ["Submit", "Email", "Password"]     # unnamed + offscreen dropped
    assert report["count"] == 3
    assert "Submit (button)" in report["summary"]


def test_describe_carries_center_coordinates(enabled):
    report = describe_visible()
    submit = report["ui_targets"][0]
    assert (submit["x"], submit["y"]) == (350, 520)      # 300+100//2, 500+40//2


def test_describe_is_empty_when_grounding_off(monkeypatch):
    monkeypatch.delenv("EVA_GUI_GROUNDING_ENABLED", raising=False)
    monkeypatch.setattr(grounding, "_default_provider", lambda: list(FORM))
    report = describe_visible()
    assert report == {"ui_targets": [], "count": 0, "summary": ""}


def test_describe_respects_the_limit(enabled):
    report = describe_visible(limit=2)
    assert report["count"] == 2


# -- observe_screen_once integration ---------------------------------------

def test_observe_reports_ui_targets_even_when_screenshot_fails(enabled, monkeypatch):
    # Force the pixel grab to fail; the a11y tree must still describe the UI.
    def boom(_reason):
        raise RuntimeError("no display")

    monkeypatch.setattr(screen_observer, "capture_screen", boom)
    obs = screen_observer.observe_screen_once("check the login form")
    assert obs.ok is False and obs.error == "screen_observation_unavailable"
    assert [t["label"] for t in obs.ui_targets] == ["Submit", "Email", "Password"]
    assert "Visible controls" in obs.local_summary


def test_observe_merges_controls_into_summary_on_success(enabled, monkeypatch):
    from eva.screen.screen_observer import ScreenFrame

    monkeypatch.setattr(
        screen_observer,
        "capture_screen",
        lambda _r: ScreenFrame("f1", "C:/tmp/f1.png", 1920, 1080, "2026-07-17T00:00:00+00:00", "Login"),
    )
    obs = screen_observer.observe_screen_once("check the login form")
    assert obs.ok is True
    assert [t["label"] for t in obs.ui_targets] == ["Submit", "Email", "Password"]
    assert "Active window" in obs.local_summary and "Visible controls" in obs.local_summary


def test_observe_is_unchanged_when_grounding_off(monkeypatch):
    monkeypatch.delenv("EVA_GUI_GROUNDING_ENABLED", raising=False)

    def boom(_reason):
        raise RuntimeError("no display")

    monkeypatch.setattr(screen_observer, "capture_screen", boom)
    obs = screen_observer.observe_screen_once("look")
    assert obs.ui_targets == []
    assert "Visible controls" not in obs.local_summary
