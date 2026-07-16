"""Proactive trigger evaluation + rule store (Phase 46).

The clock is injected, so a whole day of schedule behavior runs in microseconds.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from eva.proactivity.models import MAX_FIRES_PER_DAY_CEILING, ProactiveRule
from eva.proactivity.store import ProactivityStore
from eva.proactivity.triggers import should_fire

T0 = datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc)


def _rule(**kwargs) -> ProactiveRule:
    base = dict(id="r1", name="r", kind="interval", spec={"seconds": 60}, request="do it")
    base.update(kwargs)
    return ProactiveRule(**base)


# -- interval --------------------------------------------------------------

def test_interval_fires_when_never_fired():
    fires, _ = should_fire(_rule(), T0)
    assert fires is True


def test_interval_waits_for_the_interval():
    rule = _rule(last_fired_at=T0.isoformat())
    assert should_fire(rule, T0 + timedelta(seconds=30))[0] is False
    assert should_fire(rule, T0 + timedelta(seconds=61))[0] is True


def test_interval_with_bad_spec_never_fires():
    assert should_fire(_rule(spec={"seconds": 0}), T0)[0] is False
    assert should_fire(_rule(spec={"seconds": "abc"}), T0)[0] is False
    assert should_fire(_rule(spec={}), T0)[0] is False


# -- daily -----------------------------------------------------------------

def test_daily_fires_only_at_or_after_target():
    rule = _rule(kind="daily", spec={"at": "08:30"})
    assert should_fire(rule, datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc))[0] is False
    assert should_fire(rule, datetime(2026, 7, 15, 8, 31, tzinfo=timezone.utc))[0] is True


def test_daily_fires_once_per_day():
    fired_at = datetime(2026, 7, 15, 8, 31, tzinfo=timezone.utc)
    rule = _rule(kind="daily", spec={"at": "08:30"}, last_fired_at=fired_at.isoformat())
    # later the same day -> no
    assert should_fire(rule, datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc))[0] is False
    # next day at target -> yes
    assert should_fire(rule, datetime(2026, 7, 16, 8, 30, tzinfo=timezone.utc))[0] is True


def test_daily_with_bad_spec_never_fires():
    assert should_fire(_rule(kind="daily", spec={"at": "99:99"}), T0)[0] is False
    assert should_fire(_rule(kind="daily", spec={"at": "nonsense"}), T0)[0] is False


# -- file change -----------------------------------------------------------

def test_file_watch_baselines_first_then_fires_on_change(tmp_path):
    path = tmp_path / "w.txt"
    path.write_text("v1")
    rule = _rule(kind="file_change", spec={"path": str(path)})

    fires, state = should_fire(rule, T0)
    assert fires is False, "first observation must only baseline, never fire"
    assert state["fingerprint"] is not None

    rule = _rule(kind="file_change", spec={"path": str(path)}, state=state)
    assert should_fire(rule, T0)[0] is False, "unchanged file must not fire"

    path.write_text("v2 different length")
    fires, state2 = should_fire(rule, T0)
    assert fires is True
    assert state2["fingerprint"] != state["fingerprint"]


def test_file_watch_missing_path_never_fires():
    assert should_fire(_rule(kind="file_change", spec={"path": ""}), T0)[0] is False


def test_file_watch_fires_once_when_a_known_file_disappears(tmp_path):
    path = tmp_path / "gone.txt"
    path.write_text("here")
    _, state = should_fire(_rule(kind="file_change", spec={"path": str(path)}), T0)
    path.unlink()
    rule = _rule(kind="file_change", spec={"path": str(path)}, state=state)
    fires, new_state = should_fire(rule, T0)
    assert fires is True
    assert new_state["fingerprint"] is None


# -- general ---------------------------------------------------------------

def test_disabled_rule_never_fires():
    assert should_fire(_rule(enabled=False), T0)[0] is False


def test_unknown_kind_never_fires():
    assert should_fire(_rule(kind="telepathy"), T0)[0] is False


# -- store -----------------------------------------------------------------

def test_store_roundtrip_and_persistence(tmp_path):
    path = tmp_path / "p.sqlite3"
    store = ProactivityStore(path)
    rule = store.add_rule("news", "interval", {"seconds": 3600}, "summarize news")
    assert rule is not None
    # A standing rule must survive a restart.
    assert ProactivityStore(path).get_rule(rule.id).name == "news"
    assert len(ProactivityStore(path).list_rules()) == 1


def test_store_rejects_invalid_rule(tmp_path):
    store = ProactivityStore(tmp_path / "p.sqlite3")
    assert store.add_rule("x", "not_a_kind", {}, "req") is None
    assert store.add_rule("x", "interval", {"seconds": 1}, "   ") is None


def test_store_clamps_daily_budget(tmp_path):
    store = ProactivityStore(tmp_path / "p.sqlite3")
    rule = store.add_rule("greedy", "interval", {"seconds": 1}, "x", max_fires_per_day=10_000)
    assert rule.max_fires_per_day == MAX_FIRES_PER_DAY_CEILING


def test_store_enable_disable_and_delete(tmp_path):
    store = ProactivityStore(tmp_path / "p.sqlite3")
    rule = store.add_rule("r", "interval", {"seconds": 1}, "x")
    assert store.set_enabled(rule.id, False).enabled is False
    assert store.list_rules(enabled_only=True) == []
    assert store.delete_rule(rule.id) is True
    assert store.get_rule(rule.id) is None


def test_notifications_roundtrip_and_mark_read(tmp_path):
    store = ProactivityStore(tmp_path / "p.sqlite3")
    store.add_notification("r1", "something happened")
    assert len(store.list_notifications(unread_only=True)) == 1
    assert store.mark_all_read() == 1
    assert store.list_notifications(unread_only=True) == []
