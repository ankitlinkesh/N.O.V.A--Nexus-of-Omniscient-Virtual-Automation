from __future__ import annotations

import hashlib

from ..capabilities.permissions import get_capability_permission
from ..capabilities.resource_mapping import resolve_capability
from .capability_selector import explain_capability_selection, infer_goal_intents, select_capabilities_for_goal
from .models import EvaTaskPlan, EvaTaskStep, utc_now_iso
from .risk_review import review_plan_risks
from .templates import apply_template_to_goal, get_template_for_goal


def create_task_plan(goal_text: str, context: dict | None = None) -> EvaTaskPlan:
    normalized = _normalize(goal_text)
    capabilities = select_capabilities_for_goal(normalized)
    steps = decompose_goal(normalized)
    template = get_template_for_goal(normalized)
    if template:
        template_steps = apply_template_to_goal(normalized, template.template_id)
        if template_steps and steps:
            template_steps[0].depends_on = [steps[-1].step_id]
        steps.extend(template_steps)

    for capability_id in capabilities:
        if capability_id not in {step.capability_id for step in steps if step.capability_id}:
            steps.append(build_step_for_capability(capability_id, normalized, depends_on=[steps[-1].step_id] if steps else []))

    if _needs_browser_step(normalized) and not _has_step_type(steps, "browser_open"):
        steps.append(_future_step("browser_open", "Open browser target", "Browser or Chrome control is not enabled in Phase 10A.", "browser.control", normalized, "blocked"))
    if _needs_message_step(normalized) and not any(step.permission_status == "confirmation_required" for step in steps):
        steps.extend(_message_steps(normalized, depends_on=steps[-1].step_id if steps else None))
    if _needs_destructive_step(normalized) and not any(step.capability_id == "file.delete" for step in steps):
        steps.append(_future_step("blocked", "Block destructive or system action", "Delete, shell, install, shutdown, and system-changing actions are not executable in Planner v3 Phase 10A.", "file.delete", normalized, "override_required"))
    if _needs_file_or_document_step(normalized) and not _has_step_type(steps, "local_write"):
        steps.append(_future_step("local_write", "Draft file or document work plan", "File and document writes are future permission-gated actions; this phase only plans them.", None, normalized, "preview_only"))
    if _needs_comparison_report(normalized):
        steps.extend(_comparison_report_steps(normalized, depends_on=steps[-1].step_id if steps else None))
    if _needs_hackathon_steps(normalized) and not has_title_fragment(steps, "submission requirements"):
        steps.extend(_hackathon_steps(normalized, depends_on=steps[-1].step_id if steps else None))
    if not steps:
        steps.append(_unknown_step(normalized))

    if _should_add_verification(steps):
        steps.append(_verification_step(normalized, depends_on=steps[-1].step_id))

    steps = _assign_step_ids(steps)
    required = _dedupe([step.capability_id for step in steps if step.capability_id])
    plan = EvaTaskPlan(
        plan_id=_plan_id(normalized),
        user_goal=str(goal_text or "").strip(),
        normalized_goal=normalized,
        summary=_summary_for_goal(normalized, capabilities),
        steps=steps,
        required_capabilities=required,
        blocked_capabilities=[],
        confirmation_required=False,
        override_required=False,
        can_execute_now=False,
        preview_only=True,
        safety_summary="Planner v3 Phase 10A is planning-only.",
        next_recommended_action="Review the preview plan. No task was executed.",
        created_at=utc_now_iso(),
    )
    return review_plan_risks(plan)


