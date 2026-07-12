# Eva Capabilities

Eva capabilities are local metadata records that describe what an existing Eva system can do, how risky it is, and which verifier covers it. They are discovery and planning inputs, not a broad execution switch.

## Capability Model

Each capability records:

- id and name
- provider and category
- risk level
- read-only or local-write mode
- confirmation requirement
- default enabled status
- safety notes
- verifier name when available

The safe catalog currently covers existing Research Memory, FileAgent read-only repo inspection, heuristic project understanding, output-only draft previews, apply-readiness planning, approval-ledger metadata, sandbox-only apply harness metadata, explicit Eva v2 preview/status paths, and public release/demo/status surfaces.

Phase 12O adds read-only project/reality capabilities:

- `eva.project_inspect`
- `eva.project_reality_check`
- `eva.project_recent_changes`
- `eva.project_next_step`
- `eva.project_proof`
- `eva.done_check`

They are metadata/status formatters only. They do not run verifiers or enable file, browser, desktop, MCP, terminal, package, cloud, or message execution.

Phase 12P upgrades Control Center status capabilities:

- `eva.control_center_status`
- `eva.control_center_summary`
- `eva.locked_features`
- `eva.enabled_features`
- `eva.next_safe_step`

These are read-only dashboard/status views. They make locked features visible instead of hidden, but they do not unlock them.

Phase 12Q adds WorkSession/audit capabilities:

- `eva.work_sessions_status`
- `eva.work_sessions_recent`
- `eva.work_session_timeline`
- `eva.audit_timeline`
- `eva.latest_work_session`

These are local audit/status views. They display sanitized WorkSession records for routed `eva ask` requests and do not execute tools, verifiers, browser/desktop control, shell commands, MCP, package installs, cloud calls, message sends, or broad file actions.

Phase 12S adds read-only readiness/proof capabilities:

- `eva.phase12_ready`
- `eva.phase12_summary`
- `eva.phase12_limits`
- `eva.phase12_proof`

These show checkpoint readiness, limits, and proof commands. They do not run verifier subprocesses or enable any new execution path.

## Permissions

The permission matrix explains whether a capability is read-only, an explicit local write, confirmation-gated, or blocked by default. External sending, browser control, desktop control, MCP execution, Playwright, PyAutoGUI, arbitrary shell, and destructive file actions remain disabled or future-gated.

Commands:

- `eva capability permissions`
- `eva capability permission <capability_id>`

## Resource Mapping

Phase 9D adds a metadata-only bridge:

Capability -> Permission decision -> Resource -> Provider or agent -> Tool schema preview -> Execution availability -> Safety notes

This helps future Planner v3 answer:

- which capability fits a goal
- which resource backs it
- whether it is allowed
- whether it is available now, preview-only, disabled experimental, or reference-only
- which agent would handle it later

Commands:

- `eva capability resolve <capability_id>`
- `eva capability resources <capability_id>`
- `eva resource capabilities <resource_id>`
- `eva capability resource matrix`
- `eva capabilities available`
- `eva capabilities preview only`
- `eva capabilities blocked`
- `eva capability plan resources <goal text>`

## Tool Schema Previews

Tool schema previews describe parameters and execution class for safe existing capabilities. They do not execute tools.

Commands:

- `eva capability schema <capability_id>`
- `eva tool schema preview <capability_id>`
- `eva tool schemas`

## Public vs Private Mode

Public/community mode keeps high-risk systems disabled. Private/local development may expose more metadata, but Phase 9D does not enable risky execution in either mode.

Current non-enabled surfaces:

- MCP execution
- Playwright execution
- PyAutoGUI execution
- browser control
- screen watching
- WhatsApp sending
- arbitrary shell
- cloud embeddings
- default vector search
- normal-chat routing through Eva v2

## Examples

`eva capability resolve research_memory.retrieve` shows the Research Memory resource, permission status, ResearchAgent ownership, schema-preview availability, and `available_read_only` status.

