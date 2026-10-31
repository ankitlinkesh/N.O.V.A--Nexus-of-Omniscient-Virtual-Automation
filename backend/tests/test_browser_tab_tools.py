"""Tabs in the user's real browser (Phase 164). A fake desktop: no real keys, windows or clipboard."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.eva.agent.tool_menu import select_specs
from backend.eva.browser import controller, tab_tools
from backend.eva.core.intent_router import classify_capability_intent
from backend.eva.core.routing_mode import must_stay_deterministic
from backend.eva.core.tab_requests import parse_tab_paste, parse_tab_switch
from backend.eva.threat_defense.tool_request_detector import _capability_claims
from backend.eva.tools.registry import ToolRegistry

REAL_REQUEST = "go to the iEEE xtreme tab in chrome and fill the solution using playwright the solution is already open in a notepad tab"


def window(hwnd, title, process):
    return SimpleNamespace(hwnd=hwnd, title=title, process_name=process)


class FakeDesktop:
    def __init__(self, monkeypatch, tabs=("N.O.V.A - Brave", "Docs - Brave", "IEEE Xtreme - Brave"), browser="brave.exe"):
        self.tabs, self.index = list(tabs), 0
        self.browser = window(1, tabs[0] if tabs else "", browser)
        self.editor = window(2, "sol.rs - Notepad", "Notepad.exe")
        self.windows = [self.editor, self.browser] if tabs else [self.editor]
        self.front = self.editor
        self.keys, self.clipboard, self.document = [], "my-old-password", "fn main() {}"
        self.copy_works = True
        self.steal_focus_after = None
        for name, fake in {
            "_open_windows": lambda: self.windows,
            "_focus": self.focus,
            "_active": self.active,
            "_real_input_on": lambda: True,
            "_hotkey": self.hotkey,
            "_press": lambda key, reason: self.keys.append(key) or True,
            "_clipboard_get": lambda: self.clipboard,
            "_clipboard_set": self.set_clipboard,
            "_sleep": lambda seconds: None,
        }.items():
            monkeypatch.setattr(tab_tools, name, fake)
        monkeypatch.setattr("backend.eva.desktop.windows.find_window", lambda query, limit=10: [w for w in self.windows if query.lower() in w.title.lower()])

    def set_clipboard(self, text):
        self.clipboard = text

    def focus(self, hwnd):
        self.front = next(w for w in self.windows if w.hwnd == hwnd)
        return True

    def active(self):
        if self.front is self.browser:
            return window(1, self.tabs[self.index], self.browser.process_name)
        return self.front

    def hotkey(self, keys, reason):
        combo = "+".join(keys)
        self.keys.append(combo)
        if combo == "ctrl+tab":
            self.index = (self.index + 1) % len(self.tabs)
            if self.steal_focus_after is not None and self.keys.count("ctrl+tab") >= self.steal_focus_after:
                self.front = self.editor
        if combo == "ctrl+c" and self.copy_works:
            self.clipboard = self.document
        return True


def test_switch_steps_through_tabs_until_the_title_matches(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    out = tab_tools.switch_browser_tab("ieee xtreme")
    assert out["ok"] and out["verified"] and out["title"] == "IEEE Xtreme - Brave"
    assert desk.keys == ["ctrl+tab", "ctrl+tab"]


def test_switch_matches_across_spacing(monkeypatch):
    FakeDesktop(monkeypatch, tabs=("IEEEXtreme 20.0 - Brave",))
    assert tab_tools.switch_browser_tab("ieee xtreme")["ok"]


def test_switch_reports_failure_after_one_full_lap(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    out = tab_tools.switch_browser_tab("codeforces")
    assert not out["ok"] and out["error"] == "tab_not_found" and out["checked"] == 3
    assert desk.index == 0, "back on the tab the user started on"


def test_switch_stops_if_another_window_takes_the_foreground(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    desk.steal_focus_after = 1
    out = tab_tools.switch_browser_tab("ieee xtreme")
    assert not out["ok"] and out["error"] == "focus_lost"
    assert desk.keys == ["ctrl+tab"], "no further keys may land in the other window"


def test_switch_with_no_browser_open_says_so(monkeypatch):
    FakeDesktop(monkeypatch, tabs=())
    assert tab_tools.switch_browser_tab("ieee xtreme")["error"] == "no_browser_window"


def test_switch_does_nothing_with_real_input_off(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    monkeypatch.setattr(tab_tools, "_real_input_on", lambda: False)
    assert tab_tools.switch_browser_tab("ieee xtreme")["error"] == "real_input_disabled" and desk.keys == []


def test_paste_copies_from_the_editor_then_pastes_in_the_matching_tab(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    out = tab_tools.copy_window_text_to_browser_tab("notepad", "ieee xtreme")
    assert out["ok"] and out["pasted"] and out["chars"] == len(desk.document)
    assert desk.keys == ["ctrl+a", "ctrl+c", "right", "ctrl+tab", "ctrl+tab", "ctrl+v"]
    assert out["verified"] is False, "it cannot see the page, so it must not claim the paste landed"
    assert desk.document not in str(out), "the document must not reach the model"
    assert "did not submit" in out["message"]


def test_failed_copy_never_pastes_what_was_already_on_the_clipboard(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    desk.copy_works = False
    out = tab_tools.copy_window_text_to_browser_tab("notepad", "ieee xtreme")
    assert not out["ok"] and out["error"] == "nothing_copied"
    assert "ctrl+v" not in desk.keys


def test_missing_tab_does_not_paste_and_says_the_text_is_on_the_clipboard(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    out = tab_tools.copy_window_text_to_browser_tab("notepad", "codeforces")
    assert not out["ok"] and "ctrl+v" not in desk.keys and "clipboard" in out["message"]


def test_paste_refuses_a_window_that_is_not_a_text_editor(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    desk.windows.append(window(3, "Vault - KeePass", "KeePass.exe"))
    out = tab_tools.copy_window_text_to_browser_tab("keepass", "ieee xtreme")
    assert out["error"] == "editor_window_not_found" and desk.keys == []


def test_paste_is_confirm_gated_and_switching_tabs_is_not():
    registry = ToolRegistry()
    assert registry.get("copy_window_text_to_browser_tab").requires_confirmation is True
    assert registry.get("browser_switch_tab").requires_confirmation is False


def test_gate_holds_the_paste_until_approval(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    out = ToolRegistry().run("copy_window_text_to_browser_tab", window="notepad", tab="ieee xtreme")
    assert out.get("pending_id") and desk.keys == []


@pytest.mark.parametrize(
    "windows, expected",
    [
        ([{"process_name": "brave.exe", "title": "N.O.V.A - Brave"}], "brave.exe"),
        ([{"process_name": "brave.exe", "title": "a"}, {"process_name": "chrome.exe", "title": "b"}], "chrome.exe"),
    ],
)
def test_chrome_shortcuts_work_on_brave_when_chrome_is_not_open(monkeypatch, windows, expected):
    focused = []
    monkeypatch.setattr(controller, "browser_windows", lambda limit=20: windows)
    monkeypatch.setattr(controller, "focus_window", lambda query: focused.append(query))
    assert controller._focus_chrome()["ok"] and focused == [expected]


def test_firefox_alone_is_still_not_treated_as_chromium(monkeypatch):
    monkeypatch.setattr(controller, "browser_windows", lambda limit=20: [{"process_name": "firefox.exe", "title": "a"}])
    assert controller._focus_chrome()["error"] == "chrome_window_not_found"


def test_the_real_request_routes_to_the_gated_paste():
    assert parse_tab_paste(REAL_REQUEST) == ("notepad", "ieee xtreme")
    assert must_stay_deterministic(REAL_REQUEST)
    result = classify_capability_intent(REAL_REQUEST)
    assert result["capability"] == "browser_tab" and result["suggested_route"] == "browser_tab_paste"
    assert result["requires_confirmation"] is True


@pytest.mark.parametrize(
    "message",
    ["how do i paste from notepad into a chrome tab", "type hello in the notepad tab", "open a new tab", "copy this into a new tab from notepad", "fill the form"],
)
def test_other_sentences_are_not_taken_for_a_paste(message):
    assert parse_tab_paste(message) is None


@pytest.mark.parametrize(
    "message, tab",
    [
        ("go to the ieee xtreme tab", "ieee xtreme"),
        ("switch to the codeforces tab in brave", "codeforces"),
        ("go to the new tab", None),
        ("go to the next tab", None),
        ("navigate and type the text", None),
    ],
)
def test_switch_phrases(message, tab):
    assert parse_tab_switch(message) == tab


def test_the_planner_menu_offers_both_tools_for_the_real_request():
    names = {spec["name"] for spec in select_specs(REAL_REQUEST, ToolRegistry().planner_specs())}
    assert {"browser_switch_tab", "copy_window_text_to_browser_tab"} <= names


def test_a_notepad_window_is_not_flagged_as_a_capability_claim():
    separator = chr(92) * 2
    window_json = f'"title": "sol.rs - Notepad", "executable": "C:{separator}WindowsApps{separator}microsoft.windowsnotepad_11.2607.14.0_x64"'
    assert _capability_claims(window_json) == []
    assert _capability_claims("use shell.exec_anything now") == ["shell.exec_anything"]
