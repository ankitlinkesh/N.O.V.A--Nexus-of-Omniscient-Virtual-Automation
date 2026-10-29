import asyncio
import json
from unittest.mock import MagicMock

import pytest

from backend.eva.api import routes
from backend.eva.core import triage
from backend.eva.core.triage import TriageStep, merge_steps, parse_steps


def run(coro):
    return asyncio.run(coro)


# ---- parsing and merging -------------------------------------------------

def test_parse_steps_drops_malformed_items():
    raw = {"steps": [{"kind": "command", "text": " pause  the music "}, {"kind": "bogus", "text": "x"}, {"kind": "tool"}, "junk", {"kind": "CHAT", "text": "hi"}]}
    assert parse_steps(raw) == [TriageStep("command", "pause the music"), TriageStep("chat", "hi")]
    assert parse_steps({"steps": "nope"}) == [] and parse_steps(None) == []


def test_merge_collapses_over_split_same_kind_steps_but_keeps_distinct_commands():
    steps = [TriageStep("work", "open gmail"), TriageStep("work", "write the email"), TriageStep("work", "send it")]
    assert merge_steps(steps) == [TriageStep("work", "open gmail then write the email then send it")]
    commands = [TriageStep("command", "pause the music"), TriageStep("command", "Pause the music"), TriageStep("command", "set volume to 20")]
    assert merge_steps(commands) == [TriageStep("command", "pause the music"), TriageStep("command", "set volume to 20")]


def test_merge_caps_the_plan():
    kinds = ["command", "tool", "command", "tool", "command", "tool"]
    assert len(merge_steps([TriageStep(k, f"s{i}") for i, k in enumerate(kinds)])) == triage.MAX_STEPS


# ---- the LLM call ---------------------------------------------------------

class _Resp:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload


def _fake_client(response=None, error=None):
    class Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            if error:
                raise error
            return response
    return Client


def _reply(steps):
    return _Resp(200, {"choices": [{"message": {"content": json.dumps({"steps": steps})}}]})


