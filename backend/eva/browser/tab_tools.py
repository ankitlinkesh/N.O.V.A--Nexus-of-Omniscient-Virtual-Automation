"""Reach a tab in the user's own browser, and paste text from an editor window into it.

The Playwright tools (web.*) launch their own separate Chromium, so they can never see a tab the
user has open and is logged in to. These tools work on the real window instead, with the keyboard,
and read the window title to know which tab is in front. Keys only ever go to a window confirmed
to be in the foreground, and nothing here presses Submit or reads the page.

The text copied from the editor never reaches the model: replies carry only a character count.
"""

from __future__ import annotations

import time
from typing import Any

# Chromium browsers share these shortcuts, and show the active tab in the window title.
BROWSER_PROCESSES = ("chrome.exe", "brave.exe", "msedge.exe", "opera.exe")
# Only windows whose whole text is the user's own document. Not browsers, terminals or password managers.
EDITOR_PROCESSES = frozenset({"notepad.exe", "notepad++.exe", "code.exe", "sublime_text.exe"})
MAX_TABS = 40
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


def copy_window_text_to_browser_tab(window: str, tab: str) -> dict[str, Any]:
    """Copy all the text from an editor window and paste it at the cursor in a browser tab. Never submits."""
    if not _real_input_on():
        return _fail("real_input_disabled", "Real keyboard input is off (EVA_ENABLE_REAL_INPUT), so I did not copy or paste anything.")
    from ..desktop.windows import find_window

    source = next((w for w in find_window(str(window or "")) if str(w.process_name or "").lower() in EDITOR_PROCESSES), None)
    if source is None:
        return _fail("editor_window_not_found", f"I could not find a text editor window matching \"{window}\". I only copy from Notepad, Notepad++, VS Code and Sublime Text.")
    if not _focus(source.hwnd) or not _in_front(source.hwnd):
        return _fail("editor_not_in_front", f"I could not bring \"{source.title}\" to the front, so I did not copy anything.")

    # A marker first, so a failed copy can never paste whatever was already on the clipboard (often a password).
    marker = f"nova-copy-{time.time_ns()}"
    _clipboard_set(marker)
    if not (_hotkey(["ctrl", "a"], f"select the text in {source.title}") and _hotkey(["ctrl", "c"], f"copy the text in {source.title}")):
        return _fail("copy_failed", f"Pressing the copy keys in \"{source.title}\" failed. Nothing was pasted.")
    _sleep(KEY_SETTLE_SECONDS)
    _press("right", "clear the selection so a stray key cannot replace the document")
    text = _clipboard_get()
    if not text or text == marker:
        _clipboard_set("")
        return _fail("nothing_copied", f"Nothing was copied from \"{source.title}\" (is it empty?). Nothing was pasted.")
    chars = len(text)

    switched = switch_browser_tab(tab)
    if not switched.get("ok"):
        return _fail(
            str(switched.get("error") or "tab_not_found"),
            f"I copied {chars} characters from \"{source.title}\" but did not paste them. {switched.get('message')} The text is on your clipboard.",
            chars=chars,
        )
    if not _hotkey(["ctrl", "v"], f"paste the text into the tab {switched.get('title')}"):
        return _fail("paste_failed", f"Pressing Ctrl+V failed. {chars} characters are still on your clipboard.", chars=chars)
    message = (
        f"Pasted {chars} characters from \"{source.title}\" into \"{switched.get('title')}\" at the cursor. I did not submit anything. "
        "I cannot see the page, so check it: if the box is empty, click inside it and press Ctrl+V, since the text is still on your clipboard."
    )
    return {"ok": True, "pasted": True, "verified": False, "chars": chars, "source": source.title, "tab": switched.get("title"), "message": message, "summary": message}
