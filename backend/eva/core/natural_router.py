from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class NaturalRouteResult:
    original_text: str
    intent: str
    confidence: float
    routed_to: str
    suggested_command: str | None
    authority_category: str
    needs_planner: bool
    needs_file_agent: bool
    needs_memory: bool
    needs_approval: bool
    sandbox_only: bool
    real_execution_requested: bool
    refusal_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def route_natural_request(text: str) -> NaturalRouteResult:
    original = str(text or "").strip()
    normalized = _normalize(original)
    if not normalized:
        return _route(original, "unknown", 0.0, None, "unknown", refusal="Give me a request after `eva ask`.")
    if _has_any(normalized, ("show release candidate status", "show rc status")):
        return _route(original, "rc_status", 0.997, "eva rc status", "read", planner=True)
    if _has_any(normalized, ("show dirty tree manifest",)):
        return _route(original, "rc_manifest", 0.997, "eva rc manifest", "read", planner=True)
    if _has_any(normalized, ("show commit plan", "what should i commit")):
        return _route(original, "rc_commit_plan", 0.997, "eva rc commit plan", "read", planner=True)
    if _has_any(normalized, ("show hardening report",)):
        return _route(original, "rc_hardening_report", 0.997, "eva rc hardening report", "read", planner=True)
    if _has_any(normalized, ("show rc checklist",)):
        return _route(original, "rc_checklist", 0.997, "eva rc checklist", "read", planner=True)
    if _has_any(normalized, ("is eva safe to commit", "is eva ready for release candidate")):
        return _route(original, "rc_readiness", 0.997, "eva rc readiness", "read", planner=True)
    if _has_any(normalized, ("show rc verification",)):
        return _route(original, "rc_verification", 0.997, "eva rc verification", "read", planner=True)
    if _has_any(normalized, ("show release status",)):
        return _route(original, "release_status", 0.995, "eva release status", "read", planner=True)
    if _has_any(normalized, ("show public demo",)):
        return _route(original, "release_demo", 0.995, "eva release demo", "read", planner=True)
    if _has_any(normalized, ("show demo smoke test", "how do i demo eva safely", "what should i run in the demo")):
        return _route(original, "release_demo_smoke", 0.997, "eva release smoke test", "read", planner=True)
    if _has_any(normalized, ("show post push sync status", "is eva synced with github", "show post-push sync status")):
        return _route(original, "release_post_push_sync", 0.997, "eva release post push sync", "read", planner=True)
    if _has_any(normalized, ("show eva roadmap status", "show roadmap status", "show phase roadmap", "show improvement roadmap")):
        return _route(original, "roadmap_status", 0.997, "eva roadmap status", "read", planner=True)
    if _has_any(normalized, ("show execution boundaries", "show execution boundary audit", "what can eva actually execute safely", "what can eva execute safely")):
        return _route(original, "execution_boundaries", 0.997, "eva execution boundaries", "read", planner=True)
    if _has_any(normalized, ("show catalog status", "show capability catalog status", "show command catalog status")):
        return _route(original, "catalog_status", 0.997, "eva catalog status", "read", planner=True)
    if _has_any(normalized, ("show frontend truth status", "show safe demo ui status")):
        return _route(original, "frontend_truth_status", 0.997, "eva frontend truth status", "read", planner=True)
    if _has_any(normalized, ("show grounded answer status", "show grounded routing status")):
        return _route(original, "grounded_answer_status", 0.997, "eva grounded answer status", "read", planner=True)
    if _has_any(normalized, ("show voice reliability status", "show voice diagnostics status")):
        return _route(original, "voice_reliability_status", 0.997, "eva voice reliability status", "read", planner=True)
    if _has_any(normalized, ("show verifier dashboard status", "show verifier metadata status")):
        return _route(original, "verifier_dashboard_status", 0.997, "eva verifier dashboard status", "read", planner=True)
    if _has_any(normalized, ("show demo commands",)):
        return _route(original, "release_commands", 0.995, "eva release commands", "read", planner=True)
    if _has_any(normalized, ("show capability map",)) or normalized == "what can eva do":
        return _route(original, "release_capability_map", 0.995, "eva release capability map", "read", planner=True)
    if _has_any(normalized, ("show safety proof",)):
        return _route(original, "release_safety_proof", 0.995, "eva release safety proof", "read", planner=True)
    if _has_any(normalized, ("show release readiness", "is eva ready for demo")):
        return _route(original, "release_readiness", 0.995, "eva release readiness", "read", planner=True)
    if _has_any(normalized, ("show known limitations", "what can eva not do")):
        return _route(original, "release_limitations", 0.995, "eva release limitations", "read", planner=True)
    if _has_any(normalized, ("what can eva do now", "show eva os dashboard")):
        return _route(original, "ai_os_dashboard", 0.98, "eva os dashboard", "read", planner=True)
    if _has_any(normalized, ("show ai os status",)):
        return _route(original, "ai_os_status", 0.98, "eva os status", "read", planner=True)
    if _has_any(normalized, ("show system map",)):
        return _route(original, "ai_os_system_map", 0.98, "eva os system map", "read", planner=True)
    if _has_any(normalized, ("show capability matrix",)):
        return _route(original, "ai_os_capability_matrix", 0.98, "eva os capability matrix", "read", planner=True)
    if _has_any(normalized, ("can eva really execute anything",)):
        return _route(original, "ai_os_safety_boundaries", 0.98, "eva os safety boundaries", "read", planner=True)
    if _has_any(normalized, ("show eva readiness",)):
        return _route(original, "ai_os_readiness", 0.98, "eva os readiness", "read", planner=True)
    if _has_any(normalized, ("show browser read-only status", "show browser readonly status")):
        return _route(original, "browser_read_status", 0.99, "eva browser read status", "read", planner=True)
    if _has_any(normalized, ("can eva click or type in the browser",)):
        return _route(original, "browser_read_boundaries", 0.99, "eva browser read policy", "read", planner=True)
    if _has_any(normalized, ("show browser read-only policy", "show browser readonly policy")):
        return _route(original, "browser_read_policy", 0.99, "eva browser read policy", "read", planner=True)
    if _has_any(normalized, ("show blocked browser urls",)):
        return _route(original, "browser_read_blocked_urls", 0.99, "eva browser read blocked urls", "read", planner=True)
    if _has_any(normalized, ("observe a webpage read only", "observe a web page read only")):
        return _route(original, "browser_read_observe", 0.99, "eva browser read observe", "read", planner=True)
    if _has_any(normalized, ("can eva use my logged-in browser", "can eva use my logged in browser")):
        return _route(original, "browser_read_session_boundary", 0.99, "eva browser read policy", "read", planner=True)
    if _has_any(normalized, ("show browser read-only readiness", "show browser readonly readiness")):
        return _route(original, "browser_read_readiness", 0.99, "eva browser read readiness", "read", planner=True)
    if _has_any(normalized, ("can eva read a webpage", "can eva read a web page")):
        return _route(original, "browser_read_policy", 0.99, "eva browser read policy", "read", planner=True)
    if _has_any(normalized, ("show coding specialist status",)):
        return _route(original, "coding_status", 0.995, "eva coding status", "read", planner=True)
    if _has_any(
        normalized,
        ("can eva edit code", "can eva apply patches", "can eva run tests", "can eva run git commands"),
    ):
        return _route(original, "coding_policy", 0.995, "eva coding policy", "read", planner=True)
    if _has_any(normalized, ("plan a code change", "show coding patch plan")):
        return _route(original, "coding_patch_plan", 0.995, "eva coding patch plan", "read", planner=True)
    if _has_any(normalized, ("review this coding task",)):
        return _route(original, "coding_review_checklist", 0.995, "eva coding review checklist", "read", planner=True)
    if _has_any(normalized, ("show coding test plan",)):
        return _route(original, "coding_test_plan", 0.995, "eva coding test plan", "read", planner=True)
    if _has_any(normalized, ("show coding risk review",)):
        return _route(original, "coding_risk_review", 0.995, "eva coding risk review", "read", planner=True)
    if _has_any(normalized, ("show coding handoff",)):
        return _route(original, "coding_handoff", 0.995, "eva coding handoff", "read", planner=True)
    if _has_any(normalized, ("show coding readiness",)):
        return _route(original, "coding_readiness", 0.995, "eva coding readiness", "read", planner=True)
    if _has_any(normalized, ("show news dashboard",)):
        return _route(original, "news_dashboard", 0.995, "eva news dashboard", "read", planner=True)
    if _has_any(normalized, ("show web intelligence status",)):
        return _route(original, "news_status", 0.995, "eva news status", "read", planner=True)
    if _has_any(normalized, ("what is eva's news policy", "what is evas news policy", "can eva monitor news", "can eva crawl the web")):
        return _route(original, "news_policy", 0.995, "eva news policy", "read", planner=True)
    if _has_any(normalized, ("show news source reliability",)):
        return _route(original, "news_sources", 0.995, "eva news sources", "read", planner=True)
    if _has_any(normalized, ("show news freshness",)):
        return _route(original, "news_freshness", 0.995, "eva news freshness", "read", planner=True)
    if _has_any(normalized, ("show news readiness",)):
        return _route(original, "news_readiness", 0.995, "eva news readiness", "read", planner=True)
    if _has_any(normalized, ("show desktop control status",)):
        return _route(original, "desktop_control_status", 0.995, "eva desktop control status", "read", planner=True)
    if _has_any(normalized, ("can eva control my desktop", "can eva click or type", "show desktop control policy")):
        return _route(original, "desktop_control_policy", 0.995, "eva desktop control policy", "read", planner=True)
    if _has_any(normalized, ("dry run desktop action",)):
        return _route(original, "desktop_control_dry_run", 0.995, "eva desktop control dry run", "read", planner=True)
    if _has_any(normalized, ("what desktop actions are blocked",)):
        return _route(original, "desktop_control_blocked_actions", 0.995, "eva desktop control blocked actions", "read", planner=True)
    if _has_any(normalized, ("what approval is required for desktop control",)):
        return _route(original, "desktop_control_approvals", 0.995, "eva desktop control approvals", "read", planner=True)
    if _has_any(normalized, ("show desktop control readiness",)):
        return _route(original, "desktop_control_readiness", 0.995, "eva desktop control readiness", "read", planner=True)
    if _has_any(normalized, ("show desktop observation status",)):
        return _route(original, "desktop_observe_status", 0.99, "eva desktop observe status", "read", planner=True)
    if _has_any(normalized, ("can eva click or type on my desktop", "can eva control apps or windows")):
        return _route(original, "desktop_observe_boundaries", 0.99, "eva desktop observe policy", "read", planner=True)
    if _has_any(normalized, ("show desktop observation policy",)):
        return _route(original, "desktop_observe_policy", 0.99, "eva desktop observe policy", "read", planner=True)
    if _has_any(normalized, ("show sensitive screen policy",)):
        return _route(original, "desktop_observe_sensitive_screens", 0.99, "eva desktop observe sensitive screens", "read", planner=True)
    if _has_any(normalized, ("observe desktop read only",)):
        return _route(original, "desktop_observe_mock", 0.99, "eva desktop observe mock", "read", planner=True)
    if _has_any(normalized, ("show desktop observation readiness",)):
        return _route(original, "desktop_observe_readiness", 0.99, "eva desktop observe readiness", "read", planner=True)
    if _has_any(normalized, ("can eva see my screen",)):
        return _route(original, "desktop_observe_policy", 0.99, "eva desktop observe policy", "read", planner=True)
    if _has_any(normalized, ("show voice assistant status",)):
        return _route(original, "voice_status", 0.97, "eva voice status", "read", planner=True)
    if _has_any(normalized, ("how will eva voice work",)):
        return _route(original, "voice_policy", 0.97, "eva voice policy", "read", planner=True)
    if _has_any(normalized, ("can eva listen to my microphone",)):
        return _route(original, "voice_listen_state", 0.97, "eva voice listen state", "read", planner=True)
    if _has_any(normalized, ("can eva speak using tts", "show voice provider policy")):
        return _route(original, "voice_providers", 0.97, "eva voice providers", "read", planner=True)
    if _has_any(normalized, ("show voice transcript safety",)):
        return _route(original, "voice_transcript_safety", 0.97, "eva voice transcript safety", "read", planner=True)
    if _has_any(normalized, ("can voice commands execute tools",)):
        return _route(original, "voice_confirmations", 0.97, "eva voice confirmations", "read", planner=True)
    if _has_any(normalized, ("show voice readiness",)):
        return _route(original, "voice_readiness", 0.97, "eva voice readiness", "read", planner=True)
    if _has_any(normalized, ("show memory v3 status",)):
        return _route(original, "memory_v3_status", 0.97, "eva memory v3 status", "read", planner=True, memory=True)
    if _has_any(normalized, ("how does eva decide what to remember", "can memory override safety policy")):
        return _route(original, "memory_v3_policy", 0.97, "eva memory v3 policy", "read", planner=True, memory=True)
    if _has_any(normalized, ("can eva store secrets in memory",)):
        return _route(original, "memory_v3_privacy", 0.97, "eva memory v3 privacy", "read", planner=True, memory=True)
    if _has_any(normalized, ("show memory freshness",)):
        return _route(original, "memory_v3_freshness", 0.97, "eva memory v3 freshness", "read", planner=True, memory=True)
    if _has_any(normalized, ("show memory conflicts",)):
        return _route(original, "memory_v3_conflicts", 0.97, "eva memory v3 conflicts", "read", planner=True, memory=True)
    if _has_any(normalized, ("what memory will eva use for context",)):
        return _route(original, "memory_v3_retrieval_preview", 0.97, "eva memory v3 retrieval preview", "read", planner=True, memory=True)
    if _has_any(normalized, ("show memory v3 readiness",)):
        return _route(original, "memory_v3_readiness", 0.97, "eva memory v3 readiness", "read", planner=True, memory=True)
    if _has_any(normalized, ("show execution gates status",)):
        return _route(original, "execution_gates_status", 0.97, "eva execution gates status", "read", planner=True)
    if _has_any(normalized, ("what can eva execute", "show structured execution gate policy", "show execution gate policy")):
        return _route(original, "execution_gates_policy", 0.97, "eva execution gates policy", "read", planner=True)
    if _has_any(normalized, ("can eva execute tools", "can eva control browser or desktop", "can eva read secrets")):
        return _route(original, "execution_gates_blocked_actions", 0.97, "eva execution gates blocked actions", "read", planner=True)
    if _has_any(normalized, ("what requires approval",)):
        return _route(original, "execution_gates_approvals", 0.97, "eva execution gates approvals", "read", planner=True)
    if _has_any(normalized, ("what confirmation phrase is needed",)):
        return _route(original, "execution_gates_confirmations", 0.97, "eva execution gates confirmations", "read", planner=True)
    if _has_any(normalized, ("show execution gate readiness", "show execution gates readiness")):
        return _route(original, "execution_gates_readiness", 0.97, "eva execution gates readiness", "read", planner=True)
    if _has_any(normalized, ("show context assembly status",)):
        return _route(original, "context_status", 0.96, "eva context status", "read", planner=True)
    if _has_any(normalized, ("how does eva choose context",)):
        return _route(original, "context_policy", 0.96, "eva context policy", "read", planner=True)
    if _has_any(normalized, ("what context will eva send to the llm",)):
        return _route(original, "context_assemble_preview", 0.96, "eva context assemble preview", "read", planner=True)
    if _has_any(normalized, ("can eva include secrets in context", "show context redaction policy")):
        return _route(original, "context_redaction_policy", 0.96, "eva context redaction policy", "read", planner=True)
    if _has_any(normalized, ("show context budget",)):
        return _route(original, "context_budget", 0.96, "eva context budget", "read", planner=True)
    if _has_any(normalized, ("show context grounding report",)):
        return _route(original, "context_grounding_report", 0.96, "eva context grounding report", "read", planner=True)
    if _has_any(normalized, ("show context readiness",)):
        return _route(original, "context_readiness", 0.96, "eva context readiness", "read", planner=True)
    if _has_any(normalized, ("show threat defense status",)):
        return _route(original, "threat_status", 0.96, "eva threat status", "read", planner=True)
    if _has_any(normalized, ("how does eva stop prompt injection",)):
        return _route(original, "threat_policy", 0.96, "eva threat policy", "read", planner=True)
    if _has_any(normalized, ("scan this for prompt injection",)):
        return _route(original, "threat_scan_preview", 0.96, "eva threat scan preview", "read", planner=True)
    if _has_any(normalized, ("what if context says ignore safety policy", "can untrusted context override instructions", "show context poisoning guard")):
        return _route(original, "threat_context_guard", 0.96, "eva threat context guard", "read", planner=True)
    if _has_any(normalized, ("can eva leak secrets through context",)):
        return _route(original, "threat_exfiltration_examples", 0.96, "eva threat exfiltration examples", "read", planner=True)
    if _has_any(normalized, ("show threat defense readiness",)):
        return _route(original, "threat_readiness", 0.96, "eva threat readiness", "read", planner=True)
    if _has_any(normalized, ("show agent loop status",)):
        return _route(original, "agent_loop_status", 0.96, "eva agent loop status", "read", planner=True)
    if _has_any(normalized, ("run agent loop preview",)):
        return _route(original, "agent_loop_run_preview", 0.96, "eva agent loop run preview", "read", planner=True)
    if _has_any(normalized, ("how does eva's agent loop work", "how does evas agent loop work")):
        return _route(original, "agent_loop_policy", 0.96, "eva agent loop policy", "read", planner=True)
    if _has_any(normalized, ("can the agent loop execute tools", "show agent loop safety report")):
        return _route(original, "agent_loop_safety_report", 0.96, "eva agent loop safety report", "read", planner=True)
    if _has_any(normalized, ("what happens if the agent loop gets stuck",)):
        return _route(original, "agent_loop_stop_reasons", 0.96, "eva agent loop stop reasons", "read", planner=True)
    if _has_any(normalized, ("show agent loop action previews",)):
        return _route(original, "agent_loop_action_previews", 0.96, "eva agent loop action previews", "read", planner=True)
    if _has_any(normalized, ("show agent loop readiness",)):
        return _route(original, "agent_loop_readiness", 0.96, "eva agent loop readiness", "read", planner=True)
    if _has_any(normalized, ("show workflow planner status",)):
        return _route(original, "workflow_planner_status", 0.96, "eva workflow planner status", "read", planner=True)
    if _has_any(normalized, ("plan a workflow preview",)):
        return _route(original, "workflow_planner_preview", 0.96, "eva workflow planner preview", "read", planner=True)
    if _has_any(normalized, ("how does eva choose workflows", "can workflow planner execute tools")):
        return _route(original, "workflow_planner_policy", 0.96, "eva workflow planner policy", "read", planner=True)
    if _has_any(normalized, ("show workflow dependencies",)):
        return _route(original, "workflow_planner_dependencies", 0.96, "eva workflow planner dependencies", "read", planner=True)
    if _has_any(normalized, ("show workflow approval preview",)):
        return _route(original, "workflow_planner_approvals", 0.96, "eva workflow planner approvals", "read", planner=True)
    if _has_any(normalized, ("show workflow rollback plan",)):
        return _route(original, "workflow_planner_rollback", 0.96, "eva workflow planner rollback", "read", planner=True)
    if _has_any(normalized, ("show workflow planner readiness",)):
        return _route(original, "workflow_planner_readiness", 0.96, "eva workflow planner readiness", "read", planner=True)
    if _has_any(normalized, ("what llms can eva use", "show llm providers")):
        return _route(original, "llm_providers", 0.96, "eva llm providers", "read", planner=True)
    if _has_any(normalized, ("is llm routing enabled", "show llm router status", "can eva call the llm now")):
        return _route(original, "llm_status", 0.96, "eva llm status", "read", planner=True)
    if _has_any(normalized, ("what happens if the llm fails", "llm fallback policy")):
        return _route(original, "llm_fallback_policy", 0.96, "eva llm fallback policy", "read", planner=True)
    if _has_any(normalized, ("how does eva choose a model", "llm routing policy")):
        return _route(original, "llm_routing_policy", 0.96, "eva llm routing policy", "read", planner=True)
    if _has_any(normalized, ("what are eva's token limits", "what are evas token limits", "llm limits")):
        return _route(original, "llm_limits", 0.96, "eva llm limits", "read", planner=True)
    if _has_any(normalized, ("run llm red team tests",)):
        return _route(original, "llm_red_team_run", 0.96, "eva llm red team run", "read", planner=True)
    if _has_any(normalized, ("show llm failure tests",)):
        return _route(original, "llm_failure_tests", 0.96, "eva llm failure tests", "read", planner=True)
    if _has_any(normalized, ("can unsafe llm output execute tools",)):
        return _route(original, "llm_red_team_status", 0.96, "eva llm red team status", "read", planner=True)
    if _has_any(normalized, ("what if the llm leaks secrets", "what if the llm ignores safety policy", "show llm safety failure report")):
        return _route(original, "llm_safety_failure_report", 0.96, "eva llm safety failure report", "read", planner=True)
    if _has_any(normalized, ("show llm red team readiness",)):
        return _route(original, "llm_red_team_readiness", 0.96, "eva llm red team readiness", "read", planner=True)
    if _has_any(normalized, ("show llm validation readiness", "llm validation readiness")):
        return _route(original, "llm_validation_readiness", 0.96, "eva llm validation readiness", "read", planner=True)
    if _has_any(normalized, ("what happens if the llm returns bad json", "what happens if the llm asks to execute a tool", "how does eva handle hallucinated capabilities")):
        return _route(original, "llm_validation_invalid_examples", 0.96, "eva llm validate invalid examples", "read", planner=True)
    if _has_any(normalized, ("how does eva validate llm output", "show structured output validation policy")):
        return _route(original, "llm_validation_policy", 0.96, "eva llm validation policy", "read", planner=True)
    if _has_any(normalized, ("can invalid llm output execute actions",)):
        return _route(original, "llm_validation_status", 0.96, "eva llm validation status", "read", planner=True)
    if _has_any(normalized, ("show structured output rules", "llm structured output")):
        return _route(original, "llm_structured_output", 0.96, "eva llm structured output", "read", planner=True)
    if _has_any(normalized, ("what happens if gemini fails", "what happens if all llms fail", "show llm fallback chain", "simulate an llm timeout")):
        return _route(original, "llm_fallback_simulate", 0.96, "eva llm fallback simulate timeout", "read", planner=True)
    if _has_any(normalized, ("show llm degraded mode",)):
        return _route(original, "llm_degraded_mode", 0.96, "eva llm degraded mode", "read", planner=True)
    if _has_any(normalized, ("llm session limits",)):
        return _route(original, "llm_session_limits", 0.96, "eva llm session limits", "read", planner=True)
    if _has_any(normalized, ("how does eva prevent runaway loops", "llm runaway protection")):
        return _route(original, "llm_runaway_protection", 0.96, "eva llm runaway protection", "read", planner=True)
    if _has_any(normalized, ("show llm routing audit",)):
        return _route(original, "llm_routing_audit_preview", 0.96, "eva llm routing audit preview", "read", planner=True)

    approval_id = _approval_id(original)
    if _has_any(normalized, ("show golden workflow proof", "golden workflow proof", "did the golden workflow pass", "did golden workflow pass")):
        return _route(original, "golden_workflow_proof", 0.96, "eva workflow golden proof", "read", planner=True, file=True)
    if _has_any(normalized, ("golden workflow test plan", "show golden workflow test plan")):
        return _route(original, "golden_workflow_test_plan", 0.96, "eva workflow golden test plan", "read", planner=True, file=True)
    if _has_any(normalized, ("show golden workflow status", "golden workflow status", "golden workflows")):
        return _route(original, "golden_workflow_status", 0.96, "eva golden workflow status", "read", planner=True, file=True)
    if _has_any(normalized, ("is phase 12 ready", "phase 12 ready", "phase twelve ready", "ready for phase 12 checkpoint")):
        return _route(original, "phase12_ready", 0.96, "eva phase 12 ready", "read", planner=True)
    if _has_any(normalized, ("summarize phase 12", "phase 12 summary", "phase twelve summary")):
        return _route(original, "phase12_summary", 0.95, "eva phase 12 summary", "read", planner=True)
    if _has_any(normalized, ("what are phase 12 limits", "phase 12 limits", "phase twelve limits")):
        return _route(original, "phase12_limits", 0.95, "eva phase 12 limits", "read", planner=True)
    if _has_any(normalized, ("show phase 12 proof", "phase 12 proof", "phase twelve proof")):
        return _route(original, "phase12_proof", 0.95, "eva phase 12 proof", "read", planner=True)
    if _has_any(normalized, ("is desktop phase 14 complete", "desktop phase 14 ready", "is desktop phase 14 ready")):
        return _route(original, "desktop_phase14_ready", 0.97, "eva desktop phase 14 ready", "read", planner=True)
    if _has_any(normalized, ("summarize desktop phase 14", "desktop phase 14 summary")):
        return _route(original, "desktop_phase14_summary", 0.96, "eva desktop phase 14 summary", "read", planner=True)
    if _has_any(normalized, ("what are desktop phase 14 limits", "desktop phase 14 limits")):
        return _route(original, "desktop_phase14_limits", 0.96, "eva desktop phase 14 limits", "read", planner=True)
    if _has_any(normalized, ("prove desktop control is still locked", "desktop phase 14 final proof", "show desktop phase 14 final proof")):
        return _route(original, "desktop_phase14_final_proof", 0.97, "eva desktop phase 14 final proof", "read", planner=True)
    if _has_any(normalized, ("desktop readiness proof",)):
        return _route(original, "desktop_readiness_proof", 0.96, "eva desktop readiness proof", "read", planner=True)
    if _has_any(normalized, ("what is missing before desktop observation", "what is missing before desktop control", "desktop readiness gaps")):
        return _route(original, "desktop_readiness_gaps", 0.96, "eva desktop readiness gaps", "read", planner=True)
    if _has_any(normalized, ("can eva control my desktop now", "can you control my desktop now", "desktop locked status")):
        return _route(original, "desktop_locked_status", 0.97, "eva desktop locked status", "read", planner=True)
    if _has_any(normalized, ("can eva take screenshots", "can you take screenshots")):
        return _route(original, "desktop_screen_capture_gate", 0.96, "eva desktop screen capture gate", "read", planner=True)
    if _has_any(normalized, ("what screens are sensitive", "sensitive screens")):
        return _route(original, "desktop_sensitive_screens", 0.96, "eva desktop sensitive screens", "read", planner=True)
    if _has_any(normalized, ("what would eva redact from screen", "screen redaction", "redact from screen")):
        return _route(original, "desktop_screen_redaction_policy", 0.96, "eva desktop screen redaction policy", "read", planner=True)
    if _has_any(normalized, ("show screen observation policy", "screen observation policy")):
        return _route(original, "desktop_screen_observation_policy", 0.96, "eva desktop screen observation policy", "read", planner=True)
    if _has_any(normalized, ("is screen observation ready", "screen readiness")):
        return _route(original, "desktop_screen_readiness", 0.96, "eva desktop screen readiness", "read", planner=True)
    if _has_any(normalized, ("can eva see my screen", "can you see my screen", "can eva read my screen", "can you read my screen")):
        return _route(original, "desktop_screen_policy", 0.96, "eva desktop screen policy", "read", planner=True)
    if _has_any(normalized, ("can eva control my desktop", "can you control my desktop", "is desktop control enabled")):
        return _route(original, "desktop_status", 0.96, "eva desktop status", "read", planner=True)
    if _has_any(normalized, ("show desktop session status", "desktop session status")):
        return _route(original, "desktop_session_status", 0.96, "eva desktop session status", "read", planner=True)
    if _has_any(normalized, ("start a desktop session", "create desktop session", "desktop session preview")):
        return _route(original, "desktop_session_preview", 0.96, "eva desktop session preview", "read", planner=True)
    if _has_any(normalized, ("what would desktop observation include", "desktop session plan", "future desktop session lifecycle")):
        return _route(original, "desktop_session_plan", 0.95, "eva desktop session plan", "read", planner=True)
    if _has_any(normalized, ("can eva see open windows", "can you see open windows", "desktop window status", "open window preview")):
        return _route(original, "desktop_window_status_preview", 0.95, "eva desktop window status preview", "read", planner=True)
    if _has_any(normalized, ("can eva detect the active app", "can you detect the active app", "active context preview", "active app preview")):
        return _route(original, "desktop_active_context_preview", 0.95, "eva desktop active context preview", "read", planner=True)
    if _has_any(normalized, ("can eva inspect my screen", "can you inspect my screen", "is desktop observation ready", "desktop observation readiness")):
        return _route(original, "desktop_observation_readiness", 0.95, "eva desktop observation readiness", "read", planner=True)
    if _has_any(normalized, ("what desktop actions need approval", "desktop action approvals")):
        return _route(original, "desktop_action_approvals", 0.96, "eva desktop action approvals", "read", planner=True)
    if _has_any(normalized, ("show desktop action dry run policy", "desktop dry run policy")):
        return _route(original, "desktop_dry_run_policy", 0.96, "eva desktop dry run policy", "read", planner=True)
    if _has_any(normalized, ("dry run clicking a button", "dry run desktop action", "desktop action dry run")):
        return _route(original, "desktop_action_dry_run", 0.96, "eva desktop action dry run " + original, "read", planner=True)
    if _has_any(normalized, ("what would eva do to open an app", "plan desktop actions", "desktop action plan")):
        return _route(original, "desktop_action_plan_preview", 0.96, "eva desktop action plan " + original, "read", planner=True)
    if "browser" not in normalized and "website" not in normalized and "webpage" not in normalized and "site" not in normalized and _has_any(normalized, ("can eva click this", "can eva type into an app", "can eva press hotkeys", "desktop action risk")):
        return _route(original, "desktop_action_risk", 0.96, "eva desktop action risk " + _desktop_action_hint(normalized), "read", planner=True)
    if _has_any(normalized, ("how risky is clicking this", "how risky is typing my password", "score the risk of opening terminal", "score the risk of uploading a file", "desktop risk score")):
        return _route(original, "desktop_risk_score", 0.96, "eva desktop risk score " + original, "read", planner=True)
    if _has_any(normalized, ("desktop risk factors", "what risk factors")):
        return _route(original, "desktop_risk_factors", 0.95, "eva desktop risk factors " + original, "read", planner=True)
    if _has_any(normalized, ("can i approve eva to control my desktop", "show desktop approval policy", "desktop approval policy")):
        return _route(original, "desktop_approval_policy", 0.97, "eva desktop approval policy", "read", planner=True)
    if _has_any(normalized, ("desktop approval levels", "show desktop approval levels")):
        return _route(original, "desktop_approval_levels", 0.96, "eva desktop approval levels", "read", planner=True)
    if "what approval is needed to send a message" not in normalized and _has_any(normalized, ("what approval is needed to click", "what approval is needed to type", "approval needed to click", "approval needed to type")):
        return _route(original, "desktop_approval_preview", 0.97, "eva desktop approval preview " + original, "read", planner=True)
    if _has_any(normalized, ("what desktop actions are forbidden", "desktop forbidden actions")):
        return _route(original, "desktop_forbidden_actions", 0.97, "eva desktop forbidden actions", "read", planner=True)
    if _has_any(normalized, ("what confirmation phrase would be required", "desktop confirmation phrase", "confirmation phrase would be required")):
        return _route(original, "desktop_confirmation_phrase", 0.97, "eva desktop confirmation phrase " + original, "read", planner=True)
    if _has_any(normalized, ("is desktop approval ready", "desktop approval readiness")):
        return _route(original, "desktop_approval_readiness", 0.96, "eva desktop approval readiness", "read", planner=True)
    if _has_any(normalized, ("what approval is needed to send a message", "desktop approval required", "approval required")):
        return _route(original, "desktop_approval_required", 0.96, "eva desktop approval required " + original, "read", planner=True)
    if _has_any(normalized, ("what desktop actions are high risk", "desktop high risk actions")):
        return _route(original, "desktop_high_risk_actions", 0.96, "eva desktop high risk actions", "read", planner=True)
    if _has_any(normalized, ("show desktop safety matrix", "desktop safety matrix")):
        return _route(original, "desktop_safety_matrix", 0.96, "eva desktop safety matrix", "read", planner=True)
    if _has_any(normalized, ("desktop risk readiness", "is desktop risk ready")):
        return _route(original, "desktop_risk_readiness", 0.95, "eva desktop risk readiness", "read", planner=True)
    if _has_any(normalized, ("show desktop policy", "desktop policy", "what desktop actions are allowed")):
        return _route(original, "desktop_policy", 0.95, "eva desktop policy", "read", planner=True)
    if _has_any(normalized, ("desktop blocked actions", "what desktop actions are blocked")):
        return _route(original, "desktop_blocked_actions", 0.95, "eva desktop blocked actions", "read", planner=True)
    if _has_any(normalized, ("can eva click and type", "can you click and type", "can eva open apps", "can eva use terminal", "can you use terminal", "desktop action safety")):
        return _route(original, "desktop_action_safety", 0.95, "eva desktop action safety " + _desktop_action_hint(normalized), "read", planner=True)
    if _has_any(normalized, ("desktop app risk", "app risk")):
        return _route(original, "desktop_app_risk", 0.94, "eva desktop app risk " + _desktop_app_hint(normalized), "read", planner=True)
    if _has_any(normalized, ("desktop readiness", "is desktop ready")):
        return _route(original, "desktop_readiness", 0.94, "eva desktop readiness", "read", planner=True)
    if _has_any(normalized, ("can eva use the browser", "can you use the browser", "is browser control enabled")):
        return _route(original, "browser_status", 0.95, "eva browser status", "read", planner=True)
    if _has_any(normalized, ("show browser session status", "browser session status", "can eva browse websites", "can you browse websites")):
        return _route(original, "browser_session_status", 0.95, "eva browser session status", "read", planner=True)
    if _has_any(normalized, ("start a browser session", "open a browser", "start browser session", "create browser session")):
        return _route(original, "browser_session_preview", 0.95, "eva browser session preview", "read", planner=True)
    if _has_any(normalized, ("what would a browser session do", "browser session plan", "future browser session lifecycle")):
        return _route(original, "browser_session_plan", 0.95, "eva browser session plan", "read", planner=True)
    if _has_any(normalized, ("is browser phase 13 complete", "browser phase 13 ready", "is browser phase 13 ready")):
        return _route(original, "browser_phase13_ready", 0.97, "eva browser phase 13 ready", "read", planner=True)
    if _has_any(normalized, ("summarize browser phase 13", "browser phase 13 summary")):
        return _route(original, "browser_phase13_summary", 0.97, "eva browser phase 13 summary", "read", planner=True)
    if _has_any(normalized, ("what are browser phase 13 limits", "browser phase 13 limits")):
        return _route(original, "browser_phase13_limits", 0.97, "eva browser phase 13 limits", "read", planner=True)
    if _has_any(normalized, ("browser phase 13 final proof", "show browser phase 13 final proof")):
        return _route(original, "browser_phase13_final_proof", 0.97, "eva browser phase 13 final proof", "read", planner=True)
    if _has_any(normalized, ("is browser read-only mode ready", "browser read only mode ready", "browser readonly mode ready")):
        return _route(original, "browser_readonly_readiness", 0.96, "eva browser read only readiness", "read", planner=True)
    if _has_any(normalized, ("prove browser control is still locked", "show browser safety proof", "browser safety proof")):
        return _route(original, "browser_safety_proof", 0.96, "eva browser safety proof", "read", planner=True)
    if _has_any(normalized, ("what is missing before browser read-only", "missing before browser read only", "browser readiness gaps")):
        return _route(original, "browser_readiness_gaps", 0.96, "eva browser readiness gaps", "read", planner=True)
    if _has_any(normalized, ("is phase 13 browser safe", "phase 13 browser safe", "browser phase 13 proof")):
        return _route(original, "browser_phase13_proof", 0.96, "eva browser phase 13 proof", "read", planner=True)
    if _has_any(normalized, ("can eva browse now", "can you browse now", "is browser browsing enabled")):
        return _route(original, "browser_locked_status", 0.96, "eva browser locked status", "read", planner=True)
    if _has_any(normalized, ("browser readiness proof", "show browser readiness proof")):
        return _route(original, "browser_readiness_proof", 0.96, "eva browser readiness proof", "read", planner=True)
    if _has_any(normalized, ("can eva read a webpage", "can eva summarize a page", "can you summarize a page", "can eva read a web page")):
        return _route(original, "browser_page_summary_policy", 0.95, "eva browser page summary policy", "read", planner=True)
    if "domain" not in normalized and _has_any(normalized, ("can eva inspect dom", "can you inspect dom", "browser dom", "inspect dom")):
        return _route(original, "browser_dom_summary_policy", 0.95, "eva browser dom summary policy", "read", planner=True)
    if _has_any(normalized, ("can eva take screenshots", "can you take screenshots", "browser screenshots")):
        return _route(original, "browser_observation_readiness", 0.95, "eva browser observation readiness", "read", planner=True)
    if _has_any(normalized, ("show browser observation policy", "browser observation policy", "observation policy")):
        return _route(original, "browser_observation_readiness", 0.95, "eva browser observation readiness", "read", planner=True)
    if _has_any(normalized, ("what would eva extract from a webpage", "what would eva extract from a web page", "browser extraction preview")):
        return _route(original, "browser_page_summary_preview", 0.95, "eva browser page summary preview", "read", planner=True)
    if _has_any(normalized, ("what browser actions need approval", "browser action approvals")):
        return _route(original, "browser_action_approvals", 0.95, "eva browser action approvals", "read", planner=True)
    if _has_any(normalized, ("show browser action dry run policy", "browser dry run policy")):
        return _route(original, "browser_dry_run_policy", 0.95, "eva browser dry run policy", "read", planner=True)
    if _has_any(normalized, ("is example.com safe for eva", "is this site safe for eva", "domain check")):
        return _route(original, "browser_domain_check", 0.95, "eva browser domain check " + _domain_hint(normalized), "read", planner=True)
    if _has_any(normalized, ("can eva open a banking website", "can eva use gmail", "can eva upload files to a site", "site risk")):
        return _route(original, "browser_site_risk", 0.95, "eva browser site risk " + _domain_hint(normalized), "read", planner=True)
    if _has_any(normalized, ("show browser domain policy", "browser domain policy", "browser domain rules")):
        return _route(original, "browser_domain_rules", 0.95, "eva browser domain rules", "read", planner=True)
    if _has_any(normalized, ("what approvals are needed for sensitive sites", "browser domain approvals", "sensitive site approvals")):
        return _route(original, "browser_domain_approvals", 0.95, "eva browser domain approvals", "read", planner=True)
    if _has_any(normalized, ("what sites are risky", "sensitive sites")):
        return _route(original, "browser_sensitive_sites", 0.95, "eva browser sensitive sites", "read", planner=True)
    if _has_any(normalized, ("dry run opening a website", "dry run browser", "browser action dry run")):
        return _route(original, "browser_action_dry_run", 0.95, "eva browser action dry run " + original, "read", planner=True)
    if _has_any(normalized, ("what would eva do to search google", "plan browser actions", "browser action plan")):
        return _route(original, "browser_action_plan_preview", 0.95, "eva browser action plan " + original, "read", planner=True)
    if _has_any(normalized, ("can eva click this", "can eva type into a website", "can eva submit", "browser action risk")):
        return _route(original, "browser_action_risk", 0.95, "eva browser action risk " + _browser_action_hint(normalized), "read", planner=True)
    if _has_any(normalized, ("what browser actions are allowed", "show browser policy", "browser policy")):
        return _route(original, "browser_policy", 0.95, "eva browser policy", "read", planner=True)
    if _has_any(normalized, ("can eva click", "can eva type", "can eva login", "can eva upload", "can eva download", "can you click", "can you type", "can you login", "can you upload", "click login", "login or upload")):
        return _route(original, "browser_action_safety", 0.95, "eva browser action safety " + _browser_action_hint(normalized), "read", planner=True)
    if _has_any(normalized, ("run quick check", "quick check", "smoke test", "verify eva", "how do i verify eva", "show phase 12 status", "phase 12 status", "is eva safe", "what works right now", "what is locked")):
        if _has_any(normalized, ("quick check", "smoke test", "verify eva", "how do i verify eva")):
            return _route(original, "phase12_verify_status", 0.92, "eva smoke status", "read", planner=True)
        return _route(original, "phase12_status", 0.9, "eva phase 12 status", "read", planner=True)
    if _has_any(normalized, ("what real actions can eva do now", "what real actions can you do now", "real actions available", "real apply policy")):
        return _route(original, "real_apply_policy", 0.94, "eva file real apply policy", "read", file=True)
    if _has_any(normalized, ("what features are locked", "locked features", "what is locked")):
        return _route(original, "locked_features", 0.94, "eva locked features", "read", planner=True)
    if _has_any(normalized, ("what features are enabled", "enabled features", "what is enabled")):
        return _route(original, "enabled_features", 0.94, "eva enabled features", "read", planner=True)
    if _has_any(normalized, ("what is the next safe step", "next safe step")):
        return _route(original, "next_safe_step", 0.94, "eva next safe step", "read", planner=True)
    if _has_any(normalized, ("work session status", "sessions status", "show sessions", "show work sessions")):
        return _route(original, "work_sessions_status", 0.94, "eva sessions status", "read", planner=True)
    if _has_any(normalized, ("audit timeline", "show audit", "work session timeline")):
        return _route(original, "audit_timeline", 0.94, "eva audit timeline", "read", planner=True)
    if _has_any(normalized, ("what happened last", "what did eva do last", "latest session", "last work session")):
        return _route(original, "latest_work_session", 0.94, "eva session latest", "read", planner=True)
    if _has_any(normalized, ("what should we do next", "what should eva do next", "next safe phase")):
        return _route(original, "project_next_step", 0.94, "eva project next step", "read", planner=True, file=True)
    if _has_any(normalized, ("what changed recently", "recent changes", "what changed in eva", "latest changes")):
        return _route(original, "project_recent_changes", 0.93, "eva project recent changes", "read", planner=True, file=True)
    if _has_any(normalized, ("what is broken", "what seems broken", "what is failing", "what failed")):
        return _route(original, "project_broken_status", 0.93, "eva project reality check", "read", planner=True)
    if _has_any(normalized, ("what proof do we have", "show proof", "completion proof", "what evidence do we have")):
        return _route(original, "project_proof", 0.94, "eva project proof", "read", planner=True)
    if _has_any(normalized, ("are we actually done", "are we done", "done check")):
        return _route(original, "done_check", 0.94, "eva done check", "read", planner=True)
    if _has_any(normalized, ("summarize current eva status", "current eva status", "summarize eva status")):
        return _route(original, "project_inspect", 0.92, "eva project inspect", "read", planner=True, file=True)
    if _has_any(normalized, ("what should i do next", "next step", "what next")):
        return _route(original, "workflow_next_step", 0.9, "eva workflow next", "read", planner=True, file=True)
    if _has_any(normalized, ("verify this phase",)):
        return _route(original, "verification_before_completion", 0.9, "eva phase 12 status", "read", planner=True)
    if _has_any(normalized, ("continue golden workflow", "continue workflow", "continue the project note workflow", "continue project note workflow")):
        return _route(original, "workflow_continue", 0.9, "eva workflow next", "read", file=True, approval=True)
    if _is_project_note_request(normalized):
        return _route(original, "golden_project_note_create", 0.94, "eva golden workflow start project note " + original, "golden_workflow", file=True, approval=True, sandbox=True)
    if normalized.startswith("confirm rollback real create ") and approval_id:
        return _route(original, "real_create_rollback_confirm", 0.98, f"eva file approval real rollback {approval_id} confirm rollback real create {approval_id}", "rollback_real_create", file=True, approval=True, real=True)
    if normalized.startswith("confirm real create ") and approval_id:
        return _route(original, "real_create_confirm", 0.98, f"eva file approval real create {approval_id} confirm real create {approval_id}", "real_create_safe_text", file=True, approval=True, real=True)
    if _has_any(normalized, ("verify the real file apply", "verify real file apply", "verify real created file", "verify real create", "real create verify")):
        cmd = f"eva file approval real verify {approval_id}" if approval_id else None
        return _route(original, "real_create_verify", 0.9, cmd, "verify", file=True, approval=True)
    if _has_any(normalized, ("verify the latest real create", "verify latest real create", "verify latest real file")):
        return _route(original, "real_create_verify_latest", 0.9, "eva file latest real create", "read", file=True, approval=True)
    if _has_any(normalized, ("rollback the real file apply", "rollback real file apply", "rollback real created file", "rollback real create")):
        cmd = f"eva file approval real rollback {approval_id} confirm rollback real create {approval_id}" if approval_id else None
        return _route(original, "real_create_rollback_request", 0.9, cmd, "rollback_real_create", file=True, approval=True, real=True)
    if _has_any(normalized, ("rollback the golden workflow real create", "rollback golden workflow real create", "rollback the golden workflow")):
        return _route(original, "real_create_rollback_latest", 0.9, "eva file latest rollback", "read", file=True, approval=True)
    if _has_any(normalized, ("rollback the latest real create", "rollback latest real create", "rollback latest real file")):
        return _route(original, "real_create_rollback_latest", 0.9, "eva file latest rollback", "read", file=True, approval=True)
    if _has_any(normalized, ("create the approved text file", "create the approved docs file", "really create the approved docs file", "apply the approved docs file for real", "apply the approved docs note for real", "create the approved file", "real apply this approved new file", "real apply the approved file", "make the approved markdown file", "real apply approved text file")):
        cmd = f"eva file real apply eligibility {approval_id}" if approval_id else None
        return _route(original, "real_create_request", 0.92, cmd, "real_create_safe_text", file=True, approval=True, real=True)
    if _has_any(normalized, ("apply all my changes for real", "apply my changes for real", "real apply everything", "really apply all changes", "broad real apply")):
        return _route(original, "blocked_broad_real_apply", 0.95, None, "local_write", file=True, real=True, refusal="Broad real apply is blocked. Phase 12L only allows create-new-text-file under docs/ or samples/ after approval and exact confirmation.")

    if _has_any(
        normalized,
        (
            "show control center",
            "control center",
            "eva dashboard",
            "show dashboard status",
            "dashboard status",
            "eva status",
            "show eva status",
            "what is eva doing",
            "system state",
            "show system state",
        ),
    ):
        return _route(original, "control_center_status", 0.94, "eva control center summary", "read", planner=True)
    if _has_any(normalized, ("show dashboard", "open dashboard", "open control center")):
        return _route(original, "control_center_dashboard", 0.9, "eva dashboard url", "read", planner=True)

    if _has_any(normalized, ("delete", "remove my files", "wipe", "format")):
        return _route(original, "blocked_destructive", 0.95, None, "destructive", real=True, refusal="Destructive file/system actions are blocked. Phase 12L only allows create-new-text-file under docs/ or samples/ after approval and exact confirmation.")
    if _has_any(normalized, ("send whatsapp", "send email", "post ", "submit form", "message ")):
        return _route(original, "blocked_external_send", 0.92, None, "external_send", real=True, refusal="External sending is blocked in Phase 12G.")
    if _has_any(normalized, ("run shell", "run powershell", "terminal", "cmd.exe", "execute command")):
        return _route(original, "blocked_terminal", 0.95, None, "terminal", real=True, refusal="Terminal execution is blocked in Phase 12G.")
    if _has_any(normalized, ("open chrome", "browser control", "click", "screen", "pyautogui", "playwright")):
        return _route(original, "blocked_browser_desktop", 0.86, None, "browser_action", real=True, refusal="Browser/desktop control is not enabled through `eva ask`.")

    if _has_any(normalized, ("verify sandbox apply", "verify the sandbox apply", "check sandbox apply")):
        cmd = f"eva file approval sandbox verify {approval_id}" if approval_id else None
        return _route(original, "approval_sandbox_verify", 0.95, cmd, "verify", file=True, approval=True, sandbox=True)
    if _has_any(normalized, ("rollback sandbox apply", "rollback the sandbox apply", "undo sandbox apply")):
        cmd = f"eva file approval sandbox rollback {approval_id}" if approval_id else None
        return _route(original, "approval_sandbox_rollback", 0.95, cmd, "rollback", file=True, approval=True, sandbox=True)
    if _has_any(normalized, ("sandbox apply", "apply approved change", "apply the approved change", "test approved file change")):
        cmd = f"eva file approval sandbox apply {approval_id}" if approval_id else None
        return _route(original, "approval_sandbox_apply", 0.95, cmd, "sandbox_apply", file=True, approval=True, sandbox=True)

    if _has_any(normalized, ("pending approvals", "show approvals", "show file approvals")):
        return _route(original, "approval_pending", 0.94, "eva file approvals pending", "approve", file=True, approval=True)
    if _has_any(normalized, ("approval status", "file approval status")):
        return _route(original, "approval_status", 0.9, "eva file approval status", "approve", file=True, approval=True)
    if _has_any(normalized, ("approve this file change", "create approval request", "approval request")):
        return _route(original, "approval_request", 0.84, None, "approve", file=True, approval=True)

    if _has_any(normalized, ("what can eva do safely", "what can you do safely", "safe capabilities", "safely right now")):
        return _route(original, "capability_status", 0.94, "eva capabilities safe", "read", planner=True)
    if _has_any(normalized, ("show capabilities", "eva capabilities", "capabilities")):
        return _route(original, "capability_status", 0.86, "eva capabilities", "read", planner=True)
    if _has_any(normalized, ("show agents", "agent framework", "agents status")):
        return _route(original, "agent_status", 0.86, "eva agents", "read", planner=True)
    if _has_any(normalized, ("planner status", "plan status")):
        return _route(original, "planner_status", 0.86, "eva planner status", "read", planner=True)
    if _has_any(normalized, ("research memory status", "research status")):
        return _route(original, "research_memory_status", 0.86, "research memory status", "read", memory=True)
    if _has_any(normalized, ("safety status", "permissions status", "authority status")):
        return _route(original, "safety_status", 0.86, "permissions status", "read")

    if _has_any(normalized, ("draft readme", "readme section")):
        topic = _after_any(original, ("draft a README section about ", "draft README section about ", "draft readme section about ")) or "FileAgent"
        return _route(original, "file_draft", 0.9, f"eva draft readme section {topic.strip()}", "draft", file=True)
    if _has_any(normalized, ("draft report", "report outline")):
        return _route(original, "file_draft", 0.84, "eva draft report outline " + original, "draft", file=True)
    if _has_any(normalized, ("file change is safe", "file edit is safe", "apply readiness", "check if this file change is safe")):
        return _route(original, "file_apply_readiness", 0.82, "eva file apply policy", "plan", file=True)
    if _has_any(normalized, ("understand file", "summarize file", "summarise file")):
        return _route(original, "file_understand", 0.78, None, "read", file=True)
    if _has_any(normalized, ("inspect this project", "inspect project", "project inventory")):
        return _route(original, "project_inspect", 0.94, "eva project inspect", "read", planner=True, file=True)
    if _has_any(normalized, ("explain this project", "explain this repo", "what is this project")):
        return _route(original, "project_inspect", 0.9, "eva project inspect", "read", planner=True, file=True)
    if _has_any(normalized, ("inspect file", "preview file", "read file")):
        return _route(original, "file_inspect", 0.78, None, "read", file=True)

    return _route(original, "unknown", 0.2, None, "unknown", refusal="I could not map that to a safe Eva action yet.")


