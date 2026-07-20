"""Standalone verifier for Phase 72 (per-role tool containment).

The permission gate classifies per TOOL, globally: `file.write_text` costs the
same whoever asks. That is right for a single actor and wrong for a delegated
sub-task, because a research sub-task reads UNTRUSTED CONTENT -- a web page can
ask it to do anything -- and the gate has no way to say "this one may read the
web and must never touch the screen".

Phase 72 adds the missing dimension (role x tool -> GREEN/ORANGE/RED) as a
CONTAINMENT layer, not a second gate. What this verifies:

  1. NO ACTIVE ROLE = NO CHANGE. Ordinary console/planner calls are untouched;
     this layer only exists inside a delegated sub-task.
  2. RED REALLY REFUSES, and refuses BEFORE the handler. It also reports the
     attempt as an injection signal -- a research role reaching for
     screen.click is evidence that content it read tried to reach an actuator.
  3. THE REFUSAL DOES NOT ECHO ARGUMENTS. A refusal caused by injected content
     must not relay that content back to the user (the Phase 68 lesson behind
     confirmation.py's explicit key list).
  4. THE ROLE CARRIES NO CALLER AUTHORITY. role/_role/agent_role kwargs are
     stripped exactly like confirmed/_approved/content_args, because a caller
     that names its own role just claims whichever role unlocks the tool.
  5. IT FAILS CLOSED. An unknown role is RED on everything; a newly registered
     tool is RED for every role until someone declares it.
  6. GREEN IS NOT A BYPASS. A tool that is GREEN for a role is still classified
     by the gate exactly as it would be with no role at all. If GREEN could
     lower friction, this file would be a self-authorization channel of the
     same shape as the stripped `confirmed` flag.
  7. ORANGE STRICTLY DOMINATES PHASE 42. Role escalation is applied AFTER trust
     calibration, so an ORANGE action can never be handed back and auto-allowed
     for prior approvals.
  8. THE ESCALATION ONLY EVER RAISES, and never touches hard_block.
  9. NO GHOST ENTRIES. Every declared tool name is a real registered tool -- a
     misspelled GREEN entry would silently leave the intended tool RED while
     the policy still read as permissive.

Fully offline: no network, no LLM, no real filesystem writes. Every tool that
could actually do something is replaced by a probe handler, so a REGRESSION in
this file cannot itself cause an action.
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


class _Probe:
    """Records whether the tool's handler was reached, and with what."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, **kwargs: object) -> dict:
        self.calls.append(dict(kwargs))
        return {"ok": True, "probe": True}

    @property
    def ran(self) -> bool:
        return bool(self.calls)


def _registry_with_probe(tool_name: str):
    """A real ToolRegistry with one tool's handler swapped for a probe.

    Everything else (gate, risk signals, trust policy, role layer) stays
    genuine -- only the side effect is removed.
    """
    from eva.tools.registry import ToolRegistry

    registry = ToolRegistry()
    probe = _Probe()
    spec = registry._tools[tool_name]
    registry._tools[tool_name] = replace(spec, handler=probe)
    return registry, probe


