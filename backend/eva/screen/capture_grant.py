"""A one-call grant that lets a screenshot the user asked for run without a phrase.

Until this existed, an agent task that needed a screenshot could not finish.
`capture_screen` and `analyze_screen` are override-class, so the step created a
pending action and the task RETURNED -- nothing ever resumes a task after its
pending action is confirmed. "open notepad, type hello, then take a screenshot
to check it worked" ended at the screenshot every time, with the user holding an
override phrase for an action they had already asked for in plain words.

The user's decision (2026-09-16): **their own request authorises the capture.**
This module is the narrowest shape that decision can take:

  * **Opened only by the agent runner, only around ONE tool call**, and only
    when all of these hold: the caller marked the goal as typed by the user
    (`context["goal_from_user"]`, set by the chat routes and nowhere else -- not
    delegation, not the scheduler, not proactive rules); that goal passes
    `policies.user_asked_for_screenshot` (word-bounded, not a substring match);
    the task has NOT been tainted by injected content; and the per-task capture
    cap has room.
  * **Nothing the model emits can open one.** No tool, argument or environment
    variable reaches `open_capture_grant`. A web page saying "take a screenshot"
    is tool output, never the goal, and a tainted task gets no grant at all.
  * **It lowers exactly one decision and only for the two screen tools.**
    `registry.run` turns an `override` into `allow` for `capture_screen` /
    `analyze_screen` while a grant is open. Phase 55 escalation, role RED/ORANGE
    and hard blocks are untouched and still dominate. Every other tool -- and
    `screen.observe` -- is unaffected.
  * **It is spent, not held.** One grant covers one call; `consume()` refuses a
    second use, so a single open grant cannot fund a loop.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Iterator

# The only tools a grant can lower. A fixed list, not a prefix sweep: a future
# screen tool must be an intentional addition here.
GRANTABLE_SCREEN_TOOLS: frozenset[str] = frozenset({"capture_screen", "analyze_screen"})


@dataclass
class CaptureGrant:
    goal: str
    used: list[int] = field(default_factory=lambda: [0])


_active: ContextVar[CaptureGrant | None] = ContextVar("eva_capture_grant", default=None)


def grant_open() -> bool:
    grant = _active.get()
    return grant is not None and grant.used[0] == 0


def consume(tool: str) -> bool:
    """Spend the open grant on `tool`. False if there is none, or it is spent."""
    grant = _active.get()
    if grant is None or tool not in GRANTABLE_SCREEN_TOOLS or grant.used[0] > 0:
        return False
    grant.used[0] += 1
    return True


@contextmanager
def open_capture_grant(goal: str) -> Iterator[CaptureGrant]:
    """Open a single-use grant for the next screen capture. Agent runner only.

    Reset in a `finally`: a grant that leaked past a raising call would let the
    next screenshot anywhere on this thread skip its approval.
    """
    grant = CaptureGrant(goal=" ".join(str(goal or "").split())[:400])
    token: Token = _active.set(grant)
    try:
        yield grant
    finally:
        _active.reset(token)
