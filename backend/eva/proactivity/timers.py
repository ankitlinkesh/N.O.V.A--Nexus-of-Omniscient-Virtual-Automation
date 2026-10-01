"""One-shot timers and reminders, parsed deterministically (Phase 126).

"set a timer for 5 minutes", "remind me in 20 minutes to stretch", "remind me at
6 pm to call mom", "remind me tomorrow at 9 to submit the form".

Like :mod:`eva.proactivity.nl_rules` this is a **pure, LLM-free parser**: the same
sentence always yields the same result, and anything it does not recognise yields
``None`` so ordinary requests fall through untouched. It writes nothing; the
typed-console fast command turns a parse into a persisted ONCE rule.

Two rules keep it from swallowing ordinary speech (Phases 112 and 121-123 were
all substring bugs):

  * every phrasing is a WHOLE-sentence pattern (``^...$``). "remind me what I
    said earlier", "what time is it", "timer settings" and "set the oven to 5
    minutes" match nothing, because no phrasing is allowed to float inside a
    longer sentence;
  * the duration vocabulary is closed: seconds, minutes and hours. Days, weeks
    and everything else are refused rather than guessed at.

Limits: a duration is floored at 5 seconds (the scheduler cannot honour less)
and capped at 7 days; beyond that the caller is told, not silently clamped.

Clock and timezone are injectable. "at 6 pm" means the person's LOCAL 6 pm
(Phase 122's lesson), resolved to an absolute UTC instant here, so the stored
rule is timezone-free from then on.

A one-shot only NOTIFIES. ``request`` here is display text; nothing downstream
may enqueue it as a task ("remind me to delete my files" must stay a sentence).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Any

from .models import ONCE

MIN_SECONDS = 5
MAX_SECONDS = 7 * 24 * 3600
_MAX_TEXT = 200

_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "a": 1, "an": 1,
}
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600}

_NUMW = "|".join(sorted((re.escape(w) for w in _NUM_WORDS), key=len, reverse=True))
_UNITS = r"(?:seconds?|secs?|minutes?|mins?|hours?|hrs?)"
_TERM = r"(?:half\s+an?\s+hour|(?:\d+(?:\.\d+)?|" + _NUMW + r")\s*-?\s*" + _UNITS + r")"
_DUR = _TERM + r"(?:(?:\s*,\s*|\s+and\s+|\s+)" + _TERM + r")*"
_TERM_PARSE = re.compile(
    r"(?:(?P<half>half\s+an?\s+hour)|(?P<n>\d+(?:\.\d+)?|" + _NUMW + r")\s*-?\s*(?P<u>" + _UNITS + r"))",
    re.IGNORECASE,
)

_PRE = r"(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
_POST = r"(?:\s+please)?"
_LEAD = r"(?:remind\s+me|set\s+(?:me\s+)?(?:a\s+)?reminder)"
_LEAD_IN = r"(?:remind\s+me\s+in|set\s+(?:me\s+)?(?:a\s+)?reminder\s+(?:in|for))"
_TO = r"(?:to|that|about)"
_TIMEP = (
    r"(?:(?P<day>tomorrow|today)\s+)?at\s+(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<mer>am|pm)?"
)


def _c(pattern: str) -> re.Pattern[str]:
    return re.compile(r"^" + pattern + r"$", re.IGNORECASE)


_SET = r"(?:set|start|create|make|begin)"
_TIMER_PATTERNS = (
    # set a timer for 5 minutes / start a timer 5 minutes / set me a timer of ...
    _c(_PRE + _SET + r"\s+(?:me\s+)?(?:a\s+|an\s+|the\s+|my\s+)?(?:timer|countdown)\s+(?:(?:for|of)\s+)?(?P<d>" + _DUR + r")" + _POST),
    # set a 5 minute timer
    _c(_PRE + _SET + r"\s+(?:me\s+)?(?:a\s+|an\s+)(?P<d>" + _DUR + r")\s+(?:timer|countdown)" + _POST),
    # timer 10 min / timer for 10 minutes
    _c(_PRE + r"(?:timer|countdown)\s+(?:(?:for|of)\s+)?(?P<d>" + _DUR + r")" + _POST),
    # 5 minute timer
    _c(_PRE + r"(?P<d>" + _DUR + r")\s+(?:timer|countdown)" + _POST),
)
_REMIND_IN_PATTERNS = (
    _c(_PRE + _LEAD_IN + r"\s+(?P<d>" + _DUR + r")(?:\s*,?\s*" + _TO + r"\s+(?P<w>.+?))?" + _POST),
    _c(_PRE + _LEAD + r"\s+" + _TO + r"\s+(?P<w>.+?)\s+in\s+(?P<d>" + _DUR + r")" + _POST),
    _c(_PRE + r"in\s+(?P<d>" + _DUR + r")\s*,?\s*" + _LEAD + r"\s+" + _TO + r"\s+(?P<w>.+?)" + _POST),
)
_REMIND_AT_PATTERNS = (
    _c(_PRE + _LEAD + r"\s+(?:for\s+)?" + _TIMEP + r"(?:\s*,?\s*" + _TO + r"\s+(?P<w>.+?))?" + _POST),
    _c(_PRE + _LEAD + r"\s+" + _TO + r"\s+(?P<w>.+?)\s*,?\s+" + _TIMEP + _POST),
    _c(_PRE + _TIMEP + r"\s*,?\s*" + _LEAD + r"\s+" + _TO + r"\s+(?P<w>.+?)" + _POST),
)


@dataclass(frozen=True)
class ParsedOnce:
    """A timer/reminder recovered from a sentence. ``error`` set means "I
    understood this is a timer but cannot do it" (too long, time passed)."""

    what: str = "timer"            # "timer" | "reminder"
    text: str = ""                 # timer: "5 minutes"; reminder: what to remind
    at_utc: datetime | None = None
    seconds: int = 0               # delay from `now`
    day_word: str = ""             # "", "today" or "tomorrow" (absolute reminders)
    error: str = ""
    absolute: bool = False         # "at 6 pm" style vs "in 20 minutes"
    matched: str = field(default="", compare=False)

    @property
    def name(self) -> str:
        return f"Timer {self.text}" if self.what == "timer" else f"Reminder: {self.text}"[:120]

    def as_add_rule_kwargs(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": ONCE,
            "spec": {
                "at_utc": self.at_utc.isoformat() if self.at_utc else "",
                "what": self.what,
                "text": self.text,
                "seconds": self.seconds,
            },
            # Display text only. The engine NEVER enqueues a ONCE rule's request.
            "request": f"timer for {self.text}" if self.what == "timer" else self.text,
            "cooldown_seconds": 0,
            "max_fires_per_day": 1,
        }


