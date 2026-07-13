"""Declarative table for exact-match "eva <namespace> ..." status/report commands.

These commands were previously dispatched by a run of near-identical
`if normalized in {...}: <local dict>; return dict[normalized](), "fast-command"`
blocks in fast_commands.py. They are pure: exact-match on the normalized
message, zero args, no session/memory/tool state, and each returns report text.
Consolidating them here keeps the routing as data and preserves the lazy
import behavior (the formatter module is imported only when its command runs).
"""
from __future__ import annotations

import importlib
from typing import Callable

# command string -> (module path, formatter function name).
# Imports stay lazy: the module is loaded only when the command is dispatched.
STATUS_COMMANDS: dict[str, tuple[str, str]] = {
    # release candidate
    "eva rc status": ("backend.eva.release_candidate.formatter", "format_rc_status"),
    "eva rc manifest": ("backend.eva.release_candidate.formatter", "format_rc_manifest"),
    "eva rc commit plan": ("backend.eva.release_candidate.formatter", "format_rc_commit_plan"),
    "eva rc hardening report": ("backend.eva.release_candidate.formatter", "format_rc_hardening_report"),
    "eva rc checklist": ("backend.eva.release_candidate.formatter", "format_rc_checklist"),
    "eva rc readiness": ("backend.eva.release_candidate.formatter", "format_rc_readiness"),
    "eva rc safety proof": ("backend.eva.release_candidate.formatter", "format_rc_safety_proof"),
    "eva rc verification": ("backend.eva.release_candidate.formatter", "format_rc_verification"),
    # release demo
    "eva release status": ("backend.eva.release_demo.formatter", "format_release_status"),
    "eva release demo": ("backend.eva.release_demo.formatter", "format_release_demo"),
    "eva release commands": ("backend.eva.release_demo.formatter", "format_release_commands"),
    "eva release capability map": ("backend.eva.release_demo.formatter", "format_release_capability_map"),
    "eva release safety proof": ("backend.eva.release_demo.formatter", "format_release_safety_proof"),
    "eva release readiness": ("backend.eva.release_demo.formatter", "format_release_readiness"),
    "eva release limitations": ("backend.eva.release_demo.formatter", "format_release_limitations"),
    "eva release verification": ("backend.eva.release_demo.formatter", "format_release_verification"),
    "eva release smoke test": ("backend.eva.release_demo.formatter", "format_release_demo_smoke"),
    "eva release post push sync": ("backend.eva.release_demo.formatter", "format_release_post_push_sync"),
    # capability truth (aliases)
    "eva capability truth": ("backend.eva.security.capability_truth", "format_capability_truth"),
    "eva execution truth": ("backend.eva.security.capability_truth", "format_capability_truth"),
    "what can eva actually execute": ("backend.eva.security.capability_truth", "format_capability_truth"),
    # roadmap
    "eva roadmap status": ("backend.eva.roadmap.formatter", "format_phase_roadmap"),
    "eva execution boundaries": ("backend.eva.roadmap.formatter", "format_execution_boundary_audit"),
    "eva catalog status": ("backend.eva.roadmap.formatter", "format_catalog_status"),
    "eva frontend truth status": ("backend.eva.roadmap.formatter", "format_frontend_truth_status"),
    "eva grounded answer status": ("backend.eva.roadmap.formatter", "format_grounded_answer_status"),
    "eva voice reliability status": ("backend.eva.roadmap.formatter", "format_voice_reliability_status"),
    "eva verifier dashboard status": ("backend.eva.roadmap.formatter", "format_verifier_dashboard_status"),
    # news dashboard
    "eva news status": ("backend.eva.news_dashboard.formatter", "format_news_status"),
    "eva news policy": ("backend.eva.news_dashboard.formatter", "format_news_policy"),
    "eva news dashboard": ("backend.eva.news_dashboard.formatter", "format_news_dashboard"),
    "eva news topics": ("backend.eva.news_dashboard.formatter", "format_news_topics"),
    "eva news sources": ("backend.eva.news_dashboard.formatter", "format_news_sources"),
    "eva news freshness": ("backend.eva.news_dashboard.formatter", "format_news_freshness"),
    "eva news safety report": ("backend.eva.news_dashboard.formatter", "format_news_safety_report"),
    "eva news readiness": ("backend.eva.news_dashboard.formatter", "format_news_readiness"),
    # coding agent
    "eva coding status": ("backend.eva.coding_agent.formatter", "format_coding_status"),
    "eva coding policy": ("backend.eva.coding_agent.formatter", "format_coding_policy"),
    "eva coding specialists": ("backend.eva.coding_agent.formatter", "format_coding_specialists"),
    "eva coding task preview": ("backend.eva.coding_agent.formatter", "format_coding_task_preview"),
    "eva coding project context": ("backend.eva.coding_agent.formatter", "format_coding_project_context"),
    "eva coding patch plan": ("backend.eva.coding_agent.formatter", "format_coding_patch_plan"),
    "eva coding review checklist": ("backend.eva.coding_agent.formatter", "format_coding_review_checklist"),
    "eva coding test plan": ("backend.eva.coding_agent.formatter", "format_coding_test_plan"),
    "eva coding risk review": ("backend.eva.coding_agent.formatter", "format_coding_risk_review"),
    "eva coding handoff": ("backend.eva.coding_agent.formatter", "format_coding_handoff"),
    "eva coding blocked actions": ("backend.eva.coding_agent.formatter", "format_coding_blocked_actions"),
    "eva coding readiness": ("backend.eva.coding_agent.formatter", "format_coding_readiness"),
    # desktop control gate
    "eva desktop control status": ("backend.eva.desktop_control_gate.formatter", "format_desktop_control_status"),
    "eva desktop control policy": ("backend.eva.desktop_control_gate.formatter", "format_desktop_control_policy"),
    "eva desktop control actions": ("backend.eva.desktop_control_gate.formatter", "format_desktop_control_actions"),
    "eva desktop control dry run": ("backend.eva.desktop_control_gate.formatter", "format_desktop_control_dry_run"),
    "eva desktop control approvals": ("backend.eva.desktop_control_gate.formatter", "format_desktop_control_approvals"),
    "eva desktop control confirmations": ("backend.eva.desktop_control_gate.formatter", "format_desktop_control_confirmations"),
    "eva desktop control blocked actions": ("backend.eva.desktop_control_gate.formatter", "format_desktop_control_blocked_actions"),
    "eva desktop control readiness": ("backend.eva.desktop_control_gate.formatter", "format_desktop_control_readiness"),
    # desktop observation
    "eva desktop observe status": ("backend.eva.desktop_observation.formatter", "format_desktop_observe_status"),
    "eva desktop observe policy": ("backend.eva.desktop_observation.formatter", "format_desktop_observe_policy"),
    "eva desktop observe backend": ("backend.eva.desktop_observation.formatter", "format_desktop_observe_backend"),
    "eva desktop observe mock": ("backend.eva.desktop_observation.formatter", "format_desktop_observe_mock"),
    "eva desktop observe safety report": ("backend.eva.desktop_observation.formatter", "format_desktop_observe_safety_report"),
    "eva desktop observe sensitive screens": ("backend.eva.desktop_observation.formatter", "format_desktop_observe_sensitive_screens"),
    "eva desktop observe redaction policy": ("backend.eva.desktop_observation.formatter", "format_desktop_observe_redaction_policy"),
    "eva desktop observe readiness": ("backend.eva.desktop_observation.formatter", "format_desktop_observe_readiness"),
}


def _resolve(normalized: str) -> Callable[[], str] | None:
    entry = STATUS_COMMANDS.get(normalized)
    if entry is None:
        return None
    module_path, func_name = entry
    module = importlib.import_module(module_path)
    return getattr(module, func_name)


def dispatch_status_command(normalized: str) -> str | None:
    """Return the report text for an exact-match status command, or None."""
    formatter = _resolve(normalized)
    if formatter is None:
        return None
    return formatter()
