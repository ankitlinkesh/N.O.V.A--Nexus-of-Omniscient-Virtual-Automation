"""Pressing a key or key combination from an ordinary chat task, on a combo the user named.

Before this, `screen.press` and `screen.hotkey` were reachable only from a
console-opened `gui:` scope, and even there they stopped to ask ("clicking
flows, keystrokes ask" -- `core/fast_command_gui.py`). "open notepad and press
ctrl+s" opened Notepad and could not press anything.

The user's decision, the same rule they chose for typing (Phase 110) and
clicking (Phase 120): NOVA may press a key without asking ONLY when every one
of these holds:

  * the exact key combination appears in the user's OWN typed message
    (word-bounded; "ctrl+s", "control s" and "Ctrl S" are the same combo, and
    "ctrl+s" is NOT named by "ctrl+shift+s");
  * it goes to the app the task opened and verified, and that app is verified
    in front right before pressing;
  * the task is untainted;
  * the per-task cap has room.

Anything else keeps the ordinary confirm-class gate; on approval the verified
app window is restored first (Phase 117 `target_app` scope). Two mechanisms,
both opened only by the agent runner:

  * **The offer** (task-wide) makes `screen.press` and `screen.hotkey` visible
    to the planner. Opened only for a goal the chat routes marked as typed by
    the user (`goal_from_user`) that names at least one key combo. Visibility is
    not authority.
  * **The grant** (one call) is bound to one exact normalised combo and covers
    both tools. The registry spends it only on a call whose normalised keys
    equal it.

DANGEROUS COMBOS ARE NEVER GRANTED, even when the user named them
(`is_dangerous`): closing or switching windows can destroy unsaved work or move
focus to another app, so they always go to confirm. That is a hard "no grant"
-- `consume` re-checks it, so a grant opened by mistake still cannot spend on
one. Bare-key words ("enter", "tab", "up") only count when the user used them as
a key press ("press enter", "hit escape", "the enter key"), so "open a new tab"
does not name the Tab key.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Iterable, Iterator

PRESS_TOOL = "screen.press"
HOTKEY_TOOL = "screen.hotkey"
KEY_TOOLS = frozenset({PRESS_TOOL, HOTKEY_TOOL})
DEFAULT_MAX_KEYS_PER_TASK = 6

_MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")

# Spelling -> canonical name.
_ALIASES = {
    "control": "ctrl", "ctl": "ctrl", "ctrl": "ctrl",
    "alt": "alt", "option": "alt",
    "shift": "shift",
    "win": "win", "windows": "win", "super": "win", "cmd": "win", "command": "win",
    "esc": "escape", "escape": "escape",
    "del": "delete", "delete": "delete",
    "return": "enter", "enter": "enter",
    "pgup": "pageup", "page up": "pageup", "pageup": "pageup",
    "pgdn": "pagedown", "pgdown": "pagedown", "page down": "pagedown", "pagedown": "pagedown",
    "up arrow": "up", "down arrow": "down", "left arrow": "left", "right arrow": "right",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "spacebar": "space", "space": "space",
    "tab": "tab", "backspace": "backspace", "home": "home", "end": "end", "insert": "insert",
}
for _n in range(1, 13):
    _ALIASES[f"f{_n}"] = f"f{_n}"

_NAMED_KEYS = frozenset(set(_ALIASES.values()) - set(_MODIFIER_ORDER))

_MOD_WORDS = sorted((w for w, c in _ALIASES.items() if c in _MODIFIER_ORDER), key=len, reverse=True)
_KEY_WORDS = sorted(_ALIASES, key=len, reverse=True)
_MOD_RE = "(?:" + "|".join(re.escape(w) for w in _MOD_WORDS) + ")"
_NAMED_RE = "(?:" + "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in _KEY_WORDS if _ALIASES[w] not in _MODIFIER_ORDER) + ")"
_KEY_RE = rf"(?:{_NAMED_RE}|[a-z0-9])"
_SEP = r"(?:\s*\+\s*|\s*-\s*|\s+)"

# modifier(+modifier...)+key -- whole-word on both ends, and the lookbehind
# refuses to start mid-token ("xctrl+s") or after a "+" (the tail of a longer
# chain), so "ctrl+s" can never be carved out of "ctrl+shift+s".
_COMBO = re.compile(
    rf"(?<![\w+\-])(?P<mods>(?:{_MOD_RE}{_SEP})+)(?P<key>{_KEY_RE})(?![\w+])",
    re.IGNORECASE,
)

# A bare named key counts only as an explicit key press.
_PRESS_VERB = r"(?:press(?:ing)?|hit|hitting|tap|tapping|push|strike|send)"
_BARE_AFTER_VERB = re.compile(
    rf"(?<!\w){_PRESS_VERB}\s+(?:the\s+)?(?P<keys>{_NAMED_RE}(?:\s*(?:,|and then|and|then)\s*(?:the\s+)?{_NAMED_RE})*)(?!\w)",
    re.IGNORECASE,
)
_BARE_KEY_WORD = re.compile(rf"(?<!\w)(?P<key>{_NAMED_RE})\s+key(?!\w)", re.IGNORECASE)
_NAMED_ITER = re.compile(rf"(?<!\w)({_NAMED_RE})(?!\w)", re.IGNORECASE)


def _normalize(text: object) -> str:
    return " ".join(str(text or "").split())


def _canon(word: str) -> str | None:
    cleaned = " ".join(str(word or "").lower().split())
    if cleaned in _ALIASES:
        return _ALIASES[cleaned]
    if len(cleaned) == 1 and cleaned.isalnum():
        return cleaned
    return None


def _build(parts: Iterable[str]) -> str:
    mods = {p for p in parts if p in _MODIFIER_ORDER}
    keys = [p for p in parts if p not in _MODIFIER_ORDER]
    if len(keys) != 1:
        return ""
    ordered = [m for m in _MODIFIER_ORDER if m in mods]
    return "+".join([*ordered, keys[0]])


def normalize_combo(value: object) -> str:
    """Canonical combo: modifiers in a fixed order, then the key, '+'-joined.

    Accepts a string ("Ctrl+S", "control s", "esc"), or the list a `screen.hotkey`
    call carries (["ctrl", "s"], or a one-element ["ctrl+s"]). '' when it is not
    a recognisable single combo (several non-modifier keys, an unknown word).
    """
    if isinstance(value, (list, tuple)):
        text = "+".join(str(v) for v in value)
    else:
        text = str(value or "")
    text = _normalize(text).lower()
    if not text:
        return ""
    # Longest alias first so "page up" / "up arrow" win over "up".
    pieces = [p for p in re.split(r"\s*\+\s*|\s*-\s*(?=\S)|\s+", text) if p]
    parts: list[str] = []
    i = 0
    while i < len(pieces):
        two = " ".join(pieces[i:i + 2])
        if i + 1 < len(pieces) and two in _ALIASES:
            parts.append(_ALIASES[two])
            i += 2
            continue
        canon = _canon(pieces[i])
        if canon is None:
            return ""
        parts.append(canon)
        i += 1
    return _build(parts)


def named_combos(goal: str) -> set[str]:
    """Every key combo the goal names, normalised."""
    text = _normalize(goal)
    found: set[str] = set()
    for match in _COMBO.finditer(text):
        combo = normalize_combo(match.group("mods") + match.group("key"))
        if combo:
            found.add(combo)
    for match in _BARE_AFTER_VERB.finditer(text):
        for word in _NAMED_ITER.finditer(match.group("keys")):
            canon = _canon(word.group(1))
            if canon:
                found.add(canon)
    for match in _BARE_KEY_WORD.finditer(text):
        canon = _canon(match.group("key"))
        if canon:
            found.add(canon)
    return found


def user_asked_to_press(goal: str) -> bool:
    """Offer visibility: the goal names at least one key combo."""
    return bool(named_combos(goal))


def user_named_keys(combo: object, goal: str) -> bool:
    """True when `combo` (normalised) is one of the combos the goal names."""
    wanted = normalize_combo(combo)
    return bool(wanted) and wanted in named_combos(goal)


# Never granted, even when named. Closing or switching windows can destroy
# unsaved work or move focus off the verified app.
_ALWAYS_DANGEROUS = frozenset({
    "alt+f4", "ctrl+alt+delete", "ctrl+shift+escape", "ctrl+escape", "alt+escape",
    "alt+tab", "alt+shift+tab", "ctrl+alt+tab",
    # The close/quit family: ctrl+w/ctrl+q close a tab or the whole browser (and
    # a tab holding unsaved work in an editor); judged dangerous in EVERY app,
    # not only browsers, because "is it a browser" is a guess about the target.
    "ctrl+w", "ctrl+q", "ctrl+f4", "ctrl+shift+w", "ctrl+shift+q",
})


def is_dangerous(combo: object) -> bool:
    canon = normalize_combo(combo)
    if not canon:
        return True  # unrecognisable is never granted
    parts = canon.split("+")
    if canon in _ALWAYS_DANGEROUS:
        return True
    if "win" in parts:  # win+l/r/x/d/... lock, run, switch, show desktop
        return True
    if "delete" in parts:  # delete, shift+delete, ctrl+shift+delete
        return True
    if "ctrl" in parts and "alt" in parts:  # system-wide hotkeys
        return True
    return False


def keys_of_call(args: dict) -> str:
    """The normalised combo a screen.press / screen.hotkey call would send."""
    args = args or {}
    value = args.get("keys") if args.get("keys") else args.get("key")
    return normalize_combo(value)


@dataclass
class _Grant:
    combo: str
    used: list[int] = field(default_factory=lambda: [0])


_offer: ContextVar[str | None] = ContextVar("eva_key_offer", default=None)
_grant: ContextVar[_Grant | None] = ContextVar("eva_key_grant", default=None)


def keys_offered() -> bool:
    return _offer.get() is not None


def consume(tool: str, args: dict) -> bool:
    """Spend the open grant on this exact call. False otherwise."""
    grant = _grant.get()
    if grant is None or tool not in KEY_TOOLS or grant.used[0] > 0:
        return False
    combo = keys_of_call(args)
    if not combo or combo != grant.combo or is_dangerous(combo):
        return False
    grant.used[0] += 1
    return True


@contextmanager
def open_key_offer(goal: str) -> Iterator[None]:
    token: Token = _offer.set(_normalize(goal)[:800])
    try:
        yield
    finally:
        _offer.reset(token)


@contextmanager
def open_key_grant(combo: object) -> Iterator[None]:
    token: Token = _grant.set(_Grant(combo=normalize_combo(combo)))
    try:
        yield
    finally:
        _grant.reset(token)
