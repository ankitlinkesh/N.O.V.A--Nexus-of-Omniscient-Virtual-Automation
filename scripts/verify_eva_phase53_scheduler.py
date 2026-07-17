"""Standalone verifier for Phase 53 (the background scheduler).

Phases 45 and 46 built a durable queue and a proactive rule engine and then
deliberately never started either. That left both inert: a rule saying "every
morning at 8:30" only fired if you happened to reboot at 8:30, and queued work
sat forever. This is the loop that runs them — the first thing in the project
that acts with nobody watching.

So the verification is mostly about what it CANNOT do:

  1. THE SAFETY CLAIM: a task gets NO authority from having been queued. A
     queued privileged action (file.copy, override-class) runs through the
     ordinary gate and PARKS — the file is not copied. Unattended execution is
     safe precisely because the scheduler delegates to the gate rather than
     deciding anything itself.
  2. The scheduler exposes no approve/confirm/override of its own.
  3. Default OFF, and no activation profile may enable it — opt-in one flag at a
     time, like the microphone and the browser.
  4. BOUNDED: the interval has a hard floor (a scheduler that can spin is a
     bug) and tasks-per-cycle is capped.
  5. ROBUST: a broken tick or a broken drain is recorded and the loop survives;
     one bad cycle must not silently kill the only thing running.
  6. A cycle ticks rules THEN drains, so work proposed this cycle is picked up
     in the same pass; run_forever is stoppable and honours max_cycles.
  7. Startup wiring exists and passes the gate-governed runner as the executor.

Fully offline: temp DBs, injected executor, no network, no LLM, no real sleep.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


async def _yield_sleep(_seconds):
    await asyncio.sleep(0)


def main() -> int:
    from backend.eva.proactivity.engine import ProactivityEngine
    from backend.eva.proactivity.store import ProactivityStore
    from backend.eva.runtime.activation import PROFILES, profile_flags
    from backend.eva.runtime.scheduler import (
        BackgroundScheduler,
        background_worker_enabled,
        max_tasks_per_cycle,
        scheduler_interval,
        scheduler_status,
    )
    from backend.eva.security import tool_gate
    from backend.eva.tasks.durable_queue import DurableTaskQueue
    from backend.eva.tasks.worker import DurableTaskWorker
    from backend.eva.tools.registry import ToolRegistry
    from scripts import verify_eva_all

    ENV = ("EVA_BACKGROUND_WORKER_ENABLED", "EVA_SCHEDULER_INTERVAL_SECONDS", "EVA_SCHEDULER_MAX_TASKS")
    saved = {k: os.environ.get(k) for k in ENV}
    scratch = Path(tempfile.mkdtemp(prefix="eva_phase53_"))
    tool_gate.reset_pending_calls()

    try:
        # 1. THE SAFETY CLAIM: queued != authorized.
        source = scratch / "secret.txt"
        source.write_text("sensitive", encoding="utf-8")
        destination = scratch / "copied.txt"
        registry = ToolRegistry()
        attempted: list[str] = []

        async def gate_governed_executor(request: str) -> dict:
            result = registry.run("file.copy", source=str(source), destination=str(destination))
            attempted.append(request)
            return {"ok": not (isinstance(result, dict) and result.get("requires_confirmation"))}

        queue = DurableTaskQueue(scratch / "q.sqlite3")
        store = ProactivityStore(scratch / "p.sqlite3")
        engine = ProactivityEngine(store, queue)
        queue.enqueue("copy my secret file somewhere")

        scheduler = BackgroundScheduler(engine, DurableTaskWorker(queue, gate_governed_executor))
        asyncio.run(scheduler.run_cycle())
        check(attempted, "the queued task should have been attempted by the drain")
        check(
            destination.exists() is False,
            "THE GATE MUST STILL HOLD: a queued privileged action must NOT execute unattended",
        )

        # 2. The scheduler has no approval powers of its own.
        for attr in ("approve", "confirm", "override", "authorize"):
            check(not hasattr(scheduler, attr), f"a scheduler must not expose {attr}()")
        check("approves nothing" in scheduler_status()["note"], "status must state the scheduler approves nothing")

        # 3. Default OFF + no profile may enable it.
        os.environ.pop("EVA_BACKGROUND_WORKER_ENABLED", None)
        check(background_worker_enabled() is False, "the unattended loop must be OFF by default")
        os.environ["EVA_BACKGROUND_WORKER_ENABLED"] = "1"
        check(background_worker_enabled() is True, "the flag must enable it")
        for name in PROFILES:
            check(
                "EVA_BACKGROUND_WORKER_ENABLED" not in profile_flags(name),
                f"profile {name!r} must never auto-start the unattended loop",
            )

        # 4. BOUNDED.
        os.environ["EVA_SCHEDULER_INTERVAL_SECONDS"] = "0"
        check(scheduler_interval() >= 5.0, "the interval must have a floor; a scheduler that can spin is a bug")
        os.environ["EVA_SCHEDULER_INTERVAL_SECONDS"] = "nonsense"
        check(scheduler_interval() == 60.0, "a malformed interval must fall back to the default")
        os.environ["EVA_SCHEDULER_MAX_TASKS"] = "10000"
        check(max_tasks_per_cycle() <= 10, "tasks per cycle must be capped")
        os.environ.pop("EVA_SCHEDULER_MAX_TASKS", None)

        # 5. ROBUST: one bad cycle must not kill the loop.
        class _BrokenEngine:
            def tick(self):
                raise RuntimeError("kaboom")

        broken = BackgroundScheduler(_BrokenEngine(), None)
        result = asyncio.run(broken.run_cycle())
        check(any("tick:" in e for e in result["errors"]), "a broken tick must be recorded")
        check(broken.stats.cycles == 1, "the cycle must still complete after a broken tick")

        class _BrokenWorker:
            async def drain(self, *, max_tasks=3):
                raise RuntimeError("kaboom")

        broken_drain = BackgroundScheduler(None, _BrokenWorker())
        result = asyncio.run(broken_drain.run_cycle())
        check(any("drain:" in e for e in result["errors"]), "a broken drain must be recorded, not raised")

        # 6. Propose-then-drain in one pass; stoppable; bounded cycles.
        store2 = ProactivityStore(scratch / "p2.sqlite3")
        queue2 = DurableTaskQueue(scratch / "q2.sqlite3")
        engine2 = ProactivityEngine(store2, queue2)
        store2.add_rule("news", "interval", {"seconds": 1}, "summarize my news", cooldown_seconds=0)
        seen: list[str] = []

        async def ok_executor(request: str) -> dict:
            seen.append(request)
            return {"ok": True}

        s2 = BackgroundScheduler(engine2, DurableTaskWorker(queue2, ok_executor))
        cycle = asyncio.run(s2.run_cycle())
        check(cycle["proposed"] == 1, f"the due rule must propose, got {cycle!r}")
        check(cycle["ran"] == 1 and seen == ["summarize my news"], "work proposed this cycle must drain in the same pass")

        bounded = asyncio.run(BackgroundScheduler(None, None).run_forever(max_cycles=3, sleep=_yield_sleep))
        check(bounded.cycles == 3, f"run_forever must honour max_cycles, got {bounded.cycles}")

        stoppable = BackgroundScheduler(None, None)

        async def drive():
            task = asyncio.create_task(stoppable.run_forever(sleep=_yield_sleep))
            await asyncio.sleep(0)
            stoppable.request_stop()
            return await asyncio.wait_for(task, timeout=5)

        stats = asyncio.run(drive())
        check(stats.cycles >= 1, "a stoppable loop must run at least one cycle and then exit")

        # 7. Startup wiring passes the GATE-GOVERNED runner as the executor.
        main_source = (ROOT / "backend" / "eva" / "main.py").read_text(encoding="utf-8")
        check("_start_background_scheduler_if_enabled" in main_source, "main.py must wire the scheduler")
        check("_gate_governed_executor" in main_source, "the scheduler's executor must be the gate-governed runner")
        check("run_agentic_task" in main_source, "the executor must go through the ordinary agent loop")

        verifier_name = "verify_eva_phase53_scheduler.py"
        check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 53 verifier")
        check(verifier_name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 53 verifier")
        check(verifier_name in getattr(verify_eva_all, "VERIFIER_DESCRIPTORS"), "master descriptor missing the Phase 53 verifier")

    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        tool_gate.reset_pending_calls()

    print(
        "PASS: Phase 53 background scheduler -- Phases 45/46 finally RUN, and unattended execution stays safe "
        "because the scheduler decides nothing: a task gets no authority from having been queued, so a queued "
        "override-class file.copy PARKED at the gate and the file was never copied. The scheduler exposes no "
        "approve/confirm/override of its own, is off by default, and no activation profile may start it. Every loop "
        "is bounded (a hard interval floor so it cannot spin, a cap on tasks per cycle) and robust (a broken tick or "
        "drain is recorded and the loop survives). A cycle proposes then drains in one pass, run_forever is "
        "stoppable and honours max_cycles, and startup wires the GATE-GOVERNED agent runner as the executor."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
