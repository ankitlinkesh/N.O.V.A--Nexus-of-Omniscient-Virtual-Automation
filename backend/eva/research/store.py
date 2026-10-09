from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import ResearchItem, ResearchNote, ResearchTopic
from ..core.data_paths import data_path

DEFAULT_RESEARCH_DB = Path(__file__).resolve().parents[1] / "data" / "research_knowledge.sqlite3"
MAX_RAW_CONTENT_CHARS = 12000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return uuid4().hex


def _clean_text(value: object, limit: int = 4000) -> str:
    text = str(value or "").replace("\x00", "").strip()
    return text[:limit]


def _tokens(text: str) -> set[str]:
    return {part.lower() for part in "".join(ch if ch.isalnum() else " " for ch in text).split() if len(part) > 2}


class ResearchStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else data_path(DEFAULT_RESEARCH_DB)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def ensure_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_topics (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_items (
                    id TEXT PRIMARY KEY,
                    topic_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL,
                    snippet TEXT NOT NULL,
                    content_summary TEXT NOT NULL,
                    raw_content TEXT,
                    credibility_note TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(topic_id) REFERENCES research_topics(id)
                );

                CREATE TABLE IF NOT EXISTS research_notes (
                    id TEXT PRIMARY KEY,
                    topic_id TEXT NOT NULL,
                    note TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(topic_id) REFERENCES research_topics(id)
                );

                CREATE TABLE IF NOT EXISTS research_embeddings (
                    id TEXT PRIMARY KEY,
                    item_id TEXT,
                    note_id TEXT,
                    model TEXT NOT NULL,
                    vector_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(item_id) REFERENCES research_items(id),
                    FOREIGN KEY(note_id) REFERENCES research_notes(id)
                );

                CREATE TABLE IF NOT EXISTS research_sessions (
                    id TEXT PRIMARY KEY,
                    topic_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    sources_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(topic_id) REFERENCES research_topics(id)
                );
                """
            )

    def get_or_create_topic(self, name: str, description: str = "") -> ResearchTopic:
        clean_name = _clean_text(name, 180)
        if not clean_name:
            raise ValueError("Research topic is empty.")
        clean_description = _clean_text(description, 1200)
        now = _now()
        with self._connect() as db:
            row = db.execute("SELECT * FROM research_topics WHERE lower(name)=lower(?)", (clean_name,)).fetchone()
            if row:
                if clean_description and clean_description != row["description"]:
                    db.execute("UPDATE research_topics SET description=?, updated_at=? WHERE id=?", (clean_description, now, row["id"]))
                    row = db.execute("SELECT * FROM research_topics WHERE id=?", (row["id"],)).fetchone()
                return self._topic(row)
            topic_id = _id()
            db.execute(
                "INSERT INTO research_topics(id, name, description, created_at, updated_at) VALUES(?, ?, ?, ?, ?)",
                (topic_id, clean_name, clean_description, now, now),
            )
            row = db.execute("SELECT * FROM research_topics WHERE id=?", (topic_id,)).fetchone()
            return self._topic(row)

    def topic_by_name(self, name: str) -> ResearchTopic | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM research_topics WHERE lower(name)=lower(?)", (_clean_text(name, 180),)).fetchone()
            return self._topic(row) if row else None

    def save_note(self, topic: str, note: str, tags: str = "") -> ResearchNote:
        research_topic = self.get_or_create_topic(topic)
        clean_note = _clean_text(note, 6000)
        if not clean_note:
            raise ValueError("Research note is empty.")
        note_id = _id()
        created_at = _now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO research_notes(id, topic_id, note, tags, created_at) VALUES(?, ?, ?, ?, ?)",
                (note_id, research_topic.id, clean_note, _clean_text(tags, 500), created_at),
            )
            db.execute("UPDATE research_topics SET updated_at=? WHERE id=?", (created_at, research_topic.id))
            row = db.execute("SELECT * FROM research_notes WHERE id=?", (note_id,)).fetchone()
            return self._note(row)

    def save_web_results(self, topic: str, query: str, results: list[dict[str, Any]], source: str = "web") -> list[dict[str, Any]]:
        research_topic = self.get_or_create_topic(topic)
        saved: list[dict[str, Any]] = []
        now = _now()
        with self._connect() as db:
            for item in results:
                if not isinstance(item, dict):
                    continue
                url = _clean_text(item.get("url"), 2000)
                title = _clean_text(item.get("title") or url or "Untitled source", 500)
                if not url and not title:
                    continue
                snippet = _clean_text(item.get("snippet") or item.get("content") or item.get("description"), 3000)
                summary = _clean_text(item.get("content_summary") or item.get("summary") or snippet, 3000)
                raw_content = _clean_text(item.get("raw_content") or "", MAX_RAW_CONTENT_CHARS)
                credibility = _clean_text(item.get("credibility_note") or f"Saved from {source}.", 1000)
                item_source = _clean_text(item.get("source") or source, 120)
                item_id = _id()
                db.execute(
                    """
                    INSERT INTO research_items(
                        id, topic_id, title, url, source, snippet, content_summary, raw_content, credibility_note, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (item_id, research_topic.id, title, url, item_source, snippet, summary, raw_content, credibility, now, now),
                )
                saved.append(
                    {
                        "id": item_id,
                        "topic": research_topic.name,
                        "title": title,
                        "url": url,
                        "source": item_source,
                        "snippet": snippet,
                        "content_summary": summary,
                        "credibility_note": credibility,
                    }
                )
            db.execute(
                "INSERT INTO research_sessions(id, topic_id, query, summary, sources_count, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                (_id(), research_topic.id, _clean_text(query, 800), self._session_summary(query, saved), len(saved), now),
            )
            db.execute("UPDATE research_topics SET updated_at=? WHERE id=?", (now, research_topic.id))
        return saved

    def recall(self, topic: str, query: str = "", limit: int = 5) -> list[dict[str, Any]]:
        research_topic = self.topic_by_name(topic)
        if research_topic is None:
            return []
        terms = _tokens(f"{topic} {query}")
        matches: list[dict[str, Any]] = []
        with self._connect() as db:
            notes = db.execute("SELECT * FROM research_notes WHERE topic_id=? ORDER BY created_at DESC", (research_topic.id,)).fetchall()
            items = db.execute("SELECT * FROM research_items WHERE topic_id=? ORDER BY updated_at DESC", (research_topic.id,)).fetchall()
        for row in notes:
            text = f"{row['note']} {row['tags']}"
            matches.append({"type": "note", "topic": research_topic.name, "text": row["note"], "tags": row["tags"], "score": self._score(text, terms), "created_at": row["created_at"]})
        for row in items:
            text = f"{row['title']} {row['snippet']} {row['content_summary']} {row['url']}"
            matches.append(
                {
                    "type": "source",
                    "topic": research_topic.name,
                    "title": row["title"],
                    "url": row["url"],
                    "text": row["content_summary"] or row["snippet"],
                    "snippet": row["snippet"],
                    "source": row["source"],
                    "score": self._score(text, terms),
                    "created_at": row["created_at"],
                }
            )
        ordered = sorted(matches, key=lambda item: (item.get("score", 0), item.get("created_at", "")), reverse=True)
        return ordered[: max(1, min(25, int(limit or 5)))]

    def summarize_topic(self, topic: str, limit: int = 8) -> dict[str, Any]:
        research_topic = self.topic_by_name(topic)
        if research_topic is None:
            return {"ok": False, "error": "topic_not_found", "topic": topic, "summary": ""}
        matches = self.recall(research_topic.name, "", limit=limit)
        lines = [f"Research topic: {research_topic.name}"]
        if research_topic.description:
            lines.append(f"Description: {research_topic.description}")
        notes = [item for item in matches if item.get("type") == "note"]
        sources = [item for item in matches if item.get("type") == "source"]
        if notes:
            lines.append("Saved notes:")
            for item in notes[:4]:
                lines.append(f"- {item.get('text')}")
        if sources:
            lines.append("Saved sources:")
            for item in sources[:5]:
                lines.append(f"- {item.get('title')}: {item.get('url')} - {item.get('text')}")
        if not notes and not sources:
            lines.append("No saved notes or sources yet.")
        return {"ok": True, "topic": research_topic.as_dict(), "summary": "\n".join(lines), "matches": matches}

    def status(self) -> dict[str, Any]:
        with self._connect() as db:
            topic_count = int(db.execute("SELECT COUNT(*) FROM research_topics").fetchone()[0])
            item_count = int(db.execute("SELECT COUNT(*) FROM research_items").fetchone()[0])
            note_count = int(db.execute("SELECT COUNT(*) FROM research_notes").fetchone()[0])
            session_count = int(db.execute("SELECT COUNT(*) FROM research_sessions").fetchone()[0])
            last = db.execute("SELECT name, updated_at FROM research_topics ORDER BY updated_at DESC LIMIT 1").fetchone()
        return {"topic_count": topic_count, "item_count": item_count, "note_count": note_count, "session_count": session_count, "last_topic": dict(last) if last else None, "database": str(self.path)}

    def delete_topic(self, topic: str) -> bool:
        research_topic = self.topic_by_name(topic)
        if research_topic is None:
            return False
        with self._connect() as db:
            db.execute("DELETE FROM research_embeddings WHERE item_id IN (SELECT id FROM research_items WHERE topic_id=?)", (research_topic.id,))
            db.execute("DELETE FROM research_embeddings WHERE note_id IN (SELECT id FROM research_notes WHERE topic_id=?)", (research_topic.id,))
            db.execute("DELETE FROM research_sessions WHERE topic_id=?", (research_topic.id,))
            db.execute("DELETE FROM research_items WHERE topic_id=?", (research_topic.id,))
            db.execute("DELETE FROM research_notes WHERE topic_id=?", (research_topic.id,))
            db.execute("DELETE FROM research_topics WHERE id=?", (research_topic.id,))
        return True

    def _session_summary(self, query: str, saved: list[dict[str, Any]]) -> str:
        if not saved:
            return f"No sources saved for query: {query}"
        titles = ", ".join(item.get("title", "source") for item in saved[:5])
        return f"Saved {len(saved)} sources for query '{query}': {titles}"

    def _score(self, text: str, terms: set[str]) -> int:
        if not terms:
            return 1
        haystack = _tokens(text)
        return len(terms & haystack)

    def _topic(self, row: sqlite3.Row) -> ResearchTopic:
        return ResearchTopic(id=row["id"], name=row["name"], description=row["description"], created_at=row["created_at"], updated_at=row["updated_at"])

    def _item(self, row: sqlite3.Row) -> ResearchItem:
        return ResearchItem(
            id=row["id"],
            topic_id=row["topic_id"],
            title=row["title"],
            url=row["url"],
            source=row["source"],
            snippet=row["snippet"],
            content_summary=row["content_summary"],
            raw_content=row["raw_content"] or "",
            credibility_note=row["credibility_note"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _note(self, row: sqlite3.Row) -> ResearchNote:
        return ResearchNote(id=row["id"], topic_id=row["topic_id"], note=row["note"], tags=row["tags"], created_at=row["created_at"])
