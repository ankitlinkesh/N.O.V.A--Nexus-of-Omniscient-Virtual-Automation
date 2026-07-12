# Eva Verification

Phase 12K adds a fast verification entrypoint for local Eva development.

Phase 12L adds `scripts/verify_eva_file_agent_real_apply_gate.py` for the narrow create-new-text-file real apply gate.

Phase 12O adds `scripts/verify_eva_project_reality_workflow.py` for project inspection, proof/done checks, broken-status wording, natural `eva ask` routing, capabilities, planner/team review, and Control Center project/reality summaries.

Phase 12P adds `scripts/verify_eva_control_center_v1.py` for the upgraded Control Center summaries, locked/enabled feature commands, natural `eva ask` routing, capabilities, planner/team review, and status-only safety boundaries.

Phase 12Q adds `scripts/verify_eva_work_sessions_audit.py` for local WorkSession creation, sanitized timeline events, `eva ask` audit logging, Control Center WorkSession panels, capability/schema/resource metadata, planner/team review integration, and forbidden-execution checks.

Phase 12R adds `scripts/verify_eva_golden_workflow_e2e.py` for the natural FileAgent project-note workflow across approval, sandbox, exact Phase 12L real create, verification, WorkSession timeline, Control Center status, and guarded rollback.

Phase 12S adds `scripts/verify_eva_phase12_ready.py` for final readiness, summary, limits, proof commands, capability/resource/schema metadata, planner/team-review routing, and clean status output.

## Commands

Quick smoke profile:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --quick
```

Full profile:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --full
```

List profiles:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --list
```

Optional per-script timeout:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --quick --timeout 90
```

## Profiles

The quick profile runs only the fast Phase 12 smoke checks, golden workflow checks, and Control Center checks.

The full profile runs the broader Phase 12/FileAgent/planner verifier set. It is meant for checkpoint readiness.

The full profile includes the Phase 12O project/reality workflow verifier and the Phase 12P Control Center verifier.

The full profile includes the Phase 12R golden workflow E2E verifier.

The full and quick profiles include the Phase 12L real apply verifier. That verifier creates only isolated test `.md`/`.txt` files under allowed safe folders and removes only files it created.

## Chat Status

Eva can show verification status and manual commands:

- `eva smoke status`
- `eva verify quick command`
- `eva verify full command`
- `eva phase 12 status`
- `eva phase 12 ready`
- `eva phase 12 summary`
- `eva phase 12 limits`
- `eva phase 12 proof`
- `eva ux status`
- `eva project inspect`
- `eva project reality check`
- `eva project proof`
- `eva done check`
- `eva control center`
- `eva control center summary`
- `eva locked features`
- `eva enabled features`
- `eva sessions status`
- `eva sessions recent`
- `eva session latest`
- `eva audit timeline`
- `eva work status`
- `eva workflow golden proof`
- `eva workflow golden test plan`
- `eva next safe step`
- `eva ask run quick check`
- `eva ask how do I verify Eva`

These commands do not run shell commands from chat. They only return friendly status text or the command for the user/developer to run manually.

## Control Center

The Control Center has a Phase 12 Health / Verification section. It shows the smoke verifier, quick/full commands, latest dashboard-local status, project/reality summary, workflow state, WorkSession audit status, enabled real action, locked features, and next safe step. The dashboard does not run verifiers automatically.

The Phase 12S readiness commands show the same proof posture from chat: readiness is a status claim until the quick/full verifier commands pass in the current terminal. These commands print evidence surfaces and manual commands only; they do not execute subprocesses.

## Safety Boundary

Verification UX and WorkSession audit UX do not enable MCP, Playwright, PyAutoGUI, browser control, desktop control, screen watching, terminal execution, package installs, cloud calls, external sending, or broad file writes. Phase 12L real apply remains limited to approved create-new-text-file operations under `docs/` or `samples/`.

# Phase 13A BrowserAgent Safety

BrowserAgent safety verification is covered by:

- `scripts/verify_eva_browser_agent_safety.py`
- `scripts/verify_eva_all.py --quick`
- `scripts/verify_eva_all.py --full`

