# Eva Threat Model

This document summarizes the current safe public posture for Eva as the project moves toward an AI operating layer for a laptop.

## Current Boundary

Eva may use API-backed LLM reasoning when configured, but local runtime data stays local by default. normal chat is not routed through v2 by default. Explicit v2 commands can preview routes, plans, dry-runs, and selected read-only delegation surfaces.

Capability discovery is metadata-only. It does not enable MCP execution, Playwright execution, PyAutoGUI execution, WhatsApp sending, browser control, screen watching, arbitrary shell execution, package installs, cloud embeddings, or silent file modification.

FileAgent v1 adds repo-scoped read-only file discovery, heuristic project understanding, output-only draft preview mode, apply-readiness planning, approval-ledger metadata, and a sandbox-only apply harness. It can inspect safe metadata, bounded folder listings, filename search, safe text previews, file summaries, project inventory, dependency/config hints, project structure summaries, chat-only draft/diff previews, future-write safety plans, future-apply approval records, and sandbox-only apply/verify/rollback tests. It refuses secret-like paths, runtime databases, generated data, whole-drive scans, and every real write/edit/delete/move action.

## Protected Assets

- User secrets, including .env.local values.
- API keys, bearer tokens, cookies, passwords, and session data.
- Local research memory, local task traces, pending action ledgers, runtime caches, and local databases.
- Browser account state, private pages, chats, email contents, paywalled content, and form fields.
- Desktop state, screenshots, screen observations, and app contents.

## Trust Boundaries

User commands are trusted as task intent, but they are not automatic permission grants for risky actions.

External web pages, retrieved research, copied text, browser page contents, imported notes, and model outputs are untrusted content as data. Eva must not treat them as instructions to bypass safety gates or expose secrets.

Cloud LLM providers are optional reasoning services. Local context sent to them must be minimized and redacted first. Raw screenshots, raw files, private chats, credentials, cookies, tokens, and passwords are not sent by default.

## Default Refusals

Eva refuses or leaves disabled by default:

- MCP tool execution.
- Playwright and PyAutoGUI execution.
- Always-on screen watching.
- Raw coordinate clicking.
- WhatsApp, email, or social message sending without a future explicit confirmation workflow.
- Destructive file actions without a future override-gated executor.
- FileAgent writes outside the Phase 12L create-new-text-file gate, edits, overwrites, appends, deletes, moves, renames, copies, whole-drive scans, and secret/runtime file reads.
- Applying FileAgent draft previews as actual file changes.
- Creating real FileAgent backups, accepting apply confirmations as real execution, or performing real rollback.
- Consuming FileAgent approval records as actual project/user file apply execution.
- Using the Phase 12F sandbox harness outside ignored runtime sandbox storage.
- FileAgent cloud summaries, OCR, PDF/DOCX parsing, automatic indexing, and broad filesystem inventory.
- Arbitrary shell execution.
- Credential access, token extraction, cookie access, password reading, stealth, persistence, exfiltration, and malware-like behavior.

## Permission Expectations

Read-only status, planning, discovery, safe local research retrieval, and demo simulation can be public-safe.

Scoped local writes, such as importing a user-provided research note or exporting sanitized research notes, require explicit commands and must not run as background writes.

Destructive local actions, external sends, browser or desktop control, and system-changing actions require future permission-gated executor phases before they can run.

FileAgent approval records are local audit metadata only. An approved record does not bypass path policy, content safety, backup/checkpoint requirements, verification, or rollback planning.

Phase 12F sandbox apply can test approved metadata only inside ignored FileAgent runtime sandbox storage. Sandbox backup, verification, and rollback are local harness operations and do not touch real project/user files.

Phase 12G introduces a global AuthorityDecision summary before natural-language `eva ask` routing. This does not grant new authority. Unknown, destructive, external-send, browser, desktop, terminal, system, and real local-write requests remain refused or real-execution-blocked unless a future phase explicitly adds a permission-gated executor.