`eva capability resolve research_memory.vector_search` shows that the vector index resource is experimental and disabled by default. Lexical Research Memory retrieval remains primary.

`eva resource capabilities eva-research-memory-v2` lists the capabilities backed by the local Research Memory v2 store.

`eva capability resolve file.preview_text` shows the FileAgent resource, read-only permission status, schema-preview availability, and project-scoped path safety notes.

`eva capability resolve file.project_inventory` shows the FileAgent project inventory capability. It is available only through explicit read-only commands and still skips secrets, runtime data, and whole-drive paths.

`eva capability resolve file.draft_create_preview` shows the FileAgent draft preview capability. It is preview-only: proposed content is shown in chat output and no file is created or modified.

`eva capability resolve file.apply_readiness` shows the FileAgent future-write safety capability. It is preview-only: Eva can explain confirmation, backup, rollback, and verification requirements, but cannot apply the change.

`eva capability resolve file.approval_request_create` shows the FileAgent approval-ledger capability. It is metadata-only: Eva can create a future-apply approval record, but cannot write, back up, restore, or apply files.

`eva capability resolve file.sandbox_apply_approved` shows the FileAgent sandbox executor capability. It can apply an approved record only inside ignored runtime sandbox storage, with sandbox-only backup, verification, and rollback. It is not real project file apply.

`eva capability resolve eva.ask` shows the Phase 12G natural-language wrapper. It is a local router over existing safe commands, not a new executor.

`eva capability resolve eva.authority_status` shows the global authority spine status. Authority decisions are human-readable summaries and do not execute tools by themselves.

`eva capability resolve eva.control_center_status` shows the Phase 12H Control Center status capability. It is read-only and summarizes authority, routing, FileAgent, approvals, sandbox apply, capabilities, agents, planner, verifiers, safety boundaries, and locked future modules.

`eva capability resolve eva.dashboard_url` shows the local dashboard URL capability. It prints `http://127.0.0.1:8765/control` but does not open a browser or use browser automation.

`eva capability resolve eva.audit_timeline` shows the Phase 12Q local audit timeline capability. It reads only WorkSession metadata and does not execute the underlying workflow.

`eva capability resolve file.real_create_new_text_file` shows the Phase 12L narrow real apply capability. It is a high-risk local write capability, disabled by default in public mode, and requires exact approval confirmation. It can create only a brand-new `.md` or `.txt` file in `docs/` or `samples/`.

`eva capability resolve file.real_rollback_new_text_file` shows the controlled rollback capability. It can remove only an unchanged Eva-created file from the Phase 12L gate after exact rollback confirmation.

`eva capability resolve eva.golden_workflow_project_note` shows the Phase 12J golden workflow capability. It orchestrates draft, approval, sandbox, narrow real-create eligibility, exact confirmation, verification, and rollback guidance through FileAgent. It is not broad write permission.

`eva capability resolve eva.golden_workflows_status` shows current golden workflow status and the next safe action.

`eva capability resolve eva.golden_workflow_test_plan` and `eva capability resolve eva.golden_workflow_proof` show the Phase 12R E2E golden workflow status/proof surfaces. They are read-only evidence views and do not execute workflow steps.

`eva capability resolve eva.smoke_status` shows the Phase 12K smoke/quick verification status capability. It is read-only and does not run verifiers from chat.

`eva capability resolve eva.verify_quick_command` and `eva capability resolve eva.verify_full_command` show manual-command surfaces. They print the exact local verifier commands and do not execute shell commands.

`eva capability resolve eva.phase12_status` and `eva capability resolve eva.ux_status` show the Phase 12 status and command UX status surfaces.

`eva capability resolve eva.phase12_ready`, `eva.phase12_summary`, `eva.phase12_limits`, and `eva.phase12_proof` show Phase 12S checkpoint readiness, summary, limits, and proof surfaces. They are read-only metadata views and do not run verifier subprocesses.