The verifier checks that BrowserAgent commands are policy/status only, risky browser actions are blocked, Control Center shows real browser control as locked, capability/resource/schema surfaces exist, and no Playwright/browser-use/Stagehand/Maxun execution, MCP, PyAutoGUI, browser control, desktop control, shell/package/cloud calls, cookie/localStorage/profile reads, screenshots, or screen watching are enabled.

# Phase 13B Browser Session Preview

Browser session preview verification is covered by:

- `scripts/verify_eva_browser_session_preview.py`
- `scripts/verify_eva_all.py --quick`
- `scripts/verify_eva_all.py --full`

The verifier checks preview-only session records, latest/list/status outputs, `eva ask` routing, Control Center Browser Session Preview panel, capabilities/resource/schema surfaces, planner/team-review routing, and that no real browser launch/navigation/screenshot/DOM/click/type/form/upload/download/session-read execution is enabled.

# Phase 13C Browser Page/Text/DOM Summary Design

Browser observation design verification is covered by:

- `scripts/verify_eva_browser_page_summary_design.py`
- `scripts/verify_eva_all.py --quick`
- `scripts/verify_eva_all.py --full`

The verifier checks page/text/DOM preview schemas, redaction policy, live-read/DOM/screenshot locks, commands, `eva ask` routing, Control Center Browser Observation Preview panel, capabilities/resource/schema surfaces, planner/team-review routing, and that no real browser observation/control, screenshots, DOM access, Playwright/browser-use/Stagehand/Maxun, MCP, PyAutoGUI, shell/package/cloud calls, cookies, localStorage, browser profiles, sessions, passwords, or tokens are enabled.

# Phase 13D Browser Action Dry-Run

Browser action dry-run verification is covered by:

- `scripts/verify_eva_browser_action_dry_run.py`
- `scripts/verify_eva_all.py --quick`
- `scripts/verify_eva_all.py --full`

The verifier checks dry-run plans, risk levels, approval requirements, commands, `eva ask` routing, Control Center Browser Action Dry-Run panel, capabilities/resource/schema surfaces, planner/team-review routing, roadmap order, and that no real browser execution/observation/control, screenshots, DOM access, Playwright/browser-use/Stagehand/Maxun, MCP, PyAutoGUI, shell/package/cloud calls, cookies, localStorage, browser profiles, sessions, passwords, or tokens are enabled.

# Phase 13E Browser Domain Policy + Site Risk

Browser domain policy verification is covered by:

- `scripts/verify_eva_browser_domain_policy.py`
- `scripts/verify_eva_all.py --quick`
- `scripts/verify_eva_all.py --full`

The verifier checks string-only domain/site-risk classification, sensitive categories, future approval wording, commands, `eva ask` routing, Control Center Browser Domain Risk panel, capabilities/resource/schema surfaces, planner/team-review routing, and that no DNS/network call, real browser execution/observation/control, screenshots, DOM access, Playwright/browser-use/Stagehand/Maxun, MCP, PyAutoGUI, shell/package/cloud calls, cookies, localStorage, browser profiles, sessions, passwords, or tokens are enabled.

# Phase 13F Browser Read-Only Readiness Proof

Browser read-only readiness proof verification is covered by:

- `scripts/verify_eva_browser_readiness_proof.py`
- `scripts/verify_eva_all.py --quick`
- `scripts/verify_eva_all.py --full`

The verifier checks the proof checklist over safety, session preview, observation/page summary design, action dry-run, and domain/site-risk layers; commands; `eva ask` routing; Control Center Browser Read-Only Readiness Proof panel; capabilities/resource/schema surfaces; planner/team-review routing; and that no real browser read-only mode, DNS/network call, browser launch/navigation, live page read, screenshot, DOM access, Playwright/browser-use/Stagehand/Maxun, MCP, PyAutoGUI, shell/package/cloud call, cookie, localStorage, browser profile, session, password, or token access is enabled.

# Phase 13G BrowserAgent Hardening

