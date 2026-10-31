"""Reach a tab in the user's own browser, and type text from an editor window into it.

The Playwright tools (web.*) launch their own separate Chromium, so they can never see a tab the
user has open and is logged in to. These tools work on the real window instead, with the keyboard,
and read the window title to know which tab is in front. Keys only ever go to a window confirmed
to be in the foreground, and nothing here presses Submit or reads the page.

The text read from the editor never reaches the model: replies carry only counts.
"""

from __future__ import annotations

import time
from typing import Any

# Chromium browsers share these shortcuts, and show the active tab in the window title.
BROWSER_PROCESSES = ("chrome.exe", "brave.exe", "msedge.exe", "opera.exe")
# Only windows whose whole text is the user's own document. Not browsers, terminals or password managers.
EDITOR_PROCESSES = frozenset({"notepad.exe", "notepad++.exe", "code.exe", "sublime_text.exe"})
MAX_TABS = 40
MAX_TYPE_CHARS = 20_000
TYPE_INTERVAL_SECONDS = 0.01
KEY_SETTLE_SECONDS = 0.2


def _sleep(seconds: float) -> None:  # seam: tests do not wait
    time.sleep(seconds)


def _open_windows() -> list[Any]:
    from ..desktop.windows import list_open_windows

    return list(list_open_windows(limit=80))


def _focus(hwnd: int) -> bool:
    from ..desktop.windows import focus_window_handle

    return bool(focus_window_handle(hwnd).get("ok"))


def _active() -> Any:
    from ..desktop.windows import get_active_window

    return get_active_window()


def _real_input_on() -> bool:
    from ..screen import screen_controller

    return bool(screen_controller.real_input_enabled())


def _hotkey(keys: list[str], reason: str) -> bool:
    from ..screen import screen_controller

    return bool(screen_controller.hotkey(keys, reason).success)


def _press(key: str, reason: str) -> bool:
    from ..screen import screen_controller

    return bool(screen_controller.press(key, reason).success)


def _type(text: str) -> bool:
    """Type one line. Moving the mouse into a screen corner aborts it (pyautogui's failsafe)."""
    from ..screen import screen_controller

    gui, _error = screen_controller._pyautogui()
    if gui is None:
        return False
    try:
        gui.write(text, interval=TYPE_INTERVAL_SECONDS)
    except Exception:  # noqa: BLE001 - the failsafe, or a dead input queue: stop and report it
        return False
    return True


def _clipboard_get() -> str | None:
    from ..tools import clipboard_tools

    return clipboard_tools._get_text()


def _clipboard_set(text: str) -> None:
    from ..tools import clipboard_tools

    clipboard_tools._set_text(text)


def _normalize(text: Any) -> str:
    """"IEEE Xtreme" and "IEEEXtreme 20.0" should match, so compare letters and digits only."""
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def _in_front(hwnd: int) -> bool:
    active = _active()
    return bool(active) and getattr(active, "hwnd", None) == hwnd


def _browser_windows() -> list[Any]:
    windows = [w for w in _open_windows() if str(w.process_name or "").lower() in BROWSER_PROCESSES]
    # Chrome first, because that is what "chrome" in a request means when it is open.
    return sorted(windows, key=lambda w: BROWSER_PROCESSES.index(str(w.process_name).lower()))