`eva capability resolve eva.specialists_status`, `eva capability resolve eva.skill_select`, and `eva capability resolve eva.workflow_plan` show the Phase 12M specialist/skill workflow foundation. These capabilities are route metadata and workflow previews only.

`eva capability resolve eva.fileagent_project_note_workflow` shows the project-note workflow plan. It describes the FileAgent draft, approval, sandbox, Phase 12L narrow real-create, verification, and rollback sequence without executing the steps.

`eva capability resolve eva.workflow_state`, `eva.workflow_next_step`, `eva.workflow_latest_approval`, `eva.workflow_latest_apply`, `eva.workflow_disambiguate`, and `eva.file_latest_status` show Phase 12N latest-state workflow capabilities. They are read-only/status surfaces and do not execute workflow steps.

`eva capability resolve browser.status` shows the Phase 13A BrowserAgent safety status capability. It is read-only and reports that real browser control is locked.

`eva capability resolve browser.policy`, `browser.blocked_actions`, `browser.domain_policy`, `browser.action_safety_preview`, and `browser.readiness` show BrowserAgent policy/readiness previews. These capabilities do not launch Chrome, navigate pages, click, type, submit forms, automate login/payment/upload/download, read cookies/localStorage/browser profiles, take screenshots, enable Playwright/browser-use/Stagehand/Maxun, enable MCP, enable PyAutoGUI, run shell commands, install packages, or call cloud services.

`eva capability resolve browser.session_status`, `browser.session_preview`, `browser.sessions_list`, `browser.session_plan`, and `browser.session_readiness` show Phase 13B Browser Session Preview surfaces. They can create and list local preview-only records and explain readiness, but they do not create a real browser session or read browser/page state.

`eva capability resolve browser.page_summary_policy`, `browser.page_summary_preview`, `browser.dom_summary_policy`, `browser.text_extraction_policy`, `browser.observation_readiness`, and `browser.redaction_policy` show Phase 13C BrowserAgent page/text/DOM summary design surfaces. They can describe future extraction schemas and redaction rules or preview summaries from mock text, but they do not read live pages, DOM, screenshots, cookies, localStorage, browser profiles, sessions, passwords, or tokens.

`eva capability resolve browser.action_dry_run`, `browser.action_plan_preview`, `browser.action_risk`, `browser.action_approvals`, `browser.dry_run_policy`, and `browser.action_readiness` show Phase 13D BrowserAgent action dry-run surfaces. They can classify risk and describe what would happen, but they do not execute browser launch, navigation, click, type, submit, login, payment, upload, download, screenshot, DOM, or live page actions.

`eva capability resolve browser.domain_check`, `browser.site_risk`, `browser.domain_rules`, `browser.sensitive_sites`, `browser.domain_approvals`, and `browser.domain_readiness` show Phase 13E BrowserAgent domain/site-risk policy surfaces. They classify provided domain strings and explain sensitive categories or future approvals, but they do not perform DNS/network calls, launch browsers, navigate, fetch pages, read DOM, take screenshots, read cookies/localStorage/profile/session/password/token data, or execute Playwright/browser-use/Stagehand/Maxun/MCP/PyAutoGUI/shell/package/cloud actions.

`eva capability resolve browser.readonly_readiness`, `browser.readiness_proof`, `browser.safety_proof`, `browser.readiness_gaps`, `browser.locked_status`, and `browser.phase13_proof` show Phase 13F BrowserAgent read-only readiness proof surfaces. They prove the current BrowserAgent safety layers exist and list future gaps, but real browser read-only mode remains disabled.

`eva capability resolve browser.phase13_status`, `browser.phase13_summary`, `browser.phase13_limits`, `browser.phase13_ready`, and `browser.phase13_final_proof` show Phase 13G BrowserAgent hardening surfaces. They are read-only proof/status capabilities. They state that Phase 13 is safety/readiness only, real browser read-only mode is not enabled, real browser control is not enabled, network/DNS/live page read/DOM/screenshot/action execution are locked, future read-only browser mode needs a separate approved gate, and Phase 12L narrow real create remains a gated write path.

