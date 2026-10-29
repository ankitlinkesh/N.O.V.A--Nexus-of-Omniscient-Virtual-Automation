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
    (finished, force), ran = _apply(monkeypatch, steps, {"pause the music": ("Paused.", "desktop-tool"), "set volume to 20": ("Volume 20.", "desktop-tool")})
    assert ran == ["pause the music", "set volume to 20"] and not force
    assert finished[0] == "Paused.\nVolume 20."


def test_an_unclaimed_command_is_reported_honestly_and_stops(monkeypatch):
    steps = [TriageStep("command", "pause the music"), TriageStep("command", "do a barrel roll"), TriageStep("command", "mute")]
    (finished, _), ran = _apply(monkeypatch, steps, {"pause the music": ("Paused.", "desktop-tool")})
    assert ran == ["pause the music", "do a barrel roll"]
    assert finished[0] == "Paused.\nI could not do: do a barrel roll"


def test_work_steps_force_the_agent_runner_and_run_nothing_early(monkeypatch):
    steps = [TriageStep("command", "open spotify"), TriageStep("work", "email rahul")]
    (finished, force), ran = _apply(monkeypatch, steps, {})
    assert finished is None and force is True and ran == []


def test_mixed_tool_and_chat_plans_fall_through_unchanged(monkeypatch):
    (finished, force), ran = _apply(monkeypatch, [TriageStep("tool", "weather"), TriageStep("chat", "joke")], {})
    assert finished is None and force is False and ran == []


def test_no_plan_means_the_old_routing(monkeypatch):
    (finished, force), ran = _apply(monkeypatch, None, {})
    assert finished is None and force is False
