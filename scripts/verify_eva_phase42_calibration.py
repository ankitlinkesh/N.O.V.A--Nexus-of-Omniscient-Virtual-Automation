"""Standalone verifier for Phase 42b (calibrated autonomy: tests + eval + gate).

Proves, end to end and independent of pytest, that Phase 42a's calibration
primitives (backend/eva/permissions/trust_policy.py) are both correct in
isolation AND actually wired into the live tool gate and agent loop:

  1. ``calibrate``'s full contract: flag-off never de-escalates a confirm-class
     action no matter how many approvals exist; flag-on + an eligible action
     type + enough approvals de-escalates confirm -> allow; a non-eligible
     action type (outside TRUST_ELIGIBLE_ACTION_TYPES) and override/hard_block
     base decisions are NEVER de-escalated, even with the flag on and huge
     approval counts; low confidence always escalates an "allow" to "confirm",
     unconditionally (regardless of the trust flag).
  2. ``count_approvals`` reads a real (temp) pending-action ledger: seeding N
     confirmed approvals for a (tool, target) signature yields N; a different
     target yields 0.
  3. The gate end to end via ``ToolRegistry.run``: a synthetic MCP-eligible
     confirm-class tool stays gated with the flag off; auto-executes once the
     flag is on and the ledger holds enough approvals for that exact
     signature; a real override-class tool (screen.observe) is NEVER
     auto-allowed by trust, however many approvals exist, because the gate
     only ever calibrates a "confirm" classification.
  4. The agent loop hooks via ``run_agentic_task`` + a deterministic
     ScriptedPlanner: a mid-task interrupt stops the task honestly
     ("interrupted" in safety_stops, ok=False, no tool executed); a low
     ``min_action_confidence`` escalates the next planned action instead of
     executing it ("low_confidence_escalation" in safety_stops).
  5. Source wiring: registry.py references trust_policies_enabled and
     count_approvals; runner.py references _is_interrupted and
     min_action_confidence.
  6. The new eval task is registered and the whole offline suite stays green.
  7. This verifier is wired into scripts/verify_eva_all.py's profiles.

Fully offline and deterministic: no network, no live LLM. A temp ledger path
(env override) is used for every ledger-touching check, never the real
ledger, and every env var this file touches is restored in a ``finally``
block; ``tool_gate.reset_pending_calls()`` is called around the gate checks.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


class ScriptedPlanner:
    """Deterministic planner for driving the agent loop in tests. Returns queued
    PlannerDecisions in order; repeats the last one once exhausted."""

    def __init__(self, decisions):
        self._decisions = list(decisions)
        self.calls = 0

    async def plan(self, goal, history, mode="agent_step", task_context=None):
        decision = self._decisions[min(self.calls, len(self._decisions) - 1)]
        self.calls += 1
        return decision


def main() -> int:
    from backend.eva.agent.planner import PlannedToolCall, PlannerDecision
    from backend.eva.agent.runner import run_agentic_task
    from backend.eva.evals import run_offline_evals
    from backend.eva.evals.offline_suite import offline_tasks
    from backend.eva.permissions.ledger import confirm_pending_action, create_pending_action
    from backend.eva.permissions.pending_actions import EvaPendingAction
    from backend.eva.permissions.trust_policy import (
        TRUST_ELIGIBLE_ACTION_TYPES,
        approval_threshold,
        calibrate,
        count_approvals,
        low_confidence_threshold,
    )
    from backend.eva.security import tool_gate
    from backend.eva.tools.registry import ToolRegistry, ToolSpec
    from scripts import verify_eva_all

    ENV_KEYS = ("EVA_TRUST_POLICIES_ENABLED", "EVA_TRUST_APPROVAL_THRESHOLD", "EVA_LOW_CONFIDENCE_THRESHOLD", "EVA_PENDING_ACTION_LEDGER_PATH")
    saved_env = {key: os.environ.get(key) for key in ENV_KEYS}
    scratch_dir = Path(tempfile.mkdtemp(prefix="eva_phase42_calibration_"))

    try:
        # 1. calibrate()'s full contract.
        os.environ.pop("EVA_TRUST_POLICIES_ENABLED", None)
        flag_off = calibrate(base_decision="confirm", action_type="MCP_TOOL_CALL", approvals=999)
        check(flag_off.decision == "confirm", f"flag-off must never de-escalate confirm, got {flag_off.decision!r}")
        check(flag_off.auto_allowed is False, "flag-off must not auto_allow")

        os.environ["EVA_TRUST_POLICIES_ENABLED"] = "1"
        eligible_enough = calibrate(base_decision="confirm", action_type="MCP_TOOL_CALL", approvals=approval_threshold())
        check(eligible_enough.decision == "allow", f"flag-on + eligible + enough approvals must de-escalate to allow, got {eligible_enough.decision!r}")
        check(eligible_enough.auto_allowed is True, "flag-on + eligible + enough approvals must set auto_allowed=True")

        eligible_not_enough = calibrate(base_decision="confirm", action_type="MCP_TOOL_CALL", approvals=approval_threshold() - 1)
        check(eligible_not_enough.decision == "confirm", f"below-threshold approvals must stay confirm, got {eligible_not_enough.decision!r}")

        check("EXTERNAL_POST" not in TRUST_ELIGIBLE_ACTION_TYPES, "EXTERNAL_POST must not be trust-eligible")
        non_eligible = calibrate(base_decision="confirm", action_type="EXTERNAL_POST", approvals=999)
        check(non_eligible.decision == "confirm", f"a non-eligible action type must never de-escalate, got {non_eligible.decision!r}")

        override_never = calibrate(base_decision="override", action_type="DESTRUCTIVE_FILE_ACTION", approvals=999)
        check(override_never.decision == "override", f"override must never de-escalate, got {override_never.decision!r}")
        hard_block_never = calibrate(base_decision="hard_block", action_type="MCP_TOOL_CALL", approvals=999)
        check(hard_block_never.decision == "hard_block", f"hard_block must never de-escalate, got {hard_block_never.decision!r}")

        threshold = low_confidence_threshold()
        low_confidence_escalates = calibrate(base_decision="allow", action_type="x", confidence=threshold - 0.01)
        check(low_confidence_escalates.decision == "confirm", "low confidence must escalate allow -> confirm")
        check(low_confidence_escalates.escalated is True, "low confidence escalation must set escalated=True")
        os.environ.pop("EVA_TRUST_POLICIES_ENABLED", None)
        low_confidence_escalates_flag_off = calibrate(base_decision="allow", action_type="x", confidence=threshold - 0.01)
        check(low_confidence_escalates_flag_off.escalated is True, "low confidence escalation must fire regardless of the trust flag")

        # 2. count_approvals() over a temp ledger.
        ledger_path = scratch_dir / "ledger.jsonl"
        os.environ["EVA_PENDING_ACTION_LEDGER_PATH"] = str(ledger_path)

        def _seed(tool: str, target: str, n: int) -> None:
            for _ in range(n):
                action = EvaPendingAction.new(
                    action_type=tool,
                    risk_level="medium",
                    risk_category="MCP_TOOL_CALL",
                    summary=f"{tool}: seeded approval",
                    target=target,
                    requires_confirmation=True,
                    source="verifier",
                    executor_available=True,
                    executor_name=tool,
                )
                create_pending_action(action)
                confirm_pending_action(action.id)

        _seed("mcp.verifier_tool", "widget-1", 4)
        check(count_approvals("mcp.verifier_tool", "widget-1") == 4, "count_approvals must count all seeded confirmed approvals for the matching signature")
        check(count_approvals("mcp.verifier_tool", "widget-2") == 0, "count_approvals must be 0 for a non-matching target")

        os.environ["EVA_PENDING_ACTION_LEDGER_PATH"] = str(scratch_dir / "missing" / "ledger.jsonl")
        check(count_approvals("mcp.verifier_tool", "widget-1") == 0, "count_approvals must fail safe to 0 when the ledger path does not exist")

        # 3. Gate end to end via ToolRegistry.run.
        os.environ["EVA_PENDING_ACTION_LEDGER_PATH"] = str(ledger_path)
        FAKE_TOOL = "mcp.fake_eligible_tool"
        TARGET = "widget-9"

        def _fake_handler(target: str | None = None) -> dict:
            return {"ok": True, "handled_target": target}

        def _fresh_registry_with_fake_tool() -> ToolRegistry:
            registry = ToolRegistry()
            registry._tools[FAKE_TOOL] = ToolSpec(
                name=FAKE_TOOL,
                description="Synthetic MCP-eligible confirm-class tool for the Phase 42 verifier.",
                args_schema={"type": "object", "properties": {"target": {"type": "string"}}, "required": [], "additionalProperties": False},
                safety_level="sensitive",
                handler=_fake_handler,
                action_type="MCP_TOOL_CALL",
                risk_categories=("MCP_TOOL_CALL",),
                requires_confirmation=True,
            )
            return registry

        tool_gate.reset_pending_calls()
        os.environ.pop("EVA_TRUST_POLICIES_ENABLED", None)
        registry = _fresh_registry_with_fake_tool()
        gated = registry.run(FAKE_TOOL, target=TARGET)
        check(isinstance(gated, dict) and gated.get("requires_confirmation") is True, f"flag-off must gate the confirm-class tool, got {gated!r}")

        os.environ["EVA_TRUST_POLICIES_ENABLED"] = "1"
        _seed(FAKE_TOOL, TARGET, approval_threshold())
        tool_gate.reset_pending_calls()
        registry = _fresh_registry_with_fake_tool()
        auto_allowed = registry.run(FAKE_TOOL, target=TARGET)
        check(auto_allowed == {"ok": True, "handled_target": TARGET}, f"flag-on + enough approvals must auto-execute the handler, got {auto_allowed!r}")

        tool_gate.reset_pending_calls()
        _seed("screen.observe", "", approval_threshold() + 50)
        registry = ToolRegistry()
        override_result = registry.run("screen.observe", reason="verifier probe")
        check(isinstance(override_result, dict) and override_result.get("requires_confirmation") is True, "an override-class tool must never be auto-allowed by trust")
        check(override_result.get("risk_class") == "override", f"screen.observe must stay override-class, got {override_result.get('risk_class')!r}")
        tool_gate.reset_pending_calls()

        # 4. Agent loop hooks: interrupt + confidence escalation.
        os.environ.pop("EVA_TRUST_POLICIES_ENABLED", None)
        workspace_status_step = PlannerDecision(
            type="tool_calls", reason="x", tool_calls=[PlannedToolCall(tool="workspace_status", args={})], final_response="", continue_after_tools=True
        )
        done_step = PlannerDecision(type="done", reason="done", tool_calls=[], final_response="All set.", continue_after_tools=False)

        interrupted = asyncio.run(
            run_agentic_task(
                "multi step goal",
                {"planner": ScriptedPlanner([workspace_status_step]), "registry": ToolRegistry(), "interrupt": lambda: True, "execute_tools": True},
            )
        )
        check(interrupted["status"] == "interrupted", f"an interrupt must yield status=interrupted, got {interrupted['status']!r}")
        check(interrupted["ok"] is False, "an interrupted task must report ok=False")
        check("interrupted" in interrupted["safety_stops"], f"safety_stops must record 'interrupted', got {interrupted['safety_stops']!r}")
        check(interrupted["tools_executed"] == [], "an interrupted task must not have executed any tool")

        escalated = asyncio.run(
            run_agentic_task(
                "multi step goal",
                {"planner": ScriptedPlanner([workspace_status_step]), "registry": ToolRegistry(), "min_action_confidence": 0.99, "execute_tools": True},
            )
        )
        check(escalated["status"] == "waiting_for_confirmation", f"low min_action_confidence must escalate, got status={escalated['status']!r}")
        check(escalated["requires_confirmation"] is True, "an escalated action must report requires_confirmation=True")
        check("low_confidence_escalation" in escalated["safety_stops"], f"safety_stops must record low_confidence_escalation, got {escalated['safety_stops']!r}")

        not_escalated = asyncio.run(
            run_agentic_task(
                "multi step goal",
                {"planner": ScriptedPlanner([workspace_status_step, done_step]), "registry": ToolRegistry(), "execute_tools": True},
            )
        )
        check("low_confidence_escalation" not in not_escalated["safety_stops"], "no min_action_confidence must never escalate")
        check(not_escalated["ok"] is True, "a normal run without min_action_confidence must still succeed")

        # 5. Source wiring.
        registry_source = (ROOT / "backend" / "eva" / "tools" / "registry.py").read_text(encoding="utf-8")
        check("trust_policies_enabled" in registry_source, "registry.py must reference trust_policies_enabled")
        check("count_approvals" in registry_source, "registry.py must reference count_approvals")

        runner_source = (ROOT / "backend" / "eva" / "agent" / "runner.py").read_text(encoding="utf-8")
        check("_is_interrupted" in runner_source, "runner.py must reference _is_interrupted")
        check("min_action_confidence" in runner_source, "runner.py must reference min_action_confidence")

        # 6. The new eval is registered and the whole offline suite is green.
        task_ids = {task.id for task in offline_tasks()}
        check("calibrated_autonomy_holds" in task_ids, "the calibrated_autonomy_holds eval must be registered")

        eval_report = run_offline_evals()
        check(eval_report.all_passed, f"offline eval suite must stay green: {eval_report.summary_text()}")
        check(
            any(r.task_id == "calibrated_autonomy_holds" and r.passed for r in eval_report.results),
            "calibrated_autonomy_holds must pass",
        )

        # 7. Registered in the master verifier profiles.
        verifier_name = "verify_eva_phase42_calibration.py"
        check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 42 calibration verifier")
        descriptors = getattr(verify_eva_all, "VERIFIER_DESCRIPTORS")
        check(verifier_name in descriptors, "master verifier descriptor missing the Phase 42 calibration verifier")

    finally:
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        tool_gate.reset_pending_calls()

    print(
        "PASS: Phase 42 calibrated autonomy -- calibrate() never de-escalates with the flag off, de-escalates "
        "confirm->allow only for an eligible action type once enough approvals exist, never de-escalates a "
        "non-eligible action type or an override/hard_block base decision no matter how many approvals pile up, "
        "and always escalates low-confidence allow->confirm regardless of the flag; count_approvals reads a real "
        "temp ledger correctly and fails safe to 0 for a missing path or mismatched target; ToolRegistry.run gates "
        "a synthetic MCP-eligible confirm tool by default, auto-executes it once the flag is on with enough "
        "approvals, and never auto-allows an override-class tool (screen.observe) regardless of approvals; "
        "run_agentic_task's mid-task interrupt and confidence-aware escalation hooks both fire correctly via a "
        "ScriptedPlanner; registry.py and runner.py are wired to the calibration primitives; the new "
        "calibrated_autonomy_holds eval is registered and the whole offline suite stays green; and this verifier "
        "is wired into the master profiles."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