`eva capability resolve desktop.status`, `desktop.policy`, `desktop.blocked_actions`, `desktop.action_safety_preview`, `desktop.app_risk`, and `desktop.readiness` show Phase 14A DesktopAgent safety surfaces. They are read-only status/policy capabilities. They do not capture screens, take screenshots, inspect windows/apps, launch apps, move/click/type, use hotkeys, access clipboard, automate file dialogs, run terminal/package commands, send messages, call cloud services, enable PyAutoGUI/Playwright/MCP, or broaden real writes beyond Phase 12L.

`eva capability resolve desktop.session_status`, `desktop.sessions_list`, `desktop.session_preview`, `desktop.session_plan`, `desktop.app_status_preview`, `desktop.window_status_preview`, `desktop.active_context_preview`, and `desktop.observation_readiness` show Phase 14B DesktopAgent session/app/window preview surfaces. They are read-only status/preview capabilities. They can create local in-memory preview records and show future app/window/active-context schemas, but they do not capture screens, take screenshots, enumerate windows, inspect apps, detect active apps, launch apps, move/click/type, use hotkeys, access clipboard, automate file dialogs, run terminal/package commands, send messages, call cloud services, enable PyAutoGUI/Playwright/MCP, or broaden real writes beyond Phase 12L.

`eva capability resolve desktop.screen_policy`, `desktop.screen_observation_policy`, `desktop.sensitive_screens`, `desktop.screen_redaction_policy`, `desktop.screen_capture_gate`, `desktop.screen_readiness`, and `desktop.observation_policy` show Phase 14C DesktopAgent screen observation policy surfaces. They are read-only status/policy capabilities. They explain sensitive-screen categories, future redaction, capture gate requirements, and readiness gaps, but they do not capture screens, take screenshots, run OCR or image analysis, inspect windows/apps, detect active apps, launch apps, move/click/type, access clipboard, run terminal/package commands, send messages, call cloud services, enable PyAutoGUI/Playwright/MCP, or broaden real writes beyond Phase 12L.

`eva capability resolve desktop.action_dry_run`, `desktop.action_plan_preview`, `desktop.action_risk`, `desktop.action_approvals`, `desktop.dry_run_policy`, and `desktop.action_readiness` show Phase 14D Desktop Action Dry-Run surfaces. They can classify desktop action risk and describe what would happen, but they do not execute mouse movement/click/drag, keyboard typing/hotkeys, clipboard reads/writes, app launch/focus, file dialog automation, screen capture, screenshots, terminal/package commands, browser/network calls, PyAutoGUI/Playwright/MCP, cloud calls, or normal-chat desktop execution.

`eva capability resolve desktop.risk_score`, `desktop.risk_factors`, `desktop.approval_required`, `desktop.safety_matrix`, `desktop.high_risk_actions`, and `desktop.risk_readiness` show Phase 14E Desktop Action Risk Scoring surfaces. They can score request strings, explain risk factors, show future approval levels, and list forbidden action classes, but they do not observe screens, inspect windows/apps, launch apps, move/click/type, use hotkeys, access clipboard, automate file dialogs, run terminal/package commands, call browser/network/cloud services, enable PyAutoGUI/Playwright/MCP, or broaden real writes beyond Phase 12L.

`eva capability resolve desktop.approval_policy`, `desktop.approval_levels`, `desktop.approval_preview`, `desktop.confirmation_phrase`, `desktop.forbidden_actions`, `desktop.approval_audit_status`, and `desktop.approval_readiness` show Phase 14F Desktop Human Approval Model surfaces. They can explain approval levels, phrase previews, forbidden classes, and audit/status readiness, but approvals do not unlock real desktop execution.

`eva capability resolve desktop.phase14_status`, `desktop.phase14_summary`, `desktop.phase14_limits`, `desktop.phase14_ready`, `desktop.phase14_final_proof`, `desktop.readiness_proof`, `desktop.locked_status`, and `desktop.readiness_gaps` show Phase 14G DesktopAgent Locked Readiness Proof surfaces. They are read-only proof/status capabilities and confirm that approvals do not unlock real desktop observation or control.

