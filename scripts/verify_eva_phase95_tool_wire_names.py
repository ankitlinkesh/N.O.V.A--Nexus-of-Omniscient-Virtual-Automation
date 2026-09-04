"""Standalone verifier for Phase 95 (Eva's tool names made NIM reject every plan).

Found within minutes of Phase 92's model fix making NVIDIA NIM reachable at all.
With a live model configured, NIM answered a bare chat probe and still refused
every real planner call:

    Validation: Function at index 73 has an invalid name: "web.click".
    Only a-z, A-Z, 0-9, underscores, and dashes are allowed.   [HTTP 400]

25 registered tools are named with dots, and 7 of those are planner-visible once
Playwright is enabled. ONE illegal name makes the provider reject the WHOLE
request, so NIM could never serve a planner call -- every request silently fell
through to Gemini, which happens to tolerate dots. It stayed invisible for as
long as it did because the configured NIM model was returning 410 Gone *before*
the payload was ever validated: fixing one bug is what exposed the next, and the
"NIM is primary" belief was wrong in a way no green suite could show.

The fix is a transport detail, not a rename. The wire name is sanitized on the
way out and mapped back on the way in; the tool's real name never changes and
nothing downstream of the planner sees a sanitized name.

Two properties carry the safety:

  * **A collision is refused, never guessed.** Two tools sharing a wire name
    would route a call for one tool to a DIFFERENT tool, and the permission gate
    could not catch it -- the gate classifies whatever tool it is handed. There
    are no collisions across the 25 dotted names today, so `wire_name_map` raises
    rather than picking a winner, and a future tool named into a collision breaks
    the build instead of misrouting a call.
  * **Resolution happens BEFORE the whitelist check.** Sanitizing the payload is
    only half the fix: an unresolved `web_click` fails `name in valid_names`, so
    the request would succeed and the tool would still never run.

Fully offline: no network, no LLM, no provider.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


LEGAL = re.compile(r"^[A-Za-z0-9_-]+$")


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> int:
    from eva.agent import planner as planner_module
    from eva.core.config import ModelSettings
    from eva.llm.tool_schema import (
        ToolNameCollision,
        resolve_tool_name,
        sanitize_tool_name,
        to_openai_tools,
        wire_name_map,
    )
    from eva.llm.types import LLMResponse, RoutedLLMResponse
    from eva.tools.registry import ToolRegistry

    registry = ToolRegistry()

    # ---------------------------------------------- every name must be legal
    # Deliberately the WHOLE registry, not planner_specs(): which tools are
    # visible depends on EVA_V2_PLAYWRIGHT_ENABLED, so a planner-only check
    # passes vacuously wherever that flag is off while the operator's real
    # payload is still rejected.
    every = [{"name": name} for name in registry._tools]
    dotted = [s["name"] for s in every if "." in s["name"]]
    check(
        dotted,
        "no registered tool has a dot any more -- if the naming convention changed, retire this verifier "
        "rather than letting it pass vacuously",
    )
    illegal = [t["function"]["name"] for t in to_openai_tools(every) if not LEGAL.match(t["function"]["name"])]
    check(
        illegal == [],
        "REGRESSION: %r would be sent as function names. ONE illegal name makes NVIDIA NIM reject the ENTIRE "
        "request with HTTP 400, so the planner cannot use NIM at all and silently falls through to whichever "
        "provider tolerates dots." % illegal,
    )

    check(sanitize_tool_name("web.click") == "web_click", "a dot must become an underscore on the wire")
    check(sanitize_tool_name("system_time") == "system_time", "a legal name must be left alone")
    check(sanitize_tool_name("browser-open") == "browser-open", "dashes are legal and must survive")

    # ------------------------------------------------------- round tripping
    specs = [{"name": "system_time"}, {"name": "web.click"}, {"name": "screen.observe"}]
    check(resolve_tool_name("web_click", specs) == "web.click", "the wire name must resolve back")
    check(resolve_tool_name("screen_observe", specs) == "screen.observe", "the wire name must resolve back")
    check(
        resolve_tool_name("web.click", specs) == "web.click",
        "a provider that accepted the dots returns the real name; that must still resolve to itself",
    )
    check(
        resolve_tool_name("totally_made_up", specs) == "totally_made_up",
        "an unknown name must pass through unchanged -- the planner's whitelist is what rejects it, and "
        "inventing a resolution here would route a hallucinated call to a real tool",
    )

    # ------------------------------------------------ collisions are refused
    check(len(wire_name_map(every)) == len(every), "the real registry must have no wire-name collisions")
    for colliding in ([{"name": "web.click"}, {"name": "web_click"}], [{"name": "a.b"}, {"name": "a_b"}]):
        try:
            wire_name_map(colliding)
        except ToolNameCollision:
            pass
        else:
            raise AssertionError(
                "REGRESSION: two tools mapping to one wire name is accepted. That silently routes a call for "
                "one tool to a DIFFERENT tool, which the permission gate cannot catch -- it classifies whatever "
                "tool it is handed. Refusing is the only safe answer."
            )
    try:
        to_openai_tools([{"name": "a.b"}, {"name": "a_b"}])
    except ToolNameCollision:
        pass
    else:
        raise AssertionError("building a payload from a colliding set must refuse before anything is sent")

    # --------------------------- ARRIVAL: resolution must precede the whitelist
    class _Registry:
        def planner_specs(self):
            return [
                {"name": "system_time", "description": "clock", "args_schema": {"type": "object", "properties": {}}},
                {"name": "web.click", "description": "click", "args_schema": {"type": "object", "properties": {}}},
            ]

    async def fake_complete(*args, **kwargs):
        return RoutedLLMResponse(
            response=LLMResponse(
                provider="nvidia_nim",
                model="test",
                ok=True,
                text="",
                tool_calls=[{"function": {"name": "web_click", "arguments": "{}"}}],
            ),
            attempts=[],
        )

    original = planner_module.complete_with_fallback
    planner_module.complete_with_fallback = fake_complete
    try:
        planner = planner_module.ToolCallPlanner(ModelSettings(), _Registry())
        decision = asyncio.run(planner._native_plan("do it", [], mode="single_turn", task_context={}))
    finally:
        planner_module.complete_with_fallback = original

    check(
        decision is not None and [c.tool for c in decision.tool_calls] == ["web.click"],
        "THE HALF THAT IS EASY TO MISS: a returned wire name must be resolved BEFORE the whitelist check. "
        "Unresolved, `web_click` fails `name in valid_names`, the planner reports no tool call, and the "
        "request succeeds while the tool never runs -- sanitizing the payload alone fixes nothing.",
    )

    # ---------------------------------------------------------- registration
    import verify_eva_all

    name = "verify_eva_phase95_tool_wire_names.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 95 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 95 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 95 verifier")

    print(
        "PASS: Phase 95 tool wire names. Eva names 25 tools with dots, and one of them in the payload made "
        "NVIDIA NIM reject the ENTIRE planner request with HTTP 400 -- so NIM could never plan and every call "
        "silently fell through to Gemini, hidden until Phase 92's model fix made NIM reachable enough to fail "
        "this way. Function names are now provider-legal on the wire and resolved back before the whitelist "
        "check, a wire-name collision is refused rather than guessed, and an unknown name passes through "
        "untouched so the whitelist stays the thing that rejects it."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
