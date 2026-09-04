"""A bounded window in which the planner may drive the real mouse and keyboard.

Everything needed to control the GUI has existed since Phases 56-60: the
accessibility-tree grounding that finds a control by name, the DPI-correct
click, the typing, the confidence floor that refuses rather than guessing. It
was all reachable from the typed console and from `/api/tools`, and from
nowhere else -- `screen.*` is deliberately absent from `planner_specs()`, and
`backend/tests/test_planner_reachability.py` pins that as
"must never be planner-reachable ... regardless of any flag".

That invariant exists for a real reason. Tool output, window titles and web
pages are untrusted content; if the planner could choose to click, then a
crafted page title could steer a physical mouse. `authorization.py` states the
principle: untrusted content proposes, it never authorizes.

This module does not remove that invariant. It narrows it, and writes down the
narrower version:

    screen.* is never planner-reachable UNLESS a human opened a GUI scope from
    the typed console, and then only for the duration of that one task.

Why this is the safe shape:

  * **The console is the trust boundary this project already uses.** Rule
    creation (54), form filling (58), delegation (73) and the bounded command
    runner (74) are all console-only for exactly this reason: untrusted content
    cannot reach a command the human types. Opening a GUI scope is one more
    entry in that list, not a new kind of trust.
  * **Nothing the model emits can open one.** There is no tool, no argument and
    no env var that opens a scope -- only `open_gui_scope()`, called from the
    console handler. A page that says "enable GUI mode" is just text.
  * **It is bounded and it closes.** One task, a step budget, and a `finally`
    that resets even when the task raises -- the same discipline as
    `role_scope`, and for the same reason: a leaked scope is a silently widened
    boundary.
  * **It only affects VISIBILITY, never the gate.** Inside a scope the planner
    can *choose* `screen.click`; every existing check still runs -- the
    permission gate, the 0.75 grounding confidence floor, the ambiguity refusal,
    the `EVA_ENABLE_REAL_INPUT` flag, and the Phase 55 argument-aware
    escalation. Typing and hotkeys remain confirm-class and still stop to ask.
    This is strictly a narrower change than "make the tools visible".
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Iterator


# The tools a GUI scope makes visible to the planner. Deliberately a fixed,
# explicit list rather than a `startswith("screen.")` sweep: a future
# `screen.something_dangerous` must be an intentional addition here, not
# something a scope silently starts granting. `screen.submit_form` is NOT in it
# -- that one carries vault-backed values and keeps its own one-approval flow.
GUI_SCOPE_TOOLS: tuple[str, ...] = (
    # screen.observe is deliberately NOT here. It captures a screenshot and is
    # override-class, and the scope already hands the agent the control list from
    # a local, pixel-free accessibility read -- so granting it would add a
    # privacy cost and an approval stall to reach information the agent already
    # has. Told it had the labels, the model asked to observe anyway; removing
    # the option is structural where the instruction was advisory. The cost is
    # real and named: within one scope the agent cannot re-read a UI that changes
    # under it, so a task whose controls appear only after a click will fail
    # honestly rather than adapt.
    "screen.click",
    "screen.type_text",
    "screen.press",
    "screen.hotkey",
    "screen.scroll",
    "screen.wait",
)

# Tools a GUI scope REMOVES from the planner's view for its duration. Both send
# a screenshot of the whole screen to Google Gemini Vision and both are
# override-class, so inside a GUI task they are simultaneously the wrong tool,
# the most privacy-costly one, and a guaranteed stall on an override prompt.
# Told in the system prompt not to call analyze_screen during a GUI task, the
# model did it anyway on three consecutive live runs: it is the obvious-looking
# tool for "look at the screen". Removing it is structural where the rule was
# advisory -- the project's own repeated lesson. Nothing is lost: the scope hands
# the agent the control list from a local, pixel-free accessibility read.
GUI_SCOPE_HIDDEN: frozenset[str] = frozenset({"analyze_screen", "capture_screen"})

# A scope is for one errand. The cap is not a safety boundary on its own -- the
# gate is -- but an agent looping on a GUI it cannot read should run out of
# scope rather than keep clicking.
DEFAULT_MAX_ACTIONS = 12


@dataclass(frozen=True)
class GuiScope:
    """The open window: what it was opened for, and what it has spent."""

    goal: str
    max_actions: int = DEFAULT_MAX_ACTIONS

    def as_dict(self) -> dict[str, object]:
        return {"goal": self.goal, "max_actions": self.max_actions}


_active_scope: ContextVar[GuiScope | None] = ContextVar("eva_active_gui_scope", default=None)

# A MUTABLE counter, deliberately, not a ContextVar[int]. The first version
# stored the count as an int in a ContextVar and reported "0/12 actions used"
# after a run that had plainly clicked twice: `run_agentic_task` executes in
# another context, which gets a COPY of the context vars, so every `set()` inside
# the task updated the copy and the console read the untouched original. Holding
# one mutable object means both contexts share the same counter by reference.
# (The enforcement inside the task was correct even then -- it was the report to
# the user that was wrong, which is this project's oldest bug shape.)
_counter: ContextVar[list[int]] = ContextVar("eva_gui_actions_used", default=[0])


def active_scope() -> GuiScope | None:
    """The GUI scope in force, or None when the planner may not touch the GUI."""
    return _active_scope.get()


def gui_scope_open() -> bool:
    return _active_scope.get() is not None


def actions_used() -> int:
    return _counter.get()[0]


def budget_remaining() -> int:
    scope = _active_scope.get()
    if scope is None:
        return 0
    return max(0, scope.max_actions - _counter.get()[0])


def record_action() -> int:
    """Count one GUI action against the open scope; returns the new total.

    Called by the registry when a scope-granted tool actually runs, so the
    budget measures what happened rather than what was planned.
    """
    holder = _counter.get()
    holder[0] += 1
    return holder[0]


@contextmanager
def open_gui_scope(goal: str, *, max_actions: int = DEFAULT_MAX_ACTIONS) -> Iterator[GuiScope]:
    """Open a GUI scope for one task. Callable ONLY from the typed console.

    There is deliberately no tool, argument or environment variable that reaches
    this function: that absence is the whole security property, and the Phase 96
    verifier asserts it by scanning for callers.

    The reset is in a `finally` for the same reason `role_scope`'s is -- a scope
    that leaked past a raising task would leave the planner holding mouse and
    keyboard access with nobody watching, which is the exact state this is meant
    to prevent.
    """
    scope = GuiScope(goal=" ".join(str(goal or "").split())[:400], max_actions=max(1, int(max_actions)))
    token: Token = _active_scope.set(scope)
    used_token: Token = _counter.set([0])
    try:
        yield scope
    finally:
        _active_scope.reset(token)
        _counter.reset(used_token)