def _route(
    original: str,
    intent: str,
    confidence: float,
    command: str | None,
    category: str,
    *,
    planner: bool = False,
    file: bool = False,
    memory: bool = False,
    approval: bool = False,
    sandbox: bool = False,
    real: bool = False,
    refusal: str | None = None,
) -> NaturalRouteResult:
    return NaturalRouteResult(
        original_text=original,
        intent=intent,
        confidence=confidence,
        routed_to=command or "authority_preview",
        suggested_command=command,
        authority_category=category,
        needs_planner=planner,
        needs_file_agent=file,
        needs_memory=memory,
        needs_approval=approval,
        sandbox_only=sandbox,
        real_execution_requested=real,
        refusal_reason=refusal,
    )


def _normalize(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _approval_id(text: str) -> str | None:
    match = re.search(r"\b(fap_[a-zA-Z0-9]+)\b", text)
    return match.group(1) if match else None


def _after_any(text: str, prefixes: tuple[str, ...]) -> str | None:
    lowered = text.lower()
    for prefix in prefixes:
        idx = lowered.find(prefix.lower())
        if idx >= 0:
            return text[idx + len(prefix) :].strip(" .:")
    return None


def _is_project_note_request(text: str) -> bool:
    note_words = ("project note", "docs note", "phase note", "safe markdown note", "markdown note", "safe project note", "latest fileagent phase")
    action_words = ("create", "make", "draft", "safely create")
    if any(note in text for note in note_words) and any(action in text for action in action_words):
        return True
    return "draft and safely create a note" in text


def _browser_action_hint(text: str) -> str:
    for action in ("click", "type", "login", "upload", "download", "submit", "payment", "cookie", "profile"):
        if action in text:
            return action
    return "unknown"


def _desktop_action_hint(text: str) -> str:
    for action in ("screenshot", "screen", "click", "type", "hotkey", "clipboard", "file dialog", "terminal", "shell", "install", "launch", "open app"):
        if action in text:
            return action
    return "unknown"


def _desktop_app_hint(text: str) -> str:
    for app in ("terminal", "powershell", "cmd", "whatsapp", "email", "bank", "file explorer", "settings", "password", "notepad"):
        if app in text:
            return app
    return "unknown"


def _domain_hint(text: str) -> str:
    for token in str(text or "").replace("?", " ").split():
        if "." in token and len(token) > 3:
            return token.strip(".,;:()[]{}")
    if "gmail" in text:
        return "gmail.com"
    if "banking" in text or "bank" in text:
        return "banking.example"
    if "upload" in text or "files" in text:
        return "dropbox.com"
    return "example.com"
