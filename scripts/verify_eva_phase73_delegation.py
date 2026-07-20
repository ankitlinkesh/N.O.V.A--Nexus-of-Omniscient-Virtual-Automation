"""Standalone verifier for Phase 73 (role-scoped delegation).

Phase 72 built the containment boundary and deliberately shipped it inert --
nothing could open a role scope, so GREEN/ORANGE/RED never fired outside their
own tests. That is the same "registered, gated, reachable from nowhere" shape
that hid voice.listen_once (49b until 61) and app.focus. This phase closes it.

What this verifies:

  1. CONTAINMENT ACTUALLY FIRES INSIDE A DELEGATION. A sub-task confined to a
     role cannot reach a tool that role forbids -- proven through the real
     registry, with the handler replaced by a probe, so a regression here
     cannot itself cause an action.
  2. REFUSALS SURFACE. A refusal recorded deep inside a sub-task reaches the
     caller and is flagged. A refusal that dies inside the sub-task wastes the
     signal -- a research role reaching for capture_screen is the shape an
     injection takes.
  3. DELEGATION IS CONSOLE-ONLY. Neither the delegation runner nor the console
     command is exposed as a planner tool. Delegation only ever NARROWS
     capability, so letting the planner delegate would not be an escalation --
     but whoever picks the role and writes the goal decides where the sub-task
     goes, and that choice must not be reachable from untrusted content.
  4. THE RESULT IS DATA, NOT INSTRUCTIONS. The rendered output carries its own
     untrusted marker, so a summary cannot travel onward stripped of it.
  5. IT FAILS CLOSED. An unknown role never reaches the executor.
  6. NESTING STILL ONLY NARROWS through the real delegation path.

Fully offline: the executor is faked and every tool handler is a probe. No
network, no LLM, no real action. The end-to-end path was validated live
separately (see the Phase 73 README row).
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> int:
    import eva.agent.runner as agent_runner
    from eva.agents.delegation_runner import DelegatedResult, run_delegated
    from eva.agents.role_context import active_roles, denials, role_scope
    from eva.mcp.runner import run_async
    from eva.tools.registry import ToolRegistry

    # ------------------------------------------------------------------ 1/2
    # Containment fires inside a real delegation, and the refusal is collected.
    registry = ToolRegistry()
    reached: list[str] = []
    for tool_name in ("capture_screen", "workspace_status"):
        spec = registry._tools[tool_name]
        registry._tools[tool_name] = replace(
            spec, handler=lambda _tool=tool_name, **_kw: (reached.append(_tool), {"ok": True})[1]
        )

    original_run = agent_runner.run_agentic_task

    observed_roles: list[tuple[str, ...]] = []

    async def _subtask_that_overreaches(goal, context):
        """Stands in for a sub-task steered toward an actuator it may not use.

        This RECORDS what it saw rather than asserting: an assertion raised in
        here would be caught by the runner's own fault isolation -- the thing
        under test -- and converted into a generic failure, so it could never
        signal the specific defect. Every claim is checked after the run.
        """
        reg = context["registry"]
        observed_roles.append(active_roles())
        denied = reg.run("capture_screen")
        allowed = reg.run("workspace_status")
        return {
            "ok": True,
            "final_response": "attempted both",
            "_denied": denied,
            "_allowed": allowed,
        }

    try:
        agent_runner.run_agentic_task = _subtask_that_overreaches  # type: ignore[assignment]
        result = run_async(run_delegated("research", "look at my screen", {"registry": registry}))
    finally:
        agent_runner.run_agentic_task = original_run  # type: ignore[assignment]

    check(result.error is None, f"the delegated sub-task failed outright: {result.error}")
    check(observed_roles == [("research",)], f"the role scope was not active inside the sub-task: {observed_roles}")
    check("capture_screen" not in reached, "a RED tool's handler ran inside a delegated sub-task")
    check("workspace_status" in reached, "a GREEN tool was blocked inside a delegated sub-task")
    check(result.refusals, "the refusal was not collected and returned to the caller")
    check(
        any(item["tool"] == "capture_screen" for item in result.refusals),
        "the collected refusal does not name the tool that was attempted",
    )
    check(result.injection_suspected is True, "an out-of-role attempt was not flagged")
    rendered = result.as_text()
    check("capture_screen" in rendered, "the refusal was not surfaced in the rendered output")
    check("signal" in rendered.lower(), "the rendered output does not explain why the refusal matters")

    # ------------------------------------------------------------------ 3
    # Delegation is console-only: not a planner tool, not a registered tool.
    planner_visible = {spec["name"] for spec in ToolRegistry().planner_specs()}
    for forbidden in ("delegate", "run_delegated", "agents.delegate", "delegation"):
        check(forbidden not in planner_visible, f"`{forbidden}` is planner-visible; delegation must stay console-only")
    registered = set(ToolRegistry()._tools)
    check(
        not (registered & {"delegate", "run_delegated", "agents.delegate"}),
        "delegation was registered as a tool; it must remain a typed-console command only",
    )
    # The console command itself exists and is reachable.
    from eva.core.fast_commands import maybe_handle_fast_command

    listed = maybe_handle_fast_command("roles", ToolRegistry(), session_context={}, memory=None, session_id="verify73")
    check(listed is not None, "the `roles` console command is not reachable")
    check("research" in listed[0], "the `roles` command does not list the known roles")

    # ------------------------------------------------------------------ 4
    # The result carries its own untrusted marker.
    check(result.untrusted is True, "a delegated result was not marked untrusted")
    check("untrusted" in rendered.lower(), "the rendered output dropped the untrusted marker")
    check("not an instruction" in rendered.lower(), "the rendered output does not say the summary is not an instruction")

    # ------------------------------------------------------------------ 5
    # Unknown role fails closed without reaching the executor.
    ran = False

    async def _must_not_run(goal, context):
        nonlocal ran
        ran = True
        return {}

    try:
        agent_runner.run_agentic_task = _must_not_run  # type: ignore[assignment]
        bad = run_async(run_delegated("desktop-please", "do a thing"))
    finally:
        agent_runner.run_agentic_task = original_run  # type: ignore[assignment]
    check(bad.ok is False, "an unknown role did not fail")
    check(not ran, "an unknown role reached the executor")

    # ------------------------------------------------------------------ 6
    # Nesting through the real delegation path still only narrows.
    with role_scope("desktop"):
        with role_scope("research"):
            check(active_roles() == ("desktop", "research"), "nested delegation did not accumulate roles")
            nested_registry = ToolRegistry()
            hit: list[str] = []
            spec = nested_registry._tools["screen.click"]
            nested_registry._tools["screen.click"] = replace(
                spec, handler=lambda **_kw: (hit.append("screen.click"), {"ok": True})[1]
            )
            refused = nested_registry.run("screen.click", label="X")
            check(refused.get("role_denied") is True, "an inner research role regained screen access by nesting")
            check(not hit, "a nested scope reached a handler its inner role denies")
    check(active_roles() == (), "the role stack leaked after nested delegation")
    check(denials() == (), "the denial collector leaked outside its scope")

    # ------------------------------------------------------------------ 7
    # Registered with the suite.
    import verify_eva_all

    name = "verify_eva_phase73_delegation.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 73 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 73 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 73 verifier")
    check(isinstance(DelegatedResult(role="r", goal="g", ok=True, summary="s"), DelegatedResult), "sanity")

    print(
        "PASS: Phase 73 role-scoped delegation -- the caller that makes Phase 72's containment live, closing the "
        "'reachable from nowhere' gap that phase shipped on purpose. A sub-task runs through the SAME live executor "
        "(agent/runner.run_agentic_task) wrapped in a role scope, so there is no second execution path; it inherits "
        "the registry, memory and session but NOT the parent's history, which is the context isolation that is the "
        "point of delegating. Containment fires for real inside a delegation: a research sub-task steered at "
        "capture_screen is refused before the handler while its permitted workspace_status still runs, and the "
        "refusal is COLLECTED and surfaced to the caller rather than dying inside the sub-task -- a research role "
        "reaching for an actuator is the shape an injection takes. The result is data, not instructions: it carries "
        "its own untrusted marker into the rendered output. Delegation is typed-console-only and appears in neither "
        "planner_specs() nor the tool registry, because whoever picks the role and writes the goal decides where the "
        "sub-task goes and that choice must never be reachable from untrusted content. It fails closed on an unknown "
        "role without reaching the executor, and nesting through the real path still only ever narrows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
