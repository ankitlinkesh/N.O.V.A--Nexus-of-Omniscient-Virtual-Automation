from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from ..tools.desktop import BLOCKED_CLOSE_APP_NAMES, CLOSE_APP_PROCESS_NAMES, close_app_allowlist


SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_SHOWMAXIMIZED = 3
SW_RESTORE = 9
WM_CLOSE = 0x0010
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SPI_GETFOREGROUNDLOCKTIMEOUT = 0x2000
FOREGROUND_LOCK_TIMEOUT_REGISTRY_DEFAULT_MS = 200000


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    process_id: int
    process_name: str
    executable: str
    visible: bool = True

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data.pop("hwnd", None)
        return data


def _unsupported() -> bool:
    return os.name != "nt"


if not _unsupported():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.IsZoomed.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.POINTER(wintypes.DWORD), wintypes.UINT]
    user32.SystemParametersInfoW.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL


def _window_title(hwnd: int) -> str:
    if _unsupported():
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value.strip()


def _process_path(pid: int) -> str:
    if _unsupported() or pid <= 0:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _process_name(pid: int) -> tuple[str, str]:
    path = _process_path(pid)
    if not path:
        return "", ""
    return Path(path).name, path


def _window_info(hwnd: int) -> WindowInfo | None:
    if _unsupported():
        return None
    title = _window_title(hwnd)
    if not title:
        return None
    visible = bool(user32.IsWindowVisible(hwnd))
    if not visible:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process_name, executable = _process_name(int(pid.value))
    return WindowInfo(
        hwnd=int(hwnd),
        title=title,
        process_id=int(pid.value),
        process_name=process_name,
        executable=executable,
        visible=visible,
    )


def list_open_windows(limit: int = 80) -> list[WindowInfo]:
    if _unsupported():
        return []
    windows: list[WindowInfo] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, _lparam: int) -> bool:
        if len(windows) >= limit:
            return False
        info = _window_info(hwnd)
        if info is not None:
            windows.append(info)
        return True

    user32.EnumWindows(callback, 0)
    return windows


def get_active_window() -> WindowInfo | None:
    if _unsupported():
        return None
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    return _window_info(int(hwnd))


def _matches(info: WindowInfo, query: str) -> bool:
    clean = " ".join(query.lower().strip().split())
    if not clean:
        return False
    haystack = f"{info.title} {info.process_name} {info.executable}".lower()
    if clean in haystack:
        return True
    for part in clean.split():
        if len(part) >= 3 and part in haystack:
            return True
    return False


def find_window(query: str, limit: int = 10) -> list[WindowInfo]:
    return [window for window in list_open_windows() if _matches(window, query)][:limit]


def _window_reached_state(hwnd: int, command: int) -> bool:
    """Independently confirm ShowWindow's target state actually took effect.

    ShowWindow's own return value is NOT a success flag: per MSDN, it reports
    whether the window was PREVIOUSLY visible, not whether this call worked.
    Treating that as "it worked" is exactly the "ok: True regardless" pattern
    Phase 64 exists to remove, so this reads the real post-call window state
    instead (IsIconic/IsZoomed), the same way focus_window below independently
    reads GetForegroundWindow rather than trusting SetForegroundWindow's return.
    """
    if command == SW_SHOWMINIMIZED:
        return bool(user32.IsIconic(hwnd))
    if command == SW_SHOWMAXIMIZED:
        return bool(user32.IsZoomed(hwnd))
    if command == SW_RESTORE:
        return not bool(user32.IsIconic(hwnd)) and not bool(user32.IsZoomed(hwnd))
    return True


def _show_window(query: str, command: int) -> dict[str, object]:
    matches = find_window(query, limit=1)
    if not matches:
        return {"ok": False, "error": "window_not_found", "query": query}
    window = matches[0]
    if _unsupported():
        return {"ok": False, "error": "unsupported_platform", "query": query}
    user32.ShowWindow(window.hwnd, command)
    verified = _window_reached_state(window.hwnd, command)
    payload: dict[str, object] = {"ok": verified, "changed": verified, "window": window.as_dict()}
    if not verified:
        payload["error"] = "show_window_failed"
    return payload


