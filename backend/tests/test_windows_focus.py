"""Executable spec for backend/eva/desktop/windows.py's focus_window (Phase 64,
Defects 1+2).

Measured from a forced clean state (Notepad foreground, asked to focus
Chrome), the pre-Phase-64 focus_window returned:

    ok=True focused=False verified=False

A bare ``user32.SetForegroundWindow(hwnd)`` is blocked by Windows' foreground
lock when called from a background process, so the focus silently never took
effect -- and ``ok`` was hardcoded ``True`` regardless, so every caller (the
house convention everywhere else is ``result.get("ok") is True`` means
success) read total failure as success.

The fix has two parts, both covered here:

  1. Actually attempt the focus change with the AttachThreadInput dance
     (``_try_set_foreground``), and poll ``get_active_window()`` over a short
     bounded window rather than reading it immediately (``_wait_for_focus``)
     -- an immediate read races the window manager and can see a real,
     completed focus change as if it had not happened.
  2. ``ok`` is tied to the independently verified outcome, never to whether
     the OS call claimed success.

Everything here is offline and deterministic: find_window, get_active_window,
and the win32 call surface are all monkeypatched, so no test drives a real
desktop or waits out the real (up to ~0.5s) default settle window -- each
passes a small explicit settle_timeout/settle_interval instead.
"""

from __future__ import annotations

import pytest

from eva.desktop import windows as windows_module
from eva.desktop.windows import WindowInfo, focus_window

CHROME = WindowInfo(hwnd=4242, title="Google Chrome", process_id=111, process_name="chrome.exe", executable=r"C:\chrome\chrome.exe")
NOTEPAD = WindowInfo(hwnd=99, title="Untitled - Notepad", process_id=222, process_name="notepad.exe", executable=r"C:\Windows\notepad.exe")


# -- 1. The exact CONFIRMED regression: ok must be False when focus never ---
#       took effect, not True with focused=False/verified=False buried inside.


def test_focus_window_ok_false_when_focus_never_takes_effect(monkeypatch):
    monkeypatch.setattr(windows_module, "find_window", lambda query, limit=1: [CHROME])
    # SetForegroundWindow silently no-ops from a background process (the
    # measured behavior); stub the OS-touching half out entirely so the test
    # is offline, and pin what was actually measured: the foreground window
    # never moves off Notepad.
    monkeypatch.setattr(windows_module, "_try_set_foreground", lambda hwnd: None)
    monkeypatch.setattr(windows_module, "get_active_window", lambda: NOTEPAD)

    result = focus_window("chrome", settle_timeout=0.05, settle_interval=0.01)

    assert result["ok"] is False, f"ok must reflect that focus did NOT happen, got {result}"
    assert result["focused"] is False
    assert result["verified"] is False
    assert result["error"] == "focus_failed"
    # The actual foreground window must be in the payload so the failure is
    # diagnosable, not just a bare boolean.
    assert result["active_window"]["title"] == "Untitled - Notepad"
    assert result["window"]["title"] == "Google Chrome"


# -- 2. ok is True only when the foreground window REALLY matches -----------


def test_focus_window_ok_true_when_foreground_really_matches(monkeypatch):
    monkeypatch.setattr(windows_module, "find_window", lambda query, limit=1: [CHROME])
    monkeypatch.setattr(windows_module, "_try_set_foreground", lambda hwnd: None)
    monkeypatch.setattr(windows_module, "get_active_window", lambda: CHROME)

    result = focus_window("chrome", settle_timeout=0.05, settle_interval=0.01)

    assert result["ok"] is True
    assert result["focused"] is True
    assert result["verified"] is True
    assert "error" not in result
    assert result["active_window"]["title"] == "Google Chrome"


def test_focus_window_ok_false_when_a_different_window_is_foreground(monkeypatch):
    """Some other window (not Notepad, not Chrome) ends up foreground --
    verified must key on the REQUESTED window's hwnd, not merely on "some
    window is now focused"."""
    other = WindowInfo(hwnd=7, title="Calculator", process_id=333, process_name="calc.exe", executable=r"C:\calc.exe")
    monkeypatch.setattr(windows_module, "find_window", lambda query, limit=1: [CHROME])
    monkeypatch.setattr(windows_module, "_try_set_foreground", lambda hwnd: None)
    monkeypatch.setattr(windows_module, "get_active_window", lambda: other)

    result = focus_window("chrome", settle_timeout=0.05, settle_interval=0.01)

    assert result["ok"] is False
    assert result["verified"] is False


# -- 3. Poll over a short bounded window instead of reading immediately -----


