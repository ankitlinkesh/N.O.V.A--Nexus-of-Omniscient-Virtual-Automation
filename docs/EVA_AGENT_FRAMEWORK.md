# Eva Agent Framework v1

> **Current-state correction (2026-07-12).** The per-phase notes below are a
> historical changelog. Several repeat "Phase 12L narrow `.md`/`.txt` creation
> remains the only real write path" and "execution remains locked" — those are
> no longer accurate as present-tense claims. Eva executes a whitelisted set of
> tools and gates destructive/privacy/external ones behind explicit user
> approval via the central permission gate (`ToolRegistry.run()`). For the exact,
> code-derived picture, run `eva capability truth`. Read the phase notes as
> "true when written," not as the current boundary.

Agent Framework v1 gives Eva's specialist subsystems a shared lifecycle interface so Planner v3 steps can be assigned consistently in future executor phases.

This phase is framework, status, explain, and dry-run only. It does not execute planned tasks.

## Lifecycle

Each registered agent exposes:

- `plan`
- `dry_run`
- `execute`
- `observe`
- `verify`
- `rollback`
- `explain`

In Phase 11A:

- `plan` and `dry_run` are available as previews.
- `explain` and status commands are available.
- `execute` refuses by default with an Agent Framework v1 disabled-execution message.
- `observe`, `verify`, and `rollback` return preview/unavailable results unless a later phase explicitly enables a safe path.

## Registered Agents

Initial registered agents:

- `ResearchAgent`: Research Memory, saved research, local research metadata, and safe public-research planning.
- `MemoryAgent`: local memory and task-context planning.
- `SafetyAgent`: permission, privacy, destructive action, and cloud-context precheck planning.
- `BrowserAgent`: browser and Chrome task planning only.
- `DesktopAgent`: desktop and visible UI task planning only.
- `MediaAgent`: Spotify/YouTube media task planning only.
- `FileAgent`: repo-scoped, read-only file and folder inspection, filename search, safe text previews, heuristic file understanding, project inventory, project structure summaries, output-only draft/diff previews, apply-readiness planning, and approval-ledger metadata.
- `CodeAgent`: Code Intelligence and workspace review planning only.
- `PlannerAgent`: Planner v3 templates, validation, and review.
- `PublicReleaseAgent`: public release, demo, safety simulator, and hardening status.
- `SupervisorAgent`: legacy specialist routing preview.

## Planner-To-Agent Delegation

The command `eva agents dry run plan <goal>`:

1. Builds a Planner v3 preview plan.
2. Selects an agent for each step using step metadata, capability id, and resource mapping.
3. Calls each agent's `dry_run`.
4. Validates that every assigned step has a dry-run result.
5. Adds assignment coverage and an agent-team recommendation.
6. Formats the assignments and what each agent would do.

No tools are executed, no browser or desktop is controlled, and no message or file action runs.

## Phase 11B Quality Layer

Phase 11B adds agent assignment quality and agent-team review before any real executor phase.

The quality layer checks:

- each planner step has a selected agent or a clear fallback
- assigned agents match the step capability, category, or risk profile
- browser and desktop agents remain dry-run only
- external-message steps include confirmation or refusal handling
- destructive and system-changing steps are blocked or override-gated
- dry-run results never claim that execution happened

Assignment confidence is reported as:

- high: exact planner hint or capability-to-agent match
- medium: category or keyword match
- low: safe fallback through Planner, Safety, or Supervisor

## Agent Team Review

The team review command builds a Planner v3 preview plan, assigns agents, runs dry-run previews, and summarizes specialist findings.

Review roles:

- `PlannerAgent` reviews plan structure and missing information.
- `ProjectInspectorAgent` and the existing codebase onboarding specialist handle read-only repo explanations through FileAgent inventory.
- `RealityCheckerAgent`, `EvidenceCollector`, and `TestResultsAnalyzer` frame done/proof/broken-status answers around verifier evidence and local status surfaces.

## Phase 12O Project Reality Workflow

Phase 12O adds read-only project/reality routes for `eva ask inspect this project`, `eva ask what proof do we have`, `eva ask are we actually done`, `eva ask what is broken`, and `eva ask what should we do next`.

These routes do not execute tools, run verifiers, write files, open browsers, control desktop apps, call cloud services, or enable normal-chat v2 routing. They only format local evidence from FileAgent inventory, workflow state, Control Center status, capabilities, and verifier-command surfaces.

