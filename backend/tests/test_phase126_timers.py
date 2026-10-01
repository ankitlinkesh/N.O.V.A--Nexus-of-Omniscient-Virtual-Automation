"""Phase 126: one-shot timers and reminders.

Parsing is deterministic and whole-sentence; a one-shot fires exactly once at an
absolute UTC instant; firing NOTIFIES and never enqueues work. Every test uses an
injected clock, so nothing sleeps.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from eva.proactivity import timers as timers_mod
from eva.proactivity import triggers
from eva.proactivity.engine import ProactivityEngine
from eva.proactivity.models import ONCE
from eva.proactivity.store import ProactivityStore
from eva.proactivity.timers import parse_once_request
from eva.tasks.durable_queue import DurableTaskQueue

PDT = timezone(timedelta(hours=-7))
# 12:00 noon in PDT == 19:00Z.
NOW = datetime(2026, 10, 1, 19, 0, tzinfo=timezone.utc)


def parse(text, now=NOW, tz=PDT):
    return parse_once_request(text, now, tz)


# -- parsing -----------------------------------------------------------------

@pytest.mark.parametrize(
    "text, seconds, what",
    [
        ("set a timer for 5 minutes", 300, "timer"),
        ("Set a timer for 5 minutes.", 300, "timer"),
        ("timer 10 min", 600, "timer"),
        ("timer for 10 mins", 600, "timer"),
        ("5 minute timer", 300, "timer"),
        ("set a 5 minute timer", 300, "timer"),
        ("set a 5-minute timer", 300, "timer"),
        ("start a timer for 90 seconds", 90, "timer"),
        ("set a timer for an hour", 3600, "timer"),
        ("set a timer for half an hour", 1800, "timer"),
        ("set a timer for 1 hour 30 minutes", 5400, "timer"),
        ("set a timer for 1.5 hours", 5400, "timer"),
        ("set a timer for five minutes", 300, "timer"),
        ("can you please set a timer for 3 minutes?", 180, "timer"),
        ("remind me in 20 minutes to stretch", 1200, "reminder"),
        ("remind me to stretch in 20 minutes", 1200, "reminder"),
        ("in 20 minutes remind me to stretch", 1200, "reminder"),
        ("set a reminder in 2 hours to call the bank", 7200, "reminder"),
    ],
)
def test_duration_phrasings(text, seconds, what):
    p = parse(text)
    assert p is not None and not p.error, text
    assert (p.what, p.seconds) == (what, seconds)
    assert p.at_utc == NOW + timedelta(seconds=seconds)


def test_reminder_text_is_kept_verbatim():
    assert parse("remind me in 20 minutes to stretch").text == "stretch"
    assert parse("remind me at 6 pm to call mom").text == "call mom"
    assert parse("remind me tomorrow at 9 to submit the form").text == "submit the form"


@pytest.mark.parametrize(
    "text",
    [
        "remind me what I said earlier",
        "remind me",
        "what time is it",
        "timer settings",
        "set the oven to 5 minutes",
        "set a timer",
        "what's the timer for 5 minutes",
        "how long left on my timer",
        "remind me every day at 9 to stretch",     # recurring: the rule parser's job
        "remind me every 5 minutes to stretch",
        "remind me to read in 3 days",              # days are not in the vocabulary
        "set a timer for 2 days",
        "tell me about timers",
        "",
    ],
)
def test_non_schedules_are_refused(text):
    assert parse(text) is None, text


@pytest.mark.parametrize(
    "text",
    [
        "reset a timer for 5 minutes",               # contains "set a timer for 5 minutes"
        "preset a timer for 5 minutes",
        "I will set a timer for 5 minutes tomorrow",
        "why did you set a timer for 5 minutes",
    ],
)
def test_phrasings_match_whole_sentences_never_substrings(text):
    assert parse(text) is None, text


def test_floor_and_cap():
    assert parse("set a timer for 2 seconds").seconds == 5          # floored, not refused
    assert parse("set a timer for 7 days") is None                  # days are not a unit
    assert parse("set a timer for 168 hours").seconds == 7 * 24 * 3600
    over = parse("set a timer for 169 hours")
    assert over.error and over.at_utc is None                       # told, not silently clamped
    zero = parse("set a timer for 0 minutes")
    assert zero.error and zero.at_utc is None


def test_absolute_times_use_local_time_not_utc():
    # 12:00 PDT: "6 pm" is 18:00 PDT == 01:00Z tomorrow. Applying it to UTC would
    # have fired at 18:00Z, i.e. 11:00 local.
    p = parse("remind me at 6 pm to call mom")
    assert p.at_utc == datetime(2026, 10, 2, 1, 0, tzinfo=timezone.utc)
    assert p.day_word == "today" and p.absolute


def test_time_already_past_goes_to_tomorrow():
    seven_pm_local = datetime(2026, 10, 2, 2, 0, tzinfo=timezone.utc)
    p = parse("remind me at 6 pm to call mom", now=seven_pm_local)
    assert p.at_utc == datetime(2026, 10, 3, 1, 0, tzinfo=timezone.utc)  # 18:00 PDT tomorrow
    assert p.day_word == "tomorrow"
    # Still ahead -> today.
    assert parse("remind me at 18:30 to call mom").day_word == "today"
    # 24h and am/pm agree.
    assert parse("remind me at 18:30 to x").at_utc == datetime(2026, 10, 2, 1, 30, tzinfo=timezone.utc)


def test_tomorrow_at_nine_is_nine_in_the_morning():
    p = parse("remind me tomorrow at 9 to submit the form")
    assert p.at_utc == datetime(2026, 10, 2, 16, 0, tzinfo=timezone.utc)  # 09:00 PDT tomorrow
    assert p.day_word == "tomorrow"
    assert parse("remind me tomorrow at 3 to x").at_utc == datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc)  # 3 pm


def test_explicit_today_that_has_passed_is_an_error_not_tomorrow():
    p = parse("remind me today at 11 am to x")
    assert p.error and p.at_utc is None


@pytest.mark.parametrize("text", ["remind me at 25 to x", "remind me at 13 pm to x", "remind me at 9:75 to x"])
def test_invalid_clock_times_are_errors(text):
    p = parse(text)
    assert p is not None and p.error


def test_default_timezone_comes_from_the_injectable_local_tz(monkeypatch):
    monkeypatch.setattr(triggers, "_local_tz", lambda: PDT)
    p = parse_once_request("remind me at 6 pm to call mom", NOW)
    assert p.at_utc == datetime(2026, 10, 2, 1, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(triggers, "_local_tz", lambda: timezone.utc)
    p = parse_once_request("remind me at 6 pm to call mom", NOW)
    assert p.at_utc == datetime(2026, 10, 2, 18, 0, tzinfo=timezone.utc)  # 19:00Z now, so 18:00Z is tomorrow
    assert timers_mod.format_local_time(NOW) == "7:00 PM"


# -- one-shot firing ---------------------------------------------------------

@pytest.fixture()
def parts(tmp_path):
    store = ProactivityStore(tmp_path / "p.sqlite3")
    queue = DurableTaskQueue(tmp_path / "q.sqlite3")
    sent: list = []
    engine = ProactivityEngine(store, queue, notifier=lambda title, body: sent.append((title, body)))
    return store, queue, engine, sent


def add(store, sentence, now=NOW):
    parsed = parse(sentence, now)
    assert parsed is not None and not parsed.error, sentence
    rule = store.add_rule(**parsed.as_add_rule_kwargs())
    assert rule is not None and rule.kind == ONCE
    return rule, parsed


def test_one_shot_never_fires_early_fires_at_the_instant_and_never_twice(parts):
    store, queue, engine, sent = parts
    rule, parsed = add(store, "set a timer for 5 minutes")
    for early in (NOW, NOW + timedelta(seconds=299), parsed.at_utc - timedelta(microseconds=1)):
        assert engine.tick(early)["notified"] == []
    assert store.list_notifications() == []

    fired = engine.tick(parsed.at_utc)
    assert len(fired["notified"]) == 1
    assert len(store.list_notifications()) == 1

    # Never twice: later ticks, the dedicated timer poll, and a re-tick at the same instant.
    for later in (parsed.at_utc, parsed.at_utc + timedelta(seconds=1), parsed.at_utc + timedelta(days=30)):
        assert engine.tick(later)["notified"] == []
        assert engine.tick_once_rules(later) == []
    assert len(store.list_notifications()) == 1
    assert len(sent) == 1

    done = store.get_rule(rule.id)
    assert done.enabled is False and done.state == {"done": True} and done.last_fired_at


def test_two_ticks_racing_on_the_same_due_rule_notify_once(parts):
    """Both the 60s cycle and the 2s timer loop can hold the same due rule.
    The store's atomic claim, not luck, decides who announces it."""
    store, queue, engine, sent = parts
    rule, parsed = add(store, "set a timer for 1 minute")
    stale = store.get_rule(rule.id)  # both racers took their snapshot before either fired
    day = parsed.at_utc.date().isoformat()
    first = engine._fire_once(stale, parsed.at_utc, day)
    second = engine._fire_once(stale, parsed.at_utc, day)
    assert first is not None and second is None
    assert len(store.list_notifications()) == 1 and len(sent) == 1