BrowserAgent Phase 13 hardening verification is covered by:

- `scripts/verify_eva_browser_phase13_hardening.py`
- `scripts/verify_eva_all.py --quick`
- `scripts/verify_eva_all.py --full`

The verifier checks final Phase 13 status, summary, limits, readiness, and final-proof commands; `eva ask` routing; Control Center agreement; capabilities/resource/schema surfaces; planner/team-review routing; and that real browser read-only mode, browser control, network/DNS, live page reads, DOM reads, screenshots, action execution, Playwright/browser-use/Stagehand/Maxun, MCP, PyAutoGUI, shell/package/cloud calls, cookies, localStorage, browser profiles, sessions, passwords, and tokens remain locked. Phase 12L narrow real create remains a gated write path.

# Phase 14A DesktopAgent Safety

DesktopAgent safety verification is covered by:

- `scripts/verify_eva_desktop_agent_safety.py`
- `scripts/verify_eva_all.py --quick`
- `scripts/verify_eva_all.py --full`

The verifier checks DesktopAgent imports, status/policy output, blocked risky desktop actions, app-risk string classification, direct commands, `eva ask` routing, Control Center DesktopAgent panel, capabilities/resource/schema surfaces, planner/team-review routing, and that no screen capture, screenshots, window/app inspection, app launch, mouse/keyboard/clipboard/file-dialog automation, terminal/package execution, PyAutoGUI, Playwright, MCP, browser/desktop execution, shell/package/cloud calls, secrets, tokens, private desktop state, or browser sessions are read or enabled.

# Phase 14B Desktop Session Preview

Desktop session/app/window preview verification is covered by:

- `scripts/verify_eva_desktop_session_preview.py`
- `scripts/verify_eva_all.py --quick`
- `scripts/verify_eva_all.py --full`

The verifier checks preview-only desktop session records, latest/list status, app/window/active-context schema previews, direct commands, `eva ask` routing, Control Center Desktop Session Preview panel, capabilities/resource/schema surfaces, planner/team-review routing, and that no real screen capture, screenshot, window enumeration, app inspection, active app detection, app launch, mouse/keyboard/clipboard/file-dialog automation, terminal/package execution, PyAutoGUI, Playwright, MCP, browser/desktop execution, shell/package/cloud calls, secrets, tokens, cookies, passwords, private desktop state, or browser sessions are read or enabled.

# Phase 14C Desktop Screen Observation Policy

Desktop screen observation policy verification is covered by:

- `scripts/verify_eva_desktop_screen_observation_policy.py`
- `scripts/verify_eva_all.py --quick`
- `scripts/verify_eva_all.py --full`

The verifier checks screen policy modules, sensitive-screen categories, redaction policy, capture gate, readiness gaps, direct commands, `eva ask` routing, Control Center Desktop Screen Observation Policy panel, capabilities/resource/schema surfaces, planner/team-review routing, and that no real screen capture, screenshots, OCR, image analysis, window/app inspection, active app detection, PyAutoGUI, Playwright, MCP, browser/desktop execution, shell/package/cloud calls, secrets, tokens, cookies, passwords, private desktop state, or browser sessions are read or enabled.

# Phase 14D Desktop Action Dry-Run

Desktop action dry-run verification is covered by:

- `scripts/verify_eva_desktop_action_dry_run.py`
- `scripts/verify_eva_all.py --quick`
- `scripts/verify_eva_all.py --full`

The verifier checks dry-run plans, action risk levels, approval requirements, direct commands, `eva ask` routing, Control Center Desktop Action Dry-Run panel, capabilities/resource/schema surfaces, planner/team-review routing, and that no real desktop control, screen capture, screenshots, app/window inspection, app launch/focus, mouse movement/click/drag, keyboard typing/hotkeys, clipboard access, file dialog automation, terminal/package execution, PyAutoGUI, Playwright, MCP, browser/network/cloud calls, secrets, tokens, cookies, passwords, private desktop state, or browser sessions are read or enabled.

# Phase 14E Desktop Action Risk Scoring

