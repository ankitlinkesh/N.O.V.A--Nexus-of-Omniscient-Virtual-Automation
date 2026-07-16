"""Memory must actually reach the model — regressions found by real prompt testing.

Three bugs hid behind a fully green suite for entire phases, because every test
checked that memory was *stored* and none checked that it *arrived*:

  1. The planner prompt builders filtered history to {"user","assistant"} and
     took ``history[-4:]``. The recall blocks are ``system`` messages PREPENDED
     at the head, so they were dropped twice over — assembled, then silently
     thrown away before the model ever saw them.
  2. Long-term memory stored Eva's OWN replies and served them back as "things
     you remember about the user". A later question matched her own earlier
     answer, so she parroted her own generic reply as though it were a fact
     about the user. An echo chamber.
  3. The user's own current question came back as a "memory", crowding out real
     facts.

Symptom: Eva knew the user was allergic to shellfish and still recited a stock
food-safety list she had written herself.
"""

from __future__ import annotations

import pytest

from eva.agent.planner import _memory_block, _split_history
from eva.memory.store import MemoryStore


# -- bug 1: the prompt builders dropped system notes -----------------------

def test_split_history_keeps_system_notes():
    history = [
        {"role": "system", "content": "What you've learned about the user (durable memory):\n- allergy: shellfish"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hey"},
    ]
    notes, recent = _split_history(history)
    assert any("shellfish" in n for n in notes), "durable memory must survive into the prompt"
    assert [m["role"] for m in recent] == ["user", "assistant"]


def test_split_history_keeps_notes_even_when_chat_is_long():
    """The notes sit at the HEAD; a naive history[-4:] tail slice loses them."""
    history = [{"role": "system", "content": "durable: allergy: shellfish"}]
    history += [{"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}"} for i in range(20)]
    notes, recent = _split_history(history)
    assert any("shellfish" in n for n in notes), "notes must not fall off the end of a long conversation"
    assert len(recent) == 4, "only the most recent turns are carried"


def test_memory_block_is_empty_when_nothing_is_remembered():
    # No memory must mean a byte-identical prompt to before this existed.
    assert _memory_block([]) == ""


def test_memory_block_instructs_the_model_to_use_it():
    block = _memory_block(["allergy: shellfish"])
    assert "shellfish" in block
    assert "USE them" in block
    assert "never read" in block.lower() or "not read" in block.lower()


# -- bug 2: the echo chamber ----------------------------------------------

def test_only_user_turns_are_vector_stored(tmp_path, monkeypatch):
    """Eva's own replies are NOT evidence about the user. Storing them made her
    recall her own answers and repeat them as facts."""
    stored: list[dict] = []
    import eva.vector_memory.retriever as retriever

    monkeypatch.setattr(retriever, "vector_memory_status", lambda: {"enabled": True})
    monkeypatch.setattr(retriever, "add_memory_item", lambda item: stored.append(item))

    ms = MemoryStore(tmp_path / "m.sqlite3")
    ms.add_message("s", "user", "I am allergic to shellfish and I live in Bangalore")
    ms.add_message("s", "assistant", "You should avoid raw meats, unpasteurized dairy, and soft cheeses.")

    texts = [item["text"] for item in stored]
    assert any("allergic to shellfish" in t for t in texts), "the user's own words must be remembered"
    assert not any("unpasteurized dairy" in t for t in texts), "Eva's own reply must NEVER be stored as a memory about the user"


# -- bug 3: recalling the user's own question -----------------------------

def _recall_with(monkeypatch, hits, query, tmp_path):
    import eva.vector_memory.retriever as retriever

    monkeypatch.setattr(retriever, "vector_memory_status", lambda: {"enabled": True})
    monkeypatch.setattr(retriever, "search_memory", lambda q, limit=5: {"results": [{"text": h} for h in hits]})
    ms = MemoryStore(tmp_path / "m.sqlite3")
    return ms.history_with_recall("fresh", query)


def test_recall_never_echoes_the_users_own_question(tmp_path, monkeypatch):
    history = _recall_with(monkeypatch, ["what foods should I avoid ordering?"], "what foods should I avoid ordering?", tmp_path)
    systems = [m["content"] for m in history if m["role"] == "system"]
    assert not systems, "the user's own question must never come back as a 'memory'"


def test_recall_deduplicates(tmp_path, monkeypatch):
    history = _recall_with(monkeypatch, ["I am allergic to shellfish", "I am allergic to shellfish"], "what should I eat?", tmp_path)
    block = "\n".join(m["content"] for m in history if m["role"] == "system")
    assert block.count("allergic to shellfish") == 1, "duplicate recalls must be collapsed"


def test_recall_keeps_genuine_memories(tmp_path, monkeypatch):
    history = _recall_with(monkeypatch, ["I am allergic to shellfish"], "what should I eat?", tmp_path)
    block = "\n".join(m["content"] for m in history if m["role"] == "system")
    assert "allergic to shellfish" in block
    assert "their own words" in block, "the block must be labelled as the user's own words, not Eva's"


# -- ordering: durable facts must lead ------------------------------------

def test_durable_model_leads_and_recall_follows(tmp_path, monkeypatch):
    monkeypatch.setenv("EVA_USER_MODEL_ENABLED", "1")
    import eva.vector_memory.retriever as retriever

    monkeypatch.setattr(retriever, "vector_memory_status", lambda: {"enabled": True})
    monkeypatch.setattr(retriever, "add_memory_item", lambda item: None)
    monkeypatch.setattr(retriever, "search_memory", lambda q, limit=5: {"results": [{"text": "I am allergic to shellfish"}]})

    ms = MemoryStore(tmp_path / "m.sqlite3")
    ms.add_message("a", "user", "I am allergic to shellfish and I live in Bangalore")
    history = ms.history_with_recall("b", "what should I order?")

    systems = [m["content"] for m in history if m["role"] == "system"]
    assert len(systems) == 2
    assert "durable memory" in systems[0], "high-precision durable facts must lead"
    assert "their own words" in systems[1], "fuzzier semantic recall supports them, it does not bury them"
