"""A packaged app's inner CoreWindow must not stand in for the visible frame (minimize/restore/focus)."""

from types import SimpleNamespace

from backend.eva.desktop import windows as W

CORE, FRAME, NOTEPAD = 100, 200, 300
CLASSES = {CORE: "Windows.UI.Core.CoreWindow", FRAME: "ApplicationFrameWindow", NOTEPAD: "Notepad"}


def _wire(monkeypatch):
    monkeypatch.setattr(W, "_class_name", lambda hwnd: CLASSES.get(hwnd, ""))
    monkeypatch.setattr(W, "_window_info", lambda hwnd: SimpleNamespace(title="Calculator") if hwnd in (CORE, FRAME) else None)
    monkeypatch.setattr(
        W, "find_window",
        lambda title, limit=10: [SimpleNamespace(hwnd=CORE, title="Calculator"), SimpleNamespace(hwnd=FRAME, title="Calculator")],
    )


def test_a_core_window_resolves_to_its_frame(monkeypatch):
    _wire(monkeypatch)
    assert W._top_level(CORE) == FRAME


def test_a_frame_or_an_ordinary_window_is_left_alone(monkeypatch):
    _wire(monkeypatch)
    assert W._top_level(FRAME) == FRAME and W._top_level(NOTEPAD) == NOTEPAD


def test_a_core_window_without_a_matching_frame_falls_back_to_itself(monkeypatch):
    _wire(monkeypatch)
    monkeypatch.setattr(W, "find_window", lambda title, limit=10: [SimpleNamespace(hwnd=CORE, title="Calculator")])
    assert W._top_level(CORE) == CORE


def test_show_and_focus_act_on_the_frame(monkeypatch):
    _wire(monkeypatch)
    shown, focused = [], []
    monkeypatch.setattr(W, "_unsupported", lambda: False)
    monkeypatch.setattr(W, "find_window", lambda q, limit=1: [SimpleNamespace(hwnd=CORE, title="Calculator", as_dict=lambda: {})] if limit == 1 else [SimpleNamespace(hwnd=CORE, title="Calculator"), SimpleNamespace(hwnd=FRAME, title="Calculator")])
    monkeypatch.setattr(W.user32, "ShowWindow", lambda hwnd, command: shown.append((int(hwnd), command)) or True)
    monkeypatch.setattr(W, "_window_reached_state", lambda hwnd, command: True)
    assert W._show_window("Calculator", W.SW_RESTORE)["ok"]
    assert shown == [(FRAME, W.SW_RESTORE)]
    monkeypatch.setattr(W, "_try_set_foreground", lambda hwnd: focused.append(hwnd))
    monkeypatch.setattr(W, "_wait_for_focus", lambda hwnd, **k: (SimpleNamespace(as_dict=lambda: {}), True))
    assert W.focus_window("Calculator")["ok"] and focused == [FRAME]
