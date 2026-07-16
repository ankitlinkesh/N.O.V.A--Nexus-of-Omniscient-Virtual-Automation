"""Standalone verifier for Phase 46 (proactivity: scheduled + triggered agents).

Proves, end to end and independent of pytest, that Eva can act without being
asked *without* breaking the safety model she was built on:

  1. THE INVARIANT — a trigger PROPOSES, never AUTHORIZES: a fired rule only
     enqueues its request; the task is left 'queued' (never started, finished,
     approved, or run), so it still faces the permission gate. Even a rule whose
     request is "delete all my files" can do nothing on its own.
  2. Triggers are correct and clock-injected: interval waits its interval; daily
     fires at/after its time and only once per day (then again the next day); a
     file watcher baselines on first sight and fires only on a real change.
  3. Runaway protection: a per-rule cooldown floor, a per-rule daily budget
     (which resets the next day), a store-clamped budget ceiling, and a global
     per-tick proposal cap.
  4. Robustness: a malformed rule never fires and never blocks the others; an
     unknown kind never fires; a disabled rule is not evaluated.
  5. Durability: standing rules survive a restart (a fresh store over the same
     DB file still has them).
  6. Default OFF + startup wiring: proactivity_enabled() is False by default;
     open_default_engine() is None when off; main.py wires the catch-up tick.
  7. The new eval is registered and the whole offline suite stays green; this
     verifier is wired into scripts/verify_eva_all.py's profiles.

Fully offline and deterministic: temp DBs, an injected clock, no network, no
live LLM, and no execution of any kind. Env vars are restored in a ``finally``.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> int:
    from backend.eva.evals import run_offline_evals
    from backend.eva.evals.offline_suite import offline_tasks
    from backend.eva.proactivity import open_default_engine, proactivity_enabled
    from backend.eva.proactivity.engine import MAX_PROPOSALS_PER_TICK, ProactivityEngine
    from backend.eva.proactivity.models import MAX_FIRES_PER_DAY_CEILING
    from backend.eva.proactivity.store import ProactivityStore
    from backend.eva.tasks.durable_queue import DurableTaskQueue
    from scripts import verify_eva_all

    saved_env = {"EVA_PROACTIVITY_ENABLED": os.environ.get("EVA_PROACTIVITY_ENABLED")}
    scratch = Path(tempfile.mkdtemp(prefix="eva_phase46_proactivity_"))
    T0 = datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc)

    try:
        # 1. THE INVARIANT: propose, never authorize.
        store = ProactivityStore(scratch / "inv.sqlite3")
        queue = DurableTaskQueue(scratch / "inv_q.sqlite3")
        engine = ProactivityEngine(store, queue)
        store.add_rule("unattended", "interval", {"seconds": 1}, "delete all my files", cooldown_seconds=0, max_fires_per_day=2)
        result = engine.tick(T0)
        check(len(result["proposed"]) == 1, f"a due rule must propose once, got {result['proposed']!r}")
        tasks = queue.list_tasks()
        check(len(tasks) == 1 and tasks[0].request == "delete all my files", "a fired rule must enqueue its request verbatim")
        task = tasks[0]
        check(task.status == "queued", f"a proposed task must be left queued for the gate, got {task.status!r}")
        check(not task.started_at and not task.finished_at and not task.result_summary, "a trigger must never start/finish/approve a task")
        check(queue.stats()["running"] == 0 and queue.stats()["succeeded"] == 0, "a tick must leave nothing running or succeeded")
        check(task.source.startswith("proactive:"), f"a proposed task must record its proactive source, got {task.source!r}")
        check(len(store.list_notifications()) == 1, "a fired rule must record a notification")

        # 3a. Daily budget caps it, and resets the next day.
        fired = 1
        for i in range(1, 5):
            fired += len(engine.tick(T0 + timedelta(seconds=10 * i))["proposed"])
        check(fired == 2, f"the daily budget must cap proposals at 2, got {fired}")
        capped = engine.tick(T0 + timedelta(seconds=90))
        check([s["reason"] for s in capped["suppressed"]] == ["daily_budget"], f"over-budget must be suppressed as daily_budget, got {capped['suppressed']!r}")
        check(len(engine.tick(T0 + timedelta(days=1))["proposed"]) == 1, "the daily budget must reset the next day")

        # 2. Interval + daily triggers.
        iq = DurableTaskQueue(scratch / "i_q.sqlite3")
        istore = ProactivityStore(scratch / "i.sqlite3")
        iengine = ProactivityEngine(istore, iq)
        istore.add_rule("hourly", "interval", {"seconds": 3600}, "sweep", cooldown_seconds=0)
        check(len(iengine.tick(T0)["proposed"]) == 1, "an interval rule that never fired is due immediately")
        check(len(iengine.tick(T0 + timedelta(seconds=60))["proposed"]) == 0, "an interval rule must wait its interval")
        check(len(iengine.tick(T0 + timedelta(seconds=3601))["proposed"]) == 1, "an interval rule must fire once the interval elapses")

        dstore = ProactivityStore(scratch / "d.sqlite3")
        dengine = ProactivityEngine(dstore, DurableTaskQueue(scratch / "d_q.sqlite3"))
        dstore.add_rule("brief", "daily", {"at": "08:30"}, "morning brief", cooldown_seconds=0)
        check(len(dengine.tick(datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc))["proposed"]) == 0, "a daily rule must not fire before its time")
        check(len(dengine.tick(datetime(2026, 7, 15, 8, 31, tzinfo=timezone.utc))["proposed"]) == 1, "a daily rule must fire at/after its time")
        check(len(dengine.tick(datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc))["proposed"]) == 0, "a daily rule must fire only once a day")
        check(len(dengine.tick(datetime(2026, 7, 16, 8, 31, tzinfo=timezone.utc))["proposed"]) == 1, "a daily rule must fire again the next day")

        # 2b + 3b. File watcher baseline/change + cooldown floor.
        watched = scratch / "w.txt"
        watched.write_text("v0", encoding="utf-8")
        wstore = ProactivityStore(scratch / "w.sqlite3")
        wengine = ProactivityEngine(wstore, DurableTaskQueue(scratch / "w_q.sqlite3"))
        rule = wstore.add_rule("watcher", "file_change", {"path": str(watched)}, "react", cooldown_seconds=60)
        check(len(wengine.tick(T0)["proposed"]) == 0, "a file watcher must baseline on first sight, not fire")
        check(wstore.get_rule(rule.id).state.get("fingerprint") is not None, "the baseline fingerprint must be persisted")
        check(len(wengine.tick(T0 + timedelta(seconds=1))["proposed"]) == 0, "an unchanged file must not fire")
        watched.write_text("v1 changed", encoding="utf-8")
        check(len(wengine.tick(T0 + timedelta(seconds=5))["proposed"]) == 1, "a changed file must fire")
        watched.write_text("v2 changed again", encoding="utf-8")
        cooled = wengine.tick(T0 + timedelta(seconds=10))
        check(cooled["proposed"] == [], "a re-fire inside the cooldown must be suppressed")
        check([s["reason"] for s in cooled["suppressed"]] == ["cooldown"], f"suppression reason must be cooldown, got {cooled['suppressed']!r}")

        # 3c. Store clamps the budget ceiling; 3d. per-tick proposal cap.
        clamped = wstore.add_rule("greedy", "interval", {"seconds": 1}, "x", max_fires_per_day=10_000)
        check(clamped.max_fires_per_day == MAX_FIRES_PER_DAY_CEILING, f"max_fires_per_day must be clamped to {MAX_FIRES_PER_DAY_CEILING}")

        cstore = ProactivityStore(scratch / "cap.sqlite3")
        cengine = ProactivityEngine(cstore, DurableTaskQueue(scratch / "cap_q.sqlite3"))
        for i in range(MAX_PROPOSALS_PER_TICK + 3):
            cstore.add_rule(f"r{i}", "interval", {"seconds": 1}, f"task {i}", cooldown_seconds=0)
        capped_tick = cengine.tick(T0)
        check(len(capped_tick["proposed"]) == MAX_PROPOSALS_PER_TICK, f"a tick must propose at most {MAX_PROPOSALS_PER_TICK}")
        check(any(s["reason"] == "tick_proposal_cap" for s in capped_tick["suppressed"]), "the per-tick cap must be reported as suppression")

        # 4. Robustness.
        bstore = ProactivityStore(scratch / "b.sqlite3")
        bengine = ProactivityEngine(bstore, DurableTaskQueue(scratch / "b_q.sqlite3"))
        bstore.add_rule("broken", "interval", {"seconds": "not-a-number"}, "x")
        bstore.add_rule("good", "interval", {"seconds": 1}, "works")
        robust = bengine.tick(T0)
        check([p["rule"] for p in robust["proposed"]] == ["good"], f"a malformed rule must not fire nor block others, got {robust['proposed']!r}")
        check(bstore.add_rule("bogus", "telepathy", {}, "x") is None, "an unknown rule kind must be rejected")
        disabled = bstore.add_rule("off", "interval", {"seconds": 1}, "x")
        bstore.set_enabled(disabled.id, False)
        check(all(p["rule"] != "off" for p in bengine.tick(T0 + timedelta(days=1))["proposed"]), "a disabled rule must never fire")

        # 5. Durability across a restart.
        durable_path = scratch / "durable.sqlite3"
        ds = ProactivityStore(durable_path)
        kept = ds.add_rule("survivor", "interval", {"seconds": 3600}, "still here")
        del ds
        check(ProactivityStore(durable_path).get_rule(kept.id) is not None, "a standing rule must survive a restart")

        # 6. Default OFF + startup wiring.
        os.environ.pop("EVA_PROACTIVITY_ENABLED", None)
        check(proactivity_enabled() is False, "proactivity must be off by default")
        check(open_default_engine() is None, "open_default_engine must be None when disabled")
        os.environ["EVA_PROACTIVITY_ENABLED"] = "1"
        check(proactivity_enabled() is True, "proactivity must report enabled when the flag is set")

        main_source = (ROOT / "backend" / "eva" / "main.py").read_text(encoding="utf-8")
        check("_run_proactivity_catchup_if_enabled" in main_source, "main.py must wire the proactivity catch-up tick")

        # 7. Eval registered + suite green + verifier registered.
        task_ids = {task.id for task in offline_tasks()}
        check("proactive_trigger_proposes_but_never_authorizes" in task_ids, "the proactivity eval must be registered")
        eval_report = run_offline_evals()
        check(eval_report.all_passed, f"offline eval suite must stay green: {eval_report.summary_text()}")
        check(
            any(r.task_id == "proactive_trigger_proposes_but_never_authorizes" and r.passed for r in eval_report.results),
            "proactive_trigger_proposes_but_never_authorizes must pass",
        )

        verifier_name = "verify_eva_phase46_proactivity.py"
        check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 46 proactivity verifier")
        check(verifier_name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 46 proactivity verifier")
        descriptors = getattr(verify_eva_all, "VERIFIER_DESCRIPTORS")
        check(verifier_name in descriptors, "master verifier descriptor missing the Phase 46 proactivity verifier")

    finally:
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    print(
        "PASS: Phase 46 proactivity -- a firing rule only PROPOSES: it enqueues its request (left 'queued', never "
        "started/finished/approved) and notifies, so even an unattended 'delete all my files' rule can do nothing "
        "without the permission gate; interval/daily/file-change triggers are correct under an injected clock "
        "(daily fires once a day then again the next; a watcher baselines before it ever fires); runaway "
        "protection holds at every layer (cooldown floor, per-rule daily budget that resets next day, "
        "store-clamped budget ceiling, per-tick proposal cap); a malformed or unknown rule never fires and never "
        "blocks the others; standing rules survive a restart; proactivity is off by default with "
        "open_default_engine() None and the catch-up tick wired in main.py; and the new eval plus this verifier "
        "are registered and green."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
