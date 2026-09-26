"""Clicking from an ordinary chat task, on a label the user named themselves.

Before this, `screen.click` was reachable only from a console-opened `gui:`
scope (Phase 96), and even there it already ran without a confirmation prompt
("clicking flows, keystrokes ask" -- see `core/fast_command_gui.py`). Outside
that scope it was simply invisible to the planner, so an ordinary chat task
that needed to click something could not.

The user's decision ("Label named in my message"): NOVA may click a control
without asking, from an ordinary agent task, ONLY when every one of these
holds:

  * the control's label appears in the user's OWN typed message;
  * the click lands inside the app the task opened and verified, and that
    app is verified in front right before clicking;
  * the task is untainted.

Anything else -- no offer, a label not in the goal, a substring-only match, a
tainted task, the wrong app in front, or a raw-coordinate call -- keeps the
ordinary confirm-class gate. This mirrors Phase 110's typing grant exactly,
with one structural difference: `screen.type_text` was ALREADY confirm-class
everywhere by its own ToolSpec, so the grant only ever lowered friction.
`screen.click`'s static class is allow (`SAFE_LOCAL_UI`, `safety_level="safe"`)
because inside a `gui:` scope that is the deliberate, unrelated Phase 96
decision. So the registry gate (see `tools/registry.py::ToolRegistry.run`)
first RAISES friction for a click outside a `gui:` scope, then this module's
grant lowers it back for the one call that earns it -- the escalate-then-grant
shape, not grant-only. Inside a `gui:` scope this module is never consulted at
all: `gui_scope_open()` guards the whole block, so "clicking flows" there is
untouched.

Two separate mechanisms, both opened only by the agent runner:

  * **The offer** (task-wide) makes `screen.click` visible to the planner.
    Opened only for a goal the chat routes marked as typed by the user
    (`goal_from_user`) that both asks to interact with something and names a
    label-like target (`user_asked_to_click`). Visibility is not authority: a
    call outside the grant below is still confirm-class.
  * **The grant** (one call) is bound to one exact label (role words
    stripped, e.g. "the Seven button" names "Seven"). The runner opens it
    only when ALL hold: the offer conditions; the label is the user's own
    word (`user_named_label`, word-bounded so "OK" cannot match inside "look"
    or "token"); the task is untainted; the per-task click cap has room; and
    the foreground window is the app this task opened or focused and
    verified. The registry spends it only on `screen.click` calls that carry
    that exact label.

ONLY the `label` argument path is ever granted. Raw `x`/`y` coordinates carry
no label, so `click_grant.consume` never matches them -- they fall to the
ordinary confirm gate and, once approved, `screen_tools.screen_click` itself
still refuses them outright ("I will not click raw coordinates"). Nothing the
model emits opens either mechanism, and the grant never overrides grounding's
own refusals: an ambiguous label (Phase 59) or a match below the confidence
floor still declines inside the handler, exactly as it does today -- the
grant only ever changes whether the CALL runs, never what grounding decides
once it does.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Iterator

CLICK_TOOL = "screen.click"
DEFAULT_MAX_CLICKS_PER_TASK = 6

# Words that name a control's ROLE rather than its label -- stripped before
# comparing a label against the user's sentence, the same idea as
# `grounding.py::_ROLE_SYNONYMS` (kept separately: this module only needs the
# words themselves, not grounding's role-affinity mapping, since it never
# resolves a target -- it only decides whether the user said this word).
_ROLE_WORDS = frozenset({
    "the", "a", "an",
    "button", "splitbutton", "field", "input", "textbox", "textfield",
    "checkbox", "check", "radio", "link", "dropdown", "combo", "combobox",
    "menu", "menuitem", "tab", "tabitem", "toggle", "switch", "icon",
    "option", "control", "element", "box",
})

# Offer visibility only: the goal both asks to interact with something and
# names something that looks like a control. Not authority -- see module
# docstring; the per-call grant is the only thing that lowers friction.
_CLICK_INTENT = re.compile(r"\b(?:click|press|tap|select|choose|check|toggle|hit)\b", re.IGNORECASE)
_TARGETISH = re.compile(r"[\"'“”‘’]|\b(?:button|link|tab|icon|menu|checkbox|option|field)\b", re.IGNORECASE)


def _normalize(text: object) -> str:
    return " ".join(str(text or "").split())


def _tokens(text: str) -> list[str]:
    return [tok for tok in text.replace("&", " ").replace("_", " ").split() if tok]


def _core_label(label: object) -> str:
    """Role words stripped, lowercased. 'the Seven button' -> 'seven'."""
    raw = _normalize(label).lower()
    kept = [tok for tok in _tokens(raw) if tok not in _ROLE_WORDS]
    return " ".join(kept) if kept else raw


def user_asked_to_click(goal: str) -> bool:
    text = _normalize(goal)
    return bool(_CLICK_INTENT.search(text) and _TARGETISH.search(text))


def user_named_label(label: str, goal: str) -> bool:
    """True when `label` (role words stripped) appears in the goal as a
    whole word or phrase, case-insensitively. Word-bounded so a short label
    like "OK" cannot match inside "look" or "token"."""
    core = _core_label(label)
    if not core:
        return False
    pattern = re.compile(r"(?<!\w)" + re.escape(core) + r"(?!\w)", re.IGNORECASE)
    return bool(pattern.search(_normalize(goal)))


@dataclass
class _Grant:
    label: str
    used: list[int] = field(default_factory=lambda: [0])


_offer: ContextVar[str | None] = ContextVar("eva_click_offer", default=None)
_grant: ContextVar[_Grant | None] = ContextVar("eva_click_grant", default=None)


def click_offered() -> bool:
    return _offer.get() is not None


def consume(tool: str, args: dict) -> bool:
    """Spend the open grant on this exact call. False otherwise.

    Only ever matches a `label` argument -- a raw x/y call carries no label,
    so `_core_label("")` is `""` and never equals a non-empty granted label.
    """
    grant = _grant.get()
    if grant is None or tool != CLICK_TOOL or grant.used[0] > 0:
        return False
    label = (args or {}).get("label")
    if not label or _core_label(label) != grant.label:
        return False
    grant.used[0] += 1
    return True


@contextmanager
def open_click_offer(goal: str) -> Iterator[None]:
    token: Token = _offer.set(_normalize(goal)[:800])
    try:
        yield
    finally:
        _offer.reset(token)


@contextmanager
def open_click_grant(label: str) -> Iterator[None]:
    token: Token = _grant.set(_Grant(label=_core_label(label)))
    try:
        yield
    finally:
        _grant.reset(token)