`eva capability resolve llm.status`, `llm.providers`, `llm.routing_policy`, `llm.fallback_policy`, `llm.limits`, `llm.structured_output`, `llm.route_preview`, and `llm.readiness` show Phase 15A LLM Router Interface + Provider Contract surfaces. They are mock/dry-run metadata only: live LLM/API/network calls, provider SDK use, secret/config reads, and tool execution remain locked.

Phase 15B fallback, degraded-mode, limits, runaway-protection, failure-mode, and routing-audit surfaces are deterministic mock/dry-run only. They simulate policies without provider SDKs, `.env`/secret/config reads, live calls, or LLM-output tool execution. Browser/desktop execution remains locked; Phase 12L narrow real create remains a gated write path. Next: Phase 15C Structured Output Validation Hardening.

## Phase 15C Structured Output Validation Hardening

Phase 15C is complete as a mock/local-only validation surface. The read-only capabilities are `llm.validation_status`, `llm.schema_registry`, `llm.validation_policy`, `llm.repair_policy`, `llm.validate_mock`, `llm.validate_invalid_examples`, and `llm.validation_readiness`. They expose status, policy, and refusal-preview evidence only: live LLM/API calls remain locked, provider SDKs and secret/config/session reads are not used, invalid LLM output cannot execute tools, repair does not execute or rewrite user intent, and hallucinated, secret-like, or private-path-like output is rejected. Browser/desktop execution remains locked; Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next: Phase 15D LLM Router Red-Team/Failure Tests.

## Scope

## Phase 15D LLM Router Red-Team / Failure Tests

Phase 15D is complete. `llm.red_team_status`, `llm.red_team_cases`, `llm.red_team_run`, `llm.failure_tests`, `llm.safety_failure_report`, and `llm.red_team_readiness` are local/mock report-only surfaces. They use no live LLM/API/provider call or SDK; read no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets; and keep tool, browser, desktop, shell, cloud, and MCP execution locked. Unsafe LLM-like output—including prompt injection, hallucinated capabilities, secret exfiltration, oversized output, malformed JSON, and command-injection-looking text—fails safely. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next: Phase 16 Context Assembly Engine.

Phase 15E adds a deterministic local/mock evidence lock over that catalog. It records expected safe classifications and fails verification on omissions, unknown/duplicate IDs, unsafe allows, or outcome mismatches; it does not add provider integration, execution, or writes.

## Phase 16 Context Assembly Engine

Phase 16 Context Assembly Engine is complete after this pass. `context.status`, `context.sources`, `context.policy`, `context.budget`, `context.assemble_preview`, `context.grounding_report`, `context.redaction_policy`, and `context.readiness` are local/mock preview only. They perform no live LLM/API/provider calls, use no provider SDKs, read no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets, and arbitrary file reads are blocked. Context is source-aware, budget-aware, redaction-aware, permission-aware, and grounding-aware. Prompt-injection-like content is not trusted as instruction, assembled context cannot execute tools, and browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next phase is Phase 17 LLM Threat Defense + Prompt Injection Guard.

## Phase 17 LLM Threat Defense + Prompt Injection Guard

Phase 17 LLM Threat Defense + Prompt Injection Guard is complete after this pass. `threat.status`, `threat.catalog`, `threat.policy`, `threat.scan_preview`, `threat.injection_examples`, `threat.exfiltration_examples`, `threat.context_guard`, and `threat.readiness` are local/mock preview only. They perform no live LLM/API/provider calls, no provider SDKs are used, read no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets, and arbitrary file reads are blocked. untrusted context cannot override trusted policy/instruction hierarchy. prompt-injection-like content is treated as untrusted data, defended context cannot execute tools, and exfiltration and tool-request attempts fail safely. Browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next phase is Phase 18 Agent Loop v1.

## Phase 18 Agent Loop v1