def _normalize(text: object) -> str:
    out = " ".join(str(text or "").split())
    out = re.sub(r"\b([ap])\.m\.?", r"\1m", out, flags=re.IGNORECASE)
    return out.strip().rstrip(".!?, ").strip()


def _num(raw: str) -> float | None:
    raw = " ".join(raw.lower().split())
    if raw in _NUM_WORDS:
        return float(_NUM_WORDS[raw])
    try:
        return float(raw)
    except ValueError:
        return None


def parse_duration_seconds(raw: str) -> int | None:
    """Sum of the duration terms in ``raw`` ("1 hour 30 minutes", "half an
    hour"), or None. Rounds to whole seconds."""
    total = 0.0
    found = False
    for m in _TERM_PARSE.finditer(raw or ""):
        found = True
        if m.group("half"):
            total += 1800
            continue
        n = _num(m.group("n"))
        if n is None:
            return None
        total += n * _UNIT_SECONDS[m.group("u").lower()[0]]
    return int(round(total)) if found else None


def humanize_duration(seconds: int) -> str:
    """5 -> '5 seconds', 300 -> '5 minutes', 5400 -> '1 hour 30 minutes'."""
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} hour{'s' if h != 1 else ''}")
    if m:
        parts.append(f"{m} minute{'s' if m != 1 else ''}")
    if s or not parts:
        parts.append(f"{s} second{'s' if s != 1 else ''}")
    return " ".join(parts)


def _tz() -> Any:
    # Looked up on the module at call time so a test that pins
    # ``triggers._local_tz`` pins this too.
    from . import triggers

    return triggers._local_tz()


def format_local_time(moment: datetime, tz: Any = None, *, seconds: bool = False) -> str:
    """'11:42 AM' (or '11:42:17 AM') in local time, no leading zero."""
    if tz is None:
        tz = _tz()
    local = moment.astimezone(tz)
    out = local.strftime("%I:%M:%S %p" if seconds else "%I:%M %p")
    return out.lstrip("0")


def _clean_what(raw: str | None) -> str | None:
    text = " ".join(str(raw or "").split()).strip(" ,.:;!?-")
    if len(text) > _MAX_TEXT:
        return None
    return text