## Phase 12P Control Center Status Route

Phase 12P upgrades Control Center routing for dashboard/status questions:

- `eva control center`
- `eva control center summary`
- `eva locked features`
- `eva enabled features`
- `eva next safe step`
- `eva ask show control center`
- `eva ask what features are locked`
- `eva ask what features are enabled`

Planner and team review surface these as ControlCenterAgent read-only steps. Locked-feature explanations are status only and do not enable browser, desktop, MCP, terminal, package, cloud, or broad file-write execution.
- `SafetyAgent` reviews risky, destructive, privacy, and external-visible steps.
- specialist agents review matching capability areas such as Research Memory or Browser.
- `SupervisorAgent` represents verification review until a dedicated verifier agent is implemented.

Examples:

- `eva agents review plan use my saved research about Eva`
  - ResearchAgent can preview local Research Memory retrieval.
  - Safety review is low risk.
  - Recommendation stays read-only/dry-run.
- `eva agents review plan send WhatsApp to mom saying hi`
  - SafetyAgent flags the external message.
  - message sending remains unavailable and confirmation-gated.
  - recommendation is draft/review only; do not send.

## Commands

- `eva agents`
- `eva agents status`
- `eva agent list`
- `eva agent <agent_name>`
- `eva agent capabilities <agent_name>`
- `eva agents matrix`
- `eva agents dry run plan <goal>`
- `eva agents review plan <goal>`
- `eva agent team review <goal>`
- `eva agents coverage <goal>`

FileAgent explicit read-only commands:

- `eva file status`
- `eva file inspect <path>`
- `eva folder inspect <path>`
- `eva file search <query>`
- `eva file preview <path>`
- `eva file understand <path>`
- `eva file summarize <path>`
- `eva project inventory`
- `eva project explain`
- `eva project missing`
- `eva project dependencies`
- `eva project structure`
- `eva file draft create <path> text <text>`
- `eva file draft append <path> text <text>`
- `eva file draft replace <path> old <old_text> new <new_text>`
- `eva file draft diff <path> text <proposed_full_content>`
- `eva draft readme section <topic>`
- `eva draft project summary`
- `eva draft report outline <title>`
- `eva draft project todo`
- `eva file apply policy`
- `eva file apply readiness create <path> text <text>`
- `eva file apply readiness append <path> text <text>`
- `eva file apply readiness replace <path> old <old_text> new <new_text>`
- `eva file write safety <path>`
- `eva file rollback plan <path>`
- `eva file approval status`
- `eva file approval request create <path> text <text>`
- `eva file approval request append <path> text <text>`
- `eva file approval request replace <path> old <old_text> new <new_text>`
- `eva file approvals pending`
- `eva file approval <approval_id>`
- `eva file approval approve <approval_id> confirm <exact_phrase>`
- `eva file approval deny <approval_id>`
- `eva file approval cancel <approval_id>`
- `eva file approval events <approval_id>`
- `eva file approvals expire`
- `eva file apply executor status`
- `eva file apply sandbox policy`
- `eva file approval sandbox apply <approval_id>`
- `eva file approval sandbox verify <approval_id>`
- `eva file approval sandbox rollback <approval_id>`
- `eva ask <natural language request>`
- `eva authority status`
- `eva natural route <natural language request>`
- `eva control center status`
- `eva dashboard status`
- `eva dashboard url`
- `eva file real apply policy`
- `eva file real apply eligibility <approval_id>`
- `eva file approval real create <approval_id> confirm real create <approval_id>`
- `eva file approval real verify <approval_id>`
- `eva file approval real rollback <approval_id> confirm rollback real create <approval_id>`
- `eva agents validate plan <goal>`
- `eva agent explain <agent_name>`
- `eva agent framework status`

Examples:

- `eva agents status`
- `eva agent ResearchAgent`
- `eva agent explain BrowserAgent`
- `eva agents dry run plan use my saved research about Eva`
- `eva agents dry run plan send WhatsApp to mom saying hi`
- `eva agents review plan open ChatGPT on Chrome`
- `eva agents coverage delete Downloads folder`

## Safety Limits

Phase 11A and Phase 11B do not enable:

- MCP execution
- Playwright execution
- PyAutoGUI execution
- browser control
- desktop control
- screen watching
- WhatsApp sending
- email sending
- file writes
- file edits, deletes, moves, renames, copies, or whole-drive scans through FileAgent
- applying FileAgent draft previews as real file changes
- creating real FileAgent backups or performing real rollback
- applying approved FileAgent approval records to real project/user files, except the Phase 12L create-new-text-file gate
- shell execution
- package installs
- cloud embeddings
- vector search by default
- normal chat routing through the new agent framework

Eva remains a local data/control assistant that can use API-backed LLM reasoning elsewhere when configured. This framework phase makes no cloud calls and does not read secret files.

BrowserAgent and DesktopAgent are currently review/dry-run specialists only. SafetyAgent remains the default reviewer for risky steps. Normal chat is still not routed through Agent Framework commands.

## Future Path

Later phases can connect the shared lifecycle to permission sessions, safe read-only delegates, verified executors, observation, verification, and rollback. Those phases must keep explicit confirmation, override, and refusal boundaries in place.

Phase 12E approval records are metadata only. Phase 12F can test an approved record inside the ignored FileAgent runtime sandbox with sandbox-only backup, verification, and rollback. That does not authorize real project/user file execution.

Phase 12G adds the global AuthorityDecision spine and natural-language-first `eva ask` wrapper. The wrapper routes obvious user requests to existing safe command surfaces and shows the interpreted intent plus authority decision. Commands remain available as debug/fallback surfaces. Natural routing is deterministic and local in this phase; future LLM-backed routing can be added later behind the same authority boundary.

Phase 12H adds Eva Control Center v1 as a read-only dashboard/status surface. Planner and team-review metadata can route dashboard, control center, Eva status, and system-state goals to the Control Center capability. This does not open a browser, execute tools, enable normal-chat v2 routing, or perform real file/browser/desktop/terminal actions.

Phase 12L adds a narrow FileAgent real apply gate. Planner and team-review metadata can route approved markdown/text create goals to FileAgent, but exact confirmation remains mandatory. The allowed real action is limited to creating a brand-new `.md` or `.txt` file directly in `docs/` or `samples/`, verifying it, and optionally rolling back that unchanged Eva-created file. Broad file editing, overwrite, append, delete, move, source/config/runtime writes, browser/desktop control, MCP, package installs, cloud calls, and normal-chat v2 routing remain disabled.

## Phase 12Q WorkSession Audit Route

Phase 12Q adds local WorkSession and audit timeline metadata. `eva ask` creates a sanitized local WorkSession record with interpreted intent, selected specialist/skill/workflow metadata, authority decision, visible workflow evidence, final report, and next safe step.

Planner and team-review surfaces recognize WorkSession goals such as:

- `show work sessions`
- `show audit timeline`
- `what happened last`
- `latest session`

These routes are read-only audit/status views. They do not execute tools, run verifiers, mutate files, open browsers, control desktop apps, call cloud services, enable MCP, or broaden the Phase 12L real-create gate.

## Phase 13A BrowserAgent Safety Review

Planner and team-review surfaces recognize browser safety questions such as:

- `can Eva use the browser`
- `what browser actions are allowed`
- `is browser control enabled`
- `show browser policy`
- `can Eva click login or upload files`

These route to BrowserAgent status/policy/action-safety previews only. The BrowserAgent specialist can explain that real browser control is locked and that launching, navigating, clicking, typing, submitting forms, login, payments, uploads, downloads, cookie/localStorage/profile reads, screenshots, Playwright/browser-use/Stagehand/Maxun execution, MCP, PyAutoGUI, shell, package installs, and cloud calls remain blocked.

## Phase 13B Browser Session Preview Review

Planner and team-review surfaces recognize browser-session preview questions such as:

- `start a browser session`
- `open a browser`
- `can Eva browse websites`
- `show browser session status`
- `what would a browser session do`
- `is browser read-only mode ready`

These route to BrowserAgent preview/status capabilities only. Eva may create a local preview-only session record and explain future lifecycle/readiness, but no real browser session is created and no page, screenshot, DOM, cookie, localStorage, profile, password, session, or token data is read.

## Phase 13C Browser Observation Preview Review

Planner and team-review surfaces recognize browser observation design questions such as:

- `can Eva read a webpage`
- `can Eva summarize a page`
- `can Eva inspect DOM`
- `can Eva take screenshots`
- `show browser observation policy`
- `what would Eva extract from a webpage`

These route to BrowserAgent observation preview capabilities only. Eva may explain page/text/DOM summary schemas, mock-text preview output, redaction policy, and readiness gaps, but no browser is launched and no live page, DOM, screenshot, cookie, localStorage, profile, password, session, or token data is read.