def foreground_lock_timeout_ms() -> "int | None":
    """Read Windows' foreground lock timeout (SPI_GETFOREGROUNDLOCKTIMEOUT).

    A non-zero value means Windows will refuse programmatic foreground
    changes requested by a background process -- this is exactly the
    condition that makes focus_window's AttachThreadInput dance report
    SetForegroundWindow success while the foreground never actually moves
    (measured on real hardware, Phase 68). This function only READS the
    setting for diagnosis; see the comment on the SPI_SETFOREGROUNDLOCKTIMEOUT
    call we deliberately do NOT make, below.

    Never raises -- fails safe like the rest of this module by returning None
    on any failure (unsupported platform, or the OS call itself failing).
    """
    if _unsupported():
        return None
    try:
        value = wintypes.DWORD(0)
        ok = user32.SystemParametersInfoW(SPI_GETFOREGROUNDLOCKTIMEOUT, 0, ctypes.pointer(value), 0)
        if not ok:
            return None
        return int(value.value)
    except Exception:
        return None


# We deliberately never call SPI_SETFOREGROUNDLOCKTIMEOUT (or write the
# HKCU\Control Panel\Desktop\ForegroundLockTimeout registry value) anywhere in
# this module. Overriding the lock would let focus_window "succeed" only in an
# environment we forced into a state the user doesn't actually run in --
# exactly the kind of validation-against-a-fake-environment Phase 68 exists to
# avoid. If the lock is engaged, the honest answer is to say so and let the
# user bring the window forward themselves, not to silently change a
# system-wide Windows setting out from under them.


def _foreground_lock_explanation(timeout_ms: int) -> str:
    return (
        "Windows is currently blocking programmatic focus changes on this machine "
        f"(foreground lock timeout is set to {timeout_ms} ms, and the registry default is "
        f"{FOREGROUND_LOCK_TIMEOUT_REGISTRY_DEFAULT_MS}, so an application set this at runtime; "
        "it resets on reboot or sign-out). Bring the window forward yourself and I will continue."
    )


def _try_set_foreground(hwnd: int) -> None:
    """Best-effort attempt to bring ``hwnd`` to the foreground.

    A bare ``SetForegroundWindow`` is blocked by Windows' foreground lock when
    called from a background process -- measured (Phase 64) from a forced
    clean state: it silently no-ops. The AttachThreadInput dance below is the
    standard workaround and was verified to actually work on real hardware:
    temporarily merge input processing with the thread that owns the CURRENT
    foreground window (which is allowed to hand off focus), do the
    BringWindowToTop + SetForegroundWindow while attached, then always detach
    again. Never raises -- every call here is best-effort; the caller
    independently re-checks the real result via get_active_window(), so a
    failure here just means that check will (honestly) report it.
    """
    if _unsupported():
        return
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        fg = user32.GetForegroundWindow()
        t1 = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        t2 = user32.GetWindowThreadProcessId(hwnd, None)
        attached = False
        try:
            if t1 and t2 and t1 != t2:
                attached = bool(user32.AttachThreadInput(t1, t2, True))
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            # Always detach if we attached, even if BringWindowToTop/
            # SetForegroundWindow raised above -- a stuck attach is a global,
            # cross-process side effect (it would keep merging input
            # processing between these two threads long after this call
            # returns).
            if attached:
                user32.AttachThreadInput(t1, t2, False)
    except Exception:
        # Genuinely never raise: this is best-effort, and the caller
        # independently re-checks the real result via get_active_window(), so
        # swallowing here just means that check will (honestly) report the
        # failure instead of an unrelated ctypes exception surfacing instead.
        pass


