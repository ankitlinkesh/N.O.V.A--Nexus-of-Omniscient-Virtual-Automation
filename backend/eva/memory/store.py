from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
from threading import Lock
from uuid import uuid4


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_namespace_created ON memories(namespace, created_at DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_tasks (
                    task_id TEXT PRIMARY KEY,
                    user_request TEXT,
                    status TEXT,
                    created_at TEXT,
                    completed_at TEXT,
                    summary TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_steps (
                    id INTEGER PRIMARY KEY,
                    task_id TEXT,
                    action_id TEXT,
                    tool_name TEXT,
                    action_type TEXT,
                    decision TEXT,
                    observation_summary TEXT,
                    verification_status TEXT,
                    rollback_status TEXT,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_save_candidates (
                    id INTEGER PRIMARY KEY,
                    task_id TEXT,
                    candidate_fact TEXT,
                    reason TEXT,
                    status TEXT,
                    created_at TEXT
                )
                """
            )

    def add_message(self, session_id: str, role: str, content: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (uuid4().hex, session_id, role, content, datetime.now(timezone.utc).isoformat()),
            )
        self._maybe_vector_store(session_id, role, content)

    def _maybe_vector_store(self, session_id: str, role: str, content: str) -> None:
        try:
            from ..vector_memory.retriever import add_memory_item, vector_memory_status
            if not vector_memory_status().get("enabled"):
                return
            text = (content or "").strip()
            if len(text) < 20:  # skip trivial turns ("ok", "yes", etc.)
                return
            add_memory_item({"text": text, "metadata": {"session_id": session_id, "role": role}, "source": "chat"})
        except Exception:
            return

    def log_event(self, session_id: str, kind: str, payload: dict) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO events (id, session_id, kind, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                (uuid4().hex, session_id, kind, json.dumps(payload, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
            )

    def recent_messages(self, session_id: str, limit: int = 12) -> list[dict[str, str]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [
            {"role": role, "content": content, "created_at": created_at}
            for role, content, created_at in reversed(rows)
        ]

    def history_with_recall(self, session_id: str, query: str, limit: int = 12) -> list[dict[str, str]]:
        history = self.recent_messages(session_id, limit=limit)
        try:
            from ..vector_memory.retriever import search_memory, vector_memory_status
            if not vector_memory_status().get("enabled"):
                return history
            hits = (search_memory(str(query or ""), limit=4) or {}).get("results") or []
            # de-duplicate against what's already in recent history text
            recent_texts = {m.get("content", "").strip() for m in history}
            lines = []
            for h in hits:
                t = (h.get("text") or "").strip()
                if t and t not in recent_texts:
                    lines.append(f"- {t}")
            if not lines:
                return history
            recall_msg = {"role": "system", "content": "Relevant things you remember about the user (from long-term memory):\n" + "\n".join(lines[:4])}
            return [recall_msg] + history
        except Exception:
            return history

    def remember_fact(self, key: str, value: str, *, namespace: str = "user_profile", source: str = "user") -> None:
        now = datetime.now(timezone.utc).isoformat()
        safe_key = " ".join(key.strip().split())[:120] or "note"
        safe_value = " ".join(value.strip().split())[:1000]
        if not safe_value:
            return
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memories (id, namespace, key, value, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (uuid4().hex, namespace, safe_key, safe_value, source, now, now),
            )

    def recent_memories(self, *, namespace: str = "user_profile", limit: int = 8) -> list[dict[str, str]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT key, value, source, created_at
                FROM memories
                WHERE namespace = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (namespace, limit),
            ).fetchall()
        return [
            {"key": key, "value": value, "source": source, "created_at": created_at}
            for key, value, source, created_at in rows
        ]

    def search_memories(self, query: str, *, namespace: str = "user_profile", limit: int = 8) -> list[dict[str, str]]:
        term = f"%{query.strip()}%"
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT key, value, source, created_at
                FROM memories
                WHERE namespace = ? AND (key LIKE ? OR value LIKE ?)
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (namespace, term, term, limit),
            ).fetchall()
        return [
            {"key": key, "value": value, "source": source, "created_at": created_at}
            for key, value, source, created_at in rows
        ]

    def log_agent_task(self, task_id: str, user_request: str, status: str = "started", summary: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_tasks (task_id, user_request, status, created_at, completed_at, summary)
                VALUES (?, ?, ?, COALESCE((SELECT created_at FROM agent_tasks WHERE task_id = ?), ?), ?, ?)
                """,
                (task_id, user_request, status, task_id, now, now if status in {"completed", "stopped", "failed"} else None, summary),
            )

    def log_agent_step(
        self,
        task_id: str,
        action_id: str,
        tool_name: str,
        action_type: str,
        decision: str,
        observation_summary: str = "",
        verification_status: str = "",
        rollback_status: str = "",
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_steps (task_id, action_id, tool_name, action_type, decision, observation_summary, verification_status, rollback_status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, action_id, tool_name, action_type, decision, observation_summary, verification_status, rollback_status, datetime.now(timezone.utc).isoformat()),
            )

    def add_memory_save_candidate(self, task_id: str, candidate_fact: str, reason: str, status: str = "pending") -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_save_candidates (task_id, candidate_fact, reason, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, candidate_fact, reason, status, datetime.now(timezone.utc).isoformat()),
            )
