"""Phase 117: pause-and-resume for tool-gate pending actions.

The agent loop stops and RETURNS when a planned tool call hits the permission
gate (``registry.run`` comes back with ``requires_confirmation`` and a
``pending_id`` like ``act_1a2b3c4d5e6f``). Before this phase, that return was
the end of the errand: ``confirm <id>`` ran the one approved call via
``ToolRegistry.run_approved`` and nothing else -- everything the task had
already gathered, and everything it still needed to do, was gone.

This module is the small piece that survives the gap between "the runner
returned" and "the user typed confirm": a single-use, TTL'd, in-process
snapshot keyed by the EXACT pending_id the gate created, so
``permissions/confirmation.py`` can hand it straight back to
``agent.runner.resume_agentic_task`` once -- and only once -- that id is
actually confirmed and executed.

Deliberately NOT persisted to disk and NOT shared across processes: this is a
bounded in-memory cache. Restarting the process, like letting the TTL expire,
simply loses the pause and falls back to today's behavior (confirm runs the
one action, nothing resumes). That is the safe failure mode, not a bug to
work around -- a resume that silently fails to happen is just today's
behavior; a resume that fires for the WRONG task would not be.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

# 15 minutes: long enough for a person to notice a pending action, read the
# explanation, and type `confirm ...`, short enough that a snapshot from a
# session nobody is coming back to does not sit around indefinitely.
TTL_SECONDS = 15 * 60

_lock = threading.Lock()
_snapshots: dict[str, "PausedTask"] = {}


@dataclass
class PausedTask:
    """Everything the runner needs to pick the loop back up after one gated
    step is approved.

    ``env`` is the runner's own ``_RunEnv`` bundle (task, state, budgets,
    taint, registry/executor/memory, the original ``context`` dict, etc.) --
    typed ``Any`` here deliberately so this module never imports from
    ``agent.runner`` (which imports THIS module to save/take snapshots; a
    two-way import would be circular). This module never looks inside
    ``env``, so duck-typing it costs nothing.
    """

    pending_id: str
    session_id: Any
    env: Any
    index: int
    call: Any
    step: Any
    continue_after_tools: bool
    created_at: float
    # Phase 117 review fix: the FULL delegated-role stack (`role_context.active_roles()`,
    # outermost first) that was in force when this task paused, so a resumed
    # delegated sub-task's remaining steps stay contained to it -- see
    # `runner.resume_agentic_task`, which reopens exactly this stack. `()` for
    # a task that was never delegated (the ordinary, unrestricted case).
    role_stack: tuple[str, ...] = ()


def save_paused_task(snapshot: PausedTask) -> None:
    """Register a pause. Overwrites any snapshot already at this id, though
    that should never happen -- pending ids are unique per gated call."""
    with _lock:
        _prune_locked()
        _snapshots[snapshot.pending_id] = snapshot


def take_paused_task(pending_id: str, session_id: Any = None) -> "PausedTask | None":
    """Single-use retrieval: pops the snapshot on a hit, so a second confirm
    of the same id -- already impossible through the ledger (Phase 88 locks
    an action to ``confirmed`` exactly once) -- can never resume the same
    task twice even if something upstream changes. Returns ``None``, and
    resumes nothing, when there is no snapshot, it expired, or it belongs to
    a different session; the caller then reports the confirmation the way it
    always has.

    ``session_id`` must match EXACTLY, including the ``None`` case: a
    snapshot paused with a real session id resumes only for a confirm
    carrying that same session id (a confirm with no session, or a different
    one, does not match); a snapshot paused with no session (an
    offline/script caller with nothing to compare) resumes only for a
    confirm that also carries no session. This was previously "both sides
    carry one, and they match, or either side is None" -- which let a
    confirm with no session id resume a snapshot paused inside a real
    session, since that codepath is reachable from more than one caller and
    not every caller reliably threads a session id through. Strict equality
    is the only version of this check that cannot be walked around by
    omitting the argument.
    """
    with _lock:
        _prune_locked()
        snapshot = _snapshots.get(pending_id)
        if snapshot is None:
            return None
        if snapshot.session_id != session_id:
            return None
        del _snapshots[pending_id]
        return snapshot


def _prune_locked() -> None:
    now = time.monotonic()
    expired = [key for key, snap in _snapshots.items() if now - snap.created_at > TTL_SECONDS]
    for key in expired:
        del _snapshots[key]


def peek_count() -> int:
    """Test/diagnostic helper: how many pauses are currently live."""
    with _lock:
        _prune_locked()
        return len(_snapshots)


def clear_all() -> None:
    """Test-only: drop every snapshot so tests don't leak state into each
    other through this module-level store."""
    with _lock:
        _snapshots.clear()
