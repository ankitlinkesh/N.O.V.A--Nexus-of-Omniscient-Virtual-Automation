from __future__ import annotations

from typing import Any

from .base import VectorMemoryItem, VectorSearchResult
from .chroma_store import chroma_add, chroma_query, chroma_status
from .memory_ranker import rank_memory_results
from .qdrant_store import qdrant_status


def vector_memory_status() -> dict[str, Any]:
    chroma = chroma_status()
    qdrant = qdrant_status()
    enabled = bool(chroma.get("enabled") or qdrant.get("enabled"))
    return {
        "ok": True,
        "enabled": enabled,
        "primary": "chroma" if chroma.get("enabled") else "qdrant" if qdrant.get("enabled") else "sqlite_keyword_fallback",
        "chroma": chroma,
        "qdrant": qdrant,
        "message": "Vector memory interfaces are installed; Chroma/Qdrant are optional and disabled unless explicitly enabled.",
    }


def add_memory_item(item: VectorMemoryItem | dict[str, Any]) -> dict[str, Any]:
    value = item if isinstance(item, VectorMemoryItem) else VectorMemoryItem(text=str(item.get("text") or ""), metadata=dict(item.get("metadata") or {}), source=str(item.get("source") or "local"))
    status = vector_memory_status()
    if not status["enabled"]:
        return {"ok": False, "stored": False, "backend": "sqlite_keyword_fallback", "message": "Vector backend is unavailable; keep using local SQLite memory for now.", "item": value.as_dict()}
    result = chroma_add([value])
    if result.get("ok"):
        return {"ok": True, "stored": True, "backend": "chroma", "id": value.id, "item": value.as_dict()}
    return {"ok": False, "stored": False, "backend": "chroma", "error": result.get("error"), "item": value.as_dict()}


def search_memory(query: str, filters: dict[str, Any] | None = None, limit: int = 5) -> dict[str, Any]:
    status = vector_memory_status()
    if not status["enabled"]:
        return {
            "ok": True,
            "backend": status["primary"],
            "query": query,
            "filters": filters or {},
            "results": [],
            "limit": limit,
            "message": "Vector search is interface-ready; falling back to existing local keyword memory/research retrieval.",
        }
    results = chroma_query(query, limit)
    return {
        "ok": True,
        "backend": "chroma",
        "query": query,
        "filters": filters or {},
        "results": [r.as_dict() for r in results],
        "limit": limit,
    }


__all__ = ["VectorMemoryItem", "VectorSearchResult", "add_memory_item", "search_memory", "rank_memory_results", "vector_memory_status"]