Desktop action risk scoring verification is covered by:

- `scripts/verify_eva_desktop_action_risk_scoring.py`
- `scripts/verify_eva_all.py --quick`
- `scripts/verify_eva_all.py --full`

The verifier checks risk scoring modules, human-readable output, safety matrix decisions, approval requirements, direct commands, `eva ask` routing, Control Center Desktop Action Risk Scoring panel, capabilities/resource/schema surfaces, planner/team-review routing, and that no real desktop observation/control, screen capture, screenshots, OCR/image analysis, window/app inspection, app launch, mouse/keyboard/clipboard/file-dialog automation, terminal/package execution, PyAutoGUI, Playwright, MCP, browser/network/cloud calls, `.env` reads, secrets, tokens, cookies, passwords, private desktop state, or browser sessions are read or enabled.
# Phase 14F Desktop Human Approval Model

Desktop Human Approval Model verification is covered by:

- `scripts/verify_eva_desktop_approval_model.py`
- `scripts/verify_eva_all.py --quick`
- `scripts/verify_eva_all.py --full`

The verifier checks approval model modules, approval levels, confirmation phrase previews, forbidden action classes, audit schema/status, direct commands, `eva ask` routing, Control Center Desktop Human Approval Model panel, capabilities/resource/schema surfaces, planner/team-review routing, docs, and that approval phrases do not unlock real desktop execution or enable screen observation, window/app inspection, mouse/keyboard/clipboard/file-dialog automation, terminal/package execution, PyAutoGUI, Playwright, MCP, browser/network/cloud calls, secret reads, private desktop state, or browser sessions.

# Phase 14G DesktopAgent Locked Readiness Proof

DesktopAgent final-proof verification is covered by:

- `scripts/verify_eva_desktop_phase14_readiness.py`
- `scripts/verify_eva_all.py --quick --timeout 90`
- `scripts/verify_eva_all.py --full --timeout 90`

The verifier checks the final readiness models, proof output, direct commands, `eva ask` routing, Control Center panel, capability/resource/schema metadata, planner/team-review routing, the Phase 15 intelligence-spine handoff, and the locked boundary: approvals do not unlock execution, real desktop observation/control remains disabled, real browser/network execution remains disabled, and Phase 12L narrow real create remains a gated write path.

# Phase 15A LLM Router Interface + Provider Contracts

LLM router contract verification is covered by:

- `scripts/verify_eva_llm_router_contracts.py`
- `scripts/verify_eva_all.py --quick --timeout 90`
- `scripts/verify_eva_all.py --full --timeout 90`

The verifier checks provider metadata, mock-only route preview, fallback/limit/degraded-mode policy, mock structured-output validation, direct commands, `eva ask` routing, Control Center, capability/resource/schema metadata, and planner/team-review routing. It also asserts that no live LLM/API/network call, secret/config read, provider SDK, tool execution, browser, desktop, shell, package, MCP, PyAutoGUI, or Playwright execution was added.

Phase 15B verification uses `scripts/verify_eva_llm_router_fallbacks_limits.py` plus the master quick/full profiles. It covers deterministic fallback/degraded/limit/audit simulations and confirms live calls and LLM-output tool execution remain locked before Phase 15C Structured Output Validation Hardening.

# Phase 15C Structured Output Validation Hardening

Phase 15C is complete after the core, command, wiring, and closeout proof passes. Verification includes:

- `scripts/verify_eva_llm_structured_output_core.py`
- `scripts/verify_eva_llm_structured_output_commands.py`
- `scripts/verify_eva_llm_structured_output_wiring.py`
- `scripts/verify_eva_llm_structured_output_closeout.py`
- `scripts/verify_eva_all.py --quick --timeout 90`
- `scripts/verify_eva_all.py --full --timeout 90`