def _fail(error: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error": error, "message": message, "summary": message, **extra}


def switch_browser_tab(title: str) -> dict[str, Any]:
    """Bring the open tab whose title contains `title` to the front, by stepping through the tabs."""
    wanted = _normalize(title)
    if len(wanted) < 3:
        return _fail("tab_title_too_short", "I need a few letters of the tab's title to find it.")
    if not _real_input_on():
        return _fail("real_input_disabled", "Real keyboard input is off (EVA_ENABLE_REAL_INPUT), so I did not switch tabs.")
    windows = _browser_windows()
    if not windows:
        return _fail("no_browser_window", "No Chrome, Brave, Edge or Opera window is open, so there is no tab to switch to.")

    checked = 0
    for window in windows:
        if not _focus(window.hwnd) or not _in_front(window.hwnd):
            continue
        first = str(getattr(_active(), "title", "") or "")
        current = first
        for _ in range(MAX_TABS):
            checked += 1
            if wanted in _normalize(current):
                message = f"Switched to the tab \"{current}\"."
                return {"ok": True, "switched": True, "verified": True, "title": current, "hwnd": window.hwnd, "message": message, "summary": message}
            # Something else took the foreground: stop, or these keys would land in that window.
            if not _in_front(window.hwnd):
                return _fail("focus_lost", "Another window took the foreground while I was looking for the tab, so I stopped.")
            if not _hotkey(["ctrl", "tab"], f"look for the browser tab '{title}'"):
                return _fail("hotkey_failed", "Pressing Ctrl+Tab failed, so I stopped looking for the tab.")
            _sleep(KEY_SETTLE_SECONDS)
            current = str(getattr(_active(), "title", "") or "")
            if current == first:  # all the way round
                break
    return _fail("tab_not_found", f"I checked {checked} open tab(s) and none has \"{title}\" in its title. Is it open in this browser?", checked=checked)


def _read_editor_text(source: Any) -> tuple[str | None, str]:
    """All the text in an editor window, leaving the user's clipboard as it was. (text, error)."""
    if not _focus(source.hwnd) or not _in_front(source.hwnd):
        return None, "editor_not_in_front"
    text, error = _copy_selection(f"read the text in {source.title}")
    # Leave nothing selected: a stray key would replace the whole document.
    _press("right", "clear the selection in the editor")
    return text, error


def _copy_selection(reason: str) -> tuple[str | None, str]:
    """Select all and copy in the window in front, through a marker so a failed copy cannot read
    whatever was already on the clipboard (often a password), then put the clipboard back."""
    saved = _clipboard_get()
    marker = f"nova-copy-{time.time_ns()}"
    _clipboard_set(marker)
    try:
        if not (_hotkey(["ctrl", "a"], reason) and _hotkey(["ctrl", "c"], reason)):
            return None, "copy_failed"
        _sleep(KEY_SETTLE_SECONDS)
        text = _clipboard_get()
        return (None, "nothing_copied") if not text or text == marker else (text, "")
    finally:
        _clipboard_set(saved or "")


def _squeeze(text: str) -> str:
    return "".join(str(text or "").split())


def _report_typed(read_back: str | None, typed: str, summary: str, chars: int) -> dict[str, Any]:
    """Compare what the box holds now with what was meant to arrive."""
    base = {"typed": True, "chars": chars, "submitted": False}
    if read_back is None:
        message = f"{summary} I could not read the box back, so check it yourself. I did not submit anything."
        return {"ok": True, "verified": False, **base, "message": message, "summary": message}
    held = [line.rstrip() for line in read_back.splitlines()]
    meant = [line.rstrip() for line in typed.splitlines()]
    if held == meant:
        message = f"{summary} I read the box back and it matches exactly. I did not submit anything."
        return {"ok": True, "verified": True, **base, "match": "exact", "message": message, "summary": message}
    if _squeeze(read_back) == _squeeze(typed):
        message = (
            f"{summary} I read the box back: the code matches but the spacing differs, which is the editor's auto-indent. "
            "That is fine in most languages; in Python, fix the indentation. I did not submit anything."
        )
        return {"ok": True, "verified": True, **base, "match": "ignoring_whitespace", "message": message, "summary": message}
    if _squeeze(typed) in _squeeze(read_back):
        message = f"{summary} The code arrived intact, but the box also holds other text, so check it. I did not submit anything."
        return {"ok": True, "verified": True, **base, "match": "with_other_text", "message": message, "summary": message}
    message = (
        f"{summary} But the box does NOT match the original: the editor changed it, or the cursor was not in the box. "
        "Press Ctrl+Z there, or clear the box and try again. I did not submit anything."
    )
    return {"ok": False, "verified": False, "error": "typed_text_mismatch", **base, "message": message, "summary": message}


def type_window_text_into_browser_tab(window: str, tab: str) -> dict[str, Any]:
    """Read all the text in an editor window and type it at the cursor in a browser tab. Never submits.

    Only the code path sees the text, never the model, so a small model cannot garble it.
    """
    if not _real_input_on():
        return _fail("real_input_disabled", "Real keyboard input is off (EVA_ENABLE_REAL_INPUT), so I did not read or type anything.")
    from ..desktop.windows import find_window

    source = next((w for w in find_window(str(window or "")) if str(w.process_name or "").lower() in EDITOR_PROCESSES), None)
    if source is None:
        return _fail("editor_window_not_found", f"I could not find a text editor window matching \"{window}\". I only read from Notepad, Notepad++, VS Code and Sublime Text.")

    text, error = _read_editor_text(source)
    if text is None:
        return _fail(error, f"I could not read the text in \"{source.title}\" (is it empty?). Nothing was typed.")
    lines = [line.expandtabs(4) for line in text.splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()
    chars = sum(len(line) + 1 for line in lines)
    if chars > MAX_TYPE_CHARS:
        return _fail("text_too_long", f"\"{source.title}\" has {chars} characters, more than the {MAX_TYPE_CHARS} I will type. Nothing was typed.")
    # The keyboard route silently drops anything else, which would change the code without a word.
    unusual = sum(1 for line in lines for ch in line if not 32 <= ord(ch) < 127)
    if unusual:
        return _fail("unsupported_characters", f"\"{source.title}\" has {unusual} non-keyboard character(s), such as accents or symbols, that I cannot type reliably. Replace them and try again. Nothing was typed.")

    switched = switch_browser_tab(tab)
    if not switched.get("ok"):
        return _fail(str(switched.get("error") or "tab_not_found"), f"I read {chars} characters from \"{source.title}\" but typed nothing. {switched.get('message')}", chars=chars)
    browser = int(switched["hwnd"])
    wanted = _normalize(tab)

    for index, line in enumerate(lines):
        active = _active()
        # Checked before every line: keys must never land in another window or another tab.
        if not _in_front(browser) or wanted not in _normalize(getattr(active, "title", "")):
            return _fail("focus_lost", f"The window or tab changed, so I stopped after {index} of {len(lines)} lines. Check the box; I did not submit anything.", lines_typed=index)
        if not _type(line):
            return _fail("typing_stopped", f"Typing stopped after {index} of {len(lines)} lines (moving the mouse into a screen corner does this). Check the box; I did not submit anything.", lines_typed=index)
        if index < len(lines) - 1:
            # Escape first: Enter would otherwise accept whatever the editor's suggestion popup is offering.
            _press("escape", "close any suggestion popup before the next line")
            _press("enter", "start the next line")

    # Editors auto-close brackets, and those closers pile up after the cursor: remove them.
    _press("escape", "close any suggestion popup")
    _hotkey(["ctrl", "shift", "end"], "select anything the editor added after the cursor")
    _press("delete", "remove what the editor added after the cursor")
    read_back, _ = _copy_selection("read the box back to check the typing")
    _hotkey(["ctrl", "end"], "clear the selection so a stray key cannot replace the text")
    typed = chr(10).join(lines)
    return _report_typed(read_back, typed, f"Typed {len(lines)} lines from \"{source.title}\" into \"{switched.get('title')}\".", chars)
