"""The background scheduler — the part that finally runs unattended (Phase 53).

Phases 45 and 46 built a durable task queue and a proactive rule engine, and
then deliberately did not start either of them. That was the right call at the
time: a loop that executes work while nobody is watching is exactly the thing to
be slow about. But it left both phases inert — a rule saying "every morning at
8:30" only fired if you happened to reboot at 8:30, and queued work sat forever.

This is the loop. Two things happen per cycle:

  1. **tick** the proactive engine — which, by Phase 46's construction, can only
     PROPOSE: it enqueues requests and notifies. It executes nothing.
  2. **drain** the durable queue — which runs each task through the ordinary
     gate-governed agent runner.

The safety argument rests entirely on the gate, not on this module. A drained
task is not privileged by virtue of having been queued: ``ToolRegistry.run``
classifies each of its tool calls exactly as it would if you had typed the
request. So a task whose work is allow-class completes unattended, and a task
that wants to delete a file **parks in the confirmation ledger and waits for a
human**. Nothing here can approve anything. That is the property that makes an
unattended loop tolerable, and it is what the Phase 53 verifier actually tests.

Everything is bounded and refusable:

  * default OFF (``EVA_BACKGROUND_WORKER_ENABLED``), and no activation profile
    may enable it — like the microphone and the browser, it is opt-in one flag
    at a time;
  * a minimum interval floor, so a misconfigured value cannot spin;
  * a cap on tasks drained per cycle, so one cycle cannot run away;
  * cooperative stop, and every cycle is wrapped — one bad cycle logs and the
    loop survives rather than dying silently.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

_ABSENT = {"", "0", "false", "no", "off"}

# A scheduler that can spin is a bug, not a feature.
_MIN_INTERVAL_SECONDS = 5.0
_DEFAULT_INTERVAL_SECONDS = 60.0
# One cycle must not be able to run away with the machine.
_DEFAULT_MAX_TASKS_PER_CYCLE = 3
_MAX_TASKS_CEILING = 10


def background_worker_enabled(environ: dict[str, str] | None = None) -> bool:
    """Whether the unattended loop may run (default OFF, empty == off)."""
    env = environ if environ is not None else os.environ
    return env.get("EVA_BACKGROUND_WORKER_ENABLED", "").strip().lower() not in _ABSENT


def scheduler_interval(environ: dict[str, str] | None = None) -> float:
    env = environ if environ is not None else os.environ
    try:
        value = float(str(env.get("EVA_SCHEDULER_INTERVAL_SECONDS", "") or _DEFAULT_INTERVAL_SECONDS))
    except (TypeError, ValueError):
        return _DEFAULT_INTERVAL_SECONDS
    return max(_MIN_INTERVAL_SECONDS, value)


def max_tasks_per_cycle(environ: dict[str, str] | None = None) -> int:
    env = environ if environ is not None else os.environ
    try:
        value = int(str(env.get("EVA_SCHEDULER_MAX_TASKS", "") or _DEFAULT_MAX_TASKS_PER_CYCLE))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_TASKS_PER_CYCLE
    return max(0, min(value, _MAX_TASKS_CEILING))


@dataclass
class SchedulerStats:
    cycles: int = 0
    proposed: int = 0
    tasks_ran: int = 0
    errors: int = 0
    last_cycle_at: str = ""
    last_error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycles": self.cycles,
            "proposed": self.proposed,
            "tasks_ran": self.tasks_ran,
            "errors": self.errors,
            "last_cycle_at": self.last_cycle_at,
            "last_error": self.last_error,
        }


class BackgroundScheduler:
    """Ticks proactive rules and drains the durable queue, on an interval.

    ``engine`` is a Phase 46 ProactivityEngine (propose-only) and ``worker`` a
    Phase 45 DurableTaskWorker (which executes through the gate). Either may be
    None; the scheduler simply does that half of the work and no more.
    """

    def __init__(self, engine: Any | None = None, worker: Any | None = None) -> None:
        self.engine = engine
        self.worker = worker
        self.stats = SchedulerStats()
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        """Ask the loop to finish its current cycle and exit."""
        self._stop.set()

    async def run_cycle(self) -> dict[str, Any]:
        """One cycle: propose, then drain. Never raises.

        Deliberately ordered — ticking first means anything a rule proposes this
        cycle is available to drain in the same pass.
        """
        result: dict[str, Any] = {"proposed": 0, "ran": 0, "errors": []}
        now = datetime.now(timezone.utc).isoformat()

        if self.engine is not None:
            try:
                tick = self.engine.tick()
                proposed = len(tick.get("proposed") or [])
                result["proposed"] = proposed
                self.stats.proposed += proposed
            except Exception as exc:
                result["errors"].append(f"tick:{str(exc)[:120]}")

        if self.worker is not None:
            try:
                drained = await self.worker.drain(max_tasks=max_tasks_per_cycle())
                ran = int(drained.get("ran") or 0)
                result["ran"] = ran
                self.stats.tasks_ran += ran
            except Exception as exc:
                result["errors"].append(f"drain:{str(exc)[:120]}")

        self.stats.cycles += 1
        self.stats.last_cycle_at = now
        if result["errors"]:
            self.stats.errors += len(result["errors"])
            self.stats.last_error = result["errors"][-1]
        return result

    async def run_forever(self, *, max_cycles: int | None = None, sleep: Callable | None = None) -> SchedulerStats:
        """Run cycles until asked to stop (or ``max_cycles``, for tests).

        ``sleep`` is an injection seam so a test can drive many cycles without
        waiting real seconds. One bad cycle never kills the loop.
        """
        naptime = sleep or asyncio.sleep
        interval = scheduler_interval()
        cycles = 0
        while not self._stop.is_set():
            if max_cycles is not None and cycles >= max_cycles:
                break
            try:
                await self.run_cycle()
            except Exception as exc:  # belt and braces: run_cycle already guards
                self.stats.errors += 1
                self.stats.last_error = str(exc)[:160]
            cycles += 1
            if self._stop.is_set() or (max_cycles is not None and cycles >= max_cycles):
                break
            try:
                await naptime(interval)
            except asyncio.CancelledError:
                break
        return self.stats


def scheduler_status(environ: dict[str, str] | None = None) -> dict[str, Any]:
    """Report the loop's configuration without starting anything."""
    return {
        "enabled": background_worker_enabled(environ),
        "interval_seconds": scheduler_interval(environ),
        "min_interval_seconds": _MIN_INTERVAL_SECONDS,
        "max_tasks_per_cycle": max_tasks_per_cycle(environ),
        "note": (
            "The scheduler proposes and drains; it approves nothing. Every drained task runs through the "
            "permission gate, so anything privileged parks in the confirmation ledger and waits for you."
        ),
    }


__all__ = [
    "BackgroundScheduler",
    "SchedulerStats",
    "background_worker_enabled",
    "scheduler_interval",
    "max_tasks_per_cycle",
    "scheduler_status",
]