These checks cover mock/local-only validation, blocked malformed/unsafe output, refusal-preview behavior, command and `eva ask` rendering, Control Center/catalog/planner/team-review wiring, docs, and master-profile inclusion. They confirm live LLM/API calls remain locked; no provider SDK, `.env`/`.env.local`, secret, token, cookie, password, or browser-session read is enabled; invalid LLM output cannot execute tools; repair does not execute or rewrite user intent; and browser/desktop execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next: Phase 15D LLM Router Red-Team/Failure Tests.
# Phase 12N Golden Workflow UX

# Phase 15D LLM Router Red-Team / Failure Tests

Phase 15D is complete after `scripts/verify_eva_llm_red_team_failure_tests.py` and the master quick/full profiles pass. The verifier covers local/mock adversarial cases, commands, `eva ask`, Control Center, capability/resource/schema metadata, planner/team-review routing, docs, and master inclusion. It confirms no live LLM/API/provider calls or SDKs, no secret/config/session reads, no tool execution, and no browser/desktop/shell/cloud/MCP execution. Unsafe LLM-like output fails safely; Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next: Phase 16 Context Assembly Engine.

Phase 15E verification uses `scripts/verify_eva_llm_red_team_evidence_lock.py` in both quick and full profiles. It locks expected local/mock safe outcomes and fails on stale, duplicate, missing, mismatched, or unsafe results without enabling a live harness, provider integration, execution, or writes.

# Phase 16 Context Assembly Engine

Phase 16 Context Assembly Engine is complete after `scripts/verify_eva_context_assembly_engine.py` and the master quick/full profiles pass. It is local/mock preview only. The verifier checks imports, source registry, blocked sources, policy, budget, redaction, grounding, packet assembly, commands, `eva ask` routes, Control Center, capabilities/resource mappings/tool schemas, planner/team-review routing, docs, and master-profile inclusion. It confirms no live LLM/API/provider calls happen, no provider SDKs are used, no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read, arbitrary file reads are blocked, prompt-injection-like content is not trusted as instruction, assembled context cannot execute tools, browser/desktop/shell/cloud/MCP execution remains locked, and Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next phase is Phase 17 LLM Threat Defense + Prompt Injection Guard.

# Phase 17 LLM Threat Defense + Prompt Injection Guard

Phase 17 LLM Threat Defense + Prompt Injection Guard is complete after `scripts/verify_eva_llm_threat_defense_prompt_injection.py` and the master quick/full profiles pass. It is local/mock preview only. The verifier checks module imports, threat catalog, instruction hierarchy, defense policy, prompt-injection detection, system/developer impersonation, policy-ignore requests, hidden instructions in quoted text, context poisoning, malicious memory/tool-output-like text, exfiltration blocking, direct and indirect tool requests, locked execution-surface requests, command-injection-looking text, unknown or hallucinated capability claims, oversized/nested suspicious payloads, commands, `eva ask` routes, Control Center, capabilities/resource mappings/tool schemas, planner/team-review routing, docs, and master-profile inclusion. It confirms no live LLM/API/provider calls happen, no provider SDKs are used, no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read, arbitrary file reads are blocked, untrusted context cannot override trusted policy/instruction hierarchy, prompt-injection-like content is treated as untrusted data, defended context cannot execute tools, exfiltration and tool-request attempts fail safely, browser/desktop/shell/cloud/MCP execution remains locked, and Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next phase is Phase 18 Agent Loop v1.

# Phase 18 Agent Loop v1

Phase 18 Agent Loop v1 is complete after `scripts/verify_eva_agent_loop_v1.py` and the master quick/full profiles pass. It is local/mock preview only. The verifier checks module imports, loop policy, step-limit policy, status, local preview loop state, safe and unsafe requests, prompt-injection routing through threat-defense preview, secret/config/session blocking, locked execution-surface blocking, unknown/hallucinated capability rejection, repeated/no-progress safe stops, step-limit safe stops, preview-only action models, commands, `eva ask` routes, Control Center, capabilities/resource mappings/tool schemas, planner/team-review routing, docs, and master-profile inclusion. It confirms no live LLM/API/provider calls happen, no provider SDKs are used, no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read, arbitrary file reads are blocked, all actions are preview-only, agent loop cannot execute tools, browser/desktop/shell/cloud/MCP execution remains locked, step limits, runaway detection, repeated-step detection, and no-progress stop behavior are enforced, and Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next phase is Phase 19 Agentic Workflow Planner.