## Phase 13D Browser Action Dry-Run Review

Planner and team-review surfaces recognize browser action dry-run questions such as:

- `dry run opening a website`
- `what would Eva do to search Google`
- `can Eva click this`
- `can Eva type into a website`
- `plan browser actions for logging in`
- `what browser actions need approval`
- `show browser action dry run policy`

These route to BrowserAgent action dry-run capabilities only. Eva may show text-only plan steps, risk levels, approval requirements, blocked execution, and readiness gaps, but no browser launch, navigation, screenshot, DOM read, click, type, submit, login, upload, download, cookie, localStorage, profile, password, session, or token data is accessed.

## Phase 13E Browser Domain Risk Review

Planner and team-review surfaces recognize domain/site-risk questions such as:

- `is example.com safe for Eva`
- `can Eva use Gmail`
- `can Eva open a banking website`
- `can Eva upload files to a site`
- `what sites are risky`
- `what approvals are needed for sensitive sites`

These route to BrowserAgent domain-risk capabilities only. Eva may classify a provided domain string, show sensitive categories, explain future approval requirements, and report readiness gaps. It must not perform DNS/network calls, launch or navigate browsers, fetch pages, read DOM, capture screenshots, click/type/submit/login/upload/download, read cookies/localStorage/profile/session/password/token data, or use Playwright/browser-use/Stagehand/Maxun/MCP/PyAutoGUI/shell/package/cloud execution.

## Phase 13F Browser Read-Only Readiness Proof Review

Planner and team-review surfaces recognize BrowserAgent proof questions such as:

- `is browser read-only mode ready`
- `prove browser control is still locked`
- `what is missing before browser read-only`
- `show browser safety proof`
- `is Phase 13 browser safe`
- `can Eva browse now`

These route to BrowserAgent readiness-proof capabilities only. Eva may show completed safety layers, readiness gaps, locked execution categories, next phase, and proof status, but real browser read-only mode remains disabled and no browser/network/page observation/control is attempted.

## Phase 13G BrowserAgent Hardening Review

Planner and team-review surfaces recognize final BrowserAgent Phase 13 questions such as:

- `is browser phase 13 complete`
- `summarize browser phase 13`
- `what are browser phase 13 limits`
- `browser phase 13 final proof`
- `can Eva browse now`

These route to BrowserAgent Phase 13 hardening proof/status capabilities only. Eva may show final status, summary, limits, readiness, Control Center agreement, capability metadata, and the future gate requirement. Phase 13 is safety/readiness only; real browser read-only mode is not enabled; real browser control is not enabled; network/DNS/live page read/DOM/screenshot/action execution are locked; any future real browser read-only mode requires a separate approved gate; Phase 12L narrow real create remains the only real write path.

## Phase 14A DesktopAgent Safety Review

Planner and team-review surfaces recognize DesktopAgent safety questions such as:

- `can Eva control my desktop`
- `can Eva see my screen`
- `can Eva click and type`
- `can Eva open apps`
- `can Eva use terminal`
- `show desktop policy`
- `what desktop actions are allowed`
- `is desktop control enabled`

These route to DesktopAgent safety/status capabilities only. Eva may show desktop status, policy, blocked actions, action safety, app-risk string classification, and readiness gaps. Real screen observation and real desktop control remain locked; no screen capture, screenshots, window/app inspection, app launch, mouse, keyboard, clipboard, file dialog, terminal, package, browser, desktop, MCP, PyAutoGUI, Playwright, shell, or cloud execution is attempted.

## Phase 14B Desktop Session Preview Review

Planner and team-review surfaces recognize desktop session/status-preview questions such as:

- `start a desktop session`
- `show desktop session status`
- `can Eva see open windows`
- `can Eva detect the active app`
- `can Eva inspect my screen`
- `what would desktop observation include`
- `is desktop observation ready`

These route to DesktopAgent session/status-preview capabilities only. Eva may create in-memory preview records, list latest preview sessions, show app/window/active-context schema previews, and explain observation readiness gaps. Real screen observation and real desktop control remain locked; no screen capture, screenshots, real window enumeration, app inspection, active app detection, app launch, mouse, keyboard, clipboard, file dialog, terminal, package, browser, desktop, MCP, PyAutoGUI, Playwright, shell, or cloud execution is attempted.