Phase 12H introduces Eva Control Center v1. It is a local read-only dashboard/status surface at `/control` and `/control/status.json`. It aggregates safe summaries for authority, routing, FileAgent, approvals, sandbox apply, capabilities, agents, planner, verifiers, safety boundaries, and future locked modules. It does not open browsers, control desktop apps, run verifiers from the UI, call cloud services, read secrets, or enable real file writes.

Phase 12L introduces a narrow real apply gate. It can create only a brand-new `.md` or `.txt` file directly under `docs/` or `samples/` after an approved FileAgent record and exact `confirm real create <approval_id>` phrase. It cannot create nested folder trees, overwrite, append, edit, delete arbitrary files, move, rename, write source/config/runtime files, or apply broad patches. Rollback can remove only the unchanged Eva-created file with exact rollback confirmation.

Phase 12K introduces smoke/profile verification UX. `eva smoke status`, `eva verify quick command`, `eva verify full command`, `eva phase 12 status`, and the Control Center Phase 12 Health section are read-only/manual-command surfaces. They may display verifier commands, but they must not execute subprocesses from chat or the dashboard, install packages, call cloud services, or enable browser/desktop/MCP/terminal execution.

Phase 12M introduces specialist roles and skill workflow metadata. Specialist/skill/workflow selection is deterministic and local. It may show a safe next step, but it must not execute workflow actions, bypass FileAgent approval/confirmation gates, start browser/desktop automation, call cloud services, run shell commands, enable MCP, or broaden real file editing beyond Phase 12L.

## Capability System Role

The capability registry, permission matrix, and tool schema previews are discovery surfaces. They help Eva explain what exists, what is public-safe, what needs confirmation, and what is blocked. They do not add new execution behavior.

The natural router is deterministic and local in Phase 12G. It can route to existing safe commands, but it must not call cloud LLMs, route normal chat through v2, or bypass FileAgent path/content/approval/sandbox checks.

The Control Center capability is read-only metadata and UI. It can show local status and the dashboard URL, but it must not become an executor for MCP, Playwright, PyAutoGUI, browser control, desktop control, terminal execution, cloud calls, message sending, or real project/user file changes.

The narrow real-create gate is a gated file write allowed in Phase 12L. All other file writes remain blocked or sandbox-only. Exact phrases are required; vague confirmations such as "yes", "go ahead", or "do it" are not accepted.

Specialist and skill workflow capabilities are not authority escalations. They are human-readable routing and planning surfaces over the same permission model.

Phase 12N latest-state workflow handling is also not an authority escalation. It can look up local FileAgent approval/apply metadata, show safe candidate IDs and relative display paths, and recommend a next step. It must not guess when multiple candidates exist, and it must not execute real create or rollback without the existing exact confirmation phrases.

Phase 12O project inspection and reality checking are also not authority escalations. They can summarize local project status, recent Phase 12 changes, proof surfaces, broken-status evidence, and the next safe phase. They must not claim completion without fresh verifier output, run verifiers from chat, mutate git state, execute tools, read secrets, open browsers, control the desktop, call cloud services, or broaden the Phase 12L real-create gate.

Phase 12P upgrades Control Center visibility but not authority. It can show current phase/status, verifier health metadata, project/reality summary, specialists/skills/workflows, latest workflow state, approval counts, sandbox/latest real-create/rollback status, enabled real action, locked features, and the next safe step. It must not run verifiers, execute tools, enable browser/desktop/MCP/terminal/package/cloud behavior, send messages, read secrets, or expand real writes beyond Phase 12L narrow real create.

Phase 12Q adds WorkSession and audit timeline visibility but not authority. It can create sanitized local audit records for `eva ask` routing and show recent sessions, latest session, event timeline, blocked-action evidence, verification visibility, rollback visibility, and next safe step. It must not execute tools, run verifier subprocesses, open browsers, control desktop apps, call cloud services, enable MCP, install packages, send messages, read secrets, or expand real writes beyond Phase 12L narrow real create.

