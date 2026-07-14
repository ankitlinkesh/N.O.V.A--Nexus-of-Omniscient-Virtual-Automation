"""Executable spec for the Phase 41 critic wired into run_agentic_task().

Drives backend/eva/agent/runner.py end-to-end with a deterministic
ScriptedPlanner (the injectable testability seam in ``context["planner"]``)
to prove the four contract-driven behaviors:

  * no contract -> advisory critic, task completes normally;
  * an enforcing contract whose criteria are already met in the "done"
    message -> accepted;
  * an enforcing contract whose criteria are unmet on the first "done" but a
    revision budget remains -> the critic sends it back, and a later attempt
    that does meet the criteria is accepted;
  * an enforcing contract whose criteria are unmet with no revision budget
    left -> an honest rejection (ok=False, status="attempted",
    "critic_rejected" in safety_stops, recommendation="report_honestly", and
    a "could not confirm" caveat in the final response).

Fully offline and deterministic: no network, no live LLM, and tracing is left
off (EVA_TRACING_ENABLED is never set).
"""

from __future__ import annotations

import asyncio

from backend.eva.agent.planner import PlannerDecision
from backend.eva.agent.runner import run_agentic_task
from backend.eva.tools.registry import ToolRegistry


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


def _done(final_response: str) -> PlannerDecision:
    return PlannerDecision(
        type="done",
        reason="finished",
        tool_calls=[],
        final_response=final_response,
        continue_after_tools=False,
    )


def _run(planner: ScriptedPlanner, contract=None) -> dict:
    context: dict = {"planner": planner, "registry": ToolRegistry(), "execute_tools": True}
    if contract is not None:
        context["contract"] = contract
    return asyncio.run(run_agentic_task("do it", context))


def test_no_contract_is_advisory_and_ok():
    result = _run(ScriptedPlanner([_done("All set.")]))

    assert result["ok"] is True
    assert result["critic"]["satisfied"] is True


def test_enforcing_contract_met_is_accepted():
    contract = {"success_criteria": ["report saved"], "max_revisions": 1}
    result = _run(ScriptedPlanner([_done("I saved the report saved successfully.")]), contract=contract)

    assert result["ok"] is True
    assert result["critic"]["satisfied"] is True
    assert result["critic"]["recommendation"] == "accept"


def test_revise_then_meet_is_accepted():
    contract = {"success_criteria": ["report saved"], "max_revisions": 1}
    planner = ScriptedPlanner([_done("not yet"), _done("the report saved")])
    result = _run(planner, contract=contract)

    assert result["ok"] is True
    assert result["critic"]["satisfied"] is True
    # Proves the planner was actually invoked twice (the critic sent the
    # first "done" back for revision before the second was accepted).
    assert planner.calls >= 2


def test_unmet_with_no_budget_is_honest_rejection():
    contract = {"success_criteria": ["report saved"], "max_revisions": 0}
    result = _run(ScriptedPlanner([_done("trust me it's done")]), contract=contract)

    assert result["ok"] is False
    assert result["status"] == "attempted"
    assert "critic_rejected" in result["safety_stops"]
    assert result["critic"]["recommendation"] == "report_honestly"
    assert "could not confirm" in result["final_response"]