## Phase 14C Desktop Screen Observation Policy Review

Planner and team-review surfaces recognize screen observation policy questions such as:

- `can Eva see my screen`
- `can Eva take screenshots`
- `can Eva read my screen`
- `what screens are sensitive`
- `show screen observation policy`
- `what would Eva redact from screen`
- `is screen observation ready`

These route to DesktopAgent screen policy/status capabilities only. Eva may show sensitive-screen categories, local redaction policy, capture gate requirements, and readiness gaps. Real screen observation remains locked; no screen capture, screenshots, OCR, image analysis, window/app inspection, active app detection, mouse, keyboard, clipboard, file dialog, terminal, package, browser, desktop, MCP, PyAutoGUI, Playwright, shell, or cloud execution is attempted.

## Phase 14D Desktop Action Dry-Run Review

Planner and team-review surfaces recognize Desktop Action Dry-Run questions such as:

- `dry run clicking a button`
- `what would Eva do to open an app`
- `can Eva click this`
- `can Eva type into an app`
- `can Eva press hotkeys`
- `plan desktop actions for sending a message`
- `what desktop actions need approval`
- `show desktop action dry run policy`

These route to DesktopAgent action dry-run capabilities only. Eva may show text-only plan steps, risk levels, approval requirements, blocked execution, and readiness gaps, but no screen capture, screenshot, app/window inspection, app launch, mouse movement, clicking, dragging, keyboard typing, hotkeys, clipboard access, file dialog automation, terminal/package execution, browser, desktop, MCP, PyAutoGUI, Playwright, shell, network, or cloud execution is attempted.

## Phase 14E Desktop Action Risk Scoring Review

Planner and team-review surfaces recognize Desktop Action Risk Scoring questions such as:

- `how risky is clicking this`
- `how risky is typing my password`
- `what approval is needed to send a message`
- `what desktop actions are high risk`
- `show desktop safety matrix`
- `score the risk of opening terminal`
- `score the risk of uploading a file`

These route to DesktopAgent risk/status capabilities only. Eva may calculate deterministic string-only risk scores, show risk factors, show approval levels, and list forbidden action classes. It does not observe screens, inspect windows/apps, launch apps, move/click/type, use hotkeys, access clipboard, automate file dialogs, run terminal/package commands, use MCP/PyAutoGUI/Playwright, call browser/network/cloud services, or execute desktop actions.

## Phase 14F Desktop Human Approval Model Review

Planner and team-review surfaces recognize Desktop Human Approval Model goals such as:

- `show desktop approval policy`
- `what approval is needed to click`
- `what confirmation phrase would be required`
- `what desktop actions are forbidden`
- `is desktop approval ready`

These route to DesktopAgent approval-policy/status capabilities only. Eva can show future approval levels, confirmation phrase previews, forbidden action classes, audit-schema status, and readiness gaps. Approvals do not unlock real desktop execution.

## Phase 15A LLM Router Interface + Provider Contracts

Planner and team-review surfaces recognize LLM router status, provider contract, fallback, limit, structured-output, and readiness questions. These are local metadata and mock validation surfaces only. They do not read configuration files, call providers, use provider SDKs, invoke tools from model output, or unlock browser, desktop, shell, package, MCP, or cloud execution.

Phase 15B extends this with deterministic fallback/failure simulations, degraded mode, limits, runaway protection, and routing-audit previews only. Live provider calls remain locked; the next phase is 15C Structured Output Validation Hardening.

## Phase 15C Structured Output Validation Hardening

Phase 15C is complete. Its local validation engine, commands, `eva ask` routes, Control Center panel, capability/resource/schema metadata, planner previews, and team-review boundaries are mock/local only. They do not call providers, use provider SDKs, read `.env`/`.env.local` or secrets/tokens/cookies/passwords/browser sessions, execute tools from LLM output, or unlock browser/desktop execution. Invalid output is blocked into a refusal preview; repair does not execute, rewrite user intent, or turn unsafe output into executable actions. The next phase is 15D LLM Router Red-Team/Failure Tests; Phase 12L narrow approved new `.md`/`.txt` creation remains the only real write path.

## Phase 14G DesktopAgent Locked Readiness Proof

## Phase 15D LLM Router Red-Team / Failure Tests

