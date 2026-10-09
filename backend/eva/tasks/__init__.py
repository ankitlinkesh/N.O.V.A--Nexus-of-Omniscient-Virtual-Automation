"""Durable, background task infrastructure (Phase 45).

A crash-safe SQLite task queue (:mod:`eva.tasks.durable_queue`) plus an opt-in,
gate-governed worker (:mod:`eva.tasks.worker`). The queue persists a *request*,
never an approval: recovering a task after a crash re-runs it through the same
permission gate, so durability never becomes a way to replay a privileged
action unattended.
"""

from __future__ import annotations

import os
from pathlib import Path

from .durable_queue import (
    ACTIVE_STATES,
    CANCELLED,
    FAILED,
    QUEUED,
    RUNNING,
    SUCCEEDED,
    TERMINAL_STATES,
    DurableTask,
    DurableTaskQueue,
)
from .worker import DurableTaskWorker
from ..core.data_paths import data_path

_ABSENT = {"", "0", "false", "no", "off"}

# Same data dir main.py uses for eva.sqlite3 (backend/../data).
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DEFAULT_QUEUE_PATH = _DATA_DIR / "eva_tasks.sqlite3"


def durable_queue_enabled(environ: dict[str, str] | None = None) -> bool:
    """Whether the durable task queue is active (default OFF, empty == off)."""
    env = environ if environ is not None else os.environ
    return env.get("EVA_DURABLE_QUEUE_ENABLED", "").strip().lower() not in _ABSENT


def default_queue_path(environ: dict[str, str] | None = None) -> Path:
    """The queue path: ``EVA_TASKS_PATH`` override, else the repo default.
    Overridable like the vault so a test or second profile does not write into
    the real queue (Phase 83)."""
    env = environ if environ is not None else os.environ
    override = env.get("EVA_TASKS_PATH", "").strip()
    return Path(override) if override else data_path(_DEFAULT_QUEUE_PATH)


def open_default_queue(environ: dict[str, str] | None = None) -> DurableTaskQueue | None:
    """Open the queue at the default data path, or ``None`` when disabled.

    Lets callers (fast-commands, startup) reach the queue without threading a
    handle everywhere, while keeping it default-off. Fail-safe."""
    try:
        if not durable_queue_enabled(environ):
            return None
        return DurableTaskQueue(default_queue_path(environ))
    except Exception:
        return None


__all__ = [
    "DurableTaskQueue",
    "DurableTask",
    "DurableTaskWorker",
    "durable_queue_enabled",
    "default_queue_path",
    "open_default_queue",
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    "TERMINAL_STATES",
    "ACTIVE_STATES",
]
