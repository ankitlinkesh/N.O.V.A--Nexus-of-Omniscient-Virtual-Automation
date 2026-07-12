from __future__ import annotations

from datetime import datetime, timezone

from .models import ControlCenterStatus, unavailable_summary


def collect_control_center_status() -> ControlCenterStatus:
    warnings: list[str] = []
    return ControlCenterStatus(
        app_name="Eva Control Center",
        phase="Phase 33 Execution Boundary Audit / Roadmap Foundations",
        authority_summary=_authority_summary(warnings),
        natural_router_summary=_natural_router_summary(),
        llm_router_summary=_llm_router_summary(warnings),
        llm_validation_summary=_llm_validation_summary(warnings),
        llm_red_team_summary=_llm_red_team_summary(warnings),
        context_engine_summary=_context_engine_summary(warnings),
        threat_defense_summary=_threat_defense_summary(warnings),
        agent_loop_summary=_agent_loop_summary(warnings),
        workflow_planner_summary=_workflow_planner_summary(warnings),
        execution_gates_summary=_execution_gates_summary(warnings),
        memory_v3_summary=_memory_v3_summary(warnings),
        voice_assistant_summary=_voice_assistant_summary(warnings),
        ai_os_summary=_ai_os_summary(warnings),
        browser_readonly_summary=_browser_readonly_summary(warnings),
        desktop_observation_mode_summary=_desktop_observation_mode_summary(warnings),
        desktop_control_gate_summary=_desktop_control_gate_summary(warnings),
        news_dashboard_summary=_news_dashboard_summary(warnings),
        coding_agent_summary=_coding_agent_summary(warnings),
        release_demo_summary=_release_demo_summary(warnings),
        release_candidate_summary=_release_candidate_summary(warnings),
        file_agent_summary=_file_agent_summary(warnings),
        approval_summary=_approval_summary(warnings),
        sandbox_apply_summary=_sandbox_apply_summary(warnings),
        real_apply_summary=_real_apply_summary(warnings),
        golden_workflow_summary=_golden_workflow_summary(warnings),
        phase12_health_summary=_phase12_health_summary(),
        browser_agent_summary=_browser_agent_summary(warnings),
        browser_session_summary=_browser_session_summary(warnings),
        browser_observation_summary=_browser_observation_summary(warnings),
        browser_action_summary=_browser_action_summary(warnings),
        browser_domain_summary=_browser_domain_summary(warnings),
        browser_readiness_proof_summary=_browser_readiness_proof_summary(warnings),
        desktop_agent_summary=_desktop_agent_summary(warnings),
        desktop_session_summary=_desktop_session_summary(warnings),
        desktop_screen_summary=_desktop_screen_summary(warnings),
        desktop_action_summary=_desktop_action_summary(warnings),
        desktop_risk_summary=_desktop_risk_summary(warnings),
        desktop_approval_summary=_desktop_approval_summary(warnings),
        desktop_readiness_proof_summary=_desktop_readiness_proof_summary(warnings),
        capability_summary=_capability_summary(warnings),
        specialist_summary=_specialist_summary(warnings),
        skill_summary=_skill_summary(warnings),
        workflow_summary=_workflow_summary(warnings),
        latest_workflow_summary=_latest_workflow_summary(warnings),
        work_session_summary=_work_session_summary(warnings),
        project_reality_summary=_project_reality_summary(warnings),
        locked_feature_summary=_locked_feature_summary(),
        agent_summary=_agent_summary(warnings),
        planner_summary=_planner_summary(warnings),
        verifier_summary=_verifier_summary(),
        safety_summary=_safety_summary(),
        future_modules=_future_modules(),
        warnings=warnings,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def _authority_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..authority.status import format_authority_status

        return {
            "status": "Active",
            "mode": "deterministic local authority spine",
            "real_execution": "blocked by default",
            "sandbox_apply": "available through FileAgent sandbox only",
            "summary": _first_sentence(format_authority_status()),
        }
    except Exception:
        warnings.append("Authority status unavailable.")
        return unavailable_summary("Authority", "Authority module could not be summarized.")


def _natural_router_summary() -> dict[str, object]:
    return {
        "status": "Active",
        "mode": "deterministic local routing",
        "entrypoint": "eva ask <request>",
        "llm_backed_routing": "planned later",
        "summary": "Natural requests are interpreted locally and routed to existing safe commands.",
    }


def _llm_router_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..llm.status import get_llm_router_status
        from ..llm.routing_policy import get_fallback_policy
        from ..llm.limits import get_cost_budget, get_token_budget

        status = get_llm_router_status()
        from ..llm.limits import get_rate_limit_policy, get_runaway_protection_policy
        from ..llm.session_limits import get_session_limit_policy
        from ..llm.routing_audit import get_routing_audit_preview
        return {"status": status.status, "live_provider_calls": "locked", "mode": status.mode.value, "provider_metadata": ", ".join(item.provider.value for item in status.providers), "fallback_policy": " -> ".join(item.value for item in get_fallback_policy().order), "limits": f"{get_token_budget().max_input_tokens}/{get_token_budget().max_output_tokens} tokens; ${get_cost_budget().max_cost_usd:.2f}; session {get_session_limit_policy().max_router_steps} steps", "structured_output": "mock validation only", "degraded_mode": "mock/status only", "rate_limit": get_rate_limit_policy().response, "runaway_protection": get_runaway_protection_policy().stop_behavior, "routing_audit": get_routing_audit_preview().summary, "next_phase": "Phase 15C Structured Output Validation Hardening", "summary": status.summary}
    except Exception:
        warnings.append("LLM Router status unavailable.")
        return unavailable_summary("LLM Router", "LLM Router contract summary could not be collected.")


def _llm_validation_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..llm.schema_registry import list_contracts

        return {
            "status": "available",
            "schema_registry": f"{len(list_contracts())} preview-only contracts registered",
            "safe_failure": "malformed or invalid output becomes a local refusal preview",
            "repair_policy": "does not execute or rewrite user intent",
            "hallucinated_capabilities": "flagged and blocked",
            "tool_execution": "invalid LLM output cannot execute tools",
            "live_llm_calls": "locked",
            "validation_mode": "mock/local only",
            "next_phase": "Phase 15C-D Docs + Master Proof",
            "summary": "Structured-output validation is local, read-only, and cannot enable execution.",
        }
    except Exception:
        warnings.append("LLM structured-output validation status unavailable.")
        return unavailable_summary("LLM Structured Output Validation", "Local validation summary could not be collected.")


def _llm_red_team_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..llm.red_team_cases import list_red_team_cases
        return {"status": "available", "case_count": len(list_red_team_cases()), "categories": "unsafe output, injection, secrets, provider failures", "last_run": "local simulated run available", "failure_policy": "report/status only", "unsafe_output": "blocked/refusal preview", "tool_execution": "blocked", "secret_reads": "blocked", "live_llm_calls": "locked", "next_phase": "Phase 16 Context Assembly Engine"}
    except Exception:
        warnings.append("LLM red-team status unavailable.")
        return unavailable_summary("LLM Red-Team / Failure Tests", "Local red-team summary could not be collected.")


def _context_engine_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..context_engine.source_registry import list_allowed_sources, list_blocked_sources
        from ..context_engine.status import get_context_engine_status

        status = get_context_engine_status()
        return {
            "status": status.status,
            "mode": status.mode,
            "allowed_sources": len(list_allowed_sources()),
            "blocked_sources": len(list_blocked_sources()),
            "budget_policy": "default safe budget with section-level trimming/exclusion",
            "redaction_policy": "secret-like and private-path-like text is redacted or blocked",
            "grounding_status": "source-aware packet preview with unsupported assumptions marked",
            "injection_handling": "prompt-injection-like context is untrusted data",
            "readiness": "ready for local preview; not connected to live LLM calls",
            "live_llm_calls": "locked",
            "tool_execution": "assembled context cannot execute tools",
            "next_phase": status.next_phase,
        }
    except Exception:
        warnings.append("Context Assembly Engine status unavailable.")
        return unavailable_summary("Context Assembly Engine", "Context assembly summary could not be collected.")


def _threat_defense_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..threat_defense.status import get_threat_defense_status
        from ..threat_defense.threat_catalog import list_threat_categories

        status = get_threat_defense_status()
        return {
            "status": status.status,
            "mode": status.mode,
            "threat_categories": len(list_threat_categories()),
            "instruction_hierarchy": "system/developer and Eva safety policy outrank untrusted context",
            "injection_handling": "prompt-injection-like content is treated as untrusted data",
            "exfiltration_handling": "secrets/config/session data are blocked",
            "tool_request_boundary": "defended context cannot execute tools",
            "context_poisoning": "memory/tool/webpage-like instructions remain data only",
            "readiness": "ready for local preview; not connected to live LLM calls",
            "live_llm_calls": "locked",
            "next_phase": status.next_phase,
        }
    except Exception:
        warnings.append("LLM threat defense status unavailable.")
        return unavailable_summary("LLM Threat Defense + Prompt Injection Guard", "Threat defense summary could not be collected.")


def _agent_loop_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..agent_loop.status import get_agent_loop_status
        from ..agent_loop.step_limiter import get_step_limit_policy

        status = get_agent_loop_status()
        policy = get_step_limit_policy()
        return {
            "status": status.status,
            "mode": status.mode,
            "loop_policy": "bounded local preview loop; no live execution",
            "step_limit_policy": f"default {policy.default_max_steps}; hard {policy.hard_max_steps}",
            "stage_summary": "receive, route, context preview, threat preview, plan preview, action previews, mock observations, verify, report, stop",
            "action_preview_safety": "actions are preview-only",
            "stop_reasons": "completed_preview, step_limit_exceeded, repeated_step_detected, no_progress_detected",
            "no_tool_execution_boundary": "tools are not executed",
            "readiness": "ready for local preview; not connected to live LLM calls",
            "live_llm_calls": "locked",
            "next_phase": status.next_phase,
        }
    except Exception:
        warnings.append("Agent Loop v1 status unavailable.")
        return unavailable_summary("Agent Loop v1", "Agent Loop summary could not be collected.")


def _workflow_planner_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..workflow_planner.status import get_workflow_planner_status
        from ..workflow_planner.workflow_catalog import list_workflow_templates

        status = get_workflow_planner_status()
        return {
            "status": status.status,
            "mode": status.mode,
            "workflow_catalog_summary": f"{len(list_workflow_templates())} local preview templates",
            "workflow_policy": "local/mock preview only; workflow steps are preview-only",
            "dependency_validation_status": "dependency cycles are detected and blocked",
            "approval_preview_policy": "future approval metadata only; no execution unlocked",
            "rollback_preview_policy": "rollback preview metadata only",
            "verification_plan_status": "local verification checks generated for every preview",
            "no_tool_execution_boundary": "tools are not executed",
            "readiness": "ready for local preview; not connected to live LLM calls",
            "live_llm_calls": "locked",
            "next_phase": status.next_phase,
        }
    except Exception:
        warnings.append("Agentic Workflow Planner status unavailable.")
        return unavailable_summary("Agentic Workflow Planner", "Workflow Planner summary could not be collected.")


def _execution_gates_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..execution_gates.status import get_execution_gates_status
        from ..execution_gates.gate_policy import ACTION_CLASSES, DECISION_STATES

        status = get_execution_gates_status()
        return {
            "status": status.status,
            "mode": status.mode,
            "gate_policy_summary": "local/mock policy preview only; no execution unlocked",
            "decision_states": ", ".join(DECISION_STATES),
            "allowed_preview_classes": "status_or_report, local_preview, context_preview, threat_scan_preview, agent_loop_preview, workflow_preview, fileagent_draft_preview",
            "blocked_action_classes": ", ".join(item for item in ACTION_CLASSES if item.startswith("forbidden_") or item == "unknown_or_hallucinated_action"),
            "approval_policy": "approval alone does not execute",
            "confirmation_policy": "confirmation alone does not execute unless an existing implemented gate accepts it",
            "rollback_policy": "metadata/preview only except existing Phase 12L rollback boundary if already implemented",
            "existing_phase12l_boundary": status.existing_real_write_boundary,
            "future_gate_candidates": "future file read-only, browser read-only, and desktop observation candidates remain locked",
            "readiness": "ready for local gate policy/status/evaluation reports",
            "live_llm_calls": "locked",
            "tool_execution": "tools are not executed",
            "next_phase": status.next_phase,
        }
    except Exception:
        warnings.append("Controlled Execution Gates status unavailable.")
        return unavailable_summary("Controlled Execution Gates", "Execution Gates summary could not be collected.")


def _memory_v3_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..memory_v3.status import get_memory_v3_status

        status = get_memory_v3_status()
        return {
            "status": status.status,
            "mode": status.mode,
            "memory_policy_summary": "source-aware, trust-aware, freshness-aware, privacy-aware, conflict-aware, and grounding-aware",
            "source_trust_model": "explicit user, verified evidence, local status, summaries, untrusted text, and unknown/stale classes",
            "privacy_filter_status": "secrets, credentials, sessions, cookies, and private paths blocked or redacted",
            "freshness_status": "stale memories marked and excluded until safely grounded",
            "conflict_detection_status": "conflicts reported, not merged blindly",
            "context_injection_rules": "eligible safe grounded summaries only; preview/policy only",
            "grounding_status": "current verified project evidence preferred over older memory",
            "local_no_cloud_boundary": "local only; no cloud memory or remote sync",
            "readiness": "ready for local policy/status/retrieval previews",
            "tool_execution": "memory cannot execute tools",
            "next_phase": status.next_phase,
        }
    except Exception:
        warnings.append("Memory v3 status unavailable.")
        return unavailable_summary("Memory v3", "Memory v3 summary could not be collected.")


def _voice_assistant_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..voice_assistant.status import get_voice_assistant_status

        status = get_voice_assistant_status()
        return {
            "status": status.status,
            "mode": status.mode,
            "lifecycle_state": status.lifecycle_state,
            "provider_policy": "ASR/TTS providers are locked candidates only",
            "microphone_boundary": "locked; no microphone access",
            "audio_playback_boundary": "locked; text preview only",
            "transcript_safety": status.transcript_safety_status,
            "confirmation_policy": status.confirmation_policy,
            "execution_gate_integration": status.execution_gate_integration,
            "readiness": status.readiness,
            "next_phase": status.next_phase,
        }
    except Exception:
        warnings.append("Voice Assistant Foundation status unavailable.")
        return unavailable_summary("Voice Assistant Foundation", "Voice Assistant summary could not be collected.")


def _ai_os_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..ai_os.readiness import build_ai_os_dashboard
        from ..ai_os.status import get_ai_os_status

        status = get_ai_os_status()
        dashboard = build_ai_os_dashboard()
        return {
            "status": status.status,
            "overview": dashboard.overall_readiness,
            "phase_health": dashboard.phase_health_summary,
            "system_map": dashboard.system_map_summary,
            "capability_matrix": dashboard.capability_matrix_summary,
            "feature_states": "status-only, preview-only, existing narrow gate, locked, blocked, and future states are distinguished",
            "locked_future_gates": ", ".join(dashboard.locked_future_gates),
            "next_safe_step": dashboard.next_recommended_safe_step,
            "preview_real_distinction": dashboard.existing_narrow_real_gate_summary,
            "readiness": status.overall_readiness,
            "next_phase": status.next_phase,
        }
    except Exception:
        warnings.append("AI OS status unavailable.")
        return unavailable_summary("AI OS overview", "AI OS summary could not be collected.")


def _browser_readonly_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..browser_readonly.backend_policy import get_backend_policy
        from ..browser_readonly.observer import observe_mock_page
        from ..browser_readonly.status import get_browser_readonly_status

        status = get_browser_readonly_status()
        backend = get_backend_policy()
        mock = observe_mock_page()
        return {
            "status": status.status,
            "url_policy": "public http:// and https:// only; private, local, internal, sensitive, and injection-like URLs blocked",
            "backend_availability": f"{backend.mode}; deterministic mock fixture available",
            "session_isolation_policy": "ephemeral, sessionless, credentialless, no-cookie, no-profile, and no persistent state",
            "read_only_boundaries": "no click, type, forms, downloads, uploads, login, logged-in browser access, or browser control",
            "blocked_url_classes": "non-HTTP(S), localhost/private/link-local/metadata/internal, credentials, sensitive URL content, command injection",
            "last_mock_observation_summary": f"{mock.final_status}; {mock.title_preview}",
            "execution_gate_integration": mock.execution_gate_decision,
            "readiness": status.readiness,
            "next_phase": status.next_phase,
        }
    except Exception:
        warnings.append("Real Browser Read-Only Mode status unavailable.")
        return unavailable_summary("Real Browser Read-Only Mode", "Browser read-only summary could not be collected.")


def _desktop_observation_mode_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..desktop_observation.backend_policy import get_backend_policy
        from ..desktop_observation.observer import observe_mock_desktop
        from ..desktop_observation.status import get_desktop_observation_status

        status = get_desktop_observation_status()
        backend = get_backend_policy()
        mock = observe_mock_desktop()
        return {
            "status": status.status,
            "observation_policy": "explicit user-triggered one-shot observation/report only",
            "backend_availability": f"{backend.mode}; deterministic mock fixture available",
            "capture_gate_policy": "observation-only; no persistence, background activity, or desktop authority",
            "sensitive_screen_policy": "login, payment, chat, browser session, secret, private path, security, terminal, code-secret, and unknown screens classified",
            "redaction_policy": "secret-like and private-path-like content is redacted before summary output",
            "observation_only_boundaries": "no click, type, hotkey, mouse, clipboard, app/window control, continuous monitoring, or saved screenshots",
            "last_mock_observation_summary": f"{mock.final_status}; {mock.sensitive_screen_classification}",
            "execution_gate_integration": mock.execution_gate_decision,
            "readiness": status.readiness,
            "next_phase": status.next_phase,
        }
    except Exception:
        warnings.append("Real Desktop Observation Mode status unavailable.")
        return unavailable_summary("Real Desktop Observation Mode", "Desktop observation summary could not be collected.")


def _desktop_control_gate_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..desktop_control_gate.action_catalog import ACTION_CLASSES
        from ..desktop_control_gate.approval_policy import approval_policy_text
        from ..desktop_control_gate.confirmation_policy import confirmation_policy_text
        from ..desktop_control_gate.control_policy import control_policy_text
        from ..desktop_control_gate.dry_run import build_desktop_control_dry_run
        from ..desktop_control_gate.status import get_desktop_control_gate_status

        status = get_desktop_control_gate_status()
        dry_run = build_desktop_control_dry_run("click a sample button")
        return {
            "status": status.mode,
            "control_policy": control_policy_text().splitlines()[1],
            "action_classes": ", ".join(ACTION_CLASSES),
            "risk_scoring": f"{dry_run.risk_level} ({dry_run.risk_score}) for deterministic sample",
            "approval_policy": approval_policy_text().splitlines()[-1],
            "confirmation_policy": confirmation_policy_text().splitlines()[-1],
            "dry_run_behavior": dry_run.final_status,
            "blocked_action_classes": "secrets, destructive, shell, package, browser control, file writes, unknown actions",
            "rollback_audit_metadata": "rollback/audit are metadata only",
            "no_control_boundary": "desktop control is not enabled",
            "readiness": status.readiness,
            "next_phase": status.next_phase,
        }
    except Exception:
        warnings.append("Real Desktop Control Gate status unavailable.")
        return unavailable_summary("Real Desktop Control Gate", "Desktop control-gate summary could not be collected.")


def _news_dashboard_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..news_dashboard.mock_feeds import build_mock_dashboard
        from ..news_dashboard.status import get_news_dashboard_status
        d=build_mock_dashboard(); s=get_news_dashboard_status()
        return {"status":s.backend_mode,"dashboard_policy":"local/mock or safe-read-only only","backend_availability":"live backend unavailable","topic_model":d.topic,"source_card_status":f"{len(d.source_cards)} fixture cards","event_card_status":f"{len(d.event_cards)} fixture cards","freshness_policy":", ".join(d.freshness_labels),"reliability_uncertainty_policy":d.uncertainty_notes[0],"crawler_blocked_boundary":"no unrestricted crawler","login_session_blocked_boundary":"no login/session/cookie/profile access","readiness":s.readiness,"next_phase":s.next_phase}
    except Exception:
        warnings.append("News dashboard status unavailable.")
        return unavailable_summary("News / Web Intelligence Dashboard","News dashboard summary unavailable.")


def _coding_agent_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..coding_agent.coding_policy import SPECIALIST_MODES
        from ..coding_agent.report import build_coding_report
        from ..coding_agent.status import get_coding_status

        status = get_coding_status()
        report = build_coding_report("plan a code change")
        return {
            "status": status.mode,
            "coding_policy": "deterministic local preview/report/status only",
            "specialist_modes": f"{len(SPECIALIST_MODES)} preview specialists",
            "task_classification": report.coding_task_type,
            "project_context_policy": "existing safe metadata/status/docs summaries only",
            "patch_plan_policy": report.patch_preview_summary,
            "review_checklist_status": f"{len(report.review_checklist)} review checks available",
            "test_plan_policy": "instructions/checklists only; tests are never run",
            "risk_review_status": f"{len(report.risk_review)} deterministic risk checks available",
            "handoff_report_status": "human-readable preview available",
            "blocked_execution_classes": "source edit, patch, shell, test, package, git, tool, browser, desktop, cloud, MCP",
            "no_source_edit_boundary": "CodingAgent real source editing remains locked",
            "readiness": status.readiness,
            "next_phase": status.next_phase,
        }
    except Exception:
        warnings.append("CodingAgent status unavailable.")
        return unavailable_summary(
            "Coding Specialist / CodingAgent Foundation",
            "CodingAgent preview summary unavailable.",
        )


def _release_demo_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..release_demo.demo_profile import build_demo_profile
        from ..release_demo.status import get_release_demo_status

        profile = build_demo_profile()
        status = get_release_demo_status()
        return {
            "release_status": status.mode,
            "demo_readiness": status.readiness,
            "verified_milestones": f"{len(profile.verified_milestone_summary)} public milestone summaries",
            "capability_map": f"{len(profile.capability_map_summary)} capability boundary entries",
            "demo_commands": f"{len(profile.demo_command_list)} local report commands",
            "safety_proof": f"{len(profile.safety_proof_summary)} safety proof statements",
            "known_limitations": f"{len(profile.known_limitations)} explicit limitations",
            "verification_status": "manual verifier bundle available; fresh terminal evidence required",
            "blocked_unsafe_features": f"{len(profile.blocked_feature_summary)} blocked feature groups",
            "no_publish_no_commit_boundary": "publishing, uploading, commit, tag, and push are unavailable",
            "next_safe_step": profile.next_safe_step,
        }
    except Exception:
        warnings.append("Public Demo / Release status unavailable.")
        return unavailable_summary(
            "Public Demo / Release",
            "Release demo summary unavailable.",
        )


def _release_candidate_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..release_candidate.report import build_release_candidate_report
        from ..release_candidate.status import get_release_candidate_status

        report = build_release_candidate_report()
        status = get_release_candidate_status()
        return {
            "rc_status": status.readiness,
            "dirty_tree_summary": report.dirty_tree_summary,
            "commit_plan_summary": f"{len(report.commit_grouping_plan)} logical review groups; text only",
            "hardening_report": report.docs_consistency_status,
            "checklist_status": f"{len(report.release_candidate_checklist)} checks prepared",
            "verification_status": report.verification_status,
            "safety_boundary_status": report.safety_boundary_status,
            "known_warnings": f"{len(report.known_warnings)} non-blocking warnings",
            "blocking_issues": "none" if not report.blocking_issues else "; ".join(report.blocking_issues),
            "no_commit_no_publish_boundary": "no add, commit, tag, push, publish, or upload through Eva",
            "recommended_next_action": report.recommended_next_action,
        }
    except Exception:
        warnings.append("Release Candidate Hardening status unavailable.")
        return unavailable_summary(
            "Release Candidate Hardening",
            "Release-candidate summary unavailable.",
        )


def _file_agent_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..file_agent.status import file_agent_status

        status = file_agent_status()
        return {
            "status": "Active",
            "read_only": status.read_only,
            "draft_previews": status.draft_previews,
            "approval_ledger": status.approval_ledger,
            "sandbox_apply_harness": status.sandbox_apply_harness,
            "real_apply": "12L narrow real create only",
            "summary": "FileAgent supports safe inspection, project inventory, draft previews, approvals, sandbox-only apply tests, and the guarded 12L create-new-text-file path.",
        }
    except Exception:
        warnings.append("FileAgent status unavailable.")
        return unavailable_summary("FileAgent", "FileAgent module could not be summarized.")


def _approval_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..file_agent.approval_ledger import APPROVAL_STATUSES, list_file_approval_requests

        requests = list_file_approval_requests(limit=200)
        counts = {status: 0 for status in sorted(APPROVAL_STATUSES)}
        for request in requests:
            counts[request.status] = counts.get(request.status, 0) + 1
        return {
            "status": "Active",
            "total": len(requests),
            "pending": counts.get("pending", 0),
            "approved_for_future_apply": counts.get("approved_for_future_apply", 0),
            "denied": counts.get("denied", 0),
            "cancelled": counts.get("cancelled", 0),
            "expired": counts.get("expired", 0),
            "blocked": counts.get("blocked", 0),
            "summary": "Approval records are metadata only; approval does not apply real files.",
        }
    except Exception:
        warnings.append("Approval ledger unavailable.")
        return unavailable_summary("Approvals", "Approval ledger could not be summarized.")


def _sandbox_apply_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..file_agent.apply_executor import format_apply_executor_status

        return {
            "status": "Available",
            "mode": "sandbox harness only",
            "real_project_files": "not modified",
            "verification": "sandbox readback and hash comparison",
            "rollback": "sandbox checkpoint only",
            "summary": _first_sentence(format_apply_executor_status()),
        }
    except Exception:
        warnings.append("Sandbox apply status unavailable.")
        return unavailable_summary("Sandbox Apply", "Sandbox apply harness could not be summarized.")


def _real_apply_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..file_agent.approval_ledger import list_file_approval_requests
        from ..file_agent.real_apply import evaluate_real_apply_eligibility

        eligible = []
        for approval in list_file_approval_requests(status="approved_for_future_apply", limit=50):
            item = evaluate_real_apply_eligibility(approval.approval_id)
            if item.allowed:
                eligible.append(item)
        latest_event = "none"
        for approval in list_file_approval_requests(limit=50):
            events = list(getattr(approval, "events", []) or [])
            real_events = [event for event in events if str(getattr(event, "event_type", "")).startswith(("real_create_", "real_apply_"))]
            if real_events:
                latest_event = real_events[-1].event_type
                break
        return {
            "status": "Narrowly limited",
            "allowed": "create-new-text-file only under docs/ or samples/",
            "blocked": "overwrite/edit/delete/source/config/runtime",
            "pending_eligible_approvals": len(eligible),
            "latest_event": latest_event,
            "rollback": "available only for unchanged Eva-created files",
            "summary": "Real apply is Phase 12L create-new-text-file only. Existing files cannot be edited or overwritten. Source/config/runtime files are blocked.",
        }
    except Exception:
        warnings.append("Narrow real apply status unavailable.")
        return unavailable_summary("Narrow Real Apply Gate", "Real-create gate could not be summarized.")


def _golden_workflow_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..golden_workflows.runner import get_golden_workflow_status

        status = get_golden_workflow_status()
        return {
            "status": "Available",
            "available_workflows": len(status.available_workflows),
            "main_workflow": "safe_project_note_create",
            "latest_stage": status.latest_stage,
            "pending_approvals": status.pending_approvals,
            "approved_for_future_apply": status.approved_for_future_apply,
            "latest_real_create_status": status.latest_real_create_status,
            "rollback_available": "yes" if status.rollback_available else "no",
            "next_safe_action": status.next_safe_action,
            "summary": "Golden workflow connects draft, approval, sandbox apply, narrow real-create eligibility, exact confirmation, verification, and rollback.",
        }
    except Exception:
        warnings.append("Golden workflow status unavailable.")
        return unavailable_summary("Golden Workflows", "Golden workflow status could not be summarized.")


def _phase12_health_summary() -> dict[str, object]:
    return {
        "status": "Available",
        "smoke_verifier": "scripts/verify_eva_smoke.py",
        "full_verifier": "scripts/verify_eva_all.py",
        "quick_command": r".\.venv\Scripts\python.exe scripts\verify_eva_all.py --quick",
        "full_command": r".\.venv\Scripts\python.exe scripts\verify_eva_all.py --full",
        "latest_known_status": "Not run in this dashboard session",
        "summary": "Read-only verification status. The dashboard does not run verifiers or subprocesses.",
    }


def _browser_agent_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..browser_agent.status import get_browser_agent_status

        status = get_browser_agent_status()
        return {
            "status": status.status,
            "real_browser_control": status.real_browser_control,
            "allowed_now": "policy/readiness/action preview only",
            "blocked_actions": "launch, navigate, click, type, submit, login, payment, upload, download, cookies, localStorage, profiles, screenshots",
            "next_phase": status.next_phase,
            "summary": status.summary,
        }
    except Exception:
        warnings.append("BrowserAgent safety status unavailable.")
        return unavailable_summary("BrowserAgent", "BrowserAgent safety model could not be summarized.")


def _browser_session_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..browser_agent.readiness import get_browser_session_readiness
        from ..browser_agent.session_registry import get_latest_preview_session, list_preview_sessions

        readiness = get_browser_session_readiness()
        latest = get_latest_preview_session()
        return {
            "status": "Preview only",
            "session_preview_status": readiness.status,
            "latest_preview_session": latest.session_id if latest else "none",
            "allowed_now": "preview records, session status, readiness, and lifecycle plan",
            "blocked_now": "launch, navigation, screenshots, DOM reads, click/type/submit/login/payment/upload/download, cookies, localStorage, profiles, sessions, passwords",
            "domain_policy_summary": "preview only; no page or browser state is read",
            "next_browser_phase": readiness.next_phase,
            "readiness_gaps": "; ".join(readiness.gaps[:3]),
            "preview_sessions": len(list_preview_sessions()),
            "summary": readiness.summary,
        }
    except Exception:
        warnings.append("Browser session preview status unavailable.")
        return unavailable_summary("Browser Session Preview", "Browser session preview could not be summarized.")


def _browser_observation_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..browser_agent.observation_policy import get_browser_observation_policy, get_browser_redaction_rules

        policy = get_browser_observation_policy()
        rules = get_browser_redaction_rules()
        return {
            "status": "Design preview only",
            "page_text_dom_summary_design": policy.mode,
            "live_browser_reads": "locked",
            "screenshots": "locked",
            "dom_reads": "locked",
            "redaction_policy": f"{len(rules)} local redaction rules",
            "future_readonly_requirements": "; ".join(policy.future_requirements[:3]),
            "next_browser_phase": "BrowserAgent read-only observation design with explicit local observation gates.",
            "summary": "Browser observation is schema/policy preview only; no live page, screenshot, DOM, or browser state is read.",
        }
    except Exception:
        warnings.append("Browser observation preview status unavailable.")
        return unavailable_summary("Browser Observation Preview", "Browser observation preview could not be summarized.")


def _browser_action_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..browser_agent.action_dry_run import BLOCKED_BROWSER_EXECUTION, get_browser_action_approval_requirements

        approvals = get_browser_action_approval_requirements()
        return {
            "status": "Dry-run only",
            "allowed_now": "plan text, risk explanation, approval preview, blocked-action explanation",
            "blocked_execution": "; ".join(BLOCKED_BROWSER_EXECUTION[:3]),
            "risk_levels": "low_status_only, medium_readonly_future, high_user_confirmation_required, critical_blocked, forbidden",
            "approval_requirements": f"{len(approvals)} preview approval categories",
            "next_phase": "BrowserAgent executor readiness with explicit observation and human-in-the-loop gates.",
            "summary": "Browser actions can be planned as dry-run text only; real browser execution is locked.",
        }
    except Exception:
        warnings.append("Browser action dry-run status unavailable.")
        return unavailable_summary("Browser Action Dry-Run", "Browser action dry-run could not be summarized.")


def _browser_domain_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..browser_agent.domain_rules import get_domain_policy_result, get_sensitive_action_markers

        policy = get_domain_policy_result()
        markers = get_sensitive_action_markers()
        sensitive = "email, social, banking, payment, cloud storage, file hosting, government"
        blocked = "harmful/adult/illegal/malware/phishing/piracy plus all real browser execution"
        return {
            "status": "Policy/status only",
            "site_risk_model_status": policy.status,
            "sensitive_categories": sensitive,
            "blocked_categories": blocked,
            "approval_requirements": f"{len(markers)} future approval marker categories; no approval enables execution now",
            "next_phase": "BrowserAgent read-only domain-gated observation preview.",
            "summary": "Browser domain risk is string classification only. Real browser access is locked; no network, DNS, page, screenshot, DOM, cookie, localStorage, profile, shell, package, MCP, PyAutoGUI, or cloud call is made.",
        }
    except Exception:
        warnings.append("Browser domain risk status unavailable.")
        return unavailable_summary("Browser Domain Risk", "Browser domain risk model could not be summarized.")


def _browser_readiness_proof_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..browser_agent.readiness_proof import build_browser_readiness_proof
        from ..browser_agent.phase13_final import build_browser_phase13_final_proof

        proof = build_browser_readiness_proof()
        final = build_browser_phase13_final_proof()
        return {
            "status": proof.status.value,
            "completed_safety_layers": ", ".join(proof.completed_layers),
            "readiness_gaps": len(proof.gaps),
            "locked_execution_summary": "; ".join(proof.locked_execution[:4]),
            "next_browser_phase": proof.next_phase,
            "proof_status": "proof/status only; real browser read-only mode is not enabled",
            "summary": proof.summary,
            "phase13_final_proof": "Phase 13 final proof: Phase 13 is safety/readiness only; real browser read-only mode is not enabled; real browser control is not enabled.",
            "phase13_final_limits": "network/DNS/live page read/DOM/screenshot/action execution are locked",
            "future_gate": final.future_gate,
            "phase12_boundary": "Phase 12L narrow real create remains the only real write path.",
        }
    except Exception:
        warnings.append("Browser read-only readiness proof unavailable.")
        return unavailable_summary("Browser Read-Only Readiness Proof", "Browser read-only readiness proof could not be summarized.")


def _desktop_agent_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..desktop_agent.app_risk import classify_desktop_app_risk
        from ..desktop_agent.status import get_desktop_agent_status

        status = get_desktop_agent_status()
        terminal_risk = classify_desktop_app_risk("terminal")
        return {
            "status": status.status,
            "real_screen_observation": status.real_screen_observation,
            "real_desktop_control": status.real_desktop_control,
            "allowed_now": "policy/readiness/action preview only",
            "blocked_actions": "screen capture, screenshots, window inspection, app launch, mouse, keyboard, clipboard, file dialog, terminal, package install, external send",
            "app_risk_model": f"string classification only; terminal={terminal_risk.risk_level.value}",
            "next_phase": status.next_phase,
            "summary": status.summary,
        }
    except Exception:
        warnings.append("DesktopAgent safety status unavailable.")
        return unavailable_summary("DesktopAgent", "DesktopAgent safety model could not be summarized.")


def _desktop_session_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..desktop_agent.readiness import get_desktop_observation_readiness
        from ..desktop_agent.session_registry import get_latest_preview_session, list_preview_sessions

        readiness = get_desktop_observation_readiness()
        latest = get_latest_preview_session()
        return {
            "status": "Preview only",
            "session_preview_status": readiness.status,
            "latest_preview_session": latest.session_id if latest else "none",
            "app_window_schema_preview": "app/window schema preview only; no real apps or windows are inspected",
            "active_context_schema_preview": "active context schema preview only; no real active app is detected",
            "allowed_now": "preview records, session status, schema previews, readiness, and lifecycle plan",
            "blocked_now": "screen capture, screenshots, window enumeration, app inspection, active app detection, app launch, mouse, keyboard, clipboard, file dialogs, terminal, package, PyAutoGUI, Playwright, MCP, cloud",
            "readiness_gaps": "; ".join(readiness.gaps[:3]),
            "next_phase": readiness.next_phase,
            "preview_sessions": len(list_preview_sessions()),
            "summary": readiness.summary,
        }
    except Exception:
        warnings.append("Desktop session preview status unavailable.")
        return unavailable_summary("Desktop Session Preview", "Desktop session preview could not be summarized.")


def _desktop_screen_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..desktop_agent.redaction_policy import get_desktop_screen_redaction_rules
        from ..desktop_agent.screen_observation import get_desktop_screen_capture_gate
        from ..desktop_agent.screen_policy import get_desktop_screen_observation_readiness, get_desktop_screen_policy

        policy = get_desktop_screen_policy()
        gate = get_desktop_screen_capture_gate()
        readiness = get_desktop_screen_observation_readiness()
        redaction_rules = get_desktop_screen_redaction_rules()
        return {
            "status": "Policy preview only",
            "real_capture": "locked",
            "screenshots": "locked",
            "ocr": "locked",
            "image_analysis": "locked",
            "sensitive_categories": ", ".join(policy.sensitive_categories[:5]) + ", ...",
            "redaction_policy": f"{len(redaction_rules)} local redaction rules",
            "future_capture_gate": gate.status,
            "future_gate_requirements": "; ".join(gate.future_requirements[:3]),
            "readiness_gaps": "; ".join(readiness.gaps[:3]),
            "next_phase": readiness.next_phase,
            "summary": readiness.summary,
        }
    except Exception:
        warnings.append("Desktop screen observation policy unavailable.")
        return unavailable_summary("Desktop Screen Observation Policy", "Desktop screen observation policy could not be summarized.")


def _desktop_action_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..desktop_agent.action_dry_run import BLOCKED_DESKTOP_ACTION_EXECUTION, get_desktop_action_approval_requirements

        approvals = get_desktop_action_approval_requirements()
        return {
            "status": "Dry-run only",
            "allowed_now": "plan text, risk explanation, approval preview, blocked-action explanation",
            "blocked_execution": "; ".join(BLOCKED_DESKTOP_ACTION_EXECUTION[:4]),
            "risk_levels": "low_status_only, medium_future_observation, high_user_confirmation_required, critical_blocked, forbidden",
            "approval_requirements": f"{len(approvals)} preview approval categories",
            "next_phase": "Desktop Action Risk Scoring with verified UI targets and explicit human gates.",
            "summary": "Desktop actions can be planned as dry-run text only; real desktop control is locked.",
        }
    except Exception:
        warnings.append("Desktop action dry-run status unavailable.")
        return unavailable_summary("Desktop Action Dry-Run", "Desktop action dry-run could not be summarized.")


def _desktop_risk_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..desktop_agent.risk_scoring import RISK_FACTOR_NAMES, list_high_risk_desktop_actions
        from ..desktop_agent.safety_matrix import build_desktop_safety_matrix

        matrix = build_desktop_safety_matrix()
        return {
            "status": "Risk/status only",
            "risk_factors": ", ".join(RISK_FACTOR_NAMES[:6]) + ", ...",
            "approval_levels": "none_status_only, user_preview_required, explicit_user_confirmation_required, elevated_confirmation_required, forbidden_no_approval_available",
            "forbidden_action_classes": "; ".join(matrix.forbidden_action_classes[:3]),
            "high_risk_actions": "; ".join(list_high_risk_desktop_actions()[:4]),
            "readiness_gaps": "; ".join(matrix.readiness_gaps[:3]),
            "next_phase": matrix.next_phase,
            "summary": "Desktop action risk scoring is deterministic string-only status; real desktop execution is locked.",
        }
    except Exception:
        warnings.append("Desktop action risk scoring status unavailable.")
        return unavailable_summary("Desktop Action Risk Scoring", "Desktop action risk scoring could not be summarized.")


def _desktop_approval_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..desktop_agent.approval_audit import get_desktop_approval_audit_status
        from ..desktop_agent.approval_policy import get_desktop_approval_policy, list_desktop_forbidden_action_classes

        policy = get_desktop_approval_policy()
        audit = get_desktop_approval_audit_status()
        forbidden = list_desktop_forbidden_action_classes()
        return {
            "status": policy.status,
            "approval_levels": ", ".join(level.value for level in policy.approval_levels),
            "confirmation_phrase_policy": "phrase previews only; the confirmation phrase policy does not unlock real desktop execution",
            "forbidden_action_classes": "; ".join(item.action_class for item in forbidden[:4]),
            "audit_status": f"{audit.status}; records {audit.records_count}",
            "readiness_gaps": "no real observation, verified UI target, approval session storage, execution, verification, or rollback gate",
            "next_phase": "DesktopAgent Locked Readiness Proof",
            "summary": "Desktop human approvals are policy/status only; the approval model does not unlock real desktop execution.",
        }
    except Exception:
        warnings.append("Desktop human approval model status unavailable.")
        return unavailable_summary("Desktop Human Approval Model", "Desktop human approval model could not be summarized.")


def _desktop_readiness_proof_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..desktop_agent.phase14_final import get_desktop_phase14_proof

        proof = get_desktop_phase14_proof()
        return {
            "status": proof.status,
            "completed_safety_layers": "; ".join(layer.name for layer in proof.completed_layers),
            "readiness_gaps": "explicit observation gate; sensitive-screen protection; verified UI targeting; per-action permission; target-aware verification",
            "locked_observation_summary": "real screen/window/app observation is not enabled",
            "locked_control_summary": "real desktop control is not enabled",
            "approval_boundary": "approvals do not unlock execution",
            "next_phase": "Phase 15 LLM Router + Structured Reasoning Core",
            "intelligence_spine": "Phase 15 LLM Router + Structured Reasoning Core; Phase 16 Context Assembly Engine; Phase 17 LLM Threat Defense + Prompt Injection Guard; Phase 18 Agent Loop v1",
            "phase12_boundary": proof.phase12_boundary,
            "summary": proof.summary,
        }
    except Exception:
        warnings.append("DesktopAgent Phase 14 final proof unavailable.")
        return unavailable_summary("DesktopAgent Phase 14 Final Proof", "DesktopAgent Phase 14 final proof could not be summarized.")


def _project_reality_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..skills.project_inspection import inspect_project_status
        from ..skills.reality_check import build_reality_check

        project = inspect_project_status()
        reality = build_reality_check("are we actually done")
        return {
            "status": "Active",
            "current_phase": project.current_phase,
            "latest_verifier_status": project.verifier_status,
            "enabled_real_actions": "narrow create-new-text-file only after approval and exact confirmation",
            "blocked_actions": "broad edits, source edits, browser/desktop, MCP, terminal, cloud, external sends",
            "latest_workflow_state": project.risks_unknowns[-1] if project.risks_unknowns else "No workflow state available.",
            "recommended_next_safe_phase": project.next_recommended_step,
            "done_claim": reality.answer,
            "summary": "Read-only project/reality checker status. No verifier or executor was run.",
        }
    except Exception:
        warnings.append("Project/reality status unavailable.")
        return unavailable_summary("Project Reality", "Project/reality checker could not be summarized.")


def _capability_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..capabilities.registry import build_default_registry

        registry = build_default_registry()
        capabilities = registry.list_capabilities()
        enabled = [cap for cap in capabilities if cap.enabled_by_default]
        safe = [cap for cap in enabled if cap.risk_level in {"low", "medium"} and cap.read_only]
        sandbox = [cap for cap in capabilities if "sandbox" in cap.id]
        high = [cap for cap in capabilities if cap.risk_level == "high"]
        return {
            "status": "Active",
            "total": len(capabilities),
            "enabled": len(enabled),
            "safe_read_only": len(safe),
            "sandbox_related": len(sandbox),
            "high_risk_cataloged": len(high),
            "summary": "Capabilities are cataloged for discovery and safe routing.",
        }
    except Exception:
        warnings.append("Capability registry unavailable.")
        return unavailable_summary("Capabilities", "Capability registry could not be summarized.")


def _agent_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..agents.registry import list_agent_names

        names = list_agent_names()
        return {
            "status": "Active",
            "registered": len(names),
            "agents": names,
            "execution": "disabled by default",
            "summary": "Agents are available for status, planning, review, and preview-only routing.",
        }
    except Exception:
        warnings.append("Agent registry unavailable.")
        return unavailable_summary("Agents", "Agent registry could not be summarized.")


def _specialist_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..specialists.registry import list_specialists

        items = list_specialists()
        return {
            "status": "Active",
            "registered": len(items),
            "execution": "selection only",
            "summary": "Specialist roles route work to safe existing Eva surfaces; no task execution is enabled here.",
        }
    except Exception:
        warnings.append("Specialist registry unavailable.")
        return unavailable_summary("Specialists", "Specialist registry could not be summarized.")


def _skill_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..skills.registry import list_skills

        items = list_skills()
        return {
            "status": "Active",
            "registered": len(items),
            "execution": "metadata and route selection only",
            "summary": "Skills describe reusable safe workflows and preview-only command paths.",
        }
    except Exception:
        warnings.append("Skill registry unavailable.")
        return unavailable_summary("Skills", "Skill registry could not be summarized.")


def _workflow_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..skills.registry import list_workflows

        items = list_workflows()
        return {
            "status": "Active",
            "registered": len(items),
            "main_workflow": "fileagent_project_note_create",
            "real_scope": "Phase 12L create-new-text-file only",
            "summary": "Workflow plans show next steps; this layer does not execute file, browser, desktop, shell, MCP, or cloud actions.",
        }
    except Exception:
        warnings.append("Workflow registry unavailable.")
        return unavailable_summary("Workflows", "Workflow registry could not be summarized.")


def _latest_workflow_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..skills.workflow_state import summarize_fileagent_workflow_state

        state = summarize_fileagent_workflow_state()
        return {
            "status": "Active",
            "pending_approvals": state.pending_approval_count,
            "approved_records": state.approved_for_future_apply_count,
            "latest_sandbox": state.latest_sandbox_apply.status,
            "latest_real_create": state.latest_real_create.status,
            "rollback_availability": state.latest_rollback_available.status,
            "ambiguity": state.ambiguity_status,
            "safe_next_action": state.safe_next_action,
            "summary": "Latest workflow state is read-only and path-safe.",
        }
    except Exception:
        warnings.append("Latest workflow state unavailable.")
        return unavailable_summary("Latest Workflow State", "Workflow state could not be summarized.")


def _work_session_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..work_sessions.store import list_recent_work_sessions, list_session_events

        sessions = list_recent_work_sessions(limit=10)
        latest = sessions[0] if sessions else None
        events = list_session_events(latest.session_id, limit=20) if latest else []
        blocked = [event for event in events if event.event_type == "blocked_action"]
        return {
            "status": "Available",
            "latest_session": latest.session_id if latest else "none",
            "latest_request": latest.user_request if latest else "No work sessions recorded yet.",
            "latest_status": latest.status if latest else "none",
            "recent_sessions": len(sessions),
            "active_sessions": len([item for item in sessions if item.status == "active"]),
            "latest_events": len(events),
            "blocked_actions": len(blocked),
            "next_safe_step": latest.next_safe_step if latest and latest.next_safe_step else "Use `eva ask <request>` to create a tracked session.",
            "verification_status": latest.verification_status if latest and latest.verification_status else "not observed",
            "rollback_status": latest.rollback_status if latest and latest.rollback_status else "not observed",
            "summary": "Local WorkSession audit timeline is status-only and does not execute tasks.",
        }
    except Exception:
        warnings.append("WorkSession audit state unavailable.")
        return unavailable_summary("WorkSession audit", "WorkSession state could not be summarized.")


def _locked_feature_summary() -> dict[str, object]:
    return {
        "status": "Explained",
        "existing_file_editing": "locked",
        "source_code_editing": "locked",
        "browser_control": "locked",
        "desktop_control": "locked",
        "shell_execution": "locked",
        "mcp": "locked",
        "browser_agent": "safety model only; real browser control locked",
        "news_dashboard": "Phase 27 local/mock dashboard available",
        "coding_agent": "Phase 28 preview/report/status only; real source editing locked",
        "summary": "Locked features are explained in status only; Control Center does not execute them.",
    }


def _planner_summary(warnings: list[str]) -> dict[str, object]:
    try:
        from ..planner.status import planner_status

        status = planner_status()
        return {
            "status": "Active",
            "version": status.planner_version,
            "planning_only": status.planning_only,
            "execution_enabled": status.execution_enabled,
            "summary": "Planner v3 can decompose and review goals without executing risky actions.",
        }
    except Exception:
        warnings.append("Planner status unavailable.")
        return unavailable_summary("Planner", "Planner status could not be summarized.")


def _verifier_summary() -> dict[str, object]:
    return {
        "status": "Available",
        "master_verifier": "scripts/verify_eva_all.py",
        "last_known_status": "Run manually to refresh.",
        "manual_command": r".\.venv\Scripts\python.exe scripts\verify_eva_all.py",
        "summary": "Verifier runner exists; the dashboard does not execute it.",
    }


def _safety_summary() -> dict[str, object]:
    return {
        "mode": "read-only dashboard",
        "real_execution": "narrow create-new-text-file only",
        "real_file_writes": "only approved new .md/.txt files under docs/ or samples/",
        "broad_file_writes": "disabled",
        "browser_control": "disabled",
        "desktop_control": "disabled",
        "terminal_execution": "disabled",
        "mcp": "disabled",
        "cloud_calls": "disabled",
        "summary": "Control Center displays safe summaries only and does not execute actions.",
    }


def _future_modules() -> list[dict[str, object]]:
    return [
        {"name": "Browser control", "status": "locked/disabled", "notes": "Phase 24 allows public-URL read-only observation only; clicking, typing, forms, downloads, uploads, sessions, profiles, and control remain blocked."},
        {"name": "News Dashboard", "status": "preview/status available", "notes": "Phase 27 local/mock dashboard only."},
        {"name": "CodingAgent", "status": "preview/status available", "notes": "No source modification or patch application enabled."},
        {"name": "MCP", "status": "locked/disabled", "notes": "No connector or MCP execution enabled."},
        {"name": "Desktop control", "status": "locked/disabled", "notes": "Phase 25 allows explicit one-shot observation reports only; app/window control, continuous monitoring, and saved screenshots remain blocked."},
        {"name": "Voice", "status": "locked/disabled", "notes": "No control-center voice execution."},
        {"name": "Terminal", "status": "locked/disabled", "notes": "No shell execution enabled."},
    ]


def _first_sentence(text: str) -> str:
    for line in str(text or "").splitlines():
        clean = line.strip()
        if clean:
            return clean
    return "Available."
