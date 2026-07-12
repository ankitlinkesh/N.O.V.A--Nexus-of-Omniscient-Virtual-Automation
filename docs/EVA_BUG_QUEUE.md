# Eva Bug Queue

> **Current-state correction (2026-07-12).** Entries below that say "Phase 12L
> ... only real write path" or "execution remains locked" are historical and no
> longer accurate. Eva executes whitelisted tools and gates destructive/privacy/
> external ones behind explicit user approval via `ToolRegistry.run()`. Run
> `eva capability truth` for the code-derived boundary.

Last updated: 2026-06-01

Use this queue as a stabilization handoff. Before fixing, reproduce from the current repo and prefer capability routing, skill routing, planner/tool integration, and grounded system awareness over broad fast-command patches.

## Current Phase 6.1 Notes

The original live-test bugs below have been patched and covered by verifiers where possible. Keep them here as regression tests rather than assuming they are permanently gone.

Known intentional limitations after Phases 1-6:

- Normal chat is not routed through v2 by default.
- MCP, Playwright, and PyAutoGUI execution are disabled.
- Confirmed risky pending actions do not execute yet.
- WhatsApp/message send, file write/edit/delete, arbitrary shell, and raw desktop clicks remain unavailable or refused.
- Safe Code Index v2 is metadata-only and lexical; it is not semantic vector search.

Phase 28 regression boundary:

- CodingAgent is preview/report/status only. Source edits, patch application, shell/test/package/git execution, arbitrary file access, live provider calls, and tool execution remain intentionally unavailable.
- Coding plans, reviews, test plans, risk reviews, and handoffs must remain deterministic previews, and Phase 12L remains the only real file write path.

Phase 29 regression boundary:

- Public demo/release commands are documentation/report/status/profile only and must never publish, upload, package, commit, tag, push, or execute external actions.
- Public-facing output must remain honest about locked browser/desktop control, preview-only CodingAgent behavior, local/mock News and Voice foundations, and checkout-specific verifier evidence.
- Phase 12L remains the only real file write path; Release Candidate Hardening or commit planning requires separate user approval.

## EVA-001: Architecture answer still needs more grounding

- command: `explain your full architecture`
- actual: Stabilized through capability routing and file-path grounded architecture summaries; keep testing for drift as new systems land.
- expected: Eva should explain the active architecture with concrete files such as `backend/eva/api/routes.py`, `backend/eva/core/intent_router.py`, `backend/eva/tools/registry.py`, `backend/eva/agent/runner.py`, `backend/eva/llm/router.py`, `backend/eva/memory/store.py`, `backend/eva/browser/`, `backend/eva/desktop/`, `backend/eva/research/`, `backend/eva/code/`, `backend/eva/vision/`, and `frontend/`.
- likely area: `backend/eva/core/intent_router.py`, `backend/eva/api/routes.py`, `backend/eva/diagnostics/health.py`, `backend/eva/code/`, `scripts/verify_capability_routing.py`, `scripts/verify_self_diagnostics.py`.

## EVA-002: Voice sometimes stops midway

- command: Use browser push-to-talk or voice playback for a medium/long Eva answer.
- actual: Voice UI was patched to speak final displayed replies or intentional summaries only; keep this as a regression test for browser SpeechSynthesis behavior.
- expected: Speech should continue until the displayed assistant reply is fully spoken or until the user intentionally stops it.
- likely area: `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`, `backend/eva/api/routes.py` TTS endpoints, `backend/eva/voice/piper.py`, `scripts/verify_voice_ui.py`.

## EVA-003: Voice sometimes starts from the middle or inside a word

- command: Trigger voice playback for a fresh Eva response, especially after previous playback or interruption.
- actual: Voice UI was patched to keep a global active utterance and start from the final response beginning; keep as a regression test.
- expected: Speech should start at the first character/word of the current assistant reply.
- likely area: frontend speech queue/state management in `frontend/app.js`, browser SpeechSynthesis handling, push-to-talk state transitions, `scripts/verify_voice_ui.py`.

## EVA-004: Voice sometimes speaks different text than the screen

- command: Ask Eva a prompt that renders text on screen and triggers voice playback.
- actual: Voice UI was patched to avoid tool/status/activity event speech and partial stream chunks; keep as a regression test.
- expected: TTS should speak the exact current assistant reply or a clearly intentional sanitized version of it.
- likely area: `frontend/app.js` response streaming/TTS coupling, `/api/chat/stream` events in `backend/eva/api/routes.py`, `backend/eva/voice/piper.py`, `scripts/verify_voice_ui.py`.

## EVA-005: Technical terms are pronounced badly

