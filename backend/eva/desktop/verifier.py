from __future__ import annotations

import time
import urllib.parse
from typing import Any

from ..tools.desktop import APP_ALIASES
from .windows import find_window, get_active_window


def _app_queries(app: str) -> list[str]:
    clean = app.strip().lower()
    for canonical, aliases in APP_ALIASES.items():
        if clean == canonical or clean in aliases:
            return [canonical, *aliases]
    return [clean]


def verify_window_focused(query: str, *, retries: int = 4, delay_seconds: float = 0.2) -> dict[str, Any]:
    """Best-effort check that ``query`` names the CURRENT foreground window.

    Retries like its siblings below (verify_app_opened / verify_folder_opened /
    verify_url_opened), which were already written to expect that a real
    window change can take a moment to land. This one was the odd one out
    with a single immediate read (Phase 64) -- and a focus change landing a
    moment after the call that caused it returns is exactly the kind of race
    that produced a false failure for a genuinely successful action. It is
    called independently of whatever triggered the focus change (a fresh
    postcondition check right after a tool returns, or verify_last_action at
    an arbitrary later time), so it needs to be robust on its own rather than
    relying on the caller having already settled.
    """
    active = None
    verified = False
    for _ in range(max(1, retries)):
        active = get_active_window()
        if active is not None:
            haystack = f"{active.title} {active.process_name}".lower()
            verified = any(part in haystack for part in query.lower().split() if len(part) >= 3)
        if verified:
            break
        time.sleep(delay_seconds)
    if active is None:
        return {"ok": False, "verified": False, "error": "active_window_unavailable", "query": query}
    return {"ok": True, "verified": verified, "query": query, "active_window": active.as_dict()}


def verify_app_opened(app: str, *, retries: int = 4, delay_seconds: float = 0.2) -> dict[str, Any]:
    queries = _app_queries(app)
    matches = []
    for _ in range(max(1, retries)):
        matches = [match for query in queries for match in find_window(query, limit=3)]
        if matches:
            break
        time.sleep(delay_seconds)
    return {
        "ok": True,
        "verified": bool(matches),
        "target": app,
        "matches": [match.as_dict() for match in matches[:5]],
        "message": f"{app} is open." if matches else f"I could not verify a {app} window.",
    }


def verify_folder_opened(folder: str, *, retries: int = 4, delay_seconds: float = 0.2) -> dict[str, Any]:
    query = folder.strip().lower()
    matches = []
    for _ in range(max(1, retries)):
        matches = find_window(query, limit=5)
        if matches:
            break
        time.sleep(delay_seconds)
    return {
        "ok": True,
        "verified": bool(matches),
        "target": folder,
        "matches": [match.as_dict() for match in matches[:5]],
        "message": f"{folder} looks open." if matches else f"I opened it, but could not verify the folder window.",
    }


def verify_url_opened(url_or_domain: str, *, retries: int = 3, delay_seconds: float = 0.2) -> dict[str, Any]:
    target = url_or_domain.strip()
    parsed = urllib.parse.urlparse(target if "://" in target else "https://" + target)
    domain = parsed.netloc.lower().replace("www.", "")
    query = domain.split(":")[0] if domain else target
    matches = []
    for _ in range(max(1, retries)):
        matches = find_window(query, limit=5)
        if matches:
            break
        time.sleep(delay_seconds)
    return {
        "ok": True,
        "verified": bool(matches),
        "target": target,
        "domain": domain,
        "matches": [match.as_dict() for match in matches[:5]],
        "message": "Browser window appears to match the URL." if matches else "I opened the URL, but Windows did not expose the browser URL for verification.",
    }


def verify_screen_changed() -> dict[str, Any]:
    return {"ok": True, "verified": False, "message": "Screen-change verification is not implemented in v1."}