Phase 12R adds end-to-end golden workflow proof/status visibility but not authority. It can prove the safe FileAgent project-note path through approval, sandbox, exact 12L real create, verification, WorkSession timeline, Control Center status, and guarded rollback. It must not bypass approval, exact confirmation, target safety, verification, or rollback guards, and it must not expand real writes beyond Phase 12L narrow real create.

Phase 12S adds final readiness/status cleanup but not authority. It can show Phase 12 readiness, summary, limits, proof surfaces, and manual verifier commands. It must not run verifier subprocesses from chat, execute tools, mutate files, open browsers, control desktops, call cloud services, enable MCP, install packages, send messages, read secrets, or expand real writes beyond Phase 12L narrow real create.

Phase 13A adds BrowserAgent safety/status modeling but not browser authority. It can show browser status, policy, blocked actions, domain policy, readiness, and per-action safety previews. It must not launch browsers, navigate pages, click, type, submit forms, automate login/payment/upload/download, read cookies, read localStorage, read browser profiles, read passwords or sessions, take screenshots, watch the screen, enable Playwright/browser-use/Stagehand/Maxun, enable MCP, enable PyAutoGUI, run shell commands, install packages, call cloud services, or route normal chat through browser execution.

Phase 13B adds Browser Session Preview records but not browser authority. It can create local preview-only records, list previews, show latest preview status, explain future session lifecycle, and show readiness gaps. It must not launch browsers, open URLs, navigate pages, capture screenshots, read DOM/page content, click, type, submit, automate login/payment/upload/download, read cookies, read localStorage, read profiles, read passwords/tokens/sessions, enable Playwright/browser-use/Stagehand/Maxun, enable MCP, enable PyAutoGUI, control desktops, run shell/package commands, call cloud services, or route normal chat through browser execution.

Phase 13C adds page/text/DOM summary design but not browser observation authority. It can define summary schemas, create previews from user-provided/mock text only, explain future read-only page observation, show redaction/privacy rules, and show screenshot/DOM/live-read locked status. It must not read live pages, access DOM, capture screenshots, launch or navigate browsers, click/type/submit, automate login/payment/upload/download, read cookies/localStorage/profile/session/password/token data, enable Playwright/browser-use/Stagehand/Maxun, enable MCP, enable PyAutoGUI, control desktops, run shell/package commands, call cloud services, or route normal chat through browser execution.

Phase 13D adds browser action dry-run planning but not browser action authority. It can create text-only plans, explain risks, explain future approvals, show blocked execution, show future action lifecycle, and preview a plan from a user request. It must not launch browsers, navigate, read live pages, access DOM, capture screenshots, click, type, submit forms, automate login/payment/upload/download, read cookies/localStorage/profile/session/password/token data, enable Playwright/browser-use/Stagehand/Maxun, enable MCP, enable PyAutoGUI, control desktops, run shell/package commands, call cloud services, or route normal chat through browser execution.

Phase 13E adds BrowserAgent domain policy and site-risk modeling but not browser/network authority. It can classify user-provided domain or URL strings, show sensitive categories, blocked categories, and future approval requirements. It must not perform DNS or network calls, launch or navigate browsers, fetch live pages, access DOM, capture screenshots, click/type/submit, automate login/payment/upload/download, read cookies/localStorage/profile/session/password/token data, enable Playwright/browser-use/Stagehand/Maxun, enable MCP, enable PyAutoGUI, control desktops, run shell/package commands, call cloud services, or route normal chat through browser execution.

Phase 13F adds BrowserAgent read-only readiness proof but not read-only browser authority. It can prove that safety/session/observation/action/domain layers exist, list readiness gaps, show locked execution categories, and summarize the next browser phase. It must not launch browsers, navigate, perform DNS/network calls, fetch or read live websites, access DOM, capture screenshots, click/type/submit, automate login/payment/upload/download, read cookies/localStorage/profile/session/password/token data, enable Playwright/browser-use/Stagehand/Maxun, enable MCP, enable PyAutoGUI, control desktops, run shell/package commands, call cloud services, or route normal chat through browser execution.

