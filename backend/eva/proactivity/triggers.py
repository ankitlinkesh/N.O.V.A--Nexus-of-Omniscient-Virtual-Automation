"""Trigger evaluation — pure, deterministic, clock-injected (Phase 46).

Each evaluator answers one question: *given this rule, this moment, and the
bookkeeping state from last time, should the rule fire now?* — and returns any
updated state. Nothing here touches the queue, the gate, or executes anything;
these are predicates, which is what makes proactivity testable without waiting
for real time to pass or real files to change.

Timekeeping is UTC-based and the ``now`` is always passed in, so a test can drive
a whole day of schedule behavior in microseconds.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import DAILY, FILE_CHANGE, INTERVAL, ProactiveRule


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO timestamp to an aware UTC datetime; ``None`` if unusable."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _file_fingerprint(path: str) -> dict[str, Any] | None:
    """A cheap change-detector for a file: (mtime, size). ``None`` if missing."""
    try:
        stat = os.stat(path)
        return {"mtime": stat.st_mtime, "size": stat.st_size}
    except Exception:
        return None


def _interval_should_fire(rule: ProactiveRule, now: datetime) -> bool:
    try:
        seconds = int(rule.spec.get("seconds") or 0)
    except (TypeError, ValueError):
        return False
    if seconds <= 0:
        return False
    last = parse_iso(rule.last_fired_at)
    if last is None:
        return True  # never fired: due immediately
    return (now - last) >= timedelta(seconds=seconds)


def _daily_should_fire(rule: ProactiveRule, now: datetime) -> bool:
    """Fire once per day, the first time we look at/after the target time."""
    raw = str(rule.spec.get("at") or "").strip()
    try:
        hour_str, minute_str = raw.split(":", 1)
        hour, minute = int(hour_str), int(minute_str)
    except (ValueError, TypeError):
        return False
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return False
    target_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < target_today:
        return False  # not time yet today
    last = parse_iso(rule.last_fired_at)
    if last is None:
        return True
    # Already fired at/after today's target? Then we're done for today.
    return last < target_today


def _file_change_should_fire(rule: ProactiveRule, now: datetime) -> tuple[bool, dict[str, Any]]:
    """Fire when a watched file's fingerprint changes.

    The first observation only establishes a baseline — a watcher must not fire
    merely because it has never looked before.
    """
    path = str(rule.spec.get("path") or "").strip()
    state = dict(rule.state or {})
    if not path:
        return False, state
    fingerprint = _file_fingerprint(path)
    previous = state.get("fingerprint")
    if fingerprint is None:
        # File missing/unreadable. If we had a baseline, its disappearance is a
        # change worth reporting once; otherwise stay quiet.
        if previous is None:
            return False, state
        state["fingerprint"] = None
        return True, state
    if previous is None:
        state["fingerprint"] = fingerprint  # baseline only, no fire
        return False, state
    if previous != fingerprint:
        state["fingerprint"] = fingerprint
        return True, state
    return False, state


def should_fire(rule: ProactiveRule, now: datetime) -> tuple[bool, dict[str, Any]]:
    """Whether ``rule`` fires at ``now``, plus its updated trigger state.

    Pure and fail-safe: an unknown kind or a malformed spec never fires and never
    raises (a broken rule must not be able to wedge or spam the engine).
    """
    try:
        if not rule.enabled:
            return False, dict(rule.state or {})
        if rule.kind == INTERVAL:
            return _interval_should_fire(rule, now), dict(rule.state or {})
        if rule.kind == DAILY:
            return _daily_should_fire(rule, now), dict(rule.state or {})
        if rule.kind == FILE_CHANGE:
            return _file_change_should_fire(rule, now)
        return False, dict(rule.state or {})
    except Exception:
        return False, dict(rule.state or {})


__all__ = ["should_fire", "parse_iso"]