def decompose_goal(goal_text: str) -> list[EvaTaskStep]:
    normalized = _normalize(goal_text)
    intents = infer_goal_intents(normalized)
    steps: list[EvaTaskStep] = [
        EvaTaskStep(
            step_id="step_1",
            title="Understand user goal",
            description="Classify the request into safe planner intents without executing anything.",
            step_type="planning",
            capability_id=None,
            resource_id=None,
            agent="PlannerAgent",
            input_summary=normalized,
            expected_output=", ".join(intents),
            risk_level="low",
            permission_status="allowed",
            availability_status="available_now",
            notes="Planning-only classification.",
        )
    ]
    if "specialist_selection" in intents:
        steps.append(_preview_step("specialist_selection", "Select specialists", "Select specialist roles for this request without executing them.", "eva.specialist_select", normalized, "PlannerAgent", depends_on="step_1"))
    if "skill_workflow" in intents:
        steps.append(_preview_step("skill_selection", "Select skills", "Select safe skills and workflow surfaces for this request.", "eva.skill_select", normalized, "PlannerAgent", depends_on=steps[-1].step_id))
        steps.append(_preview_step("workflow_plan", "Plan safe workflow", "Format the next workflow step without executing file, browser, desktop, shell, MCP, or cloud actions.", "eva.workflow_plan", normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    if "workflow_state" in intents:
        steps.append(_preview_step("workflow_state", "Read latest workflow state", "Summarize current FileAgent approval/apply context without executing anything.", "eva.workflow_state", normalized, "FileAgent", depends_on=steps[-1].step_id))
        steps.append(_preview_step("workflow_next_step", "Classify next safe step", "Use latest state to recommend approval, disambiguation, verification, or exact confirmation guidance.", "eva.workflow_next_step", normalized, "FileAgent", depends_on=steps[-1].step_id))
        steps.append(_preview_step("workflow_disambiguation", "Disambiguate candidates if needed", "If multiple candidates exist, list safe IDs and ask the user to specify one.", "eva.workflow_disambiguate", normalized, "SafetyAgent", depends_on=steps[-1].step_id))
    if "control_center" in intents:
        steps.append(_preview_step("control_center_status", "Read Control Center status", "Summarize current dashboard/status panels without executing tools or verifiers.", "eva.control_center_status", normalized, "ControlCenterAgent", depends_on=steps[-1].step_id))
    for intent, title, capability in (
        ("coding_status", "Read CodingAgent status", "coding.status"),
        ("coding_policy", "Read CodingAgent policy", "coding.policy"),
        ("coding_specialists", "Read coding specialist catalog", "coding.specialists"),
        ("coding_task_preview", "Classify coding task locally", "coding.task_preview"),
        ("coding_project_context", "Read safe coding context summary", "coding.project_context"),
        ("coding_patch_plan", "Build coding change-plan preview", "coding.patch_plan"),
        ("coding_review_checklist", "Build coding review checklist", "coding.review_checklist"),
        ("coding_test_plan", "Build coding test-plan preview", "coding.test_plan"),
        ("coding_risk_review", "Build coding risk-review preview", "coding.risk_review"),
        ("coding_handoff", "Build coding handoff preview", "coding.handoff"),
        ("coding_blocked_actions", "Read CodingAgent blocked actions", "coding.blocked_actions"),
        ("coding_readiness", "Read CodingAgent readiness", "coding.readiness"),
    ):
        if intent in intents:
            steps.append(
                _preview_step(
                    intent,
                    title,
                    "Local deterministic coding preview/report/status only; mutation, filesystem access, and every execution class remain locked.",
                    capability,
                    normalized,
                    "CodeAgent",
                    depends_on=steps[-1].step_id,
                )
            )
    for intent, title, capability in (
        ("rc_status", "Read release-candidate status", "rc.status"),
        ("rc_manifest", "Read dirty tree manifest snapshot", "rc.manifest"),
        ("rc_commit_plan", "Read text-only commit plan", "rc.commit_plan"),
        ("rc_hardening_report", "Read release-candidate hardening report", "rc.hardening_report"),
        ("rc_checklist", "Read release-candidate checklist", "rc.checklist"),
        ("rc_readiness", "Read release-candidate readiness", "rc.readiness"),
        ("rc_safety_proof", "Read release-candidate safety proof", "rc.safety_proof"),
        ("rc_verification", "Read release-candidate verification plan", "rc.verification"),
    ):
        if intent in intents:
            steps.append(
                _preview_step(
                    intent,
                    title,
                    "Local deterministic RC report/status/planning only; commit planning is text only and no Git, publish, mutation, filesystem, provider, control, or tool action is available.",
                    capability,
                    normalized,
                    "SafetyAgent",
                    depends_on=steps[-1].step_id,
                )
            )
    for intent, title, capability in (
        ("release_status", "Read public release status", "release.status"),
        ("release_demo", "Read public demo profile", "release.demo"),
        ("release_commands", "Read public demo command guide", "release.commands"),
        ("release_capability_map", "Read public capability map", "release.capability_map"),
        ("release_safety_proof", "Read public safety proof", "release.safety_proof"),
        ("release_readiness", "Read public release readiness", "release.readiness"),
        ("release_limitations", "Read public known limitations", "release.limitations"),
        ("release_verification", "Read public verification bundle", "release.verification"),
        ("release_demo_smoke", "Read safe local demo smoke checklist", "release.demo_smoke"),
        ("release_post_push_sync", "Read post-push sync status", "release.post_push_sync"),
    ):
        if intent in intents:
            steps.append(
                _preview_step(
                    intent,
                    title,
                    "Local deterministic release demo/report/status only; external actions, mutation, filesystem access, and every execution class remain locked.",
                    capability,
                    normalized,
                    "SafetyAgent",
                    depends_on=steps[-1].step_id,
                )
            )
    for intent, title, capability in (
        ("roadmap_status", "Read phase improvement roadmap", "roadmap.control_truth_panels"),
        ("execution_boundaries", "Read execution boundary audit", "roadmap.execution_boundary_audit"),
        ("catalog_status", "Read roadmap catalog status", "roadmap.capability_catalog"),
        ("frontend_truth_status", "Read frontend truth status", "roadmap.frontend_truth"),
        ("grounded_answer_status", "Read grounded answer status", "roadmap.grounded_answers"),
        ("voice_reliability_status", "Read voice reliability status", "roadmap.voice_reliability"),
        ("verifier_dashboard_status", "Read verifier dashboard status", "roadmap.verifier_dashboard"),
    ):
        if intent in intents:
            steps.append(
                _preview_step(
                    intent,
                    title,
                    "Local deterministic roadmap/report/status only; no new execution path is enabled and Phase 12L remains the only real write boundary.",
                    capability,
                    normalized,
                    "SafetyAgent",
                    depends_on=steps[-1].step_id,
                )
            )
    for intent,title,cap in (("news_dashboard","Read news dashboard","news.dashboard"),("news_status","Read web intelligence status","news.status"),("news_policy","Read news policy","news.policy"),("news_sources","Read news source reliability","news.sources"),("news_freshness","Read news freshness","news.freshness"),("news_readiness","Read news readiness","news.readiness")):
        if intent in intents: steps.append(_preview_step(intent,title,"Local/mock dashboard/report/status only; no crawler, browser control, login, network, or execution step.",cap,normalized,"ResearchAgent",depends_on=steps[-1].step_id))
    for intent, title, capability in (
        ("desktop_control_status", "Read desktop control-gate status", "desktop_control.status"),
        ("desktop_control_policy", "Read desktop control-gate policy", "desktop_control.policy"),
        ("desktop_control_dry_run", "Build desktop control dry-run report", "desktop_control.dry_run"),
        ("desktop_control_approvals", "Read desktop control approval policy", "desktop_control.approvals"),
        ("desktop_control_blocked_actions", "Read blocked desktop control actions", "desktop_control.blocked_actions"),
        ("desktop_control_readiness", "Read desktop control-gate readiness", "desktop_control.readiness"),
    ):
        if intent in intents:
            steps.append(_preview_step(intent, title, "Local/mock policy or dry-run report only; no desktop action or executor is created.", capability, normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    for intent, title, capability in (
        ("desktop_observe_status", "Read desktop observation status", "desktop_observe.status"),
        ("desktop_observe_policy", "Read desktop observation policy", "desktop_observe.policy"),
        ("desktop_observe_backend", "Read desktop observation backend status", "desktop_observe.backend"),
        ("desktop_observe_mock", "Observe deterministic desktop fixture", "desktop_observe.mock"),
        ("desktop_observe_safety_report", "Read desktop observation safety report", "desktop_observe.safety_report"),
        ("desktop_observe_sensitive_screens", "Read sensitive-screen policy", "desktop_observe.sensitive_screens"),
        ("desktop_observe_redaction_policy", "Read desktop observation redaction policy", "desktop_observe.redaction_policy"),
        ("desktop_observe_readiness", "Read desktop observation readiness", "desktop_observe.readiness"),
    ):
        if intent in intents:
            steps.append(_preview_step(intent, title, "Explicit one-shot redacted observation/report only; all desktop actions and persistent capture remain locked.", capability, normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "llm_status" in intents:
        steps.append(_preview_step("llm_status", "Read LLM router status", "Show mock-only LLM router status without live calls.", "llm.status", normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    if "llm_providers" in intents:
        steps.append(_preview_step("llm_providers", "Read LLM provider contracts", "Show provider metadata only.", "llm.providers", normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    if "llm_routing_policy" in intents:
        steps.append(_preview_step("llm_routing_policy", "Read LLM routing policy", "Show dry-run routing policy.", "llm.routing_policy", normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    if "llm_fallback_policy" in intents:
        steps.append(_preview_step("llm_fallback_policy", "Read LLM fallback policy", "Show fallback/degraded mode metadata.", "llm.fallback_policy", normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    if "llm_limits" in intents:
        steps.append(_preview_step("llm_limits", "Read LLM limits", "Show token/cost/timeout/retry previews.", "llm.limits", normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    if "llm_structured_output" in intents:
        steps.append(_preview_step("llm_structured_output", "Read LLM structured-output rules", "Show mock validation contract only.", "llm.structured_output", normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    for intent, title, capability in (
        ("llm_validation_status", "Read LLM validation status", "llm.validation_status"),
        ("llm_schema_registry", "Read LLM schema registry", "llm.schema_registry"),
        ("llm_validation_policy", "Read LLM validation policy", "llm.validation_policy"),
        ("llm_repair_policy", "Read LLM repair policy", "llm.repair_policy"),
        ("llm_validate_mock", "Read LLM mock validation", "llm.validate_mock"),
        ("llm_validate_invalid_examples", "Read LLM invalid examples", "llm.validate_invalid_examples"),
        ("llm_validation_readiness", "Read LLM validation readiness", "llm.validation_readiness"),
    ):
        if intent in intents:
            steps.append(_preview_step(intent, title, "Status/policy preview only: mock/local validation, live calls locked, and invalid output cannot execute tools.", capability, normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    for intent, title, capability in (("llm_red_team_status", "Read LLM red-team status", "llm.red_team_status"), ("llm_red_team_run", "Run local LLM red-team report", "llm.red_team_run"), ("llm_failure_tests", "Read LLM failure tests", "llm.failure_tests"), ("llm_safety_failure_report", "Read LLM safety failure report", "llm.safety_failure_report"), ("llm_red_team_readiness", "Read LLM red-team readiness", "llm.red_team_readiness")):
        if intent in intents:
            steps.append(_preview_step(intent, title, "Local/mock report only; no provider, tool, browser, desktop, shell, cloud, or MCP execution.", capability, normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    for intent, title, capability in (
        ("context_status", "Read context assembly status", "context.status"),
        ("context_sources", "Read context source registry", "context.sources"),
        ("context_policy", "Read context assembly policy", "context.policy"),
        ("context_budget", "Read context budget policy", "context.budget"),
        ("context_assemble_preview", "Build context assembly preview", "context.assemble_preview"),
        ("context_grounding_report", "Read context grounding report", "context.grounding_report"),
        ("context_redaction_policy", "Read context redaction policy", "context.redaction_policy"),
        ("context_readiness", "Read context readiness", "context.readiness"),
    ):
        if intent in intents:
            steps.append(_preview_step(intent, title, "Local/mock context status, policy, preview, or report only; no live LLM call, tool execution, arbitrary file read, browser, desktop, shell, cloud, or MCP step.", capability, normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    for intent, title, capability in (
        ("threat_status", "Read threat defense status", "threat.status"),
        ("threat_catalog", "Read threat catalog", "threat.catalog"),
        ("threat_policy", "Read threat defense policy", "threat.policy"),
        ("threat_scan_preview", "Build threat scan preview", "threat.scan_preview"),
        ("threat_injection_examples", "Read prompt injection examples", "threat.injection_examples"),
        ("threat_exfiltration_examples", "Read exfiltration examples", "threat.exfiltration_examples"),
        ("threat_context_guard", "Read context poisoning guard", "threat.context_guard"),
        ("threat_readiness", "Read threat defense readiness", "threat.readiness"),
    ):
        if intent in intents:
            steps.append(_preview_step(intent, title, "Local/mock threat status, policy, preview, or report only; no live LLM call, tool execution, arbitrary file read, browser, desktop, shell, cloud, or MCP step.", capability, normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    for intent, title, capability in (
        ("agent_loop_status", "Read Agent Loop v1 status", "agent_loop.status"),
        ("agent_loop_policy", "Read Agent Loop v1 policy", "agent_loop.policy"),
        ("agent_loop_run_preview", "Run Agent Loop v1 preview", "agent_loop.run_preview"),
        ("agent_loop_steps", "Read Agent Loop v1 stages", "agent_loop.steps"),
        ("agent_loop_action_previews", "Read Agent Loop v1 action previews", "agent_loop.action_previews"),
        ("agent_loop_safety_report", "Read Agent Loop v1 safety report", "agent_loop.safety_report"),
        ("agent_loop_stop_reasons", "Read Agent Loop v1 stop reasons", "agent_loop.stop_reasons"),
        ("agent_loop_readiness", "Read Agent Loop v1 readiness", "agent_loop.readiness"),
    ):
        if intent in intents:
            steps.append(_preview_step(intent, title, "Local/mock agent loop status, policy, preview, or report only; no live LLM call, no tool execution, and no locked execution-surface step.", capability, normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    for intent, title, capability in (
        ("workflow_planner_status", "Read Agentic Workflow Planner status", "workflow_planner.status"),
        ("workflow_planner_catalog", "Read workflow template catalog", "workflow_planner.catalog"),
        ("workflow_planner_policy", "Read workflow planner policy", "workflow_planner.policy"),
        ("workflow_planner_preview", "Build workflow preview", "workflow_planner.preview"),
        ("workflow_planner_dependencies", "Read workflow dependency validation", "workflow_planner.dependencies"),
        ("workflow_planner_approvals", "Read workflow approval preview", "workflow_planner.approvals"),
        ("workflow_planner_rollback", "Read workflow rollback preview", "workflow_planner.rollback"),
        ("workflow_planner_readiness", "Read workflow planner readiness", "workflow_planner.readiness"),
    ):
        if intent in intents:
            steps.append(_preview_step(intent, title, "Local/mock workflow planner status, policy, preview, or report only; no live LLM call, no tool execution, and no locked execution-surface step.", capability, normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    for intent, title, capability in (
        ("execution_gates_status", "Read Controlled Execution Gates status", "execution_gates.status"),
        ("execution_gates_policy", "Read Controlled Execution Gates policy", "execution_gates.policy"),
        ("execution_gates_evaluate", "Build Controlled Execution Gates evaluation", "execution_gates.evaluate"),
        ("execution_gates_approvals", "Read Controlled Execution Gates approval policy", "execution_gates.approvals"),
        ("execution_gates_confirmations", "Read Controlled Execution Gates confirmation policy", "execution_gates.confirmations"),
        ("execution_gates_rollback", "Read Controlled Execution Gates rollback policy", "execution_gates.rollback"),
        ("execution_gates_blocked_actions", "Read Controlled Execution Gates blocked classes", "execution_gates.blocked_actions"),
        ("execution_gates_readiness", "Read Controlled Execution Gates readiness", "execution_gates.readiness"),
    ):
        if intent in intents:
            steps.append(_preview_step(intent, title, "Local/mock gate policy, evaluation, or report only; no live LLM call, no tool execution, and no runtime surface is unlocked.", capability, normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    for intent, title, capability in (
        ("ai_os_status", "Read AI OS status", "ai_os.status"),
        ("ai_os_dashboard", "Read AI OS dashboard", "ai_os.dashboard"),
        ("ai_os_system_map", "Read AI OS system map", "ai_os.system_map"),
        ("ai_os_capability_matrix", "Read AI OS capability matrix", "ai_os.capability_matrix"),
        ("ai_os_feature_states", "Read AI OS feature states", "ai_os.feature_states"),
        ("ai_os_safety_boundaries", "Read AI OS safety boundaries", "ai_os.safety_boundaries"),
        ("ai_os_locked_features", "Read AI OS locked features", "ai_os.locked_features"),
        ("ai_os_next_safe_step", "Read AI OS next safe step", "ai_os.next_safe_step"),
        ("ai_os_readiness", "Read AI OS readiness", "ai_os.readiness"),
    ):
        if intent in intents:
            steps.append(_preview_step(intent, title, "Local AI OS status, dashboard, or report only; all runtime surfaces and mutation paths stay locked.", capability, normalized, "ControlCenterAgent", depends_on=steps[-1].step_id))
    for intent, title, capability in (
        ("voice_status", "Read Voice Assistant Foundation status", "voice.status"),
        ("voice_policy", "Read Voice Assistant Foundation policy", "voice.policy"),
        ("voice_providers", "Read locked voice provider policy", "voice.providers"),
        ("voice_listen_state", "Read mock voice lifecycle state", "voice.listen_state"),
        ("voice_transcript_safety", "Read voice transcript safety policy", "voice.transcript_safety"),
        ("voice_route_preview", "Build local voice route preview", "voice.route_preview"),
        ("voice_confirmations", "Read voice confirmation policy", "voice.confirmations"),
        ("voice_readiness", "Read Voice Assistant Foundation readiness", "voice.readiness"),
    ):
        if intent in intents:
            steps.append(_preview_step(intent, title, "Local/mock voice policy, status, or report only; input/output devices and all runtime integrations stay locked.", capability, normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    for intent, title, capability in (
        ("memory_v3_status", "Read Memory v3 status", "memory_v3.status"),
        ("memory_v3_policy", "Read Memory v3 policy", "memory_v3.policy"),
        ("memory_v3_sources", "Read Memory v3 source model", "memory_v3.sources"),
        ("memory_v3_privacy", "Read Memory v3 privacy policy", "memory_v3.privacy"),
        ("memory_v3_freshness", "Read Memory v3 freshness policy", "memory_v3.freshness"),
        ("memory_v3_conflicts", "Read Memory v3 conflict policy", "memory_v3.conflicts"),
        ("memory_v3_retrieval_preview", "Build Memory v3 retrieval preview", "memory_v3.retrieval_preview"),
        ("memory_v3_readiness", "Read Memory v3 readiness", "memory_v3.readiness"),
    ):
        if intent in intents:
            steps.append(_preview_step(intent, title, "Local-only memory policy, status, or retrieval preview; no live LLM call, no cloud memory, no tool execution, and no runtime surface is unlocked.", capability, normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    for intent, title, capability in (("llm_fallback_simulate", "Simulate LLM fallback", "llm.fallback_simulate"), ("llm_degraded_mode", "Read LLM degraded mode", "llm.degraded_mode"), ("llm_session_limits", "Read LLM session limits", "llm.session_limits"), ("llm_runaway_protection", "Read LLM runaway protection", "llm.runaway_protection"), ("llm_routing_audit_preview", "Read LLM routing audit preview", "llm.routing_audit_preview")):
        if intent in intents:
            steps.append(_preview_step(intent, title, "Mock/dry-run policy or simulation only; live LLM calls remain locked.", capability, normalized, "PlannerAgent", depends_on=steps[-1].step_id))
    if "desktop_phase14_status" in intents:
        steps.append(_preview_step("desktop_phase14_status", "Read DesktopAgent Phase 14 status", "Show final locked DesktopAgent Phase 14 status.", "desktop.phase14_status", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_phase14_summary" in intents:
        steps.append(_preview_step("desktop_phase14_summary", "Read DesktopAgent Phase 14 summary", "Summarize completed locked DesktopAgent safety/readiness layers.", "desktop.phase14_summary", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_phase14_limits" in intents:
        steps.append(_preview_step("desktop_phase14_limits", "Read DesktopAgent Phase 14 limits", "Show final locked desktop observation/control limits.", "desktop.phase14_limits", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_phase14_ready" in intents:
        steps.append(_preview_step("desktop_phase14_ready", "Read DesktopAgent Phase 14 ready check", "Show Phase 14 completion as a locked safety/readiness foundation.", "desktop.phase14_ready", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_phase14_final_proof" in intents:
        steps.append(_preview_step("desktop_phase14_final_proof", "Read DesktopAgent Phase 14 final proof", "Show final proof that Phase 14 enables no desktop observation or control.", "desktop.phase14_final_proof", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_readiness_proof" in intents:
        steps.append(_preview_step("desktop_readiness_proof", "Read DesktopAgent readiness proof", "Show locked DesktopAgent safety/readiness proof without execution.", "desktop.readiness_proof", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_locked_status" in intents:
        steps.append(_preview_step("desktop_locked_status", "Read DesktopAgent locked status", "Show locked desktop observation/control boundary.", "desktop.locked_status", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_readiness_gaps" in intents:
        steps.append(_preview_step("desktop_readiness_gaps", "Read DesktopAgent readiness gaps", "Show what is missing before a future desktop gate.", "desktop.readiness_gaps", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_status" in intents:
        steps.append(_preview_step("desktop_status", "Read DesktopAgent status", "Show DesktopAgent safety-model status without screen observation or desktop control.", "desktop.status", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_policy" in intents:
        steps.append(_preview_step("desktop_policy", "Read DesktopAgent policy", "Show DesktopAgent policy/readiness boundaries without desktop execution.", "desktop.policy", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_blocked_actions" in intents:
        steps.append(_preview_step("desktop_blocked_actions", "Read DesktopAgent blocked actions", "Show blocked desktop action categories and reasons.", "desktop.blocked_actions", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_action_safety" in intents:
        steps.append(_preview_step("desktop_action_safety", "Preview desktop action safety", "Evaluate a desktop action against the Phase 14A safety model without executing it.", "desktop.action_safety_preview", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_action_dry_run" in intents:
        steps.append(_preview_step("desktop_action_dry_run", "Create desktop action dry-run", "Show text-only desktop action dry-run steps without executing them.", "desktop.action_dry_run", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_action_plan_preview" in intents:
        steps.append(_preview_step("desktop_action_plan_preview", "Preview desktop action plan", "Show desktop action preview steps, risk, approvals, and blocked execution.", "desktop.action_plan_preview", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_action_risk" in intents:
        steps.append(_preview_step("desktop_action_risk", "Classify desktop action risk", "Classify a desktop action without executing mouse, keyboard, clipboard, app, screen, or terminal actions.", "desktop.action_risk", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_action_approvals" in intents:
        steps.append(_preview_step("desktop_action_approvals", "Read desktop action approval requirements", "Show future approval gates for desktop action categories.", "desktop.action_approvals", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_dry_run_policy" in intents:
        steps.append(_preview_step("desktop_dry_run_policy", "Read desktop dry-run policy", "Show DesktopAgent action dry-run policy.", "desktop.dry_run_policy", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_action_readiness" in intents:
        steps.append(_preview_step("desktop_action_readiness", "Read desktop action readiness", "Show gaps before future real desktop action execution.", "desktop.action_readiness", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_risk_score" in intents:
        steps.append(_preview_step("desktop_risk_score", "Score desktop action risk", "Calculate deterministic string-only desktop risk without executing actions.", "desktop.risk_score", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_risk_factors" in intents:
        steps.append(_preview_step("desktop_risk_factors", "Explain desktop risk factors", "Explain risk factors from request text only.", "desktop.risk_factors", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_approval_required" in intents:
        steps.append(_preview_step("desktop_approval_required", "Explain desktop approval requirement", "Show future approval level without enabling execution.", "desktop.approval_required", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_approval_policy" in intents:
        steps.append(_preview_step("desktop_approval_policy", "Read desktop approval policy", "Show human approval policy without unlocking desktop execution.", "desktop.approval_policy", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_approval_levels" in intents:
        steps.append(_preview_step("desktop_approval_levels", "Read desktop approval levels", "Explain DesktopAgent approval levels and forbidden states.", "desktop.approval_levels", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_approval_preview" in intents:
        steps.append(_preview_step("desktop_approval_preview", "Preview desktop approval", "Preview future approval level and state without executing desktop actions.", "desktop.approval_preview", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_confirmation_phrase" in intents:
        steps.append(_preview_step("desktop_confirmation_phrase", "Preview desktop confirmation phrase", "Show future confirmation phrase class without unlocking execution.", "desktop.confirmation_phrase", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_forbidden_actions" in intents:
        steps.append(_preview_step("desktop_forbidden_actions", "List desktop forbidden actions", "Show desktop action classes with no approval path.", "desktop.forbidden_actions", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_approval_audit_status" in intents:
        steps.append(_preview_step("desktop_approval_audit_status", "Read desktop approval audit status", "Show approval audit schema/status only.", "desktop.approval_audit_status", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_approval_readiness" in intents:
        steps.append(_preview_step("desktop_approval_readiness", "Read desktop approval readiness", "Show gaps before desktop approvals could unlock any future action.", "desktop.approval_readiness", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_safety_matrix" in intents:
        steps.append(_preview_step("desktop_safety_matrix", "Read desktop safety matrix", "Show desktop action risk and approval matrix.", "desktop.safety_matrix", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_high_risk_actions" in intents:
        steps.append(_preview_step("desktop_high_risk_actions", "List high-risk desktop actions", "List high-risk and forbidden desktop action classes.", "desktop.high_risk_actions", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_risk_readiness" in intents:
        steps.append(_preview_step("desktop_risk_readiness", "Read desktop risk readiness", "Show readiness gaps before future risk-gated desktop action execution.", "desktop.risk_readiness", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_app_risk" in intents:
        steps.append(_preview_step("desktop_app_risk", "Classify desktop app risk", "Classify an app/category string without inspecting real apps, windows, or screen state.", "desktop.app_risk", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_readiness" in intents:
        steps.append(_preview_step("desktop_readiness", "Read DesktopAgent readiness", "Show missing gates before any future real desktop observation/control.", "desktop.readiness", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_session_status" in intents:
        steps.append(_preview_step("desktop_session_status", "Read desktop session preview status", "Show preview-only desktop session status without screen observation or desktop control.", "desktop.session_status", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_session_preview" in intents:
        steps.append(_preview_step("desktop_session_preview", "Create desktop session preview", "Create a local preview-only session record without observing or controlling the desktop.", "desktop.session_preview", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_session_plan" in intents:
        steps.append(_preview_step("desktop_session_plan", "Read desktop session lifecycle plan", "Show the future desktop observation/session lifecycle plan without execution.", "desktop.session_plan", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_app_status_preview" in intents:
        steps.append(_preview_step("desktop_app_status_preview", "Preview desktop app status schema", "Show app status schema without inspecting real apps.", "desktop.app_status_preview", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_window_status_preview" in intents:
        steps.append(_preview_step("desktop_window_status_preview", "Preview desktop window status schema", "Show window status schema without enumerating real windows.", "desktop.window_status_preview", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_active_context_preview" in intents:
        steps.append(_preview_step("desktop_active_context_preview", "Preview desktop active context schema", "Show active context schema without detecting a real active app/window.", "desktop.active_context_preview", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_observation_readiness" in intents:
        steps.append(_preview_step("desktop_observation_readiness", "Read desktop observation readiness", "Show gaps before any future desktop observation can exist.", "desktop.observation_readiness", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_screen_policy" in intents:
        steps.append(_preview_step("desktop_screen_policy", "Read desktop screen policy", "Show locked screen observation policy without capture, screenshots, OCR, or image analysis.", "desktop.screen_policy", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_screen_observation_policy" in intents:
        steps.append(_preview_step("desktop_screen_observation_policy", "Read screen observation policy", "Show future screen observation schema and locked policy boundaries.", "desktop.screen_observation_policy", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_sensitive_screens" in intents:
        steps.append(_preview_step("desktop_sensitive_screens", "Read sensitive screen categories", "Show sensitive screen categories and future approval requirements.", "desktop.sensitive_screens", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_screen_redaction_policy" in intents:
        steps.append(_preview_step("desktop_screen_redaction_policy", "Read screen redaction policy", "Show local redaction policy preview for future screen observation.", "desktop.screen_redaction_policy", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_screen_capture_gate" in intents:
        steps.append(_preview_step("desktop_screen_capture_gate", "Read screen capture gate", "Show future capture gate requirements while real capture remains locked.", "desktop.screen_capture_gate", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_screen_readiness" in intents:
        steps.append(_preview_step("desktop_screen_readiness", "Read screen observation readiness", "Show readiness gaps before future screen observation can exist.", "desktop.screen_readiness", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "desktop_observation_policy" in intents:
        steps.append(_preview_step("desktop_observation_policy", "Read desktop observation policy", "Show screen observation policy and safety decision preview.", "desktop.observation_policy", normalized, "DesktopAgent", depends_on=steps[-1].step_id))
    if "browser_read_status" in intents:
        steps.append(_preview_step("browser_read_status", "Read Phase 24 browser status", "Show public-URL read-only observation status and locked action boundaries.", "browser_read.status", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_read_policy" in intents:
        steps.append(_preview_step("browser_read_policy", "Read Phase 24 browser policy", "Show URL, session-isolation, backend, and action-free observation policy.", "browser_read.policy", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_read_url_policy" in intents:
        steps.append(_preview_step("browser_read_url_policy", "Read public URL policy", "Show local public URL validation and blocked target classes.", "browser_read.url_policy", normalized, "SafetyAgent", depends_on=steps[-1].step_id))
    if "browser_read_observe" in intents:
        steps.append(_preview_step("browser_read_observe", "Observe public webpage read only", "Return sanitized observation or unavailable-safe status through the Phase 24 gate.", "browser_read.observe", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_read_mock_observe" in intents:
        steps.append(_preview_step("browser_read_mock_observe", "Observe deterministic browser fixture", "Return a sanitized local fixture observation with threat and gate summaries.", "browser_read.mock_observe", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_read_safety_report" in intents:
        steps.append(_preview_step("browser_read_safety_report", "Read browser observation safety report", "Show URL, redaction, threat-defense, and execution-gate evidence.", "browser_read.safety_report", normalized, "SafetyAgent", depends_on=steps[-1].step_id))
    if "browser_read_blocked_urls" in intents:
        steps.append(_preview_step("browser_read_blocked_urls", "Read blocked browser URL classes", "Show targets denied before any observation backend.", "browser_read.blocked_urls", normalized, "SafetyAgent", depends_on=steps[-1].step_id))
    if "browser_read_readiness" in intents:
        steps.append(_preview_step("browser_read_readiness", "Read Phase 24 browser readiness", "Show read-only observation readiness and the locked browser-action boundary.", "browser_read.readiness", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_status" in intents:
        steps.append(_preview_step("browser_safety_status", "Read BrowserAgent status", "Show BrowserAgent safety-model status without launching or controlling a browser.", "browser.status", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_session_status" in intents:
        steps.append(_preview_step("browser_session_status", "Read browser session preview status", "Show preview-only browser session status without launching or controlling a browser.", "browser.session_status", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_session_preview" in intents:
        steps.append(_preview_step("browser_session_preview", "Create browser session preview", "Create a local preview-only session record without launching, navigating, observing, or controlling a browser.", "browser.session_preview", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_session_plan" in intents:
        steps.append(_preview_step("browser_session_plan", "Read browser session lifecycle plan", "Show the future browser session lifecycle plan without execution.", "browser.session_plan", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_session_readiness" in intents:
        steps.append(_preview_step("browser_session_readiness", "Read browser session readiness", "Show readiness gaps for read-only browser preview and future control.", "browser.session_readiness", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_page_summary_policy" in intents:
        steps.append(_preview_step("browser_page_summary_policy", "Read browser page summary policy", "Show page summary design policy without live page reads.", "browser.page_summary_policy", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_page_summary_preview" in intents:
        steps.append(_preview_step("browser_page_summary_preview", "Preview browser page summary schema", "Show mock-text summary output fields without live browser observation.", "browser.page_summary_preview", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_dom_summary_policy" in intents:
        steps.append(_preview_step("browser_dom_summary_policy", "Read browser DOM summary policy", "Show DOM summary schema policy without DOM access.", "browser.dom_summary_policy", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_text_extraction_policy" in intents:
        steps.append(_preview_step("browser_text_extraction_policy", "Read browser text extraction policy", "Show text extraction policy without live page extraction.", "browser.text_extraction_policy", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_observation_readiness" in intents:
        steps.append(_preview_step("browser_observation_readiness", "Read browser observation readiness", "Show gaps before future live browser observation.", "browser.observation_readiness", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_redaction_policy" in intents:
        steps.append(_preview_step("browser_redaction_policy", "Read browser redaction policy", "Show local redaction rules for future browser observation.", "browser.redaction_policy", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_action_dry_run" in intents:
        steps.append(_preview_step("browser_action_dry_run", "Create browser action dry-run", "Show text-only browser action dry-run steps without executing them.", "browser.action_dry_run", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_action_plan_preview" in intents:
        steps.append(_preview_step("browser_action_plan_preview", "Preview browser action plan", "Show browser action plan, risk, and approvals without execution.", "browser.action_plan_preview", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_action_risk" in intents:
        steps.append(_preview_step("browser_action_risk", "Read browser action risk", "Classify a browser action risk without executing it.", "browser.action_risk", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_action_approvals" in intents:
        steps.append(_preview_step("browser_action_approvals", "Read browser action approval requirements", "Show future approval requirements for browser actions.", "browser.action_approvals", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_dry_run_policy" in intents:
        steps.append(_preview_step("browser_dry_run_policy", "Read browser dry-run policy", "Show BrowserAgent action dry-run policy.", "browser.dry_run_policy", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_action_readiness" in intents:
        steps.append(_preview_step("browser_action_readiness", "Read browser action readiness", "Show readiness gaps before browser action execution can exist.", "browser.action_readiness", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_domain_check" in intents:
        steps.append(_preview_step("browser_domain_check", "Classify browser domain", "Classify the provided domain or URL string without DNS, network, browser, page, screenshot, DOM, cookie, localStorage, profile, shell, MCP, PyAutoGUI, package, or cloud access.", "browser.domain_check", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_site_risk" in intents:
        steps.append(_preview_step("browser_site_risk", "Read browser site risk", "Show site risk category and future approval requirement from a provided domain string only.", "browser.site_risk", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_domain_rules" in intents:
        steps.append(_preview_step("browser_domain_rules", "Read browser domain rules", "Show BrowserAgent domain risk rules without accessing a browser or network.", "browser.domain_rules", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_sensitive_sites" in intents:
        steps.append(_preview_step("browser_sensitive_sites", "Read sensitive site categories", "Show sensitive site markers and blocked categories without execution.", "browser.sensitive_sites", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_domain_approvals" in intents:
        steps.append(_preview_step("browser_domain_approvals", "Read browser domain approvals", "Show future approval requirements for sensitive sites; no approval enables browser execution in this phase.", "browser.domain_approvals", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_domain_readiness" in intents:
        steps.append(_preview_step("browser_domain_readiness", "Read browser domain readiness", "Show readiness gaps for future domain-gated browser observation.", "browser.domain_readiness", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_readonly_readiness" in intents:
        steps.append(_preview_step("browser_readonly_readiness", "Read browser read-only readiness", "Show BrowserAgent read-only readiness proof without enabling browser read-only mode.", "browser.readonly_readiness", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_readiness_proof" in intents:
        steps.append(_preview_step("browser_readiness_proof", "Read browser readiness proof", "Show checklist proof for safety, session, observation, action, and domain layers.", "browser.readiness_proof", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_safety_proof" in intents:
        steps.append(_preview_step("browser_safety_proof", "Read browser safety proof", "Prove browser execution remains locked without launching or observing a browser.", "browser.safety_proof", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_readiness_gaps" in intents:
        steps.append(_preview_step("browser_readiness_gaps", "Read browser readiness gaps", "Show missing gates before any future read-only browser mode.", "browser.readiness_gaps", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_locked_status" in intents:
        steps.append(_preview_step("browser_locked_status", "Read browser locked status", "Show locked browser execution categories and current allowed status surfaces.", "browser.locked_status", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_phase13_proof" in intents:
        steps.append(_preview_step("browser_phase13_proof", "Read BrowserAgent Phase 13 proof", "Summarize Phase 13 BrowserAgent proof layers without enabling browser execution.", "browser.phase13_proof", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_phase13_status" in intents:
        steps.append(_preview_step("browser_phase13_status", "Read BrowserAgent Phase 13 status", "Show final Phase 13 safety/readiness-only status without enabling browser execution.", "browser.phase13_status", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_phase13_summary" in intents:
        steps.append(_preview_step("browser_phase13_summary", "Read BrowserAgent Phase 13 summary", "Summarize final Phase 13 safety/readiness scope without enabling browser execution.", "browser.phase13_summary", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_phase13_limits" in intents:
        steps.append(_preview_step("browser_phase13_limits", "Read BrowserAgent Phase 13 limits", "Show final locked browser/network/action categories.", "browser.phase13_limits", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_phase13_ready" in intents:
        steps.append(_preview_step("browser_phase13_ready", "Read BrowserAgent Phase 13 ready check", "Show that Phase 13 is complete as a safety/readiness foundation only.", "browser.phase13_ready", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_phase13_final_proof" in intents:
        steps.append(_preview_step("browser_phase13_final_proof", "Read BrowserAgent Phase 13 final proof", "Show final proof that Phase 13 enables no browser observation or control.", "browser.phase13_final_proof", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_policy" in intents:
        steps.append(_preview_step("browser_policy", "Read BrowserAgent policy", "Show BrowserAgent policy/readiness boundaries without browser execution.", "browser.policy", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_action_safety" in intents:
        steps.append(_preview_step("browser_action_safety", "Preview browser action safety", "Evaluate a browser action against the Phase 13A safety model without executing it.", "browser.action_safety_preview", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "browser_readiness" in intents:
        steps.append(_preview_step("browser_readiness", "Read BrowserAgent readiness", "Show missing gates before any future real browser control.", "browser.readiness", normalized, "BrowserAgent", depends_on=steps[-1].step_id))
    if "work_sessions" in intents:
        capability_id = "eva.audit_timeline" if "audit timeline" in normalized.lower() else "eva.latest_work_session" if "what happened last" in normalized.lower() or "latest session" in normalized.lower() else "eva.work_sessions_status"
        steps.append(_preview_step("work_session_audit", "Read WorkSession audit status", "Summarize local WorkSession/session timeline evidence without executing tools or verifiers.", capability_id, normalized, "ControlCenterAgent", depends_on=steps[-1].step_id))
    if "locked_features" in intents:
        steps.append(_preview_step("locked_features", "Explain locked features", "Show locked and planned features without enabling them.", "eva.locked_features", normalized, "ControlCenterAgent", depends_on=steps[-1].step_id))
    if "enabled_features" in intents:
        steps.append(_preview_step("enabled_features", "Explain enabled features", "Show enabled status surfaces and the 12L narrow real-create boundary.", "eva.enabled_features", normalized, "ControlCenterAgent", depends_on=steps[-1].step_id))
    if "next_safe_step" in intents:
        steps.append(_preview_step("next_safe_step", "Read next safe step", "Show the next safe phase recommendation without running anything.", "eva.next_safe_step", normalized, "ControlCenterAgent", depends_on=steps[-1].step_id))
    if "project_reality" in intents:
        steps.append(_preview_step("project_inspection", "Inspect project status", "Use read-only FileAgent inventory and local status surfaces to explain the repo.", "eva.project_inspect", normalized, "ProjectInspectorAgent", depends_on=steps[-1].step_id))
    if "project_recent_changes" in intents:
        steps.append(_preview_step("project_recent_changes", "Summarize recent phase changes", "Summarize latest known Phase 12 changes from docs/status surfaces, not git mutation.", "eva.project_recent_changes", normalized, "ProjectInspectorAgent", depends_on=steps[-1].step_id))
    if "project_broken_status" in intents:
        steps.append(_preview_step("reality_check", "Check broken-status evidence", "Report only verifier/status-backed failures and avoid guessing.", "eva.project_reality_check", normalized, "RealityCheckerAgent", depends_on=steps[-1].step_id))
    if "project_next_step" in intents:
        steps.append(_preview_step("project_next_step", "Recommend next safe phase", "Recommend one safe next phase without enabling execution.", "eva.project_next_step", normalized, "SafetyAgent", depends_on=steps[-1].step_id))
    if "project_proof" in intents:
        steps.append(_preview_step("evidence_review", "Collect proof surfaces", "Summarize current local proof surfaces and limitations.", "eva.project_proof", normalized, "RealityCheckerAgent", depends_on=steps[-1].step_id))
    if "done_check" in intents:
        steps.append(_preview_step("done_check", "Check completion claim", "Refuse to claim done without fresh verifier evidence.", "eva.done_check", normalized, "RealityCheckerAgent", depends_on=steps[-1].step_id))
    if "golden_workflow" in intents:
        steps.extend(_golden_workflow_steps(normalized, depends_on="step_1"))
    if "golden_workflow_proof" in intents:
        steps.append(_preview_step("golden_workflow_proof", "Read golden workflow proof", "Show latest approval, real-create, verification, rollback, and WorkSession evidence without executing a workflow step.", "eva.golden_workflow_proof", normalized, "FileAgent", depends_on=steps[-1].step_id))
    if "golden_workflow_test_plan" in intents:
        steps.append(_preview_step("golden_workflow_test_plan", "Read golden workflow test plan", "Show the E2E workflow plan without creating, verifying, or rolling back files.", "eva.golden_workflow_test_plan", normalized, "FileAgent", depends_on=steps[-1].step_id))
    return steps


def build_step_for_capability(capability_id: str, goal_text: str, depends_on: list[str] | None = None) -> EvaTaskStep:
    resolution = resolve_capability(capability_id)
    availability = _availability_from_resolution(resolution.final_status)
    permission = _permission_from_resolution(resolution)
    return EvaTaskStep(
        step_id="step_pending",
        title=_title_for_capability(resolution.capability_id),
        description=f"Use capability metadata for {resolution.capability_id}; no execution is performed.",
        step_type=_step_type_for_capability(resolution.capability_id),
        capability_id=resolution.capability_id,
        resource_id=resolution.resource_id,
        agent=resolution.agent,
        input_summary=goal_text,
        expected_output=resolution.capability_name,
        risk_level=resolution.risk_level,
        permission_status=permission,
        availability_status=availability,
        depends_on=list(depends_on or []),
        notes=resolution.reason,
    )


def enrich_step_with_resolution(step: EvaTaskStep) -> EvaTaskStep:
    if not step.capability_id:
        return step
    resolution = resolve_capability(step.capability_id)
    step.resource_id = resolution.resource_id
    step.agent = resolution.agent
    step.risk_level = resolution.risk_level
    step.permission_status = _permission_from_resolution(resolution)
    step.availability_status = _availability_from_resolution(resolution.final_status)
    step.notes = resolution.reason
    return step


def determine_plan_safety(steps: list[EvaTaskStep]) -> tuple[bool, bool, str]:
    confirmation = any(step.permission_status == "confirmation_required" for step in steps)
    override = any(step.permission_status == "override_required" for step in steps)
    blocked = any(step.permission_status == "blocked" or step.availability_status in {"blocked", "disabled", "missing"} for step in steps)
    if blocked or override:
        return confirmation, override, "Plan includes blocked or override-gated steps."
    if confirmation:
        return confirmation, override, "Plan includes confirmation-gated steps."
    return confirmation, override, "Plan is low-risk, but Phase 10A is still planning-only."


def _normalize(goal_text: str) -> str:
    return " ".join(str(goal_text or "").strip().split())


def _plan_id(goal_text: str) -> str:
    digest = hashlib.sha256(goal_text.encode("utf-8")).hexdigest()[:12]
    return f"plan_{digest}"


def _summary_for_goal(goal_text: str, capability_ids: list[str]) -> str:
    template = get_template_for_goal(goal_text)
    selection = explain_capability_selection(goal_text, capability_ids)
    if template:
        return f"Template used: {template.template_id}. {selection}"
    return selection


def _needs_browser_step(text: str) -> bool:
    text = text.lower()
    if any(term in text for term in ("desktop policy", "desktop status", "desktop readiness", "desktop action", "desktop actions", "desktop blocked actions", "desktop app risk", "can eva control my desktop", "can eva see my screen", "is desktop control enabled", "can eva click and type", "can eva open apps", "can eva use terminal", "browser policy", "browser status", "browser session", "browser readiness", "browser observation", "browser dry run", "browser action", "browser domain", "browser safety proof", "browser phase 13 proof", "browser phase 13 status", "browser phase 13 summary", "browser phase 13 limits", "browser phase 13 ready", "browser phase 13 final proof", "browser locked status", "domain check", "domain readiness", "site risk", "sensitive sites", "browser read-only mode ready", "browser readonly mode ready", "missing before browser read-only", "prove browser control is still locked", "can eva browse now", "phase 13 browser safe", "is browser phase 13 complete", "summarize browser phase 13", "browser actions", "browser action safety", "can eva use the browser", "can eva browse websites", "can eva read a webpage", "can eva summarize a page", "can eva inspect dom", "can eva take screenshots", "what would eva extract", "what would eva do to search google", "dry run opening a website", "plan browser actions", "is browser control enabled", "can eva click", "can eva type", "can eva login", "can eva upload", "can eva use gmail", "can eva open a banking website", "can eva upload files to a site", "what sites are risky", "what approvals are needed for sensitive sites", "open a browser", "start a browser session")):
        return False
    return any(term in text for term in ("open chatgpt", "open chrome", "open website", "search web", "control browser", "launch browser"))


def _needs_message_step(text: str) -> bool:
    text = text.lower()
    if any(term in text for term in ("plan desktop actions", "desktop action plan", "dry run desktop action", "approval is needed", "desktop risk score", "score the risk", "how risky is")):
        return False
    return any(term in text for term in ("send whatsapp", "send email", "message ", "post ", "submit form"))


def _needs_destructive_step(text: str) -> bool:
    text = text.lower()
    return any(term in text for term in ("delete", "shutdown", "install", "run powershell", "run shell", "terminal", "remove folder"))


def _needs_file_or_document_step(text: str) -> bool:
    text = text.lower()
    return any(term in text for term in ("edit file", "make report", "create document", "write file"))


def _needs_hackathon_steps(text: str) -> bool:
    text = text.lower()
    return "hackathon" in text or "submission" in text


def _needs_comparison_report(text: str) -> bool:
    text = text.lower()
    return "compare" in text and ("report" in text or "summary" in text or "document" in text)


def _has_step_type(steps: list[EvaTaskStep], step_type: str) -> bool:
    return any(step.step_type == step_type for step in steps)


def has_title_fragment(steps: list[EvaTaskStep], fragment: str) -> bool:
    wanted = fragment.lower()
    return any(wanted in step.title.lower() or wanted in step.description.lower() for step in steps)


def _future_step(step_type: str, title: str, description: str, capability_id: str | None, goal_text: str, permission_status: str) -> EvaTaskStep:
    resource_id = None
    agent = "PlannerAgent"
    risk = "medium"
    availability = "preview_only"
    notes = "Future capability. No execution was attempted."
    if capability_id:
        permission = get_capability_permission(capability_id)
        risk = permission.risk_level
        notes = permission.reason
        if permission.blocked_by_default:
            availability = "blocked"
    return EvaTaskStep(
        step_id="step_pending",
        title=title,
        description=description,
        step_type=step_type,
        capability_id=capability_id,
        resource_id=resource_id,
        agent=agent,
        input_summary=goal_text,
        expected_output="Planner preview only.",
        risk_level=risk,
        permission_status=permission_status,
        availability_status=availability,
        notes=notes,
    )


def _preview_step(
    step_type: str,
    title: str,
    description: str,
    capability_id: str,
    goal_text: str,
    agent: str,
    *,
    depends_on: str | None = None,
) -> EvaTaskStep:
    resolution = resolve_capability(capability_id)
    return EvaTaskStep(
        step_id="step_pending",
        title=title,
        description=description,
        step_type=step_type,
        capability_id=capability_id,
        resource_id=resolution.resource_id,
        agent=agent,
        input_summary=goal_text,
        expected_output=resolution.capability_name,
        risk_level=resolution.risk_level,
        permission_status=_permission_from_resolution(resolution),
        availability_status=_availability_from_resolution(resolution.final_status),
        depends_on=[depends_on] if depends_on else [],
        notes=resolution.reason,
    )


def _message_steps(goal_text: str, depends_on: str | None) -> list[EvaTaskStep]:
    draft = EvaTaskStep(
        step_id="step_pending",
        title="Draft external message",
        description="Identify recipient and draft message content without sending.",
        step_type="draft_content",
        capability_id=None,
        resource_id=None,
        agent="SafetyAgent",
        input_summary=goal_text,
        expected_output="Message draft preview.",
        risk_level="medium",
        permission_status="allowed",
        availability_status="preview_only",
        depends_on=[depends_on] if depends_on else [],
        notes="Drafting is planning-only here.",
    )
    confirm = EvaTaskStep(
        step_id="step_pending",
        title="Require send confirmation",
        description="External messages require explicit confirmation before any future send action.",
        step_type="user_confirmation",
        capability_id="whatsapp.send" if "whatsapp" in goal_text else "email.send",
        resource_id=None,
        agent="SafetyAgent",
        input_summary=goal_text,
        expected_output="Confirmation checkpoint.",
        risk_level="high",
        permission_status="confirmation_required",
        availability_status="blocked",
        depends_on=["step_pending"],
        notes="External sending is not enabled in Phase 10A.",
    )
    return [draft, confirm]


def _golden_workflow_steps(goal_text: str, depends_on: str | None) -> list[EvaTaskStep]:
    dep = [depends_on] if depends_on else []
    return [
        EvaTaskStep(
            step_id="step_pending",
            title="Route natural project-note request",
            description="Interpret the natural request and select the safe_project_note_create golden workflow.",
            step_type="golden_workflow",
            capability_id="eva.golden_workflow_project_note",
            resource_id=None,
            agent="FileAgent",
            input_summary=goal_text,
            expected_output="Safe project-note workflow selected.",
            risk_level="medium",
            permission_status="confirmation_required",
            availability_status="preview_only",
            depends_on=dep,
            notes="Natural route -> generate safe draft -> create approval request.",
        ),
        EvaTaskStep(
            step_id="step_pending",
            title="Run FileAgent gated workflow",
            description="Generate safe draft, create approval request, sandbox apply first, require exact real-create confirmation, verify, then allow exact rollback phrase if needed.",
            step_type="file_sandbox_apply",
            capability_id="file.sandbox_apply_approved",
            resource_id=None,
            agent="FileAgent",
            input_summary=goal_text,
            expected_output="Approval, sandbox verification, eligibility, exact confirmation, verification, and rollback guidance.",
            risk_level="medium",
            permission_status="confirmation_required",
            availability_status="preview_only",
            depends_on=["step_pending"],
            notes="Broad writes blocked; real create is limited to new .md/.txt files in allowed folders.",
        ),
    ]


def _hackathon_steps(goal_text: str, depends_on: str | None) -> list[EvaTaskStep]:
    first_dep = [depends_on] if depends_on else []
    return [
        EvaTaskStep(
            step_id="step_pending",
            title="Outline submission requirements",
            description="Break the submission into checklist items and required artifacts.",
            step_type="research",
            capability_id="eva_v2.plan",
            resource_id="eva-v2-runtime",
            agent="PlannerAgent",
            input_summary=goal_text,
            expected_output="Submission checklist.",
            risk_level="low",
            permission_status="allowed",
            availability_status="preview_only",
            depends_on=first_dep,
            notes="Planning-only checklist; no files are created.",
        ),
        EvaTaskStep(
            step_id="step_pending",
            title="Draft submission content",
            description="Plan content sections such as project summary, demo flow, and final checklist.",
            step_type="draft_content",
            capability_id="eva_v2.plan",
            resource_id="eva-v2-runtime",
            agent="PlannerAgent",
            input_summary=goal_text,
            expected_output="Draft outline.",
            risk_level="low",
            permission_status="allowed",
            availability_status="preview_only",
            depends_on=["step_pending"],
            notes="No document or file write occurs.",
        ),
    ]


def _comparison_report_steps(goal_text: str, depends_on: str | None) -> list[EvaTaskStep]:
    first_dep = [depends_on] if depends_on else []
    return [
        EvaTaskStep(
            step_id="step_pending",
            title="Identify comparison items and specs",
            description="List the exact models/specs to compare before drafting.",
            step_type="planning",
            capability_id="eva_v2.plan",
            resource_id="eva-v2-runtime",
            agent="PlannerAgent",
            input_summary=goal_text,
            expected_output="Comparison inputs and assumptions.",
            risk_level="low",
            permission_status="allowed",
            availability_status="preview_only",
            depends_on=first_dep,
            notes="For drone motors, ask for motor models, KV, thrust, weight, battery voltage, and prop size.",
        ),
        EvaTaskStep(
            step_id="step_pending",
            title="Compare technical criteria",
            description="Compare thrust, efficiency, weight, battery voltage, prop compatibility, and constraints.",
            step_type="draft_content",
            capability_id="eva_v2.plan",
            resource_id="eva-v2-runtime",
            agent="PlannerAgent",
            input_summary=goal_text,
            expected_output="Comparison matrix outline.",
            risk_level="low",
            permission_status="allowed",
            availability_status="preview_only",
            depends_on=["step_pending"],
            notes="Planning-only comparison criteria; no web search or file write happens here.",
        ),
        EvaTaskStep(
            step_id="step_pending",
            title="Draft report recommendation structure",
            description="Plan report sections for findings, tradeoffs, recommendation, and assumptions.",
            step_type="draft_content",
            capability_id="eva_v2.plan",
            resource_id="eva-v2-runtime",
            agent="PlannerAgent",
            input_summary=goal_text,
            expected_output="Report recommendation outline.",
            risk_level="low",
            permission_status="allowed",
            availability_status="preview_only",
            depends_on=["step_pending"],
            notes="Ask before saving or exporting any report.",
        ),
    ]


def _unknown_step(goal_text: str) -> EvaTaskStep:
    return EvaTaskStep(
        step_id="step_1",
        title="Create safe preview-only plan",
        description="No registered safe capability directly matched the goal.",
        step_type="blocked",
        capability_id=None,
        resource_id=None,
        agent="PlannerAgent",
        input_summary=goal_text,
        expected_output="Ask for a more specific capability or use a preview command.",
        risk_level="medium",
        permission_status="unknown",
        availability_status="preview_only",
        notes="Unknown capabilities are not executed.",
    )


def _verification_step(goal_text: str, depends_on: str) -> EvaTaskStep:
    return EvaTaskStep(
        step_id="step_pending",
        title="Verify planned outcome",
        description="Define what evidence would prove the task succeeded in a later executor phase.",
        step_type="verification",
        capability_id=None,
        resource_id=None,
        agent="VerifierAgent",
        input_summary=goal_text,
        expected_output="Verification criteria.",
        risk_level="low",
        permission_status="allowed",
        availability_status="preview_only",
        depends_on=[depends_on],
        notes="Verification criteria only; no observation is performed.",
    )


def _should_add_verification(steps: list[EvaTaskStep]) -> bool:
    return bool(steps) and steps[-1].step_type != "verification"


def _title_for_capability(capability_id: str) -> str:
    return capability_id.replace("_", " ").replace(".", " ").title()


def _step_type_for_capability(capability_id: str) -> str:
    if capability_id.startswith("research_memory."):
        if capability_id in {"research_memory.import_note", "research_memory.export_json"}:
            return "local_write"
        return "retrieve_memory"
    if capability_id.startswith("public_release."):
        return "research"
    if capability_id.startswith("eva_v2."):
        return "draft_content"
    if capability_id.startswith("eva."):
        if capability_id.startswith("eva.control_center") or capability_id == "eva.dashboard_url":
            return "control_center_status"
        if capability_id in {"eva.specialists_status", "eva.specialist_select"}:
            return "specialist_selection"
        if capability_id in {"eva.skills_status", "eva.skill_select"}:
            return "skill_selection"
        if capability_id in {"eva.workflow_select", "eva.workflow_plan", "eva.fileagent_project_note_workflow"}:
            return "workflow_plan"
        if capability_id in {"eva.workflow_state", "eva.workflow_latest_approval", "eva.workflow_latest_apply", "eva.file_latest_status"}:
            return "workflow_state"
        if capability_id == "eva.workflow_next_step":
            return "workflow_next_step"
        if capability_id == "eva.workflow_disambiguate":
            return "workflow_disambiguation"
        if capability_id in {"eva.ask", "eva.natural_router"}:
            return "natural_request"
        if capability_id in {"eva.authority_status", "eva.authority_decision_preview"}:
            return "authority_decision"
        return "verification"
    if capability_id.startswith("file."):
        if capability_id in {"file.sandbox_apply_approved", "file.sandbox_verify_apply", "file.sandbox_rollback_apply", "file.sandbox_apply_policy", "file.apply_executor_status"}:
            return "file_sandbox_apply"
        if capability_id in {"file.real_apply_policy", "file.real_apply_eligibility", "file.real_create_new_text_file", "file.real_verify_new_text_file", "file.real_rollback_new_text_file", "file.real_create_eligibility", "file.real_create_safe_text", "file.real_create_verify", "file.real_create_rollback"}:
            return "file_real_create"
        if capability_id.startswith("file.approval_"):
            return "file_approval"
        if capability_id in {"file.apply_readiness", "file.write_safety_policy", "file.rollback_plan", "file.verification_plan"}:
            return "file_apply_readiness"
        if capability_id in {"file.draft_create_preview", "file.draft_append_preview", "file.draft_replace_preview", "file.diff_preview", "file.draft_readme_section", "file.draft_project_summary", "file.draft_report_outline", "file.draft_project_todo"}:
            return "file_draft_preview"
        if capability_id == "file.search_name":
            return "file_search"
        if capability_id == "file.preview_text":
            return "file_preview"
        if capability_id in {"file.understand_text", "file.summarize_text"}:
            return "file_understanding"
        if capability_id in {"file.project_inventory", "file.project_explain", "file.project_missing", "file.project_dependencies"}:
            return "project_inventory"
        if capability_id == "file.explain_project_structure":
            return "file_project_structure"
        return "file_inspect"
    if capability_id.startswith("browser."):
        return "browser_safety_status"
    return "research"


def _availability_from_resolution(final_status: str) -> str:
    if final_status in {"available_read_only", "available_explicit_local_write"}:
        return "available_now"
    if final_status == "disabled_experimental":
        return "disabled"
    if final_status == "reference_only":
        return "reference_only"
    if final_status in {"blocked", "unknown"}:
        return "blocked"
    if final_status == "resource_missing":
        return "missing"
    return "preview_only"


def _permission_from_resolution(resolution: object) -> str:
    if resolution.requires_override:
        return "override_required"
    if resolution.requires_confirmation:
        return "confirmation_required"
    if resolution.final_status in {"blocked", "unknown", "disabled_experimental", "reference_only"}:
        return "blocked"
    if resolution.final_status == "preview_only":
        return "preview_only"
    return "allowed"


def _dedupe(items: list[str | None]) -> list[str]:
    output: list[str] = []
    for item in items:
        if item and item not in output:
            output.append(item)
    return output


def _assign_step_ids(steps: list[EvaTaskStep]) -> list[EvaTaskStep]:
    old_to_new: dict[str, str] = {}
    for index, step in enumerate(steps, start=1):
        old_id = step.step_id
        new_id = f"step_{index}"
        if old_id not in old_to_new:
            old_to_new[old_id] = new_id
        step.step_id = new_id
    for step in steps:
        step.depends_on = [old_to_new.get(dep, dep) for dep in step.depends_on if dep]
    return steps
