"""Clipboard read/write (Phase 128), ctypes + Win32 only -- no new dependency.

Two tools share this module with deliberately different trust:

- ``clipboard_write`` sets text the USER typed in their request. A reversible local
  preference-class action (SAFE_LOCAL_UI, no prompt). It reads the clipboard back
  and reports what it READ, not what it intended (the Phase 127 convention).
- ``clipboard_read`` returns whatever is on the clipboard, which is routinely a
  password or a one-time code and is ALSO untrusted (anything can put anything on
  it). The registry makes it confirm-class; this module masks secret-looking text
  in the reply, and ``redact_for_log`` keeps clipboard/file contents out of logs.

Every OS touch sits behind ``_get_text`` / ``_set_text`` so tests replace exactly
those two (conftest's autouse guard fails any test that reaches the real ones).
"""

from __future__ import annotations

import re
import time
from typing import Any

CLIPBOARD_MAX_CHARS = 20_000
WRITE_MAX_CHARS = 100_000

_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002


class ClipboardError(RuntimeError):
    pass


def _sleep(seconds: float) -> None:  # seam: tests do not wait
    time.sleep(seconds)


def _win32():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    return ctypes, user32, kernel32


def _open(user32) -> None:
    # Another process may hold the clipboard for a few milliseconds.
    for _ in range(10):
        if user32.OpenClipboard(None):
            return
        _sleep(0.05)
    raise ClipboardError("the clipboard is busy (another program is using it)")


def _get_text() -> str | None:
    """Clipboard text, or None when it holds no text (an image, files, nothing)."""
    ctypes, user32, kernel32 = _win32()
    _open(user32)
    try:
        if not user32.IsClipboardFormatAvailable(_CF_UNICODETEXT):
            return None
        handle = user32.GetClipboardData(_CF_UNICODETEXT)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _set_text(text: str) -> None:
    ctypes, user32, kernel32 = _win32()
    data = (text + "\0").encode("utf-16-le")
    _open(user32)
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
        if not handle:
            raise ClipboardError("could not allocate memory for the clipboard")
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            raise ClipboardError("could not lock clipboard memory")
        try:
            ctypes.memmove(pointer, data, len(data))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(_CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            raise ClipboardError("Windows refused to set the clipboard")
    finally:
        user32.CloseClipboard()


# --------------------------------------------------------------------- masking
_NOT_CREDENTIALS = frozenset({"email", "phone", "windows_path"})
_URLISH = re.compile(r"^(?:https?://|www\.)\S+$", re.I)


def looks_secret_like(text: object) -> bool:
    """Would showing/logging this be showing a password, key or one-time code?

    Deliberately over-inclusive: a false positive only masks, never leaks.
    Known secret shapes (redaction patterns), a live environment secret, a bare
    4-10 digit code, or one unbroken mixed-class token (password-shaped).
    """
    value = str(text or "").strip()
    if not value:
        return False
    try:
        from ..privacy.redaction import redact_secrets
        from ..privacy.secrets_broker import contains_secret_leak

        _redacted, events = redact_secrets(value)
        # An email, phone number or local path is private but not a credential;
        # masking every copied address would make the tool useless.
        if any(e.get("type") not in _NOT_CREDENTIALS for e in events) or contains_secret_leak(value):
            return True
    except Exception:
        return True  # cannot tell -> mask
    if re.fullmatch(r"\d{4,10}", value) or re.fullmatch(r"\d{3}[ -]\d{3}", value):
        return True
    if re.search(r"\s", value) or _URLISH.match(value) or not 8 <= len(value) <= 128:
        return False
    classes = sum(bool(re.search(pattern, value)) for pattern in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    return classes >= 3


def mask(text: str) -> str:
    return f"{'*' * min(len(text), 12)} ({len(text)} characters, masked)"


def redact_for_log(tool: str, args: Any = None, result: Any = None) -> tuple[Any, Any]:
    """(args, result) safe to write to a durable event log.

    File and clipboard CONTENT never goes to the log (it can be anything, and the
    log is plaintext); clipboard.write's text is kept only when it is not
    secret-looking. Everything else passes through untouched.
    """
    if tool in {"file.read_text", "clipboard.read"} and isinstance(result, dict) and "text" in result:
        result = {**result, "text": f"[{len(str(result.get('text') or ''))} characters of content not logged]"}
    if tool == "clipboard.write" and isinstance(args, dict) and "text" in args:
        text = str(args.get("text") or "")
        if looks_secret_like(text):
            args = {**args, "text": mask(text)}
    return args, result


# ----------------------------------------------------------------------- tools
def clipboard_write(text: str) -> dict[str, Any]:
    value = str(text if text is not None else "")
    if not value.strip():
        return {"ok": False, "error": "empty_text", "message": "There is nothing to copy: the text was empty."}
    if len(value) > WRITE_MAX_CHARS:
        return {"ok": False, "error": "too_long", "message": f"That is {len(value)} characters; I only copy up to {WRITE_MAX_CHARS} at a time."}
    try:
        _set_text(value)
        read_back = _get_text()
    except ClipboardError as exc:
        return {"ok": False, "error": "clipboard_unavailable", "message": f"I couldn't use the clipboard: {exc}."}
    except Exception as exc:  # ctypes / OS failure
        return {"ok": False, "error": "clipboard_unavailable", "message": f"I couldn't use the clipboard: {type(exc).__name__}."}
    if read_back != value:
        return {
            "ok": False,
            "error": "readback_mismatch",
            "message": "I set the clipboard but reading it back did not match, so I can't say it was copied.",
            "verified": False,
        }
    if looks_secret_like(value) or len(value) > 80 or "\n" in value:
        message = f"Copied {len(value)} characters to your clipboard."
    else:
        message = f'Copied "{value}" to your clipboard.'
    return {"ok": True, "chars": len(value), "verified": True, "message": message}


def clipboard_read() -> dict[str, Any]:
    try:
        text = _get_text()
    except ClipboardError as exc:
        return {"ok": False, "error": "clipboard_unavailable", "message": f"I couldn't read the clipboard: {exc}."}
    except Exception as exc:
        return {"ok": False, "error": "clipboard_unavailable", "message": f"I couldn't read the clipboard: {type(exc).__name__}."}
    if text is None or not text.strip():
        return {
            "ok": True,
            "empty": True,
            "text": "",
            "chars": 0,
            "untrusted": True,
            "message": "Your clipboard is empty, or it holds something that isn't text (an image or files).",
        }
    total = len(text)
    shown = text[:CLIPBOARD_MAX_CHARS]
    secret = looks_secret_like(shown if len(shown) <= 4096 else shown[:4096])
    result: dict[str, Any] = {
        "ok": True,
        "text": mask(shown) if secret else shown,
        "chars": len(shown),
        "total_chars": total,
        "truncated": total > len(shown),
        "masked": secret,
        # Anything can put anything on a clipboard: this is data, never instructions.
        "untrusted": True,
    }
    if secret:
        result["message"] = "Your clipboard holds something that looks like a password, key or code, so I've masked it."
    return result