def test_focus_window_polls_before_giving_up_on_a_late_focus_change(monkeypatch):
    """An immediate read races the window manager -- a real focus change that
    DID take effect can still read as unfocused at +0.00s. Simulates that:
    the first two reads see the stale (pre-focus) window, only the third read
    (after the OS catches up) sees the real, completed change."""
    monkeypatch.setattr(windows_module, "find_window", lambda query, limit=1: [CHROME])
    monkeypatch.setattr(windows_module, "_try_set_foreground", lambda hwnd: None)

    reads = {"n": 0}

    def flaky_get_active_window():
        reads["n"] += 1
        return NOTEPAD if reads["n"] < 3 else CHROME

    monkeypatch.setattr(windows_module, "get_active_window", flaky_get_active_window)

    result = focus_window("chrome", settle_timeout=0.3, settle_interval=0.01)

    assert result["ok"] is True, f"a single immediate read would have wrongly reported failure: {result}"
    assert reads["n"] >= 3, "must poll more than once before succeeding"


def test_focus_window_gives_up_after_the_settle_window_elapses(monkeypatch):
    """The poll must still be BOUNDED -- a focus that never actually lands
    must not hang forever."""
    monkeypatch.setattr(windows_module, "find_window", lambda query, limit=1: [CHROME])
    monkeypatch.setattr(windows_module, "_try_set_foreground", lambda hwnd: None)
    monkeypatch.setattr(windows_module, "get_active_window", lambda: NOTEPAD)

    result = focus_window("chrome", settle_timeout=0.05, settle_interval=0.01)

    assert result["ok"] is False
    assert result["error"] == "focus_failed"


# -- 4. window_not_found / unsupported_platform stay honest and unaffected --


def test_focus_window_reports_window_not_found(monkeypatch):
    monkeypatch.setattr(windows_module, "find_window", lambda query, limit=1: [])

    result = focus_window("some app that is not open")

    assert result["ok"] is False
    assert result["error"] == "window_not_found"


# -- 5. The AttachThreadInput dance always detaches, even on failure --------


class _FakeUser32:
    """Records every win32 call _try_set_foreground makes, so the test can
    assert on ORDER and on the always-detach invariant without touching a
    real window. BringWindowToTop raises to simulate a mid-sequence failure."""

    def __init__(self, *, raise_on_bring_to_top: bool = False) -> None:
        self.calls: list[tuple] = []
        self._raise_on_bring_to_top = raise_on_bring_to_top

    def ShowWindow(self, hwnd, cmd):
        self.calls.append(("ShowWindow", hwnd, cmd))
        return 1

    def GetForegroundWindow(self):
        return 555

    def GetWindowThreadProcessId(self, hwnd, _out):
        # Distinct, nonzero thread ids for the current-foreground window (555)
        # vs. the target window, so the attach path is actually exercised.
        return 10 if hwnd == 555 else 20

    def AttachThreadInput(self, t1, t2, flag):
        self.calls.append(("AttachThreadInput", t1, t2, bool(flag)))
        return 1

    def BringWindowToTop(self, hwnd):
        self.calls.append(("BringWindowToTop", hwnd))
        if self._raise_on_bring_to_top:
            raise OSError("simulated ctypes failure")

    def SetForegroundWindow(self, hwnd):
        self.calls.append(("SetForegroundWindow", hwnd))
        return 1


def test_try_set_foreground_attaches_then_detaches_on_the_happy_path(monkeypatch):
    fake = _FakeUser32()
    monkeypatch.setattr(windows_module, "user32", fake)

    windows_module._try_set_foreground(999)

    attach_calls = [c for c in fake.calls if c[0] == "AttachThreadInput"]
    assert attach_calls == [("AttachThreadInput", 10, 20, True), ("AttachThreadInput", 10, 20, False)], fake.calls
    assert ("BringWindowToTop", 999) in fake.calls
    assert ("SetForegroundWindow", 999) in fake.calls


def test_try_set_foreground_always_detaches_even_when_bring_to_top_raises(monkeypatch):
    fake = _FakeUser32(raise_on_bring_to_top=True)
    monkeypatch.setattr(windows_module, "user32", fake)

    # Must never raise -- it is best-effort, and the caller independently
    # re-verifies via get_active_window().
    windows_module._try_set_foreground(999)

    attach_calls = [c for c in fake.calls if c[0] == "AttachThreadInput"]
    assert attach_calls[0] == ("AttachThreadInput", 10, 20, True), fake.calls
    assert attach_calls[-1] == ("AttachThreadInput", 10, 20, False), (
        f"must always detach in a finally, even when BringWindowToTop raised (a stuck attach is a "
        f"global, cross-process side effect): {fake.calls}"
    )
    # SetForegroundWindow must never have been reached after the raise.
    assert ("SetForegroundWindow", 999) not in fake.calls


# -- 6. _show_window (minimize/maximize/restore) is honest too --------------
#       (Defect 2's "check the other functions ... and fix consistently")


def test_minimize_window_reports_ok_false_when_not_actually_minimized(monkeypatch):
    from eva.desktop.windows import minimize_window

    monkeypatch.setattr(windows_module, "find_window", lambda query, limit=1: [CHROME])
    monkeypatch.setattr(windows_module.user32, "ShowWindow", lambda hwnd, cmd: 1, raising=False)
    monkeypatch.setattr(windows_module.user32, "IsIconic", lambda hwnd: 0, raising=False)  # never actually minimized

    result = minimize_window("chrome")

    assert result["ok"] is False, f"ShowWindow's return value is not a success flag; ok must reflect real state: {result}"
    assert result["error"] == "show_window_failed"


