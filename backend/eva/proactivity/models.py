"""Data model for proactive rules and notifications (Phase 46)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Rule kinds. Each is evaluated by a pure function in :mod:`eva.proactivity.triggers`.
INTERVAL = "interval"        # spec: {"seconds": N} — fire every N seconds
DAILY = "daily"              # spec: {"at": "HH:MM"} — fire once a day at a local time
FILE_CHANGE = "file_change"  # spec: {"path": "..."} — fire when a file's fingerprint changes

RULE_KINDS = frozenset({INTERVAL, DAILY, FILE_CHANGE})

# Safety defaults: a rule may not fire more often than this, nor more times per
# day, no matter what its spec says. A runaway rule must never be able to flood
# the queue.
DEFAULT_COOLDOWN_SECONDS = 60
DEFAULT_MAX_FIRES_PER_DAY = 24
MAX_FIRES_PER_DAY_CEILING = 96


@dataclass(frozen=True)
class ProactiveRule:
    """A standing rule: when <trigger> happens, PROPOSE <request>.

    ``request`` is the task text that gets enqueued when the rule fires — it is
    a *proposal*, never an authorization (see :mod:`eva.proactivity.engine`).
    """

    id: str
    name: str
    kind: str
    spec: dict[str, Any]
    request: str
    enabled: bool = True
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS
    max_fires_per_day: int = DEFAULT_MAX_FIRES_PER_DAY
    fires_today: int = 0
    fires_day: str = ""          # the YYYY-MM-DD the counter belongs to
    last_fired_at: str | None = None
    state: dict[str, Any] = field(default_factory=dict)  # trigger bookkeeping (e.g. file fingerprint)
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProactiveNotification:
    """Something Eva wants to tell the user, recorded for them to read."""

    id: str
    rule_id: str
    message: str
    created_at: str
    read: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "ProactiveRule",
    "ProactiveNotification",
    "INTERVAL",
    "DAILY",
    "FILE_CHANGE",
    "RULE_KINDS",
    "DEFAULT_COOLDOWN_SECONDS",
    "DEFAULT_MAX_FIRES_PER_DAY",
    "MAX_FIRES_PER_DAY_CEILING",
]
