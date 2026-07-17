"""The background scheduler (Phase 53).

This is the first loop that runs with nobody watching, so the tests are mostly
about what it CANNOT do. The headline: a queued task gets no authority from
having been queued — it runs through the ordinary gate, so privileged work parks
in the confirmation ledger instead of executing unattended.
"""

from __future__ import annotations

import asyncio

import pytest

from eva.proactivity.engine import ProactivityEngine
from eva.proactivity.store import ProactivityStore
from eva.runtime import scheduler as sched
from eva.runtime.scheduler import BackgroundScheduler, background_worker_enabled, scheduler_interval
from eva.security import tool_gate
from eva.tasks.durable_queue import DurableTaskQueue
from eva.tasks.worker import DurableTaskWorker
from eva.tools.registry import ToolRegistry


@pytest.fixture()
def parts(tmp_path):
    tool_gate.reset_pending_calls()
    store = ProactivityStore(tmp_path / "p.sqlite3")
    queue = DurableTaskQueue(tmp_path / "q.sqlite3")
    yield store, queue, ProactivityEngine(store, queue)
    tool_gate.reset_pending_calls()


async def _noop_sleep(_seconds):
    # Must actually yield to the event loop, not just return: a coroutine with no
    # suspension point lets run_forever spin without ever giving another task
    # (like the one calling request_stop) a chance to run.
    await asyncio.sleep(0)


# -- the switch ------------------------------------------------------------

def test_off_by_default(monkeypatch):
    monkeypatch.delenv("EVA_BACKGROUND_WORKER_ENABLED", raising=False)
    assert background_worker_enabled() is False
    monkeypatch.setenv("EVA_BACKGROUND_WORKER_ENABLED", "1")
    assert background_worker_enabled() is True


def test_no_profile_can_enable_the_unattended_loop():
    from eva.runtime.activation import PROFILES, profile_flags

    for name in PROFILES:
        assert "EVA_BACKGROUND_WORKER_ENABLED" not in profile_flags(name)


# -- THE safety claim ------------------------------------------------------

def test_a_queued_privileged_task_parks_instead_of_running(parts, tmp_path):
    """A task gets NO authority from being queued. The gate governs it exactly
    as if the request had been typed."""
    store, queue, engine = parts
    source = tmp_path / "secret.txt"
    source.write_text("sensitive")
    destination = tmp_path / "copied.txt"

    registry = ToolRegistry()
    ran: list[str] = []

    async def gate_governed_executor(request: str) -> dict:
        # Stand-in for the real runner: it does what the runner does — call the
        # gate. The gate is what decides, not the scheduler.
        result = registry.run("file.copy", source=str(source), destination=str(destination))
        ran.append(request)
        return {"ok": not (isinstance(result, dict) and result.get("requires_confirmation"))}

    queue.enqueue("copy my secret file somewhere")
    scheduler = BackgroundScheduler(engine, DurableTaskWorker(queue, gate_governed_executor))
    asyncio.run(scheduler.run_cycle())

    assert ran, "the task should have been attempted"
    assert destination.exists() is False, "THE GATE MUST STILL HOLD: a queued privileged action must not execute unattended"


def test_the_scheduler_approves_nothing(parts):
    """The scheduler has no approval powers of its own — it only delegates."""
    store, queue, engine = parts
    scheduler = BackgroundScheduler(engine, DurableTaskWorker(queue, None))
    for attr in ("approve", "confirm", "override", "authorize"):
        assert not hasattr(scheduler, attr), f"a scheduler must not expose {attr}()"


# -- proposing + draining --------------------------------------------------

def test_cycle_ticks_rules_then_drains(parts):
    store, queue, engine = parts
    store.add_rule("news", "interval", {"seconds": 1}, "summarize my news", cooldown_seconds=0)
    seen: list[str] = []

    async def executor(request: str) -> dict:
        seen.append(request)
        return {"ok": True}

    scheduler = BackgroundScheduler(engine, DurableTaskWorker(queue, executor))
    result = asyncio.run(scheduler.run_cycle())
    # The rule proposed this cycle, and the drain picked it up in the same pass.
    assert result["proposed"] == 1
    assert result["ran"] == 1
    assert seen == ["summarize my news"]


def test_scheduler_works_with_only_an_engine(parts):
    store, queue, engine = parts
    store.add_rule("r", "interval", {"seconds": 1}, "x", cooldown_seconds=0)
    result = asyncio.run(BackgroundScheduler(engine, None).run_cycle())
    assert result["proposed"] == 1
    assert result["ran"] == 0


def test_scheduler_works_with_neither():
    result = asyncio.run(BackgroundScheduler(None, None).run_cycle())
    assert result == {"proposed": 0, "ran": 0, "errors": []}


# -- bounds + robustness ---------------------------------------------------

def test_interval_has_a_floor(monkeypatch):
    """A scheduler that can spin is a bug."""
    monkeypatch.setenv("EVA_SCHEDULER_INTERVAL_SECONDS", "0")
    assert scheduler_interval() >= 5.0
    monkeypatch.setenv("EVA_SCHEDULER_INTERVAL_SECONDS", "-100")
    assert scheduler_interval() >= 5.0
    monkeypatch.setenv("EVA_SCHEDULER_INTERVAL_SECONDS", "nonsense")
    assert scheduler_interval() == 60.0


def test_tasks_per_cycle_is_capped(monkeypatch):
    monkeypatch.setenv("EVA_SCHEDULER_MAX_TASKS", "10000")
    assert sched.max_tasks_per_cycle() <= 10


def test_a_broken_tick_does_not_kill_the_loop(parts):
    store, queue, engine = parts

    class _BrokenEngine:
        def tick(self):
            raise RuntimeError("kaboom")

    scheduler = BackgroundScheduler(_BrokenEngine(), None)
    result = asyncio.run(scheduler.run_cycle())
    assert any("tick:" in e for e in result["errors"])
    assert scheduler.stats.cycles == 1, "the cycle must still complete and be counted"


def test_a_broken_drain_does_not_kill_the_loop(parts):
    store, queue, engine = parts

    class _BrokenWorker:
        async def drain(self, *, max_tasks=3):
            raise RuntimeError("kaboom")

    scheduler = BackgroundScheduler(None, _BrokenWorker())
    result = asyncio.run(scheduler.run_cycle())
    assert any("drain:" in e for e in result["errors"])


def test_run_forever_is_stoppable(parts):
    store, queue, engine = parts
    scheduler = BackgroundScheduler(None, None)

    async def drive():
        task = asyncio.create_task(scheduler.run_forever(sleep=_noop_sleep))
        await asyncio.sleep(0)
        scheduler.request_stop()
        return await asyncio.wait_for(task, timeout=5)

    stats = asyncio.run(drive())
    assert stats.cycles >= 1


def test_run_forever_respects_max_cycles(parts):
    scheduler = BackgroundScheduler(None, None)
    stats = asyncio.run(scheduler.run_forever(max_cycles=3, sleep=_noop_sleep))
    assert stats.cycles == 3


def test_stats_accumulate(parts):
    store, queue, engine = parts
    store.add_rule("r", "interval", {"seconds": 1}, "x", cooldown_seconds=0, max_fires_per_day=96)

    async def executor(request: str) -> dict:
        return {"ok": True}

    scheduler = BackgroundScheduler(engine, DurableTaskWorker(queue, executor))
    asyncio.run(scheduler.run_forever(max_cycles=2, sleep=_noop_sleep))
    assert scheduler.stats.cycles == 2
    assert scheduler.stats.last_cycle_at
