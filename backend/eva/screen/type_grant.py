"""Typing from an ordinary chat task, limited to the user's own words.

Before this, `screen.type_text` was reachable only inside a console-opened
`gui:` scope, and even there it stopped to ask. "open notepad and type hello
from nova" opened Notepad and could not type.

The user's decision (2026-09-16): NOVA may type without asking when **the exact
text is in the user's own typed message**. That condition is what keeps the
Phase 96 invariant -- untrusted content proposes, it never authorizes -- intact
for keystrokes: a web page, a window title or a tool result can steer the model
into *proposing* a string, but it cannot put that string into the message the
user typed, so it cannot make it type without a confirmation.

Two separate mechanisms, both opened only by the agent runner:

  * **The offer** (task-wide) makes `screen.type_text` visible to the planner.
    Opened only for a goal the chat routes marked as typed by the user
    (`goal_from_user`) that asks to type (`user_asked_to_type`). Visibility is
    not authority: a call outside the grant below is still confirm-class.
  * **The grant** (one call) lowers that one call from confirm to allow. The
    runner opens it only when ALL hold: the offer conditions; the text is
    verbatim in the goal (`text_is_from_user`); the task is untainted; the
    per-task typing cap has room; and the foreground window is the app this task
    opened or focused and verified. The registry spends it only on
    `screen.type_text` with that exact text.

Nothing the model emits opens either one. Phase 55 escalation, role RED/ORANGE,
the secret-value refusal inside the handler and `EVA_ENABLE_REAL_INPUT` all
still apply.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Iterator

TYPE_TOOL = "screen.type_text"
DEFAULT_MAX_TYPES_PER_TASK = 3

_TYPE_REQUEST = re.compile(r"\btyp(?:e|ing)\b", re.IGNORECASE)


def _normalize(text: str) -> str:
    return " ".join(str(text or "").split())


def user_asked_to_type(goal: str) -> bool:
    return bool(_TYPE_REQUEST.search(_normalize(goal)))


def text_is_from_user(text: str, goal: str) -> bool:
    """True when `text` appears verbatim (case and all) in the user's goal."""
    clean = _normalize(text)
    return bool(clean) and clean in _normalize(goal)


@dataclass
class _Grant:
    text: str
    used: list[int] = field(default_factory=lambda: [0])


_offer: ContextVar[str | None] = ContextVar("eva_typing_offer", default=None)
_grant: ContextVar[_Grant | None] = ContextVar("eva_type_grant", default=None)


def typing_offered() -> bool:
    return _offer.get() is not None


def consume(tool: str, args: dict) -> bool:
    """Spend the open grant on this exact call. False otherwise."""
    grant = _grant.get()
    if grant is None or tool != TYPE_TOOL or grant.used[0] > 0:
        return False
    if _normalize(str((args or {}).get("text") or "")) != grant.text:
        return False
    grant.used[0] += 1
    return True


@contextmanager
def open_typing_offer(goal: str) -> Iterator[None]:
    token: Token = _offer.set(_normalize(goal)[:800])
    try:
        yield
    finally:
        _offer.reset(token)


@contextmanager
def open_type_grant(text: str) -> Iterator[None]:
    token: Token = _grant.set(_Grant(text=_normalize(text)))
    try:
        yield
    finally:
        _grant.reset(token)
