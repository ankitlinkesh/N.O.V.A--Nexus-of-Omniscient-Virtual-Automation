"""Typed-console timers and one-off reminders (Phase 126).

Creation, listing and cancelling live here, a leaf module like
``fast_command_rules.py``. Same trust boundary as rule creation (Phase 54):
console-only and deliberately NOT a planner tool, so untrusted web content
cannot set a reminder. A timer only NOTIFIES when it fires; it never runs
anything.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .fast_command_helpers import _PROACTIVITY_DISABLED_MSG

_ID = r"(?P<id>[0-9a-f]{4,32})"
_CANCEL_RE = re.compile(
    r"^(?:cancel|stop|delete|clear|remove)\s+(?P<scope>all\s+(?:my\s+)?|my\s+|the\s+)?(?P<noun>timers?|reminders?)(?:\s+" + _ID + r")?$"
)
_LIST_RE = re.compile(
    r"^(?:(?:list|show|what are|what's|whats)\s+)?(?:my\s+|the\s+|all\s+)?(?:active\s+)?timers?$|"
    r"^(?:how\s+(?:long|much\s+time)(?:\s+is|\s+do\s+i\s+have|\s+have\s+i\s+got)?|time)\s+(?:left|remaining)"
    r"(?:\s+(?:on|for|in|of))?(?:\s+my|\s+the)?\s+timers?$"
)


def _store():
    try:
        from ..proactivity import open_default_store, proactivity_enabled
    except Exception:
        return None, "Timers are unavailable in this build."
    if not proactivity_enabled():
        return None, _PROACTIVITY_DISABLED_MSG
    store = open_default_store()
    if store is None:
        return None, _PROACTIVITY_DISABLED_MSG
    return store, ""


def _active(store):
    from ..proactivity import ONCE
    from ..proactivity.triggers import parse_iso

    rules = [r for r in store.list_rules(enabled_only=True, kind=ONCE) if not r.last_fired_at]
    far = datetime.max.replace(tzinfo=timezone.utc)
    return sorted(rules, key=lambda r: parse_iso(r.spec.get("at_utc")) or far)


def describe_once_rule(rule, now: datetime | None = None) -> str:
    """'Timer 5 minutes: 3 minutes 12 seconds left (11:42 AM) [ab12cd34]'."""
    from ..proactivity.timers import format_local_time, humanize_duration
    from ..proactivity.triggers import parse_iso

    now = now or datetime.now(timezone.utc)
    at = parse_iso(rule.spec.get("at_utc"))
    if at is None:
        return f"{rule.name} [{rule.id[:8]}]"
    left = int((at - now).total_seconds())
    when = format_local_time(at, seconds=left < 600)
    remaining = f"{humanize_duration(left)} left" if left > 0 else "due now"
    return f"{rule.name}: {remaining} ({when}) [{rule.id[:8]}]"


def _timer_create(original: str, now: datetime | None = None) -> str | None:
    """Create a one-shot timer/reminder from a typed sentence, or None when the
    sentence is not one (so ordinary requests fall through untouched)."""
    try:
        from ..proactivity.timers import (
            format_local_time,
            humanize_duration,
            parse_once_request,
        )
    except Exception:
        return None
    moment = now or datetime.now(timezone.utc)
    parsed = parse_once_request(original, moment)
    if parsed is None:
        return None
    if parsed.error:
        return parsed.error
    store, problem = _store()
    if store is None:
        return problem
    try:
        from ..privacy.secrets_broker import contains_secret_leak

        if parsed.what == "reminder" and contains_secret_leak(parsed.text):
            return "I won't save that reminder — the text looks like it contains a secret."
    except Exception:
        pass
    # Finished one-shots are only a record; drop yesterday's.
    store.prune_done_once(older_than=(moment - timedelta(days=1)).isoformat())
    rule = store.add_rule(**parsed.as_add_rule_kwargs())
    if rule is None:
        return "I understood that, but couldn't save it. Try rephrasing."
    when = format_local_time(parsed.at_utc, seconds=parsed.seconds < 120)
    if parsed.what == "timer":
        return f"Timer set for {parsed.text} — I'll notify you at {when}."
    if parsed.absolute:
        day = {"tomorrow": " tomorrow", "today": " today"}.get(parsed.day_word, "")
        return f"Okay — I'll remind you: {parsed.text}, at {when}{day}. Say 'timers' to see it, or 'cancel my reminder'."
    return (
        f"Okay — I'll remind you in {humanize_duration(parsed.seconds)} ({when}): {parsed.text}. "
        f"Say 'timers' to see it, or 'cancel my reminder'."
    )


def _timers_list(now: datetime | None = None) -> str:
    store, problem = _store()
    if store is None:
        return problem
    active = _active(store)
    if not active:
        return "No active timers or reminders. Say 'set a timer for 5 minutes' or 'remind me in 20 minutes to stretch'."
    lines = [f"Active timers and reminders ({len(active)}):"]
    lines.extend(f"- {describe_once_rule(r, now)}" for r in active[:15])
    return "\n".join(lines)


def _timers_cancel(scope: str, noun: str, fragment: str | None) -> str:
    store, problem = _store()
    if store is None:
        return problem
    active = _active(store)
    kind_word = "timer" if noun.startswith("timer") else "reminder"
    if kind_word == "timer":
        pool = [r for r in active if r.spec.get("what") == "timer"]
    else:
        pool = [r for r in active if r.spec.get("what") != "timer"]
    if fragment:
        matches = [r for r in active if r.id.startswith(fragment)]
        if not matches:
            return f"No timer or reminder matches '{fragment}'. Say 'timers' to list them."
        if len(matches) > 1:
            return "That prefix matches several; use more characters."
        pool = matches
    else:
        if not pool:
            return f"You have no active {kind_word}s."
        if len(pool) > 1 and "all" not in (scope or ""):
            lines = [f"You have {len(pool)} active {kind_word}s — say 'cancel {kind_word} <id>' or 'cancel all {kind_word}s':"]
            lines.extend(f"- {describe_once_rule(r)}" for r in pool)
            return "\n".join(lines)
    cancelled = [r for r in pool if store.delete_rule(r.id)]
    if not cancelled:
        return "I couldn't cancel that."
    if len(cancelled) == 1:
        return f"Cancelled: {cancelled[0].name}."
    return f"Cancelled {len(cancelled)} {kind_word}s."


def maybe_handle_timer_command(original: str, normalized: str) -> str | None:
    """Dispatcher entry: list / cancel / create. None when it isn't ours."""
    text = normalized.rstrip("?.! ")
    m = _CANCEL_RE.match(text)
    if m:
        return _timers_cancel(m.group("scope") or "", m.group("noun"), m.group("id"))
    if _LIST_RE.match(text):
        return _timers_list()
    return _timer_create(original)
