"""Wiring of semantic vector memory into MemoryStore (store + recall).

Behind EVA_V2_VECTOR_MEMORY_ENABLED (default off). When the flag is off,
add_message must store nothing extra and history_with_recall must be
byte-identical to recent_messages. Vector memory errors must never break
message storage or history retrieval.
"""
from __future__ import annotations

from backend.eva.memory.store import MemoryStore


def test_add_message_disabled_stores_nothing_extra(tmp_path, monkeypatch):
    monkeypatch.delenv("EVA_V2_VECTOR_MEMORY_ENABLED", raising=False)
    store = MemoryStore(tmp_path / "m.sqlite3")

    calls = []
    monkeypatch.setattr(
        "backend.eva.vector_memory.retriever.add_memory_item",
        lambda item: calls.append(item),
    )

    store.add_message("s", "user", "this is a long enough message to store")

    assert calls == []
    contents = [m["content"] for m in store.recent_messages("s")]
    assert "this is a long enough message to store" in contents


def test_add_message_enabled_stores_long_messages_and_skips_short(tmp_path, monkeypatch):
    monkeypatch.setenv("EVA_V2_VECTOR_MEMORY_ENABLED", "1")
    monkeypatch.setattr(
        "backend.eva.vector_memory.retriever.vector_memory_status",
        lambda: {"enabled": True},
    )
    store = MemoryStore(tmp_path / "m.sqlite3")

    calls = []
    monkeypatch.setattr(
        "backend.eva.vector_memory.retriever.add_memory_item",
        lambda item: calls.append(item),
    )

    long_text = "this is a long enough message to store"
    store.add_message("s", "user", long_text)
    assert len(calls) == 1
    assert calls[0]["text"] == long_text

    store.add_message("s", "user", "ok")
    assert len(calls) == 1  # short message skipped, no new call


def test_history_with_recall_disabled_matches_recent_messages(tmp_path, monkeypatch):
    monkeypatch.delenv("EVA_V2_VECTOR_MEMORY_ENABLED", raising=False)
    store = MemoryStore(tmp_path / "m.sqlite3")

    store.add_message("s", "user", "hello there")
    store.add_message("s", "assistant", "hi, how can I help?")

    assert store.history_with_recall("s", "q") == store.recent_messages("s")


def test_history_with_recall_enabled_prepends_recall_message(tmp_path, monkeypatch):
    monkeypatch.setenv("EVA_V2_VECTOR_MEMORY_ENABLED", "1")
    monkeypatch.setattr(
        "backend.eva.vector_memory.retriever.vector_memory_status",
        lambda: {"enabled": True},
    )
    monkeypatch.setattr(
        "backend.eva.vector_memory.retriever.search_memory",
        lambda query, limit=4: {
            "results": [
                {"text": "The user is allergic to peanuts", "score": 0.9, "metadata": {}}
            ]
        },
    )
    store = MemoryStore(tmp_path / "m.sqlite3")

    store.add_message("s", "user", "what should I cook tonight")
    store.add_message("s", "assistant", "how about a stir fry")

    history = store.history_with_recall("s", "food")

    assert history[0]["role"] == "system"
    assert "allergic to peanuts" in history[0]["content"]
    assert history[1:] == store.recent_messages("s")
