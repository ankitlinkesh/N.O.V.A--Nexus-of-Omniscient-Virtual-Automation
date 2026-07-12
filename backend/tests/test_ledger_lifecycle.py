"""Lifecycle tests for the pending-action ledger.

The ledger is the trust anchor for the whole permission gate: it decides
whether a confirmed/override action may proceed. conftest.py redirects the
ledger path to a tmp file, so these exercise real create/confirm/expire/cancel
transitions without touching the project ledger.
"""
from __future__ import annotations

from backend.eva.permissions import ledger as ledger_module
from backend.eva.permissions.ledger import (
    cancel_pending_action,
    confirm_pending_action,
    create_pending_action,
    get_pending_action,
)
from backend.eva.permissions.pending_actions import EvaPendingAction


def _new(*, requires_override: bool) -> EvaPendingAction:
    action = EvaPendingAction.new(
        action_type="file.delete" if requires_override else "message.send",
        risk_level="high" if requires_override else "medium",
        risk_category="destructive_file_action" if requires_override else "external_message",
        summary="test action",
        requires_override=requires_override,
        requires_confirmation=not requires_override,
        executor_available=True,
    )
    create_pending_action(action)
    return action


def test_create_then_get_roundtrips():
    action = _new(requires_override=True)
    fetched = get_pending_action(action.id)
    assert fetched is not None
    assert fetched.status == "pending_override"
    assert fetched.requires_override is True


def test_override_action_rejects_plain_confirm():
    action = _new(requires_override=True)
    result = confirm_pending_action(action.id, override=False)
    assert result.success is False
    assert get_pending_action(action.id).status == "pending_override", "must stay pending after a wrong-form confirm"


def test_override_action_accepts_override_confirm():
    action = _new(requires_override=True)
    result = confirm_pending_action(action.id, override=True)
    assert result.success is True
    assert get_pending_action(action.id).status == "confirmed"


def test_confirm_action_rejects_override_form():
    action = _new(requires_override=False)
    result = confirm_pending_action(action.id, override=True)
    assert result.success is False, "a confirm-class action must not accept the override form"


def test_double_confirm_is_rejected():
    action = _new(requires_override=True)
    assert confirm_pending_action(action.id, override=True).success is True
    second = confirm_pending_action(action.id, override=True)
    assert second.success is False, "an already-confirmed action cannot be re-confirmed"


def test_cancel_then_confirm_is_rejected():
    action = _new(requires_override=True)
    assert cancel_pending_action(action.id).success is True
    assert get_pending_action(action.id).status == "cancelled"
    assert confirm_pending_action(action.id, override=True).success is False


def test_expired_action_cannot_be_confirmed():
    action = _new(requires_override=True)
    # Force expiry by rewriting the ledger entry with a past expiry.
    action.expires_at = "2000-01-01T00:00:00+00:00"
    ledger_module._append(action, note="test_forced_expiry")
    fetched = get_pending_action(action.id)
    assert fetched.status == "expired"
    assert confirm_pending_action(action.id, override=True).success is False


def test_unknown_id_is_handled():
    assert get_pending_action("act_missing_000000000000") is None
    assert confirm_pending_action("act_missing_000000000000", override=True).success is False