def test_a_missed_timer_fires_late_once_and_says_so(parts):
    store, queue, engine, sent = parts
    rule, parsed = add(store, "remind me in 20 minutes to stretch")
    result = engine.tick(parsed.at_utc + timedelta(hours=3))  # server was down
    assert len(result["notified"]) == 1
    assert "it was due at" in sent[0][1]


def test_firing_notifies_and_does_not_enqueue_an_executable_task(parts):
    store, queue, engine, sent = parts
    rule, parsed = add(store, "remind me in 5 minutes to delete my files")
    result = engine.tick(parsed.at_utc)
    assert result["proposed"] == []
    assert queue.stats()["queued"] == 0 and queue.list_tasks() == []
    notes = store.list_notifications()
    assert [n.message for n in notes] == ["Reminder: delete my files"]
    assert sent == [("N.O.V.A reminder", "delete my files")]


def test_timer_notification_text(parts):
    store, queue, engine, sent = parts
    rule, parsed = add(store, "set a timer for 5 minutes")
    engine.tick(parsed.at_utc)
    assert store.list_notifications()[0].message == "Your timer for 5 minutes is up."
    assert sent[0][0] == "N.O.V.A timer"


def test_a_failing_notifier_never_loses_the_in_app_notification(tmp_path):
    store = ProactivityStore(tmp_path / "p.sqlite3")

    def boom(title, body):
        raise RuntimeError("no toast")

    engine = ProactivityEngine(store, None, notifier=boom)
    rule, parsed = add(store, "set a timer for 1 minute")
    assert len(engine.tick(parsed.at_utc)["notified"]) == 1
    assert len(store.list_notifications()) == 1


