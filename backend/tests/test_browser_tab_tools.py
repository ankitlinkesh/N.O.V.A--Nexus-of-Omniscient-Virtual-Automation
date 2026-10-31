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
        self.keys, self.clipboard, self.document = [], "my-old-password", "fn main() {\n    run();\n}\n"
        self.box, self.typed_elsewhere, self.after_cursor = "", "", ""
        self.copy_works, self.box_copy_works, self.auto_close, self.auto_indent = True, True, False, False
        self.steal_focus_after = None
        self.change_tab_after_lines = None
        self.lines_typed = 0
        self.selection, self.select_after, self.home_works = 0, False, True
        for name, fake in {
            "_open_windows": lambda: self.windows,
            "_focus": self.focus,
            "_active": self.active,
            "_real_input_on": lambda: True,
            "_hotkey": self.hotkey,
            "_press": self.press,
            "_type": self.type_line,
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

    def type_line(self, text):
        if self.front is not self.browser:
            self.typed_elsewhere += text
            return True
        self.box += text
        if self.auto_close and text.endswith("{"):
            self.after_cursor += "}"
        self.lines_typed += 1
        if self.change_tab_after_lines == self.lines_typed:
            self.index = 0
        return True

    def press(self, key, reason):
        self.keys.append(key)
        if self.front is self.browser and key == "enter":
            line = self.box.rsplit("\n", 1)[-1]
            indent = line[: len(line) - len(line.lstrip())] + ("    " if line.endswith("{") else "")
            self.box += "\n" + (indent if self.auto_indent else "")
        if key == "delete":
            if self.select_after:
                self.after_cursor, self.select_after = "", False
            elif self.selection:
                self.box, self.selection = self.box[: -self.selection], 0
            else:
                self.after_cursor = self.after_cursor[1:]
        return True

    def hotkey(self, keys, reason):
        combo = "+".join(keys)
        self.keys.append(combo)
        if combo == "ctrl+tab":
            self.index = (self.index + 1) % len(self.tabs)
            if self.steal_focus_after is not None and self.keys.count("ctrl+tab") >= self.steal_focus_after:
                self.front = self.editor
        if combo == "shift+home":
            line = self.box.rsplit("\n", 1)[-1]
            self.selection = len(line) if self.home_works and not line.strip() else 0
        if combo == "ctrl+shift+end":
            self.select_after = True
        if combo == "ctrl+c":
            if self.front is self.editor and self.copy_works:
                self.clipboard = self.document
            if self.front is self.browser and self.box_copy_works:
                self.clipboard = self.box + self.after_cursor
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


def run_typing(tab="ieee xtreme"):
    return tab_tools.type_window_text_into_browser_tab("notepad", tab)


def test_reads_the_editor_and_types_it_into_the_matching_tab(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    out = run_typing()
    assert out["ok"] and out["verified"] and out["match"] == "exact" and out["submitted"] is False
    assert desk.box == "fn main() {\n    run();\n}"
    assert desk.typed_elsewhere == ""
    assert "ctrl+v" not in desk.keys, "it types; it never pastes"
    assert "run();" not in str(out), "the document must not reach the model"


def test_the_clipboard_is_put_back_after_reading_and_after_checking(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    run_typing()
    assert desk.clipboard == "my-old-password"


def test_the_editor_is_left_with_nothing_selected(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    run_typing()
    assert desk.keys[:3] == ["ctrl+a", "ctrl+c", "right"]


def test_a_failed_read_never_types_what_was_already_on_the_clipboard(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    desk.copy_works = False
    out = run_typing()
    assert not out["ok"] and out["error"] == "nothing_copied"
    assert desk.box == "" and desk.clipboard == "my-old-password"


def test_brackets_the_editor_closed_by_itself_are_removed(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    desk.auto_close = True
    out = run_typing()
    assert out["ok"] and out["match"] == "exact" and desk.after_cursor == ""


def test_the_editors_auto_indent_is_removed_so_indentation_stays_as_written(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    desk.auto_indent = True
    desk.document = "fn main() {\n    if x {\n        run();\n    }\n\n}\n"
    out = run_typing()
    assert out["ok"] and out["match"] == "exact"
    assert desk.box == "fn main() {\n    if x {\n        run();\n    }\n\n}"


def test_auto_indent_with_auto_closed_brackets_also_comes_out_exact(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    desk.auto_indent, desk.auto_close = True, True
    out = run_typing()
    assert out["ok"] and out["match"] == "exact" and desk.after_cursor == ""


def test_an_indent_that_could_not_be_removed_is_reported_not_hidden(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    desk.auto_indent, desk.home_works = True, False
    out = run_typing()
    assert out["ok"] and out["match"] == "ignoring_whitespace" and "spacing differs" in out["message"]


def test_a_box_that_does_not_match_is_a_failure(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    real_type = desk.type_line
    monkeypatch.setattr(tab_tools, "_type", lambda text: real_type(text.replace("run", "rub")))
    out = run_typing()
    assert not out["ok"] and out["error"] == "typed_text_mismatch" and out["verified"] is False


def test_other_text_already_in_the_box_is_mentioned(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    desk.box = "// template\n"
    out = run_typing()
    assert out["ok"] and out["match"] == "with_other_text"


def test_an_unreadable_box_is_reported_as_unverified(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    desk.box_copy_works = False
    out = run_typing()
    assert out["ok"] and out["verified"] is False and "check it yourself" in out["message"]


def test_typing_stops_if_the_window_changes(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    real_type = desk.type_line

    def type_then_lose_focus(text):
        real_type(text)
        desk.front = desk.editor
        return True

    monkeypatch.setattr(tab_tools, "_type", type_then_lose_focus)
    out = run_typing()
    assert not out["ok"] and out["error"] == "focus_lost" and out["lines_typed"] == 1
    assert desk.document != desk.box


def test_typing_stops_if_the_user_switches_tab(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    desk.change_tab_after_lines = 1
    out = run_typing()
    assert not out["ok"] and out["error"] == "focus_lost" and out["lines_typed"] == 1


def test_the_failsafe_stops_typing_and_says_how_far_it_got(monkeypatch):
    FakeDesktop(monkeypatch)
    monkeypatch.setattr(tab_tools, "_type", lambda text: False)
    out = run_typing()
    assert not out["ok"] and out["error"] == "typing_stopped" and out["lines_typed"] == 0


def test_missing_tab_types_nothing(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    out = run_typing("codeforces")
    assert not out["ok"] and desk.box == "" and desk.typed_elsewhere == ""


def test_non_keyboard_characters_are_refused_before_typing(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    desk.document = "// caf" + chr(233) + "\nfn main() {}\n"
    out = run_typing()
    assert not out["ok"] and out["error"] == "unsupported_characters" and desk.box == ""


def test_very_long_text_is_refused(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    desk.document = "x" * (tab_tools.MAX_TYPE_CHARS + 1)
    out = run_typing()
    assert not out["ok"] and out["error"] == "text_too_long" and desk.box == ""


def test_tabs_become_spaces_so_they_cannot_move_focus_out_of_the_box(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    desk.document = "a\n" + chr(9) + "b\n"
    assert run_typing()["ok"] and desk.box == "a\n    b"


def test_refuses_a_window_that_is_not_a_text_editor(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    desk.windows.append(window(3, "Vault - KeePass", "KeePass.exe"))
    out = tab_tools.type_window_text_into_browser_tab("keepass", "ieee xtreme")
    assert out["error"] == "editor_window_not_found" and desk.keys == []


def test_typing_is_confirm_gated_and_switching_tabs_is_not():
    registry = ToolRegistry()
    assert registry.get("type_window_text_into_browser_tab").requires_confirmation is True
    assert registry.get("browser_switch_tab").requires_confirmation is False


def test_gate_holds_the_typing_until_approval(monkeypatch):
    desk = FakeDesktop(monkeypatch)
    out = ToolRegistry().run("type_window_text_into_browser_tab", window="notepad", tab="ieee xtreme")
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


def test_the_real_request_routes_to_the_gated_typing():
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
    assert {"browser_switch_tab", "type_window_text_into_browser_tab"} <= names


def test_a_notepad_window_is_not_flagged_as_a_capability_claim():
    separator = chr(92) * 2
    window_json = f'"title": "sol.rs - Notepad", "executable": "C:{separator}WindowsApps{separator}microsoft.windowsnotepad_11.2607.14.0_x64"'
    assert _capability_claims(window_json) == []
    assert _capability_claims("use shell.exec_anything now") == ["shell.exec_anything"]
