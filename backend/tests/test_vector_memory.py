"""Vector memory (chromadb-backed) behind EVA_V2_VECTOR_MEMORY_ENABLED.

Default (flag off) must stay byte-identical to the pre-chromadb fallback
behavior, so the 62-script verifier suite and the rest of pytest never touch
chromadb or the ONNX embedding model. The real-embedding semantic test is
opt-in (EVA_RUN_VECTOR_LIVE=1) so the default test run stays fast and offline.
"""
from __future__ import annotations

import os

import pytest

from backend.eva.vector_memory import add_memory_item, search_memory
from backend.eva.vector_memory.chroma_store import _sanitize_metadata


def test_add_memory_item_disabled_by_default(monkeypatch):
    monkeypatch.delenv("EVA_V2_VECTOR_MEMORY_ENABLED", raising=False)
    result = add_memory_item({"text": "x"})
    assert result["stored"] is False
    assert result["backend"] == "sqlite_keyword_fallback"


def test_search_memory_disabled_by_default(monkeypatch):
    monkeypatch.delenv("EVA_V2_VECTOR_MEMORY_ENABLED", raising=False)
    result = search_memory("x")
    assert result["results"] == []


def test_sanitize_metadata_drops_none_keeps_scalars():
    cleaned = _sanitize_metadata({"a": "text", "b": 1, "c": 2.5, "d": True, "e": None})
    assert cleaned == {"a": "text", "b": 1, "c": 2.5, "d": True}


def test_sanitize_metadata_stringifies_nested_values():
    cleaned = _sanitize_metadata({"nested": {"x": 1}, "lst": [1, 2]})
    assert cleaned == {"nested": str({"x": 1}), "lst": str([1, 2])}


def test_sanitize_metadata_empty_defaults_to_source_local():
    assert _sanitize_metadata({}) == {"source": "local"}
    assert _sanitize_metadata({"only_none": None}) == {"source": "local"}


@pytest.mark.skipif(not os.environ.get("EVA_RUN_VECTOR_LIVE"), reason="opt-in real-embedding test")
def test_live_semantic_search_finds_related_item(monkeypatch, tmp_path):
    monkeypatch.setenv("EVA_V2_VECTOR_MEMORY_ENABLED", "1")
    monkeypatch.setenv("EVA_CHROMA_PATH", str(tmp_path))

    hiking_result = add_memory_item({"text": "I love hiking in the mountains"})
    sushi_result = add_memory_item({"text": "My favorite food is sushi"})
    assert hiking_result["stored"] is True
    assert sushi_result["stored"] is True

    result = search_memory("outdoor activities", limit=1)
    assert result["results"], "expected at least one semantic search result"
    assert "hiking" in result["results"][0]["text"].lower()
