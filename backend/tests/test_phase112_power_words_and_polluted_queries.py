"""Phase 112: bugs found by a routing sweep and by running the unregistered verifiers.

1. Power words matched as substrings in two routing layers: "turn off wifi" and
   "turn off dark mode" asked to SHUT DOWN the laptop, "restart spotify" to
   restart it, "sleep mode on my screen timer" to sleep it. It asked rather than
   acted, but a confirmation about the wrong thing is how a shutdown nobody asked
   for gets approved.
2. Phase 100's polluted-query bug, on routes 100 never covered: "google best
   laptops 2026 and open the first result" searched for that whole sentence, and
   "play lofi on spotify and turn the volume up" searched Spotify for "lofi on
   spotify and turn the volume up" and dropped the volume request.
3. "minimize all windows and lock the laptop" was one request, because "lock" was
   not a request word, so the one-shot planner did half of it.
4. "what do u know abt me" fell through to the LLM: Phase 91's exact phrase list
   dropped the shorthand.
"""

from __future__ import annotations

import pytest

from backend.eva.agent.executor import ToolExecutor, ToolExecutionResult
from backend.eva.agent.planner import ToolCallPlanner
from backend.eva.agent.policies import is_agentic_intent
from backend.eva.core.config import ModelSettings
from backend.eva.core.fast_commands import maybe_handle_fast_command
from backend.eva.core.intent_router import classify_capability_intent
from backend.eva.core.operator_commands import handle_operator_command
from backend.eva.core.power_intent import power_action_requested
from backend.eva.tools.registry import ToolRegistry

NOT_POWER = [
    "turn off wifi",
    "turn off dark mode",
    "turn off the lights",
    "turn off notifications",
    "restart spotify",
    "reboot the router",
    "sleep mode on my screen timer",
    "what time should i sleep",
    "sign out of gmail",
    "log out of instagram",
    "how do i shut down a process",
]

POWER = [
    ("shutdown", "shutdown"),
    ("shut down my laptop", "shutdown"),
    ("turn off the computer", "shutdown"),
    ("turn the laptop off", "shutdown"),
    ("please shut down now", "shutdown"),
    ("restart", "restart"),
    ("can you restart the computer please", "restart"),
    ("reboot the pc", "restart"),
    ("put the laptop to sleep", "sleep"),
    ("sleep", "sleep"),
    ("sign out", "sign_out"),
    ("log out of windows", "sign_out"),
]


class RefusingExecutor(ToolExecutor):
    def execute(self, call, *args, **kwargs):
        raise AssertionError(f"the operator layer tried to run {call.tool}")


def _operator(message: str):
    registry = ToolRegistry()
    return handle_operator_command(message, {"registry": registry, "executor": RefusingExecutor(registry), "session_context": {}})


@pytest.mark.parametrize("message", NOT_POWER)
def test_a_power_verb_aimed_at_something_else_is_not_a_power_action(message):
    assert power_action_requested(message) is None
    operator = None
    try:
        operator = _operator(message)
    except AssertionError:
        pass  # it routed to an ordinary tool, which is fine; it was not a power prompt
    assert operator is None or operator.get("tool") != "guarded_power_action", operator
    forced = ToolCallPlanner(ModelSettings(), ToolRegistry())._forced_decision(message)
    assert forced is None or forced.type != "confirmation_required", forced


@pytest.mark.parametrize(("message", "action"), POWER)
def test_a_real_power_request_still_asks_for_confirmation_in_both_layers(message, action):
    assert power_action_requested(message) == action
    operator = _operator(message)
    assert operator is not None and operator.get("tool") == "guarded_power_action"
    assert operator.get("args", {}).get("action") == action
    forced = ToolCallPlanner(ModelSettings(), ToolRegistry())._forced_decision(message)
    assert forced is not None and forced.type == "confirmation_required" and forced.action == action


def test_the_old_substring_table_is_gone():
    from backend.eva.core import operator_commands

    assert not hasattr(operator_commands, "POWER_ACTIONS")


# --- polluted queries -------------------------------------------------------------


class RecordingExecutor(ToolExecutor):
    def __init__(self, registry):
        super().__init__(registry)
        self.calls = []

    def execute(self, call, *args, **kwargs):
        self.calls.append((call.tool, dict(call.args)))
        return ToolExecutionResult(ok=True, tool=call.tool, result={"ok": True, "results": []})


@pytest.mark.parametrize(
    "message",
    [
        "google best laptops 2026 and open the first result",
        "look up the weather in delhi and open the first result",
        # "web" is not a request word, so this one is NOT caught by the agentic
        # decline earlier in the operator layer; only the search decline stops it.
        "web search cheap flights and open the first result",
    ],
)
def test_a_search_with_a_second_request_is_declined_not_polluted(message):
    registry = ToolRegistry()
    executor = RecordingExecutor(registry)
    assert handle_operator_command(message, {"registry": registry, "executor": executor, "session_context": {}}) is None
    assert executor.calls == []


def test_a_plain_search_still_runs():
    registry = ToolRegistry()
    executor = RecordingExecutor(registry)
    handle_operator_command("search for python tutorials", {"registry": registry, "executor": executor, "session_context": {}})
    assert executor.calls == [("web_search", {"query": "python tutorials"})]


@pytest.mark.parametrize(
    "message",
    ["play lofi on spotify and turn the volume up", "search spotify for drake and play the first song"],
)
def test_spotify_declines_a_query_that_carries_a_second_request(message):
    assert classify_capability_intent(message, {}).get("suggested_route") is None
    assert is_agentic_intent(message) is True


@pytest.mark.parametrize(
    ("message", "query"),
    [("play blinding lights on spotify", "blinding lights"), ("play lofi and chill beats", "lofi and chill beats"), ("open spotify and play starboy", "starboy")],
)
def test_ordinary_spotify_requests_still_play(message, query):
    result = classify_capability_intent(message, {})
    assert result.get("suggested_route") == "spotify_play_desktop"
    assert result.get("query") == query


@pytest.mark.parametrize("message", ["minimize all windows and lock the laptop", "google best laptops 2026 and open the first result"])
def test_two_requests_reach_the_agent_loop(message):
    assert is_agentic_intent(message) is True


@pytest.mark.parametrize("message", ["tell me about cats and dogs", "search for milk and eggs", "salt and pepper shakers", "search for copy and paste tutorials"])
def test_single_requests_stay_single(message):
    assert is_agentic_intent(message) is False


# --- about me -------------------------------------------------------------------------


def test_the_shorthand_about_me_question_uses_the_local_profile():
    result = maybe_handle_fast_command("what do u know abt me", ToolRegistry())
    assert result is not None and result[1] == "fast-command"