def test_one_shots_do_not_disturb_recurring_rules(parts):
    store, queue, engine, sent = parts
    store.add_rule("news", "interval", {"seconds": 3600}, "summarize my news")
    rule, parsed = add(store, "set a timer for 1 minute")
    result = engine.tick(parsed.at_utc)
    assert [p["rule"] for p in result["proposed"]] == ["news"]   # still proposes, via the queue
    assert queue.list_tasks()[0].request == "summarize my news"
    assert len(result["notified"]) == 1


def test_timer_loop_polls_fast_enough_and_fires_with_no_real_sleep(parts):
    from eva.runtime.scheduler import run_timer_loop, timer_poll_interval

    assert timer_poll_interval({}) <= 5  # a 5-second floor timer must not wait on a 60s cycle
    store, queue, engine, sent = parts
    rule, parsed = add(store, "set a timer for 1 minute", now=datetime.now(timezone.utc) - timedelta(minutes=2))

    napped: list = []

    async def fake_sleep(seconds):
        napped.append(seconds)

    polls = asyncio.run(run_timer_loop(engine, max_cycles=3, sleep=fake_sleep, interval=2.0))
    assert polls == 3 and napped == [2.0, 2.0, 2.0]
    assert len(store.list_notifications()) == 1 and len(sent) == 1


# -- fast commands -----------------------------------------------------------

@pytest.fixture()
def console(tmp_path, monkeypatch):
    monkeypatch.setenv("EVA_PROACTIVITY_ENABLED", "1")
    monkeypatch.setenv("EVA_PROACTIVITY_PATH", str(tmp_path / "rules.sqlite3"))
    from eva.core.fast_commands import maybe_handle_fast_command

    def say(text):
        reply = maybe_handle_fast_command(text, None, {})
        return reply[0] if reply and reply[1] == "fast-command" else reply

    return say


def test_creation_reply_names_the_local_time(console):
    reply = console("set a timer for 5 minutes")
    assert reply.startswith("Timer set for 5 minutes — I'll notify you at ")
    assert reply.endswith(("AM.", "PM."))


