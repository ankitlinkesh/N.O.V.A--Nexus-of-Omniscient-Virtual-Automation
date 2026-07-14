"""Standalone verifier for Phase 41 (multi-agent critic).

Proves, end to end and independent of pytest, that the critic
(backend/eva/agent/critic.py) actually gates completion rather than trusting
the planner's self-report:

  1. ``review_completion`` is advisory (always accepts) with no enforcing
     contract; met vs. unmet success criteria flip satisfaction; the
     recommendation is REVISE while the revision budget remains and
     REPORT_HONESTLY once it is exhausted; ``require_verified`` gates on the
     Phase 38 verified-success count.
  2. End to end via ``run_agentic_task`` + a deterministic ScriptedPlanner: an
     over-claimed "done" against an unmet contract with no revision budget is
     rejected honestly (ok=False, status="attempted", "critic_rejected" in
     safety_stops); a first "done" that does not meet the contract but has
     revision budget left is sent back, and a later "done" that does meet it
     is accepted.
  3. The flight recorder emits a "critic" event for an enforcing-contract task
     when tracing is on (redirecting the trace root to a scratch directory).
  4. Source wiring: runner.py references ``review_completion`` and
     ``_finalize_success``.
  5. The new eval task is registered and the whole offline suite stays green.
  6. This verifier is wired into scripts/verify_eva_all.py's profiles.

Fully offline and deterministic: no network, no live LLM. Any global state
touched (env vars, the trace-store root) is restored in a ``finally`` block.
"""

from __future__ import annotations