def test_minimize_window_reports_ok_true_when_actually_minimized(monkeypatch):
    from eva.desktop.windows import minimize_window

    monkeypatch.setattr(windows_module, "find_window", lambda query, limit=1: [CHROME])
    monkeypatch.setattr(windows_module.user32, "ShowWindow", lambda hwnd, cmd: 0, raising=False)
    monkeypatch.setattr(windows_module.user32, "IsIconic", lambda hwnd: 1, raising=False)

    result = minimize_window("chrome")

    assert result["ok"] is True
    assert result["changed"] is True


# -- 7. Phase 68: foreground_lock_timeout_ms is a diagnosis-only reader, and --
#       focus_window explains a WHY when (and only when) the lock is engaged.
#
# Measured on real hardware: SystemParametersInfoW(SPI_GETFOREGROUNDLOCKTIMEOUT)
# returned 2147483647 (INT_MAX) even though the registry default is 200000 --
# some application set the lock at runtime (SPIF_UPDATEINIFILE was not used,
# so it is transient and resets on reboot/sign-out). Under that condition a
# bare SetForegroundWindow honestly returns False, but the AttachThreadInput
# dance in _try_set_foreground returns TRUE while the foreground genuinely
# never moves -- the Win32 API lies. Phase 64 already made `ok` track the
# independently-verified outcome instead of that lying return value; this
# phase only adds an explanation of WHY it failed, never changes ok/verified.


def test_foreground_lock_timeout_ms_never_raises_and_returns_none_on_a_raising_call(monkeypatch):
    def failing(action, param, pv, flag):
        raise OSError("simulated ctypes failure")

    monkeypatch.setattr(windows_module.user32, "SystemParametersInfoW", failing, raising=False)

    assert windows_module.foreground_lock_timeout_ms() is None


def test_foreground_lock_timeout_ms_returns_none_when_the_call_reports_failure(monkeypatch):
    # BOOL return of 0/False means the OS call itself failed -- not "the
    # timeout is zero", which is a legitimate value handled separately below.
    monkeypatch.setattr(windows_module.user32, "SystemParametersInfoW", lambda *a: 0, raising=False)

    assert windows_module.foreground_lock_timeout_ms() is None


def test_foreground_lock_timeout_ms_returns_the_real_int_on_success(monkeypatch):
    def fake_spi(action, param, pv, flag):
        pv.contents.value = 2147483647
        return 1

    monkeypatch.setattr(windows_module.user32, "SystemParametersInfoW", fake_spi, raising=False)

    assert windows_module.foreground_lock_timeout_ms() == 2147483647


def test_focus_window_failure_mentions_the_lock_when_it_is_engaged(monkeypatch):
    monkeypatch.setattr(windows_module, "find_window", lambda query, limit=1: [CHROME])
    monkeypatch.setattr(windows_module, "_try_set_foreground", lambda hwnd: None)
    monkeypatch.setattr(windows_module, "get_active_window", lambda: NOTEPAD)
    monkeypatch.setattr(windows_module, "foreground_lock_timeout_ms", lambda: 2147483647)

    result = focus_window("chrome", settle_timeout=0.05, settle_interval=0.01)

    assert result["ok"] is False
    assert result["verified"] is False
    assert result["error"] == "focus_failed"
    assert "2147483647" in result["message"]
    assert "200000" in result["message"]


def test_focus_window_failure_does_not_mention_the_lock_when_it_is_not_engaged(monkeypatch):
    """The message must not become boilerplate glued onto every failure --
    when the timeout is 0 (not engaged), this failure has some other cause
    and must not falsely blame the foreground lock."""
    monkeypatch.setattr(windows_module, "find_window", lambda query, limit=1: [CHROME])
    monkeypatch.setattr(windows_module, "_try_set_foreground", lambda hwnd: None)
    monkeypatch.setattr(windows_module, "get_active_window", lambda: NOTEPAD)
    monkeypatch.setattr(windows_module, "foreground_lock_timeout_ms", lambda: 0)

    result = focus_window("chrome", settle_timeout=0.05, settle_interval=0.01)

    assert result["ok"] is False
    assert result["error"] == "focus_failed"
    assert "message" not in result


def test_focus_window_success_never_mentions_the_lock(monkeypatch):
    monkeypatch.setattr(windows_module, "find_window", lambda query, limit=1: [CHROME])
    monkeypatch.setattr(windows_module, "_try_set_foreground", lambda hwnd: None)
    monkeypatch.setattr(windows_module, "get_active_window", lambda: CHROME)
    # Even if the lock happens to be engaged, a verified success must not
    # carry a lock explanation -- the explanation only belongs on failure.
    monkeypatch.setattr(windows_module, "foreground_lock_timeout_ms", lambda: 2147483647)

    result = focus_window("chrome", settle_timeout=0.05, settle_interval=0.01)

    assert result["ok"] is True
    assert "message" not in result
