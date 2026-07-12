"""Executable spec for backend/eva/agent/executor.py's ToolExecutor.

Today, ToolExecutor._permission_decision() reads `confirmed` straight out of
PlannedToolCall.args and feeds it into PermissionContext(override_granted=...),
so a planner (or an attacker who can influence planned args) can grant its
own override just by setting confirmed=True in args, then executor.execute()
calls registry.run(call.tool, **args) which honors that same confirmed flag
again. After the fix, the executor must route through the central
ToolRegistry.run() gate (which ignores/strips `confirmed`) so args-level
`confirmed` can never bypass the ledger.
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
