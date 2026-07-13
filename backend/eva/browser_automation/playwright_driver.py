"""Real Playwright DOM-automation adapter (Phase 32 browser hands).

Off by default: nothing launches a browser unless EVA_V2_PLAYWRIGHT_ENABLED is
truthy (get_v2_feature_flags().playwright_enabled). With the flag off every
entry point returns a disabled result, so the test/verifier suite never spawns
Chromium. When enabled, a single headless Chromium session is reused across
calls; navigation is restricted to public http(s) hosts (no localhost/private
targets), and no cookie/token/storage reads are exposed.
"""
from __future__ import annotations

import os
import threading
from typing import Any
from urllib.parse import urlparse

from ..browser.safety import is_local_or_private_host, normalize_public_url
from ..runtime.feature_flags import get_v2_feature_flags

# Chromium binaries live off the system drive on this machine. Default the
# lookup path if the operator hasn't set it, but never override an explicit one.
_DEFAULT_BROWSERS_PATH = r"D:\eva-agent-tools\playwright-browsers"

# Cap page-text extraction so a huge page can't flood a tool result.
_MAX_SNAPSHOT_CHARS = 4000

_lock = threading.Lock()
_session: dict[str, Any] = {"pw": None, "browser": None, "page": None}


def is_playwright_available() -> bool:
    try:
        import playwright  # type: ignore  # noqa: F401
    except Exception:
        return False
    return True


def playwright_status() -> dict[str, Any]:
    flags = get_v2_feature_flags()
    available = is_playwright_available()
    enabled = bool(flags.playwright_enabled and available)
    return {
        "ok": True,
        "available": available,
        "enabled": enabled,
        "session_open": _session["page"] is not None,
        "message": "Playwright adapter is optional and disabled unless EVA_V2_PLAYWRIGHT_ENABLED=true.",
        "safety": "Public http(s) hosts only; no cookie, token, password, or storage reads are exposed.",
    }


def _disabled() -> dict[str, Any]:
    return {"ok": False, "error": "playwright_disabled", "message": "Playwright automation is unavailable or disabled; existing Chrome skills remain active."}


def _headless() -> bool:
    raw = os.environ.get("EVA_V2_PLAYWRIGHT_HEADLESS", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _ensure_session() -> dict[str, Any]:
    """Launch (or reuse) the single Chromium session. Caller holds _lock."""
    if _session["page"] is not None:
        return {"ok": True}
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", _DEFAULT_BROWSERS_PATH)
    from playwright.sync_api import sync_playwright  # type: ignore

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=_headless())
    page = browser.new_page()
    _session.update(pw=pw, browser=browser, page=page)
    return {"ok": True}


def _reject_private(url: str) -> str | None:
    host = urlparse(url).hostname or ""
    if is_local_or_private_host(host):
        return host
    return None


def open_url(url: str) -> dict[str, Any]:
    if not playwright_status()["enabled"]:
        return _disabled()
    try:
        safe = normalize_public_url(url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    blocked = _reject_private(safe)
    if blocked is not None:
        return {"ok": False, "error": "private_host_blocked", "host": blocked}
    with _lock:
        try:
            _ensure_session()
            page = _session["page"]
            page.goto(safe, wait_until="domcontentloaded", timeout=30000)
            return {"ok": True, "url": page.url, "title": page.title()}
        except Exception as exc:  # pragma: no cover - live browser errors
            return {"ok": False, "error": "navigation_failed", "detail": str(exc), "url": safe}


def get_page_snapshot() -> dict[str, Any]:
    if not playwright_status()["enabled"]:
        return _disabled()
    with _lock:
        page = _session["page"]
        if page is None:
            return {"ok": False, "error": "no_open_page", "message": "Call open_url first."}
        try:
            text = page.inner_text("body")
            return {
                "ok": True,
                "url": page.url,
                "title": page.title(),
                "text": text[:_MAX_SNAPSHOT_CHARS],
                "truncated": len(text) > _MAX_SNAPSHOT_CHARS,
            }
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": "snapshot_failed", "detail": str(exc)}


def _locator(page, target: dict[str, Any]):
    """Resolve a target dict {role,name,text,selector} to a Playwright locator."""
    if target.get("selector"):
        return page.locator(str(target["selector"]))
    role = target.get("role")
    name = target.get("name")
    if role:
        return page.get_by_role(str(role), name=str(name)) if name else page.get_by_role(str(role))
    if target.get("text"):
        return page.get_by_text(str(target["text"]))
    if name:
        return page.get_by_text(str(name))
    raise ValueError("target must include selector, role, or text")


def locate_element(role: str | None = None, name: str | None = None, text: str | None = None) -> dict[str, Any]:
    if not playwright_status()["enabled"]:
        return {"ok": False, "error": "playwright_disabled", "query": {"role": role, "name": name, "text": text}}
    with _lock:
        page = _session["page"]
        if page is None:
            return {"ok": False, "error": "no_open_page"}
        try:
            loc = _locator(page, {"role": role, "name": name, "text": text})
            count = loc.count()
            return {"ok": True, "found": count > 0, "count": count, "query": {"role": role, "name": name, "text": text}}
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": "locate_failed", "detail": str(exc)}


def click_element(target: dict[str, Any]) -> dict[str, Any]:
    if not playwright_status()["enabled"]:
        return _disabled()
    with _lock:
        page = _session["page"]
        if page is None:
            return {"ok": False, "error": "no_open_page"}
        try:
            self_loc = _locator(page, target or {})
            self_loc.first.click(timeout=10000)
            return {"ok": True, "clicked": target, "url": page.url}
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": "click_failed", "detail": str(exc), "target": target}


def type_text(target: dict[str, Any], text: str) -> dict[str, Any]:
    if not playwright_status()["enabled"]:
        return _disabled()
    with _lock:
        page = _session["page"]
        if page is None:
            return {"ok": False, "error": "no_open_page"}
        try:
            loc = _locator(page, target or {})
            loc.first.fill(str(text), timeout=10000)
            return {"ok": True, "filled": target, "chars": len(str(text)), "url": page.url}
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": "type_failed", "detail": str(exc), "target": target}


def verify_page(expected_url: str | None = None, expected_title: str | None = None, expected_text: str | None = None) -> dict[str, Any]:
    if not playwright_status()["enabled"]:
        return {"ok": False, "verified": False, "error": "playwright_disabled", "expected_url": expected_url, "expected_title": expected_title, "expected_text": expected_text}
    with _lock:
        page = _session["page"]
        if page is None:
            return {"ok": False, "verified": False, "error": "no_open_page"}
        try:
            checks = []
            if expected_url is not None:
                checks.append(expected_url in page.url)
            if expected_title is not None:
                checks.append(expected_title.lower() in (page.title() or "").lower())
            if expected_text is not None:
                checks.append(expected_text.lower() in (page.inner_text("body") or "").lower())
            verified = bool(checks) and all(checks)
            return {"ok": True, "verified": verified, "url": page.url, "title": page.title()}
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "verified": False, "error": "verify_failed", "detail": str(exc)}


def close_browser() -> dict[str, Any]:
    """Tear down the session if one is open. Safe to call when nothing is open."""
    with _lock:
        page, browser, pw = _session["page"], _session["browser"], _session["pw"]
        _session.update(pw=None, browser=None, page=None)
    for closer in (getattr(browser, "close", None), getattr(pw, "stop", None)):
        if closer is not None:
            try:
                closer()
            except Exception:  # pragma: no cover
                pass
    return {"ok": True, "closed": page is not None}