def _wait_for_focus(hwnd: int, *, settle_timeout: float = 0.5, settle_interval: float = 0.05) -> tuple["WindowInfo | None", bool]:
    """Poll get_active_window() until ``hwnd`` is foreground or time runs out.

    An immediate read races the window manager: a real focus change that DID
    take effect was measured (Phase 64) still reading as unfocused at +0.00s,
    turning a success into a false negative. Polling a few times over a short
    bounded window fixes that without ever blocking indefinitely.
    """
    deadline = time.monotonic() + max(0.0, settle_timeout)
    active = get_active_window()
    while True:
        if active is not None and active.hwnd == hwnd:
            return active, True
        if time.monotonic() >= deadline:
            return active, False
        time.sleep(max(0.0, settle_interval))
        active = get_active_window()


def focus_window(query: str, *, settle_timeout: float = 0.5, settle_interval: float = 0.05) -> dict[str, object]:
    matches = find_window(query, limit=1)
    if not matches:
        return {"ok": False, "error": "window_not_found", "query": query}
    window = matches[0]
    if _unsupported():
        return {"ok": False, "error": "unsupported_platform", "query": query}
    _try_set_foreground(window.hwnd)
    active, verified = _wait_for_focus(window.hwnd, settle_timeout=settle_timeout, settle_interval=settle_interval)
    # `ok` must reflect reality, not just "the call was made": every caller in
    # this codebase treats result.get("ok") is True as proof the action
    # happened, so ok is tied to the INDEPENDENTLY verified outcome, not to
    # whether SetForegroundWindow claimed success (Phase 64, Defects 1+2).
    payload: dict[str, object] = {
        "ok": verified,
        "focused": verified,
        "verified": verified,
        "window": window.as_dict(),
        "active_window": active.as_dict() if active else None,
    }
    if not verified:
        payload["error"] = "focus_failed"
        lock_timeout_ms = foreground_lock_timeout_ms()
        if lock_timeout_ms:
            payload["message"] = _foreground_lock_explanation(lock_timeout_ms)
    return payload


def minimize_window(query: str) -> dict[str, object]:
    return _show_window(query, SW_SHOWMINIMIZED)


def maximize_window(query: str) -> dict[str, object]:
    return _show_window(query, SW_SHOWMAXIMIZED)


def restore_window(query: str) -> dict[str, object]:
    return _show_window(query, SW_RESTORE)


def _allowed_process_names() -> set[str]:
    allowed: set[str] = set()
    for app in close_app_allowlist():
        for process in CLOSE_APP_PROCESS_NAMES.get(app, ()):
            allowed.add(process.lower())
    return allowed


def _window_close_allowed(window: WindowInfo, query: str) -> tuple[bool, str]:
    process = (window.process_name or "").lower()
    query_clean = " ".join(query.lower().split())
    if query_clean in BLOCKED_CLOSE_APP_NAMES or process in BLOCKED_CLOSE_APP_NAMES:
        return False, "blocked_system_process"
    if process not in _allowed_process_names():
        return False, "not_in_safe_close_allowlist"
    return True, "allowed"


def close_window(query: str) -> dict[str, object]:
    matches = find_window(query, limit=1)
    if not matches:
        return {"ok": False, "error": "window_not_found", "query": query}
    window = matches[0]
    allowed, reason = _window_close_allowed(window, query)
    if not allowed:
        return {"ok": False, "error": reason, "query": query, "window": window.as_dict()}
    posted = bool(user32.PostMessageW(window.hwnd, WM_CLOSE, 0, 0)) if not _unsupported() else False
    return {"ok": posted, "closed": posted, "window": window.as_dict(), "note": "Sent WM_CLOSE to an allowlisted window."}


def windows_as_dicts(windows: Iterable[WindowInfo]) -> list[dict[str, object]]:
    return [window.as_dict() for window in windows]