Phase 18 Agent Loop v1 is complete after this pass. `agent_loop.status`, `agent_loop.policy`, `agent_loop.run_preview`, `agent_loop.steps`, `agent_loop.action_previews`, `agent_loop.safety_report`, `agent_loop.stop_reasons`, and `agent_loop.readiness` are local/mock preview only. They perform no live LLM/API/provider calls, no provider SDKs are used, read no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets, and arbitrary file reads are blocked. all actions are preview-only, agent loop cannot execute tools, and browser/desktop/shell/cloud/MCP execution remains locked. step limits, runaway detection, repeated-step detection, and no-progress stop behavior are enforced. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next phase is Phase 19 Agentic Workflow Planner.

## Phase 19 Agentic Workflow Planner

Phase 19 Agentic Workflow Planner is complete after this pass. `workflow_planner.status`, `workflow_planner.catalog`, `workflow_planner.policy`, `workflow_planner.preview`, `workflow_planner.dependencies`, `workflow_planner.approvals`, `workflow_planner.rollback`, and `workflow_planner.readiness` are local/mock preview only. They perform no live LLM/API/provider calls, no provider SDKs are used, read no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets, and arbitrary file reads/writes are blocked. all workflow steps are preview-only, workflow planner cannot execute tools, and browser/desktop/shell/cloud/MCP execution remains locked. workflow dependency validation, precondition checks, approval previews, rollback previews, and verification plans are implemented. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next phase is Phase 20 Controlled Execution Gates.

## Phase 20 Controlled Execution Gates

Phase 20 Controlled Execution Gates is complete after this pass. `execution_gates.status`, `execution_gates.policy`, `execution_gates.evaluate`, `execution_gates.approvals`, `execution_gates.confirmations`, `execution_gates.rollback`, `execution_gates.blocked_actions`, and `execution_gates.readiness` are local/mock policy preview only. execution gates are local/mock policy preview only. no live LLM/API/provider calls happen, no provider SDKs are used, and no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. tools are not executed. approval alone does not execute. confirmation alone does not execute unless an existing implemented gate accepts it. browser/desktop/shell/cloud/MCP execution remains locked. future gates are described but locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next phase is Phase 21 Memory v3.

## Phase 21 Memory v3

Phase 21 Memory v3 adds local status, policy, source, privacy, freshness, conflict, retrieval-preview, and readiness capabilities. Memory v3 is local-only; no live LLM/API/provider calls happen; no provider SDKs are used; no cloud memory or remote sync is used; no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read; raw memory database dumps are blocked; arbitrary file reads/writes are blocked. memory is source-aware, trust-aware, freshness-aware, privacy-aware, conflict-aware, and grounding-aware. memory cannot override system/developer/safety policy; memory cannot execute tools. sensitive, injected, stale, conflicting, or ungrounded memories are excluded or marked. context injection is preview/policy only. browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 22 Voice Assistant.

## Phase 22 Voice Assistant Foundation

Phase 22 Voice Assistant Foundation is complete after this pass and adds `voice.status`, `voice.policy`, `voice.providers`, `voice.listen_state`, `voice.transcript_safety`, `voice.route_preview`, `voice.confirmations`, and `voice.readiness`. voice is local/mock preview only; no microphone access, audio recording, or audio playback happens; no live ASR/TTS/provider calls happen; no provider SDKs are used; no real LLM/API/provider calls happen; no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read; arbitrary file reads/writes are blocked; voice commands cannot execute tools. transcript safety, provider policy, wake/listen state policy, and confirmation preview are implemented. browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 23 AI OS / Control Center Upgrade.

## Phase 23 AI OS / Control Center Upgrade

Phase 23 AI OS / Control Center Upgrade is complete after this pass and adds nine `ai_os.*` read/status capabilities for status, dashboard, system map, capability matrix, feature states, safety boundaries, locked features, next safe step, and readiness. AI OS dashboard is local/status/report only; no live LLM/API/provider calls happen; no provider SDKs are used; no web server, browser launch, desktop UI launch, or daemon is created; no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read; arbitrary file reads/writes are blocked; AI OS dashboard cannot execute tools. preview-only features remain preview-only; locked future gates remain locked; browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 24 Real Browser Read-Only Mode.