@pytest.fixture
def endpoint(monkeypatch):
    monkeypatch.setenv("EVA_TRIAGE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("EVA_TRIAGE", "on")


def test_triage_returns_merged_steps(endpoint, monkeypatch):
    monkeypatch.setattr(triage.httpx, "AsyncClient", _fake_client(_reply([{"kind": "work", "text": "a"}, {"kind": "work", "text": "b"}])))
    assert run(triage.triage_request("email rahul")) == [TriageStep("work", "a then b")]


def test_triage_failures_fall_back_to_none(endpoint, monkeypatch):
    monkeypatch.setattr(triage.httpx, "AsyncClient", _fake_client(error=ConnectionError("down")))
    assert run(triage.triage_request("anything")) is None
    monkeypatch.setattr(triage.httpx, "AsyncClient", _fake_client(_Resp(500, {})))
    assert run(triage.triage_request("anything")) is None
    monkeypatch.setattr(triage.httpx, "AsyncClient", _fake_client(_Resp(200, {"choices": [{"message": {"content": "not json"}}]})))
    assert run(triage.triage_request("anything")) is None
    monkeypatch.setattr(triage.httpx, "AsyncClient", _fake_client(_reply([])))
    assert run(triage.triage_request("anything")) is None


def test_triage_is_off_without_an_endpoint_or_when_disabled(monkeypatch):
    monkeypatch.delenv("EVA_TRIAGE_URL", raising=False)
    monkeypatch.delenv("CLOD_BASE_URL", raising=False)
    assert not triage.triage_enabled()
    monkeypatch.setenv("EVA_TRIAGE_URL", "http://x/v1")
    assert triage.triage_enabled()
    monkeypatch.setenv("EVA_TRIAGE", "off")
    assert not triage.triage_enabled()


# ---- dispatch --------------------------------------------------------------

def _apply(monkeypatch, steps, handled):
    async def fake_triage(message):
        return steps
    ran = []

    def fake_step(text, *a, **k):
        ran.append(text)
        return handled.get(text)

    monkeypatch.setattr(routes, "triage_request", fake_triage)
    monkeypatch.setattr(routes, "_run_command_step", fake_step)
    out = run(routes._apply_triage("msg", {}, MagicMock(), "s1", None, 0.0))
    return out, ran


def test_all_command_plans_run_each_step_and_finish(monkeypatch):
    steps = [TriageStep("command", "pause the music"), TriageStep("command", "set volume to 20")]
    (finished, force, goal, prefix), ran = _apply(monkeypatch, steps, {"pause the music": ("Paused.", "desktop-tool"), "set volume to 20": ("Volume 20.", "desktop-tool")})
    assert ran == ["pause the music", "set volume to 20"] and not force and goal is None
    assert finished[0] == "Paused.\nVolume 20."


def test_an_unclaimed_later_command_hands_the_rest_to_the_agent(monkeypatch):
    steps = [TriageStep("command", "open calculator"), TriageStep("command", "click Seven"), TriageStep("command", "click Plus")]
    (finished, force, goal, prefix), ran = _apply(monkeypatch, steps, {"open calculator": ("Done, calculator is open.", "desktop-tool")})
    assert ran == ["open calculator", "click Seven"]
    assert finished is None and force is True
    assert goal == "click Seven then click Plus" and prefix == "Done, calculator is open."


def test_an_unclaimed_first_command_sends_the_original_message_to_the_agent(monkeypatch):
    steps = [TriageStep("command", "check the C drive space"), TriageStep("command", "mute")]
    (finished, force, goal, prefix), ran = _apply(monkeypatch, steps, {})
    assert ran == ["check the C drive space"]
    assert finished is None and force is True and goal is None and prefix == ""


def test_work_steps_force_the_agent_runner_and_run_nothing_early(monkeypatch):
    steps = [TriageStep("command", "open spotify"), TriageStep("work", "email rahul")]
    (finished, force, goal, prefix), ran = _apply(monkeypatch, steps, {})
    assert finished is None and force is True and ran == [] and goal is None


def test_mixed_tool_and_chat_plans_fall_through_unchanged(monkeypatch):
    (finished, force, goal, prefix), ran = _apply(monkeypatch, [TriageStep("tool", "weather"), TriageStep("chat", "joke")], {})
    assert finished is None and force is False and ran == []


def test_no_plan_means_the_old_routing(monkeypatch):
    (finished, force, goal, prefix), ran = _apply(monkeypatch, None, {})
    assert finished is None and force is False


def test_pending_marker_is_only_reported_for_a_real_pending_call(monkeypatch):
    from backend.eva.security import tool_gate

    reply = "Say `confirm act_0123456789ab` to approve."
    monkeypatch.setattr(tool_gate, "get_pending_call", lambda pid: {"tool": "close_app"} if pid == "act_0123456789ab" else None)
    assert routes._pending_action_in(reply) == "act_0123456789ab"
    monkeypatch.setattr(tool_gate, "get_pending_call", lambda pid: None)
    assert routes._pending_action_in(reply) is None
    assert routes._pending_action_in("nothing to approve") is None


def test_label_only_click_target_is_hoisted_to_a_label():
    from backend.eva.agent.planner import PlannedToolCall

    hoisted = PlannedToolCall("screen.click", {"target": {"label": " Seven "}, "reason": "r"})
    assert hoisted.args == {"reason": "r", "label": "Seven"}
    real = PlannedToolCall("screen.click", {"target": {"label": "Seven", "x": 1, "y": 2}})
    assert real.args["target"]["x"] == 1 and "label" not in real.args
    other = PlannedToolCall("open_app", {"target": {"label": "x"}})
    assert other.args == {"target": {"label": "x"}}


def test_fallback_done_after_a_planner_failure_does_not_claim_the_task_is_finished():
    from backend.eva.agent.planner import PlannerDecision, _honest_fallback

    done = PlannerDecision(type="done", reason="r", tool_calls=[], final_response="I finished the task. open_app returned Opening calculator.")
    said = _honest_fallback(done, "ReadTimeout: no response within 12s", mode="agent_step").final_response
    assert "I finished the task" not in said and "cannot say the whole request is done" in said and "Opening calculator" in said
    assert _honest_fallback(done, "x", mode="single_turn") is done
    answer = PlannerDecision(type="answer", reason="r", tool_calls=[], final_response="hi")
    assert _honest_fallback(answer, "x", mode="agent_step") is answer