Phase 13G hardens and closes BrowserAgent Phase 13 but does not add browser authority. It can show final Phase 13 status, summary, limits, readiness, and proof commands. It must state that Phase 13 is safety/readiness only, real browser read-only mode is not enabled, real browser control is not enabled, network/DNS/live page read/DOM/screenshot/action execution are locked, future real browser read-only mode needs a separate approved gate, and Phase 12L narrow real create remains a gated write path.

Phase 14A adds DesktopAgent safety/status modeling but not desktop authority. It can show desktop status, policy, blocked actions, action safety previews, app-risk string classification, and readiness gaps. It must not capture screens, take screenshots, inspect windows/apps, launch apps, move/click/drag the mouse, type, use hotkeys, read/write clipboard, automate file dialogs, run terminal/shell commands, install packages, send messages, read secrets/private desktop state, enable PyAutoGUI/Playwright/MCP, call cloud services, or route normal chat through desktop execution.

Phase 14B adds DesktopAgent session/app/window status previews but not desktop observation authority. It can create local preview-only session records, list latest preview sessions, show app/window/active-context schema previews, and explain observation readiness gaps. It must not capture screens, take screenshots, enumerate windows, inspect apps, detect active apps/windows, launch apps, move/click/drag the mouse, type, use hotkeys, read/write clipboard, automate file dialogs, run terminal/shell commands, install packages, send messages, read secrets/private desktop state, enable PyAutoGUI/Playwright/MCP, call cloud services, or route normal chat through desktop execution.

Phase 14C adds DesktopAgent screen observation policy but not screen observation authority. It can explain sensitive-screen categories, redaction rules, capture gate requirements, and readiness gaps. It must not capture screens, take screenshots, run OCR, perform image analysis, inspect windows/apps, detect active apps/windows, launch apps, move/click/drag the mouse, type, use hotkeys, read/write clipboard, automate file dialogs, run terminal/shell commands, install packages, send messages, read secrets/private desktop state, enable PyAutoGUI/Playwright/MCP, call cloud services, or route normal chat through desktop execution.

Phase 14D adds Desktop Action Dry-Run planning but not desktop action authority. It can create text-only plans, explain risk levels, explain future approval requirements, show blocked execution, and preview a plan from a user request. It must not capture screens, take screenshots, inspect windows/apps, launch or focus apps, move/click/drag the mouse, type, press hotkeys, read/write clipboard, automate file dialogs, run terminal/shell commands, install packages, send messages, read secrets/private desktop state, enable PyAutoGUI/Playwright/MCP, call browser/network/cloud services, or route normal chat through desktop execution.

Phase 14E adds Desktop Action Risk Scoring but not desktop action authority. It can calculate deterministic risk from request/app/screen/context strings, explain risk factors, approval levels, safety matrix decisions, high-risk actions, and readiness gaps. It must not observe screens, take screenshots, run OCR/image analysis, inspect windows/apps, detect active apps, launch/focus apps, move/click/drag the mouse, type, press hotkeys, read/write clipboard, automate file dialogs, run terminal/shell/package commands, read `.env` or secrets/tokens/cookies/passwords/browser sessions, enable PyAutoGUI/Playwright/MCP, call browser/network/cloud services, or route normal chat through desktop execution.

Phase 14F adds the Desktop Human Approval Model but not desktop action authority. It can preview approval levels, confirmation phrase classes, forbidden action classes, audit schema/status, and readiness gaps. Approval previews and confirmation phrases must not unlock real desktop execution, screen observation, app/window inspection, app launch/focus, mouse/keyboard/clipboard/file-dialog automation, terminal/shell/package execution, browser/network/cloud calls, PyAutoGUI/Playwright/MCP, or normal-chat desktop execution.

Phase 14G adds a final locked readiness proof, not an execution grant. It explicitly records that screen capture, screenshots, OCR/image analysis, real window/app inspection, UI target detection, mouse/keyboard/clipboard/file-dialog automation, terminal/package execution, browser/network execution, PyAutoGUI/Playwright/MCP/cloud calls, and secret/private-state reads remain locked. Approval previews never bypass those protections.