def _resolve_clock(h_s: str, m_s: str | None, mer: str | None, day: str, local_now: datetime):
    """Local target instant for a wall-clock phrase -> (instant, error).

    An explicit am/pm, a 24h reading (13-23, 00, or a leading zero) is
    unambiguous. A bare 1-12 is ambiguous: today it means the soonest upcoming
    reading; tomorrow it means the likelier one (1-6 -> afternoon, 7-11 ->
    morning, 12 -> noon). The reply echoes the resolved time, so a wrong guess
    is visible immediately.
    """
    try:
        hour, minute = int(h_s), (int(m_s) if m_s else 0)
    except ValueError:
        return None, "I couldn't read that time."
    if not (0 <= minute <= 59):
        return None, "I couldn't read that time."
    mer = (mer or "").lower()
    if mer:
        if not (1 <= hour <= 12):
            return None, "I couldn't read that time."
        hour = (hour % 12) + (12 if mer == "pm" else 0)
        readings = [hour]
    elif hour > 23:
        return None, "I couldn't read that time."
    elif hour == 0 or hour >= 13 or (len(h_s) == 2 and h_s.startswith("0")):
        readings = [hour]
    elif hour == 12:
        readings = [12]
    else:
        am, pm = hour, hour + 12
        readings = [pm, am] if hour <= 6 else [am, pm]  # likelier reading first
    base = local_now.date()
    tz = local_now.tzinfo

    def at(day_date, hh):
        return datetime.combine(day_date, time(hh, minute), tzinfo=tz)

    if day == "tomorrow":
        return at(base + timedelta(days=1), readings[0]), None
    upcoming = sorted(c for c in (at(base, hh) for hh in readings) if c > local_now)
    if upcoming:
        return upcoming[0], None
    if day == "today":
        return None, "That time has already passed today."
    return at(base + timedelta(days=1), readings[0]), None


def parse_once_request(text: object, now: datetime | None = None, tz: Any = None) -> ParsedOnce | None:
    """Parse a timer/reminder sentence, or ``None`` if it is not one."""
    sentence = _normalize(text)
    if not sentence:
        return None
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)

    for pat in _TIMER_PATTERNS:
        m = pat.match(sentence)
        if m:
            return _from_duration("timer", m.group("d"), None, moment, m.group(0))
    for pat in _REMIND_IN_PATTERNS:
        m = pat.match(sentence)
        if m:
            what = _clean_what(m.groupdict().get("w"))
            if what is None:
                return None
            return _from_duration("reminder", m.group("d"), what or "your reminder", moment, m.group(0))
    for pat in _REMIND_AT_PATTERNS:
        m = pat.match(sentence)
        if m:
            what = _clean_what(m.groupdict().get("w"))
            if what is None:
                return None
            zone = tz if tz is not None else _tz()
            local_now = moment.astimezone(zone)
            day = (m.group("day") or "").lower()
            local_target, err = _resolve_clock(m.group("h"), m.group("m"), m.group("mer"), day, local_now)
            if err:
                return ParsedOnce(what="reminder", text=what or "your reminder", error=err, matched=m.group(0))
            target = local_target.astimezone(timezone.utc)
            seconds = int((target - moment).total_seconds())
            if local_target.date() == local_now.date():
                day_word = "today"
            elif local_target.date() == local_now.date() + timedelta(days=1):
                day_word = "tomorrow"
            else:
                day_word = ""
            return ParsedOnce(
                what="reminder", text=what or "your reminder", at_utc=target, seconds=seconds,
                day_word=day_word, absolute=True, matched=m.group(0),
            )
    return None


def _from_duration(what: str, dur_raw: str, reminder_text: str | None, moment: datetime, matched: str) -> ParsedOnce:
    seconds = parse_duration_seconds(dur_raw)
    if seconds is None or seconds <= 0:
        return ParsedOnce(what=what, error="That isn't a duration I can time.", matched=matched)
    if seconds > MAX_SECONDS:
        return ParsedOnce(what=what, error="I can time up to 7 days; that's longer.", matched=matched)
    seconds = max(seconds, MIN_SECONDS)
    label = humanize_duration(seconds)
    return ParsedOnce(
        what=what,
        text=label if what == "timer" else (reminder_text or "your reminder"),
        at_utc=moment + timedelta(seconds=seconds),
        seconds=seconds,
        matched=matched,
    )


__all__ = [
    "ParsedOnce", "parse_once_request", "parse_duration_seconds", "humanize_duration",
    "format_local_time", "MIN_SECONDS", "MAX_SECONDS",
]