This layer is metadata/discovery plus explicit sandbox-only FileAgent harness commands, the Phase 12G natural-language wrapper, the Phase 12H read-only Control Center dashboard, the Phase 12L create-new-text-file gate, Phase 12J golden workflow orchestration, Phase 12K smoke/profile verification status, Phase 12M specialist/skill workflow previews, Phase 12N latest-state workflow status, Phase 12Q WorkSession audit/status metadata, Phase 12R golden workflow proof surfaces, Phase 12S readiness/proof summaries, Phase 13A BrowserAgent safety previews, Phase 13B Browser Session Preview records, Phase 13C Browser Observation Preview design, Phase 13D Browser Action Dry-Run previews, Phase 13E Browser Domain Policy + Site Risk previews, Phase 13F Browser Read-Only Readiness Proof, Phase 13G BrowserAgent hardening/final proof surfaces, Phase 14A DesktopAgent safety/status surfaces, Phase 14B DesktopAgent session/app/window preview surfaces, Phase 14C DesktopAgent screen observation policy surfaces, Phase 14D Desktop Action Dry-Run surfaces, Phase 14E Desktop Action Risk Scoring surfaces, and Phase 14F Desktop Human Approval Model surfaces. It does not install packages, call cloud APIs, read secret files, control browsers/desktops, send messages, edit/overwrite/delete/move existing files, write source/config/runtime files, execute shell commands from chat, or execute MCP tools.

## Phase 24 Real Browser Read-Only Mode

Phase 24 Real Browser Read-Only Mode is complete after this pass. It adds `browser_read.status`, `browser_read.policy`, `browser_read.url_policy`, `browser_read.observe`, `browser_read.mock_observe`, `browser_read.safety_report`, `browser_read.blocked_urls`, and `browser_read.readiness`. Browser mode is public-URL read-only observation only: no clicking, typing, forms, downloads, uploads, login, or browser control. There is no logged-in browser profile/session/cookie access, and no provider SDKs or package installs. no real LLM/API/provider calls happen. no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. browser read-only observations cannot execute tools. browser control remains locked; desktop/shell/cloud/MCP execution remains locked. Deterministic mock observation is available, while real URLs return backend unavailable because no pre-existing safe backend exists. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 25 Real Desktop Observation Mode.

## Phase 25 Real Desktop Observation Mode

Phase 25 Real Desktop Observation Mode is complete after this pass. It adds `desktop_observe.status`, `desktop_observe.policy`, `desktop_observe.backend`, `desktop_observe.mock`, `desktop_observe.safety_report`, `desktop_observe.sensitive_screens`, `desktop_observe.redaction_policy`, and `desktop_observe.readiness`. desktop mode is observation-only: no clicking, typing, hotkeys, app/window control, continuous monitoring, or screenshot saving. There is no cookie/session/browser profile/password-manager access, and no provider SDKs or package installs. no real LLM/API/provider calls happen. no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. desktop observations cannot execute tools. sensitive screens are classified and redacted or blocked. browser control remains locked; desktop control remains locked; shell/cloud/MCP execution remains locked. Deterministic mock observation is available, while real desktop observation returns backend unavailable because no pre-existing safe backend exists. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 26 Real Desktop Control Gate.

## Phase 26 Real Desktop Control Gate

Phase 26 Real Desktop Control Gate is complete after this pass. It adds `desktop_control.status`, `desktop_control.policy`, `desktop_control.actions`, `desktop_control.dry_run`, `desktop_control.approvals`, `desktop_control.confirmations`, `desktop_control.blocked_actions`, and `desktop_control.readiness`. desktop control is dry-run/gate-only: no clicking, typing, hotkeys, clipboard, app/window control, automation, or shell execution happens. no provider SDKs or package installs were added; no real LLM/API/provider calls happen. no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. approval alone does not execute. confirmation alone does not execute. rollback/audit are metadata only. desktop observation remains observation-only; browser control remains locked; shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 27 News/Web Intelligence Dashboard.

