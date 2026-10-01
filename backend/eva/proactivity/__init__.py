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
    ONCE,
    RULE_KINDS,
    ProactiveNotification,
    ProactiveRule,
)
from .nl_rules import ParsedRule, parse_rule_request
from .timers import ParsedOnce, parse_once_request
from .store import ProactivityStore
from .triggers import should_fire

_ABSENT = {"", "0", "false", "no", "off"}

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DEFAULT_STORE_PATH = _DATA_DIR / "eva_proactivity.sqlite3"


def proactivity_enabled(environ: dict[str, str] | None = None) -> bool:
    """Whether proactivity is active (default OFF, empty == off)."""
    env = environ if environ is not None else os.environ
    return env.get("EVA_PROACTIVITY_ENABLED", "").strip().lower() not in _ABSENT


def default_store_path(environ: dict[str, str] | None = None) -> Path:
    """The rules-store path: ``EVA_PROACTIVITY_PATH`` override, else the repo
    default. Overridable like the vault so a test or second profile does not
    write into the real store (Phase 83)."""
    env = environ if environ is not None else os.environ
    override = env.get("EVA_PROACTIVITY_PATH", "").strip()
    return Path(override) if override else _DEFAULT_STORE_PATH


def open_default_store(environ: dict[str, str] | None = None) -> ProactivityStore | None:
    """Open the rules store at the default path, or ``None`` when disabled."""
    try:
        if not proactivity_enabled(environ):
            return None
        return ProactivityStore(default_store_path(environ))
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
        try:
            from ..runtime.toast import toast_notifier

            notifier = toast_notifier
        except Exception:
            notifier = None
        return ProactivityEngine(store, queue, notifier=notifier)
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
    "parse_rule_request",
    "ParsedRule",
    "ParsedOnce",
    "parse_once_request",
    "INTERVAL",
    "DAILY",
    "FILE_CHANGE",
    "ONCE",
    "RULE_KINDS",
    "MAX_PROPOSALS_PER_TICK",
]
