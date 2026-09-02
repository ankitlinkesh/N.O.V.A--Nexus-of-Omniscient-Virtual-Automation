"""Standalone verifier for Phase 51 (the auto-allow audit).

Two real bugs shipped with one root cause: **the safe-looking default is the
dangerous one**. Omit ``action_type`` on a ToolSpec and it silently becomes
``SAFE_LOCAL_READ`` = ALLOW-class, and nothing complains. That is how
``capture_screen`` ended up screenshotting the user with no confirmation while
the correctly-typed ``screen.observe`` sat gated and unreachable, and how
``desktop_observe`` ended up letting the model unlock pixel capture with a
caller-supplied flag. A permission gate whose default is "allow" fails open.

This verifier makes that class of bug impossible to introduce silently:

  1. NO UNAUDITED AUTO-ALLOW: every tool typed SAFE_LOCAL_READ must appear in
     the explicitly reviewed AUDITED_SAFE_LOCAL_READ list. A new tool that
     forgets action_type now FAILS THE BUILD instead of quietly becoming
     unguarded.
  2. Every action_type is a real ActionType (a typo would silently be
     unclassified, i.e. auto-allowed).
  3. NO ALLOW-CLASS TOOL HAS A PIXEL PATH — the Phase 50 regression, pinned:
     every screen-capturing tool is override-class and privileged (so the Phase
     40 injection defense covers it), and desktop_observe exposes no screen
     switch.
  4. Honest metadata: network tools say NETWORK_ACTION, local writes do not
     claim to be reads. Both are allow-class exactly as before, so this is
     truth-in-labelling, not a gate change.
  5. GATE-PRESERVING: the relabelling changed no tool's class. Pinned by exact
     counts so a future edit cannot quietly loosen the gate.
  6. The audited list means what it claims: nothing in it is a known-dangerous
     tool.

Fully offline: no network, no LLM, no execution.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


# The gate classes as they stand. Pinned so a future change that loosens the
# gate has to say so out loud rather than drift.
# Phase 62: confirm 7 -> 8 for the new "screen.submit_form" tool (fill+submit a
# form staged from the trusted console; confirm-class, SAFE_LOCAL_UI).
# Phase 70: four unrouted duplicate tools were deleted, so the totals fall by
# exactly four -- allow 84 -> 83 (`app.open`, SAFE_LOCAL_UI) and override
# 12 -> 9 (`app.close_request` SYSTEM_CHANGE, `file.read_text`
# PRIVACY_FILE_READ, `file.patch_text` DESTRUCTIVE_FILE_ACTION); confirm is
# unchanged. Deleting a tool only ever removes capability, and no surviving
# tool moved to a weaker class -- which is the direction this pin guards.
#
# Phase 74 added exactly one tool, `shell.run_bounded` (SYSTEM_CHANGE,
# safety_level dangerous), taking override 9 -> 10 with allow and confirm
# unchanged. The movement is toward MORE friction, the direction this pin
# allows; it guards against a surviving tool sliding into a weaker class.
# Phase 82 moved close_app from allow -> confirm (requires_confirmation=True):
# closing an app can discard unsaved work, so it now asks first. allow 83->82,
# confirm 8->9.
# Phase 91 added exactly one tool, `system_time` (SAFE_LOCAL_READ, listed in
# AUDITED_SAFE_LOCAL_READ's status group): it reads the system clock, touches no
# pixels, mutates nothing and reaches no network. allow 82 -> 83; override and
# confirm unchanged. This pin fired before it was updated, which is the point of
# having it.
EXPECTED_CLASS_COUNTS = {"allow": 83, "override": 10, "confirm": 9}

SCREEN_CAPTURE_TOOLS = ("capture_screen", "analyze_screen", "screen.observe")


def main() -> int:
    from backend.eva.agent.runner import _is_privileged_tool
    from backend.eva.security import tool_gate
    from backend.eva.security.action_audit import (
        AUDITED_SAFE_LOCAL_READ,
        LOCAL_WRITE_TOOLS,
        NETWORK_TOOLS,
        unaudited_safe_local_reads,
    )
    from backend.eva.security.action_types import ActionType
    from backend.eva.tools.registry import ToolRegistry
    from scripts import verify_eva_all

    registry = ToolRegistry()
    tools = registry._tools

    # 1. THE GUARD: no unaudited auto-allow.
    offenders = unaudited_safe_local_reads(tools)
    check(
        not offenders,
        "these tools are SAFE_LOCAL_READ (auto-allow) but nobody reviewed them — declare an honest "
        f"action_type or add them to AUDITED_SAFE_LOCAL_READ with a reason: {offenders}",
    )

    # 2. Every action_type is real. A typo is not a new class — it is auto-allow.
    valid = {t.value for t in ActionType}
    for name, spec in tools.items():
        check(spec.action_type in valid, f"{name} has action_type {spec.action_type!r}, which is not a real ActionType")

    # 3. NO ALLOW-CLASS TOOL HAS A PIXEL PATH (the Phase 50 regression).
    for name in SCREEN_CAPTURE_TOOLS:
        spec = registry.get(name)
        check(spec is not None, f"{name} must be registered")
        check(spec.action_type == "PRIVACY_SCREEN_READ", f"{name} grabs pixels; it must be a PRIVACY_SCREEN_READ")
        check(tool_gate.classify_tool_call(spec) == "override", f"{name} must be override-class")
        check(_is_privileged_tool(registry, name), f"{name} must be privileged so the injection defense escalates it")

    observe = registry.get("desktop_observe")
    props = set((observe.args_schema or {}).get("properties") or {})
    check("include_screen" not in props, "an allow-class tool must not expose a screen-capture switch")
    check("explicit_screen_intent" not in props, "a caller-supplied flag must never unlock screen capture")

    # 4. Honest metadata for network + local writes.
    for name in NETWORK_TOOLS:
        spec = registry.get(name)
        if spec is None:
            continue  # optional/flag-gated tool not registered in this profile
        check(
            spec.action_type in {"NETWORK_ACTION", "SAFE_LOCAL_UI", "EXTERNAL_POST"},
            f"{name} reaches the network; it must not claim to be a SAFE_LOCAL_READ (got {spec.action_type})",
        )
    for name in LOCAL_WRITE_TOOLS:
        spec = registry.get(name)
        if spec is None:
            continue
        check(spec.action_type != "SAFE_LOCAL_READ", f"{name} writes local state; it must not claim to be a read")

    # 5. GATE-PRESERVING: relabelling must not have changed any tool's class.
    counts: dict[str, int] = {}
    for spec in tools.values():
        cls = tool_gate.classify_tool_call(spec)
        counts[cls] = counts.get(cls, 0) + 1
    check(
        counts == EXPECTED_CLASS_COUNTS,
        f"gate class counts drifted: expected {EXPECTED_CLASS_COUNTS}, got {counts}. If this was deliberate, "
        "update EXPECTED_CLASS_COUNTS in this verifier and say why in the commit.",
    )

    # 6. The audited list must not launder something dangerous.
    for name in AUDITED_SAFE_LOCAL_READ:
        spec = registry.get(name)
        if spec is None:
            continue
        check(
            tool_gate.classify_tool_call(spec) == "allow",
            f"{name} is on the auto-allow audit list but classifies as {tool_gate.classify_tool_call(spec)!r}",
        )
        check(name not in SCREEN_CAPTURE_TOOLS, f"{name} captures pixels and must never be on the auto-allow list")

    # 7. Registration.
    verifier_name = "verify_eva_phase51_action_type_audit.py"
    check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 51 verifier")
    check(verifier_name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 51 verifier")
    check(verifier_name in getattr(verify_eva_all, "VERIFIER_DESCRIPTORS"), "master verifier descriptor missing the Phase 51 verifier")

    print(
        "PASS: Phase 51 auto-allow audit -- the dangerous default is now guarded. Every tool typed SAFE_LOCAL_READ "
        "(the value a ToolSpec inherits when its author forgets to declare one) must appear on an explicitly "
        "reviewed list, so a new tool that omits action_type FAILS THE BUILD instead of silently becoming "
        "auto-allowed -- the exact root cause behind both the capture_screen and desktop_observe bypasses. Every "
        "action_type is a real ActionType (a typo would also mean auto-allow); no allow-class tool has a pixel path "
        "and all three screen-capture tools are override-class AND privileged so taint-tracking escalates them; "
        "network tools and local writes no longer describe themselves as safe local reads; and the relabelling is "
        "PROVEN gate-preserving by exact class counts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