Phase 15A adds LLM router contracts without a call path. Provider names are metadata only; no API/network request, provider SDK, `.env`/`.env.local` read, secret access, or tool execution is authorized. The only usable Phase 15A route is a mock/dry-run decision and structured-output validation preview.

Phase 15B simulations do not change that boundary: fallback, degraded, limit, and audit behavior is deterministic mock/dry-run only. No live provider call, secret/config read, LLM-output tool execution, browser action, or desktop action is authorized.

## Phase 15C Structured Output Validation Hardening Boundary

Phase 15C is complete as a local validation boundary, not an execution grant. Malformed JSON, missing fields, invalid enums, unknown or hallucinated capabilities, secret-like output, private-path-like output, and tool-execution requests are rejected into safe refusal/preview results. Repair is instruction-only: it does not execute, rewrite user intent, or auto-correct unsafe content into executable actions. Live LLM/API calls, provider SDKs, `.env`/`.env.local`, secrets, tokens, cookies, passwords, and browser-session reads remain locked. Browser/desktop execution remains locked, and Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next: Phase 15D LLM Router Red-Team/Failure Tests.
## Phase 12J Golden Workflow Boundary

## Phase 15D LLM Router Red-Team / Failure Tests Boundary

Phase 15D is complete and remains local/mock only. Its unsafe-output cases classify prompt injection, policy-ignore attempts, hallucinated capabilities, secret/config/session exfiltration, private paths, oversized content, command injection, and browser/desktop/shell/cloud/MCP requests as safe failures. No live LLM/API/provider call, provider SDK, `.env`/`.env.local`/secret/token/cookie/password/browser-session read, tool execution, or browser/desktop execution is authorized. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next: Phase 16 Context Assembly Engine.

Phase 15E evidence lock detects any future weakening of those safe failures. It is deterministic, local/mock only, and cannot invoke providers, tools, browser/desktop/shell/cloud/MCP execution, secret/config/session reads, or a new write path.

## Phase 16 Context Assembly Engine Boundary

Phase 16 Context Assembly Engine is complete after this pass as a local/mock preview only boundary, not an execution grant. It performs no live LLM/API/provider calls, uses no provider SDKs, reads no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets, and arbitrary file reads are blocked. Context is source-aware, budget-aware, redaction-aware, permission-aware, and grounding-aware. Prompt-injection-like content is not trusted as instruction, assembled context cannot execute tools, and browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next phase is Phase 17 LLM Threat Defense + Prompt Injection Guard.

## Phase 17 LLM Threat Defense + Prompt Injection Guard Boundary

Phase 17 LLM Threat Defense + Prompt Injection Guard is complete after this pass as a local/mock preview only boundary, not an execution grant. It performs no live LLM/API/provider calls, no provider SDKs are used, reads no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets, and arbitrary file reads are blocked. untrusted context cannot override trusted policy/instruction hierarchy. prompt-injection-like content is treated as untrusted data, defended context cannot execute tools, and exfiltration and tool-request attempts fail safely. Browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next phase is Phase 18 Agent Loop v1.

## Phase 18 Agent Loop v1 Boundary

Phase 18 Agent Loop v1 is complete after this pass as a local/mock preview only boundary, not an execution grant. It performs no live LLM/API/provider calls, no provider SDKs are used, reads no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets, and arbitrary file reads are blocked. all actions are preview-only, agent loop cannot execute tools, and browser/desktop/shell/cloud/MCP execution remains locked. step limits, runaway detection, repeated-step detection, and no-progress stop behavior are enforced so repeated or stalled previews stop safely with a report. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next phase is Phase 19 Agentic Workflow Planner.

## Phase 19 Agentic Workflow Planner Boundary