## Phase 27 News / Web Intelligence Dashboard
Phase 27 News / Web Intelligence Dashboard is complete after this pass. It adds eight `news.*` dashboard/report/status capabilities. dashboard is local/mock by default. No unrestricted crawling, login scraping, session/cookie/profile access, or browser control is enabled. Source freshness, reliability, uncertainty, and citation metadata are tracked; Phase 24 public URL read-only policy is respected. No provider SDKs, package installs, real LLM/API/provider calls, secret/config/session reads, arbitrary file reads/writes, tool execution, or browser/desktop/shell/cloud/MCP execution was added. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 28 Coding Specialist / CodingAgent.

## Phase 28 Coding Specialist / CodingAgent Foundation

Phase 28 Coding Specialist / CodingAgent Foundation is complete after this pass. It adds twelve read/status capabilities under `coding.*` for status, policy, specialist catalog, task classification, safe project context, patch-plan preview, review checklist, test-plan preview, risk review, handoff, blocked actions, and readiness. Every capability is deterministic local preview/report/status only.

No source edit, patch application, arbitrary code execution, shell/test/package/git operation, arbitrary filesystem read/write, tool execution, provider SDK, package install, or real LLM/API/provider call is enabled. Secret/config/session and raw private dumps remain blocked. Browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 29 Public Demo / Release.

## Phase 29 Public Demo / Release

Phase 29 Public Demo / Release is complete after this pass. It adds eight read/status capabilities under `release.*` for status, demo profile, command guide, capability map, safety proof, readiness, limitations, and verification guidance. Every capability returns deterministic local demo/report/status text only.

No publishing, uploading, package release, installer creation, commit, tag, push, source edit, shell/test/package/git execution, arbitrary filesystem access, live provider call, or tool execution is enabled. Secret/config/session and raw private dumps remain blocked. Browser/desktop/shell/cloud/MCP execution remains locked. CodingAgent, News Dashboard, and Voice retain their Phase 28/27/22 boundaries. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path.

Phase 29 handed off to Phase 30 Release Candidate Hardening. The current next safe step is user-approved commit execution outside Eva or a separate explicit commit-approval phase.

## Phase 33-42 Roadmap Foundations

Phase 33 Execution Boundary Audit is complete as a foundation after this pass. It adds report/status/catalog capabilities for the Phase 33 through Phase 42 improvement roadmap.

New roadmap capabilities:

- `roadmap.execution_boundary_audit`: classify risky runtime surfaces and existing gates.
- `roadmap.command_catalog`: expose command descriptors before deeper router decomposition.
- `roadmap.capability_catalog`: expose shared capability descriptors for docs, planner, resources, schemas, and verifiers.
- `roadmap.control_truth_panels`: track Control Center and AI OS truth-panel work.
- `roadmap.frontend_truth`: track safe demo UI labels and quick chips.
- `roadmap.grounded_answers`: track deterministic catalog-backed answers for Eva capability/architecture questions.
- `roadmap.voice_reliability`: track voice lifecycle and diagnostics work.
- `roadmap.verifier_dashboard`: track verifier metadata and profile reporting.
- `roadmap.safe_real_pilot`: remains blocked until later explicit approval.
- `roadmap.release_candidate_v2`: records Phase 42 hardening as documentation/verification only.

Execution boundary audit status: no new execution path is enabled. These capabilities are report/status/catalog only, except `roadmap.safe_real_pilot`, which is blocked until a later explicit approval phase. Phase 42 does not tag, release, upload, publish, package, deploy, or push anything.

No provider SDKs or package installs were added. No real LLM/API/provider calls happen. No `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config contents are read. Browser/desktop/shell/cloud/MCP execution remains locked. CodingAgent remains preview/report/status only. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path.
