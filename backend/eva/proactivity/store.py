"""Persistence for proactive rules and notifications (Phase 46).

Rules outlive the process — a standing "every morning, summarize my news" must
survive a reboot, exactly like the Phase 45 durable queue it feeds.

Connection discipline follows the Phase 45 lesson: every connection is closed
via ``contextlib.closing`` (sqlite3's own context manager commits but does not
close), and no method ever calls a public, lock-taking reader while already
holding ``self._lock`` (``Lock`` is not reentrant — that deadlocks).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from .models import (
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_MAX_FIRES_PER_DAY,
    MAX_FIRES_PER_DAY_CEILING,
    RULE_KINDS,
    ProactiveNotification,
    ProactiveRule,
)

_RULE_COLUMNS = (
    "id, name, kind, spec, request, enabled, cooldown_seconds, max_fires_per_day, "
    "fires_today, fires_day, last_fired_at, state, created_at"
)
_NOTE_COLUMNS = "id, rule_id, message, created_at, read"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _rule_from_row(row: tuple) -> ProactiveRule:
    return ProactiveRule(
        id=row[0],
        name=row[1],
        kind=row[2],
        spec=_loads(row[3]),
        request=row[4],
        enabled=bool(row[5]),
        cooldown_seconds=int(row[6]),
        max_fires_per_day=int(row[7]),
        fires_today=int(row[8]),
        fires_day=row[9] or "",
        last_fired_at=row[10],
        state=_loads(row[11]),
        created_at=row[12] or "",
    )


def _note_from_row(row: tuple) -> ProactiveNotification:
    return ProactiveNotification(id=row[0], rule_id=row[1], message=row[2], created_at=row[3], read=bool(row[4]))


class ProactivityStore:
    """SQLite persistence for standing rules and their notifications."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10.0)

    def _init_db(self) -> None:
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS proactive_rules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    spec TEXT NOT NULL,
                    request TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    cooldown_seconds INTEGER NOT NULL,
                    max_fires_per_day INTEGER NOT NULL,
                    fires_today INTEGER NOT NULL,
                    fires_day TEXT,
                    last_fired_at TEXT,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS proactive_notifications (
                    id TEXT PRIMARY KEY,
                    rule_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    read INTEGER NOT NULL
                )
                """
            )

    # -- rules ---------------------------------------------------------------

    def add_rule(
        self,
        name: str,
        kind: str,
        spec: dict[str, Any],
        request: str,
        *,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        max_fires_per_day: int = DEFAULT_MAX_FIRES_PER_DAY,
        enabled: bool = True,
    ) -> ProactiveRule | None:
        """Create a standing rule. Returns ``None`` for an invalid kind/empty
        request. Rate limits are clamped to safe ceilings regardless of input."""
        try:
            clean_name = " ".join(str(name or "").split())[:120] or "rule"
            clean_request = " ".join(str(request or "").split())[:2000]
            if kind not in RULE_KINDS or not clean_request:
                return None
            rule = ProactiveRule(
                id=uuid4().hex,
                name=clean_name,
                kind=kind,
                spec=dict(spec or {}),
                request=clean_request,
                enabled=bool(enabled),
                cooldown_seconds=max(0, int(cooldown_seconds)),
                max_fires_per_day=max(1, min(int(max_fires_per_day), MAX_FIRES_PER_DAY_CEILING)),
                fires_today=0,
                fires_day="",
                last_fired_at=None,
                state={},
                created_at=_now(),
            )
            with self._lock, closing(self._connect()) as conn, conn:
                conn.execute(
                    f"INSERT INTO proactive_rules ({_RULE_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        rule.id, rule.name, rule.kind, json.dumps(rule.spec), rule.request,
                        int(rule.enabled), rule.cooldown_seconds, rule.max_fires_per_day,
                        rule.fires_today, rule.fires_day, rule.last_fired_at,
                        json.dumps(rule.state), rule.created_at,
                    ),
                )
            return rule
        except Exception:
            return None

    def list_rules(self, *, enabled_only: bool = False) -> list[ProactiveRule]:
        try:
            with self._lock, closing(self._connect()) as conn:
                sql = f"SELECT {_RULE_COLUMNS} FROM proactive_rules"
                if enabled_only:
                    sql += " WHERE enabled = 1"
                sql += " ORDER BY created_at ASC"
                return [_rule_from_row(row) for row in conn.execute(sql).fetchall()]
        except Exception:
            return []

    def get_rule(self, rule_id: str) -> ProactiveRule | None:
        try:
            with self._lock, closing(self._connect()) as conn:
                row = conn.execute(f"SELECT {_RULE_COLUMNS} FROM proactive_rules WHERE id = ?", (rule_id,)).fetchone()
            return _rule_from_row(row) if row else None
        except Exception:
            return None

    def set_enabled(self, rule_id: str, enabled: bool) -> ProactiveRule | None:
        try:
            with self._lock, closing(self._connect()) as conn, conn:
                conn.execute("UPDATE proactive_rules SET enabled = ? WHERE id = ?", (int(bool(enabled)), rule_id))
                row = conn.execute(f"SELECT {_RULE_COLUMNS} FROM proactive_rules WHERE id = ?", (rule_id,)).fetchone()
            return _rule_from_row(row) if row else None
        except Exception:
            return None

    def delete_rule(self, rule_id: str) -> bool:
        try:
            with self._lock, closing(self._connect()) as conn, conn:
                cur = conn.execute("DELETE FROM proactive_rules WHERE id = ?", (rule_id,))
                return cur.rowcount > 0
        except Exception:
            return False

    def record_fire(self, rule_id: str, *, fired_at: str, state: dict[str, Any], day: str) -> ProactiveRule | None:
        """Persist a fire: timestamp, updated trigger state, per-day counter."""
        try:
            with self._lock, closing(self._connect()) as conn, conn:
                row = conn.execute(
                    "SELECT fires_today, fires_day FROM proactive_rules WHERE id = ?", (rule_id,)
                ).fetchone()
                if row is None:
                    return None
                fires_today = int(row[0]) if row[1] == day else 0
                conn.execute(
                    "UPDATE proactive_rules SET last_fired_at = ?, state = ?, fires_today = ?, fires_day = ? WHERE id = ?",
                    (fired_at, json.dumps(state or {}), fires_today + 1, day, rule_id),
                )
                updated = conn.execute(f"SELECT {_RULE_COLUMNS} FROM proactive_rules WHERE id = ?", (rule_id,)).fetchone()
            return _rule_from_row(updated) if updated else None
        except Exception:
            return None

    def update_state(self, rule_id: str, state: dict[str, Any]) -> None:
        """Persist trigger bookkeeping without counting a fire (e.g. a file
        watcher establishing its first baseline)."""
        try:
            with self._lock, closing(self._connect()) as conn, conn:
                conn.execute("UPDATE proactive_rules SET state = ? WHERE id = ?", (json.dumps(state or {}), rule_id))
        except Exception:
            return

    # -- notifications -------------------------------------------------------

    def add_notification(self, rule_id: str, message: str) -> ProactiveNotification | None:
        try:
            text = " ".join(str(message or "").split())[:1000]
            if not text:
                return None
            note = ProactiveNotification(id=uuid4().hex, rule_id=rule_id, message=text, created_at=_now(), read=False)
            with self._lock, closing(self._connect()) as conn, conn:
                conn.execute(
                    f"INSERT INTO proactive_notifications ({_NOTE_COLUMNS}) VALUES (?, ?, ?, ?, ?)",
                    (note.id, note.rule_id, note.message, note.created_at, int(note.read)),
                )
            return note
        except Exception:
            return None

    def list_notifications(self, *, unread_only: bool = False, limit: int = 25) -> list[ProactiveNotification]:
        try:
            with self._lock, closing(self._connect()) as conn:
                sql = f"SELECT {_NOTE_COLUMNS} FROM proactive_notifications"
                if unread_only:
                    sql += " WHERE read = 0"
                sql += " ORDER BY created_at DESC LIMIT ?"
                return [_note_from_row(row) for row in conn.execute(sql, (int(limit),)).fetchall()]
        except Exception:
            return []

    def mark_all_read(self) -> int:
        try:
            with self._lock, closing(self._connect()) as conn, conn:
                cur = conn.execute("UPDATE proactive_notifications SET read = 1 WHERE read = 0")
                return cur.rowcount
        except Exception:
            return 0


__all__ = ["ProactivityStore"]