def test_list_cancel_single_multiple_and_by_id(console):
    assert "No active timers" in console("timers")
    console("set a timer for 5 minutes")
    assert "5 minutes" in console("how long left on my timer")
    assert "5 minutes" in console("my reminders")             # merged with the Phase 122 rules list
    assert console("cancel my timer").startswith("Cancelled:")
    assert "No active timers" in console("timers")

    console("set a timer for 5 minutes")
    console("set a timer for 10 minutes")
    listed = console("cancel the timer")                       # two active -> list, cancel nothing
    assert "2 active timers" in listed and "5 minutes" in listed and "10 minutes" in listed
    assert "Active timers and reminders (2)" in console("timers")
    short_id = listed.split("[")[1].split("]")[0]
    assert console(f"cancel timer {short_id}").startswith("Cancelled:")
    assert "Active timers and reminders (1)" in console("timers")
    assert "Cancelled 1" in console("cancel all timers") or console("timers").startswith("No active")


def test_delete_rule_still_removes_a_timer_and_recurring_rules_still_work(console):
    reply = console("set a timer for 5 minutes")
    listing = console("timers")
    rule_id = listing.split("[")[1].split("]")[0]
    assert console(f"delete rule {rule_id}").startswith("Deleted rule")
    assert "No active timers" in console("timers")
    assert console("remind me every morning to summarize my news").startswith("Rule created")
    assert "Proactive rules (1)" in console("rules")


def test_reminders_that_are_not_timers_are_left_to_other_handlers(console):
    assert console("remind me what I said earlier") is None or "Timer set" not in str(console("remind me what I said earlier"))
    assert not str(console("set the oven to 5 minutes")).startswith("Timer set")


def test_a_reminder_carrying_a_live_secret_is_refused(console, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-0123456789abcdefghijklmnop")
    reply = console("remind me in 5 minutes to use key sk-live-0123456789abcdefghijklmnop")
    assert "secret" in reply
    assert "No active timers" in console("timers")


def test_proactivity_off_says_so_instead_of_pretending(tmp_path, monkeypatch):
    monkeypatch.delenv("EVA_PROACTIVITY_ENABLED", raising=False)
    from eva.core.fast_commands import maybe_handle_fast_command

    reply = maybe_handle_fast_command("set a timer for 5 minutes", None, {})[0]
    assert "EVA_PROACTIVITY_ENABLED" in reply


# -- trust boundary + planner guidance ---------------------------------------

def test_timers_are_not_a_planner_tool():
    from eva.tools.registry import ToolRegistry

    names = " ".join(t["name"] for t in ToolRegistry().list_tools()).lower()
    for word in ("timer", "remind", "reminder", "proactiv", "add_rule", "schedule"):
        assert word not in names, word


def test_both_planner_rule_lists_tell_the_user_how_to_set_a_timer():
    import inspect

    from eva.agent import planner

    source = inspect.getsource(planner)
    assert source.count("set a timer for 5 minutes") >= 2
    assert source.count("You cannot set timers, alarms or reminders yourself") == 2


def test_toast_never_pops_under_pytest_and_survives_a_dead_powershell():
    from eva.runtime import toast

    assert toast.toasts_enabled() is False  # PYTEST_CURRENT_TEST is set

    class Boom:
        def __call__(self, *a, **k):
            raise FileNotFoundError("powershell")

    result = toast.send_toast("t", "b", runner=Boom(), platform="win32")
    assert result["ok"] is False and "powershell" in result["detail"]
    assert toast.send_toast("t", "b", platform="linux")["ok"] is False

    seen: dict = {}

    class Proc:
        returncode = 0
        stdout = stderr = ""

    def fake_run(cmd, **kw):
        seen["env"], seen["cmd"] = kw["env"], cmd
        return Proc()

    ok = toast.send_toast("Title <&>", "Body $(rm -rf)", runner=fake_run, platform="win32")
    assert ok["ok"] is True
    # Text travels in the environment, never spliced into the script.
    assert seen["env"]["NOVA_TOAST_BODY"] == "Body $(rm -rf)"
    assert "rm -rf" not in " ".join(seen["cmd"])


def test_should_fire_itself_refuses_a_done_or_already_fired_one_shot(parts):
    """The predicate is a guard of its own, independent of the store's claim."""
    store, queue, engine, sent = parts
    rule, parsed = add(store, "set a timer for 1 minute")
    late = parsed.at_utc + timedelta(minutes=5)
    assert triggers.should_fire(rule, late)[0] is True
    from dataclasses import replace

    assert triggers.should_fire(replace(rule, state={"done": True}), late)[0] is False
    assert triggers.should_fire(replace(rule, last_fired_at=late.isoformat()), late)[0] is False
    assert triggers.should_fire(replace(rule, spec={"at_utc": "garbage"}), late)[0] is False
