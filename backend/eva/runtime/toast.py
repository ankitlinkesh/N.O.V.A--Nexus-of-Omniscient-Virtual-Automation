"""Windows toast delivery for timers and reminders (Phase 126).

A timer that only lands in a list nobody is looking at has not done its job, so
a firing one-shot also raises a desktop toast. No new dependency: it drives the
WinRT toast API through a bounded PowerShell subprocess.

Delivery is best-effort by design. The in-app notification is the record of
truth and is written before this is called; if the toast fails (no PowerShell,
focus-assist, a locked-down box) it logs and returns a result dict, and nothing
else is affected.

The title and body travel in environment variables, never spliced into the
script text, so reminder text cannot inject PowerShell. The script itself is a
constant.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

_ABSENT_OFF = {"0", "false", "no", "off"}
TOAST_TIMEOUT_SECONDS = 15
# PowerShell's own registered AppUserModelID: toasts from an unregistered app id
# are silently dropped by Windows, this one is always present.
_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$t = [System.Security.SecurityElement]::Escape($env:NOVA_TOAST_TITLE)
$b = [System.Security.SecurityElement]::Escape($env:NOVA_TOAST_BODY)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast scenario='reminder'><visual><binding template='ToastGeneric'><text>$t</text><text>$b</text></binding></visual></toast>")
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:NOVA_TOAST_APPID).Show($toast)
"""

# The last delivery attempt, for diagnosis (``toast_status``).
_last_result: dict[str, Any] = {}


def toasts_enabled(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    if env.get("PYTEST_CURRENT_TEST"):
        return False  # a test must never pop a real notification
    return env.get("EVA_TOASTS", "1").strip().lower() not in _ABSENT_OFF


def send_toast(title: str, body: str, *, runner: Callable | None = None, platform: str | None = None) -> dict[str, Any]:
    """Raise one toast, blocking up to ``TOAST_TIMEOUT_SECONDS``. Never raises."""
    result: dict[str, Any] = {"ok": False, "detail": ""}
    try:
        if (platform or sys.platform) != "win32":
            result["detail"] = "not windows"
        else:
            env = dict(os.environ)
            env["NOVA_TOAST_TITLE"] = str(title)[:120]
            env["NOVA_TOAST_BODY"] = str(body)[:400]
            env["NOVA_TOAST_APPID"] = _APP_ID
            run = runner or subprocess.run
            proc = run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _SCRIPT],
                env=env, capture_output=True, text=True, timeout=TOAST_TIMEOUT_SECONDS,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            result["ok"] = proc.returncode == 0
            if not result["ok"]:
                result["detail"] = (str(proc.stderr or proc.stdout or "")).strip()[:300] or f"exit {proc.returncode}"
    except Exception as exc:
        result["detail"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    if result["ok"]:
        logger.info("toast delivered: %s", title)
    else:
        logger.warning("toast not delivered (%s): %s", title, result["detail"])
    _last_result.clear()
    _last_result.update(result)
    return result


def toast_notifier(title: str, body: str) -> None:
    """The engine's notifier: fire-and-forget on a daemon thread, so a slow
    PowerShell start never stalls the timer loop or the event loop."""
    if not toasts_enabled():
        return
    threading.Thread(target=send_toast, args=(title, body), name="nova-toast", daemon=True).start()


def toast_status() -> dict[str, Any]:
    return {"enabled": toasts_enabled(), "last": dict(_last_result)}


__all__ = ["send_toast", "toast_notifier", "toast_status", "toasts_enabled"]
