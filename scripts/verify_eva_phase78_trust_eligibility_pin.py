"""Standalone verifier for Phase 78 (trust-eligibility pin + Phase 55 comment).

Two Phase-42/55 calibrations meet in ``registry.run``: Phase 55 escalates
friction from a call's arguments, then Phase 42 may de-escalate a ``confirm``
to ``allow`` for an often-approved action. The code and comments claim Phase 55
"strictly dominates" -- a risk-escalated action is never then auto-allowed. The
old comment justified that with "a risk-escalated action is off 'confirm'
already, so it is never reached", which is FALSE: a sensitive-target READ
(SAFE_LOCAL_READ, allow-class) escalates ``allow -> confirm`` and lands exactly
in the de-escalation branch.

The dominance is real, but it rests on a disjointness nothing pinned: the only
trust-eligible type (``MCP_TOOL_CALL``) escalates ``confirm -> override`` on a
sensitive target (off confirm), and the reading types that stop at ``confirm``
are absent from ``TRUST_ELIGIBLE_ACTION_TYPES``. This phase corrects the comment
to state the actual invariant and pins the allowlist so a future edit cannot
silently break it.

What this verifies:

  1. THE ALLOWLIST IS EXACTLY {MCP_TOOL_CALL}. Any addition fails, forcing the
     editor to re-argue dominance.
  2. IT IS DISJOINT FROM THE RISK LAYER'S TARGET-ACTING TYPES -- the property
     that actually makes dominance hold.
  3. THE PREMISE IS REAL: a sensitive-target SAFE_LOCAL_READ genuinely lands at
     ``confirm`` (the old comment was false), so the disjointness guards a live
     path, not a non-event.
  4. DOMINANCE END TO END: for every eligible type, assess_friction then
     calibrate (flag on, abundant approvals) ends at ``override``, never
     ``allow``.
  5. THE FALSE COMMENT IS GONE and the corrected invariant is stated in source.

Fully offline: pure functions only, no gate, no network.
"""

from __future__ import annotations

import sys
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
    import os

    from eva.permissions.risk_signals import (
        _READING_ACTION_TYPES,
        _TARGET_ACTING_ACTION_TYPES,
        assess_friction,
    )
    from eva.permissions.trust_policy import TRUST_ELIGIBLE_ACTION_TYPES, calibrate

    sensitive = {"path": "C:/Users/HP/.ssh/id_rsa"}

    # ------------------------------------------------------------------ 1
    check(
        TRUST_ELIGIBLE_ACTION_TYPES == frozenset({"MCP_TOOL_CALL"}),
        f"TRUST_ELIGIBLE_ACTION_TYPES changed to {sorted(TRUST_ELIGIBLE_ACTION_TYPES)}; "
        "re-argue Phase 55 dominance before touching this pin",
    )

    # ------------------------------------------------------------------ 2
    check(
        TRUST_ELIGIBLE_ACTION_TYPES.isdisjoint(_READING_ACTION_TYPES),
        "a reading type is trust-eligible -- a sensitive read could be de-escalated back to allow",
    )
    check(
        TRUST_ELIGIBLE_ACTION_TYPES.isdisjoint(_TARGET_ACTING_ACTION_TYPES),
        "a target-acting type is trust-eligible -- risk escalation could be undone by trust",
    )

    # ------------------------------------------------------------------ 3
    read = assess_friction(base_decision="allow", action_type="SAFE_LOCAL_READ", args=sensitive)
    check(read.escalated, "a sensitive-target SAFE_LOCAL_READ did not escalate at all")
    check(
        read.decision == "confirm",
        f"SAFE_LOCAL_READ landed at {read.decision!r}, not confirm -- the premise of the pin is wrong",
    )

    # ------------------------------------------------------------------ 4
    os.environ["EVA_TRUST_POLICIES_ENABLED"] = "1"
    try:
        for eligible in TRUST_ELIGIBLE_ACTION_TYPES:
            friction = assess_friction(base_decision="confirm", action_type=eligible, args=sensitive)
            check(friction.escalated, f"{eligible} did not escalate on a sensitive target")
            check(friction.decision == "override", f"{eligible} did not move off confirm to override")
            decision = friction.decision if friction.escalated else "confirm"
            if decision == "confirm":
                decision = calibrate(base_decision="confirm", action_type=eligible, approvals=999).decision
            check(decision == "override", f"{eligible} was de-escalated after a risk escalation")

        # And the regression the pin exists to prevent: a reading type, if it
        # were eligible, would be de-escalated -- shown via the mechanism, not by
        # mutating the real set. calibrate refuses SAFE_LOCAL_READ ONLY because
        # it is absent from the allowlist.
        gated = calibrate(base_decision="confirm", action_type="SAFE_LOCAL_READ", approvals=999)
        check(
            gated.decision == "confirm" and gated.auto_allowed is False,
            "SAFE_LOCAL_READ was auto-allowed -- the allowlist membership check is not what gates it",
        )
    finally:
        os.environ.pop("EVA_TRUST_POLICIES_ENABLED", None)

    # ------------------------------------------------------------------ 5
    registry_src = (BACKEND / "eva" / "tools" / "registry.py").read_text(encoding="utf-8")
    check(
        'is off "confirm" already, so it is never reached' not in registry_src,
        "the false 'off confirm already' comment is still present",
    )
    check(
        "TRUST_ELIGIBLE_ACTION_TYPES" in registry_src or "the real invariant" in registry_src,
        "registry.run no longer explains the real dominance invariant",
    )
    trust_src = (BACKEND / "eva" / "permissions" / "trust_policy.py").read_text(encoding="utf-8")
    check(
        "verify_eva_phase78" in trust_src,
        "trust_policy.py does not point at the pin that guards its allowlist",
    )

    # ------------------------------------------------------------------ 6
    import verify_eva_all

    name = "verify_eva_phase78_trust_eligibility_pin.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 78 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 78 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 78 verifier")

    print(
        "PASS: Phase 78 trust-eligibility pin. Phase 55's argument-aware escalation is documented to strictly dominate "
        "Phase 42's trust de-escalation, but the old justification ('a risk-escalated action is off confirm already') "
        "was false: a sensitive-target SAFE_LOCAL_READ escalates allow->confirm and lands in the de-escalation branch. "
        "Dominance actually rests on a disjointness -- the only trust-eligible type (MCP_TOOL_CALL) escalates "
        "confirm->override on a sensitive target, while the reading types that stop at confirm are absent from "
        "TRUST_ELIGIBLE_ACTION_TYPES. The comment is corrected to state that invariant, and the allowlist is now pinned "
        "to exactly {MCP_TOOL_CALL} and proven disjoint from the risk layer's target-acting types, with the end-to-end "
        "ordering shown to keep a risk-escalated eligible action at override, never allow. If a reading type were ever "
        "added, a risk-escalated read of ~/.ssh could be trust-de-escalated back to allow -- which this now fails on."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