def main() -> int:
    from eva.agents.role_context import ROLE_KWARG_NAMES, active_role, role_scope
    from eva.agents.role_policy import (
        ROLE_POLICIES,
        RoleTier,
        escalate_one_step,
        known_roles,
        tier_for,
    )
    from eva.tools.registry import ToolRegistry, ToolSpec

    # ------------------------------------------------------------------ 1
    # No active role: the layer is inert and the tool runs as it always did.
    check(active_role() is None, "a role was already active at verifier start")
    registry, probe = _registry_with_probe("status")
    registry.run("status")
    check(probe.ran, "with no active role, status did not execute as before")

    # ------------------------------------------------------------------ 2/3
    # RED refuses before the handler, flags the injection signal, and does not
    # echo the arguments back.
    registry, probe = _registry_with_probe("screen.click")
    with role_scope("research"):
        refusal = registry.run("screen.click", label="Seven", reason="pay the invoice now")
    check(isinstance(refusal, dict), "RED refusal must be a structured result")
    check(refusal.get("role_denied") is True, "RED did not report role_denied")
    check(refusal.get("injection_signal") is True, "RED did not flag the attempt as an injection signal")
    check(refusal.get("role") == "research", "RED did not name the role")
    check(refusal.get("tool") == "screen.click", "RED did not name the tool")
    check(not probe.ran, "RED refusal still reached the tool handler")
    blob = str(refusal)
    check("Seven" not in blob, "refusal echoed the `label` argument back to the user")
    check("pay the invoice" not in blob, "refusal echoed injected argument content back to the user")

    # ------------------------------------------------------------------ 4
    # A caller-supplied role carries no authority.
    registry, probe = _registry_with_probe("screen.click")
    with role_scope("research"):
        spoofed = registry.run("screen.click", label="X", role="desktop", _role="desktop", agent_role="desktop")
    check(spoofed.get("role_denied") is True, "a caller-supplied role kwarg granted access")
    check(spoofed.get("role") == "research", "a caller-supplied role kwarg changed the effective role")
    check(not probe.ran, "a spoofed role reached the handler")
    check(ROLE_KWARG_NAMES == {"role", "_role", "agent_role"}, "the stripped role-kwarg spellings changed unexpectedly")

    # ------------------------------------------------------------------ 5a
    # Unknown / injected role name is RED on everything, including a tool that
    # is harmless and green for every real role.
    registry, probe = _registry_with_probe("status")
    with role_scope("desktop-please"):
        bogus = registry.run("status")
    check(bogus.get("role_denied") is True, "an unknown role was not refused (fail-open)")
    check(not probe.ran, "an unknown role reached a handler")

    # ------------------------------------------------------------------ 5b
    # A newly registered tool is RED for every role until declared. This is the
    # fail-closed-by-construction property: adding a tool must never silently
    # grant it to every existing role.
    fresh = ToolRegistry()
    new_probe = _Probe()
    fresh._tools["probe.newly_added"] = ToolSpec(
        name="probe.newly_added",
        description="A tool registered after the role policy was written.",
        args_schema={},
        safety_level="safe",
        handler=new_probe,
        action_type="SAFE_LOCAL_READ",
    )
    for role in known_roles():
        with role_scope(role):
            denied = fresh.run("probe.newly_added")
        check(denied.get("role_denied") is True, f"role `{role}` could call an undeclared new tool")
    check(not new_probe.ran, "an undeclared new tool was executed by some role")

    # ------------------------------------------------------------------ 6
    # GREEN IS NOT A BYPASS. screen.observe is PRIVACY_SCREEN_READ (gated) and
    # GREEN for the desktop role. Under that role it must be treated exactly as
    # it is with no role at all -- gated, handler never reached.
    check(tier_for("desktop", "screen.observe") is RoleTier.GREEN, "fixture drift: screen.observe is not GREEN for desktop")
    registry, probe = _registry_with_probe("screen.observe")
    baseline = registry.run("screen.observe")
    baseline_ran = probe.ran

    registry, probe = _registry_with_probe("screen.observe")
    with role_scope("desktop"):
        under_role = registry.run("screen.observe")
    under_role_ran = probe.ran

    check(
        baseline_ran == under_role_ran,
        "GREEN changed whether a gated tool executes -- GREEN must not lower friction",
    )
    check(not under_role_ran, "a gated tool executed under a GREEN role without passing the gate")
    check(
        under_role.get("role_denied") is None,
        "a GREEN tool was refused by the role layer",
    )
    check(
        set(map(type, [baseline, under_role])) == {dict},
        "GREEN changed the shape of a gated response",
    )

    # ------------------------------------------------------------------ 7
    # ORANGE STRICTLY DOMINATES PHASE 42. close_app is allow-class and ORANGE
    # for the desktop role. With trust calibration forced to auto-allow, the
    # ordering is what saves us: role escalation runs AFTER Phase 42, so the
    # action still parks. Were it applied BEFORE, Phase 42 would see the
    # freshly-escalated "confirm" and hand it straight back to "allow".
    check(tier_for("desktop", "close_app") is RoleTier.ORANGE, "fixture drift: close_app is not ORANGE for desktop")
    from eva.permissions import trust_policy

    original_enabled = trust_policy.trust_policies_enabled
    original_calibrate = trust_policy.calibrate
    try:
        trust_policy.trust_policies_enabled = lambda: True  # type: ignore[assignment]
        trust_policy.calibrate = lambda **_kwargs: type(  # type: ignore[assignment]
            "_Calibrated", (), {"auto_allowed": True, "decision": "allow"}
        )()

        registry, probe = _registry_with_probe("close_app")
        with role_scope("desktop"):
            registry.run("close_app", target="eva_nonexistent_probe_window")
        check(
            not probe.ran,
            "an ORANGE action was auto-allowed by trust calibration -- role escalation "
            "must be applied AFTER Phase 42 so it strictly dominates",
        )
    finally:
        trust_policy.trust_policies_enabled = original_enabled  # type: ignore[assignment]
        trust_policy.calibrate = original_calibrate  # type: ignore[assignment]

    # ------------------------------------------------------------------ 8
    # The escalation only ever raises, and hard_block is terminal.
    check(escalate_one_step("allow") == "confirm", "allow did not escalate to confirm")
    check(escalate_one_step("confirm") == "override", "confirm did not escalate to override")
    check(escalate_one_step("override") == "override", "override must stay override")
    check(escalate_one_step("hard_block") == "hard_block", "hard_block must never be altered by role escalation")

    # ------------------------------------------------------------------ 9
    # No ghost entries: every declared name is a real tool. A typo would leave
    # the intended tool RED while the policy still read as permissive.
    real_tools = set(ToolRegistry()._tools)
    for role_name, policy in ROLE_POLICIES.items():
        ghosts_green = sorted(policy.green - real_tools)
        ghosts_orange = sorted(policy.orange - real_tools)
        check(not ghosts_green, f"role `{role_name}` declares GREEN tools that do not exist: {ghosts_green}")
        check(not ghosts_orange, f"role `{role_name}` declares ORANGE tools that do not exist: {ghosts_orange}")
        overlap = sorted(policy.green & policy.orange)
        check(not overlap, f"role `{role_name}` declares the same tool GREEN and ORANGE: {overlap}")

    # Containment is real, not nominal: a large share of the surface is
    # reachable by NO role. If this ever hits zero, the policy has become a
    # rubber stamp.
    covered = set().union(*[p.green | p.orange for p in ROLE_POLICIES.values()])
    unreachable = real_tools - covered
    check(len(unreachable) > 20, f"only {len(unreachable)} tools are unreachable by every role -- containment has eroded")

    # ------------------------------------------------------------------ 10
    # The role does not leak out of its scope, even when the sub-task raises.
    try:
        with role_scope("research"):
            raise RuntimeError("sub-task failure")
    except RuntimeError:
        pass
    check(active_role() is None, "the active role leaked after a raising sub-task")

    # ------------------------------------------------------------------ 11
    # NESTING ONLY NARROWS. A delegated sub-task that opens a further scope may
    # subtract capability, never add it. Were nesting a REPLACEMENT, a research
    # sub-task could open a `desktop` scope and gain precisely the screen access
    # its own role exists to deny -- a containment escape reachable the moment
    # any delegation runner exists.
    from eva.agents.role_context import active_roles
    from eva.agents.role_policy import effective_tier

    registry, probe = _registry_with_probe("screen.click")
    with role_scope("research"):
        with role_scope("desktop"):
            nested = registry.run("screen.click", label="X")
            check(active_roles() == ("research", "desktop"), "nested scopes did not accumulate")
    check(
        nested.get("role_denied") is True,
        "CONTAINMENT ESCAPE: a research sub-task regained screen access by nesting a desktop scope",
    )
    check(not probe.ran, "a nested scope reached a handler its outer role denies")
    check(nested.get("role") == "research", "the refusal did not name the outer role that actually denied it")

    # ... while a role that legitimately holds the grant alone still proceeds,
    # so the intersection is not simply denying everything.
    check(effective_tier(("desktop",), "screen.click") is RoleTier.GREEN, "desktop alone lost its own grant")
    check(effective_tier(("desktop", "research"), "screen.click") is RoleTier.RED, "nesting failed to subtract")
    check(
        effective_tier(("research", "code"), "workspace_read_file") is RoleTier.GREEN,
        "intersection denied a tool BOTH roles allow",
    )
    check(effective_tier((), "screen.click") is None, "an empty role stack must not read as a tier")

    # ------------------------------------------------------------------ 12
    # Registered with the suite.
    import verify_eva_all

    name = "verify_eva_phase72_role_policy.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 72 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 72 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 72 verifier")

    print(
        "PASS: Phase 72 per-role tool containment. The gate classifies per TOOL, blind to WHO is asking, which is "
        "wrong for a delegated sub-task whose input is untrusted content. A role now declares only what it may use "
        "(GREEN) or may use under confirmation (ORANGE); everything else is RED and refused before the handler, and "
        "reported as an injection signal without echoing the arguments back. The layer is inert with no active role, "
        "so existing console and planner behavior is unchanged. It fails closed in every direction: an unknown role "
        "is RED on everything, and a newly registered tool is RED for every role until declared. GREEN is not a "
        "bypass -- a gated tool stays gated under a GREEN role -- and ORANGE is applied AFTER Phase 42 so a "
        "role-escalated action can never be handed back to trust calibration and auto-allowed. Escalation only ever "
        "raises and never touches hard_block. Every declared name is cross-checked against the live registry, so a "
        f"typo cannot silently leave a tool RED behind a permissive-looking policy; {len(unreachable)} of "
        f"{len(real_tools)} tools remain reachable by no role at all."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