- command: Ask Eva to speak text with terms such as `OS`, `.exe`, repo-relative paths, `OpenRouter`, `NVIDIA NIM`, or Windows paths.
- actual: Speech-safe replacements were added for common technical text; keep as a regression test for new voice paths.
- expected: Voice output should normalize common technical tokens into speakable text without changing the on-screen reply.
- likely area: TTS text normalization in `frontend/app.js` and/or `backend/eva/voice/piper.py`; add coverage to `scripts/verify_voice_ui.py`.

## EVA-006: OpenRouter/OpenRoute confusion needs retest

- command: `test OpenRouter API` and `openrouter API is built in within u`
- actual: Provider diagnostics routing is covered by capability verifiers and should not route to maps/web search.
- expected: OpenRouter should route to provider diagnostics; OpenRoute/OpenRouteService map-routing concepts should not be confused with Eva's LLM provider.
- likely area: `backend/eva/core/intent_router.py`, `backend/eva/diagnostics/providers.py`, `backend/eva/api/routes.py`, `scripts/verify_capability_routing.py`, `scripts/verify_self_diagnostics.py`.

## EVA-007: Some capability questions may fall through to generic LLM chat

- command: Ask capability questions such as `what systems do you have`, `what page am I on`, `what window am I on`, `where is browser agent implemented`, or `what do we know about NVIDIA NIM`.
- actual: Improved through capability routing, browser live-state handling, Safe Code Index v2 read-only delegation, and diagnostics/status commands; keep testing for new fallthroughs.
- expected: Capability questions should route to deterministic diagnostics, capability routes, agentic skills, or safe tools as appropriate, with file/tool/source grounding where relevant.
- likely area: `backend/eva/core/capabilities.py`, `backend/eva/core/intent_router.py`, `backend/eva/api/routes.py`, `backend/eva/core/fast_commands.py`, `backend/eva/agent/policies.py`, `backend/eva/tools/registry.py`, `scripts/verify_capability_routing.py`.

## Phase 30 release-candidate audit

Phase 30 Release Candidate Hardening / Commit Planning is complete after this pass. Phase 30 is report/status/planning only. The commit plan is text only.

- Blocking release-candidate issues: none after the focused and master verification sweep passes.
- Non-blocking warning: ignored `.env` and `.env.local` filenames exist; contents were not read.
- Non-blocking warning: the Phase 30 tree remains intentionally uncommitted for user review.
- Next safe action: user-approved commit execution outside Eva or a separate explicit commit-approval phase.

For Phase 30, no git add/commit/tag/push was performed and no publishing/uploading was performed. No provider SDKs or package installs were added. No real LLM/API/provider calls happen. Arbitrary file reads/writes remain blocked; browser/desktop/shell/cloud/MCP and tool execution remain locked.

No secrets, tokens, cookies, passwords, browser sessions, or config contents are read. CodingAgent remains preview/report/status only. News remains local/mock or safe-read-only. Voice remains a locked/mock foundation. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real write path.

## Phase 32 post-push/demo-smoke audit

Phase 32 Post-Push Sync + Demo Smoke Test Hardening is complete after this pass.

- Blocking demo smoke issues: none after `scripts/verify_eva_post_push_demo_smoke.py` and the master quick/full profiles pass.
- Known warning: GitHub network/auth state can block `git fetch --dry-run origin`; do not pull, merge, rebase, reset, checkout, clean, force push, tag, or release automatically.
- Remote moved warning was handled by updating local origin to `https://github.com/ankitlinkesh/eva-community.git`.

No commit/push/tag/release was performed in Phase 32. Demo smoke test is report/status/checklist only. No provider SDKs or package installs. No real LLM/API/provider calls happen. No `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config contents are read. No secrets, tokens, cookies, passwords, browser sessions, or config contents are read.

Browser/desktop/shell/cloud/MCP execution remains locked. CodingAgent remains preview/report/status only. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real file write path.

## Phase 33-42 roadmap audit

Phase 33 Execution Boundary Audit is complete as a foundation after this pass.

- Blocking roadmap-foundation issues: none after `scripts/verify_eva_phase33_roadmap_foundations.py` and the master quick profile pass.
- Regression target: command, capability, resource, schema, planner, frontend, and docs status must not drift apart as Phase 34 through Phase 42 work lands.
- Regression target: `eva execution boundaries` must keep risky runtime tool-registry surfaces classified as gated real actions or blocked; safe demo/status commands must stay report-only.
- Regression target: frontend quick chips must prefer safe demo/report-only commands over broad real-control examples.

Execution boundary audit status: no new execution path is enabled. Phase 41 remains blocked until a later explicit approval phase. Phase 42 Release Candidate v2 Hardening is documentation/verification hardening only and does not tag, release, upload, publish, package, deploy, or push anything.

No provider SDKs or package installs were added. No real LLM/API/provider calls happen. No `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config contents are read. Browser/desktop/shell/cloud/MCP execution remains locked. CodingAgent remains preview/report/status only. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real file write path.