Phase 19 Agentic Workflow Planner is complete after this pass as a local/mock preview only boundary, not an execution grant. It performs no live LLM/API/provider calls, no provider SDKs are used, reads no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets, and arbitrary file reads/writes are blocked. all workflow steps are preview-only, workflow planner cannot execute tools, and browser/desktop/shell/cloud/MCP execution remains locked. workflow dependency validation, precondition checks, approval previews, rollback previews, and verification plans are implemented so unsafe, cyclic, unsupported, or under-specified workflows fail safely as preview reports. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next phase is Phase 20 Controlled Execution Gates.

## Phase 20 Controlled Execution Gates Boundary

Phase 20 Controlled Execution Gates is complete after this pass as a local/mock policy preview only boundary, not an execution grant. execution gates are local/mock policy preview only. no live LLM/API/provider calls happen, no provider SDKs are used, and no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. tools are not executed. approval alone does not execute. confirmation alone does not execute unless an existing implemented gate accepts it. browser/desktop/shell/cloud/MCP execution remains locked. future gates are described but locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path. Next phase is Phase 21 Memory v3.

## Phase 21 Memory v3 Boundary

Phase 21 Memory v3 treats memory as untrusted, policy-filtered context rather than authority. Memory v3 is local-only; no live LLM/API/provider calls happen; no provider SDKs are used; no cloud memory or remote sync is used; no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read; raw memory database dumps are blocked; arbitrary file reads/writes are blocked. memory is source-aware, trust-aware, freshness-aware, privacy-aware, conflict-aware, and grounding-aware. memory cannot override system/developer/safety policy; memory cannot execute tools. sensitive, injected, stale, conflicting, or ungrounded memories are excluded or marked. context injection is preview/policy only. browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 22 Voice Assistant.

## Phase 22 Voice Assistant Foundation Boundary

Phase 22 Voice Assistant Foundation is complete after this pass and treats every mock transcript as untrusted input until local safety classification succeeds. voice is local/mock preview only; no microphone access, audio recording, or audio playback happens; no live ASR/TTS/provider calls happen; no provider SDKs are used; no real LLM/API/provider calls happen; no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read; arbitrary file reads/writes are blocked; voice commands cannot execute tools. transcript safety, provider policy, wake/listen state policy, and confirmation preview are implemented. browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 23 AI OS / Control Center Upgrade.

## Phase 23 AI OS / Control Center Upgrade Boundary

Phase 23 AI OS / Control Center Upgrade is complete after this pass and treats dashboard metadata as explanation rather than authority. AI OS dashboard is local/status/report only; no live LLM/API/provider calls happen; no provider SDKs are used; no web server, browser launch, desktop UI launch, or daemon is created; no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read; arbitrary file reads/writes are blocked; AI OS dashboard cannot execute tools. preview-only features remain preview-only; locked future gates remain locked; browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 24 Real Browser Read-Only Mode.

Golden workflows are safe orchestration wrappers, not new execution privileges.

Allowed:

- deterministic local draft generation
- FileAgent approval request creation
- sandbox apply, verify, and rollback through ignored runtime storage
- narrow real-create eligibility checks
- exact real-create confirmation for one new safe `.md` or `.txt` file
- hash verification and exact rollback for unchanged Eva-created files

Blocked:

- vague confirmations such as `yes`, `do it`, or `go ahead`
- broad file writes
- editing or overwriting existing files
- source/config/runtime writes
- browser/desktop control
- MCP, package installs, cloud calls, and normal-chat v2 execution

## Phase 24 Real Browser Read-Only Mode

Phase 24 Real Browser Read-Only Mode is complete after this pass. Browser mode is public-URL read-only observation only: no clicking, typing, forms, downloads, uploads, login, or browser control. URL policy blocks non-HTTP(S), local, private, link-local, metadata, internal, credential-bearing, sensitive, and command-injection-looking targets. Page text remains untrusted data under Phase 17. There is no logged-in browser profile/session/cookie access, and no provider SDKs or package installs. no real LLM/API/provider calls happen. no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. browser read-only observations cannot execute tools. browser control remains locked; desktop/shell/cloud/MCP execution remains locked. Deterministic mock observation is available, while real URLs return backend unavailable because no pre-existing safe backend exists. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 25 Real Desktop Observation Mode.

