from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .action_model import AgentAction, RollbackResult
from ..core.data_paths import data_path


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    task_id: str
    action_id: str
    checkpoint_type: str
    target: str
    checkpoint_data: dict[str, Any]
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class CheckpointStore:
    def __init__(self, path: Path | None = None, *, root: Path | None = None, max_file_bytes: int = 2_000_000) -> None:
        data_root = data_path(Path(__file__).resolve().parents[3] / "data")
        self.path = path or (data_root / "agent_checkpoints.sqlite3")
        self.root = root or (data_root / "checkpoints")
        self.max_file_bytes = max_file_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_checkpoints (
                    id INTEGER PRIMARY KEY,
                    checkpoint_id TEXT,
                    task_id TEXT,
                    action_id TEXT,
                    checkpoint_type TEXT,
                    target TEXT,
                    checkpoint_data TEXT,
                    created_at TEXT
                )
                """
            )

    def create_checkpoint(self, action: AgentAction, task_id: str = "local-task") -> Checkpoint | None:
        target = str(action.rollback.get("target") or action.params.get("path") or action.params.get("src") or "")
        checkpoint_type = str(action.rollback.get("checkpoint_type") or "metadata_only")
        data: dict[str, Any] = {}
        if checkpoint_type == "file_snapshot" and target:
            path = Path(target)
            if not path.exists() or not path.is_file() or path.stat().st_size > self.max_file_bytes:
                checkpoint_type = "metadata_only"
                data = {"exists": path.exists(), "reason": "missing_or_too_large"}
            else:
                checkpoint_id = uuid4().hex
                snapshot = self.root / f"{checkpoint_id}_{path.name}"
                shutil.copy2(path, snapshot)
                data = {"snapshot": str(snapshot)}
                return self._record(checkpoint_id, task_id, action.action_id, checkpoint_type, target, data)
        return self._record(uuid4().hex, task_id, action.action_id, checkpoint_type, target, data)

    def _record(self, checkpoint_id: str, task_id: str, action_id: str, checkpoint_type: str, target: str, data: dict[str, Any]) -> Checkpoint:
        created = datetime.now(timezone.utc).isoformat()
        checkpoint = Checkpoint(checkpoint_id, task_id, action_id, checkpoint_type, target, data, created)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_checkpoints (checkpoint_id, task_id, action_id, checkpoint_type, target, checkpoint_data, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (checkpoint_id, task_id, action_id, checkpoint_type, target, json.dumps(data), created),
            )
        return checkpoint

    def restore_checkpoint(self, checkpoint_id: str) -> RollbackResult:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT action_id, checkpoint_type, target, checkpoint_data FROM agent_checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).fetchone()
        if not row:
            return RollbackResult(checkpoint_id, True, False, "Checkpoint not found.", "checkpoint_not_found")
        action_id, checkpoint_type, target, raw_data = row
        data = json.loads(raw_data or "{}")
        if checkpoint_type == "file_snapshot" and data.get("snapshot") and target:
            shutil.copy2(Path(data["snapshot"]), Path(target))
            return RollbackResult(action_id, True, True, f"Restored file checkpoint for {target}.")
        return RollbackResult(action_id, True, False, "No restorable checkpoint data.", "not_restorable")

    def list_checkpoints(self, task_id: str) -> list[Checkpoint]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT checkpoint_id, task_id, action_id, checkpoint_type, target, checkpoint_data, created_at FROM agent_checkpoints WHERE task_id = ? ORDER BY created_at",
                (task_id,),
            ).fetchall()
        return [Checkpoint(a, b, c, d, e, json.loads(f or "{}"), g) for a, b, c, d, e, f, g in rows]


def create_checkpoint(action: AgentAction) -> Checkpoint | None:
    return CheckpointStore().create_checkpoint(action)


def restore_checkpoint(checkpoint_id: str) -> RollbackResult:
    return CheckpointStore().restore_checkpoint(checkpoint_id)
