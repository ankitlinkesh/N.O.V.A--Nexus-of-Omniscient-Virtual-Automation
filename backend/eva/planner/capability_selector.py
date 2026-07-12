from __future__ import annotations


def _text(goal_text: str) -> str:
    return " ".join(str(goal_text or "").lower().split())


def infer_goal_intents(goal_text: str) -> list[str]:
    text = _text(goal_text)
    intents: list[str] = []
    if "release candidate status" in text or "rc status" in text: intents.append("rc_status")
    if "dirty tree manifest" in text: intents.append("rc_manifest")
    if "commit plan" in text or "what should i commit" in text: intents.append("rc_commit_plan")
    if "hardening report" in text: intents.append("rc_hardening_report")
    if "rc checklist" in text: intents.append("rc_checklist")
    if "safe to commit" in text or "ready for release candidate" in text: intents.append("rc_readiness")
    if "rc safety proof" in text: intents.append("rc_safety_proof")
    if "rc verification" in text: intents.append("rc_verification")
    if "release status" in text: intents.append("release_status")
    if "public demo" in text: intents.append("release_demo")
    if "demo commands" in text: intents.append("release_commands")
    if "capability map" in text or text == "what can eva do": intents.append("release_capability_map")
    if "safety proof" in text: intents.append("release_safety_proof")
    if "release readiness" in text or "ready for demo" in text: intents.append("release_readiness")
    if "known limitations" in text or "what can eva not do" in text: intents.append("release_limitations")
    if "release verification" in text: intents.append("release_verification")
    if "demo smoke" in text or "smoke test" in text or "demo safely" in text: intents.append("release_demo_smoke")
    if "post push sync" in text or "post-push sync" in text or "synced with github" in text: intents.append("release_post_push_sync")
    if "roadmap status" in text or "improvement roadmap" in text or "phase roadmap" in text: intents.append("roadmap_status")
    if "execution boundaries" in text or "execution boundary audit" in text or "actually execute safely" in text: intents.append("execution_boundaries")
    if "catalog status" in text or "capability catalog" in text or "command catalog" in text: intents.append("catalog_status")
    if "frontend truth" in text or "safe demo ui" in text: intents.append("frontend_truth_status")
    if "grounded answer" in text or "grounded routing" in text: intents.append("grounded_answer_status")
    if "voice reliability" in text or "voice diagnostics" in text: intents.append("voice_reliability_status")
    if "verifier dashboard" in text or "verifier metadata" in text: intents.append("verifier_dashboard_status")
    if "coding specialist status" in text or "coding status" in text: intents.append("coding_status")
    if any(x in text for x in ("can eva edit code", "can eva apply patches", "can eva run tests", "can eva run git commands", "coding policy")): intents.append("coding_policy")
    if "coding specialists" in text: intents.append("coding_specialists")
    if "coding task preview" in text: intents.append("coding_task_preview")
    if "coding project context" in text: intents.append("coding_project_context")
    if any(x in text for x in ("plan a code change", "coding patch plan")): intents.append("coding_patch_plan")
    if "coding review checklist" in text or "review this coding task" in text: intents.append("coding_review_checklist")
    if "coding test plan" in text: intents.append("coding_test_plan")
    if "coding risk review" in text: intents.append("coding_risk_review")
    if "coding handoff" in text: intents.append("coding_handoff")
    if "coding blocked actions" in text: intents.append("coding_blocked_actions")
    if "coding readiness" in text: intents.append("coding_readiness")
    if "show news dashboard" in text: intents.append("news_dashboard")
    if "show web intelligence status" in text: intents.append("news_status")
    if any(x in text for x in ("news policy","monitor news","crawl the web")): intents.append("news_policy")
    if "news source reliability" in text: intents.append("news_sources")
    if "news freshness" in text: intents.append("news_freshness")
    if "news readiness" in text: intents.append("news_readiness")
    if "show desktop control status" in text:
        intents.append("desktop_control_status")
    if any(term in text for term in ("can eva control my desktop", "can eva click or type", "show desktop control policy")):
        intents.append("desktop_control_policy")
    if "dry run desktop action" in text:
        intents.append("desktop_control_dry_run")
    if "what desktop actions are blocked" in text:
        intents.append("desktop_control_blocked_actions")
    if "what approval is required for desktop control" in text:
        intents.append("desktop_control_approvals")
    if "show desktop control readiness" in text:
        intents.append("desktop_control_readiness")
    if any(term in text for term in ("desktop observation status", "desktop observe status")):
        intents.append("desktop_observe_status")
    if any(term in text for term in ("desktop observation policy", "desktop observe policy", "can eva see my screen")):
        intents.append("desktop_observe_policy")
    if any(term in text for term in ("desktop observation backend", "desktop observe backend")):
        intents.append("desktop_observe_backend")
    if any(term in text for term in ("observe desktop read only", "desktop observation mock", "desktop observe mock")):
        intents.append("desktop_observe_mock")
    if any(term in text for term in ("desktop observation safety report", "desktop observe safety report")):
        intents.append("desktop_observe_safety_report")
    if any(term in text for term in ("sensitive screen policy", "desktop observation sensitive screens")):
        intents.append("desktop_observe_sensitive_screens")
    if any(term in text for term in ("desktop observation redaction policy", "desktop observe redaction policy")):
        intents.append("desktop_observe_redaction_policy")
    if any(term in text for term in ("desktop observation readiness", "desktop observe readiness")):
        intents.append("desktop_observe_readiness")
    if any(term in text for term in ("context assembly status", "context status")):
        intents.append("context_status")
    if any(term in text for term in ("context sources", "allowed context sources", "blocked context sources")):
        intents.append("context_sources")
    if any(term in text for term in ("how does eva choose context", "context policy")):
        intents.append("context_policy")
    if any(term in text for term in ("context budget", "show context budget")):
        intents.append("context_budget")
    if any(term in text for term in ("what context will eva send to the llm", "context assemble preview", "assemble context")):
        intents.append("context_assemble_preview")
    if any(term in text for term in ("context grounding report", "show context grounding report")):
        intents.append("context_grounding_report")
    if any(term in text for term in ("context redaction policy", "can eva include secrets in context")):
        intents.append("context_redaction_policy")
    if any(term in text for term in ("context readiness", "show context readiness")):
        intents.append("context_readiness")
    if any(term in text for term in ("threat defense status", "show threat defense status")):
        intents.append("threat_status")
    if any(term in text for term in ("threat catalog", "show threat catalog")):
        intents.append("threat_catalog")
    if any(term in text for term in ("how does eva stop prompt injection", "threat policy", "prompt injection policy")):
        intents.append("threat_policy")
    if any(term in text for term in ("scan this for prompt injection", "threat scan preview", "scan prompt injection")):
        intents.append("threat_scan_preview")
    if any(term in text for term in ("threat injection examples", "prompt injection examples")):
        intents.append("threat_injection_examples")
    if any(term in text for term in ("can eva leak secrets through context", "threat exfiltration examples", "exfiltration examples")):
        intents.append("threat_exfiltration_examples")
    if any(term in text for term in ("context poisoning guard", "untrusted context override", "can untrusted context override instructions", "context says ignore safety policy")):
        intents.append("threat_context_guard")
    if any(term in text for term in ("threat defense readiness", "show threat defense readiness")):
        intents.append("threat_readiness")
    if any(term in text for term in ("agent loop status", "show agent loop status")):
        intents.append("agent_loop_status")
    if any(term in text for term in ("agent loop policy", "how does eva's agent loop work", "how does evas agent loop work")):
        intents.append("agent_loop_policy")
    if any(term in text for term in ("run agent loop preview", "agent loop run preview")):
        intents.append("agent_loop_run_preview")
    if any(term in text for term in ("agent loop steps", "agent loop stages")):
        intents.append("agent_loop_steps")
    if any(term in text for term in ("agent loop action previews", "show agent loop action previews")):
        intents.append("agent_loop_action_previews")
    if any(term in text for term in ("agent loop safety report", "can the agent loop execute tools", "show agent loop safety report")):
        intents.append("agent_loop_safety_report")
    if any(term in text for term in ("agent loop stop reasons", "what happens if the agent loop gets stuck")):
        intents.append("agent_loop_stop_reasons")
    if any(term in text for term in ("agent loop readiness", "show agent loop readiness")):
        intents.append("agent_loop_readiness")
    if any(term in text for term in ("workflow planner status", "show workflow planner status")):
        intents.append("workflow_planner_status")
    if any(term in text for term in ("workflow planner catalog", "show workflow planner catalog")):
        intents.append("workflow_planner_catalog")
    if any(term in text for term in ("workflow planner policy", "how does eva choose workflows", "can workflow planner execute tools")):
        intents.append("workflow_planner_policy")
    if any(term in text for term in ("plan a workflow preview", "workflow planner preview")):
        intents.append("workflow_planner_preview")
    if any(term in text for term in ("workflow dependencies", "show workflow dependencies")):
        intents.append("workflow_planner_dependencies")
    if any(term in text for term in ("workflow approval preview", "show workflow approval preview")):
        intents.append("workflow_planner_approvals")
    if any(term in text for term in ("workflow rollback plan", "show workflow rollback plan")):
        intents.append("workflow_planner_rollback")
    if any(term in text for term in ("workflow planner readiness", "show workflow planner readiness")):
        intents.append("workflow_planner_readiness")
    if any(term in text for term in ("execution gates status", "show execution gates status")):
        intents.append("execution_gates_status")
    if any(term in text for term in ("execution gates policy", "execution gate policy", "what can eva execute", "structured execution gate policy")):
        intents.append("execution_gates_policy")
    if any(term in text for term in ("execution gates evaluate", "execution gate evaluate")):
        intents.append("execution_gates_evaluate")
    if any(term in text for term in ("what requires approval", "execution gates approvals", "execution gate approvals")):
        intents.append("execution_gates_approvals")
    if any(term in text for term in ("what confirmation phrase is needed", "execution gates confirmations", "execution gate confirmations")):
        intents.append("execution_gates_confirmations")
    if any(term in text for term in ("execution gates rollback", "execution gate rollback")):
        intents.append("execution_gates_rollback")
    if any(term in text for term in ("can eva execute tools", "can eva control browser or desktop", "can eva read secrets", "execution gates blocked actions", "execution gate blocked actions")):
        intents.append("execution_gates_blocked_actions")
    if any(term in text for term in ("execution gate readiness", "execution gates readiness", "show execution gate readiness")):
        intents.append("execution_gates_readiness")
    if any(term in text for term in ("ai os status", "show ai os status")):
        intents.append("ai_os_status")
    if any(term in text for term in ("eva os dashboard", "show eva os dashboard", "what can eva do now")):
        intents.append("ai_os_dashboard")
    if any(term in text for term in ("system map", "show system map")):
        intents.append("ai_os_system_map")
    if any(term in text for term in ("capability matrix", "show capability matrix")):
        intents.append("ai_os_capability_matrix")
    if any(term in text for term in ("feature states", "show feature states")):
        intents.append("ai_os_feature_states")
    if any(term in text for term in ("safety boundaries", "can eva really execute anything")):
        intents.append("ai_os_safety_boundaries")
    if any(term in text for term in ("ai os locked features", "eva os locked features")):
        intents.append("ai_os_locked_features")
    if any(term in text for term in ("ai os next safe step", "eva os next safe step")):
        intents.append("ai_os_next_safe_step")
    if any(term in text for term in ("eva readiness", "show eva readiness")):
        intents.append("ai_os_readiness")
    if any(term in text for term in ("voice assistant status", "voice status", "show voice assistant status")):
        intents.append("voice_status")
    if any(term in text for term in ("voice policy", "how will eva voice work")):
        intents.append("voice_policy")
    if any(term in text for term in ("voice providers", "voice provider policy", "can eva speak using tts")):
        intents.append("voice_providers")
    if any(term in text for term in ("voice listen state", "can eva listen to my microphone")):
        intents.append("voice_listen_state")
    if any(term in text for term in ("voice transcript safety", "show voice transcript safety")):
        intents.append("voice_transcript_safety")
    if any(term in text for term in ("voice route preview", "show voice route preview")):
        intents.append("voice_route_preview")
    if any(term in text for term in ("voice confirmations", "can voice commands execute tools")):
        intents.append("voice_confirmations")
    if any(term in text for term in ("voice readiness", "show voice readiness")):
        intents.append("voice_readiness")
    if any(term in text for term in ("memory v3 status", "show memory v3 status")):
        intents.append("memory_v3_status")
    if any(term in text for term in ("memory v3 policy", "how does eva decide what to remember", "can memory override safety policy")):
        intents.append("memory_v3_policy")
    if any(term in text for term in ("memory v3 sources", "memory source model", "memory trust model")):
        intents.append("memory_v3_sources")
    if any(term in text for term in ("memory v3 privacy", "can eva store secrets in memory")):
        intents.append("memory_v3_privacy")
    if any(term in text for term in ("memory v3 freshness", "show memory freshness")):
        intents.append("memory_v3_freshness")
    if any(term in text for term in ("memory v3 conflicts", "show memory conflicts")):
        intents.append("memory_v3_conflicts")
    if any(term in text for term in ("memory v3 retrieval preview", "what memory will eva use for context")):
        intents.append("memory_v3_retrieval_preview")
    if any(term in text for term in ("memory v3 readiness", "show memory v3 readiness")):
        intents.append("memory_v3_readiness")
    if any(term in text for term in ("llm router status", "llm routing enabled", "can eva call the llm")):
        intents.append("llm_status")
    if any(term in text for term in ("what llms can eva use", "llm providers")):
        intents.append("llm_providers")
    if any(term in text for term in ("how does eva choose a model", "llm routing policy")):
        intents.append("llm_routing_policy")
    if any(term in text for term in ("what happens if the llm fails", "llm fallback policy")):
        intents.append("llm_fallback_policy")
    if any(term in text for term in ("token limits", "llm limits")):
        intents.append("llm_limits")
    if any(term in text for term in ("structured output rules", "llm structured output")):
        intents.append("llm_structured_output")
    if any(term in text for term in ("llm validation status", "structured output validation status")):
        intents.append("llm_validation_status")
    if any(term in text for term in ("llm schema registry", "structured output schema registry")):
        intents.append("llm_schema_registry")
    if any(term in text for term in ("bad json", "malformed llm output", "invalid enum", "unknown capability", "hallucinated capability", "secret-like llm output", "tool execution")):
        intents.append("llm_validation_policy")
    if "llm repair policy" in text or "structured output repair policy" in text:
        intents.append("llm_repair_policy")
    if any(term in text for term in ("llm validate mock", "structured output validate mock")):
        intents.append("llm_validate_mock")
    if any(term in text for term in ("llm validate invalid examples", "structured output invalid examples")):
        intents.append("llm_validate_invalid_examples")
    if any(term in text for term in ("llm validation readiness", "structured output validation readiness")):
        intents.append("llm_validation_readiness")
    if "llm red team" in text:
        intents.append("llm_red_team_run" if "run" in text else "llm_red_team_status")
    if "llm failure tests" in text:
        intents.append("llm_failure_tests")
    if any(term in text for term in ("llm leaks secrets", "llm ignores safety policy", "llm safety failure report")):
        intents.append("llm_safety_failure_report")
    if "llm red team readiness" in text:
        intents.append("llm_red_team_readiness")
    if any(term in text for term in ("gemini fails", "all llms fail", "llm fallback chain", "simulate an llm timeout")):
        intents.append("llm_fallback_simulate")
    if "llm degraded mode" in text:
        intents.append("llm_degraded_mode")
    if any(term in text for term in ("llm session limits", "llm rate limits", "token limits")):
        intents.append("llm_session_limits")
    if any(term in text for term in ("runaway loops", "runaway protection")):
        intents.append("llm_runaway_protection")
    if "llm routing audit" in text:
        intents.append("llm_routing_audit_preview")
    if "desktop phase 14 status" in text:
        intents.append("desktop_phase14_status")
    if any(term in text for term in ("summarize desktop phase 14", "desktop phase 14 summary")):
        intents.append("desktop_phase14_summary")
    if any(term in text for term in ("desktop phase 14 limits", "what are desktop phase 14 limits")):
        intents.append("desktop_phase14_limits")
    if any(term in text for term in ("is desktop phase 14 complete", "desktop phase 14 ready", "is desktop phase 14 ready")):
        intents.append("desktop_phase14_ready")
    if any(term in text for term in ("prove desktop control is still locked", "desktop phase 14 final proof", "show desktop phase 14 final proof")):
        intents.append("desktop_phase14_final_proof")
    if any(term in text for term in ("desktop readiness proof", "is desktop observation ready")):
        intents.append("desktop_readiness_proof")
    if any(term in text for term in ("desktop locked status", "can eva control my desktop now")):
        intents.append("desktop_locked_status")
    if any(term in text for term in ("desktop readiness gaps", "what is missing before desktop observation", "what is missing before desktop control")):
        intents.append("desktop_readiness_gaps")
    if text.startswith("ask eva") or text.startswith("eva ask") or "natural request" in text:
        intents.append("natural_request")
    if any(term in text for term in ("specialist", "specialists", "who should handle", "which specialist")):
        intents.append("specialist_selection")
    if not any(intent.startswith("workflow_planner_") for intent in intents) and any(term in text for term in ("skill", "skills", "workflow", "workflows", "next workflow step")):
        intents.append("skill_workflow")
    if any(term in text for term in ("continue workflow", "continue the project note workflow", "continue project note workflow", "what should i do next", "next step", "latest approval", "latest real create", "latest rollback")):
        intents.append("workflow_state")
    if any(term in text for term in ("golden workflow proof", "did the golden workflow pass")):
        intents.append("golden_workflow_proof")
    if "golden workflow test plan" in text:
        intents.append("golden_workflow_test_plan")
    if any(term in text for term in ("create a project note", "project note", "safe markdown note", "golden workflow", "draft and safely create", "continue workflow", "rollback created note")):
        intents.append("golden_workflow")
    if any(term in text for term in ("docs note", "phase note", "latest fileagent phase")):
        intents.extend(["golden_workflow", "skill_workflow"])
    if any(term in text for term in ("show dashboard", "open dashboard", "control center", "show eva status", "what is eva doing", "show system state", "system state")):
        intents.append("control_center")
    if any(term in text for term in ("can eva control my desktop", "can eva see my screen", "is desktop control enabled", "desktop status")):
        intents.append("desktop_status")
    if any(term in text for term in ("desktop policy", "what desktop actions are allowed", "show desktop policy")):
        intents.append("desktop_policy")
    if any(term in text for term in ("desktop blocked actions", "what desktop actions are blocked")):
        intents.append("desktop_blocked_actions")
    if any(term in text for term in ("desktop action safety", "can eva click and type", "can eva click", "can eva type", "can it click", "can it type", "can eva open apps", "can eva use terminal")):
        intents.append("desktop_action_safety")
    if any(term in text for term in ("dry run clicking a button", "dry run desktop action", "desktop action dry run")):
        intents.append("desktop_action_dry_run")
    if any(term in text for term in ("what would eva do to open an app", "plan desktop actions", "desktop action plan")):
        intents.append("desktop_action_plan_preview")
    if any(term in text for term in ("can eva click this", "can eva type into an app", "can eva press hotkeys", "desktop action risk")):
        intents.append("desktop_action_risk")
    if any(term in text for term in ("desktop actions need approval", "desktop action approvals")):
        intents.append("desktop_action_approvals")
    if "desktop dry run policy" in text:
        intents.append("desktop_dry_run_policy")
    if "desktop action readiness" in text:
        intents.append("desktop_action_readiness")
    if any(term in text for term in ("how risky is", "score the risk", "desktop risk score")):
        intents.append("desktop_risk_score")
    if any(term in text for term in ("desktop risk factors", "what risk factors")):
        intents.append("desktop_risk_factors")
    if any(term in text for term in ("desktop approval policy", "approve eva to control my desktop")):
        intents.append("desktop_approval_policy")
    if "desktop approval levels" in text:
        intents.append("desktop_approval_levels")
    if any(term in text for term in ("desktop approval preview", "what approval is needed to click", "what approval is needed to type")):
        intents.append("desktop_approval_preview")
    if "confirmation phrase" in text:
        intents.append("desktop_confirmation_phrase")
    if any(term in text for term in ("desktop actions are forbidden", "desktop forbidden actions")):
        intents.append("desktop_forbidden_actions")
    if "approval audit" in text:
        intents.append("desktop_approval_audit_status")
    if any(term in text for term in ("desktop approval readiness", "is desktop approval ready")):
        intents.append("desktop_approval_readiness")
    if any(term in text for term in ("approval is needed", "desktop approval required")):
        intents.append("desktop_approval_required")
    if "desktop safety matrix" in text:
        intents.append("desktop_safety_matrix")
    if any(term in text for term in ("desktop actions are high risk", "desktop high risk actions")):
        intents.append("desktop_high_risk_actions")
    if "desktop risk readiness" in text:
        intents.append("desktop_risk_readiness")
    if any(term in text for term in ("desktop app risk", "app risk")):
        intents.append("desktop_app_risk")
    if any(term in text for term in ("desktop readiness", "is desktop ready")):
        intents.append("desktop_readiness")
    if any(term in text for term in ("desktop session status", "show desktop session status")):
        intents.append("desktop_session_status")
    if any(term in text for term in ("start a desktop session", "desktop session preview")):
        intents.append("desktop_session_preview")
    if any(term in text for term in ("desktop session plan", "what would desktop observation include")):
        intents.append("desktop_session_plan")
    if "desktop app status preview" in text:
        intents.append("desktop_app_status_preview")
    if any(term in text for term in ("desktop window status preview", "can eva see open windows", "open window preview")):
        intents.append("desktop_window_status_preview")
    if any(term in text for term in ("desktop active context preview", "can eva detect the active app")):
        intents.append("desktop_active_context_preview")
    if any(term in text for term in ("desktop observation readiness", "is desktop observation ready", "can eva inspect my screen")):
        intents.append("desktop_observation_readiness")
    if any(term in text for term in ("desktop screen policy", "can eva see my screen", "can eva read my screen")):
        intents.append("desktop_screen_policy")
    if any(term in text for term in ("screen observation policy", "show screen observation policy")):
        intents.append("desktop_screen_observation_policy")
    if any(term in text for term in ("sensitive screens", "what screens are sensitive")):
        intents.append("desktop_sensitive_screens")
    if any(term in text for term in ("screen redaction", "redact from screen")):
        intents.append("desktop_screen_redaction_policy")
    if any(term in text for term in ("screen capture gate", "take screenshots", "can eva take screenshots")):
        intents.append("desktop_screen_capture_gate")
    if any(term in text for term in ("screen readiness", "is screen observation ready")):
        intents.append("desktop_screen_readiness")
    if "desktop observation policy" in text:
        intents.append("desktop_observation_policy")
    if any(term in text for term in ("browser read-only status", "browser readonly status", "browser read status")):
        intents.append("browser_read_status")
    if any(term in text for term in ("browser read-only policy", "browser readonly policy", "can eva read a webpage", "can eva click or type in the browser", "logged-in browser")):
        intents.append("browser_read_policy")
    if any(term in text for term in ("browser read url policy", "browser url policy")):
        intents.append("browser_read_url_policy")
    if any(term in text for term in ("observe a webpage read only", "observe a web page read only", "browser read observe")):
        intents.append("browser_read_observe")
    if "browser read mock observe" in text:
        intents.append("browser_read_mock_observe")
    if "browser read safety report" in text:
        intents.append("browser_read_safety_report")
    if any(term in text for term in ("blocked browser urls", "browser read blocked urls")):
        intents.append("browser_read_blocked_urls")
    if any(term in text for term in ("browser read-only readiness", "browser readonly readiness", "browser read readiness")):
        intents.append("browser_read_readiness")
    if any(term in text for term in ("can eva use the browser", "can you use the browser", "is browser control enabled", "browser status")):
        intents.append("browser_status")
    if any(term in text for term in ("browser session status", "show browser session status", "can eva browse websites")):
        intents.append("browser_session_status")
    if any(term in text for term in ("start a browser session", "open a browser", "browser session preview")):
        intents.append("browser_session_preview")
    if any(term in text for term in ("browser session plan", "what would a browser session do")):
        intents.append("browser_session_plan")
    if any(term in text for term in ("browser read-only mode ready", "browser readonly mode ready")):
        intents.append("browser_session_readiness")
    if any(term in text for term in ("can eva read a webpage", "can eva summarize a page", "page summary policy")):
        intents.append("browser_page_summary_policy")
    if any(term in text for term in ("what would eva extract from a webpage", "page summary preview", "browser extraction preview")):
        intents.append("browser_page_summary_preview")
    if any(term in text for term in ("can eva inspect dom", "inspect dom", "dom summary policy")):
        intents.append("browser_dom_summary_policy")
    if "text extraction policy" in text:
        intents.append("browser_text_extraction_policy")
    if any(term in text for term in ("can eva take screenshots", "browser observation policy", "observation readiness")):
        intents.append("browser_observation_readiness")
    if "redaction policy" in text:
        intents.append("browser_redaction_policy")
    if any(term in text for term in ("dry run opening a website", "browser action dry run")):
        intents.append("browser_action_dry_run")
    if any(term in text for term in ("what would eva do to search google", "plan browser actions", "browser action plan")):
        intents.append("browser_action_plan_preview")
    if any(term in text for term in ("can eva click this", "can eva type into a website", "browser action risk")):
        intents.append("browser_action_risk")
    if any(term in text for term in ("browser actions need approval", "browser action approvals")):
        intents.append("browser_action_approvals")
    if "browser dry run policy" in text:
        intents.append("browser_dry_run_policy")
    if "browser action readiness" in text:
        intents.append("browser_action_readiness")
    if any(term in text for term in ("is example.com safe", "site safe for eva", "domain check")):
        intents.append("browser_domain_check")
    if any(term in text for term in ("can eva use gmail", "can eva open a banking website", "can eva upload files to a site", "site risk")):
        intents.append("browser_site_risk")
    if any(term in text for term in ("browser domain rules", "show browser domain policy")):
        intents.append("browser_domain_rules")
    if any(term in text for term in ("what sites are risky", "sensitive sites")):
        intents.append("browser_sensitive_sites")
    if any(term in text for term in ("approvals are needed for sensitive sites", "domain approvals", "sensitive site approvals")):
        intents.append("browser_domain_approvals")
    if "domain readiness" in text:
        intents.append("browser_domain_readiness")
    if any(term in text for term in ("browser read-only mode ready", "browser readonly mode ready", "browser read only readiness")):
        intents.append("browser_readonly_readiness")
    if "browser readiness proof" in text:
        intents.append("browser_readiness_proof")
    if any(term in text for term in ("browser safety proof", "prove browser control is still locked")):
        intents.append("browser_safety_proof")
    if any(term in text for term in ("missing before browser read-only", "browser readiness gaps")):
        intents.append("browser_readiness_gaps")
    if any(term in text for term in ("can eva browse now", "browser locked status")):
        intents.append("browser_locked_status")
    if any(term in text for term in ("phase 13 browser safe", "browser phase 13 proof")):
        intents.append("browser_phase13_proof")
    if any(term in text for term in ("browser phase 13 status", "phase 13 browser status")):
        intents.append("browser_phase13_status")
    if any(term in text for term in ("summarize browser phase 13", "browser phase 13 summary")):
        intents.append("browser_phase13_summary")
    if any(term in text for term in ("what are browser phase 13 limits", "browser phase 13 limits")):
        intents.append("browser_phase13_limits")
    if any(term in text for term in ("is browser phase 13 complete", "browser phase 13 ready", "is browser phase 13 ready")):
        intents.append("browser_phase13_ready")
    if any(term in text for term in ("browser phase 13 final proof", "show browser phase 13 final proof")):
        intents.append("browser_phase13_final_proof")
    if any(term in text for term in ("browser policy", "browser actions are allowed", "show browser policy", "what browser actions")):
        intents.append("browser_policy")
    if any(term in text for term in ("browser action safety", "can eva click", "can eva type", "can eva login", "can eva upload", "can eva download", "can it click", "can it type", "click login", "login or upload")):
        intents.append("browser_action_safety")
    if "browser readiness" in text:
        intents.append("browser_readiness")
    if any(term in text for term in ("work session", "work sessions", "session status", "latest session", "what happened last", "audit timeline")):
        intents.append("work_sessions")
    if any(term in text for term in ("what features are locked", "locked features", "features locked")):
        intents.append("locked_features")
    if any(term in text for term in ("what features are enabled", "enabled features", "features enabled")):
        intents.append("enabled_features")
    if any(term in text for term in ("what is the next safe step", "next safe step")):
        intents.append("next_safe_step")
    if any(term in text for term in ("quick check", "smoke test", "verify eva", "how do i verify eva", "phase 12 status", "is eva safe", "what works right now", "what is locked", "ux status")):
        intents.append("phase12_verification")
    if any(term in text for term in ("is phase 12 ready", "phase 12 ready", "phase12 ready", "ready for phase 12 checkpoint")):
        intents.append("phase12_ready")
    if any(term in text for term in ("summarize phase 12", "phase 12 summary", "phase12 summary")):
        intents.append("phase12_summary")
    if any(term in text for term in ("what are phase 12 limits", "phase 12 limits", "phase12 limits")) or ("phase 12" in text and "limit" in text):
        intents.append("phase12_limits")
    if any(term in text for term in ("show phase 12 proof", "phase 12 proof", "phase12 proof")):
        intents.append("phase12_proof")
    if any(term in text for term in ("inspect this project", "explain this repo", "explain this project", "summarize current eva status", "project reality check", "current eva status")):
        intents.append("project_reality")
    if any(term in text for term in ("what changed recently", "recent changes", "latest changes")):
        intents.append("project_recent_changes")
    if any(term in text for term in ("what is broken", "what failed", "what is failing")):
        intents.append("project_broken_status")
    if any(term in text for term in ("what should we do next", "next safe phase")):
        intents.append("project_next_step")
    if any(term in text for term in ("what proof do we have", "show proof", "completion proof")):
        intents.append("project_proof")
    if any(term in text for term in ("are we actually done", "are we done", "what proof do we have", "show proof", "completion proof")):
        intents.extend(["phase12_verification", "skill_workflow", "workflow_state"])
    if any(term in text for term in ("are we actually done", "are we done", "done check")):
        intents.append("done_check")
    if any(term in text for term in ("saved research", "research memory", "retrieve my notes", "what did i save", "my research")):
        intents.append("retrieve_memory")
    if any(term in text for term in ("review memory", "promote candidates", "recall stats")):
        intents.append("memory_review")
    if any(term in text for term in ("import note", "save research", "save note")):
        intents.append("research_memory_write")
    if ("demo" in text or "public status" in text or "safety test" in text) and not any(
        intent.startswith("release_") for intent in intents
    ):
        intents.append("public_demo")
    if "dry run" in text or "dry-run" in text or "plan this" in text or text.startswith("plan "):
        intents.append("v2_planning")
    if "route this" in text or "route preview" in text:
        intents.append("route_preview")
    if any(term in text for term in ("open website", "open chatgpt", "open chrome", "search web", "control browser", "launch browser")):
        intents.append("browser_open")
    if any(term in text for term in ("what is this project", "explain this repo", "explain repo", "project inventory", "project explain", "what files are missing", "missing files", "project dependencies", "key files", "inspect project structure", "inspect file", "read file", "preview file", "file preview", "find file", "search file", "project structure", "folder inspect", "show file", "summarize file", "summarise file", "summarize readme", "summarise readme")) or ("inspect" in text and any(term in text for term in ("readme", ".md", ".py", ".json", "file"))):
        intents.append("file_read_only")
    if any(term in text for term in ("edit file", "make report", "create document", "write file")):
        intents.append("file_or_document")
    if any(term in text for term in ("draft readme", "readme section", "make a report", "create report", "draft report", "report outline", "append to readme", "append to file", "replace text", "draft file", "make a file", "create file", "write a project summary", "project todo", "diff preview", "create changelog")):
        intents.append("file_draft_preview")
        intents.append("skill_workflow")
    if any(term in text for term in ("apply this draft", "apply this change", "apply this file change", "write this to file", "update readme", "edit this file", "is this file change safe", "is this file edit safe", "prepare to update", "what would happen if we apply")):
        intents.append("file_apply_readiness")
    if any(term in text for term in ("sandbox apply", "test this approved file change", "verify sandbox apply", "rollback sandbox apply")):
        intents.append("file_sandbox_apply")
    if any(term in text for term in ("create approved markdown", "create the approved text file", "really create the approved docs file", "apply the approved docs file for real", "real apply approved", "real apply this approved", "real create", "verify real created", "rollback real created", "rollback real create")):
        intents.append("file_real_create")
    if any(term in text for term in ("approve this file change", "create an approval request", "create an approval for", "approve readme edit", "what approvals are pending", "pending approvals", "is this file edit approved", "apply approved file change")):
        intents.append("file_approval")
    desktop_preview_request = any(term in text for term in ("plan desktop actions", "desktop action plan", "dry run desktop action", "approval is needed", "desktop risk score", "score the risk", "how risky is"))
    if not desktop_preview_request and any(term in text for term in ("send whatsapp", "send email", "message ", "post ", "submit form")):
        intents.append("external_message")
    if any(term in text for term in ("delete", "shutdown", "install", "run powershell", "run shell", "terminal", "remove folder")):
        intents.append("destructive_or_system")
    if "context" not in text and any(term in text for term in ("hackathon", "submission", "proposal", "report", "summary", "summarize")):
        intents.append("draft_content")
    if not intents:
        intents.append("unknown")
    return _dedupe(intents)


