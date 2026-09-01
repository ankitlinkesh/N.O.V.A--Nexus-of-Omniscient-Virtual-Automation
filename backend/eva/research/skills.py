from __future__ import annotations

import os
from typing import Any

from .collector import collect_web_sources
from .retriever import retrieve_research
from .store import ResearchStore
from .summarizer import summarize_research_topic


def _store(store: ResearchStore | None = None) -> ResearchStore:
    return store or ResearchStore()


def _safe_error(exc: Exception) -> dict[str, Any]:
    return {"ok": False, "error": str(exc)[:500]}


def research_start_topic(topic: str, description: str = "", store: ResearchStore | None = None) -> dict[str, Any]:
    try:
        created = _store(store).get_or_create_topic(topic, description)
        return {"ok": True, "topic": created.as_dict(), "message": f"Research topic ready: {created.name}"}
    except Exception as exc:
        return _safe_error(exc)


def research_save_note(topic: str, note: str, tags: str = "", store: ResearchStore | None = None) -> dict[str, Any]:
    try:
        saved = _store(store).save_note(topic, note, tags)
        return {"ok": True, "topic": topic, "note": saved.as_dict(), "message": f"Saved research note for {topic}."}
    except Exception as exc:
        return _safe_error(exc)


def research_recall(topic: str, query: str = "", limit: int = 5, store: ResearchStore | None = None) -> dict[str, Any]:
    try:
        return retrieve_research(topic, query=query, limit=limit, store=_store(store))
    except Exception as exc:
        return _safe_error(exc)


def research_summary(topic: str, store: ResearchStore | None = None) -> dict[str, Any]:
    try:
        return summarize_research_topic(topic, store=_store(store))
    except Exception as exc:
        return _safe_error(exc)


def research_status(store: ResearchStore | None = None) -> dict[str, Any]:
    try:
        status = _store(store).status()
        status.update(
            {
                "ok": True,
                "nim_embedding_configured": bool(os.environ.get("NVIDIA_NIM_API_KEY", "").strip())
                and bool(os.environ.get("NVIDIA_NIM_EMBED_MODEL", "nvidia/nemotron-3-embed-1b").strip()),
                "retrieval_mode": "keyword",
                "rerank_mode": "keyword",
            }
        )
        return status
    except Exception as exc:
        return _safe_error(exc)


def research_web(topic: str, query: str, max_results: int = 5, store: ResearchStore | None = None) -> dict[str, Any]:
    try:
        active_store = _store(store)
        active_store.get_or_create_topic(topic)
        web_result = collect_web_sources(query, max_results=max_results)
        if web_result.get("ok") and isinstance(web_result.get("results"), list):
            normalized = []
            for item in web_result.get("results", [])[: max(1, min(10, int(max_results or 5)))]:
                if not isinstance(item, dict):
                    continue
                normalized.append(
                    {
                        "title": item.get("title") or "Untitled",
                        "url": item.get("url") or "",
                        "source": "tavily",
                        "snippet": item.get("content") or "",
                        "content_summary": item.get("content") or "",
                        "credibility_note": "Fresh Tavily web result.",
                    }
                )
            saved = active_store.save_web_results(topic, query, normalized, source="tavily")
            return {
                "ok": True,
                "topic": topic,
                "query": query,
                "provider": "tavily",
                "fresh_results": web_result.get("results", [])[:5],
                "answer": web_result.get("answer") or "",
                "saved_count": len(saved),
                "saved_results": saved,
                "quality": "fresh_web_results",
            }
        active_store.save_web_results(topic, query, [], source="browser_fallback")
        return {
            "ok": False,
            "topic": topic,
            "query": query,
            "provider": "tavily",
            "error": web_result.get("error") or "tavily_unavailable",
            "fallback": "browser",
            "quality": "limited_browser_fallback",
            "message": "Tavily was unavailable; existing browser fallback can be used, but no rich source content was saved.",
        }
    except Exception as exc:
        return _safe_error(exc)
