"""The proactivity engine: proposes work, never authorizes it (Phase 46)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from eva.proactivity.engine import MAX_PROPOSALS_PER_TICK, ProactivityEngine
from eva.proactivity.store import ProactivityStore
from eva.tasks.durable_queue import DurableTaskQueue

T0 = datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc)


@pytest.fixture()
def parts(tmp_path):
    store = ProactivityStore(tmp_path / "p.sqlite3")
    queue = DurableTaskQueue(tmp_path / "q.sqlite3")
    return store, queue, ProactivityEngine(store, queue)


def test_firing_rule_enqueues_and_notifies(parts):
    store, queue, engine = parts
    store.add_rule("news", "interval", {"seconds": 3600}, "summarize my news")
    result = engine.tick(T0)
    assert [p["rule"] for p in result["proposed"]] == ["news"]
    # It PROPOSED: the request is queued, awaiting the gate.
    assert queue.stats()["queued"] == 1
    assert queue.list_tasks()[0].request == "summarize my news"
    assert len(store.list_notifications()) == 1


def test_a_tick_never_executes_anything(parts):
    """The core safety property: a fired rule only enqueues — the task is left
    'queued', never run, never approved, never completed."""
    store, queue, engine = parts
    store.add_rule("dangerous", "interval", {"seconds": 1}, "delete all my files")
    engine.tick(T0)
    task = queue.list_tasks()[0]
    assert task.status == "queued"
    assert task.started_at is None
    assert task.finished_at is None
    assert task.result_summary == ""
    assert queue.stats()["succeeded"] == 0
    assert queue.stats()["running"] == 0


def test_queued_task_records_the_proactive_source(parts):
    store, queue, engine = parts
    rule = store.add_rule("watcher", "interval", {"seconds": 1}, "react")
    engine.tick(T0)
    assert queue.list_tasks()[0].source.startswith("proactive:")


def test_cooldown_suppresses_rapid_refire(tmp_path):
    store = ProactivityStore(tmp_path / "p.sqlite3")
    queue = DurableTaskQueue(tmp_path / "q.sqlite3")
    engine = ProactivityEngine(store, queue)
    watched = tmp_path / "w.txt"
    watched.write_text("v0")
    store.add_rule("watcher", "file_change", {"path": str(watched)}, "react", cooldown_seconds=60)

    engine.tick(T0)  # baseline
    watched.write_text("v1")
    assert len(engine.tick(T0 + timedelta(seconds=5))["proposed"]) == 1
    watched.write_text("v2 longer")
    result = engine.tick(T0 + timedelta(seconds=10))
    assert result["proposed"] == []
    assert [s["reason"] for s in result["suppressed"]] == ["cooldown"]


def test_daily_budget_caps_a_spammy_rule(parts):
    store, queue, engine = parts
    store.add_rule("spammy", "interval", {"seconds": 1}, "do it", cooldown_seconds=0, max_fires_per_day=2)
    fired = 0
    for i in range(4):
        fired += len(engine.tick(T0 + timedelta(seconds=10 * i))["proposed"])
    assert fired == 2, "the daily budget must cap the number of proposals"
    assert queue.stats()["queued"] == 2
    last = engine.tick(T0 + timedelta(seconds=100))
    assert [s["reason"] for s in last["suppressed"]] == ["daily_budget"]


def test_daily_budget_resets_next_day(parts):
    store, queue, engine = parts
    store.add_rule("daily-ish", "interval", {"seconds": 1}, "x", cooldown_seconds=0, max_fires_per_day=1)
    assert len(engine.tick(T0)["proposed"]) == 1
    assert len(engine.tick(T0 + timedelta(seconds=5))["proposed"]) == 0
    assert len(engine.tick(T0 + timedelta(days=1))["proposed"]) == 1


def test_tick_proposal_cap_bounds_a_single_tick(parts):
    store, queue, engine = parts
    for i in range(MAX_PROPOSALS_PER_TICK + 3):
        store.add_rule(f"rule{i}", "interval", {"seconds": 1}, f"task {i}", cooldown_seconds=0)
    result = engine.tick(T0)
    assert len(result["proposed"]) == MAX_PROPOSALS_PER_TICK
    assert any(s["reason"] == "tick_proposal_cap" for s in result["suppressed"])


def test_disabled_rule_is_not_evaluated(parts):
    store, queue, engine = parts
    rule = store.add_rule("off", "interval", {"seconds": 1}, "x")
    store.set_enabled(rule.id, False)
    result = engine.tick(T0)
    assert result["proposed"] == []
    assert result["evaluated"] == 0


def test_engine_without_queue_still_notifies_but_queues_nothing(tmp_path):
    store = ProactivityStore(tmp_path / "p.sqlite3")
    engine = ProactivityEngine(store, None)
    store.add_rule("no-queue", "interval", {"seconds": 1}, "x")
    result = engine.tick(T0)
    assert len(result["proposed"]) == 1
    assert result["proposed"][0]["task_id"] == ""
    assert len(store.list_notifications()) == 1


def test_broken_rule_does_not_stop_the_others(parts):
    store, queue, engine = parts
    store.add_rule("broken", "interval", {"seconds": "not-a-number"}, "x")
    store.add_rule("good", "interval", {"seconds": 1}, "works")
    result = engine.tick(T0)
    assert [p["rule"] for p in result["proposed"]] == ["good"]


def test_file_baseline_state_persists_without_firing(tmp_path):
    store = ProactivityStore(tmp_path / "p.sqlite3")
    engine = ProactivityEngine(store, DurableTaskQueue(tmp_path / "q.sqlite3"))
    watched = tmp_path / "w.txt"
    watched.write_text("v0")
    rule = store.add_rule("watcher", "file_change", {"path": str(watched)}, "react")
    assert engine.tick(T0)["proposed"] == []
    # The baseline must have been persisted, so a later change is detected.
    assert store.get_rule(rule.id).state.get("fingerprint") is not None
