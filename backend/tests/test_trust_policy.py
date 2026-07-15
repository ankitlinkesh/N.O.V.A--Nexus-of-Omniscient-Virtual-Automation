"""Executable spec for Phase 42a's calibration primitives (backend/eva/permissions/trust_policy.py).

Phase 42a is done and MUST NOT be modified by this spec; it only imports and
drives ``calibrate``/``count_approvals`` to prove every branch of the contract:

  * Escalation (confidence-aware, adding friction) is unconditional -- it fires
    regardless of the trust-policies flag.
  * De-escalation ("approvals that scale", removing friction) is OFF by
    default, applies ONLY to the ``TRUST_ELIGIBLE_ACTION_TYPES`` allowlist, and
    ONLY once the approval count reaches ``approval_threshold()``.
  * override/hard_block base decisions are never de-escalated, no matter how
    many approvals exist.
  * ``count_approvals`` reads the pending-action ledger (JSONL) for the latest
    state per action id and counts confirmed/executed actions whose
    (tool, target) signature matches; it fails safe (returns 0) when the
    ledger path does not exist.

Fully offline and deterministic: a temp ledger path (env override) is used for
every ledger-touching test, never the real ledger, and all env vars this file
touches are restored automatically by ``monkeypatch``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.eva.permissions.ledger import confirm_pending_action, create_pending_action
from backend.eva.permissions.pending_actions import EvaPendingAction
from backend.eva.permissions.trust_policy import (
    TRUST_ELIGIBLE_ACTION_TYPES,
    approval_threshold,
    calibrate,
    count_approvals,
    low_confidence_threshold,
)


def _seed_approval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, tool: str, target: str) -> None:
    action = EvaPendingAction.new(
        action_type=tool,
        risk_level="medium",
        risk_category="MCP_TOOL_CALL",
        summary=f"{tool}: test approval",
        target=target,
        requires_confirmation=True,
        source="test",
        executor_available=True,
        executor_name=tool,
    )
    create_pending_action(action)
    confirm_pending_action(action.id)


def _use_temp_ledger(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EVA_PENDING_ACTION_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))


# ---------------------------------------------------------------------------
# calibrate(): trust de-escalation gated by the flag, eligibility, and count.
# ---------------------------------------------------------------------------


def test_flag_off_confirm_eligible_many_approvals_stays_confirm(monkeypatch):
    monkeypatch.delenv("EVA_TRUST_POLICIES_ENABLED", raising=False)

    decision = calibrate(base_decision="confirm", action_type="MCP_TOOL_CALL", approvals=999)

    assert decision.decision == "confirm"
    assert decision.auto_allowed is False
    assert decision.escalated is False


def test_flag_on_eligible_enough_approvals_de_escalates_to_allow(monkeypatch):
    monkeypatch.setenv("EVA_TRUST_POLICIES_ENABLED", "1")

    decision = calibrate(base_decision="confirm", action_type="MCP_TOOL_CALL", approvals=approval_threshold())

    assert decision.decision == "allow"
    assert decision.auto_allowed is True
    assert decision.escalated is False


def test_flag_on_eligible_not_enough_approvals_stays_confirm(monkeypatch):
    monkeypatch.setenv("EVA_TRUST_POLICIES_ENABLED", "1")

    decision = calibrate(base_decision="confirm", action_type="MCP_TOOL_CALL", approvals=approval_threshold() - 1)

    assert decision.decision == "confirm"
    assert decision.auto_allowed is False


def test_flag_on_non_eligible_action_type_never_de_escalates(monkeypatch):
    monkeypatch.setenv("EVA_TRUST_POLICIES_ENABLED", "1")
    assert "EXTERNAL_POST" not in TRUST_ELIGIBLE_ACTION_TYPES

    decision = calibrate(base_decision="confirm", action_type="EXTERNAL_POST", approvals=999)

    assert decision.decision == "confirm"
    assert decision.auto_allowed is False


@pytest.mark.parametrize("base", ["override", "hard_block"])
def test_override_and_hard_block_never_de_escalated(monkeypatch, base):
    monkeypatch.setenv("EVA_TRUST_POLICIES_ENABLED", "1")

    decision = calibrate(base_decision=base, action_type="MCP_TOOL_CALL", approvals=999)

    assert decision.decision == base
    assert decision.auto_allowed is False


# ---------------------------------------------------------------------------
# calibrate(): confidence-aware escalation, unconditional.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flag", [None, "0", "1"])
def test_low_confidence_always_escalates_allow_to_confirm(monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv("EVA_TRUST_POLICIES_ENABLED", raising=False)
    else:
        monkeypatch.setenv("EVA_TRUST_POLICIES_ENABLED", flag)

    threshold = low_confidence_threshold()
    decision = calibrate(base_decision="allow", action_type="x", confidence=threshold - 0.01)

    assert decision.decision == "confirm"
    assert decision.escalated is True
    assert decision.auto_allowed is False


def test_confidence_at_or_above_threshold_does_not_escalate(monkeypatch):
    monkeypatch.delenv("EVA_TRUST_POLICIES_ENABLED", raising=False)
    threshold = low_confidence_threshold()

    decision = calibrate(base_decision="allow", action_type="x", confidence=threshold)

    assert decision.decision == "allow"
    assert decision.escalated is False


def test_confidence_none_never_escalates(monkeypatch):
    decision = calibrate(base_decision="allow", action_type="x", confidence=None)

    assert decision.decision == "allow"
    assert decision.escalated is False


def test_escalation_wins_over_trust_de_escalation():
    # A confirm decision with low confidence has no allow-de-escalation path to
    # begin with (de-escalation only applies to base_decision=="confirm" and
    # escalation only applies to base_decision=="allow"), so this proves the
    # two rules never fight over the same base decision -- escalation always
    # gets first refusal on "allow".
    threshold = low_confidence_threshold()
    decision = calibrate(base_decision="allow", action_type="MCP_TOOL_CALL", approvals=999, confidence=threshold - 0.1)
    assert decision.decision == "confirm"
    assert decision.escalated is True
    assert decision.auto_allowed is False


# ---------------------------------------------------------------------------
# env overrides
# ---------------------------------------------------------------------------


def test_approval_threshold_env_override(monkeypatch):
    monkeypatch.setenv("EVA_TRUST_APPROVAL_THRESHOLD", "7")
    assert approval_threshold() == 7


def test_approval_threshold_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("EVA_TRUST_APPROVAL_THRESHOLD", "not-a-number")
    assert approval_threshold() == 3


def test_approval_threshold_below_one_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("EVA_TRUST_APPROVAL_THRESHOLD", "0")
    assert approval_threshold() == 3


def test_low_confidence_threshold_env_override(monkeypatch):
    monkeypatch.setenv("EVA_LOW_CONFIDENCE_THRESHOLD", "0.75")
    assert low_confidence_threshold() == 0.75


def test_low_confidence_threshold_out_of_range_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("EVA_LOW_CONFIDENCE_THRESHOLD", "1.5")
    assert low_confidence_threshold() == 0.4


# ---------------------------------------------------------------------------
# count_approvals(): reads the pending-action ledger.
# ---------------------------------------------------------------------------


def test_count_approvals_counts_seeded_confirmed_actions(monkeypatch, tmp_path):
    _use_temp_ledger(monkeypatch, tmp_path)
    for _ in range(3):
        _seed_approval(monkeypatch, tmp_path, tool="mcp.some_tool", target="widget-1")

    assert count_approvals("mcp.some_tool", "widget-1") == 3


def test_count_approvals_is_zero_for_a_different_target(monkeypatch, tmp_path):
    _use_temp_ledger(monkeypatch, tmp_path)
    _seed_approval(monkeypatch, tmp_path, tool="mcp.some_tool", target="widget-1")

    assert count_approvals("mcp.some_tool", "widget-2") == 0


def test_count_approvals_is_zero_for_a_different_tool(monkeypatch, tmp_path):
    _use_temp_ledger(monkeypatch, tmp_path)
    _seed_approval(monkeypatch, tmp_path, tool="mcp.some_tool", target="widget-1")

    assert count_approvals("mcp.other_tool", "widget-1") == 0


def test_count_approvals_fail_safe_when_ledger_path_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("EVA_PENDING_ACTION_LEDGER_PATH", str(tmp_path / "does_not_exist" / "ledger.jsonl"))

    assert count_approvals("mcp.some_tool", "widget-1") == 0
