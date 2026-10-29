"""Web search that needs no API key: DuckDuckGo through the open-source `ddgs` package.

Used only when Tavily is not configured (or refuses the key). It returns the same
dict shape as `tavily_search`, with provider "duckduckgo", so every caller works
unchanged. It is a scraper, not an API: it can be rate-limited or break when the site
changes, so any failure is reported honestly and the callers' own fallbacks still apply.
Set EVA_KEYLESS_SEARCH=off to disable it.
"""

from __future__ import annotations

import os
from typing import Any

MAX_QUERY_LENGTH = 400


def keyless_enabled() -> bool:
    return os.environ.get("EVA_KEYLESS_SEARCH", "on").strip().lower() not in {"0", "off", "false", "no"}


def keyless_search_sync(query: str, max_results: int | None = None) -> dict[str, Any]:
    clean = " ".join(str(query or "").split())[:MAX_QUERY_LENGTH]
    if not clean:
        return {"ok": False, "provider": "duckduckgo", "query": query, "error": "empty_query", "fallback": "browser"}
    limit = max(1, min(10, int(max_results or 5)))
    try:
        from ddgs import DDGS

        raw = DDGS(timeout=10).text(clean, max_results=limit) or []
    except ImportError:
        return {"ok": False, "provider": "duckduckgo", "query": clean, "error": "ddgs_not_installed", "fallback": "browser"}
    except Exception as exc:  # rate limit, network, or a site change: say so, never fake results
        return {"ok": False, "provider": "duckduckgo", "query": clean, "error": f"keyless_search_failed:{exc.__class__.__name__}", "fallback": "browser"}
    results = [
        {
            "title": str(item.get("title") or "Untitled")[:240],
            "url": str(item.get("href") or item.get("url") or "")[:800],
            "content": str(item.get("body") or "")[:1200],
            "score": 0.0,
        }
        for item in raw
        if isinstance(item, dict) and (item.get("href") or item.get("url"))
    ]
    if not results:
        return {"ok": False, "provider": "duckduckgo", "query": clean, "error": "no_results", "fallback": "browser"}
    return {"ok": True, "provider": "duckduckgo", "query": clean, "answer": "", "results": results}
