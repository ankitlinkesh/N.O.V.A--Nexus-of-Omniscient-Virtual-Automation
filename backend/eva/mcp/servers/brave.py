"""eva-brave: Brave Search as a read-only stdio MCP server (Phase 160).

Standalone -- it does not wrap a NOVA tool. Needs BRAVE_API_KEY (a Brave Search API subscription
token); without one every call returns a clear error instead of guessing. Run:
python -m backend.eva.mcp.servers.brave
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("eva-brave")
_BASE = "https://api.search.brave.com/res/v1"


def _get(path: str, query: str, count: int) -> dict[str, Any]:
    key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not key:
        return {"ok": False, "error": "BRAVE_API_KEY is not set, so Brave Search was not called."}
    count = max(1, min(int(count or 5), 20))
    try:
        resp = httpx.get(
            f"{_BASE}/{path}",
            params={"q": query, "count": count},
            headers={"X-Subscription-Token": key, "Accept": "application/json"},
            timeout=15.0,
        )
        resp.raise_for_status()
        return {"ok": True, "data": resp.json()}
    except Exception as exc:  # noqa: BLE001 - reported to the caller, never raised
        return {"ok": False, "error": f"Brave Search failed: {type(exc).__name__}: {exc}"}


def _trim(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"title": str(i.get("title", "")), "url": str(i.get("url", "")), "snippet": str(i.get("description", ""))}
        for i in items
    ]


@mcp.tool()
def brave_web_search(query: str, count: int = 5) -> dict[str, Any]:
    """Search the web with Brave. Returns title, url and snippet for up to `count` results."""
    out = _get("web/search", query, count)
    if not out["ok"]:
        return out
    return {"ok": True, "results": _trim((out["data"].get("web") or {}).get("results", []))}


@mcp.tool()
def brave_news_search(query: str, count: int = 5) -> dict[str, Any]:
    """Search recent news with Brave. Returns title, url and snippet for up to `count` stories."""
    out = _get("news/search", query, count)
    if not out["ok"]:
        return out
    return {"ok": True, "results": _trim(out["data"].get("results", []))}


if __name__ == "__main__":
    mcp.run()
