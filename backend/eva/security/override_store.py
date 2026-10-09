from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from ..core.data_paths import data_path


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class OverrideGrant:
    action_id: str
    action_type: str
    risk_categories: list[str]
    granted: bool
    reason: str
    created_at: str
    expires_at: str
    path: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class OverrideStore:
    def __init__(self, path: Path | None = None, *, expires_after_seconds: int = 120) -> None:
        root = data_path(Path(__file__).resolve().parents[3] / "data")
        self.path = path or (root / "override_events.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.expires_after_seconds = expires_after_seconds
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS override_events (
                    id INTEGER PRIMARY KEY,
                    action_id TEXT,
                    action_type TEXT,
                    risk_categories TEXT,
                    user_phrase TEXT,
                    granted INTEGER,
                    reason TEXT,
                    created_at TEXT,
                    expires_at TEXT
                )
                """
            )

    def create_override(self, action_id: str, action_type: str, risks: list[str], phrase: str, reason: str) -> OverrideGrant:
        created = _now()
        expires = created + timedelta(seconds=self.expires_after_seconds)
        granted = phrase.strip().lower() == "confirm override"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO override_events (action_id, action_type, risk_categories, user_phrase, granted, reason, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (action_id, action_type, json.dumps(risks), phrase, int(granted), reason, created.isoformat(), expires.isoformat()),
            )
        return OverrideGrant(action_id, action_type, risks, granted, reason, created.isoformat(), expires.isoformat(), str(self.path))

    def is_override_valid(self, action_id: str) -> bool:
        now = _now().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT granted FROM override_events WHERE action_id = ? AND granted = 1 AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
                (action_id, now),
            ).fetchone()
        return bool(row)

    def expire_old_overrides(self) -> int:
        now = _now().isoformat()
        with self._connect() as conn:
            cur = conn.execute("UPDATE override_events SET granted = 0 WHERE granted = 1 AND expires_at <= ?", (now,))
            return int(cur.rowcount or 0)

    def log_denied_override(self, action_id: str, action_type: str, risks: list[str], phrase: str, reason: str) -> None:
        created = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO override_events (action_id, action_type, risk_categories, user_phrase, granted, reason, created_at, expires_at)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (action_id, action_type, json.dumps(risks), phrase, reason, created.isoformat(), created.isoformat()),
            )
