"""Confirm-class gating (complements the override-class e2e in test_registry_gate).

External-message and screen-input tools are 'confirm' class: they require a
plain `confirm <id>` (not override) and create a pending_confirmation ledger
entry. These tests verify the gate classification and ledger state without
executing the side-effectful handler.
"""
from __future__ import annotations

from backend.eva.permissions.ledger import get_pending_action
from backend.eva.tools.registry import ToolRegistry

from backend.tests.conftest import import_tool_gate


def test_screen_type_text_is_confirm_class_and_gated():
    registry = ToolRegistry()
    result = registry.run("screen.type_text", text="hello", reason="test")
    assert result.get("requires_confirmation") is True
    assert result.get("risk_class") == "confirm"
    pending = get_pending_action(result["pending_id"])
    assert pending is not None
    assert pending.status == "pending_confirmation"
    assert pending.requires_override is False


def test_external_message_tool_gated_without_side_effect():
    """message.send_via_ui must gate (not send) and register a pending call."""
    tool_gate = import_tool_gate()
    registry = ToolRegistry()
    result = registry.run("message.send_via_ui", recipient="Alice", message="hi")
    assert result.get("requires_confirmation") is True
    assert result.get("risk_class") in {"confirm", "override"}
    assert tool_gate.get_pending_call(result["pending_id"]) is not None


def test_run_approved_requires_prior_ledger_confirmation():
    """A confirm-class pending cannot be executed until the ledger confirms it."""
    registry = ToolRegistry()
    gated = registry.run("screen.type_text", text="x", reason="test")
    pending_id = gated["pending_id"]
    # Not confirmed via the ledger yet -> run_approved must refuse.
    refused = registry.run_approved(pending_id)
    assert refused.get("ok") is False