# Phase 19 Agentic Workflow Planner

Phase 19 Agentic Workflow Planner is complete after `scripts/verify_eva_agentic_workflow_planner.py` and the master quick/full profiles pass. It is local/mock preview only. The verifier checks module imports, workflow catalog, workflow policy, status, local workflow preview state, safe and unsafe workflow requests, tool/browser/desktop/shell/cloud/MCP/package blocking, secret/config/session blocking, arbitrary file read/write blocking, unknown/hallucinated capability rejection, dependency cycle blocking, missing precondition reporting, approval previews, rollback previews, verification plans, commands, `eva ask` routes, Control Center, capabilities/resource mappings/tool schemas, planner/team-review routing, docs, and master-profile inclusion. It confirms no live LLM/API/provider calls happen, no provider SDKs are used, no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read, arbitrary file reads/writes are blocked, all workflow steps are preview-only, workflow planner cannot execute tools, browser/desktop/shell/cloud/MCP execution remains locked, workflow dependency validation, precondition checks, approval previews, rollback previews, and verification plans are implemented, and Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next phase is Phase 20 Controlled Execution Gates.

# Phase 20 Controlled Execution Gates

Phase 20 Controlled Execution Gates is complete after `scripts/verify_eva_controlled_execution_gates.py` and the master quick/full profiles pass. execution gates are local/mock policy preview only. no live LLM/API/provider calls happen, no provider SDKs are used, and no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. tools are not executed. approval alone does not execute. confirmation alone does not execute unless an existing implemented gate accepts it. browser/desktop/shell/cloud/MCP execution remains locked. future gates are described but locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next phase is Phase 21 Memory v3.

# Phase 21 Memory v3

Run `scripts/verify_eva_memory_v3.py` directly and through both master profiles. It verifies models, policy, candidate filtering, retrieval preview, commands, ask routing, Control Center, capability/resource/schema metadata, planner/team-review routing, documentation, and forbidden runtime surfaces. Memory v3 is local-only; no live LLM/API/provider calls happen; no provider SDKs are used; no cloud memory or remote sync is used; no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read; raw memory database dumps are blocked; arbitrary file reads/writes are blocked. memory is source-aware, trust-aware, freshness-aware, privacy-aware, conflict-aware, and grounding-aware. memory cannot override system/developer/safety policy; memory cannot execute tools. sensitive, injected, stale, conflicting, or ungrounded memories are excluded or marked. context injection is preview/policy only. browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 22 Voice Assistant.

# Phase 22 Voice Assistant Foundation

Run `scripts/verify_eva_voice_assistant_foundation.py` directly and through both master profiles. Phase 22 Voice Assistant Foundation is complete after this pass when those checks pass. voice is local/mock preview only; no microphone access, audio recording, or audio playback happens; no live ASR/TTS/provider calls happen; no provider SDKs are used; no real LLM/API/provider calls happen; no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read; arbitrary file reads/writes are blocked; voice commands cannot execute tools. transcript safety, provider policy, wake/listen state policy, and confirmation preview are implemented. browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 23 AI OS / Control Center Upgrade.

# Phase 23 AI OS / Control Center Upgrade

Run `scripts/verify_eva_ai_os_control_center_upgrade.py` directly and through both master profiles. Phase 23 AI OS / Control Center Upgrade is complete after this pass when those checks pass. AI OS dashboard is local/status/report only; no live LLM/API/provider calls happen; no provider SDKs are used; no web server, browser launch, desktop UI launch, or daemon is created; no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read; arbitrary file reads/writes are blocked; AI OS dashboard cannot execute tools. preview-only features remain preview-only; locked future gates remain locked; browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 24 Real Browser Read-Only Mode.

Phase 12N verifier:

- `scripts/verify_eva_golden_workflow_ux.py`

