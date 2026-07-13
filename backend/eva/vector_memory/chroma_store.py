from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..runtime.feature_flags import get_v2_feature_flags
from .base import VectorMemoryItem, VectorSearchResult


_DEFAULT_CHROMA_PATH = Path(__file__).resolve().parents[1] / "data" / "vector" / "chroma"
CHROMA_PATH = Path(os.environ.get("EVA_CHROMA_PATH") or _DEFAULT_CHROMA_PATH)


def _chroma_path() -> Path:
    return Path(os.environ.get("EVA_CHROMA_PATH") or _DEFAULT_CHROMA_PATH)


def is_chroma_available() -> bool:
    try:
        import chromadb  # type: ignore  # noqa: F401
    except Exception:
        return False
    return True


def chroma_status() -> dict[str, object]:
    flags = get_v2_feature_flags()
    available = is_chroma_available()
    return {
        "ok": True,
        "backend": "chroma",
        "available": available,
        "enabled": bool(flags.vector_memory_enabled and available),
        "path": str(_chroma_path()),
    }


def _client():
    import chromadb  # type: ignore

    return chromadb.PersistentClient(path=str(_chroma_path()))


def _collection():
    return _client().get_or_create_collection("eva_memory")


def _sanitize_metadata(md: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, val in (md or {}).items():
        if val is None:
            continue
        if isinstance(val, (str, int, float, bool)):
            cleaned[key] = val
        else:
            cleaned[key] = str(val)
    if not cleaned:
        return {"source": "local"}
    return cleaned


def chroma_add(items: list[VectorMemoryItem]) -> dict[str, Any]:
    try:
        ids = [i.id for i in items]
        documents = [i.text for i in items]
        metadatas = [_sanitize_metadata({**i.metadata, "source": i.source, "created_at": i.created_at}) for i in items]
        _collection().add(ids=ids, documents=documents, metadatas=metadatas)
        return {"ok": True, "stored": len(items), "ids": ids}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "stored": 0}


def chroma_query(query: str, limit: int = 5) -> list[VectorSearchResult]:
    try:
        res = _collection().query(query_texts=[query], n_results=limit)
        ids = (res.get("ids") or [[]])[0]
        documents = (res.get("documents") or [[]])[0]
        distances = (res.get("distances") or [[]])[0]
        metadatas = (res.get("metadatas") or [[]])[0]
        results: list[VectorSearchResult] = []
        for idx, doc_id in enumerate(ids):
            document = documents[idx] if idx < len(documents) else ""
            distance = distances[idx] if idx < len(distances) else 0.0
            metadata = metadatas[idx] if idx < len(metadatas) else {}
            score = 1.0 / (1.0 + float(distance))
            results.append(VectorSearchResult(id=doc_id, text=document, score=score, metadata=metadata or {}))
        return results
    except Exception:
        return []