## Phase 25 Real Desktop Observation Mode

Phase 25 Real Desktop Observation Mode is complete after this pass. desktop mode is observation-only: no clicking, typing, hotkeys, app/window control, continuous monitoring, or screenshot saving. Captured text is untrusted data under Phase 17, and prompt-injection-like screen content cannot become instruction. There is no cookie/session/browser profile/password-manager access, and no provider SDKs or package installs. no real LLM/API/provider calls happen. no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. desktop observations cannot execute tools. sensitive screens are classified and redacted or blocked before output. browser control remains locked; desktop control remains locked; shell/cloud/MCP execution remains locked. Deterministic mock observation is available, while real desktop observation returns backend unavailable because no pre-existing safe backend exists. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 26 Real Desktop Control Gate.

## Phase 26 Real Desktop Control Gate

Phase 26 Real Desktop Control Gate is complete after this pass. desktop control is dry-run/gate-only: no clicking, typing, hotkeys, clipboard, app/window control, automation, or shell execution happens. Sensitive-screen context raises risk or blocks; credentials, secrets, sessions, destructive actions, unknown capabilities, shell, package, cloud, and MCP actions are denied. no provider SDKs or package installs were added; no real LLM/API/provider calls happen. no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read. arbitrary file reads/writes are blocked. approval alone does not execute. confirmation alone does not execute. rollback/audit are metadata only. desktop observation remains observation-only; browser control remains locked; shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 27 News/Web Intelligence Dashboard.

## Phase 27 News / Web Intelligence Dashboard
Phase 27 News / Web Intelligence Dashboard is complete after this pass. dashboard is local/mock by default. Unrestricted crawling, recursive crawling, login scraping, sessions/cookies/profiles, private URLs, and browser control remain blocked. Source freshness, reliability, uncertainty, and citation metadata are tracked; Phase 24 public URL read-only policy is respected and Phase 17 treats source text as untrusted. No provider SDKs, package installs, real LLM/API/provider calls, secret/config/session reads, arbitrary file reads/writes, tool execution, or browser/desktop/shell/cloud/MCP execution was added. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 28 Coding Specialist / CodingAgent.

## Phase 28 Coding Specialist / CodingAgent Foundation

Phase 28 Coding Specialist / CodingAgent Foundation is complete after this pass. Coding requests are treated as untrusted input and classified into deterministic preview/report/status workflows. Execution-seeking, secret-seeking, arbitrary-file, raw-dump, and hallucinated-capability requests fail closed. Project context comes only from existing safe metadata/status/documentation summaries; raw source is not exposed.

Source editing, patch application, arbitrary code execution, shell/test/package/git operations, arbitrary filesystem reads/writes, and tool execution remain blocked. No provider SDKs or package installs were added. No real LLM/API/provider calls happen, and no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, config secrets, raw WorkSession dumps, or raw memory database dumps are read. Browser/desktop/shell/cloud/MCP execution remains locked. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Next phase is Phase 29 Public Demo / Release.

## Phase 29 Public Demo / Release

Phase 29 Public Demo / Release is complete after this pass. The release-demo layer uses static in-memory metadata and deterministic formatting. It has no arbitrary file reader, secret/config/session reader, network client, provider SDK, tool executor, publishing client, package builder, installer builder, git release operation, browser controller, desktop controller, crawler, or external-send path.

No publishing/uploading/commit/tag/push happened. No provider SDKs or package installs were added. No real LLM/API/provider calls happen. No `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, config secrets, raw source dumps, raw WorkSession dumps, or raw memory database dumps are read. Arbitrary filesystem reads/writes remain blocked. CodingAgent remains preview/report/status only; News remains local/mock or safe-read-only; Voice remains locked/mock; browser/desktop/shell/cloud/MCP execution remains locked.

Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path. Phase 29 handed off to Phase 30 Release Candidate Hardening; the current next safe step is user-approved commit execution outside Eva or a separate explicit commit-approval phase.
