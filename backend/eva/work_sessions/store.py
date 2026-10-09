from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import WORK_SESSION_EVENT_TYPES, WorkSession, WorkSessionEvent
from ..core.data_paths import data_path


_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s]*")
_SECRET_RE = re.compile(
    r"(?i)(bearer\s+\S+|sk-[a-z0-9_\-]{4,}|api[_-]?key\s*[:=]\s*\S+|token\s*[:=]\s*\S+|password\s*[:=]\s*\S+)"
)


def create_work_session(request_text: str, source: str = "eva ask") -> WorkSession:
    now = _now()
    safe_request = sanitize_value(request_text)
    session_id = _session_id(safe_request, now)
    session = WorkSession(
        session_id=session_id,
        user_request=str(safe_request),
        source=str(sanitize_value(source)),
        created_at=now,
        updated_at=now,
    )
    with _database() as conn:
        _ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO work_sessions (
                session_id, user_request, source, interpreted_intent, status,
                selected_specialists, selected_skills, selected_workflow, planner_steps,
                authority_decision, approval_id, sandbox_apply_status, real_create_status,
                verification_status, rollback_status, final_summary, next_safe_step,
                created_at, updated_at, closed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.session_id,
                session.user_request,
                session.source,
                session.interpreted_intent,
                session.status,
                json.dumps(list(session.selected_specialists)),
                json.dumps(list(session.selected_skills)),
                session.selected_workflow,
                json.dumps(list(session.planner_steps)),
                session.authority_decision,
                session.approval_id,
                session.sandbox_apply_status,
                session.real_create_status,
                session.verification_status,
                session.rollback_status,
                session.final_summary,
                session.next_safe_step,
                session.created_at,
                session.updated_at,
                session.closed_at,
            ),
        )
    add_session_event(session_id, "request_received", "Request received for local WorkSession tracking.", {"source": source})
    return get_work_session(session_id) or session


def get_work_session(session_id: str) -> WorkSession | None:
    with _database() as conn:
        _ensure_schema(conn)
        row = conn.execute("SELECT * FROM work_sessions WHERE session_id = ?", (str(session_id),)).fetchone()
    return _row_to_session(row) if row else None


def list_recent_work_sessions(limit: int = 10) -> list[WorkSession]:
    safe_limit = max(1, min(int(limit or 10), 50))
    with _database() as conn:
        _ensure_schema(conn)
        rows = conn.execute("SELECT * FROM work_sessions ORDER BY updated_at DESC, created_at DESC LIMIT ?", (safe_limit,)).fetchall()
    return [_row_to_session(row) for row in rows]


def find_latest_active_work_session() -> WorkSession | None:
    with _database() as conn:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT * FROM work_sessions WHERE status = 'active' ORDER BY updated_at DESC, created_at DESC LIMIT 1"
        ).fetchone()
    return _row_to_session(row) if row else None


