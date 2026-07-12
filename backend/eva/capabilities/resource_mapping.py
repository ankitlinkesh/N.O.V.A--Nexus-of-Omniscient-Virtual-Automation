from __future__ import annotations

from dataclasses import asdict, dataclass

from .permissions import evaluate_capability_permission, get_capability_permission
from .registry import build_default_registry
from .tool_schemas import capability_to_tool_schema
from ..resources.registry import evaluate_resource_by_id, get_resource


@dataclass(frozen=True)
class CapabilityResourceLink:
    capability_id: str
    resource_id: str
    provider: str
    agent: str | None
    execution_path: str
    available_now: bool
    preview_only: bool
    notes: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityResolution:
    capability_id: str
    capability_name: str
    permission_summary: str
    resource_id: str | None
    resource_status: str
    provider: str
    agent: str | None
    tool_schema_available: bool
    execution_path: str
    available_now: bool
    preview_only: bool
    allowed_in_public_mode: bool
    requires_confirmation: bool
    requires_override: bool
    risk_level: str
    final_status: str
    reason: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


_ALIASES = {
    "llm_fallback_chain": "llm.fallback_chain", "llm_fallback_simulate": "llm.fallback_simulate", "llm_degraded_mode": "llm.degraded_mode", "llm_session_limits": "llm.session_limits", "llm_rate_limits": "llm.rate_limits", "llm_routing_audit_preview": "llm.routing_audit_preview", "llm_failure_modes": "llm.failure_modes", "llm_runaway_protection": "llm.runaway_protection",
    "llm_status": "llm.status", "llm_providers": "llm.providers", "llm_routing_policy": "llm.routing_policy", "llm_fallback_policy": "llm.fallback_policy", "llm_limits": "llm.limits", "llm_structured_output": "llm.structured_output", "llm_route_preview": "llm.route_preview", "llm_readiness": "llm.readiness",
    "research_memory.save": "research_memory.import_note",
    "research_memory.import": "research_memory.import_note",
    "research_memory.export": "research_memory.export_json",
    "public_release.status": "public_release.public_status",
    "public_release.demo": "public_release.demo_scenarios",
    "public_release.safety_test": "public_release.safety_simulator",
    "public_release.doctor": "public_release.ready_check",
    "public_release.hardening": "public_release.hardening_audit",
    "eva_v2.route": "eva_v2.route_preview",
    "eva_v2.plan": "eva_v2.plan_preview",
    "file.inspect": "file.inspect_path",
    "file.preview": "file.preview_text",
    "file.summarize": "file.summarize_text",
    "file.understand": "file.understand_text",
    "file.search": "file.search_name",
    "file.structure": "file.explain_project_structure",
    "file.inventory": "file.project_inventory",
    "file.project": "file.project_explain",
    "file.draft_create": "file.draft_create_preview",
    "file.draft_append": "file.draft_append_preview",
    "file.draft_replace": "file.draft_replace_preview",
    "file.draft_diff": "file.diff_preview",
    "file.draft_readme": "file.draft_readme_section",
    "file.draft_summary": "file.draft_project_summary",
    "file.draft_report": "file.draft_report_outline",
    "file.draft_todo": "file.draft_project_todo",
    "file.apply": "file.apply_readiness",
    "file.write_safety": "file.write_safety_policy",
    "file.rollback": "file.rollback_plan",
    "file.verify_write": "file.verification_plan",
    "file.approval_create": "file.approval_request_create",
    "file.approval_pending": "file.approval_list_pending",
    "file.approval_approve": "file.approval_approve_future",
    "file.sandbox_apply": "file.sandbox_apply_approved",
    "file.sandbox_verify": "file.sandbox_verify_apply",
    "file.sandbox_rollback": "file.sandbox_rollback_apply",
    "file.apply_executor": "file.apply_executor_status",
    "file.real_policy": "file.real_apply_policy",
    "file.real_eligibility": "file.real_apply_eligibility",
    "file.real_create": "file.real_create_new_text_file",
    "file.real_verify": "file.real_verify_new_text_file",
    "file.real_rollback": "file.real_rollback_new_text_file",
    "file.real_create_eligibility": "file.real_apply_eligibility",
    "file.real_create_safe_text": "file.real_create_new_text_file",
    "file.real_create_verify": "file.real_verify_new_text_file",
    "file.real_create_rollback": "file.real_rollback_new_text_file",
    "browser": "browser.status",
    "browser_status": "browser.status",
    "browser_policy": "browser.policy",
    "browser_blocked": "browser.blocked_actions",
    "browser_domain_policy": "browser.domain_policy",
    "browser_action_safety": "browser.action_safety_preview",
    "browser_readiness": "browser.readiness",
    "browser_session_status": "browser.session_status",
    "browser_session_preview": "browser.session_preview",
    "browser_sessions": "browser.sessions_list",
    "browser_session_plan": "browser.session_plan",
    "browser_session_readiness": "browser.session_readiness",
    "browser_page_summary_policy": "browser.page_summary_policy",
    "browser_page_summary_preview": "browser.page_summary_preview",
    "browser_dom_summary_policy": "browser.dom_summary_policy",
    "browser_text_extraction_policy": "browser.text_extraction_policy",
    "browser_observation_readiness": "browser.observation_readiness",
    "browser_redaction_policy": "browser.redaction_policy",
    "browser_action_dry_run": "browser.action_dry_run",
    "browser_action_plan_preview": "browser.action_plan_preview",
    "browser_action_risk": "browser.action_risk",
    "browser_action_approvals": "browser.action_approvals",
    "browser_dry_run_policy": "browser.dry_run_policy",
    "browser_action_readiness": "browser.action_readiness",
    "browser_domain_check": "browser.domain_check",
    "browser_site_risk": "browser.site_risk",
    "browser_domain_rules": "browser.domain_rules",
    "browser_sensitive_sites": "browser.sensitive_sites",
    "browser_domain_approvals": "browser.domain_approvals",
    "browser_domain_readiness": "browser.domain_readiness",
    "browser_readonly_readiness": "browser.readonly_readiness",
    "browser_readiness_proof": "browser.readiness_proof",
    "browser_safety_proof": "browser.safety_proof",
    "browser_readiness_gaps": "browser.readiness_gaps",
    "browser_locked_status": "browser.locked_status",
    "browser_phase13_proof": "browser.phase13_proof",
    "browser_phase13_status": "browser.phase13_status",
    "browser_phase13_summary": "browser.phase13_summary",
    "browser_phase13_limits": "browser.phase13_limits",
    "browser_phase13_ready": "browser.phase13_ready",
    "browser_phase13_final_proof": "browser.phase13_final_proof",
    "desktop": "desktop.status",
    "desktop_status": "desktop.status",
    "desktop_policy": "desktop.policy",
    "desktop_blocked_actions": "desktop.blocked_actions",
    "desktop_action_safety": "desktop.action_safety_preview",
    "desktop_app_risk": "desktop.app_risk",
    "desktop_readiness": "desktop.readiness",
    "desktop_session_status": "desktop.session_status",
    "desktop_sessions": "desktop.sessions_list",
    "desktop_session_preview": "desktop.session_preview",
    "desktop_session_plan": "desktop.session_plan",
    "desktop_app_status_preview": "desktop.app_status_preview",
    "desktop_window_status_preview": "desktop.window_status_preview",
    "desktop_active_context_preview": "desktop.active_context_preview",
    "desktop_observation_readiness": "desktop.observation_readiness",
    "desktop_screen_policy": "desktop.screen_policy",
    "desktop_screen_observation_policy": "desktop.screen_observation_policy",
    "desktop_sensitive_screens": "desktop.sensitive_screens",
    "desktop_screen_redaction_policy": "desktop.screen_redaction_policy",
    "desktop_screen_capture_gate": "desktop.screen_capture_gate",
    "desktop_screen_readiness": "desktop.screen_readiness",
    "desktop_observation_policy": "desktop.observation_policy",
    "desktop_phase14_status": "desktop.phase14_status",
    "desktop_phase14_summary": "desktop.phase14_summary",
    "desktop_phase14_limits": "desktop.phase14_limits",
    "desktop_phase14_ready": "desktop.phase14_ready",
    "desktop_phase14_final_proof": "desktop.phase14_final_proof",
    "desktop_readiness_proof": "desktop.readiness_proof",
    "desktop_locked_status": "desktop.locked_status",
    "desktop_readiness_gaps": "desktop.readiness_gaps",
    "eva.ask_router": "eva.ask",
    "eva.router": "eva.natural_router",
    "eva.authority": "eva.authority_status",
    "eva.authority_preview": "eva.authority_decision_preview",
    "eva.smoke": "eva.smoke_status",
    "eva.verify_quick": "eva.verify_quick_command",
    "eva.verify_full": "eva.verify_full_command",
    "eva.phase12": "eva.phase12_status",
    "eva.phase12_ready": "eva.phase12_ready",
    "eva.phase12_summary": "eva.phase12_summary",
    "eva.phase12_limits": "eva.phase12_limits",
    "eva.phase12_proof": "eva.phase12_proof",
    "eva.ux": "eva.ux_status",
    "eva.control": "eva.control_center_status",
    "eva.control_center": "eva.control_center_status",
    "eva.control_summary": "eva.control_center_summary",
    "eva.dashboard": "eva.control_center_dashboard",
    "eva.status_dashboard": "eva.control_center_status",
    "eva.sessions": "eva.work_sessions_status",
    "eva.work": "eva.work_sessions_status",
    "eva.latest_session": "eva.latest_work_session",
    "eva.audit": "eva.audit_timeline",
    "eva.locked": "eva.locked_features",
    "eva.enabled": "eva.enabled_features",
    "eva.next_safe": "eva.next_safe_step",
    "eva.golden": "eva.golden_workflows_status",
    "eva.golden_status": "eva.golden_workflow_status",
    "eva.golden_test_plan": "eva.golden_workflow_test_plan",
    "eva.golden_proof": "eva.golden_workflow_proof",
    "eva.golden_project_note": "eva.golden_workflow_project_note",
    "eva.golden_continue": "eva.golden_workflow_continue",
    "eva.golden_demo": "eva.golden_workflow_demo",
    "eva.specialists": "eva.specialists_status",
    "eva.specialist": "eva.specialist_select",
    "eva.skills": "eva.skills_status",
    "eva.skill": "eva.skill_select",
    "eva.workflow": "eva.workflow_select",
    "eva.project_note_workflow": "eva.fileagent_project_note_workflow",
    "eva.latest_workflow": "eva.workflow_state",
    "eva.workflow_latest": "eva.workflow_state",
    "eva.file_latest": "eva.file_latest_status",
    "eva.project": "eva.project_inspect",
    "eva.project_status": "eva.project_inspect",
    "eva.project_reality": "eva.project_reality_check",
    "eva.project_changes": "eva.project_recent_changes",
    "eva.project_next": "eva.project_next_step",
    "eva.proof": "eva.project_proof",
    "eva.done": "eva.done_check",
}

