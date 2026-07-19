"""Executable spec for backend/eva/desktop/verifier.py's verify_window_focused
(Phase 64 follow-up).

verify_app_opened / verify_folder_opened / verify_url_opened in this same
file were already written with retries=4, delay_seconds=0.2 -- they already
knew a launch takes a moment to produce a window. verify_window_focused was
the odd one out: a single immediate read. That mattered once
eva.tools.postconditions started calling it as an INDEPENDENT postcondition
check (Phase 64) -- a focus change landing a moment late would read as a
false failure. This pins the fix directly on the function, independent of
the postcondition layer that consumes it (verify_last_action, in
eva/desktop/skills.py, is the other caller and gets the fix for free).

Deterministic and offline throughout: get_active_window is monkeypatched,
and every test passes a small delay_seconds so no test actually sleeps for
the real-world default (up to 4 * 0.2s = 0.8s).
"""

from __future__ import annotations

from eva.desktop import verifier as desktop_verifier
from eva.desktop.verifier import verify_window_focused
from eva.desktop.windows import WindowInfo

CHROME = WindowInfo(hwnd=1, title="Google Chrome", process_id=1, process_name="chrome.exe", executable=r"C:\chrome.exe")
NOTEPAD = WindowInfo(hwnd=2, title="Untitled - Notepad", process_id=2, process_name="notepad.exe", executable=r"C:\Windows\notepad.exe")


def test_verifies_immediately_when_already_matching(monkeypatch):
    reads = {"n": 0}

    def immediate():
        reads["n"] += 1
        return CHROME

    monkeypatch.setattr(desktop_verifier, "get_active_window", immediate)

    result = verify_window_focused("chrome", retries=4, delay_seconds=0.01)

    assert result["ok"] is True
    assert result["verified"] is True
    assert reads["n"] == 1, "must not retry when the very first read already matches"


def test_retries_and_succeeds_on_a_later_read(monkeypatch):
    """A focus change that lands a moment after the first read must not be
    reported as a false failure -- this is the exact bug: verify_window_focused
    used to do a single immediate read with no retry at all."""
    reads = {"n": 0}

    def flaky():
        reads["n"] += 1
        return NOTEPAD if reads["n"] < 3 else CHROME

    monkeypatch.setattr(desktop_verifier, "get_active_window", flaky)

    result = verify_window_focused("chrome", retries=4, delay_seconds=0.01)

    assert result["ok"] is True
    assert result["verified"] is True, f"a focus landing on the 3rd read must not be a false failure: {result}"
    assert reads["n"] >= 3


def test_still_reports_unverified_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(desktop_verifier, "get_active_window", lambda: NOTEPAD)

    result = verify_window_focused("chrome", retries=3, delay_seconds=0.01)

    assert result["ok"] is True
    assert result["verified"] is False, "a genuine, persistent mismatch must still fail after retries are exhausted"


def test_active_window_unavailable_is_reported_not_swallowed(monkeypatch):
    monkeypatch.setattr(desktop_verifier, "get_active_window", lambda: None)

    result = verify_window_focused("chrome", retries=2, delay_seconds=0.01)

    assert result["ok"] is False
    assert result["error"] == "active_window_unavailable"
