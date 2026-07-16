"""Skill synthesis: learning from traces, and refusing to invent capability (Phase 47)."""

from __future__ import annotations

import pytest

from eva.self_improvement.models import SkillStep
from eva.self_improvement.synthesis import (
    MIN_OBSERVATIONS,
    NEVER_LEARN_TOOLS,
    propose_skills_from_traces,
    validate_steps,
)
from eva.tools.registry import ToolRegistry


@pytest.fixture()
def registry():
    return ToolRegistry()


def _trace(trace_id: str, tools: list[str], summary: str = "ok") -> dict:
    return {
        "trace_id": trace_id,
        "events": [
            {"type": "tool_call", "payload": {"tool_name": t, "args": {}, "result_summary": summary}}
            for t in tools
        ],
    }


# -- validation: the anti-escalation check --------------------------------

def test_a_skill_cannot_invent_a_tool(registry):
    ok, reason = validate_steps([SkillStep(tool="run_shell", args={"cmd": "rm -rf /"})], registry)
    assert ok is False
    assert "unknown tool" in reason


def test_a_skill_cannot_bake_in_a_never_learn_tool(registry):
    for tool in ("screen.observe", "file.delete"):
        ok, reason = validate_steps([SkillStep(tool=tool, args={})], registry)
        assert ok is False, f"{tool} must never be learnable"
        assert "never be baked" in reason


def test_validate_accepts_existing_tools(registry):
    ok, _ = validate_steps([SkillStep(tool="workspace_status", args={})], registry)
    assert ok is True


def test_validate_rejects_empty_and_oversized(registry):
    assert validate_steps([], registry)[0] is False
    too_many = [SkillStep(tool="workspace_status", args={}) for _ in range(50)]
    assert validate_steps(too_many, registry)[0] is False


def test_validate_fails_closed_without_a_registry():
    ok, _ = validate_steps([SkillStep(tool="workspace_status", args={})], None)
    assert ok is False, "no registry to check against must fail closed"


# -- the learning loop -----------------------------------------------------

def test_learns_a_repeated_workflow(registry):
    traces = [_trace(f"t{i}", ["workspace_status", "workspace_search", "workspace_read_file"]) for i in range(3)]
    candidates = propose_skills_from_traces(traces, registry)
    assert len(candidates) == 1
    assert [s.tool for s in candidates[0]["steps"]] == ["workspace_status", "workspace_search", "workspace_read_file"]
    assert candidates[0]["observed_count"] == 3


def test_a_one_off_sequence_is_not_learned(registry):
    traces = [_trace("t1", ["workspace_status", "workspace_search"])]
    assert propose_skills_from_traces(traces, registry) == []


def test_below_min_observations_is_not_learned(registry):
    traces = [_trace(f"t{i}", ["workspace_status", "workspace_search"]) for i in range(MIN_OBSERVATIONS - 1)]
    assert propose_skills_from_traces(traces, registry) == []


def test_a_gated_call_that_never_ran_is_not_evidence(registry):
    # A held (unconfirmed) call did not happen, so it cannot prove a workflow.
    traces = [_trace(f"g{i}", ["workspace_status", "file.copy"], summary="requires_confirmation") for i in range(3)]
    assert propose_skills_from_traces(traces, registry) == []


def test_a_failed_call_is_not_evidence(registry):
    traces = [_trace(f"e{i}", ["workspace_status", "workspace_search"], summary="error: boom") for i in range(3)]
    assert propose_skills_from_traces(traces, registry) == []


def test_hallucinated_tools_in_traces_are_rejected(registry):
    traces = [_trace(f"b{i}", ["workspace_status", "run_shell"]) for i in range(3)]
    assert propose_skills_from_traces(traces, registry) == []


def test_subsequences_are_dropped_in_favour_of_the_longest(registry):
    traces = [_trace(f"t{i}", ["workspace_status", "workspace_search", "workspace_read_file"]) for i in range(3)]
    candidates = propose_skills_from_traces(traces, registry)
    # Only the full 3-step habit, not its 2-step sub-windows.
    assert len(candidates) == 1
    assert len(candidates[0]["steps"]) == 3


def test_a_repeat_within_one_trace_is_not_a_habit(registry):
    # The same sequence twice inside ONE trace is one observation, not two.
    traces = [_trace("t1", ["workspace_status", "workspace_search", "workspace_status", "workspace_search"])]
    assert propose_skills_from_traces(traces, registry) == []


def test_a_repeated_poll_of_one_tool_is_not_a_skill(registry):
    """Real traces are full of status -> status -> status. That is noise, not a
    workflow: a named skill must involve more than one distinct tool."""
    traces = [_trace(f"t{i}", ["workspace_status"] * 4) for i in range(3)]
    assert propose_skills_from_traces(traces, registry) == []


def test_learned_skill_names_are_not_truncated_mid_token(registry):
    long_seq = ["workspace_status", "workspace_search", "workspace_read_file", "workspace_project_summary"]
    traces = [_trace(f"t{i}", long_seq) for i in range(3)]
    candidates = propose_skills_from_traces(traces, registry)
    assert candidates, "a long distinct workflow should still be learned"
    name = candidates[0]["name"]
    assert len(name) <= 80
    # No dangling partial tool name at the end.
    assert not name.endswith("_stat")


def test_synthesis_is_fail_safe_on_garbage(registry):
    assert propose_skills_from_traces([{"trace_id": "x"}], registry) == []
    assert propose_skills_from_traces([], registry) == []
    assert propose_skills_from_traces(None, registry) == []


def test_never_learn_set_covers_the_dangerous_actions():
    for tool in ("screen.observe", "file.delete", "power_action"):
        assert tool in NEVER_LEARN_TOOLS
