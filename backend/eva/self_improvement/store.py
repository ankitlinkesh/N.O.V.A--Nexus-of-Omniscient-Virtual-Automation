"""Persistence + approval lifecycle for learned skills (Phase 47).

A skill Eva proposes is stored ``proposed`` and stays inert there until a human
approves it — self-improvement is opt-in per skill, not a standing permission.
Approval is the human's decision to make; nothing in this package can approve on
Eva's behalf.

Connection discipline follows the Phase 45 lesson: connections are closed via
``contextlib.closing``, and no method calls a public lock-taking reader while
holding ``self._lock`` (``Lock`` is not reentrant).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Iterable
from uuid import uuid4

from .models import (
    APPROVED,
    MAX_NAME_LEN,
    MAX_SKILL_STEPS,
    PROPOSED,
    REJECTED,
    LearnedSkill,
    SkillStep,
)

_COLUMNS = (
    "id, name, description, steps, status, source_trace_id, observed_count, uses, created_at, approved_at"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _steps_from_json(raw: Any) -> tuple[SkillStep, ...]:
    try:
        data = json.loads(raw or "[]")
        if not isinstance(data, list):
            return ()
        return tuple(
            SkillStep(tool=str(item.get("tool") or ""), args=dict(item.get("args") or {}))
            for item in data
            if isinstance(item, dict)
        )
    except Exception:
        return ()


def _row_to_skill(row: tuple) -> LearnedSkill:
    return LearnedSkill(
        id=row[0],
        name=row[1],
        description=row[2],
        steps=_steps_from_json(row[3]),
        status=row[4],
        source_trace_id=row[5] or "",
        observed_count=int(row[6]),
        uses=int(row[7]),
        created_at=row[8] or "",
        approved_at=row[9],
    )


class SkillStore:
    """SQLite persistence for learned skills and their approval state."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10.0)

    def _fetch(self, conn: sqlite3.Connection, skill_id: str) -> LearnedSkill | None:
        row = conn.execute(f"SELECT {_COLUMNS} FROM learned_skills WHERE id = ?", (skill_id,)).fetchone()
        return _row_to_skill(row) if row else None

    def _init_db(self) -> None:
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS learned_skills (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    steps TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_trace_id TEXT,
                    observed_count INTEGER NOT NULL,
                    uses INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    approved_at TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_learned_skills_status ON learned_skills(status)")

    def propose(
        self,
        name: str,
        description: str,
        steps: Iterable[SkillStep],
        *,
        source_trace_id: str = "",
        observed_count: int = 1,
    ) -> LearnedSkill | None:
        """Record a proposed skill. It is INERT until approved.

        Returns ``None`` for an empty/oversized skill or a duplicate name.
        """
        try:
            clean_name = " ".join(str(name or "").split())[:MAX_NAME_LEN]
            step_list = list(steps)
            if not clean_name or not step_list or len(step_list) > MAX_SKILL_STEPS:
                return None
            if self.get_by_name(clean_name) is not None:
                return None
            skill = LearnedSkill(
                id=uuid4().hex,
                name=clean_name,
                description=" ".join(str(description or "").split())[:500],
                steps=tuple(step_list),
                status=PROPOSED,
                source_trace_id=str(source_trace_id or ""),
                observed_count=max(1, int(observed_count)),
                uses=0,
                created_at=_now(),
                approved_at=None,
            )
            payload = json.dumps([s.as_dict() for s in skill.steps])
            with self._lock, closing(self._connect()) as conn, conn:
                conn.execute(
                    f"INSERT INTO learned_skills ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        skill.id, skill.name, skill.description, payload, skill.status,
                        skill.source_trace_id, skill.observed_count, skill.uses,
                        skill.created_at, skill.approved_at,
                    ),
                )
            return skill
        except Exception:
            return None

    def approve(self, skill_id: str) -> LearnedSkill | None:
        """A human approves a proposed skill, making it runnable."""
        return self._set_status(skill_id, APPROVED, stamp_approved=True)

    def reject(self, skill_id: str) -> LearnedSkill | None:
        return self._set_status(skill_id, REJECTED, stamp_approved=False)

    def _set_status(self, skill_id: str, status: str, *, stamp_approved: bool) -> LearnedSkill | None:
        try:
            with self._lock, closing(self._connect()) as conn, conn:
                skill = self._fetch(conn, skill_id)
                if skill is None:
                    return None
                conn.execute(
                    "UPDATE learned_skills SET status = ?, approved_at = ? WHERE id = ?",
                    (status, _now() if stamp_approved else None, skill_id),
                )
                return self._fetch(conn, skill_id)
        except Exception:
            return None

    def record_use(self, skill_id: str) -> None:
        try:
            with self._lock, closing(self._connect()) as conn, conn:
                conn.execute("UPDATE learned_skills SET uses = uses + 1 WHERE id = ?", (skill_id,))
        except Exception:
            return

    def get(self, skill_id: str) -> LearnedSkill | None:
        try:
            with self._lock, closing(self._connect()) as conn:
                return self._fetch(conn, skill_id)
        except Exception:
            return None

    def get_by_name(self, name: str) -> LearnedSkill | None:
        try:
            with self._lock, closing(self._connect()) as conn:
                row = conn.execute(f"SELECT {_COLUMNS} FROM learned_skills WHERE name = ?", (name,)).fetchone()
            return _row_to_skill(row) if row else None
        except Exception:
            return None

    def list_skills(self, *, status: str | None = None, limit: int = 50) -> list[LearnedSkill]:
        try:
            with self._lock, closing(self._connect()) as conn:
                if status:
                    rows = conn.execute(
                        f"SELECT {_COLUMNS} FROM learned_skills WHERE status = ? ORDER BY observed_count DESC, created_at ASC LIMIT ?",
                        (status, int(limit)),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"SELECT {_COLUMNS} FROM learned_skills ORDER BY created_at DESC LIMIT ?",
                        (int(limit),),
                    ).fetchall()
            return [_row_to_skill(row) for row in rows]
        except Exception:
            return []


__all__ = ["SkillStore"]