def add_session_event(session_id: str, event_type: str, summary: str, metadata: dict[str, object] | None = None) -> WorkSessionEvent:
    safe_type = event_type if event_type in WORK_SESSION_EVENT_TYPES else "blocked_action"
    now = _now()
    safe_summary = str(sanitize_value(summary))[:600]
    safe_metadata = sanitize_value(metadata or {})
    event_id = _event_id(str(session_id), safe_type, now, safe_summary)
    with _database() as conn:
        _ensure_schema(conn)
        cursor = conn.execute(
            """
            INSERT INTO work_session_events (event_id, session_id, event_type, summary, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, str(session_id), safe_type, safe_summary, json.dumps(safe_metadata, sort_keys=True), now),
        )
        sequence = int(cursor.lastrowid or 0)
        conn.execute("UPDATE work_sessions SET updated_at = ? WHERE session_id = ?", (now, str(session_id)))
    return WorkSessionEvent(event_id, str(session_id), safe_type, safe_summary, safe_metadata if isinstance(safe_metadata, dict) else {}, now, sequence)


def list_session_events(session_id: str, limit: int = 100) -> list[WorkSessionEvent]:
    safe_limit = max(1, min(int(limit or 100), 200))
    with _database() as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT id, event_id, session_id, event_type, summary, metadata_json, created_at FROM work_session_events WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (str(session_id), safe_limit),
        ).fetchall()
    return [_row_to_event(row) for row in rows]


def close_work_session(session_id: str, status: str, final_summary: str) -> WorkSession:
    now = _now()
    safe_status = str(sanitize_value(status or "closed"))[:40]
    safe_summary = str(sanitize_value(final_summary or "Work session closed."))[:800]
    with _database() as conn:
        _ensure_schema(conn)
        conn.execute(
            "UPDATE work_sessions SET status = ?, final_summary = ?, updated_at = ?, closed_at = ? WHERE session_id = ?",
            (safe_status, safe_summary, now, now, str(session_id)),
        )
    add_session_event(session_id, "final_report", safe_summary, {"status": safe_status})
    session = get_work_session(session_id)
    if session is None:
        raise ValueError("Work session not found.")
    return session


def update_work_session(session_id: str, **fields: object) -> WorkSession | None:
    allowed = {
        "interpreted_intent",
        "selected_specialists",
        "selected_skills",
        "selected_workflow",
        "planner_steps",
        "authority_decision",
        "approval_id",
        "sandbox_apply_status",
        "real_create_status",
        "verification_status",
        "rollback_status",
        "final_summary",
        "next_safe_step",
    }
    updates: list[tuple[str, object]] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key in {"selected_specialists", "selected_skills", "planner_steps"}:
            safe = json.dumps([str(sanitize_value(item)) for item in (value or [])])
        else:
            safe = str(sanitize_value(value or ""))[:1000]
        updates.append((key, safe))
    if not updates:
        return get_work_session(session_id)
    now = _now()
    assignments = ", ".join(f"{key} = ?" for key, _ in updates)
    params = [value for _, value in updates]
    params.extend([now, str(session_id)])
    with _database() as conn:
        _ensure_schema(conn)
        conn.execute(f"UPDATE work_sessions SET {assignments}, updated_at = ? WHERE session_id = ?", params)
    return get_work_session(session_id)


def sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        text = _WINDOWS_PATH_RE.sub("[LOCAL_PATH]", value)
        text = text.replace(".env.local", "[REDACTED_SECRET_PATH]")
        text = _SECRET_RE.sub("[REDACTED_SECRET]", text)
        return text
    if isinstance(value, dict):
        return {str(sanitize_value(key)): sanitize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize_value(item) for item in value]
    return value


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _database():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _db_path() -> Path:
    override = os.environ.get("EVA_WORK_SESSIONS_DB_PATH")
    if override:
        return Path(override)
    return data_path(Path(__file__).resolve().parents[1] / "data" / "work_sessions" / "work_sessions.sqlite3")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_sessions (
            session_id TEXT PRIMARY KEY,
            user_request TEXT,
            source TEXT,
            interpreted_intent TEXT,
            status TEXT,
            selected_specialists TEXT,
            selected_skills TEXT,
            selected_workflow TEXT,
            planner_steps TEXT,
            authority_decision TEXT,
            approval_id TEXT,
            sandbox_apply_status TEXT,
            real_create_status TEXT,
            verification_status TEXT,
            rollback_status TEXT,
            final_summary TEXT,
            next_safe_step TEXT,
            created_at TEXT,
            updated_at TEXT,
            closed_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_session_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT,
            session_id TEXT,
            event_type TEXT,
            summary TEXT,
            metadata_json TEXT,
            created_at TEXT
        )
        """
    )


def _row_to_session(row: sqlite3.Row) -> WorkSession:
    return WorkSession(
        session_id=str(row["session_id"] or ""),
        user_request=str(row["user_request"] or ""),
        source=str(row["source"] or ""),
        interpreted_intent=str(row["interpreted_intent"] or ""),
        status=str(row["status"] or ""),
        selected_specialists=tuple(_json_list(row["selected_specialists"])),
        selected_skills=tuple(_json_list(row["selected_skills"])),
        selected_workflow=str(row["selected_workflow"] or ""),
        planner_steps=tuple(_json_list(row["planner_steps"])),
        authority_decision=str(row["authority_decision"] or ""),
        approval_id=str(row["approval_id"] or ""),
        sandbox_apply_status=str(row["sandbox_apply_status"] or ""),
        real_create_status=str(row["real_create_status"] or ""),
        verification_status=str(row["verification_status"] or ""),
        rollback_status=str(row["rollback_status"] or ""),
        final_summary=str(row["final_summary"] or ""),
        next_safe_step=str(row["next_safe_step"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
        closed_at=str(row["closed_at"] or ""),
    )


def _row_to_event(row: sqlite3.Row) -> WorkSessionEvent:
    metadata = {}
    try:
        metadata = json.loads(row["metadata_json"] or "{}")
    except Exception:
        metadata = {}
    return WorkSessionEvent(
        event_id=str(row["event_id"] or ""),
        session_id=str(row["session_id"] or ""),
        event_type=str(row["event_type"] or ""),
        summary=str(row["summary"] or ""),
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=str(row["created_at"] or ""),
        sequence=int(row["id"] or 0),
    )


def _json_list(value: object) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except Exception:
        parsed = []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _session_id(request_text: object, now: str) -> str:
    digest = hashlib.sha256(f"{now}|{request_text}".encode("utf-8")).hexdigest()[:10]
    compact_time = re.sub(r"[^0-9]", "", now)[:14]
    return f"ws_{compact_time}_{digest}"


def _event_id(session_id: str, event_type: str, now: str, summary: str) -> str:
    digest = hashlib.sha256(f"{session_id}|{event_type}|{now}|{summary}".encode("utf-8")).hexdigest()[:12]
    return f"wse_{digest}"