Phase 15D is complete as a local/mock-only adversarial test layer. Its case runner and reports never call providers, use SDKs, read config/secrets/sessions, execute tools, or unlock browser/desktop/shell/cloud/MCP actions. Prompt injection, hallucinated capabilities, secret exfiltration, oversized output, malformed JSON, and command-injection-looking text fail safely before any future provider integration. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real write path; next: Phase 16 Context Assembly Engine.

Phase 15E locks those deterministic outcomes into a local/mock regression baseline and evidence report. It is CI-safe and report-only, not a live red-team harness, provider integration, execution path, or new write path.

Planner and team-review surfaces also recognize final Phase 14 status, summary, limits, ready-check, proof, locked-status, and readiness-gap requests. Those routes are proof/status only: they confirm real desktop observation and control are not enabled, approvals do not unlock execution, BrowserAgent remains locked, and Phase 12L narrow real create remains the only real write path. The next core architecture track is Phase 15 LLM Router + Structured Reasoning Core, followed by Context Assembly, LLM Threat Defense, and Agent Loop foundations.

## Phase 12S Readiness Route

Planner and team-review surfaces recognize Phase 12 checkpoint questions such as:

- `is phase 12 ready`
- `summarize phase 12`
- `what are phase 12 limits`
- `show phase 12 proof`

These route to VerifierAgent status/proof capabilities. They show readiness, summary, limits, and manual verifier commands, but they do not run subprocesses, execute tools, mutate files, open browsers, control desktops, call cloud services, enable MCP, or broaden the Phase 12L narrow real-create gate.
## Phase 12J Golden Workflow Review

Planner and team-review surfaces recognize golden workflow goals such as:

- `create a project note`
- `make a safe markdown note`
- `draft and safely create`
- `continue golden workflow`
- `rollback created note`

The dry-run plan should show FileAgent as the specialist and preserve the sequence: route natural request, generate safe draft, create approval request, sandbox apply first, require exact real-create confirmation, verify the created file, and offer rollback only through the exact rollback phrase.

This remains preview/orchestration work. Normal chat is not routed through v2 by default, and broad file writes remain disabled.

## Phase 12K Verification UX

Planner and team-review surfaces recognize verification/status goals such as:

- `verify Eva with quick check`
- `run quick check`
- `how do I verify Eva`
- `show phase 12 status`
- `is Eva safe right now`

These route to read-only capabilities such as `eva.smoke_status`, `eva.verify_quick_command`, `eva.verify_full_command`, `eva.phase12_status`, and `eva.ux_status`. VerifierAgent review may suggest the quick/full commands, but it does not run shell commands, install packages, call cloud services, or enable feature execution.

The master verifier supports:

## Phase 16 Context Assembly Engine

Planner and team-review surfaces recognize Phase 16 Context Assembly Engine requests as local/mock preview only. The engine assembles source-aware, budget-aware, redaction-aware, permission-aware, and grounding-aware packet previews with no live LLM/API/provider calls, no provider SDKs, no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config-secret reads, and arbitrary file reads are blocked. Prompt-injection-like content is not trusted as instruction, assembled context cannot execute tools, and browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real write path. Next phase is Phase 17 LLM Threat Defense + Prompt Injection Guard.

## Phase 17 LLM Threat Defense + Prompt Injection Guard

Planner and team-review surfaces recognize Phase 17 LLM Threat Defense + Prompt Injection Guard requests as local/mock preview only. The guard scans user requests, assembled context, memory-like text, tool-output-like text, and untrusted content with no live LLM/API/provider calls, no provider SDKs are used, no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config-secret reads, and arbitrary file reads are blocked. untrusted context cannot override trusted policy/instruction hierarchy. prompt-injection-like content is treated as untrusted data, defended context cannot execute tools, and exfiltration and tool-request attempts fail safely. Browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real write path. Next phase is Phase 18 Agent Loop v1.

## Phase 18 Agent Loop v1

Planner and team-review surfaces recognize Phase 18 Agent Loop v1 requests as local/mock preview only. The loop receives a request, classifies route intent, assembles a safe context preview, runs threat-defense preview, creates a bounded plan preview, creates action previews only, creates mock observations only, verifies plan/action safety, produces a final status/report, and stops safely. It performs no live LLM/API/provider calls, no provider SDKs are used, no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read, and arbitrary file reads are blocked. all actions are preview-only, agent loop cannot execute tools, and browser/desktop/shell/cloud/MCP execution remains locked. step limits, runaway detection, repeated-step detection, and no-progress stop behavior are enforced. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real write path. Next phase is Phase 19 Agentic Workflow Planner.

