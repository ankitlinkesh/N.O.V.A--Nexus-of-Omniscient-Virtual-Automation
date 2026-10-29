from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.parse
from typing import Any

from ..desktop.verifier import verify_url_opened as desktop_verify_url_opened
from ..desktop.windows import focus_window, get_active_window, list_open_windows
from ..tools.desktop import open_app
from ..tools.desktop import open_url as desktop_open_url
from ..tools.tavily_search import tavily_search_sync
from .safety import normalize_public_url, safe_search_url
from .state import current_state, invalidate_current_page, remember_live_probe, remember_navigation, remember_page, remember_search


BROWSER_PROCESSES = {"chrome.exe", "msedge.exe", "brave.exe", "firefox.exe", "opera.exe"}
CHROME_PROCESS = "chrome.exe"
CHROME_KEY_DELAY_MS = 80


def _chrome_executable() -> str | None:
    resolved = shutil.which("chrome.exe") or shutil.which("chrome")
    if resolved:
        return resolved
    candidates = [
        os.path.join(os.environ.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    return next((path for path in candidates if path and os.path.exists(path)), None)


def _focus_chrome() -> dict[str, Any]:
    window = next((item for item in browser_windows(limit=20) if str(item.get("process_name") or "").lower() == CHROME_PROCESS), None)
    if not window:
        return {"ok": False, "error": "chrome_window_not_found"}
    focus_window(str(window.get("process_name") or window.get("title") or "chrome"))
    return {"ok": True, "window": window}


def _send_chrome_keys(keys: str) -> dict[str, Any]:
    allowed = {"^l", "^t", "^w", "{F5}", "%{LEFT}", "%{RIGHT}", "^{F5}", "{TAB}", "{ENTER}"}
    if keys not in allowed:
        return {"ok": False, "error": "unsupported_key_sequence"}
    focus = _focus_chrome()
    if not focus.get("ok"):
        return focus
    ps = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Start-Sleep -Milliseconds {CHROME_KEY_DELAY_MS}
[System.Windows.Forms.SendKeys]::SendWait('{keys}')
"""
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=4,
        )
    except Exception as exc:
        return {"ok": False, "error": "chrome_sendkeys_failed", "detail": str(exc)[:160]}
    return {"ok": completed.returncode == 0, "keys": keys, "method": "visible_chrome_sendkeys", "returncode": completed.returncode}


def _set_clipboard_text(value: str) -> dict[str, Any]:
    if os.name != "nt":
        return {"ok": False, "error": "unsupported_platform"}
    ps = """
$ErrorActionPreference = 'Stop'
$text = [Console]::In.ReadToEnd()
Set-Clipboard -Value $text
"""
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            input=value,
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=4,
        )
    except Exception as exc:
        return {"ok": False, "error": "clipboard_copy_failed", "detail": str(exc)[:160]}
    return {"ok": completed.returncode == 0, "method": "set_clipboard", "returncode": completed.returncode}


def browser_windows(limit: int = 20) -> list[dict[str, Any]]:
    windows = []
    for window in list_open_windows(limit=80):
        process = (window.process_name or "").lower()
        title = window.title or ""
        if process in BROWSER_PROCESSES or "google chrome" in title.lower() or "microsoft edge" in title.lower():
            windows.append(window.as_dict())
        if len(windows) >= limit:
            break
    return windows


def active_browser_window() -> dict[str, Any] | None:
    windows = browser_windows(limit=1)
    return windows[0] if windows else None


def _copy_active_browser_url_once() -> dict[str, Any]:
    """Best-effort URL probe for explicit browser-page commands.

    This uses only the address bar and clipboard, then restores the previous
    clipboard value. It does not inspect DOM, cookies, browser storage, forms, or
    passwords.
    """
    if os.name != "nt":
        return {"ok": False, "error": "unsupported_platform"}
    window = active_browser_window()
    if not window:
        return {"ok": False, "error": "browser_window_not_found"}
    previous_active = get_active_window()
    focus_window(str(window.get("process_name") or window.get("title") or "chrome"))
    ps = r"""
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Windows.Forms
$old = Get-Clipboard -Raw
[System.Windows.Forms.SendKeys]::SendWait('^l')
Start-Sleep -Milliseconds 90
[System.Windows.Forms.SendKeys]::SendWait('^c')
Start-Sleep -Milliseconds 90
$url = Get-Clipboard -Raw
[System.Windows.Forms.SendKeys]::SendWait('{ESC}')
if ($null -ne $old) { Set-Clipboard -Value $old } else { Set-Clipboard -Value '' }
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Output $url
"""
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=4,
        )
    except Exception as exc:
        return {"ok": False, "error": "address_bar_probe_failed", "detail": str(exc)[:160]}
    finally:
        if previous_active is not None:
            try:
                focus_window(str(previous_active.process_name or previous_active.title))
            except Exception:
                pass
    if completed.returncode != 0:
        return {"ok": False, "error": "address_bar_probe_failed"}
    raw = (completed.stdout or "").strip().splitlines()
    candidate = raw[-1].strip() if raw else ""
    if not candidate:
        return {"ok": False, "error": "address_bar_empty"}
    try:
        url = normalize_public_url(candidate)
    except ValueError as exc:
        return {"ok": False, "error": "address_bar_not_public_url", "detail": str(exc)[:160]}
    remember_live_probe(url, title=str(window.get("title") or ""))
    return {
        "ok": True,
        "url": url,
        "title": window.get("title"),
        "method": "address_bar_clipboard_probe",
        "privacy_note": "Used one explicit address-bar copy. Did not read cookies, tokens, forms, passwords, or page storage.",
    }


def get_browser_status() -> dict[str, Any]:
    discovered = discover_current_url()
    windows = browser_windows(limit=20)
    state = current_state()
    return {
        "ok": True,
        "browser_detected": bool(windows),
        "active_window_title": windows[0].get("title") if windows else None,
        "known_current_url": state.get("url"),
        "known_current_title": state.get("title"),
        "url": state.get("url") if discovered.get("ok") and discovered.get("verified") else None,
        "title": state.get("title"),
        "source": state.get("source") or discovered.get("source") or "unknown",
        "verified": bool(discovered.get("ok") and discovered.get("verified")),
        "stale": bool(state.get("stale") or not discovered.get("ok")),
        "captured_at": state.get("captured_at"),
        "age_seconds": state.get("age_seconds"),
        "message": discovered.get("summary") or state.get("message") or "",
        "tabs_supported": False,
        "tabs_note": "Direct tab enumeration is not available without a browser extension or debugging port.",
        "open_browser_windows": windows,
    }


def open_url(url: str) -> dict[str, Any]:
    target = normalize_public_url(url)
    opened = desktop_open_url(target)
    verification = desktop_verify_url_opened(target)
    remember_navigation(target, source="cache", verified=bool(verification.get("verified")) if isinstance(verification, dict) else False)
    return {
        "ok": True,
        "url": target,
        "opened": True,
        "message": opened,
        "verified": bool(verification.get("verified")) if isinstance(verification, dict) else False,
        "verification": verification,
    }


def open_url_in_chrome(url: str) -> dict[str, Any]:
    target = normalize_public_url(url)
    executable = _chrome_executable()
    if executable:
        subprocess.Popen([executable, target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        opened = f"Opening {target} in Chrome."
    else:
        opened = open_app("chrome")
        time.sleep(0.2)
        desktop_open_url(target)
    time.sleep(0.3)
    verification = desktop_verify_url_opened(target)
    remember_navigation(target, source="cache", verified=bool(verification.get("verified")) if isinstance(verification, dict) else False)
    return {
        "ok": True,
        "url": target,
        "opened": True,
        "browser": "chrome",
        "message": opened,
        "verified": bool(verification.get("verified")) if isinstance(verification, dict) else False,
        "verification": verification,
        "verification_strategy": "Opened a public http/https URL in the installed Chrome app and checked visible browser windows.",
    }


def chrome_copy_current_url_to_clipboard() -> dict[str, Any]:
    discovered = discover_current_url()
    if not discovered.get("ok") or not discovered.get("url") or not discovered.get("verified"):
        return {
            "ok": False,
            "error": discovered.get("error") or "current_url_unverified",
            "summary": discovered.get("summary") or "I can't verify the current Chrome page right now, so I did not copy a stale URL.",
            "source": discovered.get("source") or "unknown",
            "verified": False,
            "stale": True,
        }
    url = normalize_public_url(str(discovered.get("url")))
    copied = _set_clipboard_text(url)
    if not copied.get("ok"):
        return copied
    return {
        "ok": True,
        "url": url,
        "copied": True,
        "message": "Copied the current browser URL.",
        "source": discovered.get("source"),
        "privacy_note": "Copied only the visible address-bar URL after an explicit user command. No page storage or form fields were read.",
    }


def chrome_new_tab() -> dict[str, Any]:
    result = _send_chrome_keys("^t")
    if result.get("ok"):
        invalidate_current_page("opening a new tab")
    return {"ok": bool(result.get("ok")), "action": "new_tab", "result": result, "message": "Opened a new Chrome tab." if result.get("ok") else "I could not open a new Chrome tab safely."}


def chrome_close_tab() -> dict[str, Any]:
    result = _send_chrome_keys("^w")
    if result.get("ok"):
        invalidate_current_page("closing a tab")
    return {"ok": bool(result.get("ok")), "action": "close_tab", "result": result, "message": "Closed the current Chrome tab." if result.get("ok") else "I could not close the Chrome tab safely."}


def chrome_reload() -> dict[str, Any]:
    result = _send_chrome_keys("{F5}")
    if result.get("ok"):
        invalidate_current_page("reloading the page")
    return {"ok": bool(result.get("ok")), "action": "reload", "result": result, "message": "Reloaded the current Chrome tab." if result.get("ok") else "I could not reload Chrome safely."}


def chrome_back() -> dict[str, Any]:
    result = _send_chrome_keys("%{LEFT}")
    if result.get("ok"):
        invalidate_current_page("browser back navigation")
    return {"ok": bool(result.get("ok")), "action": "back", "result": result, "message": "Sent Chrome back." if result.get("ok") else "I could not go back safely."}


def chrome_forward() -> dict[str, Any]:
    result = _send_chrome_keys("%{RIGHT}")
    if result.get("ok"):
        invalidate_current_page("browser forward navigation")
    return {"ok": bool(result.get("ok")), "action": "forward", "result": result, "message": "Sent Chrome forward." if result.get("ok") else "I could not go forward safely."}


def chrome_focus_address_bar() -> dict[str, Any]:
    result = _send_chrome_keys("^l")
    return {"ok": bool(result.get("ok")), "action": "focus_address_bar", "result": result, "message": "Focused the Chrome address bar." if result.get("ok") else "I could not focus Chrome's address bar safely."}


def chrome_activate_first_visible_result() -> dict[str, Any]:
    first_tab = _send_chrome_keys("{TAB}")
    time.sleep(0.25)
    enter = _send_chrome_keys("{ENTER}") if first_tab.get("ok") else {"ok": False, "error": "tab_focus_failed"}
    return {
        "ok": bool(first_tab.get("ok") and enter.get("ok")),
        "method": "bounded_visible_keyboard_activation",
        "sequence": [first_tab, enter],
        "verification_note": "Used only bounded visible Chrome keyboard input. Playback cannot be proven without reading page internals.",
    }


def open_search(query: str) -> dict[str, Any]:
    clean = str(query or "").strip()
    if not clean:
        raise ValueError("Search query is empty.")
    search_url = safe_search_url(clean)
    tavily_result = tavily_search_sync(clean)
    desktop_open_url(search_url)
    results = tavily_result.get("results") if isinstance(tavily_result.get("results"), list) else []
    remember_search(clean, search_url, results)
    return {
        "ok": True,
        "query": clean,
        "opened": True,
        "browser_url": search_url,
        "provider": tavily_result.get("provider") if isinstance(tavily_result, dict) else None,
        "answer": tavily_result.get("answer") if isinstance(tavily_result, dict) else "",
        "results": results,
        "tavily_ok": bool(tavily_result.get("ok")) if isinstance(tavily_result, dict) else False,
        "fallback": None if bool(tavily_result.get("ok")) else "browser",
        "error": tavily_result.get("error") if isinstance(tavily_result, dict) else None,
    }


def get_current_url() -> str | None:
    value = current_state().get("last_url")
    return str(value) if value else None


def discover_current_url() -> dict[str, Any]:
    probed = _copy_active_browser_url_once()
    if probed.get("ok") and probed.get("url"):
        return {
            "ok": True,
            "url": probed["url"],
            "source": "live_probe",
            "title": probed.get("title"),
            "verified": True,
            "stale": False,
            "captured_at": current_state().get("captured_at"),
            "age_seconds": current_state().get("age_seconds"),
        }
    state = current_state()
    if state.get("url"):
        return {
            "ok": False,
            "url": state.get("url"),
            "title": state.get("title"),
            "source": "cache",
            "verified": False,
            "stale": True,
            "captured_at": state.get("captured_at"),
            "age_seconds": state.get("age_seconds"),
            "error": probed.get("error") or "live_probe_failed",
            "summary": f"I can't verify the current Chrome page right now. Last known page was {state.get('url')}.",
        }
    return {**probed, "verified": False, "stale": True, "summary": "I can't verify the current Chrome page right now."}


def get_current_title() -> str | None:
    window = active_browser_window()
    if window and window.get("title"):
        return str(window.get("title"))
    value = current_state().get("last_title")
    return str(value) if value else None


def list_browser_tabs() -> dict[str, Any]:
    windows = browser_windows(limit=30)
    return {
        "ok": True,
        "supported": False,
        "tabs": [{"title": item.get("title"), "url": None, "process_name": item.get("process_name")} for item in windows],
        "note": "Eva can see browser window titles, but direct tab URLs need a browser extension or debugging port.",
    }


def verify_url_opened(url_or_domain: str) -> dict[str, Any]:
    return desktop_verify_url_opened(normalize_public_url(url_or_domain))
