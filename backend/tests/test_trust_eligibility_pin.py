"""Executable spec for the trust-eligibility pin (Phase 78).

Phase 42 can de-escalate a ``confirm`` decision to ``allow`` for an action the
user has approved many times. Phase 55 can escalate friction when a call's
arguments point at a sensitive target. The two meet in ``registry.run``, where
Phase 55 runs first and is documented to "strictly dominate" — a risk-escalated
action must never be handed back to trust and auto-allowed.

That dominance is narrower than it looks, and this file pins the thing it
actually rests on. It is NOT true that escalation always moves a decision off
``confirm``: a sensitive-target READ (``SAFE_LOCAL_READ``, allow-class)
escalates ``allow -> confirm`` and lands exactly where de-escalation looks. The
only reason it is not then de-escalated back to ``allow`` is that the reading
types are absent from ``TRUST_ELIGIBLE_ACTION_TYPES``; the one type that IS
eligible (``MCP_TOOL_CALL``) escalates ``confirm -> override`` on a sensitive
target and so is never seen by the de-escalation branch.

If a future edit added a reading type to the allowlist, a risk-escalated read of
``~/.ssh`` could be trust-de-escalated straight back to ``allow`` — the exact
regression this pins against.
"""

from __future__ import annotations

from eva.permissions.risk_signals import (
    _MUTATING_ACTION_TYPES,
    _READING_ACTION_TYPES,
    _TARGET_ACTING_ACTION_TYPES,
    assess_friction,
)
from eva.permissions.trust_policy import (
    TRUST_ELIGIBLE_ACTION_TYPES,
    calibrate,
)

_SENSITIVE = {"path": "C:/Users/HP/.ssh/id_rsa"}


class TestMembershipIsPinned:
    def test_exact_membership(self) -> None:
        """The allowlist is exactly {MCP_TOOL_CALL}. Any addition must fail here
        and force whoever made it to re-argue Phase 55 dominance."""
        assert TRUST_ELIGIBLE_ACTION_TYPES == frozenset({"MCP_TOOL_CALL"})

    def test_no_reading_type_is_trust_eligible(self) -> None:
        """The load-bearing disjointness: a reading type escalates to confirm and
        would be re-de-escalatable if it were ever eligible."""
        assert TRUST_ELIGIBLE_ACTION_TYPES.isdisjoint(_READING_ACTION_TYPES)

    def test_no_target_acting_type_is_trust_eligible(self) -> None:
        """Stronger and simpler than strictly necessary: no type the risk layer
        reasons about (reading or mutating) is eligible, so no argument-aware
        escalation can ever be reached by de-escalation."""
        assert TRUST_ELIGIBLE_ACTION_TYPES.isdisjoint(_TARGET_ACTING_ACTION_TYPES)


class TestReadingTypeReallyLandsAtConfirm:
    """The premise of the pin: prove the 'off confirm already' comment WAS false,
    so the disjointness is doing real work rather than guarding a non-event."""

    def test_sensitive_read_escalates_allow_to_confirm(self) -> None:
        for reading in _READING_ACTION_TYPES:
            result = assess_friction(
                base_decision="allow",
                action_type=reading,
                args=_SENSITIVE,
            )
            # A reading floor is 'confirm'. For an allow-class read that means it
            # lands AT confirm -- exactly where de-escalation can see it.
            if result.escalated:
                assert result.decision in {"confirm", "override"}
                # SAFE_LOCAL_READ (allow-class) is the one that stops at confirm.
                if reading == "SAFE_LOCAL_READ":
                    assert result.decision == "confirm"


class TestEligibleTypeIsNeverReDeEscalated:
    """The dominance property, end to end, in the registry's order."""

    def test_eligible_type_escalates_off_confirm_on_sensitive_target(self) -> None:
        """Every trust-eligible type, escalated on a sensitive target, must leave
        'confirm' -- otherwise the Phase 42 block (`if decision == 'confirm'`)
        would still see it."""
        for eligible in TRUST_ELIGIBLE_ACTION_TYPES:
            result = assess_friction(
                base_decision="confirm",
                action_type=eligible,
                args=_SENSITIVE,
            )
            assert result.escalated, f"{eligible} did not escalate on a sensitive target"
            assert result.decision == "override", f"{eligible} did not move off confirm"

    def test_full_registry_ordering_keeps_a_risk_escalated_eligible_action_gated(self) -> None:
        """Reproduce registry.run: assess_friction, then (only if still 'confirm')
        calibrate with the flag on and abundant approvals. The escalated action
        must end at 'override', never 'allow'."""
        import os

        os.environ["EVA_TRUST_POLICIES_ENABLED"] = "1"
        try:
            for eligible in TRUST_ELIGIBLE_ACTION_TYPES:
                friction = assess_friction(base_decision="confirm", action_type=eligible, args=_SENSITIVE)
                decision = friction.decision if friction.escalated else "confirm"
                if decision == "confirm":
                    decision = calibrate(base_decision="confirm", action_type=eligible, approvals=999).decision
                assert decision == "override", f"{eligible} was de-escalated after a risk escalation"
        finally:
            os.environ.pop("EVA_TRUST_POLICIES_ENABLED", None)

    def test_the_regression_the_pin_prevents(self) -> None:
        """If a reading type WERE trust-eligible, its sensitive-target escalation
        (allow->confirm) would be de-escalated back to allow. We do not mutate the
        real allowlist; we demonstrate the mechanism directly so the danger is
        concrete: calibrate() with a reading type behaves as if eligible only
        because it checks membership, which is exactly what the pin guards."""
        import os

        os.environ["EVA_TRUST_POLICIES_ENABLED"] = "1"
        try:
            # SAFE_LOCAL_READ escalates allow->confirm on a sensitive target...
            friction = assess_friction(base_decision="allow", action_type="SAFE_LOCAL_READ", args=_SENSITIVE)
            assert friction.decision == "confirm"
            # ...and calibrate() refuses to de-escalate it *solely* because it is
            # not in the allowlist -- flip that and the read would go back to allow.
            still_gated = calibrate(base_decision="confirm", action_type="SAFE_LOCAL_READ", approvals=999)
            assert still_gated.decision == "confirm"
            assert still_gated.auto_allowed is False
        finally:
            os.environ.pop("EVA_TRUST_POLICIES_ENABLED", None)
