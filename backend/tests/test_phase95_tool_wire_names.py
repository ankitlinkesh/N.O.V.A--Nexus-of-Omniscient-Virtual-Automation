"""Phase 95: Eva's own tool names made NVIDIA NIM reject every planner request.

Found immediately after Phase 92's model fix made NIM reachable at all. With a
live model configured, NIM answered a bare chat probe and still refused every
real planner call:

    Validation: Function at index 73 has an invalid name: "web.click".
    Only a-z, A-Z, 0-9, underscores, and dashes are allowed.   [HTTP 400]

25 registered tools are named with dots, and 7 are planner-visible once
Playwright is enabled. ONE of them in the payload makes the provider reject the
WHOLE request, so NIM could never plan -- every call silently fell through to
Gemini, which happens to tolerate dots. It stayed invisible because the retired
model returned 410 Gone *before* the payload was ever validated: fixing one bug
is what exposed the next.

The fix is a transport detail. The wire name is sanitized on the way out and
mapped back on the way in; the tool's real name never changes, and nothing
downstream of the planner sees a sanitized name.
"""

from __future__ import annotations

import re

import pytest

from backend.eva.llm.tool_schema import (
    ToolNameCollision,
    resolve_tool_name,
    sanitize_tool_name,
    to_openai_tools,
    wire_name_map,
)
from backend.eva.tools.registry import ToolRegistry


LEGAL = re.compile(r"^[A-Za-z0-9_-]+$")

SPECS = [
    {"name": "system_time", "description": "clock", "args_schema": {"type": "object"}},
    {"name": "web.click", "description": "click", "args_schema": {"type": "object"}},
    {"name": "screen.observe", "description": "observe", "args_schema": {"type": "object"}},
]


def test_the_payload_carries_only_provider_legal_names():
    """The exact rule NIM enforces, applied to EVERY registered tool.

    Deliberately not just `planner_specs()`: which tools are visible depends on
    EVA_V2_PLAYWRIGHT_ENABLED, and without it no dotted tool is visible, so a
    planner-only check passes trivially in CI while the operator's real payload
    is rejected. Checking the whole registry is what the operator actually hits.
    """
    registry = ToolRegistry()
    every_spec = [{"name": name} for name in registry._tools]
    assert [s["name"] for s in every_spec if "." in s["name"]], (
        "this test is pointless if no tool has a dot any more -- if the naming convention changed, "
        "retire the test rather than letting it pass vacuously"
    )
    tools = to_openai_tools(every_spec)
    illegal = [t["function"]["name"] for t in tools if not LEGAL.match(t["function"]["name"])]
    assert illegal == [], (
        "these names make NVIDIA NIM reject the ENTIRE request with HTTP 400, so the planner "
        "silently falls through to whichever provider tolerates dots: %r" % illegal
    )


def test_a_dotted_tool_becomes_an_underscore_on_the_wire():
    names = [t["function"]["name"] for t in to_openai_tools(SPECS)]
    assert names == ["system_time", "web_click", "screen_observe"]


def test_a_legal_name_is_left_alone():
    assert sanitize_tool_name("system_time") == "system_time"
    assert sanitize_tool_name("browser-open") == "browser-open"


def test_the_wire_name_resolves_back_to_the_real_tool():
    assert resolve_tool_name("web_click", SPECS) == "web.click"
    assert resolve_tool_name("screen_observe", SPECS) == "screen.observe"


def test_a_real_name_resolves_to_itself():
    """Providers that accept dots return what they were sent; both must work."""
    assert resolve_tool_name("web.click", SPECS) == "web.click"
    assert resolve_tool_name("system_time", SPECS) == "system_time"


def test_an_unknown_name_is_passed_through_not_invented():
    """The planner's whitelist check is what rejects it -- resolution must not guess."""
    assert resolve_tool_name("totally_made_up", SPECS) == "totally_made_up"


def test_the_real_registry_has_no_wire_name_collisions():
    """Two tools sharing a wire name would route a call to the WRONG tool."""
    registry = ToolRegistry()
    specs = [{"name": name} for name in registry._tools]
    mapping = wire_name_map(specs)
    assert len(mapping) == len(specs)


def test_a_collision_is_refused_rather_than_guessed():
    """The gate classifies whatever tool it is handed, so it cannot catch a misroute."""
    with pytest.raises(ToolNameCollision):
        wire_name_map([{"name": "web.click"}, {"name": "web_click"}])


def test_building_the_payload_refuses_a_colliding_set():
    with pytest.raises(ToolNameCollision):
        to_openai_tools([{"name": "a.b"}, {"name": "a_b"}])


# --------------------------------------------------------- ARRIVAL in the planner


def test_the_planner_turns_a_wire_name_back_into_a_real_tool_call():
    """The check the unit tests above do not make.

    Sanitizing the payload is only half the fix: if the returned `web_click` is
    not resolved BEFORE the whitelist check, the call fails `name in valid_names`
    and the planner reports no tool call at all -- the request would succeed and
    the tool would still never run.
    """
    import asyncio

    from backend.eva.agent import planner as planner_module
    from backend.eva.core.config import ModelSettings
    from backend.eva.llm.types import LLMResponse, RoutedLLMResponse

    # An INJECTED registry rather than the real one: whether a dotted tool is
    # planner-visible depends on EVA_V2_PLAYWRIGHT_ENABLED, which pytest does not
    # load, so the real registry made this test SKIP -- and a skipped test is not
    # evidence of anything.
    class _Registry:
        def planner_specs(self):
            return [
                {"name": "system_time", "description": "clock", "args_schema": {"type": "object", "properties": {}}},
                {"name": "web.click", "description": "click", "args_schema": {"type": "object", "properties": {}}},
            ]

    registry = _Registry()
    real = "web.click"
    wire = sanitize_tool_name(real)
    assert wire == "web_click"

    async def fake_complete(*args, **kwargs):
        return RoutedLLMResponse(
            response=LLMResponse(
                provider="nvidia_nim",
                model="test",
                ok=True,
                text="",
                tool_calls=[{"function": {"name": wire, "arguments": "{}"}}],
            ),
            attempts=[],
        )

    original = planner_module.complete_with_fallback
    planner_module.complete_with_fallback = fake_complete
    try:
        planner = planner_module.ToolCallPlanner(ModelSettings(), registry)
        decision = asyncio.run(planner._native_plan("do the thing", [], mode="single_turn", task_context={}))
    finally:
        planner_module.complete_with_fallback = original

    assert decision is not None, "a valid tool call came back and the planner reported nothing"
    assert [c.tool for c in decision.tool_calls] == [real], (
        "the wire name %r was not resolved back to %r, so the whitelist rejected a good call" % (wire, real)
    )