def select_capabilities_for_goal(goal_text: str) -> list[str]:
    intents = infer_goal_intents(goal_text)
    text = _text(goal_text)
    selected: list[str] = []
    if "context_status" in intents:
        selected.append("context.status")
    if "context_sources" in intents:
        selected.append("context.sources")
    if "context_policy" in intents:
        selected.append("context.policy")
    if "context_budget" in intents:
        selected.append("context.budget")
    if "context_assemble_preview" in intents:
        selected.append("context.assemble_preview")
    if "context_grounding_report" in intents:
        selected.append("context.grounding_report")
    if "context_redaction_policy" in intents:
        selected.append("context.redaction_policy")
    if "context_readiness" in intents:
        selected.append("context.readiness")
    if "threat_status" in intents:
        selected.append("threat.status")
    if "threat_catalog" in intents:
        selected.append("threat.catalog")
    if "threat_policy" in intents:
        selected.append("threat.policy")
    if "threat_scan_preview" in intents:
        selected.append("threat.scan_preview")
    if "threat_injection_examples" in intents:
        selected.append("threat.injection_examples")
    if "threat_exfiltration_examples" in intents:
        selected.append("threat.exfiltration_examples")
    if "threat_context_guard" in intents:
        selected.append("threat.context_guard")
    if "threat_readiness" in intents:
        selected.append("threat.readiness")
    if "agent_loop_status" in intents:
        selected.append("agent_loop.status")
    if "agent_loop_policy" in intents:
        selected.append("agent_loop.policy")
    if "agent_loop_run_preview" in intents:
        selected.append("agent_loop.run_preview")
    if "agent_loop_steps" in intents:
        selected.append("agent_loop.steps")
    if "agent_loop_action_previews" in intents:
        selected.append("agent_loop.action_previews")
    if "agent_loop_safety_report" in intents:
        selected.append("agent_loop.safety_report")
    if "agent_loop_stop_reasons" in intents:
        selected.append("agent_loop.stop_reasons")
    if "agent_loop_readiness" in intents:
        selected.append("agent_loop.readiness")
    if "workflow_planner_status" in intents:
        selected.append("workflow_planner.status")
    if "workflow_planner_catalog" in intents:
        selected.append("workflow_planner.catalog")
    if "workflow_planner_policy" in intents:
        selected.append("workflow_planner.policy")
    if "workflow_planner_preview" in intents:
        selected.append("workflow_planner.preview")
    if "workflow_planner_dependencies" in intents:
        selected.append("workflow_planner.dependencies")
    if "workflow_planner_approvals" in intents:
        selected.append("workflow_planner.approvals")
    if "workflow_planner_rollback" in intents:
        selected.append("workflow_planner.rollback")
    if "workflow_planner_readiness" in intents:
        selected.append("workflow_planner.readiness")
    if "execution_gates_status" in intents:
        selected.append("execution_gates.status")
    if "execution_gates_policy" in intents:
        selected.append("execution_gates.policy")
    if "execution_gates_evaluate" in intents:
        selected.append("execution_gates.evaluate")
    if "execution_gates_approvals" in intents:
        selected.append("execution_gates.approvals")
    if "execution_gates_confirmations" in intents:
        selected.append("execution_gates.confirmations")
    if "execution_gates_rollback" in intents:
        selected.append("execution_gates.rollback")
    if "execution_gates_blocked_actions" in intents:
        selected.append("execution_gates.blocked_actions")
    if "execution_gates_readiness" in intents:
        selected.append("execution_gates.readiness")
    if "ai_os_status" in intents:
        selected.append("ai_os.status")
    if "ai_os_dashboard" in intents:
        selected.append("ai_os.dashboard")
    if "ai_os_system_map" in intents:
        selected.append("ai_os.system_map")
    if "ai_os_capability_matrix" in intents:
        selected.append("ai_os.capability_matrix")
    if "ai_os_feature_states" in intents:
        selected.append("ai_os.feature_states")
    if "ai_os_safety_boundaries" in intents:
        selected.append("ai_os.safety_boundaries")
    if "ai_os_locked_features" in intents:
        selected.append("ai_os.locked_features")
    if "ai_os_next_safe_step" in intents:
        selected.append("ai_os.next_safe_step")
    if "ai_os_readiness" in intents:
        selected.append("ai_os.readiness")
    if "voice_status" in intents:
        selected.append("voice.status")
    if "voice_policy" in intents:
        selected.append("voice.policy")
    if "voice_providers" in intents:
        selected.append("voice.providers")
    if "voice_listen_state" in intents:
        selected.append("voice.listen_state")
    if "voice_transcript_safety" in intents:
        selected.append("voice.transcript_safety")
    if "voice_route_preview" in intents:
        selected.append("voice.route_preview")
    if "voice_confirmations" in intents:
        selected.append("voice.confirmations")
    if "voice_readiness" in intents:
        selected.append("voice.readiness")
    if "memory_v3_status" in intents:
        selected.append("memory_v3.status")
    if "memory_v3_policy" in intents:
        selected.append("memory_v3.policy")
    if "memory_v3_sources" in intents:
        selected.append("memory_v3.sources")
    if "memory_v3_privacy" in intents:
        selected.append("memory_v3.privacy")
    if "memory_v3_freshness" in intents:
        selected.append("memory_v3.freshness")
    if "memory_v3_conflicts" in intents:
        selected.append("memory_v3.conflicts")
    if "memory_v3_retrieval_preview" in intents:
        selected.append("memory_v3.retrieval_preview")
    if "memory_v3_readiness" in intents:
        selected.append("memory_v3.readiness")
    if "llm_status" in intents:
        selected.append("llm.status")
    if "llm_providers" in intents:
        selected.append("llm.providers")
    if "llm_routing_policy" in intents:
        selected.append("llm.routing_policy")
    if "llm_fallback_policy" in intents:
        selected.append("llm.fallback_policy")
    if "llm_limits" in intents:
        selected.append("llm.limits")
    if "llm_structured_output" in intents:
        selected.append("llm.structured_output")
    if "llm_validation_status" in intents:
        selected.append("llm.validation_status")
    if "llm_schema_registry" in intents:
        selected.append("llm.schema_registry")
    if "llm_validation_policy" in intents:
        selected.append("llm.validation_policy")
    if "llm_repair_policy" in intents:
        selected.append("llm.repair_policy")
    if "llm_validate_mock" in intents:
        selected.append("llm.validate_mock")
    if "llm_validate_invalid_examples" in intents:
        selected.append("llm.validate_invalid_examples")
    if "llm_validation_readiness" in intents:
        selected.append("llm.validation_readiness")
    if "llm_red_team_status" in intents:
        selected.append("llm.red_team_status")
    if "llm_red_team_run" in intents:
        selected.append("llm.red_team_run")
    if "llm_failure_tests" in intents:
        selected.append("llm.failure_tests")
    if "llm_safety_failure_report" in intents:
        selected.append("llm.safety_failure_report")
    if "llm_red_team_readiness" in intents:
        selected.append("llm.red_team_readiness")
    if "llm_fallback_simulate" in intents:
        selected.append("llm.fallback_simulate")
    if "llm_degraded_mode" in intents:
        selected.append("llm.degraded_mode")
    if "llm_session_limits" in intents:
        selected.append("llm.session_limits")
    if "llm_runaway_protection" in intents:
        selected.append("llm.runaway_protection")
    if "llm_routing_audit_preview" in intents:
        selected.append("llm.routing_audit_preview")
    if "natural_request" in intents:
        selected.append("eva.ask")
    if "specialist_selection" in intents:
        selected.append("eva.specialist_select")
    if "skill_workflow" in intents:
        selected.extend(["eva.skill_select", "eva.workflow_select", "eva.workflow_plan"])
    if "workflow_state" in intents:
        selected.extend(["eva.workflow_state", "eva.workflow_next_step", "eva.workflow_disambiguate"])
    if "golden_workflow" in intents:
        if "status" in _text(goal_text) or "show" in _text(goal_text):
            selected.append("eva.golden_workflows_status")
        elif "continue" in _text(goal_text) or "rollback" in _text(goal_text):
            selected.append("eva.golden_workflow_continue")
        else:
            selected.extend(["eva.fileagent_project_note_workflow", "eva.golden_workflow_project_note"])
    if "golden_workflow_proof" in intents:
        selected.append("eva.golden_workflow_proof")
    if "golden_workflow_test_plan" in intents:
        selected.append("eva.golden_workflow_test_plan")
    if "control_center" in intents:
        selected.append("eva.control_center_status")
    for intent, capability in (
        ("coding_status", "coding.status"),
        ("coding_policy", "coding.policy"),
        ("coding_specialists", "coding.specialists"),
        ("coding_task_preview", "coding.task_preview"),
        ("coding_project_context", "coding.project_context"),
        ("coding_patch_plan", "coding.patch_plan"),
        ("coding_review_checklist", "coding.review_checklist"),
        ("coding_test_plan", "coding.test_plan"),
        ("coding_risk_review", "coding.risk_review"),
        ("coding_handoff", "coding.handoff"),
        ("coding_blocked_actions", "coding.blocked_actions"),
        ("coding_readiness", "coding.readiness"),
    ):
        if intent in intents:
            selected.append(capability)
    for intent, capability in (
        ("rc_status", "rc.status"),
        ("rc_manifest", "rc.manifest"),
        ("rc_commit_plan", "rc.commit_plan"),
        ("rc_hardening_report", "rc.hardening_report"),
        ("rc_checklist", "rc.checklist"),
        ("rc_readiness", "rc.readiness"),
        ("rc_safety_proof", "rc.safety_proof"),
        ("rc_verification", "rc.verification"),
    ):
        if intent in intents:
            selected.append(capability)
    for intent, capability in (
        ("release_status", "release.status"),
        ("release_demo", "release.demo"),
        ("release_commands", "release.commands"),
        ("release_capability_map", "release.capability_map"),
        ("release_safety_proof", "release.safety_proof"),
        ("release_readiness", "release.readiness"),
        ("release_limitations", "release.limitations"),
        ("release_verification", "release.verification"),
        ("release_demo_smoke", "release.demo_smoke"),
        ("release_post_push_sync", "release.post_push_sync"),
    ):
        if intent in intents:
            selected.append(capability)
    for intent, capability in (
        ("roadmap_status", "roadmap.control_truth_panels"),
        ("execution_boundaries", "roadmap.execution_boundary_audit"),
        ("catalog_status", "roadmap.capability_catalog"),
        ("frontend_truth_status", "roadmap.frontend_truth"),
        ("grounded_answer_status", "roadmap.grounded_answers"),
        ("voice_reliability_status", "roadmap.voice_reliability"),
        ("verifier_dashboard_status", "roadmap.verifier_dashboard"),
    ):
        if intent in intents:
            selected.append(capability)
    for intent,cap in (("news_dashboard","news.dashboard"),("news_status","news.status"),("news_policy","news.policy"),("news_sources","news.sources"),("news_freshness","news.freshness"),("news_readiness","news.readiness")):
        if intent in intents: selected.append(cap)
    if "desktop_control_status" in intents:
        selected.append("desktop_control.status")
    if "desktop_control_policy" in intents:
        selected.append("desktop_control.policy")
    if "desktop_control_dry_run" in intents:
        selected.append("desktop_control.dry_run")
    if "desktop_control_approvals" in intents:
        selected.append("desktop_control.approvals")
    if "desktop_control_blocked_actions" in intents:
        selected.append("desktop_control.blocked_actions")
    if "desktop_control_readiness" in intents:
        selected.append("desktop_control.readiness")
    if "desktop_observe_status" in intents:
        selected.append("desktop_observe.status")
    if "desktop_observe_policy" in intents:
        selected.append("desktop_observe.policy")
    if "desktop_observe_backend" in intents:
        selected.append("desktop_observe.backend")
    if "desktop_observe_mock" in intents:
        selected.append("desktop_observe.mock")
    if "desktop_observe_safety_report" in intents:
        selected.append("desktop_observe.safety_report")
    if "desktop_observe_sensitive_screens" in intents:
        selected.append("desktop_observe.sensitive_screens")
    if "desktop_observe_redaction_policy" in intents:
        selected.append("desktop_observe.redaction_policy")
    if "desktop_observe_readiness" in intents:
        selected.append("desktop_observe.readiness")
    if "desktop_status" in intents:
        selected.append("desktop.status")
    if "desktop_policy" in intents:
        selected.append("desktop.policy")
    if "desktop_blocked_actions" in intents:
        selected.append("desktop.blocked_actions")
    if "desktop_action_safety" in intents:
        selected.append("desktop.action_safety_preview")
    if "desktop_action_dry_run" in intents:
        selected.append("desktop.action_dry_run")
    if "desktop_action_plan_preview" in intents:
        selected.append("desktop.action_plan_preview")
    if "desktop_action_risk" in intents:
        selected.append("desktop.action_risk")
    if "desktop_action_approvals" in intents:
        selected.append("desktop.action_approvals")
    if "desktop_dry_run_policy" in intents:
        selected.append("desktop.dry_run_policy")
    if "desktop_action_readiness" in intents:
        selected.append("desktop.action_readiness")
    if "desktop_risk_score" in intents:
        selected.append("desktop.risk_score")
    if "desktop_risk_factors" in intents:
        selected.append("desktop.risk_factors")
    if "desktop_approval_required" in intents:
        selected.append("desktop.approval_required")
    if "desktop_approval_policy" in intents:
        selected.append("desktop.approval_policy")
    if "desktop_approval_levels" in intents:
        selected.append("desktop.approval_levels")
    if "desktop_approval_preview" in intents:
        selected.append("desktop.approval_preview")
    if "desktop_confirmation_phrase" in intents:
        selected.append("desktop.confirmation_phrase")
    if "desktop_forbidden_actions" in intents:
        selected.append("desktop.forbidden_actions")
    if "desktop_approval_audit_status" in intents:
        selected.append("desktop.approval_audit_status")
    if "desktop_approval_readiness" in intents:
        selected.append("desktop.approval_readiness")
    if "desktop_phase14_status" in intents:
        selected.append("desktop.phase14_status")
    if "desktop_phase14_summary" in intents:
        selected.append("desktop.phase14_summary")
    if "desktop_phase14_limits" in intents:
        selected.append("desktop.phase14_limits")
    if "desktop_phase14_ready" in intents:
        selected.append("desktop.phase14_ready")
    if "desktop_phase14_final_proof" in intents:
        selected.append("desktop.phase14_final_proof")
    if "desktop_readiness_proof" in intents:
        selected.append("desktop.readiness_proof")
    if "desktop_locked_status" in intents:
        selected.append("desktop.locked_status")
    if "desktop_readiness_gaps" in intents:
        selected.append("desktop.readiness_gaps")
    if "desktop_safety_matrix" in intents:
        selected.append("desktop.safety_matrix")
    if "desktop_high_risk_actions" in intents:
        selected.append("desktop.high_risk_actions")
    if "desktop_risk_readiness" in intents:
        selected.append("desktop.risk_readiness")
    if "desktop_app_risk" in intents:
        selected.append("desktop.app_risk")
    if "desktop_readiness" in intents:
        selected.append("desktop.readiness")
    if "desktop_session_status" in intents:
        selected.append("desktop.session_status")
    if "desktop_session_preview" in intents:
        selected.append("desktop.session_preview")
    if "desktop_session_plan" in intents:
        selected.append("desktop.session_plan")
    if "desktop_app_status_preview" in intents:
        selected.append("desktop.app_status_preview")
    if "desktop_window_status_preview" in intents:
        selected.append("desktop.window_status_preview")
    if "desktop_active_context_preview" in intents:
        selected.append("desktop.active_context_preview")
    if "desktop_observation_readiness" in intents:
        selected.append("desktop.observation_readiness")
    if "desktop_screen_policy" in intents:
        selected.append("desktop.screen_policy")
    if "desktop_screen_observation_policy" in intents:
        selected.append("desktop.screen_observation_policy")
    if "desktop_sensitive_screens" in intents:
        selected.append("desktop.sensitive_screens")
    if "desktop_screen_redaction_policy" in intents:
        selected.append("desktop.screen_redaction_policy")
    if "desktop_screen_capture_gate" in intents:
        selected.append("desktop.screen_capture_gate")
    if "desktop_screen_readiness" in intents:
        selected.append("desktop.screen_readiness")
    if "desktop_observation_policy" in intents:
        selected.append("desktop.observation_policy")
    if "browser_read_status" in intents:
        selected.append("browser_read.status")
    if "browser_read_policy" in intents:
        selected.append("browser_read.policy")
    if "browser_read_url_policy" in intents:
        selected.append("browser_read.url_policy")
    if "browser_read_observe" in intents:
        selected.append("browser_read.observe")
    if "browser_read_mock_observe" in intents:
        selected.append("browser_read.mock_observe")
    if "browser_read_safety_report" in intents:
        selected.append("browser_read.safety_report")
    if "browser_read_blocked_urls" in intents:
        selected.append("browser_read.blocked_urls")
    if "browser_read_readiness" in intents:
        selected.append("browser_read.readiness")
    if "browser_status" in intents:
        selected.append("browser.status")
    if "browser_session_status" in intents:
        selected.append("browser.session_status")
    if "browser_session_preview" in intents:
        selected.append("browser.session_preview")
    if "browser_session_plan" in intents:
        selected.append("browser.session_plan")
    if "browser_session_readiness" in intents:
        selected.append("browser.session_readiness")
    if "browser_page_summary_policy" in intents:
        selected.append("browser.page_summary_policy")
    if "browser_page_summary_preview" in intents:
        selected.append("browser.page_summary_preview")
    if "browser_dom_summary_policy" in intents:
        selected.append("browser.dom_summary_policy")
    if "browser_text_extraction_policy" in intents:
        selected.append("browser.text_extraction_policy")
    if "browser_observation_readiness" in intents:
        selected.append("browser.observation_readiness")
    if "browser_redaction_policy" in intents:
        selected.append("browser.redaction_policy")
    if "browser_action_dry_run" in intents:
        selected.append("browser.action_dry_run")
    if "browser_action_plan_preview" in intents:
        selected.append("browser.action_plan_preview")
    if "browser_action_risk" in intents:
        selected.append("browser.action_risk")
    if "browser_action_approvals" in intents:
        selected.append("browser.action_approvals")
    if "browser_dry_run_policy" in intents:
        selected.append("browser.dry_run_policy")
    if "browser_action_readiness" in intents:
        selected.append("browser.action_readiness")
    if "browser_domain_check" in intents:
        selected.append("browser.domain_check")
    if "browser_site_risk" in intents:
        selected.append("browser.site_risk")
    if "browser_domain_rules" in intents:
        selected.append("browser.domain_rules")
    if "browser_sensitive_sites" in intents:
        selected.append("browser.sensitive_sites")
    if "browser_domain_approvals" in intents:
        selected.append("browser.domain_approvals")
    if "browser_domain_readiness" in intents:
        selected.append("browser.domain_readiness")
    if "browser_readonly_readiness" in intents:
        selected.append("browser.readonly_readiness")
    if "browser_readiness_proof" in intents:
        selected.append("browser.readiness_proof")
    if "browser_safety_proof" in intents:
        selected.append("browser.safety_proof")
    if "browser_readiness_gaps" in intents:
        selected.append("browser.readiness_gaps")
    if "browser_locked_status" in intents:
        selected.append("browser.locked_status")
    if "browser_phase13_proof" in intents:
        selected.append("browser.phase13_proof")
    if "browser_phase13_status" in intents:
        selected.append("browser.phase13_status")
    if "browser_phase13_summary" in intents:
        selected.append("browser.phase13_summary")
    if "browser_phase13_limits" in intents:
        selected.append("browser.phase13_limits")
    if "browser_phase13_ready" in intents:
        selected.append("browser.phase13_ready")
    if "browser_phase13_final_proof" in intents:
        selected.append("browser.phase13_final_proof")
    if "browser_policy" in intents:
        selected.append("browser.policy")
    if "browser_action_safety" in intents:
        selected.append("browser.action_safety_preview")
    if "browser_readiness" in intents:
        selected.append("browser.readiness")
    if "work_sessions" in intents:
        if "audit timeline" in text:
            selected.append("eva.audit_timeline")
        elif any(term in text for term in ("latest session", "what happened last")):
            selected.append("eva.latest_work_session")
        else:
            selected.append("eva.work_sessions_status")
    if "locked_features" in intents:
        selected.append("eva.locked_features")
    if "enabled_features" in intents:
        selected.append("eva.enabled_features")
    if "next_safe_step" in intents:
        selected.append("eva.next_safe_step")
    if "phase12_verification" in intents:
        text = _text(goal_text)
        if "full" in text:
            selected.append("eva.verify_full_command")
        elif any(term in text for term in ("quick check", "smoke test", "verify eva", "how do i verify eva")):
            selected.append("eva.smoke_status")
            selected.append("eva.verify_quick_command")
        elif "ux" in text:
            selected.append("eva.ux_status")
        else:
            selected.append("eva.phase12_status")
    if "phase12_ready" in intents:
        selected.append("eva.phase12_ready")
    if "phase12_summary" in intents:
        selected.append("eva.phase12_summary")
    if "phase12_limits" in intents:
        selected.append("eva.phase12_limits")
    if "phase12_proof" in intents:
        selected.append("eva.phase12_proof")
    if "project_reality" in intents:
        selected.append("eva.project_inspect")
    if "project_recent_changes" in intents:
        selected.append("eva.project_recent_changes")
    if "project_broken_status" in intents:
        selected.append("eva.project_reality_check")
    if "project_next_step" in intents:
        selected.append("eva.project_next_step")
    if "project_proof" in intents:
        selected.append("eva.project_proof")
    if "done_check" in intents:
        selected.append("eva.done_check")
    if "retrieve_memory" in intents:
        selected.extend(["research_memory.retrieve", "research_memory.search"])
    if "memory_review" in intents:
        text = _text(goal_text)
        if "recall stats" in text:
            selected.append("research_memory.recall_stats")
        elif "promote" in text:
            selected.append("research_memory.promote_candidates")
        else:
            selected.append("research_memory.review_memory")
    if "research_memory_write" in intents:
        selected.append("research_memory.save")
    if "public_demo" in intents:
        text = _text(goal_text)
        if "status" in text:
            selected.append("public_release.status")
        elif "safety test" in text:
            selected.append("public_release.safety_test")
        else:
            selected.append("public_release.demo")
    if "v2_planning" in intents:
        selected.append("eva_v2.plan")
    if "route_preview" in intents:
        selected.append("eva_v2.route")
    if "file_read_only" in intents:
        text = _text(goal_text)
        if any(term in text for term in ("find file", "search file")):
            selected.append("file.search_name")
        elif any(term in text for term in ("what is this project", "explain this repo", "explain repo", "project explain")):
            selected.append("file.project_explain")
        elif any(term in text for term in ("project inventory", "inspect project structure")):
            selected.append("file.project_inventory")
        elif any(term in text for term in ("what files are missing", "missing files")):
            selected.append("file.project_missing")
        elif any(term in text for term in ("project dependencies", "dependency", "key config")):
            selected.append("file.project_dependencies")
        elif any(term in text for term in ("summarize", "summarise", "understand", "readme")):
            selected.append("file.understand_text")
        elif "project structure" in text or "folder inspect" in text:
            selected.append("file.explain_project_structure")
        else:
            selected.append("file.preview_text")
    if "file_draft_preview" in intents:
        text = _text(goal_text)
        if "readme" in text and ("section" in text or "draft" in text):
            selected.append("file.draft_readme_section")
        elif "project summary" in text:
            selected.append("file.draft_project_summary")
        elif "project todo" in text:
            selected.append("file.draft_project_todo")
        elif "report" in text:
            selected.append("file.draft_report_outline")
        elif "append" in text:
            selected.append("file.draft_append_preview")
        elif "replace" in text:
            selected.append("file.draft_replace_preview")
        elif "diff" in text:
            selected.append("file.diff_preview")
        else:
            selected.append("file.draft_create_preview")
    if "file_apply_readiness" in intents:
        selected.append("file.apply_readiness")
    if "file_sandbox_apply" in intents:
        text = _text(goal_text)
        if "verify" in text:
            selected.append("file.sandbox_verify_apply")
        elif "rollback" in text:
            selected.append("file.sandbox_rollback_apply")
        else:
            selected.append("file.sandbox_apply_approved")
    if "file_real_create" in intents:
        text = _text(goal_text)
        if "verify" in text:
            selected.append("file.real_verify_new_text_file")
        elif "rollback" in text:
            selected.append("file.real_rollback_new_text_file")
        else:
            selected.extend(["file.real_apply_eligibility", "file.real_create_new_text_file", "file.real_create_safe_text"])
    if "file_approval" in intents:
        text = _text(goal_text)
        if "pending" in text:
            selected.append("file.approval_list_pending")
        elif "apply approved" in text:
            selected.append("file.sandbox_apply_approved")
        elif "approve " in text:
            selected.append("file.approval_approve_future")
        else:
            selected.append("file.approval_request_create")
    if "draft_content" in intents:
        selected.append("eva_v2.plan")
    return _dedupe(selected)


def explain_capability_selection(goal_text: str, capability_ids: list[str]) -> str:
    if not capability_ids:
        return "No registered safe capability directly matched this goal; the planner will produce a preview-only unknown step."
    intents = ", ".join(infer_goal_intents(goal_text))
    capabilities = ", ".join(capability_ids)
    return f"Detected intents: {intents}. Selected capabilities: {capabilities}."


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out