import asyncio
import glob
import json
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
    from backend.eva.agent.critic import (
        ACCEPT,
        REPORT_HONESTLY,
        REVISE,
        DelegationContract,
        review_completion,
    )
    from backend.eva.agent.planner import PlannerDecision
    from backend.eva.agent.runner import run_agentic_task
    from backend.eva.evals.harness import run_offline_evals
    from backend.eva.evals.offline_suite import offline_tasks
    from backend.eva.observability import local_trace_store
    from backend.eva.tools.registry import ToolRegistry
    from scripts import verify_eva_all

    def _done(final_response: str) -> PlannerDecision:
        return PlannerDecision(
            type="done",
            reason="finished",
            tool_calls=[],
            final_response=final_response,
            continue_after_tools=False,
        )

    saved_env = {key: os.environ.get(key) for key in ("EVA_TRACING_ENABLED",)}
    saved_trace_root = local_trace_store.DEFAULT_TRACE_ROOT

    try:
        # 1. review_completion: advisory acceptance, met/unmet criteria,
        #    REVISE vs. REPORT_HONESTLY by revision budget, require_verified.
        no_contract_verdict = review_completion(
            goal="do a thing",
            final_response="All done.",
            observations=[],
            verified_successes=0,
            failures=0,
            contract=None,
        )
        check(no_contract_verdict.satisfied is True, "no contract must be advisory and satisfied")
        check(no_contract_verdict.recommendation == ACCEPT, "no contract must recommend accept")

        met_contract = DelegationContract(success_criteria=("report saved",), max_revisions=1)
        met_verdict = review_completion(
            goal="save the report",
            final_response="the report saved successfully",
            observations=[],
            verified_successes=0,
            failures=0,
            contract=met_contract,
        )
        check(met_verdict.satisfied is True, "a met success criterion must satisfy the critic")
        check(met_verdict.recommendation == ACCEPT, "a satisfied verdict must recommend accept")

        revise_verdict = review_completion(
            goal="save the report",
            final_response="not yet",
            observations=[],
            verified_successes=0,
            failures=0,
            contract=met_contract,
            revisions_used=0,
        )
        check(revise_verdict.satisfied is False, "an unmet criterion must be unsatisfied")
        check("report saved" in revise_verdict.unmet_criteria, f"unmet_criteria must list the missing criterion, got {revise_verdict.unmet_criteria!r}")
        check(revise_verdict.recommendation == REVISE, "revision budget remaining must recommend revise")

        exhausted_contract = DelegationContract(success_criteria=("report saved",), max_revisions=0)
        honest_verdict = review_completion(
            goal="save the report",
            final_response="trust me it's done",
            observations=[],
            verified_successes=0,
            failures=0,
            contract=exhausted_contract,
            revisions_used=0,
        )
        check(honest_verdict.satisfied is False, "an exhausted budget must still be unsatisfied")
        check(honest_verdict.recommendation == REPORT_HONESTLY, "exhausted revision budget must recommend report_honestly")

        verified_contract = DelegationContract(success_criteria=("report saved",), require_verified=True, max_revisions=1)
        unverified = review_completion(
            goal="save the report",
            final_response="report saved",
            observations=[],
            verified_successes=0,
            failures=0,
            contract=verified_contract,
        )
        check(unverified.satisfied is False, "require_verified with zero verified successes must be unsatisfied")

        verified = review_completion(
            goal="save the report",
            final_response="report saved",
            observations=[],
            verified_successes=1,
            failures=0,
            contract=verified_contract,
        )
        check(verified.satisfied is True, "require_verified with a verified success and met criteria must be satisfied")

        # 2. End-to-end via run_agentic_task: over-claimed rejection and
        #    revise-then-meet acceptance.
        overclaimed = asyncio.run(
            run_agentic_task(
                "save the report",
                {
                    "planner": ScriptedPlanner([_done("trust me it's done")]),
                    "registry": ToolRegistry(),
                    "contract": {"success_criteria": ["report saved"], "max_revisions": 0},
                    "execute_tools": True,
                },
            )
        )
        check(overclaimed["ok"] is False, f"an over-claimed done against an unmet contract must not report ok=True, got {overclaimed['ok']!r}")
        check(overclaimed["status"] == "attempted", f"a critic rejection must leave status='attempted', got {overclaimed['status']!r}")
        check("critic_rejected" in overclaimed["safety_stops"], f"safety_stops must record critic_rejected, got {overclaimed['safety_stops']!r}")
        check(overclaimed["critic"]["recommendation"] == REPORT_HONESTLY, f"the critic verdict must recommend report_honestly, got {overclaimed['critic']!r}")
        check("could not confirm" in overclaimed["final_response"], f"the final response must carry an honest caveat, got {overclaimed['final_response']!r}")

        revise_planner = ScriptedPlanner([_done("not yet"), _done("the report saved")])
        revise_then_meet = asyncio.run(
            run_agentic_task(
                "save the report",
                {
                    "planner": revise_planner,
                    "registry": ToolRegistry(),
                    "contract": {"success_criteria": ["report saved"], "max_revisions": 1},
                    "execute_tools": True,
                },
            )
        )
        check(revise_then_meet["ok"] is True, f"a revise-then-meet run must end ok=True, got {revise_then_meet['ok']!r}")
        check(revise_then_meet["critic"]["satisfied"] is True, f"the final critic verdict must be satisfied, got {revise_then_meet['critic']!r}")
        check(revise_planner.calls >= 2, "the critic must have sent the first done back, forcing a second planner call")

        # 3. Flight recorder: a "critic" event appears when tracing is on.
        scratch_root = Path(tempfile.mkdtemp(prefix="eva_phase41_critic_trace_"))
        os.environ["EVA_TRACING_ENABLED"] = "1"
        local_trace_store.DEFAULT_TRACE_ROOT = scratch_root
        try:
            asyncio.run(
                run_agentic_task(
                    "save the report",
                    {
                        "planner": ScriptedPlanner([_done("the report saved successfully")]),
                        "registry": ToolRegistry(),
                        "contract": {"success_criteria": ["report saved"], "max_revisions": 1},
                        "execute_tools": True,
                    },
                )
            )
            trace_files = glob.glob(str(scratch_root / "*.jsonl"))
            check(trace_files, f"tracing on must write at least one trace file to {scratch_root}")
            found_critic_event = False
            for trace_file in trace_files:
                for line in Path(trace_file).read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except Exception:
                        continue
                    if event.get("type") == "critic":
                        found_critic_event = True
                        break
                if found_critic_event:
                    break
            check(found_critic_event, f"expected a 'critic' event in one of {trace_files}")
        finally:
            os.environ.pop("EVA_TRACING_ENABLED", None)
            local_trace_store.DEFAULT_TRACE_ROOT = saved_trace_root

        # 4. Source wiring.
        runner_source = (ROOT / "backend" / "eva" / "agent" / "runner.py").read_text(encoding="utf-8")
        check("review_completion" in runner_source, "runner.py must reference review_completion")
        check("_finalize_success" in runner_source, "runner.py must define/call _finalize_success")

        # 5. The new eval is registered and the whole offline suite is green.
        task_ids = {task.id for task in offline_tasks()}
        check("critic_gates_overclaimed_completion" in task_ids, "the critic-gating eval must be registered")

        eval_report = run_offline_evals()
        check(eval_report.all_passed, f"offline eval suite must stay green: {eval_report.summary_text()}")
        check(
            any(r.task_id == "critic_gates_overclaimed_completion" and r.passed for r in eval_report.results),
            "critic_gates_overclaimed_completion must pass",
        )

        # 6. Registered in the master verifier profiles.
        verifier_name = "verify_eva_phase41_critic.py"
        check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 41 critic verifier")
        descriptors = getattr(verify_eva_all, "VERIFIER_DESCRIPTORS")
        check(verifier_name in descriptors, "master verifier descriptor missing the Phase 41 critic verifier")

    finally:
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        local_trace_store.DEFAULT_TRACE_ROOT = saved_trace_root

    print(
        "PASS: Phase 41 multi-agent critic -- review_completion is advisory with no enforcing contract, flips "
        "satisfaction on met/unmet success criteria, recommends revise while the revision budget remains and "
        "report_honestly once it is exhausted, and gates on require_verified's independently-verified-success "
        "count; run_agentic_task honestly rejects an over-claimed done against an unmet, budget-exhausted "
        "contract (ok=False, status=attempted, critic_rejected, a 'could not confirm' caveat) and recovers a "
        "revise-then-meet run to ok=True after the critic sends the first done back; the flight recorder emits a "
        "'critic' event when tracing is on; runner.py wires review_completion/_finalize_success; the new "
        "critic_gates_overclaimed_completion eval is registered and the whole offline suite stays green; and this "
        "verifier is wired into the master profiles."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
