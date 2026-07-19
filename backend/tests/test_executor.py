"""Executable spec for backend/eva/agent/executor.py's ToolExecutor.

Today, ToolExecutor._permission_decision() reads `confirmed` straight out of
PlannedToolCall.args and feeds it into PermissionContext(override_granted=...),
so a planner (or an attacker who can influence planned args) can grant its
own override just by setting confirmed=True in args, then executor.execute()
calls registry.run(call.tool, **args) which honors that same confirmed flag
again. After the fix, the executor must route through the central
ToolRegistry.run() gate (which ignores/strips `confirmed`) so args-level
`confirmed` can never bypass the ledger.

Also covers Phase 64, Defect 4: execute_all() used to slice planned calls with
a hardcoded, unnamed ``calls[:3]`` -- anything beyond the third call was
dropped with no error, no warning, and nothing told to the model or the user,
so a multi-step agent would proceed believing its whole plan had run. The
fix names the cap (policies.max_tools_per_step(), env EVA_MAX_TOOLS_PER_STEP,
default still 3) and, when it actually truncates a plan, appends a
ToolExecutionResult reporting exactly that.
"""

from __future__ import annotations

from backend.eva.agent.executor import ToolExecutor
from backend.eva.agent.planner import PlannedToolCall
from backend.eva.tools.registry import ToolRegistry


def test_file_delete_confirmed_in_args_does_not_bypass_gate(sandbox_dir):
    target = sandbox_dir / "victim.txt"
    target.write_text("do not delete me", encoding="utf-8")

    executor = ToolExecutor(ToolRegistry())
    call = PlannedToolCall(tool="file.delete", args={"path": str(target), "confirmed": True})

    result = executor.execute(call)

    assert result.requires_confirmation is True, (
        "confirmed=True inside PlannedToolCall.args must not bypass the central "
        f"gate; got result={result.as_dict()}"
    )
    assert target.exists(), "file.delete executed for real despite missing ledger confirmation"


# -- Phase 64, Defect 4: truncation is reported, not silent -----------------


def test_max_tools_per_step_default_and_env_override(monkeypatch):
    from backend.eva.agent.policies import max_tools_per_step

    monkeypatch.delenv("EVA_MAX_TOOLS_PER_STEP", raising=False)
    assert max_tools_per_step() == 3, "the default must stay 3 -- no behavior change out of the box"

    monkeypatch.setenv("EVA_MAX_TOOLS_PER_STEP", "7")
    assert max_tools_per_step() == 7


def test_execute_all_truncates_at_the_configured_limit_and_reports_it(monkeypatch):
    monkeypatch.setenv("EVA_MAX_TOOLS_PER_STEP", "3")
    executor = ToolExecutor(ToolRegistry())
    calls = [PlannedToolCall(tool="workspace_status", args={}) for _ in range(5)]

    results = executor.execute_all(calls)

    assert len(results) == 4, f"3 executed + 1 truncation notice, got {[r.tool for r in results]}"
    for executed in results[:3]:
        assert executed.tool == "workspace_status"
        assert executed.ok is True

    notice = results[-1]
    assert notice.tool == "plan_truncated"
    assert notice.ok is False, "silent success would be the exact bug this test guards against"
    assert notice.error and "3" in notice.error
    assert notice.result["truncated"] is True
    assert notice.result["limit"] == 3
    assert notice.result["skipped_tools"] == ["workspace_status", "workspace_status"]


def test_execute_all_does_not_truncate_when_the_whole_plan_fits(monkeypatch):
    monkeypatch.setenv("EVA_MAX_TOOLS_PER_STEP", "3")
    executor = ToolExecutor(ToolRegistry())
    calls = [PlannedToolCall(tool="workspace_status", args={}) for _ in range(2)]

    results = executor.execute_all(calls)

    assert len(results) == 2
    assert not any(r.tool == "plan_truncated" for r in results)


def test_execute_all_limit_is_configurable_via_env(monkeypatch):
    monkeypatch.setenv("EVA_MAX_TOOLS_PER_STEP", "2")
    executor = ToolExecutor(ToolRegistry())
    calls = [PlannedToolCall(tool="workspace_status", args={}) for _ in range(4)]

    results = executor.execute_all(calls)

    assert len(results) == 3, f"2 executed + 1 truncation notice, got {[r.tool for r in results]}"
    assert results[-1].tool == "plan_truncated"
    assert results[-1].result["limit"] == 2


def test_execute_all_does_not_report_truncation_when_stopped_for_confirmation(monkeypatch, sandbox_dir):
    """A stop for confirmation is already surfaced through
    requires_confirmation -- it is not the silent-drop bug Defect 4 fixes,
    and must not ALSO get a truncation notice appended on top of it."""
    monkeypatch.setenv("EVA_MAX_TOOLS_PER_STEP", "3")
    target = sandbox_dir / "victim.txt"
    target.write_text("do not delete me", encoding="utf-8")

    executor = ToolExecutor(ToolRegistry())
    calls = [
        PlannedToolCall(tool="file.delete", args={"path": str(target)}),
        PlannedToolCall(tool="workspace_status", args={}),
        PlannedToolCall(tool="workspace_status", args={}),
        PlannedToolCall(tool="workspace_status", args={}),
        PlannedToolCall(tool="workspace_status", args={}),
    ]

    results = executor.execute_all(calls)

    assert len(results) == 1, f"must stop at the first requires_confirmation result: {[r.tool for r in results]}"
    assert results[0].requires_confirmation is True
    assert not any(r.tool == "plan_truncated" for r in results)
    assert target.exists(), "must not have actually deleted anything"