It checks latest-state workflow summaries, next-step handling, safe disambiguation, Control Center workflow status, capability/schema/resource metadata, and compatibility with the Phase 12 verifier profile. It does not execute shell commands from Eva chat and does not enable broad file editing.

# Phase 24 Real Browser Read-Only Mode

Run `scripts/verify_eva_browser_readonly_mode.py` directly and through both master profiles. Phase 24 Real Browser Read-Only Mode is complete after this pass when those checks pass. Browser mode is public-URL read-only observation only: no clicking, typing, forms, downloads, uploads, login, or browser control. The verifier uses deterministic fixtures and performs no external network call. There is no logged-in browser profile/session/cookie access, and no provider SDKs or package installs. no real LLM/API/provider calls happen. no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. browser read-only observations cannot execute tools. browser control remains locked; desktop/shell/cloud/MCP execution remains locked. Real URLs return backend unavailable because no pre-existing safe backend exists. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 25 Real Desktop Observation Mode.

# Phase 25 Real Desktop Observation Mode

Run `scripts/verify_eva_desktop_observation_mode.py` directly and through both master profiles. Phase 25 Real Desktop Observation Mode is complete after this pass when those checks pass. desktop mode is observation-only: no clicking, typing, hotkeys, app/window control, continuous monitoring, or screenshot saving. The verifier uses a deterministic mock screen and performs no real screen capture. There is no cookie/session/browser profile/password-manager access, and no provider SDKs or package installs. no real LLM/API/provider calls happen. no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. desktop observations cannot execute tools. sensitive screens are classified and redacted or blocked. browser control remains locked; desktop control remains locked; shell/cloud/MCP execution remains locked. Real desktop observation returns backend unavailable because no pre-existing safe backend exists. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 26 Real Desktop Control Gate.

# Phase 26 Real Desktop Control Gate

Run `scripts/verify_eva_desktop_control_gate.py` directly and through both master profiles. Phase 26 Real Desktop Control Gate is complete after this pass when those checks pass. desktop control is dry-run/gate-only: no clicking, typing, hotkeys, clipboard, app/window control, automation, or shell execution happens. The verifier uses deterministic local strings and performs no desktop control. no provider SDKs or package installs were added; no real LLM/API/provider calls happen. no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. approval alone does not execute. confirmation alone does not execute. rollback/audit are metadata only. desktop observation remains observation-only; browser control remains locked; shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 27 News/Web Intelligence Dashboard.

# Phase 27 News / Web Intelligence Dashboard
Run `scripts/verify_eva_news_web_intelligence_dashboard.py` directly and through both master profiles. Phase 27 News / Web Intelligence Dashboard is complete after this pass. dashboard is local/mock by default and the verifier performs no network call. No unrestricted crawling, login scraping, session/cookie/profile access, or browser control is enabled. Source freshness, reliability, uncertainty, and citation metadata are tracked; Phase 24 public URL read-only policy is respected. No provider SDKs, package installs, real LLM/API/provider calls, secret/config/session reads, arbitrary file reads/writes, tool execution, or browser/desktop/shell/cloud/MCP execution was added. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 28 Coding Specialist / CodingAgent.

# Phase 28 Coding Specialist / CodingAgent Foundation

Run `scripts/verify_eva_coding_agent_foundation.py` directly and through both master profiles. Phase 28 Coding Specialist / CodingAgent Foundation is complete after this pass when the focused, quick, and full checks pass. The verifier covers modules, policy, status, specialist catalog, deterministic task classification, safe metadata-only project context, patch/review/test/risk/handoff previews, blocked execution and privacy classes, commands, `eva ask`, Control Center, AI OS, capabilities, resource mappings, tool schemas, planner, team review, docs, and master-profile inclusion.

The verifier performs no source edit, patch application, shell/test/package/git execution, arbitrary filesystem access, tool execution, provider SDK import, package install, live LLM/API/provider/network call, browser/desktop/cloud/MCP action, or secret/config/session/private-dump read. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 29 Public Demo / Release.

# Phase 29 Public Demo / Release

