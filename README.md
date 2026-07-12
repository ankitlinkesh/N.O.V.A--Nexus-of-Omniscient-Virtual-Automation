# Eva Agent

Eva is a source-available, local-first desktop AI agent foundation built with Python, FastAPI, and a browser-based command center. It combines deterministic commands, bounded planning, capability metadata, local memory foundations, and explicit safety gates.

Eva is not presented as an unrestricted autonomous operator. The public demo is designed to show what is implemented, what remains locked, and which evidence should be refreshed before a release decision.

## What Is Eva?

- A modular foundation for local laptop-assistant workflows.
- A deterministic command system with human-readable status and refusal paths.
- A bounded planner and agent loop with stop, verification, and risk-review concepts.
- A capability registry with permission, resource, schema, and verifier metadata.
- A local/mock-first architecture for demonstrating future browser, desktop, voice, coding, and research workflows safely.

## Current Verified Status

The repository contains the Phase 32 safe local demo smoke layer and the Phase 33 roadmap-foundation layer. These are report/status/documentation/catalog surfaces only and are considered ready for local demo review only after the focused, quick, and full verifier commands below pass in the current checkout.

These specific report/status phases add no new execution path: no publication, upload, package release, installer, commit, tag, or push is performed by them, and they enable no new tool. (This is scoped to the report/status phases — see the Execution Model section below for what Eva does execute.)

## Execution Model

Eva is not execution-free. It runs a whitelisted set of local tools and makes real LLM provider calls. What keeps this safe is not the absence of execution but a central permission gate — every tool call goes through `ToolRegistry.run()`, which classifies it and enforces approval; a `confirmed` argument carries no authority.

- **Runs immediately:** safe, bounded local reads and observation, plus a whitelist of UI/browser/app actions the planner may choose (open a URL/app, media keys, window and tab control, workspace/code/research reads).
- **Requires explicit confirmation or override:** privacy reads, destructive file actions, screen input (type/hotkey/press), and external messages. These return a pending-action ledger id and run only after a user types `confirm <id>` / `confirm override <id>`.
- **Not reachable by the LLM planner:** destructive file tools and screen-input tools are registered but excluded from the planner whitelist; they run only via the local, header-guarded `/api/tools` endpoint and still pass the gate.
- **Live provider calls:** real LLM API calls happen when keys are configured (NVIDIA NIM, Gemini, OpenRouter, Groq, CLoD) with local Ollama fallback.

For the exact, code-derived picture (never hand-maintained), run `eva capability truth`.

## Capabilities

- FileAgent inspection, drafts, approval metadata, and sandbox previews.
- Phase 12L narrow approved creation of one new `.md` or `.txt` file under `docs/` or `samples/`.
- Bounded planner, agent-loop, workflow, context, threat-defense, and memory previews.
- Browser public-URL read-only observation reports; browser control remains locked.
- One-shot redacted desktop observation reports; desktop control remains locked.
- Desktop-control policy and dry-run gate reports without real control.
- News/Web Intelligence local/mock or safe-read-only reports.
- CodingAgent classification, patch-plan, review, test-plan, risk, and handoff previews without source editing.
- Voice Assistant locked/mock foundation without microphone or audio execution.

## Demo Commands

```text
eva capability truth
eva release status
eva release demo
eva release commands
eva release capability map
eva release safety proof
eva release readiness
eva release limitations
eva release verification
eva release smoke test
eva release post push sync
eva roadmap status
eva execution boundaries
eva catalog status
eva frontend truth status
eva grounded answer status
eva voice reliability status
eva verifier dashboard status
```

These commands return deterministic local text. They do not publish, execute tools, inspect private sessions, or unlock restricted features.

## Safe Local Demo

Phase 32 adds a safe local demo smoke layer for a fresh user/demo run. Use `eva release smoke test` to show the demo-smoke checklist and `eva release post push sync` to show the post-push sync status. These are report/status/checklist only.

To verify Eva without enabling unsafe features:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_post_push_demo_smoke.py
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --quick --timeout 90
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --full --timeout 90
```

No provider SDKs or package installs are needed. No real LLM/API/provider calls happen. No `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config contents are read. Browser/desktop/shell/cloud/MCP execution remains locked. CodingAgent remains preview/report/status only. Phase 12L narrow approved new `.md`/`.txt` creation remains the only real write path.

## Phase 33-42 Roadmap Foundations

Phase 33 starts the execution boundary audit and typed catalog foundation for the Phase 33 through Phase 42 improvement roadmap. Phase 42 remains Release Candidate v2 hardening and does not publish, tag, release, upload, or deploy anything.

Roadmap status commands:

```text
eva roadmap status
eva execution boundaries
eva catalog status
eva frontend truth status
eva grounded answer status
eva voice reliability status
eva verifier dashboard status
```

These commands are report/status/catalog only. They classify existing runtime surfaces, document risky tool boundaries, and expose the next phase plan without enabling a new execution path. Phase 12L remains the only real project write boundary.

Additional established safety demonstrations remain available:

```text
eva public checklist
eva public hardening status
eva demo scenarios
eva demo run whatsapp-confirmation
eva safety test read .env.local
eva doctor public
```

## Run Locally

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.eva.main:app --host 127.0.0.1 --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

Private settings can be created from `.env.example`. Never commit or display private environment files.

## Verification

Run the Phase 29 verifier:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_public_demo_release.py
```

Run the Phase 33 roadmap-foundation verifier:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_phase33_roadmap_foundations.py
```

Run both master profiles:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --quick --timeout 90
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --full --timeout 90
```

Finish with:

```powershell
git diff --check
git status --short
```

These commands provide local evidence only. They do not publish or certify production security.

## Safety Boundaries

- No unrestricted shell or arbitrary command execution (SHELL_ACTION is hard-blocked).
- No browser login, upload, download, cookie, profile, or session control. Eva can open URLs and do bounded tab/window control; it does not automate form-filling or logged-in actions.
- Desktop and screen input (click/type/hotkey) require explicit confirmation and are not planner-reachable; there is no continuous monitoring.
- No unrestricted crawler.
- No CodingAgent source editing or patch application.
- No public-demo live LLM/API/provider call.
- No cloud or MCP execution.
- No microphone, audio recording, playback, ASR, or TTS execution in the voice foundation.
- No secret, configuration, session, raw memory database, or private WorkSession dump exposure.
- No broad filesystem mutation: file writes/patches/moves/deletes are gated (require override), path-restricted to the project and Documents/Desktop/Downloads, and deny `.env*`, `.git`, `*.sqlite3`, and key files.
- No secret exfiltration: the path allowlist blocks reading or writing secret/config/database files by name.

## Known Limitations

- The public demo is a local report/status profile, not a hosted service.
- Browser and desktop backends may report unavailable while preserving safe mock/status behavior.
- News is local/mock or safe-read-only; it is not unrestricted web crawling.
- CodingAgent creates plans and reviews only.
- Voice remains a locked/mock foundation.
- Verification evidence is checkout-specific and must be refreshed before release review.
- Phase 29 does not create a release candidate, commit, tag, installer, package, or upload.

## Non-Goals

- Unrestricted autonomy or self-modifying code.
- Silent background monitoring.
- Production-security certification.
- Automatic publication or deployment.
- Automatic messaging, purchasing, submitting, or destructive file actions.
- Claims that locked or preview-only features are real execution capabilities.

## License

Eva is source-available under the PolyForm Noncommercial License 1.0.0.

Non-commercial use is allowed. Commercial use, resale, paid redistribution, hosted commercial services, or selling modified versions requires separate written permission from the author.