_VIRTUAL_NAMES = {
    "research_memory.delete_item": "Delete Research Memory Item",
    "research_memory.clear_topic": "Clear Research Memory Topic",
    "research_memory.vector_status": "Research Memory Vector Status",
    "research_memory.vector_search": "Research Memory Vector Search",
    "eva_v2.execute_safe": "Eva v2 Safe Execution Bridge",
    "reference.odysseus_ai_workspace": "Odysseus AI Workspace Reference",
    "reference.memos_memory_operating_system": "MemOS Memory Operating System Reference",
    "reference.tradingagents": "TradingAgents Reference",
    "reference.agency_agents": "Agency Agents Reference",
}


def _link(
    capability_id: str,
    resource_id: str,
    provider: str,
    *,
    agent: str | None = None,
    execution_path: str = "fast_command",
    available_now: bool = True,
    preview_only: bool = False,
    notes: str = "Metadata-only capability-resource link.",
) -> CapabilityResourceLink:
    return CapabilityResourceLink(
        capability_id=capability_id,
        resource_id=resource_id,
        provider=provider,
        agent=agent,
        execution_path=execution_path,
        available_now=available_now,
        preview_only=preview_only,
        notes=notes,
    )


_LINKS: tuple[CapabilityResourceLink, ...] = (
    _link("research_memory.status", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="fast_command", notes="Read-only local Research Memory status."),
    _link("research_memory.help", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="fast_command", notes="Read-only local Research Memory help."),
    _link("research_memory.recent", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="fast_command", notes="Read-only recent local notes."),
    _link("research_memory.topics", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="fast_command", notes="Read-only topic listing."),
    _link("research_memory.search", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="read_only_delegate", notes="Lexical local Research Memory search."),
    _link("research_memory.retrieve", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="read_only_delegate", notes="Ranked local Research Memory retrieval."),
    _link("research_memory.topic_summary", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="read_only_delegate", notes="Read-only topic summary from local notes."),
    _link("research_memory.import_note", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="fast_command", notes="Explicit local write through sanitized import command."),
    _link("research_memory.export_json", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="fast_command", notes="Explicit local export of sanitized stored notes."),
    _link("research_memory.delete_item", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="future_permission_gated", available_now=False, preview_only=True, notes="Scoped local delete requires explicit item id and confirmation."),
    _link("research_memory.clear_topic", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="future_permission_gated", available_now=False, preview_only=True, notes="Scoped topic clear requires the confirm phrase."),
    _link("research_memory.stats", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="fast_command", notes="Read-only path-free local stats."),
    _link("research_memory.tags", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="fast_command", notes="Read-only tag counts."),
    _link("research_memory.quality", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="fast_command", notes="Read-only quality warnings; no cleanup runs."),
    _link("research_memory.duplicates_preview", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="fast_command", preview_only=True, notes="Preview duplicate groups only."),
    _link("research_memory.ranking_status", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="fast_command", notes="Read-only ranking status."),
    _link("research_memory.recall_stats", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="fast_command", notes="Read-only recall stats with hashed query references."),
    _link("research_memory.promote_candidates", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="fast_command", preview_only=True, notes="Preview-only promotion candidates; no write."),
    _link("research_memory.review_memory", "eva-research-memory-v2", "Research Memory", agent="ResearchAgent", execution_path="fast_command", notes="Read-only local memory review."),
    _link("research_memory.vector_status", "eva-research-memory-vector-index", "Research Memory", agent="ResearchAgent", execution_path="fast_command", preview_only=True, notes="Vector interface status only; vector search remains disabled by default."),
    _link("research_memory.vector_search", "eva-research-memory-vector-index", "Research Memory", agent="ResearchAgent", execution_path="disabled_reference", available_now=False, preview_only=True, notes="Experimental vector search interface disabled by default. Lexical retrieval remains primary."),
    _link("file.inspect_path", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_read_only_command", notes="Repo-scoped read-only file/folder metadata inspection through FileAgent path policy."),
    _link("file.list_folder", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_read_only_command", notes="Limited folder listing; skips runtime and sensitive paths."),
    _link("file.search_name", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_read_only_command", notes="Filename-only search inside allowed project scope."),
    _link("file.preview_text", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_read_only_command", notes="Safe text/code/docs preview with size limits and secret path refusals."),
    _link("file.explain_project_structure", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_read_only_command", notes="Limited project structure preview; no whole-drive scan."),
    _link("file.understand_text", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_read_only_command", notes="Heuristic local text/code/docs understanding; no cloud or LLM summary."),
    _link("file.summarize_text", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_read_only_command", notes="Alias for heuristic local text/code/docs summary."),
    _link("file.project_inventory", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_read_only_command", notes="Bounded read-only repo/project inventory; skips runtime and sensitive paths."),
    _link("file.project_explain", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_read_only_command", notes="Heuristic project explanation from safe inventory and key files."),
    _link("file.project_missing", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_read_only_command", notes="Read-only missing recommended docs/config checklist."),
    _link("file.project_dependencies", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_read_only_command", notes="Shallow dependency/config detection without printing secret-like values."),
    _link("file.draft_create_preview", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_preview_command", preview_only=True, notes="Output-only create draft preview; no file is created."),
    _link("file.draft_append_preview", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_preview_command", preview_only=True, notes="Output-only append draft and diff preview; no file is modified."),
    _link("file.draft_replace_preview", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_preview_command", preview_only=True, notes="Output-only replacement draft and diff preview; no file is modified."),
    _link("file.diff_preview", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_preview_command", preview_only=True, notes="Output-only unified diff preview; no patch is applied."),
    _link("file.draft_readme_section", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_preview_command", preview_only=True, notes="Output-only README section draft."),
    _link("file.draft_project_summary", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_preview_command", preview_only=True, notes="Output-only project summary draft from read-only inventory."),
    _link("file.draft_report_outline", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_preview_command", preview_only=True, notes="Output-only report outline draft."),
    _link("file.draft_project_todo", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_preview_command", preview_only=True, notes="Output-only project TODO draft from read-only inventory."),
    _link("file.apply_readiness", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_preview_command", preview_only=True, notes="Planning-only apply readiness; no write, backup, restore, or rollback occurs."),
    _link("file.write_safety_policy", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_preview_command", preview_only=True, notes="Planning-only write safety policy for a path."),
    _link("file.rollback_plan", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_preview_command", preview_only=True, notes="Planning-only rollback design; no backup or restore occurs."),
    _link("file.verification_plan", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="explicit_preview_command", preview_only=True, notes="Planning-only future write verification checklist."),
    _link("file.approval_status", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="approval_metadata_only", notes="Read-only approval ledger status; no file apply."),
    _link("file.approval_request_create", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="approval_metadata_only", preview_only=True, notes="Creates local approval metadata for future apply only; no target file write."),
    _link("file.approval_list_pending", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="approval_metadata_only", notes="Lists pending approval metadata only."),
    _link("file.approval_view", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="approval_metadata_only", notes="Views one approval metadata record."),
    _link("file.approval_approve_future", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="approval_metadata_only", preview_only=True, notes="Marks metadata approved for future apply only; actual apply is unavailable."),
    _link("file.approval_deny", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="approval_metadata_only", preview_only=True, notes="Marks metadata denied; no audit record is deleted."),
    _link("file.approval_cancel", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="approval_metadata_only", preview_only=True, notes="Marks metadata cancelled; no target file change."),
    _link("file.approval_events", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="approval_metadata_only", notes="Shows audit events for approval metadata."),
    _link("file.approval_expire", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="approval_metadata_only", preview_only=True, notes="Expires old approval metadata; no records are deleted."),
    _link("file.apply_executor_status", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="sandbox_only_executor", notes="Shows sandbox apply executor status; no real apply."),
    _link("file.sandbox_apply_policy", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="sandbox_only_executor", notes="Explains sandbox-only apply policy."),
    _link("file.sandbox_apply_approved", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="sandbox_only_executor", notes="Applies approved metadata inside ignored FileAgent sandbox only; future apply to real files remains unavailable."),
    _link("file.sandbox_verify_apply", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="sandbox_only_executor", notes="Verifies sandbox apply result only; no real file readback."),
    _link("file.sandbox_rollback_apply", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="sandbox_only_executor", notes="Rolls back sandbox state only; no real file restore."),
    _link("file.real_apply_policy", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="fast_command", notes="Read-only Phase 12L create-new-text-file policy."),
    _link("file.real_apply_eligibility", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="approval_check", preview_only=True, notes="Checks one approval for narrow create-new-text-file eligibility; no file write."),
    _link("file.real_create_new_text_file", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="exact_confirmation_real_create_gate", notes="Creates one new .md/.txt file in docs/ or samples/ only after exact approved confirmation."),
    _link("file.real_verify_new_text_file", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="verification", notes="Verifies an Eva-created Phase 12L file by hash."),
    _link("file.real_rollback_new_text_file", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="exact_confirmation_rollback_gate", notes="Removes only an unchanged Eva-created Phase 12L file after exact rollback confirmation."),
    _link("file.real_create_eligibility", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="approval_check", preview_only=True, notes="Compatibility alias for Phase 12L eligibility."),
    _link("file.real_create_safe_text", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="exact_confirmation_real_create_gate", notes="Compatibility alias for Phase 12L create-new-text-file."),
    _link("file.real_create_verify", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="verification", notes="Compatibility alias for Phase 12L verification."),
    _link("file.real_create_rollback", "eva-file-agent-v1", "FileAgent", agent="FileAgent", execution_path="exact_confirmation_rollback_gate", notes="Compatibility alias for Phase 12L rollback."),
    _link("browser.status", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only BrowserAgent safety status; no browser control."),
    _link("browser.policy", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only browser policy summary; real browser control remains locked."),
    _link("browser.blocked_actions", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only blocked browser action list."),
    _link("browser.domain_policy", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only domain/privacy policy preview."),
    _link("browser.action_safety_preview", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only action safety preview; no browser action is executed."),
    _link("browser.readiness", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only BrowserAgent readiness status."),
    _link("browser.session_status", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only preview browser session status; no browser is launched."),
    _link("browser.session_preview", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Creates a local preview-only session record; no browser execution."),
    _link("browser.sessions_list", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Lists preview-only browser session records."),
    _link("browser.session_plan", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only future browser session lifecycle plan."),
    _link("browser.session_readiness", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only BrowserAgent session readiness gaps."),
    _link("browser.page_summary_policy", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only page summary design policy; no live page read."),
    _link("browser.page_summary_preview", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Mock-text page summary preview; no browser observation."),
    _link("browser.dom_summary_policy", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only DOM summary schema policy; no DOM access."),
    _link("browser.text_extraction_policy", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only text extraction policy; no live extraction."),
    _link("browser.observation_readiness", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only observation readiness gaps."),
    _link("browser.redaction_policy", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only redaction policy for future browser observation."),
    _link("browser.action_dry_run", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Text-only browser action dry-run; no browser execution."),
    _link("browser.action_plan_preview", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Dry-run browser action plan preview."),
    _link("browser.action_risk", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only risk preview for browser actions."),
    _link("browser.action_approvals", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only future approval requirements for browser action types."),
    _link("browser.dry_run_policy", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only BrowserAgent dry-run policy."),
    _link("browser.action_readiness", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only readiness gaps for future browser action execution."),
    _link("browser.domain_check", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="String-only domain policy check; no DNS, network, browser, screenshot, DOM, cookie, or profile access."),
    _link("browser.site_risk", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only site risk classification from a provided domain or URL string."),
    _link("browser.domain_rules", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only BrowserAgent domain rule summary."),
    _link("browser.sensitive_sites", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only sensitive site category summary."),
    _link("browser.domain_approvals", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only future approval requirements for sensitive site categories."),
    _link("browser.domain_readiness", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only readiness gaps for future domain-gated browser observation."),
    _link("browser.readonly_readiness", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only BrowserAgent readiness proof; no browser read-only mode is enabled."),
    _link("browser.readiness_proof", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only checklist proof over safety, session, observation, action, and domain layers."),
    _link("browser.safety_proof", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only proof that browser execution remains locked."),
    _link("browser.readiness_gaps", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only list of missing future read-only browser gates."),
    _link("browser.locked_status", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only locked browser execution status."),
    _link("browser.phase13_proof", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only Phase 13 BrowserAgent proof summary."),
    _link("browser.phase13_status", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only final Phase 13 status; browser read-only/control remains locked."),
    _link("browser.phase13_summary", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only final Phase 13 safety/readiness summary."),
    _link("browser.phase13_limits", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only final Phase 13 limits and locked execution categories."),
    _link("browser.phase13_ready", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only final Phase 13 ready check as a safety/readiness foundation."),
    _link("browser.phase13_final_proof", "eva-browser-agent-safety", "BrowserAgent", agent="BrowserAgent", execution_path="fast_command", notes="Read-only final proof that Phase 13 enables no browser/network/page/control execution."),
    _link("browser_read.status", "eva-browser-agent-safety", "Real Browser Read-Only Mode", agent="BrowserAgent", execution_path="fast_command", notes="Phase 24 read-only status; browser control remains locked."),
    _link("browser_read.policy", "eva-browser-agent-safety", "Real Browser Read-Only Mode", agent="BrowserAgent", execution_path="fast_command", notes="Public-URL observation, isolation, and action-boundary policy."),
    _link("browser_read.url_policy", "eva-browser-agent-safety", "Real Browser Read-Only Mode", agent="SafetyAgent", execution_path="fast_command", notes="Local public URL validation and blocked-class report."),
    _link("browser_read.observe", "eva-browser-agent-safety", "Real Browser Read-Only Mode", agent="BrowserAgent", execution_path="fast_command", notes="Observation/report output only; unavailable-safe when no backend exists."),
    _link("browser_read.mock_observe", "eva-browser-agent-safety", "Real Browser Read-Only Mode", agent="BrowserAgent", execution_path="fast_command", notes="Deterministic redacted fixture observation only."),
    _link("browser_read.safety_report", "eva-browser-agent-safety", "Real Browser Read-Only Mode", agent="SafetyAgent", execution_path="fast_command", notes="Phase 17 and Phase 20 integrated safety report only."),
    _link("browser_read.blocked_urls", "eva-browser-agent-safety", "Real Browser Read-Only Mode", agent="SafetyAgent", execution_path="fast_command", notes="Blocked URL class report only."),
    _link("browser_read.readiness", "eva-browser-agent-safety", "Real Browser Read-Only Mode", agent="BrowserAgent", execution_path="fast_command", notes="Phase 24 readiness; browser control and desktop execution remain locked."),
    _link("desktop_observe.status", "eva-desktop-agent-safety", "Real Desktop Observation Mode", agent="DesktopAgent", execution_path="fast_command", notes="Phase 25 observation-only status; desktop control remains locked."),
    _link("desktop_observe.policy", "eva-desktop-agent-safety", "Real Desktop Observation Mode", agent="DesktopAgent", execution_path="fast_command", notes="Explicit one-shot observation and locked-control policy."),
    _link("desktop_observe.backend", "eva-desktop-agent-safety", "Real Desktop Observation Mode", agent="DesktopAgent", execution_path="fast_command", notes="Unavailable-safe backend status; no screen is captured by this command."),
    _link("desktop_observe.mock", "eva-desktop-agent-safety", "Real Desktop Observation Mode", agent="DesktopAgent", execution_path="fast_command", notes="Deterministic redacted fixture observation only."),
    _link("desktop_observe.safety_report", "eva-desktop-agent-safety", "Real Desktop Observation Mode", agent="SafetyAgent", execution_path="fast_command", notes="Phase 17 and Phase 20 integrated safety report only."),
    _link("desktop_observe.sensitive_screens", "eva-desktop-agent-safety", "Real Desktop Observation Mode", agent="SafetyAgent", execution_path="fast_command", notes="Sensitive-screen classification and blocking policy."),
    _link("desktop_observe.redaction_policy", "eva-desktop-agent-safety", "Real Desktop Observation Mode", agent="SafetyAgent", execution_path="fast_command", notes="Local observation-output redaction policy."),
    _link("desktop_observe.readiness", "eva-desktop-agent-safety", "Real Desktop Observation Mode", agent="DesktopAgent", execution_path="fast_command", notes="Phase 25 readiness; desktop control remains locked."),
    _link("desktop_control.status", "eva-desktop-agent-safety", "Real Desktop Control Gate", agent="DesktopAgent", execution_path="fast_command", notes="Phase 26 local/mock gate status only."),
    _link("desktop_control.policy", "eva-desktop-agent-safety", "Real Desktop Control Gate", agent="SafetyAgent", execution_path="fast_command", notes="Policy and no-control boundaries only."),
    _link("desktop_control.actions", "eva-desktop-agent-safety", "Real Desktop Control Gate", agent="DesktopAgent", execution_path="fast_command", notes="Deterministic action catalog only."),
    _link("desktop_control.dry_run", "eva-desktop-agent-safety", "Real Desktop Control Gate", agent="DesktopAgent", execution_path="fast_command", notes="Local/mock dry-run report; no action execution."),
    _link("desktop_control.approvals", "eva-desktop-agent-safety", "Real Desktop Control Gate", agent="SafetyAgent", execution_path="fast_command", notes="Approval metadata only; approval cannot execute."),
    _link("desktop_control.confirmations", "eva-desktop-agent-safety", "Real Desktop Control Gate", agent="SafetyAgent", execution_path="fast_command", notes="Confirmation metadata only; confirmation cannot execute."),
    _link("desktop_control.blocked_actions", "eva-desktop-agent-safety", "Real Desktop Control Gate", agent="SafetyAgent", execution_path="fast_command", notes="Blocked action report only."),
    _link("desktop_control.readiness", "eva-desktop-agent-safety", "Real Desktop Control Gate", agent="DesktopAgent", execution_path="fast_command", notes="Phase 26 readiness; real desktop control remains locked."),
    *[_link(f"news.{name}","eva-browser-agent-safety","News / Web Intelligence Dashboard",agent="ResearchAgent",execution_path="fast_command",notes="Local/mock dashboard report only; no crawler or browser control.") for name in ("status","policy","dashboard","topics","sources","freshness","safety_report","readiness")],
    *[
        _link(
            f"coding.{name}",
            "eva-control-center",
            "Coding Specialist / CodingAgent Foundation",
            agent="CodeAgent",
            execution_path="fast_command",
            preview_only=True,
            notes="Phase 28 preview/report/status only; no source edits, patch application, execution, arbitrary file access, or new write path.",
        )
        for name in (
            "status",
            "policy",
            "specialists",
            "task_preview",
            "project_context",
            "patch_plan",
            "review_checklist",
            "test_plan",
            "risk_review",
            "handoff",
            "blocked_actions",
            "readiness",
        )
    ],
    *[
        _link(
            f"release.{name}",
            "eva-public-release-mode",
            "Public Demo / Release",
            agent="SafetyAgent",
            execution_path="fast_command",
            preview_only=True,
            notes="Phase 29 demo/report/status only; no publishing, git release operation, external action, execution, file access, or new write path.",
        )
        for name in (
            "status",
            "demo",
            "commands",
            "capability_map",
            "safety_proof",
            "readiness",
            "limitations",
            "verification",
            "demo_smoke",
            "post_push_sync",
        )
    ],
    *[
        _link(
            f"rc.{name}",
            "eva-release-candidate",
            "Release Candidate Hardening",
            agent="SafetyAgent",
            execution_path="fast_command",
            preview_only=True,
            notes="Phase 30 report/status/planning only; commit plan is text only and no Git, publish, execution, file-access, or new-write action is available.",
        )
        for name in (
            "status",
            "manifest",
            "commit_plan",
            "hardening_report",
            "checklist",
            "readiness",
            "safety_proof",
            "verification",
        )
    ],
    *[
        _link(
            f"roadmap.{name}",
            "eva-roadmap-foundations",
            "Roadmap Foundations",
            agent="SafetyAgent",
            execution_path="fast_command",
            preview_only=True,
            notes="Phase 33-42 report/status/catalog only; no new execution path is available and Phase 12L remains a gated write boundary.",
        )
        for name in (
            "execution_boundary_audit",
            "command_catalog",
            "capability_catalog",
            "control_truth_panels",
            "frontend_truth",
            "grounded_answers",
            "voice_reliability",
            "verifier_dashboard",
            "safe_real_pilot",
            "release_candidate_v2",
        )
    ],
    _link("desktop.status", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only DesktopAgent safety status; no screen observation or desktop control."),
    _link("desktop.policy", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only desktop policy summary; real screen observation and desktop control remain locked."),
    _link("desktop.blocked_actions", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only blocked desktop action list."),
    _link("desktop.action_safety_preview", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only desktop action safety preview; no desktop action is executed."),
    _link("desktop.app_risk", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="String-only app/category risk classification; no real apps or windows are inspected."),
    _link("desktop.readiness", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only DesktopAgent readiness status."),
    _link("desktop.session_status", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only preview desktop session status; no screen observation or desktop control."),
    _link("desktop.sessions_list", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Lists local preview-only desktop session records."),
    _link("desktop.session_preview", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Creates a local preview-only desktop session record; no real desktop observation/control."),
    _link("desktop.session_plan", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only future desktop session lifecycle plan."),
    _link("desktop.app_status_preview", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only app status schema preview; no real app inspection."),
    _link("desktop.window_status_preview", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only window status schema preview; no real window enumeration."),
    _link("desktop.active_context_preview", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only active context schema preview; no active app/window detection."),
    _link("desktop.observation_readiness", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only desktop observation readiness gaps."),
    _link("desktop.screen_policy", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only screen observation policy; no screen capture or screenshot."),
    _link("desktop.screen_observation_policy", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only future screen observation schema; real screen observation locked."),
    _link("desktop.sensitive_screens", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only sensitive-screen category policy."),
    _link("desktop.screen_redaction_policy", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only screen redaction policy preview."),
    _link("desktop.screen_capture_gate", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only capture gate requirements; capture remains locked."),
    _link("desktop.screen_readiness", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only screen observation readiness gaps."),
    _link("desktop.observation_policy", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only observation policy and safety decision preview."),
    _link("desktop.action_dry_run", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Text-only desktop action dry-run; no desktop execution."),
    _link("desktop.action_plan_preview", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only desktop action plan preview; no mouse, keyboard, clipboard, app, screen, or terminal execution."),
    _link("desktop.action_risk", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="String-only desktop action risk classification."),
    _link("desktop.action_approvals", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only future approval requirements for desktop action categories."),
    _link("desktop.dry_run_policy", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only desktop action dry-run policy."),
    _link("desktop.action_readiness", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only readiness gaps for future desktop action execution."),
    _link("desktop.risk_score", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="String-only desktop action risk score; no desktop execution."),
    _link("desktop.risk_factors", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only desktop action risk factor explanation."),
    _link("desktop.approval_required", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only future approval requirement explanation."),
    _link("desktop.safety_matrix", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only desktop action safety matrix."),
    _link("desktop.high_risk_actions", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only high-risk desktop action classes."),
    _link("desktop.risk_readiness", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only readiness gaps for future risk-gated desktop actions."),
    _link("desktop.approval_policy", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only DesktopAgent human approval policy; approvals do not unlock execution."),
    _link("desktop.approval_levels", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only DesktopAgent approval-level explanation."),
    _link("desktop.approval_preview", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only desktop approval preview for a request."),
    _link("desktop.confirmation_phrase", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only future confirmation phrase preview; no execution unlock."),
    _link("desktop.forbidden_actions", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only desktop forbidden-action class list."),
    _link("desktop.approval_audit_status", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only DesktopAgent approval audit schema/status."),
    _link("desktop.approval_readiness", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only readiness gaps for future desktop approval gates."),
    _link("llm.status", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="Mock-only router status."),
    _link("llm.providers", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="Provider metadata only."),
    _link("llm.routing_policy", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="Dry-run routing policy."),
    _link("llm.fallback_policy", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="Fallback metadata only."),
    _link("llm.limits", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="Token/cost policy preview."),
    _link("llm.structured_output", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="Mock validation contract."),
    _link("llm.route_preview", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="No-call route preview."),
    _link("llm.readiness", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="Readiness status only."),
    _link("llm.validation_status", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Mock/local validation status; no live calls or execution."),
    _link("llm.schema_registry", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Preview-contract registry only."),
    _link("llm.validation_policy", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Invalid output is blocked before any execution path."),
    _link("llm.repair_policy", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Repair explanation only; it never executes or rewrites intent."),
    _link("llm.validate_mock", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Bundled local mock validation only."),
    _link("llm.validate_invalid_examples", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local blocked/refusal-preview examples only."),
    _link("llm.validation_readiness", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Readiness status only; live calls remain locked."),
    _link("llm.red_team_status", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local red-team status only."),
    _link("llm.red_team_cases", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local case catalog only."),
    _link("llm.red_team_run", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local simulated run only."),
    _link("llm.failure_tests", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Provider failures simulated only."),
    _link("llm.safety_failure_report", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Safe report only."),
    _link("llm.red_team_readiness", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Readiness status only."),
    _link("context.status", "eva-llm-router-contracts", "Context Assembly Engine", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local/mock context status only; no live LLM call or execution."),
    _link("context.sources", "eva-llm-router-contracts", "Context Assembly Engine", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Allowed/blocked source registry only; no arbitrary file reads."),
    _link("context.policy", "eva-llm-router-contracts", "Context Assembly Engine", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Context policy status only; injected context cannot become instruction."),
    _link("context.budget", "eva-llm-router-contracts", "Context Assembly Engine", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Budget/trimming policy only."),
    _link("context.assemble_preview", "eva-llm-router-contracts", "Context Assembly Engine", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Sanitized packet preview only; no live LLM call."),
    _link("context.grounding_report", "eva-llm-router-contracts", "Context Assembly Engine", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Grounding/exclusion report only."),
    _link("context.redaction_policy", "eva-llm-router-contracts", "Context Assembly Engine", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Redaction policy status only; no secret/config/session reads."),
    _link("context.readiness", "eva-llm-router-contracts", "Context Assembly Engine", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Readiness status only; Phase 17 is next."),
    _link("threat.status", "eva-llm-router-contracts", "LLM Threat Defense", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local/mock threat defense status only; no live LLM call or execution."),
    _link("threat.catalog", "eva-llm-router-contracts", "LLM Threat Defense", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local threat category catalog only."),
    _link("threat.policy", "eva-llm-router-contracts", "LLM Threat Defense", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Instruction hierarchy and policy report only."),
    _link("threat.scan_preview", "eva-llm-router-contracts", "LLM Threat Defense", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local scan preview only; defended context cannot execute tools."),
    _link("threat.injection_examples", "eva-llm-router-contracts", "LLM Threat Defense", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Prompt-injection examples only; no live call."),
    _link("threat.exfiltration_examples", "eva-llm-router-contracts", "LLM Threat Defense", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Exfiltration blocking examples only; no secret/config/session reads."),
    _link("threat.context_guard", "eva-llm-router-contracts", "LLM Threat Defense", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Context poisoning guard report only."),
    _link("threat.readiness", "eva-llm-router-contracts", "LLM Threat Defense", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Readiness status only; Phase 18 is next."),
    _link("agent_loop.status", "eva-agent-loop-v1", "Agent Loop v1", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local/mock Agent Loop status only; no live LLM call or execution."),
    _link("agent_loop.policy", "eva-agent-loop-v1", "Agent Loop v1", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Loop policy report only."),
    _link("agent_loop.run_preview", "eva-agent-loop-v1", "Agent Loop v1", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Deterministic preview loop only; actions are preview-only."),
    _link("agent_loop.steps", "eva-agent-loop-v1", "Agent Loop v1", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Stage and step-limit report only."),
    _link("agent_loop.action_previews", "eva-agent-loop-v1", "Agent Loop v1", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Action preview model only; tools are not executed."),
    _link("agent_loop.safety_report", "eva-agent-loop-v1", "Agent Loop v1", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Safety report only; no browser, desktop, shell, cloud, or MCP execution."),
    _link("agent_loop.stop_reasons", "eva-agent-loop-v1", "Agent Loop v1", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Stop-reason policy only."),
    _link("agent_loop.readiness", "eva-agent-loop-v1", "Agent Loop v1", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Readiness status only; Phase 19 is next."),
    _link("workflow_planner.status", "eva-agentic-workflow-planner", "Agentic Workflow Planner", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local/mock workflow planner status only; no live LLM call or execution."),
    _link("workflow_planner.catalog", "eva-agentic-workflow-planner", "Agentic Workflow Planner", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Workflow template catalog only."),
    _link("workflow_planner.policy", "eva-agentic-workflow-planner", "Agentic Workflow Planner", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Workflow safety policy only."),
    _link("workflow_planner.preview", "eva-agentic-workflow-planner", "Agentic Workflow Planner", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Deterministic workflow preview only; workflow steps are preview-only."),
    _link("workflow_planner.dependencies", "eva-agentic-workflow-planner", "Agentic Workflow Planner", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Dependency validation report only."),
    _link("workflow_planner.approvals", "eva-agentic-workflow-planner", "Agentic Workflow Planner", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Approval preview metadata only; no execution unlocked."),
    _link("workflow_planner.rollback", "eva-agentic-workflow-planner", "Agentic Workflow Planner", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Rollback preview metadata only."),
    _link("workflow_planner.readiness", "eva-agentic-workflow-planner", "Agentic Workflow Planner", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Readiness status only; Phase 20 is next."),
    _link("execution_gates.status", "eva-controlled-execution-gates", "Controlled Execution Gates", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local/mock gate status only; no live LLM call or execution."),
    _link("execution_gates.policy", "eva-controlled-execution-gates", "Controlled Execution Gates", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Gate policy report only; no execution unlocked."),
    _link("execution_gates.evaluate", "eva-controlled-execution-gates", "Controlled Execution Gates", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Deterministic local gate evaluation only; tools are not executed."),
    _link("execution_gates.approvals", "eva-controlled-execution-gates", "Controlled Execution Gates", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Approval policy metadata only; approval alone does not execute."),
    _link("execution_gates.confirmations", "eva-controlled-execution-gates", "Controlled Execution Gates", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Confirmation policy metadata only; confirmation alone does not execute unless an existing implemented gate accepts it."),
    _link("execution_gates.rollback", "eva-controlled-execution-gates", "Controlled Execution Gates", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Rollback metadata preview only."),
    _link("execution_gates.blocked_actions", "eva-controlled-execution-gates", "Controlled Execution Gates", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Blocked action class report only."),
    _link("execution_gates.readiness", "eva-controlled-execution-gates", "Controlled Execution Gates", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Readiness status only; Phase 21 Memory v3 is next."),
    _link("memory_v3.status", "eva-memory-v3", "Memory v3", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local-only Memory v3 status; no live call or execution."),
    _link("memory_v3.policy", "eva-memory-v3", "Memory v3", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local-only memory policy report."),
    _link("memory_v3.sources", "eva-memory-v3", "Memory v3", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local-only source and trust model report."),
    _link("memory_v3.privacy", "eva-memory-v3", "Memory v3", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local-only privacy policy report."),
    _link("memory_v3.freshness", "eva-memory-v3", "Memory v3", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local-only freshness policy report."),
    _link("memory_v3.conflicts", "eva-memory-v3", "Memory v3", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local-only conflict policy report."),
    _link("memory_v3.retrieval_preview", "eva-memory-v3", "Memory v3", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Deterministic bundled retrieval preview; no database dump or context injection."),
    _link("memory_v3.readiness", "eva-memory-v3", "Memory v3", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Phase 21 readiness status only."),
    _link("voice.status", "eva-voice-assistant-foundation", "Voice Assistant Foundation", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Local/mock voice status only; audio devices remain locked."),
    _link("voice.policy", "eva-voice-assistant-foundation", "Voice Assistant Foundation", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Voice lifecycle and response policy report only."),
    _link("voice.providers", "eva-voice-assistant-foundation", "Voice Assistant Foundation", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Locked ASR/TTS provider candidate metadata only."),
    _link("voice.listen_state", "eva-voice-assistant-foundation", "Voice Assistant Foundation", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Mock wake/listen state report only."),
    _link("voice.transcript_safety", "eva-voice-assistant-foundation", "Voice Assistant Foundation", agent="SafetyAgent", execution_path="fast_command", preview_only=True, notes="Transcript safety policy only; no transcription occurs."),
    _link("voice.route_preview", "eva-voice-assistant-foundation", "Voice Assistant Foundation", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Bundled transcript route preview only; no action route."),
    _link("voice.confirmations", "eva-voice-assistant-foundation", "Voice Assistant Foundation", agent="SafetyAgent", execution_path="fast_command", preview_only=True, notes="Confirmation preview metadata only; confirmation does not execute."),
    _link("voice.readiness", "eva-voice-assistant-foundation", "Voice Assistant Foundation", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Phase 22 readiness status only."),
    _link("ai_os.status", "eva-ai-os-control-center", "AI OS / Control Center", agent="ControlCenterAgent", execution_path="fast_command", preview_only=True, notes="Local AI OS status only."),
    _link("ai_os.dashboard", "eva-ai-os-control-center", "AI OS / Control Center", agent="ControlCenterAgent", execution_path="fast_command", preview_only=True, notes="Deterministic local dashboard report only."),
    _link("ai_os.system_map", "eva-ai-os-control-center", "AI OS / Control Center", agent="ControlCenterAgent", execution_path="fast_command", preview_only=True, notes="Known system-state metadata only."),
    _link("ai_os.capability_matrix", "eva-ai-os-control-center", "AI OS / Control Center", agent="ControlCenterAgent", execution_path="fast_command", preview_only=True, notes="Capability state report only; no gate unlocked."),
    _link("ai_os.feature_states", "eva-ai-os-control-center", "AI OS / Control Center", agent="ControlCenterAgent", execution_path="fast_command", preview_only=True, notes="Feature-state policy report only."),
    _link("ai_os.safety_boundaries", "eva-ai-os-control-center", "AI OS / Control Center", agent="SafetyAgent", execution_path="fast_command", preview_only=True, notes="Safety-boundary report only."),
    _link("ai_os.locked_features", "eva-ai-os-control-center", "AI OS / Control Center", agent="SafetyAgent", execution_path="fast_command", preview_only=True, notes="Locked future-gate report only."),
    _link("ai_os.next_safe_step", "eva-ai-os-control-center", "AI OS / Control Center", agent="PlannerAgent", execution_path="fast_command", preview_only=True, notes="Next-phase recommendation metadata only."),
    _link("ai_os.readiness", "eva-ai-os-control-center", "AI OS / Control Center", agent="ControlCenterAgent", execution_path="fast_command", preview_only=True, notes="Phase 23 readiness status only."),
    _link("llm.fallback_chain", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="Mock-only fallback chain."),
    _link("llm.fallback_simulate", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="Deterministic failure simulation; no provider call."),
    _link("llm.degraded_mode", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="Status-only degraded mode."),
    _link("llm.session_limits", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="Policy-only session limits."),
    _link("llm.rate_limits", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="Simulated rate-limit policy."),
    _link("llm.routing_audit_preview", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="Secret-free local audit preview."),
    _link("llm.failure_modes", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="Status-only failure modes."),
    _link("llm.runaway_protection", "eva-llm-router-contracts", "LLM Router", agent="PlannerAgent", execution_path="fast_command", notes="Policy-only stop limit."),
    _link("desktop.phase14_status", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only final Phase 14 DesktopAgent status; real observation/control remains locked."),
    _link("desktop.phase14_summary", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only final Phase 14 safety/readiness summary."),
    _link("desktop.phase14_limits", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only final Phase 14 limits and locked execution categories."),
    _link("desktop.phase14_ready", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only Phase 14 ready check as a locked safety/readiness foundation."),
    _link("desktop.phase14_final_proof", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only final proof that Phase 14 enables no desktop observation or control."),
    _link("desktop.readiness_proof", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only DesktopAgent locked readiness proof."),
    _link("desktop.locked_status", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only locked DesktopAgent status."),
    _link("desktop.readiness_gaps", "eva-desktop-agent-safety", "DesktopAgent", agent="DesktopAgent", execution_path="fast_command", notes="Read-only gaps before future desktop gates."),
    _link("eva.ask", "eva-authority-router", "Eva Core", agent="PlannerAgent", execution_path="fast_command", notes="Natural-language wrapper over existing safe commands; no real execution beyond existing sandbox-only harness."),
    _link("eva.natural_router", "eva-authority-router", "Eva Core", agent="PlannerAgent", execution_path="preview_only", preview_only=True, notes="Deterministic local route classification; no LLM call."),
    _link("eva.authority_status", "eva-authority-router", "Eva Core", agent="SafetyAgent", execution_path="fast_command", notes="Read-only global authority spine status."),
    _link("eva.authority_decision_preview", "eva-authority-router", "Eva Core", agent="SafetyAgent", execution_path="preview_only", preview_only=True, notes="Authority decision preview only; no tool execution."),
    _link("eva.verify_all", "eva-authority-router", "Eva Core", agent="VerifierAgent", execution_path="local_verifier_runner", notes="Runs repo verifier scripts with current Python executable; no dependency setup or feature execution surfaces."),
    _link("eva.smoke_status", "eva-phase12-verification", "Eva Core", agent="VerifierAgent", execution_path="status_only", notes="Read-only Phase 12 smoke/quick verification status; does not start external commands."),
    _link("eva.verify_quick_command", "eva-phase12-verification", "Eva Core", agent="VerifierAgent", execution_path="manual_command_only", notes="Prints the quick verifier command only; no shell command is executed from chat."),
    _link("eva.verify_full_command", "eva-phase12-verification", "Eva Core", agent="VerifierAgent", execution_path="manual_command_only", notes="Prints the full verifier command only; no shell command is executed from chat."),
    _link("eva.phase12_status", "eva-phase12-verification", "Eva Core", agent="SafetyAgent", execution_path="fast_command", notes="Read-only Phase 12 status and locked-module summary."),
    _link("eva.phase12_ready", "eva-phase12-verification", "Eva Core", agent="VerifierAgent", execution_path="fast_command", notes="Read-only Phase 12 readiness and proof requirements."),
    _link("eva.phase12_summary", "eva-phase12-verification", "Eva Core", agent="VerifierAgent", execution_path="fast_command", notes="Read-only Phase 12 summary."),
    _link("eva.phase12_limits", "eva-phase12-verification", "Eva Core", agent="VerifierAgent", execution_path="fast_command", notes="Read-only Phase 12 limits and locked execution areas."),
    _link("eva.phase12_proof", "eva-phase12-verification", "Eva Core", agent="VerifierAgent", execution_path="fast_command", notes="Read-only verifier proof surfaces; no verifier subprocess runs."),
    _link("eva.ux_status", "eva-phase12-verification", "Eva Core", agent="SafetyAgent", execution_path="fast_command", notes="Read-only command UX status; no feature execution."),
    _link("eva.control_center_status", "eva-control-center", "Eva Core", agent="ControlCenterAgent", execution_path="fast_command", notes="Read-only Control Center status summary; no browser is opened."),
    _link("eva.control_center_summary", "eva-control-center", "Eva Core", agent="ControlCenterAgent", execution_path="fast_command", notes="Compact read-only Control Center summary; no verifier or tool is executed."),
    _link("eva.locked_features", "eva-control-center", "Eva Core", agent="ControlCenterAgent", execution_path="fast_command", notes="Read-only locked-feature explanation; no feature is enabled."),
    _link("eva.enabled_features", "eva-control-center", "Eva Core", agent="ControlCenterAgent", execution_path="fast_command", notes="Read-only enabled-feature summary; only Phase 12L narrow real create is listed as real write."),
    _link("eva.next_safe_step", "eva-control-center", "Eva Core", agent="ControlCenterAgent", execution_path="fast_command", notes="Read-only next-safe-step recommendation."),
    _link("eva.control_center_dashboard", "eva-control-center", "Eva Core", agent="ControlCenterAgent", execution_path="local_fastapi_route", notes="Local read-only dashboard route at /control."),
    _link("eva.control_center_status_json", "eva-control-center", "Eva Core", agent="ControlCenterAgent", execution_path="local_fastapi_route", notes="Safe JSON status endpoint at /control/status.json."),
    _link("eva.dashboard_url", "eva-control-center", "Eva Core", agent="ControlCenterAgent", execution_path="fast_command", notes="Prints the local dashboard URL only; does not open a browser."),
    _link("eva.work_sessions_status", "eva-control-center", "Eva Core", agent="ControlCenterAgent", execution_path="fast_command", notes="Read-only local WorkSession status; no task is executed."),
    _link("eva.work_sessions_recent", "eva-control-center", "Eva Core", agent="ControlCenterAgent", execution_path="fast_command", notes="Read-only recent WorkSession summaries."),
    _link("eva.work_session_timeline", "eva-control-center", "Eva Core", agent="ControlCenterAgent", execution_path="fast_command", notes="Read-only WorkSession event timeline."),
    _link("eva.audit_timeline", "eva-control-center", "Eva Core", agent="ControlCenterAgent", execution_path="fast_command", notes="Read-only latest audit timeline."),
    _link("eva.latest_work_session", "eva-control-center", "Eva Core", agent="ControlCenterAgent", execution_path="fast_command", notes="Read-only latest WorkSession detail."),
    _link("eva.golden_workflows_status", "eva-golden-workflows", "Eva Core", agent="FileAgent", execution_path="fast_command", notes="Read-only golden workflow status and next safe action."),
    _link("eva.golden_workflow_status", "eva-golden-workflows", "Eva Core", agent="FileAgent", execution_path="fast_command", notes="Read-only golden workflow status alias."),
    _link("eva.golden_workflow_test_plan", "eva-golden-workflows", "Eva Core", agent="FileAgent", execution_path="fast_command", notes="Read-only E2E golden workflow test plan."),
    _link("eva.golden_workflow_proof", "eva-golden-workflows", "Eva Core", agent="FileAgent", execution_path="fast_command", notes="Read-only latest golden workflow proof and WorkSession evidence."),
    _link("eva.golden_workflow_project_note", "eva-golden-workflows", "Eva Core", agent="FileAgent", execution_path="orchestrated_file_agent_gates", available_now=False, preview_only=True, notes="Starts safe project-note draft and approval flow; broad writes remain disabled."),
    _link("eva.golden_workflow_continue", "eva-golden-workflows", "Eva Core", agent="FileAgent", execution_path="orchestrated_exact_confirmation_gates", available_now=False, preview_only=True, notes="Continues workflow only through exact FileAgent confirmation gates."),
    _link("eva.golden_workflow_demo", "eva-golden-workflows", "Eva Core", agent="FileAgent", execution_path="demo_metadata", available_now=False, preview_only=True, notes="Demo path creates metadata only and does not broad-write files."),
    _link("eva.specialists_status", "eva-authority-router", "Eva Core", agent="PlannerAgent", execution_path="fast_command", notes="Read-only specialist role catalog."),
    _link("eva.specialist_select", "eva-authority-router", "Eva Core", agent="PlannerAgent", execution_path="route_preview", preview_only=True, notes="Selects specialist roles for a request; no task execution."),
    _link("eva.skills_status", "eva-authority-router", "Eva Core", agent="PlannerAgent", execution_path="fast_command", notes="Read-only skill catalog."),
    _link("eva.skill_select", "eva-authority-router", "Eva Core", agent="PlannerAgent", execution_path="route_preview", preview_only=True, notes="Selects safe skills for a request; no task execution."),
    _link("eva.workflow_select", "eva-golden-workflows", "Eva Core", agent="PlannerAgent", execution_path="route_preview", preview_only=True, notes="Selects a workflow plan; no workflow step is executed."),
    _link("eva.workflow_plan", "eva-golden-workflows", "Eva Core", agent="PlannerAgent", execution_path="workflow_preview", preview_only=True, notes="Formats workflow steps and next actions only."),
    _link("eva.fileagent_project_note_workflow", "eva-golden-workflows", "Eva Core", agent="FileAgent", execution_path="workflow_preview", preview_only=True, notes="Plans FileAgent project-note workflow through existing guarded gates; no broad file write."),
    _link("eva.workflow_state", "eva-golden-workflows", "Eva Core", agent="FileAgent", execution_path="fast_command", notes="Read-only latest FileAgent workflow state summary."),
    _link("eva.workflow_next_step", "eva-golden-workflows", "Eva Core", agent="FileAgent", execution_path="fast_command", notes="Read-only next-step guidance from local workflow state."),
    _link("eva.workflow_latest_approval", "eva-golden-workflows", "Eva Core", agent="FileAgent", execution_path="fast_command", notes="Read-only latest approval lookup with safe disambiguation."),
    _link("eva.workflow_latest_apply", "eva-golden-workflows", "Eva Core", agent="FileAgent", execution_path="fast_command", notes="Read-only latest sandbox/real-create/rollback lookup."),
    _link("eva.workflow_disambiguate", "eva-golden-workflows", "Eva Core", agent="FileAgent", execution_path="fast_command", preview_only=True, notes="Disambiguates multiple candidates without guessing or executing."),
    _link("eva.file_latest_status", "eva-golden-workflows", "Eva Core", agent="FileAgent", execution_path="fast_command", notes="Read-only FileAgent latest status surface."),
    _link("eva.project_inspect", "eva-control-center", "Eva Core", agent="ProjectInspectorAgent", execution_path="fast_command", notes="Read-only project inspection from FileAgent inventory and local status surfaces."),
    _link("eva.project_reality_check", "eva-control-center", "Eva Core", agent="RealityCheckerAgent", execution_path="fast_command", notes="Read-only evidence check; does not claim done without fresh verifier output."),
    _link("eva.project_recent_changes", "eva-control-center", "Eva Core", agent="ProjectInspectorAgent", execution_path="fast_command", notes="Read-only recent Phase 12 summary from local docs/status surfaces."),
    _link("eva.project_next_step", "eva-control-center", "Eva Core", agent="SafetyAgent", execution_path="fast_command", notes="Read-only recommended next safe phase."),
    _link("eva.project_proof", "eva-control-center", "Eva Core", agent="RealityCheckerAgent", execution_path="fast_command", notes="Read-only proof and limitations summary."),
    _link("eva.done_check", "eva-control-center", "Eva Core", agent="RealityCheckerAgent", execution_path="fast_command", notes="Read-only done check that requires fresh verifier evidence."),
    _link("eva_v2.agent_status", "eva-v2-runtime", "Eva v2", agent="RuntimeAgent", execution_path="fast_command", notes="Read-only bounded agent status."),
    _link("eva_v2.route_preview", "eva-v2-runtime", "Eva v2", agent="PlannerAgent", execution_path="v2_dry_run", preview_only=True, notes="Route preview only; no normal-chat v2 routing."),
    _link("eva_v2.plan_preview", "eva-v2-runtime", "Eva v2", agent="PlannerAgent", execution_path="v2_dry_run", preview_only=True, notes="Plan preview only."),
    _link("eva_v2.dry_run", "eva-v2-runtime", "Eva v2", agent="PlannerAgent", execution_path="v2_dry_run", preview_only=True, notes="Dry-run planning surface; no risky execution."),
    _link("eva_v2.read_only_delegation_status", "eva-v2-runtime", "Eva v2", agent="RuntimeAgent", execution_path="fast_command", notes="Read-only delegation status."),
    _link("eva_v2.execute_safe", "eva-v2-runtime", "Eva v2", agent="RuntimeAgent", execution_path="future_permission_gated", available_now=False, preview_only=True, notes="Safe execution bridge metadata only for future planner phases."),
    _link("public_release.public_status", "eva-public-release-mode", "Public Release", agent="SafetyAgent", execution_path="fast_command", notes="Read-only public release status."),
    _link("public_release.hardening_audit", "eva-public-release-mode", "Public Release", agent="SafetyAgent", execution_path="fast_command", notes="Read-only repo hardening audit; secret files are not read."),
    _link("public_release.ready_check", "eva-public-release-mode", "Public Release", agent="SafetyAgent", execution_path="fast_command", notes="Read-only readiness check."),
    _link("public_release.demo_scenarios", "eva-public-release-mode", "Public Release", agent="SafetyAgent", execution_path="demo_only", preview_only=True, notes="Demo-only; no real action."),
    _link("public_release.safety_simulator", "eva-public-release-mode", "Public Release", agent="SafetyAgent", execution_path="demo_only", preview_only=True, notes="Simulation-only safety result."),
    _link("public_release.resource_registry_listing", "eva-public-release-mode", "Public Release", agent="SafetyAgent", execution_path="fast_command", notes="Catalog-only resource listing."),
    _link("reference.odysseus_ai_workspace", "odysseus-ai-workspace", "Reference", execution_path="disabled_reference", available_now=False, preview_only=True, notes="Reference-only architecture entry; not executable."),
    _link("reference.memos_memory_operating_system", "memos-memory-operating-system", "Reference", execution_path="disabled_reference", available_now=False, preview_only=True, notes="Reference-only memory architecture entry; no dependency or code copied."),
)


def _canonical_id(capability_id: str) -> str:
    normalized = str(capability_id or "").strip()
    return _ALIASES.get(normalized, normalized)


def list_capability_resource_links() -> list[CapabilityResourceLink]:
    return list(_LINKS)


def get_capability_resource_link(capability_id: str) -> CapabilityResourceLink | None:
    canonical = _canonical_id(capability_id)
    return next((link for link in _LINKS if link.capability_id == canonical), None)


def find_capabilities_by_resource(resource_id: str) -> list[CapabilityResourceLink]:
    wanted = str(resource_id or "").strip()
    return [link for link in _LINKS if link.resource_id == wanted]


def find_resources_for_capability(capability_id: str) -> list[str]:
    link = get_capability_resource_link(capability_id)
    return [link.resource_id] if link else []


def resolve_capability(capability_id: str, context: dict[str, object] | None = None) -> CapabilityResolution:
    requested = str(capability_id or "").strip()
    canonical = _canonical_id(requested)
    registry = build_default_registry()
    capability = registry.get(canonical)
    link = get_capability_resource_link(canonical)
    permission = get_capability_permission(canonical)
    decision = evaluate_capability_permission(canonical, context or {"mode": "public"})
    schema = capability_to_tool_schema(canonical)

    resource = get_resource(link.resource_id) if link else None
    resource_decision = evaluate_resource_by_id(link.resource_id) if link else None

    capability_name = capability.name if capability else _VIRTUAL_NAMES.get(canonical, canonical or "Unknown capability")
    resource_status = resource_decision.status if resource_decision else "resource_missing"
    resource_reason = resource_decision.reason if resource_decision else "No resource link is registered for this capability."
    final_status = _final_status(
        capability_exists=capability is not None or canonical in _VIRTUAL_NAMES,
        permission_allowed=decision.allowed,
        permission=permission,
        link=link,
        resource_status=resource_status,
        resource_executable=bool(resource_decision.executable_now) if resource_decision else False,
    )

    available_now = bool(
        link
        and link.available_now
        and final_status in {"available_read_only", "available_explicit_local_write", "preview_only"}
        and resource_decision
        and resource_decision.status not in {"blocked", "reference_only"}
    )
    if final_status in {"disabled_experimental", "reference_only", "blocked", "unknown"}:
        available_now = False

    reason = _resolution_reason(
        final_status=final_status,
        permission_reason=permission.reason,
        resource_reason=resource_reason,
        link_notes=link.notes if link else "",
        confirm_phrase=permission.confirm_phrase_required,
    )
    return CapabilityResolution(
        capability_id=canonical or requested,
        capability_name=capability_name,
        permission_summary=_permission_summary(permission),
        resource_id=link.resource_id if link else None,
        resource_status=resource_status,
        provider=link.provider if link else (resource.provider if resource else "unknown"),
        agent=link.agent if link else None,
        tool_schema_available=schema is not None,
        execution_path=link.execution_path if link else "unknown",
        available_now=available_now,
        preview_only=bool(link.preview_only) if link else False,
        allowed_in_public_mode=permission.public_mode_allowed and final_status not in {"blocked", "unknown", "reference_only", "disabled_experimental"},
        requires_confirmation=permission.requires_confirmation,
        requires_override=permission.requires_override,
        risk_level=permission.risk_level,
        final_status=final_status,
        reason=reason,
    )


def resolve_capability_resource(capability_id: str, context: dict[str, object] | None = None) -> CapabilityResolution:
    return resolve_capability(capability_id, context=context)


def _final_status(
    *,
    capability_exists: bool,
    permission_allowed: bool,
    permission: object,
    link: CapabilityResourceLink | None,
    resource_status: str,
    resource_executable: bool,
) -> str:
    if not capability_exists:
        return "unknown"
    if link is None:
        return "unknown"
    if resource_status == "resource_missing":
        return "resource_missing"
    if resource_status == "reference_only":
        return "reference_only"
    if resource_status == "blocked":
        return "blocked"
    if resource_status == "experimental":
        return "disabled_experimental"
    if not permission_allowed and not permission.requires_confirmation:
        return "blocked"
    if link.preview_only:
        return "preview_only"
    if permission.read_only and resource_executable:
        return "available_read_only"
    if permission.writes_local_data and resource_executable:
        return "available_explicit_local_write"
    return "preview_only"


def _permission_summary(permission: object) -> str:
    mode = "Read-only" if permission.read_only else "Explicit local write"
    allowed = "public/community allowed" if permission.public_mode_allowed else "public/community blocked"
    guards = []
    if permission.requires_confirmation:
        guards.append("confirmation required")
    if permission.requires_override:
        guards.append("override required")
    if permission.confirm_phrase_required:
        guards.append("confirm phrase required")
    guard = "; " + ", ".join(guards) if guards else ""
    return f"{mode}, {allowed}, {permission.risk_level} risk{guard}."


def _resolution_reason(*, final_status: str, permission_reason: str, resource_reason: str, link_notes: str, confirm_phrase: bool) -> str:
    parts = []
    if final_status == "disabled_experimental":
        parts.append("Resource is experimental or disabled by default.")
    elif final_status == "reference_only":
        parts.append("Resource is reference-only and not executable.")
    elif final_status == "blocked":
        parts.append("Permission or resource policy blocks this capability.")
    elif final_status == "preview_only":
        parts.append("This capability is preview-only or demo-only in this phase.")
    elif final_status == "resource_missing":
        parts.append("The mapped resource is missing from the registry.")
    elif final_status == "unknown":
        parts.append("Capability is not registered in the safe metadata view.")
    if confirm_phrase:
        parts.append("A confirm phrase is required for this scoped local action.")
    for item in (link_notes, permission_reason, resource_reason):
        if item and item not in parts:
            parts.append(item)
    return " ".join(parts)


def format_capability_resolution(capability_id: str) -> str:
    item = resolve_capability(capability_id)
    resource = item.resource_id or "none"
    schema = "available as preview" if item.tool_schema_available else "not registered"
    availability = "available now" if item.available_now else "not executable now"
    return "\n".join(
        [
            "Capability resolution",
            "",
            "Capability:",
            item.capability_id,
            f"Name: {item.capability_name}",
            "",
            "Permission:",
            item.permission_summary,
            "",
            "Resource:",
            resource,
            f"Resource status: {item.resource_status}",
            "",
            "Provider:",
            item.provider,
            f"Agent: {item.agent or 'none'}",
            "",
            "Execution:",
            f"Path: {item.execution_path}",
            f"Availability: {availability}",
            f"Preview only: {'yes' if item.preview_only else 'no'}",
            "",
            "Tool schema:",
            schema,
            "",
            "Status:",
            item.final_status,
            "",
            "Reason:",
            item.reason,
            "",
            "Scope:",
            "Metadata only. No tool, MCP server, browser, desktop, shell, or message action was executed.",
        ]
    )


def format_capability_resources(capability_id: str) -> str:
    item = resolve_capability(capability_id)
    lines = ["Capability resources", "", f"Capability: {item.capability_id}"]
    if item.resource_id:
        lines.extend(
            [
                f"- {item.resource_id}: {item.resource_status}; {item.final_status}; provider {item.provider}; path {item.execution_path}",
                "",
                "Safety:",
                item.reason,
            ]
        )
    else:
        lines.append("- No resource link is registered.")
    lines.extend(["", "Scope: metadata lookup only; nothing was executed."])
    return "\n".join(lines)


def format_resource_capabilities(resource_id: str) -> str:
    links = find_capabilities_by_resource(resource_id)
    lines = ["Resource capabilities", "", f"Resource: {resource_id}", f"Count: {len(links)}"]
    if not links:
        lines.append("No capabilities are mapped to this resource.")
    for link in links:
        resolution = resolve_capability(link.capability_id)
        lines.append(f"- {link.capability_id}: {resolution.final_status}; {link.execution_path}; {resolution.permission_summary}")
    lines.extend(["", "Scope: metadata lookup only; no resource was executed."])
    return "\n".join(lines)


def format_capability_resource_matrix(status: str | None = None) -> str:
    resolutions = [resolve_capability(link.capability_id) for link in _LINKS]
    wanted = str(status or "").strip().lower()
    if wanted == "available":
        title = "Available capabilities"
        resolutions = [item for item in resolutions if item.final_status in {"available_read_only", "available_explicit_local_write"}]
    elif wanted == "preview_only":
        title = "Preview-only capabilities"
        resolutions = [item for item in resolutions if item.final_status == "preview_only"]
    elif wanted == "blocked":
        title = "Blocked capabilities"
        resolutions = [item for item in resolutions if item.final_status in {"blocked", "disabled_experimental", "reference_only", "unknown", "resource_missing"}]
    else:
        title = "Capability-resource matrix"

    lines = [title, "", f"Count: {len(resolutions)}"]
    for item in resolutions:
        resource = item.resource_id or "none"
        lines.append(f"- {item.capability_id} -> {resource}: {item.final_status}; {item.execution_path}; {item.agent or 'no agent'}")
    lines.extend(["", "Scope: metadata-only mapping. No tools or resources were executed."])
    return "\n".join(lines)


def resolve_capabilities_for_goal(goal_text: str) -> list[CapabilityResolution]:
    text = str(goal_text or "").lower()
    capability_ids: list[str] = []
    if any(term in text for term in ("saved research", "research memory", "my research", "memory about")):
        capability_ids.extend(["research_memory.retrieve", "research_memory.search"])
    if "vector" in text or "semantic" in text:
        capability_ids.append("research_memory.vector_search")
    if any(term in text for term in ("summarize file", "summarise file", "understand file", "summarize readme", "summarise readme")):
        capability_ids.append("file.understand_text")
    elif any(term in text for term in ("inspect file", "read file", "preview file", "file preview")):
        capability_ids.append("file.preview_text")
    if any(term in text for term in ("browser read-only status", "browser readonly status", "browser read status")):
        capability_ids.append("browser_read.status")
    if any(term in text for term in ("browser read-only policy", "browser readonly policy", "can eva read a webpage", "logged-in browser")):
        capability_ids.append("browser_read.policy")
    if any(term in text for term in ("browser read url policy", "browser url policy")):
        capability_ids.append("browser_read.url_policy")
    if any(term in text for term in ("observe a webpage read only", "observe a web page read only", "browser read observe")):
        capability_ids.append("browser_read.observe")
    if "browser read mock observe" in text:
        capability_ids.append("browser_read.mock_observe")
    if "browser read safety report" in text:
        capability_ids.append("browser_read.safety_report")
    if any(term in text for term in ("blocked browser urls", "browser read blocked urls")):
        capability_ids.append("browser_read.blocked_urls")
    if any(term in text for term in ("browser read-only readiness", "browser readonly readiness", "browser read readiness")):
        capability_ids.append("browser_read.readiness")
    if any(term in text for term in ("can eva use the browser", "browser status", "is browser control enabled")):
        capability_ids.append("browser.status")
    if any(term in text for term in ("browser policy", "browser actions are allowed")):
        capability_ids.append("browser.policy")
    if "browser blocked" in text or "blocked browser" in text:
        capability_ids.append("browser.blocked_actions")
    if "browser domain policy" in text:
        capability_ids.append("browser.domain_policy")
    if any(term in text for term in ("browser action safety", "can eva click", "can eva type", "can eva login", "can eva upload", "can eva download")):
        capability_ids.append("browser.action_safety_preview")
    if "browser readiness" in text:
        capability_ids.append("browser.readiness")
    if any(term in text for term in ("browser session status", "show browser session status", "can eva browse websites")):
        capability_ids.append("browser.session_status")
    if any(term in text for term in ("start a browser session", "open a browser", "browser session preview")):
        capability_ids.append("browser.session_preview")
    if "browser sessions" in text:
        capability_ids.append("browser.sessions_list")
    if any(term in text for term in ("browser session plan", "what would a browser session do")):
        capability_ids.append("browser.session_plan")
    if any(term in text for term in ("browser read-only mode ready", "browser readonly mode ready")):
        capability_ids.append("browser.session_readiness")
    if any(term in text for term in ("can eva read a webpage", "can eva summarize a page", "page summary policy")):
        capability_ids.append("browser.page_summary_policy")
    if any(term in text for term in ("what would eva extract from a webpage", "page summary preview", "browser extraction preview")):
        capability_ids.append("browser.page_summary_preview")
    if any(term in text for term in ("can eva inspect dom", "dom summary policy", "inspect dom")):
        capability_ids.append("browser.dom_summary_policy")
    if "text extraction policy" in text:
        capability_ids.append("browser.text_extraction_policy")
    if any(term in text for term in ("can eva take screenshots", "browser observation policy", "observation readiness")):
        capability_ids.append("browser.observation_readiness")
    if "redaction policy" in text:
        capability_ids.append("browser.redaction_policy")
    if any(term in text for term in ("dry run opening a website", "browser action dry run")):
        capability_ids.append("browser.action_dry_run")
    if any(term in text for term in ("what would eva do to search google", "plan browser actions", "browser action plan")):
        capability_ids.append("browser.action_plan_preview")
    if any(term in text for term in ("can eva click this", "can eva type into a website", "browser action risk")):
        capability_ids.append("browser.action_risk")
    if any(term in text for term in ("browser actions need approval", "browser action approvals")):
        capability_ids.append("browser.action_approvals")
    if "browser dry run policy" in text:
        capability_ids.append("browser.dry_run_policy")
    if "browser action readiness" in text:
        capability_ids.append("browser.action_readiness")
    if any(term in text for term in ("is example.com safe", "site safe for eva", "domain check")):
        capability_ids.append("browser.domain_check")
    if any(term in text for term in ("can eva use gmail", "can eva open a banking website", "can eva upload files to a site", "site risk")):
        capability_ids.append("browser.site_risk")
    if any(term in text for term in ("browser domain rules", "show browser domain policy")):
        capability_ids.append("browser.domain_rules")
    if any(term in text for term in ("what sites are risky", "sensitive sites")):
        capability_ids.append("browser.sensitive_sites")
    if any(term in text for term in ("approvals are needed for sensitive sites", "domain approvals", "sensitive site approvals")):
        capability_ids.append("browser.domain_approvals")
    if "domain readiness" in text:
        capability_ids.append("browser.domain_readiness")
    if any(term in text for term in ("browser read-only mode ready", "browser readonly mode ready", "browser read only readiness")):
        capability_ids.append("browser.readonly_readiness")
    if "browser readiness proof" in text:
        capability_ids.append("browser.readiness_proof")
    if any(term in text for term in ("browser safety proof", "prove browser control is still locked")):
        capability_ids.append("browser.safety_proof")
    if any(term in text for term in ("missing before browser read-only", "browser readiness gaps")):
        capability_ids.append("browser.readiness_gaps")
    if any(term in text for term in ("can eva browse now", "browser locked status")):
        capability_ids.append("browser.locked_status")
    if any(term in text for term in ("phase 13 browser safe", "browser phase 13 proof")):
        capability_ids.append("browser.phase13_proof")
    if any(term in text for term in ("browser phase 13 status", "phase 13 browser status")):
        capability_ids.append("browser.phase13_status")
    if any(term in text for term in ("summarize browser phase 13", "browser phase 13 summary")):
        capability_ids.append("browser.phase13_summary")
    if any(term in text for term in ("what are browser phase 13 limits", "browser phase 13 limits")):
        capability_ids.append("browser.phase13_limits")
    if any(term in text for term in ("is browser phase 13 complete", "browser phase 13 ready", "is browser phase 13 ready")):
        capability_ids.append("browser.phase13_ready")
    if any(term in text for term in ("browser phase 13 final proof", "show browser phase 13 final proof")):
        capability_ids.append("browser.phase13_final_proof")
    if any(term in text for term in ("can eva control my desktop", "can eva see my screen", "is desktop control enabled", "desktop status")):
        capability_ids.append("desktop.status")
    if any(term in text for term in ("desktop policy", "what desktop actions are allowed", "show desktop policy")):
        capability_ids.append("desktop.policy")
    if any(term in text for term in ("desktop blocked actions", "what desktop actions are blocked")):
        capability_ids.append("desktop.blocked_actions")
    if any(term in text for term in ("desktop action safety", "can eva click", "can eva type", "can eva use terminal", "can eva open apps")):
        capability_ids.append("desktop.action_safety_preview")
    if any(term in text for term in ("dry run clicking a button", "dry run desktop action", "desktop action dry run")):
        capability_ids.append("desktop.action_dry_run")
    if any(term in text for term in ("what would eva do to open an app", "plan desktop actions", "desktop action plan")):
        capability_ids.append("desktop.action_plan_preview")
    if any(term in text for term in ("can eva click this", "can eva type into an app", "can eva press hotkeys", "desktop action risk")):
        capability_ids.append("desktop.action_risk")
    if any(term in text for term in ("desktop actions need approval", "desktop action approvals")):
        capability_ids.append("desktop.action_approvals")
    if "desktop dry run policy" in text:
        capability_ids.append("desktop.dry_run_policy")
    if "desktop action readiness" in text:
        capability_ids.append("desktop.action_readiness")
    if any(term in text for term in ("desktop risk score", "how risky is", "score the risk")):
        capability_ids.append("desktop.risk_score")
    if any(term in text for term in ("desktop risk factors", "what risk factors")):
        capability_ids.append("desktop.risk_factors")
    if any(term in text for term in ("desktop approval required", "approval is needed")):
        capability_ids.append("desktop.approval_required")
    if any(term in text for term in ("desktop approval policy", "approve eva to control my desktop")):
        capability_ids.append("desktop.approval_policy")
    if "desktop approval levels" in text:
        capability_ids.append("desktop.approval_levels")
    if any(term in text for term in ("desktop approval preview", "what approval is needed to click", "what approval is needed to type")):
        capability_ids.append("desktop.approval_preview")
    if "confirmation phrase" in text:
        capability_ids.append("desktop.confirmation_phrase")
    if "forbidden actions" in text or "desktop actions are forbidden" in text:
        capability_ids.append("desktop.forbidden_actions")
    if "approval audit" in text:
        capability_ids.append("desktop.approval_audit_status")
    if "desktop approval readiness" in text or "is desktop approval ready" in text:
        capability_ids.append("desktop.approval_readiness")
    if "desktop safety matrix" in text:
        capability_ids.append("desktop.safety_matrix")
    if any(term in text for term in ("desktop high risk actions", "desktop actions are high risk")):
        capability_ids.append("desktop.high_risk_actions")
    if "desktop risk readiness" in text:
        capability_ids.append("desktop.risk_readiness")
    if any(term in text for term in ("desktop app risk", "app risk")):
        capability_ids.append("desktop.app_risk")
    if any(term in text for term in ("desktop readiness", "is desktop ready")):
        capability_ids.append("desktop.readiness")
    if any(term in text for term in ("desktop session status", "show desktop session status")):
        capability_ids.append("desktop.session_status")
    if any(term in text for term in ("start a desktop session", "desktop session preview")):
        capability_ids.append("desktop.session_preview")
    if "desktop sessions" in text:
        capability_ids.append("desktop.sessions_list")
    if any(term in text for term in ("desktop session plan", "what would desktop observation include")):
        capability_ids.append("desktop.session_plan")
    if "desktop app status preview" in text:
        capability_ids.append("desktop.app_status_preview")
    if any(term in text for term in ("desktop window status preview", "can eva see open windows")):
        capability_ids.append("desktop.window_status_preview")
    if any(term in text for term in ("desktop active context preview", "can eva detect the active app")):
        capability_ids.append("desktop.active_context_preview")
    if any(term in text for term in ("desktop observation readiness", "is desktop observation ready", "can eva inspect my screen")):
        capability_ids.append("desktop.observation_readiness")
    if any(term in text for term in ("desktop screen policy", "can eva see my screen", "can eva read my screen")):
        capability_ids.append("desktop.screen_policy")
    if any(term in text for term in ("screen observation policy", "desktop screen observation policy")):
        capability_ids.append("desktop.screen_observation_policy")
    if any(term in text for term in ("sensitive screens", "what screens are sensitive")):
        capability_ids.append("desktop.sensitive_screens")
    if any(term in text for term in ("screen redaction", "redact from screen")):
        capability_ids.append("desktop.screen_redaction_policy")
    if any(term in text for term in ("screen capture gate", "take screenshots", "can eva take screenshots")):
        capability_ids.append("desktop.screen_capture_gate")
    if any(term in text for term in ("screen readiness", "is screen observation ready")):
        capability_ids.append("desktop.screen_readiness")
    if "desktop observation policy" in text:
        capability_ids.append("desktop.observation_policy")
    if any(term in text for term in ("find file", "search file", "filename")):
        capability_ids.append("file.search_name")
    if any(term in text for term in ("what is this project", "explain this repo", "explain repo", "project explain")):
        capability_ids.append("file.project_explain")
    if "project inventory" in text:
        capability_ids.append("file.project_inventory")
    if "missing file" in text or "files are missing" in text:
        capability_ids.append("file.project_missing")
    if "project dependencies" in text or "dependency files" in text:
        capability_ids.append("file.project_dependencies")
    if any(term in text for term in ("draft readme", "readme section")):
        capability_ids.append("file.draft_readme_section")
    if "project summary" in text:
        capability_ids.append("file.draft_project_summary")
    if "project todo" in text:
        capability_ids.append("file.draft_project_todo")
    if "report outline" in text or "draft report" in text or "make a report" in text:
        capability_ids.append("file.draft_report_outline")
    if "append" in text and "file" in text or "append to readme" in text:
        capability_ids.append("file.draft_append_preview")
    if "replace text" in text:
        capability_ids.append("file.draft_replace_preview")
    if "diff preview" in text:
        capability_ids.append("file.diff_preview")
    if any(term in text for term in ("apply this draft", "apply this change", "write this to file", "update readme", "edit this file", "file change safe", "file edit safe", "prepare to update")):
        capability_ids.append("file.apply_readiness")
    if "write safety" in text:
        capability_ids.append("file.write_safety_policy")
    if "rollback plan" in text:
        capability_ids.append("file.rollback_plan")
    if "verification plan" in text and "file" in text:
        capability_ids.append("file.verification_plan")
    if text.startswith("eva ask") or "ask eva" in text or "natural request" in text:
        capability_ids.append("eva.ask")
    if any(term in text for term in ("dashboard", "control center", "show eva status", "what is eva doing", "system state")):
        capability_ids.append("eva.control_center_status")
    if any(term in text for term in ("work session", "work sessions", "session status")):
        capability_ids.append("eva.work_sessions_status")
    if "audit timeline" in text:
        capability_ids.append("eva.audit_timeline")
    if any(term in text for term in ("what happened last", "latest session", "last work session")):
        capability_ids.append("eva.latest_work_session")
    if "locked feature" in text or "features are locked" in text:
        capability_ids.append("eva.locked_features")
    if "enabled feature" in text or "features are enabled" in text:
        capability_ids.append("eva.enabled_features")
    if "next safe step" in text:
        capability_ids.append("eva.next_safe_step")
    if any(term in text for term in ("golden workflow", "project note", "safe markdown note", "draft and safely create")):
        capability_ids.append("eva.golden_workflow_project_note")
    if "golden workflow proof" in text or "did the golden workflow pass" in text:
        capability_ids.append("eva.golden_workflow_proof")
    if "golden workflow test plan" in text:
        capability_ids.append("eva.golden_workflow_test_plan")
    if "authority decision" in text or "authority status" in text:
        capability_ids.append("eva.authority_status")
    if "phase 12 ready" in text or "phase12 ready" in text:
        capability_ids.append("eva.phase12_ready")
    if "phase 12 summary" in text or "summarize phase 12" in text:
        capability_ids.append("eva.phase12_summary")
    if "phase 12 limits" in text:
        capability_ids.append("eva.phase12_limits")
    if "phase 12 proof" in text:
        capability_ids.append("eva.phase12_proof")
    if any(term in text for term in ("sandbox apply", "test this approved file change", "apply approved file change")):
        capability_ids.append("file.sandbox_apply_approved")
    if "verify sandbox apply" in text:
        capability_ids.append("file.sandbox_verify_apply")
    if "rollback sandbox apply" in text:
        capability_ids.append("file.sandbox_rollback_apply")
    if any(term in text for term in ("real apply approved", "create approved markdown", "create approved text file", "real create", "really create the approved docs file")):
        capability_ids.append("file.real_create_new_text_file")
    if "verify real create" in text or "verify real created" in text:
        capability_ids.append("file.real_verify_new_text_file")
    if "rollback real create" in text or "rollback real created" in text:
        capability_ids.append("file.real_rollback_new_text_file")
    if any(term in text for term in ("approval request", "approve this file change", "approve readme edit")):
        capability_ids.append("file.approval_request_create")
    if "pending approvals" in text or "approvals pending" in text:
        capability_ids.append("file.approval_list_pending")
    if "project structure" in text or "folder" in text:
        capability_ids.append("file.explain_project_structure")
    if "public" in text and "status" in text:
        capability_ids.append("public_release.public_status")
    if "dry run" in text or "dry-run" in text:
        capability_ids.append("eva_v2.dry_run")
    if "route" in text and "preview" in text:
        capability_ids.append("eva_v2.route_preview")
    if "plan" in text and "preview" in text:
        capability_ids.append("eva_v2.plan_preview")
    if any(term in text for term in ("demo unsafe", "safety test", "unsafe env")):
        capability_ids.append("public_release.safety_simulator")
    if "demo" in text and "scenario" in text:
        capability_ids.append("public_release.demo_scenarios")
    if not capability_ids and "status" in text:
        capability_ids.append("eva_v2.agent_status")

    deduped: list[str] = []
    for item in capability_ids:
        if item not in deduped:
            deduped.append(item)
    return [resolve_capability(item) for item in deduped]


def format_capability_plan_resources(goal_text: str) -> str:
    resolutions = resolve_capabilities_for_goal(goal_text)
    lines = ["Likely capability resources", "", f"Goal: {str(goal_text or '').strip()}"]
    if not resolutions:
        lines.append("No safe metadata capability matched this goal yet.")
    for item in resolutions:
        lines.append(f"- {item.capability_id} -> {item.resource_id or 'none'}: {item.final_status}; {item.permission_summary}")
    lines.extend(["", "Scope: planner-readiness preview only. No LLM call or tool execution occurred."])
    return "\n".join(lines)