## Phase 19 Agentic Workflow Planner

Planner and team-review surfaces recognize Phase 19 Agentic Workflow Planner requests as local/mock preview only. The planner receives a workflow request, classifies workflow intent, selects a candidate template, assembles safe context preview, runs threat-defense preview, composes workflow steps, validates dependencies and preconditions, creates action previews only, creates approval requirements preview, creates rollback plan preview, creates verification plan, produces a final workflow report, and stops safely. It performs no live LLM/API/provider calls, no provider SDKs are used, no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read, and arbitrary file reads/writes are blocked. all workflow steps are preview-only, workflow planner cannot execute tools, and browser/desktop/shell/cloud/MCP execution remains locked. workflow dependency validation, precondition checks, approval previews, rollback previews, and verification plans are implemented. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real write path. Next phase is Phase 20 Controlled Execution Gates.

## Phase 20 Controlled Execution Gates

Planner and team-review surfaces recognize Phase 20 Controlled Execution Gates as local/mock policy preview only. execution gates are local/mock policy preview only. no live LLM/API/provider calls happen, no provider SDKs are used, and no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. tools are not executed. approval alone does not execute. confirmation alone does not execute unless an existing implemented gate accepts it. browser/desktop/shell/cloud/MCP execution remains locked. future gates are described but locked. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real write path. Next phase is Phase 21 Memory v3.

## Phase 21 Memory v3

Phase 21 Memory v3 adds a deterministic local policy layer for candidate classification, retrieval eligibility, and context preview. Memory v3 is local-only; no live LLM/API/provider calls happen; no provider SDKs are used; no cloud memory or remote sync is used; no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read; raw memory database dumps are blocked; arbitrary file reads/writes are blocked. memory is source-aware, trust-aware, freshness-aware, privacy-aware, conflict-aware, and grounding-aware. memory cannot override system/developer/safety policy; memory cannot execute tools. sensitive, injected, stale, conflicting, or ungrounded memories are excluded or marked. context injection is preview/policy only. browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real file write path. Next phase is Phase 22 Voice Assistant.

## Phase 22 Voice Assistant Foundation

Phase 22 Voice Assistant Foundation is complete after this pass as a deterministic pipeline model from mock transcript safety through local route, confirmation, and execution-gate previews. voice is local/mock preview only; no microphone access, audio recording, or audio playback happens; no live ASR/TTS/provider calls happen; no provider SDKs are used; no real LLM/API/provider calls happen; no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read; arbitrary file reads/writes are blocked; voice commands cannot execute tools. transcript safety, provider policy, wake/listen state policy, and confirmation preview are implemented. browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real file write path. Next phase is Phase 23 AI OS / Control Center Upgrade.

## Phase 23 AI OS / Control Center Upgrade

Phase 23 AI OS / Control Center Upgrade is complete after this pass as a deterministic aggregation layer over known local status metadata. AI OS dashboard is local/status/report only; no live LLM/API/provider calls happen; no provider SDKs are used; no web server, browser launch, desktop UI launch, or daemon is created; no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read; arbitrary file reads/writes are blocked; AI OS dashboard cannot execute tools. preview-only features remain preview-only; locked future gates remain locked; browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real file write path. Next phase is Phase 24 Real Browser Read-Only Mode.

## Phase 12M Specialist And Skill Workflows

Phase 12M adds a deterministic specialist and skill workflow foundation:

- Specialists: FileAgent workflow, codebase onboarding, technical writing, reality checking, evidence collection, test result analysis, and safety review.
- Skills: project-note workflow, safe draft, read-only project inspection, verification-before-completion, and safety status review.
- Workflow: `fileagent_project_note_create`, a plan-only wrapper around existing FileAgent gates.

Planner and team-review output can now show interpreted specialist, skill, and workflow routes. These routes do not execute tasks. They are metadata and next-step guidance over existing safe commands.

## Phase 12N Latest-State Workflow Review

Phase 12N lets planner and team-review surfaces include latest FileAgent workflow state:

- pending approval count
- approved record count
- latest sandbox apply status
- latest real-create status
- rollback availability
- ambiguity warning
- exact next safe step

This is still status and routing metadata. It helps the user continue workflows without memorizing IDs when one safe candidate is unambiguous, but it does not bypass FileAgent approval, exact confirmation, verification, or rollback gates.

