"""Guards the code-derived capability-truth report and its core safety invariant.

The point of capability_truth is that the safety docs quote generated facts,
not hand-maintained prose. These tests fail loudly if the generator breaks or
if a change lets a destructive/privacy tool become silently auto-runnable by
the LLM planner.
"""
from __future__ import annotations

from backend.eva.security.capability_truth import build_capability_truth, format_capability_truth

# Action types that must never run without an explicit human approval step.
_APPROVAL_REQUIRED_ACTION_TYPES = {
    "DESTRUCTIVE_FILE_ACTION",
    "SYSTEM_CHANGE",
    "PRIVACY_FILE_READ",
    "PRIVACY_CHAT_READ",
    "EXTERNAL_MESSAGE_SEND",
    "EXTERNAL_POST",
    "POWER_ACTION",
}


def test_report_renders_and_counts_are_consistent():
    data = build_capability_truth()
    assert data["total_tools"] > 0
    assert sum(data["counts"].values()) == data["total_tools"], "gate-class counts must partition all tools"
    text = format_capability_truth()
    assert "Eva does execute tools" in text
    assert "cannot be bypassed" in text


def test_no_destructive_tool_is_planner_reachable_and_auto_allowed():
    """The core invariant: nothing that mutates/exfiltrates/acts externally may
    be both reachable by the LLM planner AND classified 'allow' (runs with no
    confirmation). This is what would catch someone adding file.delete to the
    planner whitelist or mislabeling its action_type."""
    data = build_capability_truth()
    offenders = [
        item["tool"]
        for item in data["tools"]
        if item["planner_reachable"]
        and item["gate_class"] == "allow"
        and item["action_type"] in _APPROVAL_REQUIRED_ACTION_TYPES
    ]
    assert not offenders, f"approval-required tools are planner-reachable and auto-allowed: {offenders}"


def test_known_dangerous_tools_are_gated_and_not_planner_reachable():
    data = build_capability_truth()
    by_name = {item["tool"]: item for item in data["tools"]}
    for name in ("file.delete", "file.write_text", "file.copy", "screen.type_text", "screen.hotkey"):
        assert name in by_name, f"expected {name} in registry"
        assert by_name[name]["gate_class"] in {"confirm", "override"}, f"{name} must be gated"
        assert by_name[name]["planner_reachable"] is False, f"{name} must not be planner-reachable"