Run `scripts/verify_eva_public_demo_release.py` directly and through both master profiles. Phase 29 Public Demo / Release is complete after this pass when the focused, quick, and full checks pass. The verifier covers the release-demo model, profile, commands, capability map, safety proof, readiness, limitations, verification guidance, commands, `eva ask`, Control Center, AI OS, capabilities, resource mappings, tool schemas, planner, team review, README, public docs, phase docs, and master-profile inclusion.

The verifier performs no publishing, uploading, packaging, installer creation, commit, tag, push, provider SDK import, package install, shell/test/package/git execution, arbitrary filesystem access through the release-demo layer, live LLM/API/provider/network call, browser/desktop control, source edit, unrestricted crawl, secret/config/session/private-dump read, or tool execution. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path.

Phase 29 handed off to the Phase 30 release-candidate verifier documented below.

# Phase 30 Release Candidate Hardening / Commit Planning

Phase 30 Release Candidate Hardening / Commit Planning is complete after this pass when the focused verifier, master quick/full profiles, compileall, `git diff --check`, and final status review pass. Run `scripts/verify_eva_release_candidate_hardening.py` directly. Phase 30 is report/status/planning only. The commit plan is text only.

The verifier covers RC models, status, manifest, commit plan, hardening report, checklist, readiness, safety proof, verification guidance, all eight commands, `eva ask`, Control Center, AI OS, capabilities, mappings, schemas, planner, team review, docs, master-profile inclusion, human-readable output, and forbidden runtime surfaces.

For Phase 30, no git add/commit/tag/push was performed and no publishing/uploading was performed. No provider SDKs or package installs were added. No real LLM/API/provider calls happen. No `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config contents are read. Arbitrary file reads/writes remain blocked. Browser/desktop/shell/cloud/MCP execution and tool execution remain locked.

CodingAgent remains preview/report/status only, News remains local/mock or safe-read-only, and Voice remains a locked/mock foundation. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path.

Next safe step: user-approved commit execution outside Eva or a separate explicit commit-approval phase.

# Phase 32 Post-Push Sync + Demo Smoke Test Hardening

Phase 32 Post-Push Sync + Demo Smoke Test Hardening is complete after this pass. The focused verifier is:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_post_push_demo_smoke.py
```

The verifier covers release demo smoke modules, post-push sync status, human-readable output, `eva release smoke test`, `eva release post push sync`, `eva ask` routes, README/demo docs, master verifier inclusion, and forbidden runtime surfaces.

Remote moved warning was handled by updating local origin to:

```text
https://github.com/ankitlinkesh/eva-community.git
```

No commit/push/tag/release was performed in Phase 32. Demo smoke test is report/status/checklist only. No provider SDKs or package installs. No real LLM/API/provider calls happen. No `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config contents are read. No secrets, tokens, cookies, passwords, browser sessions, or config contents are read.

Browser/desktop/shell/cloud/MCP execution remains locked. CodingAgent remains preview/report/status only. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path.

# Phase 33-42 Roadmap Foundations

Phase 33 Execution Boundary Audit is complete as a foundation after this pass. The focused verifier is:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_phase33_roadmap_foundations.py
```

The verifier covers ExecutionClass values, typed execution boundary metadata, risky tool-registry classifications, Phase 32 demo-smoke catalog entries, Phase 33 through Phase 42 roadmap entries, command descriptors, capability descriptors, verifier descriptors, fast commands, `eva ask` routes, README/docs status, frontend truth labels, and master-profile inclusion.

Run it before claiming roadmap-foundation readiness:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_phase33_roadmap_foundations.py
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --quick --timeout 90
```

Execution boundary audit status: no new execution path is enabled. Roadmap commands are report/status/catalog only. Phase 41 remains blocked until a later explicit approval phase. Phase 42 Release Candidate v2 Hardening is documentation/verification hardening only and does not tag, release, upload, publish, package, deploy, or push anything.

No provider SDKs or package installs were added. No real LLM/API/provider calls happen. No `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config contents are read. Browser/desktop/shell/cloud/MCP execution remains locked. CodingAgent remains preview/report/status only. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path.
