"""Executable spec for the Phase 42b end-to-end gate wiring in
backend/eva/tools/registry.py (``ToolRegistry.run``).

Phase 42a's ``calibrate``/``count_approvals`` are pure functions; this spec
proves the registry actually wires them into the live gate: a confirm-class,
trust-eligible (``action_type == "MCP_TOOL_CALL"``) synthetic tool stays gated
by default, and only auto-executes once ``EVA_TRUST_POLICIES_ENABLED`` is on
AND the ledger holds enough confirmed approvals for that exact (tool, target)
signature. An override-class tool (real ``screen.observe``) must never be
auto-allowed by trust, no matter how many approvals pile up, because
``ToolRegistry.run`` only ever calibrates a "confirm" classification.

Fully offline and deterministic: a temp ledger path (env override) is used,
never the real ledger, and ``tool_gate.reset_pending_calls()`` plus every env
var this file touches are cleared/restored around each test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.eva.permissions.ledger import confirm_pending_action, create_pending_action
from backend.eva.permissions.pending_actions import EvaPendingAction
from backend.eva.permissions.trust_policy import approval_threshold
from backend.eva.security import tool_gate
from backend.eva.tools.registry import ToolRegistry, ToolSpec

FAKE_TOOL_NAME = "mcp.fake_eligible_tool"
TARGET = "widget-1"


def _fake_handler(target: str | None = None) -> dict:
    return {"ok": True, "handled_target": target}


def _install_fake_tool(registry: ToolRegistry) -> None:
    registry._tools[FAKE_TOOL_NAME] = ToolSpec(
        name=FAKE_TOOL_NAME,
        description="Synthetic MCP-eligible confirm-class tool for the trust gate spec.",
        args_schema={"type": "object", "properties": {"target": {"type": "string"}}, "required": [], "additionalProperties": False},
        safety_level="sensitive",
        handler=_fake_handler,
        action_type="MCP_TOOL_CALL",
        risk_categories=("MCP_TOOL_CALL",),
        requires_confirmation=True,
    )


def _seed_approvals(count: int, *, tool: str = FAKE_TOOL_NAME, target: str = TARGET) -> None:
    for _ in range(count):
        action = EvaPendingAction.new(
            action_type=tool,
            risk_level="medium",
            risk_category="MCP_TOOL_CALL",
            summary=f"{tool}: seeded approval",
            target=target,
            requires_confirmation=True,
            source="test",
            executor_available=True,
            executor_name=tool,
        )
        create_pending_action(action)
        confirm_pending_action(action.id)


@pytest.fixture(autouse=True)
def _isolated_gate_state(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EVA_PENDING_ACTION_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))
    monkeypatch.delenv("EVA_TRUST_POLICIES_ENABLED", raising=False)
    tool_gate.reset_pending_calls()
    yield
    tool_gate.reset_pending_calls()


def test_flag_off_confirm_class_tool_stays_gated(monkeypatch):
    monkeypatch.delenv("EVA_TRUST_POLICIES_ENABLED", raising=False)
    _seed_approvals(approval_threshold() + 5)
    registry = ToolRegistry()
    _install_fake_tool(registry)

    result = registry.run(FAKE_TOOL_NAME, target=TARGET)

    assert isinstance(result, dict)
    assert result.get("requires_confirmation") is True
    assert result.get("ok") is False


def test_flag_on_with_enough_approvals_auto_executes(monkeypatch):
    monkeypatch.setenv("EVA_TRUST_POLICIES_ENABLED", "1")
    _seed_approvals(approval_threshold())
    registry = ToolRegistry()
    _install_fake_tool(registry)

    result = registry.run(FAKE_TOOL_NAME, target=TARGET)

    assert result == {"ok": True, "handled_target": TARGET}
    assert not (isinstance(result, dict) and result.get("requires_confirmation"))


def test_flag_on_but_not_enough_approvals_stays_gated(monkeypatch):
    monkeypatch.setenv("EVA_TRUST_POLICIES_ENABLED", "1")
    _seed_approvals(max(approval_threshold() - 1, 0))
    registry = ToolRegistry()
    _install_fake_tool(registry)

    result = registry.run(FAKE_TOOL_NAME, target=TARGET)

    assert isinstance(result, dict)
    assert result.get("requires_confirmation") is True


def test_flag_on_with_approvals_for_a_different_target_stays_gated(monkeypatch):
    monkeypatch.setenv("EVA_TRUST_POLICIES_ENABLED", "1")
    _seed_approvals(approval_threshold() + 5, target="a-different-widget")
    registry = ToolRegistry()
    _install_fake_tool(registry)

    result = registry.run(FAKE_TOOL_NAME, target=TARGET)

    assert isinstance(result, dict)
    assert result.get("requires_confirmation") is True


def test_override_class_tool_is_never_auto_allowed_even_with_trust_and_approvals(monkeypatch):
    monkeypatch.setenv("EVA_TRUST_POLICIES_ENABLED", "1")
    # screen.observe is action_type=PRIVACY_SCREEN_READ, which classify_tool_call
    # resolves to "override" -- ToolRegistry.run only ever calibrates a "confirm"
    # classification, so no volume of approvals can de-escalate it.
    _seed_approvals(approval_threshold() + 50, tool="screen.observe", target="")
    registry = ToolRegistry()

    result = registry.run("screen.observe", reason="trust spec probe")

    assert isinstance(result, dict)
    assert result.get("requires_confirmation") is True
    assert result.get("risk_class") == "override"