- `scripts/verify_eva_all.py --quick`
- `scripts/verify_eva_all.py --full`
- `scripts/verify_eva_all.py --list`
- optional `--timeout <seconds>` per verifier script

## Phase 24 Real Browser Read-Only Mode

Phase 24 Real Browser Read-Only Mode is complete after this pass. The framework routes browser read-only goals to public URL policy, observation, status, or report steps only. Browser mode is public-URL read-only observation only: no clicking, typing, forms, downloads, uploads, login, or browser control. There is no logged-in browser profile/session/cookie access, and no provider SDKs or package installs. no real LLM/API/provider calls happen. no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. browser read-only observations cannot execute tools. browser control remains locked; desktop/shell/cloud/MCP execution remains locked. Deterministic mock observation is available, while real URLs return backend unavailable because no pre-existing safe backend exists. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real file write path. Next phase is Phase 25 Real Desktop Observation Mode.

## Phase 25 Real Desktop Observation Mode

Phase 25 Real Desktop Observation Mode is complete after this pass. The framework routes desktop observation goals only to one-shot observation, policy, status, readiness, or report steps. desktop mode is observation-only: no clicking, typing, hotkeys, app/window control, continuous monitoring, or screenshot saving. There is no cookie/session/browser profile/password-manager access, and no provider SDKs or package installs. no real LLM/API/provider calls happen. no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. desktop observations cannot execute tools. sensitive screens are classified and redacted or blocked. browser control remains locked; desktop control remains locked; shell/cloud/MCP execution remains locked. Deterministic mock observation is available, while real desktop observation returns backend unavailable because no pre-existing safe backend exists. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real file write path. Next phase is Phase 26 Real Desktop Control Gate.

## Phase 26 Real Desktop Control Gate

Phase 26 Real Desktop Control Gate is complete after this pass. The framework routes desktop-control goals only to local policy, eligibility, risk, approval, confirmation, readiness, or dry-run reports. desktop control is dry-run/gate-only: no clicking, typing, hotkeys, clipboard, app/window control, automation, or shell execution happens. no provider SDKs or package installs were added; no real LLM/API/provider calls happen. no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. approval alone does not execute. confirmation alone does not execute. rollback/audit are metadata only. desktop observation remains observation-only; browser control remains locked; shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real file write path. Next phase is Phase 27 News/Web Intelligence Dashboard.

## Phase 27 News / Web Intelligence Dashboard
Phase 27 News / Web Intelligence Dashboard is complete after this pass. dashboard is local/mock by default and planner routes remain dashboard/report/status only. No unrestricted crawling, login scraping, session/cookie/profile access, or browser control is enabled. Source freshness, reliability, uncertainty, and citation metadata are tracked; Phase 24 public URL read-only policy is respected. No provider SDKs, package installs, real LLM/API/provider calls, secret/config/session reads, arbitrary file reads/writes, tool execution, or browser/desktop/shell/cloud/MCP execution was added. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real file write path. Next phase is Phase 28 Coding Specialist / CodingAgent.

## Phase 28 Coding Specialist / CodingAgent Foundation

Phase 28 Coding Specialist / CodingAgent Foundation is complete after this pass. The planner and team-review layers can route coding questions to deterministic local classification, planning, checklist, risk-review, and handoff previews. These routes are preview/report/status only and cannot decompose work into source editing, patch application, shell execution, test execution, package installation, git operations, arbitrary file access, browser/desktop control, cloud/MCP calls, or tool execution.

No provider SDKs or package installs were added; no real LLM/API/provider calls happen; no secret/config/session data or raw private dumps are read. Browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real file write path. Next phase is Phase 29 Public Demo / Release.

## Phase 29 Public Demo / Release

Phase 29 Public Demo / Release is complete after this pass. Planner and team-review routes treat release/demo questions as local documentation/report/status/profile requests only. They do not create publishing, uploading, packaging, installer, commit, tag, push, shell, browser, desktop, source-edit, filesystem, cloud, MCP, or execution steps.

No provider SDKs or package installs were added; no real LLM/API/provider calls happen; no secret/config/session data or raw private dumps are read. CodingAgent remains preview/report/status only, News Dashboard remains local/mock or safe-read-only only, Voice remains locked/mock, and browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real file write path.

Phase 29 handed off to Phase 30 Release Candidate Hardening. The current next safe step is user-approved commit execution outside Eva or a separate explicit commit-approval phase.
