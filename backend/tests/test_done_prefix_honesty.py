"""'Done.' must be earned, not assumed (Phase 64 / Phase 87 defect class).

Regression cover for backend/eva/api/routes.py::_local_tool_summary, which used
to prefix every summary with "Done. " and denylist a handful of opening phrases.
An action held for approval renders an explainer starting "What you are being
asked to approve", which was not on that denylist -- so Eva announced "Done."
for something that had explicitly not run.
"""

from __future__ import annotations

from backend.eva.api.routes import _local_tool_summary
from backend.eva.agent.executor import ToolExecutionResult

APPROVAL_EXPLAINER = (
    "What you are being asked to approve\n\n"
    "Command: analyze_screen(question='what is on my screen?')\n"
    "If you do nothing, it will not run. Nothing has happened yet."
)


def _result(tool, *, ok, requires_confirmation=False, result=None, error=None, action="run"):
    return ToolExecutionResult(
        tool=tool, ok=ok, result=result, error=error,
        requires_confirmation=requires_confirmation, action=action,
    )


def test_pending_approval_is_not_reported_as_done():
    summary = _local_tool_summary([
        _result("analyze_screen", ok=False, result={"user_message": APPROVAL_EXPLAINER}),
    ])
    assert not summary.startswith("Done")
    assert "Nothing has happened yet." in summary


def test_requires_confirmation_is_not_reported_as_done():
    summary = _local_tool_summary([
        _result("close_app", ok=True, requires_confirmation=True, action="closing Notepad"),
    ])
    assert not summary.startswith("Done")


def test_failed_tool_is_not_reported_as_done():
    summary = _local_tool_summary([
        _result("open_app", ok=False, error="not found"),
    ])
    assert not summary.startswith("Done")
    assert "open_app failed" in summary


def test_one_pending_result_taints_a_mixed_batch():
    """A batch that half-ran must not claim the whole thing did."""
    summary = _local_tool_summary([
        _result("window_list", ok=True, result={"message": "3 windows open."}),
        _result("analyze_screen", ok=False, result={"user_message": APPROVAL_EXPLAINER}),
    ])
    assert not summary.startswith("Done")


def test_genuine_success_still_says_done():
    """The fix must not make Eva coy about work that really happened."""
    summary = _local_tool_summary([
        _result("window_list", ok=True, result={"message": "3 windows open."}),
    ])
    assert summary.startswith("Done")
