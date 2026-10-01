"""Phase 122: findings from prompting NOVA through its chat UI.

1. "search the web for who won the 2026 FIFA World Cup" answered "it has not
   happened yet" in October 2026 without searching: no planner prompt had the date.
2. "list my rules" took 26.7s through the planner; only "rules"/"list rules" matched.
3. "remind me every morning at 9" fired at 04:36 Pacific (09:00 was read as UTC).
   Covered in test_proactivity_triggers.py.
4. The model copied an old approval prompt (and its action id) out of the history
   instead of calling the tool; confirming it "succeeded" and ran nothing.
"""
from __future__ import annotations

import asyncio

from backend.eva.agent import planner as planner_mod
from backend.eva.agent.planner import PlannerDecision, ToolCallPlanner


def test_every_planner_prompt_carries_todays_date_and_the_search_rule():
    from datetime import datetime

    rule = planner_mod._freshness_rule()
    assert str(datetime.now().year) in rule
    assert "web_search" in rule and "has not happened yet" in rule


def test_the_rules_list_answers_the_phrasings_people_use():
    from backend.eva.core.fast_commands import maybe_handle_fast_command

    for phrase in ("list my rules", "show my rules", "what are my rules?", "my reminders"):
        reply = maybe_handle_fast_command(phrase, None, {})
        assert reply is not None and reply[1] == "fast-command", phrase


def test_action_ids_are_masked_in_history_given_to_the_planner():
    history = [
        {"role": "user", "content": "write a file"},
        {"role": "assistant", "content": "Say `confirm override act_343dbee85b5f` to approve"},
    ]
    masked = planner_mod._mask_action_ids(history)
    assert "act_343dbee85b5f" not in masked[1]["content"]
    assert masked[0] == history[0]


def test_an_answer_shaped_like_an_approval_prompt_is_refused():
    imitated = PlannerDecision(
        type="answer", reason="", tool_calls=[],
        final_response="What you are being asked to approve ... Say `confirm override act_343dbee85b5f`",
    )
    out = planner_mod._refuse_imitated_approval(imitated)
    assert "act_" not in out.final_response and "nothing to approve" in out.final_response
    plain = PlannerDecision(type="answer", reason="", tool_calls=[], final_response="It's 4:08 AM.")
    assert planner_mod._refuse_imitated_approval(plain) is plain


def test_plan_applies_both_guards(monkeypatch):
    seen = {}

    async def fake_plan(self, message, history=None, **kwargs):
        seen["history"] = history
        return PlannerDecision(type="answer", reason="", tool_calls=[], final_response="Say `confirm act_0123456789ab`")

    monkeypatch.setattr(ToolCallPlanner, "_plan", fake_plan)
    planner = ToolCallPlanner.__new__(ToolCallPlanner)
    out = asyncio.run(planner.plan("x", [{"role": "assistant", "content": "confirm act_0123456789ab"}]))
    assert "act_0123456789ab" not in seen["history"][0]["content"]
    assert "act_" not in out.final_response


def test_a_stale_gate_action_is_cancelled_not_confirmed(monkeypatch):
    import backend.eva.permissions.confirmation as conf
    import backend.eva.permissions.ledger as ledger
    from backend.eva.security import tool_gate

    class Action:
        source = "tool_gate"
        status = "pending_override"

    cancelled = []
    monkeypatch.setattr(ledger, "get_pending_action", lambda action_id: Action())
    monkeypatch.setattr(conf, "cancel_pending_action", lambda action_id: cancelled.append(action_id))
    monkeypatch.setattr(conf, "confirm_pending_action", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not confirm")))
    monkeypatch.setattr(tool_gate, "get_pending_call", lambda action_id: None)
    reply = conf.handle_confirmation_command("confirm override act_343dbee85b5f")
    assert "Nothing was run" in reply and cancelled == ["act_343dbee85b5f"]


def test_piper_is_given_utf8_so_non_latin_replies_can_be_spoken(monkeypatch, tmp_path):
    # Live: the Hindi translation and a window list with "◑" each returned
    # HTTP 500 from /api/tts/piper -- 'charmap' codec can't encode.
    import backend.eva.voice.piper as piper

    monkeypatch.setattr(piper, "piper_status", lambda: {
        "enabled": True, "exe_exists": True, "model_exists": True, "runtime_ready": True,
        "exe": str(tmp_path / "piper.exe"), "model": str(tmp_path / "voice.onnx"),
    })
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(kwargs)
        kwargs["input"].encode(kwargs.get("encoding") or "cp1252")  # what the real pipe does
        out = command[command.index("--output_file") + 1]
        open(out, "wb").write(b"RIFF")

        class Done:
            returncode = 0
            stdout = stderr = ""

        return Done()

    monkeypatch.setattr(piper.subprocess, "run", fake_run)
    assert piper.synthesize_piper_wav("नमस्ते ◑ hello") == b"RIFF"
    assert seen["encoding"] == "utf-8"


def test_battery_is_read_from_the_power_status():
    # Live: "what's my battery level?" -> "I don't have access to battery level".
    from backend.eva.tools.power_info import _PowerStatus, battery_from_status

    on_ac = _PowerStatus(ACLineStatus=1, BatteryFlag=1, BatteryLifePercent=80, BatteryLifeTime=0xFFFFFFFF)
    assert battery_from_status(on_ac) == {"battery_present": True, "battery_percent": 80, "plugged_in": True}
    no_battery = _PowerStatus(ACLineStatus=1, BatteryFlag=128, BatteryLifePercent=255)
    assert battery_from_status(no_battery) == {"battery_present": False}


def test_a_link_is_opened_only_when_asked_to_open_it():
    # Live: "summarize the page at https://example.com" opened the page and
    # summarized nothing.
    from backend.eva.core.operator_commands import _url_from_message

    assert _url_from_message("open https://example.com") == "https://example.com"
    assert _url_from_message("https://example.com") == "https://example.com"
    assert _url_from_message("summarize the page at https://example.com") is None
    assert _url_from_message("is https://example.com safe?") is None
