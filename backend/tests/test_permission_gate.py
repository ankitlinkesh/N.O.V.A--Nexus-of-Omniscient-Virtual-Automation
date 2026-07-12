"""Lock-in tests for backend/eva/security/permission_gate.py's evaluate_action().

These describe existing, already-correct hard-block / override behavior that
the upcoming refactor must not regress. Unlike the rest of this suite, all
tests here are expected to PASS against the current code.
"""

from __future__ import annotations

from backend.eva.agent.action_model import AgentAction
from backend.eva.security.action_types import ActionType
from backend.eva.security.permission_gate import PermissionContext, evaluate_action


def _action(**overrides) -> AgentAction:
    defaults = dict(
        tool_name="test_tool",
        action_type=ActionType.SAFE_LOCAL_READ.value,
        description="test action",
        params={},
        risk_categories=[],
    )
    defaults.update(overrides)
    return AgentAction(**defaults)


def test_shell_action_is_hard_blocked():
    action = _action(action_type=ActionType.SHELL_ACTION.value, risk_categories=[ActionType.SHELL_ACTION.value])

    decision = evaluate_action(action, PermissionContext())

    assert decision.decision == "hard_block"


def test_credential_access_risk_category_is_hard_blocked():
    action = _action(risk_categories=[ActionType.CREDENTIAL_ACCESS.value])

    decision = evaluate_action(action, PermissionContext())

    assert decision.decision == "hard_block"


def test_malware_like_risk_category_is_hard_blocked():
    action = _action(risk_categories=[ActionType.MALWARE_LIKE.value])

    decision = evaluate_action(action, PermissionContext())

    assert decision.decision == "hard_block"


def test_hard_block_is_not_overridable():
    """Even an explicit override grant must not defeat a hard block."""
    action = _action(risk_categories=[ActionType.CREDENTIAL_ACCESS.value])

    decision = evaluate_action(action, PermissionContext(override_granted=True, user_confirmed=True))

    assert decision.decision == "hard_block"


def test_destructive_action_without_override_asks_for_override():
    action = _action(
        action_type=ActionType.DESTRUCTIVE_FILE_ACTION.value,
        risk_categories=[ActionType.DESTRUCTIVE_FILE_ACTION.value],
        destructive=True,
    )

    decision = evaluate_action(action, PermissionContext(override_granted=False))

    assert decision.decision == "ask_override"


def test_destructive_action_with_override_is_allowed():
    action = _action(
        action_type=ActionType.DESTRUCTIVE_FILE_ACTION.value,
        risk_categories=[ActionType.DESTRUCTIVE_FILE_ACTION.value],
        destructive=True,
    )

    decision = evaluate_action(action, PermissionContext(override_granted=True))

    assert decision.decision == "allow"
