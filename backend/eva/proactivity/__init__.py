"""Proactivity — scheduled and triggered agents (Phase 46).

Eva's first ability to act without being asked. The safety rule that makes it
tenable: **a trigger PROPOSES work, it never AUTHORIZES it.** A firing rule
enqueues a request onto the Phase 45 durable queue and records a notification;
execution happens later through the ordinary gate-governed path, where a
privileged action still waits for a human's confirmation. See
:mod:`eva.proactivity.engine`.
"""

from __future__ import annotations

import os
from pathlib import Path

from .engine import MAX_PROPOSALS_PER_TICK, ProactivityEngine
from .models import (
    DAILY,
    FILE_CHANGE,
    INTERVAL,
    RULE_KINDS,
    ProactiveNotification,
    ProactiveRule,
)
from .store import ProactivityStore
from .triggers import should_fire

_ABSENT = {"", "0", "false", "no", "off"}

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DEFAULT_STORE_PATH = _DATA_DIR / "eva_proactivity.sqlite3"


def proactivity_enabled(environ: dict[str, str] | None = None) -> bool:
    """Whether proactivity is active (default OFF, empty == off)."""
    env = environ if environ is not None else os.environ
    return env.get("EVA_PROACTIVITY_ENABLED", "").strip().lower() not in _ABSENT


def default_store_path() -> Path:
    return _DEFAULT_STORE_PATH


def open_default_store(environ: dict[str, str] | None = None) -> ProactivityStore | None:
    """Open the rules store at the default path, or ``None`` when disabled."""
    try:
        if not proactivity_enabled(environ):
            return None
        return ProactivityStore(_DEFAULT_STORE_PATH)
    except Exception:
        return None


def open_default_engine(environ: dict[str, str] | None = None) -> ProactivityEngine | None:
    """A ready engine wired to the default rules store and the durable queue.

    ``None`` when proactivity is off. The queue is attached only if the durable
    queue is itself enabled; without it the engine can still evaluate and
    notify, but has nowhere to propose work to."""
    try:
        store = open_default_store(environ)
        if store is None:
            return None
        try:
            from ..tasks import open_default_queue

            queue = open_default_queue(environ)
        except Exception:
            queue = None
        return ProactivityEngine(store, queue)
    except Exception:
        return None


__all__ = [
    "ProactivityEngine",
    "ProactivityStore",
    "ProactiveRule",
    "ProactiveNotification",
    "proactivity_enabled",
    "default_store_path",
    "open_default_store",
    "open_default_engine",
    "should_fire",
    "INTERVAL",
    "DAILY",
    "FILE_CHANGE",
    "RULE_KINDS",
    "MAX_PROPOSALS_PER_TICK",
]
