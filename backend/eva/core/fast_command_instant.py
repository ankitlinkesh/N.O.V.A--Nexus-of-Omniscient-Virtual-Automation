"""Instant answers (Phase 125): common read-only questions with no LLM call.

Measured through POST /api/chat before this phase, "what time is it" took 10s,
"what's my battery level?" 7.4s and "how much free space is on my C drive?" 5.1s.
Every one was two LLM calls wrapped around a tool that returns in milliseconds:
one call to pick the tool, one to phrase "battery=81%, plugged in" as a sentence.

Two pieces live here, sharing ONE formatter per tool:

1. ``maybe_handle_instant_answer`` -- a closed list of whole-question phrasings,
   each bound to an existing allow-class tool and answered from a template.
2. ``synthesize_single_result`` -- used by the planner path so a single
   successful call to one of these tools skips the second ("tool-synthesis")
   LLM call. Everything else keeps the LLM.

The matching rules are the ones Phases 112 and 121-123 paid for:

- The WHOLE normalized message must match a pattern anchored at both ends. There
  is no substring or prefix match, so "what time is the meeting tomorrow",
  "what time is it in Tokyo" and "is the battery in my car good" fall through to
  the planner untouched.
- If ``split_trailing_request`` finds a second request ("what time is it and open
  chrome") this declines, so the agent loop handles both halves rather than this
  answering one and silently dropping the other.
- The tools run through ``tools.run`` (the registry), never their handlers, so
  the gate, role containment and logging still apply.

A template only states what the tool result contains. A missing field produces
a plainer sentence or ``None`` (decline -> LLM), never an invented value.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_WS = re.compile(r"\s+")


def normalize_question(text: str) -> str:
    """Lowercase, straighten quotes, drop "please" and trailing ?.! , collapse spaces."""
    t = str(text or "").lower().replace("’", "'").replace("‘", "'")
    t = _WS.sub(" ", t).strip()
    t = re.sub(r"[\s?.!,]+$", "", t)
    t = re.sub(r"^(?:please|pls)[\s,]+", "", t)
    t = re.sub(r"[\s,]+(?:please|pls)$", "", t)
    return t.strip()


_S = r"(?:'s| is)"  # what's / what is
_NOW = r"(?: right now| now| currently)?"
_MY = r"(?:my |the )?"

# --- patterns: (kind, regex). Each is fullmatch-ed against the normalized text.
_TIME = [
    ("time", rf"what{_S} the (?:current )?time{_NOW}"),
    ("time", rf"what time is it{_NOW}"),
    ("time", r"(?:the |current )?time"),
    ("time", r"tell me the time"),
    ("date", rf"what{_S} (?:the |today'?s )?(?:current )?date(?: today)?"),
    ("date", rf"what{_S} today'?s date"),
    ("date", r"(?:the |today'?s )?date"),
    ("day", rf"what day is (?:it|today)(?: today)?"),
    ("day", rf"what{_S} the day(?: today)?"),
]
_BATTERY = [
    ("battery", rf"{_MY}battery(?: level| percentage| percent| status| life)?{_NOW}"),
    ("battery", rf"what{_S} {_MY}battery(?: level| percentage| percent| status| life)?{_NOW}"),
    ("battery", rf"how much battery(?: do i have| is left| life)?(?: left| remaining)?{_NOW}"),
    ("plugged", rf"am i plugged in{_NOW}"),
    ("plugged", rf"is {_MY}(?:laptop|pc|computer) (?:currently )?(?:plugged in|charging){_NOW}"),
]
# A drive is named "C:", "C drive", or "drive C" -- never a bare letter, so "a drive" is not drive A.
_DRIVE = r"(?:(?P<l1>[b-z]):\\?|(?P<l2>[b-z]) drive|drive (?P<l3>[b-z]))"
_WHOLE_DISK = r"(?:disk|drive|hard drive|hard disk|storage|computer|pc|laptop|machine|system)"
_TARGET = rf"(?:{_MY}{_DRIVE}|{_MY}{_WHOLE_DISK})"
_SPACEWORDS = r"(?:free |disk |storage |drive )*space"
_TRAIL = r"(?: left| free| available| remaining)*"
_DISK = [
    ("disk", rf"how much {_SPACEWORDS}(?: do i have| is there| is)?{_TRAIL}(?: (?:on|in|of) {_TARGET}){{0,1}}{_TRAIL}"),
    ("disk", rf"how much (?:is )?(?:free|left)(?: space)?(?: (?:on|in|of) {_TARGET})?"),
    ("disk", rf"(?:what{_S} )?{_MY}(?:free |disk |storage )?(?:disk |storage |drive )?space(?: usage)?{_TRAIL}(?: (?:on|in|of) {_TARGET})?"),
    ("disk", rf"(?:what{_S} )?{_MY}(?:disk|storage)(?: space| usage)?{_TRAIL}"),
    ("disk", rf"(?:disk|storage|drive) space(?: usage)?{_TRAIL}(?: (?:on|in|of) {_TARGET})?"),
    ("disk", rf"storage(?: space)?{_TRAIL}"),
]
_MEMORY = [
    ("memory", rf"(?:what{_S} )?{_MY}(?:memory|ram) usage{_NOW}"),
    ("memory", rf"how much (?:ram|memory) (?:am i using|do i have|is (?:being )?used|is in use|are we using){_NOW}"),
    ("memory", rf"how much (?:of )?{_MY}(?:ram|memory) (?:am i using|is (?:being )?used|is in use){_NOW}"),
]
_WINDOWS = [
    ("windows", rf"(?:which|what) windows are (?:currently )?open{_NOW}"),
    ("windows", rf"(?:which|what) (?:apps|programs|applications) are (?:currently )?open{_NOW}"),
    ("windows", rf"what{_S} (?:currently )?open{_NOW}"),
    ("windows", rf"(?:list|show)(?: me)?(?: all)? {_MY}open (?:windows|apps|programs)"),
    ("windows", r"open windows"),
]
_FOLDERS = r"(?P<folder>downloads|documents|desktop)"
_COUNTS = [
    ("count", rf"how many (?:files|items|things) (?:are )?(?:there )?(?:in|inside) {_MY}{_FOLDERS}(?: folder| directory)?"),
    ("count", rf"how many (?:files|items) do i have (?:in|inside) {_MY}{_FOLDERS}(?: folder| directory)?"),
]

_PATTERNS = [(kind, re.compile(rx)) for kind, rx in (*_TIME, *_BATTERY, *_DISK, *_MEMORY, *_WINDOWS, *_COUNTS)]


def match_instant_question(text: str) -> tuple[str, dict[str, str]] | None:
    """Pure: which closed-list question is this, or None. Whole-message only."""
    # Defence in depth: the patterns are anchored, but a second request must
    # never be answered as if it were absent.
    try:
        from ..agent.policies import split_trailing_request

        _head, tail = split_trailing_request(text)
        if tail:
            return None
    except Exception:
        pass
    norm = normalize_question(text)
    if not norm:
        return None
    for kind, rx in _PATTERNS:
        m = rx.fullmatch(norm)
        if m:
            groups = {k: v for k, v in m.groupdict().items() if v}
            letter = groups.get("l1") or groups.get("l2") or groups.get("l3")
            if letter:
                groups["letter"] = letter.upper()
            return kind, groups
    return None


# ---------------------------------------------------------------- formatters
def _date_words(local_date: str) -> str | None:
    try:
        d = datetime.strptime(local_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None
    return f"{d.strftime('%A')}, {d.strftime('%B')} {d.day}, {d.year}"


def format_time(result: Any, kind: str = "full") -> str | None:
    if not isinstance(result, dict) or result.get("ok") is False:
        return None
    clock = result.get("local_time_12h") or result.get("local_time")
    date = _date_words(str(result.get("local_date") or ""))
    weekday = result.get("weekday")
    zone = result.get("timezone")
    if kind == "day":
        return f"It's {weekday}." if weekday else None
    if kind == "date":
        return f"Today is {date}." if date else None
    if not clock:
        return None
    tail = f" on {date}" if date else ""
    zone_note = f" ({zone})" if zone else ""
    return f"It's {clock}{tail}{zone_note}."


def format_status(result: Any, kind: str = "full") -> str | None:
    if not isinstance(result, dict):
        return None
    if kind in {"battery", "plugged"}:
        if result.get("battery_present") is False:
            return "This machine doesn't report a battery."
        pct = result.get("battery_percent")
        if pct is None:
            return None
        plugged = result.get("plugged_in")
        if plugged is True:
            state = "plugged in"
        elif plugged is False:
            state = "running on battery"
        else:
            state = None
        if kind == "plugged":
            if state is None:
                return f"Battery is at {pct}%, but Windows didn't say whether it's plugged in."
            return f"Yes, you're plugged in. Battery is at {pct}%." if plugged else f"No, you're running on battery. It's at {pct}%."
        text = f"Battery is at {pct}%" + (f" and you're {state}" if state else "") + "."
        minutes = result.get("battery_minutes_left")
        if plugged is False and isinstance(minutes, int) and minutes > 0:
            text += f" About {minutes // 60}h {minutes % 60}m left."
        return text
    if kind == "memory":
        used, total = result.get("memory_percent_used"), result.get("memory_total_gb")
        if used is None:
            return None
        return f"Memory is {used}% in use" + (f" of {total} GB installed." if total is not None else ".")
    if kind == "disk":
        return None  # needs the drive letter; see format_disks
    # full: everything the result carries, nothing it doesn't.
    lines = []
    if result.get("os_name"):
        lines.append(f"OS: {result['os_name']}.")
    battery = format_status(result, "battery")
    if battery:
        lines.append(battery)
    memory = format_status(result, "memory")
    if memory:
        lines.append(memory)
    disks = format_disks(result)
    if disks:
        lines.append(disks)
    return "\n".join(lines) if lines else None


def format_disks(result: Any, letter: str | None = None) -> str | None:
    if not isinstance(result, dict):
        return None
    disks = [d for d in (result.get("disks") or []) if isinstance(d, dict) and d.get("drive")]
    if not disks:
        return None
    if letter:
        want = f"{letter.upper()}:"
        for d in disks:
            if str(d["drive"]).upper() == want:
                return f"{d['drive']} has {d.get('free_gb')} GB free of {d.get('total_gb')} GB."
        names = ", ".join(str(d["drive"]) for d in disks)
        return f"I don't see a fixed drive {want} on this machine. Fixed drives: {names}."
    parts = [f"{d['drive']} {d.get('free_gb')} GB free of {d.get('total_gb')} GB" for d in disks]
    return "Free space: " + "; ".join(parts) + "."


# Overlay/system windows nobody means by "what's open".
_HIDDEN_TITLES = {"program manager", "windows input experience", "microsoft text input application", "task switching"}
_HIDDEN_PROCESSES = {"cua-driver.exe", "textinputhost.exe"}


def _is_user_window(item: dict) -> bool:
    title = str(item.get("title") or "").strip()
    if not title:
        return False
    low = title.lower()
    if low in _HIDDEN_TITLES or "overlay" in low or low.startswith("cua."):
        return False
    return str(item.get("process_name") or "").lower() not in _HIDDEN_PROCESSES


def format_windows(result: Any, limit: int = 15) -> str | None:
    if not isinstance(result, dict) or result.get("ok") is False or not isinstance(result.get("windows"), list):
        return None
    seen: set[str] = set()
    rows = []
    for item in result["windows"]:
        if not isinstance(item, dict) or not _is_user_window(item):
            continue
        key = str(item["title"]).strip().lower()
        if key in seen:  # UWP apps appear twice (app + ApplicationFrameHost)
            continue
        seen.add(key)
        proc = str(item.get("process_name") or "").removesuffix(".exe").removesuffix(".EXE")
        rows.append(f"- {str(item['title']).strip()}" + (f" ({proc})" if proc else ""))
    if not rows:
        return "I don't see any open app windows."
    shown = rows[:limit]
    head = f"Open windows ({len(rows)}):"
    more = f"\n...and {len(rows) - limit} more." if len(rows) > limit else ""
    return head + "\n" + "\n".join(shown) + more


def format_listing(result: Any, *, names: bool = True, label: str | None = None, max_names: int = 15) -> str | None:
    if not isinstance(result, dict) or result.get("ok") is False:
        return None
    total = result.get("total")
    items = result.get("items")
    if not isinstance(total, int) or not isinstance(items, list):
        return None
    where = label or str(result.get("path") or "That folder")
    noun = "item" if total == 1 else "items"
    text = f"{where} has {total} {noun} (files and folders combined)."
    if names and items:
        shown = ", ".join(str(n) for n in items[:max_names])
        rest = total - min(len(items), max_names)
        text += f" {'First' if rest > 0 else 'They are'}: {shown}" + (f", and {rest} more." if rest > 0 else ".")
    return text


# ----------------------------------------------------------------- dispatch
_FAILED = "I couldn't read that right now"


def _run(tools: Any, name: str, **kwargs: Any) -> tuple[Any, str | None]:
    """tools.run, returning (result, early_reply). early_reply set when parked/denied/raised."""
    try:
        result = tools.run(name, **kwargs)
    except Exception as exc:
        return None, f"{_FAILED}: {exc}"
    if isinstance(result, dict):
        if result.get("requires_confirmation") or result.get("pending_id") or result.get("requires_override"):
            return None, str(result.get("message") or "This needs your confirmation first.")
        if result.get("role_denied"):
            return None, str(result.get("message") or "Refused by role policy.")
    return result, None


def maybe_handle_instant_answer(
    message: str,
    tools: Any,
    session_context: dict | None = None,
) -> tuple[str, str] | None:
    matched = match_instant_question(message)
    if matched is None:
        return None
    kind, groups = matched
    if kind in {"time", "date", "day"}:
        result, early = _run(tools, "system_time")
        reply = early or format_time(result, kind)
    elif kind in {"battery", "plugged", "memory", "disk"}:
        result, early = _run(tools, "system_status")
        if kind == "disk":
            reply = early or format_disks(result, groups.get("letter"))
        else:
            reply = early or format_status(result, kind)
    elif kind == "windows":
        result, early = _run(tools, "window_list")
        reply = early or format_windows(result)
    elif kind == "count":
        folder = groups["folder"].capitalize()
        result, early = _run(tools, "file.list_dir", path=folder)
        reply = early or format_listing(result, names=False, label=f"Your {folder} folder")
    else:  # pragma: no cover - every kind is handled above
        return None
    if not reply:
        # The tool answered but not with what the template needs: say so rather than guess.
        reply = f"{_FAILED}; the {kind} reading came back empty."
    return reply, "instant-answer"


# ------------------------------------------------------- planner synthesis
_LISTING_ASK = re.compile(r"\b(how many|number of|count|list|show|what'?s in|what is in|contents?|files?|items?)\b", re.I)
_NAMES_ASK = re.compile(r"\b(list|show|what'?s in|what is in|contents?)\b", re.I)


def synthesize_single_result(message: str, results: list[Any]) -> str | None:
    """Template reply for ONE successful call to a templated tool, else None (-> LLM)."""
    if len(results) != 1:
        return None
    r = results[0]
    if not getattr(r, "ok", False) or getattr(r, "requires_confirmation", False) or getattr(r, "error", None):
        return None
    tool, data = getattr(r, "tool", ""), getattr(r, "result", None)
    if tool == "system_time":
        return format_time(data, "full")
    if tool in {"system_status", "status"}:
        return format_status(data, "full")
    if tool == "window_list":
        return format_windows(data)
    if tool == "file.list_dir":
        # A listing answers "how many / what's in"; it does not answer "is X in there".
        if not _LISTING_ASK.search(str(message or "")):
            return None
        # A pure count question gets the count; names only when a listing was asked for.
        wants_names = bool(_NAMES_ASK.search(str(message or "")))
        return format_listing(data, names=wants_names)
    return None
