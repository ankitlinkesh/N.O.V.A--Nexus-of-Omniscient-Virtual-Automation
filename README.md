# N.O.V.A

**Nexus of Omniscient Virtual Automation** — a source-available, local-first desktop AI agent built with Python, FastAPI, and a browser-based command center.

N.O.V.A is not presented as an unrestricted autonomous operator. Everything it can do runs through one central permission gate, and this document is written to state exactly what is real, what is flag-gated, and what is still a stub.

> **Naming note.** The product is N.O.V.A. The internal Python package, the `EVA_*` environment flags, and the `eva …` console commands keep their original names — that is an implementation detail, and renaming 600+ modules would add risk without adding value. Where this README shows a literal command, it is the command you actually type.

## What Is N.O.V.A?

- A private, local-first desktop agent: your machine, your files, your keys.
- A deterministic command system with human-readable status and refusal paths.
- A bounded plan → act → observe → reflect agent loop with recovery, self-verification, an independent critic, and budget stops.
- A capability registry where **every tool call passes a central permission gate** that classifies it and enforces approval.
- An adversarial security model: untrusted content can propose, never authorize.

## Execution Model

N.O.V.A is **not execution-free**. It runs a whitelisted set of local tools and makes real LLM provider calls. What keeps this safe is not the absence of execution but the gate — every tool call goes through `ToolRegistry.run()`, which classifies it and enforces approval; a `confirmed` argument passed by the model carries no authority.

- **Runs immediately:** bounded local reads and observation, plus a whitelist of UI/app actions the planner may choose (open a URL/app, media keys, window and tab control, workspace/code/research reads).
- **Requires explicit confirmation or override:** privacy reads, destructive file actions, screen input (type/hotkey/press), and external messages. These return a pending-action ledger id and run only after you type `confirm <id>` / `confirm override <id>`.
- **Not reachable by the LLM planner:** destructive file tools and screen-input tools are registered but excluded from the planner whitelist; they run only via the local, header-guarded `/api/tools` endpoint and still pass the gate.
- **Hard-blocked:** unrestricted shell / arbitrary command execution.
- **Live provider calls:** real LLM API calls happen when keys are configured (NVIDIA NIM, Gemini, OpenRouter, Groq, CLoD) with local Ollama fallback.

For the exact, code-derived picture (never hand-maintained), run `eva capability truth`. For which LLM providers actually work right now, run `llm doctor`.

## Capabilities

Real capabilities, and the flag each needs. **Default is off**: a fresh checkout enables none of the physical or external ones.

| Capability | Status | Flag |
|---|---|---|
| Chat, planning, deterministic commands | on | — |
| Local SQLite memory (chat, events, tools) | on | — |
| Permission gate + confirmation ledger | always on | — |
| Flight-recorder tracing of every decision | opt-in | `EVA_TRACING_ENABLED` |
| Semantic memory (Chroma, CPU embeddings) | opt-in | `EVA_V2_VECTOR_MEMORY_ENABLED` |
| Native function-calling planner | opt-in | `EVA_NATIVE_FUNCTION_CALLING` |
| Durable user model (learned facts/preferences) | opt-in | `EVA_USER_MODEL_ENABLED` |
| Situational awareness (foreground app; **metadata only, never pixels**) | opt-in | `EVA_PERCEPTION_ENABLED` |
| Durable task queue (survives crash/reboot) | opt-in | `EVA_DURABLE_QUEUE_ENABLED` |
| Proactive rules (schedules, file watchers) | opt-in | `EVA_PROACTIVITY_ENABLED` |
| Learned skills (compose existing tools) | opt-in | `EVA_SELF_IMPROVEMENT_ENABLED` |
| **Real mouse/keyboard input** | opt-in, gated | `EVA_ENABLE_REAL_INPUT` |
| **Real browser control** (Playwright) | opt-in, gated | `EVA_V2_PLAYWRIGHT_ENABLED` |
| **MCP servers** (external tools) | opt-in, gated | `EVA_MCP_ENABLED` |
| **Text-to-speech** — real, fully local (Piper, bundled exe + on-disk voice model; no audio leaves the machine) | on | `EVA_TTS_PROVIDER=piper` |
| **Speech-to-text** — real, fully local (faster-whisper/CTranslate2, no torch; no audio leaves the machine) | opt-in | `EVA_VOICE_INPUT_ENABLED` |
| **Wake word + mic capture** — real, fully local (openWakeWord ONNX; nothing is transcribed before the wake word) | opt-in | `EVA_VOICE_INPUT_ENABLED` |

`EVA_PROFILE=daily` turns on the side-effect-free "mind" capabilities in one switch. **No profile may ever auto-enable real input, the browser, or MCP** — those stay opt-in one flag at a time, by design and enforced by a verifier.

## How It Stays Trustworthy

The load-bearing ideas, each enforced by tests and a verifier:

- **One gate.** Every tool call is classified and approved in a single place. Self-approval is impossible: `confirmed`/`_approved` arguments from the model are stripped.
- **Verification-first.** An action isn't "done" because it returned — every action declares a post-condition checked against real state, and N.O.V.A reports provenance (verified / self-reported / unverified) rather than claiming an unproven action.
- **Untrusted content proposes, never authorizes.** Web/file/MCP content is taint-tracked; injected content that tries to steer a privileged action forces an escalation instead.
- **Least privilege per task**, a secrets broker (secrets are referenced by name and never enter model context), and a pinned-trust model for MCP servers.
- **An independent critic** re-derives whether the goal was actually met from real evidence, rather than trusting the planner's "done".
- **Trust that scales carefully.** Approval history can de-escalate only a strict allowlist of action types — never destructive, privacy, external-send, or power actions, no matter how many approvals exist.
- **Proactivity proposes, never acts.** A rule that fires at 3am only enqueues a request and notifies; the work still faces the gate.
- **Self-improvement composes, never escalates.** A learned skill is a sequence of tools that *already exist* — N.O.V.A never writes code — so learning adds convenience, never capability.

## Demo Commands

```text
eva capability truth
llm doctor
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

Newer subsystems (each reports "off" unless its flag is set):

```text
activation status        traces list            evals status
user model               consolidate memory     situation
queue status             queue recover          notifications
rules                    check triggers         learned skills
learn skills             approve skill <name>   run skill <name>
```

These commands return deterministic local text. They do not publish or unlock restricted features.

## Safe Local Demo

Use `eva release smoke test` to show the demo-smoke checklist and `eva release post push sync` to show the post-push sync status. These are report/status/checklist only and add **no new execution path**.

To verify Eva without enabling unsafe features:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_post_push_demo_smoke.py
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --quick --timeout 90
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --full --timeout 90
```

The verifier suite makes no real LLM/API/provider calls and reads no `.env`, `.env.local`, secrets, tokens, cookies, or browser sessions. With no flags set, browser/desktop/MCP execution stays off.

## Phase 33-42 Roadmap Foundations

Phase 33 started the execution boundary audit and typed catalog foundation for the Phase 33 through Phase 42 improvement roadmap. Phase 42 was Release Candidate v2 hardening and does not publish, tag, release, upload, or deploy anything.

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

These commands are report/status/catalog only. They classify existing runtime surfaces and document risky tool boundaries without enabling a new execution path.

## What Has Been Built

Delivered in order; each phase shipped with tests, an offline eval, and a dedicated verifier.

| Phase | What it added |
|---|---|
| 32 | **Real hands** — mouse/keyboard via pyautogui and a real headless browser via Playwright, both flag-gated and SSRF-guarded. |
| 33 | Native function-calling plumbing, wired to Gemini's own format and proven live. |
| 34 | **MCP client** — external tool servers; every MCP tool is confirm-class. |
| 35 | **Semantic memory** — Chroma with bundled CPU embeddings (no torch). |
| 36 | **Observability + eval harness** — a flight recorder for every plan/step/tool/decision, plus a CI-safe offline eval suite. |
| 37 | **Activation profiles** — one safe switch to turn the "mind" on, which can never enable hands or external reach. |
| 38 | **Verification-first execution** — declared post-conditions, independently checked, with honest provenance. |
| 39 | **Reliability** — the loop recovers from failures within a budget instead of dying on the first one. |
| 40 | **The adversarial moat** — prompt-injection taint tracking, least-privilege tool scope, secrets broker, MCP trust model, red-team suite. |
| 41 | **Critic + delegation contracts** — completion judged on evidence, not the planner's claim. |
| 42 | **Calibrated autonomy** — learned trust policies, confidence-aware escalation, mid-task interruptibility. |
| 43 | **Memory that learns** — a durable, compounding user model that refuses secrets and injected content. |
| 44 | **Perception & grounding** — situational awareness from window metadata, never pixels; sensitive titles redacted. |
| 45 | **Durable task queue** — work survives a crash or reboot; recovery replays a request, never an approval. |
| 46 | **Proactivity** — schedules and file watchers that propose work but never authorize it. |
| 47 | **Self-improvement** — learned skills that compose existing gated tools; N.O.V.A never writes code. |
| 48 | **Provider diagnostics** — `llm doctor` makes LLM provider rot visible instead of silent. |

| 49a | **Voice input** — local speech-to-text (faster-whisper/CTranslate2, no torch). Off by default; the microphone is opt-in one flag at a time and no profile may enable it. |

Already working outside that arc: **local text-to-speech** (Piper, bundled binary + `en_US-ryan-high` male voice model, fully offline). The loop is closed end to end — N.O.V.A's own spoken output transcribes back correctly.

Not yet built: **wake word + continuous mic capture** (Phase 49b) and a **native shell** (tray app + global hotkey).

## Run Locally

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.eva.main:app --host 127.0.0.1 --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

Private settings can be created from `.env.example`. `.env` and `.env.local` are gitignored — never commit or display private environment files.

## Verification

The verifier suite is load-bearing: it is the executable specification of the safety model, and it has caught real regressions. Run both master profiles:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --quick --timeout 90
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --full --timeout 90
```

Run the pytest safety suite (permission gate, ledger, path allowlist, injection defense, skill escalation):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Individual verifiers, for example:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_public_demo_release.py
.\.venv\Scripts\python.exe scripts\verify_eva_phase33_roadmap_foundations.py
```

Finish with:

```powershell
git diff --check
git status --short
```

These commands provide local evidence only. They do not publish or certify production security.

## Safety Boundaries

- **No unrestricted shell or arbitrary command execution** (SHELL_ACTION is hard-blocked).
- **No self-approval:** a `confirmed`/`_approved` argument from the model is stripped and carries no authority.
- **No browser login, upload, download, cookie, profile, or session control.** With the browser enabled, N.O.V.A can open URLs and do bounded snapshot/click/type; clicks and typing are confirm-class, private hosts are blocked, and it does not automate logged-in actions.
- **Every screen capture requires confirmation.** `capture_screen`, `analyze_screen` and `screen.observe` are all classified PRIVACY_SCREEN_READ (override-class): the planner may propose looking at your screen, but the gate holds it until you approve. No allow-class tool has a pixel path — `desktop_observe` returns window metadata only. There is no continuous monitoring.
- **Desktop and screen input (click/type/hotkey) require explicit confirmation** and are not planner-reachable.
- **No broad filesystem mutation:** writes/patches/moves/deletes are gated (require override), path-restricted to the project and Documents/Desktop/Downloads, and deny `.env*`, `.git`, `*.sqlite3`, and key files.
- **No secret exfiltration:** the path allowlist blocks reading secret/config/database files by name, and the secrets broker scrubs live secret values out of anything sent to a model or a trace.
- **No unattended privileged action:** proactive rules and durable-queue recovery replay a *request*, never an approval.
- **No self-written code:** learned skills may only compose tools that already exist.
- **Nothing is ever listening.** There is no wake word and no continuous capture; speech-to-text only runs on a buffer it is explicitly handed, and only when `EVA_VOICE_INPUT_ENABLED` is set. No activation profile may enable the microphone — like real input and the browser, it is opt-in one flag at a time.
- **Voice is fully local, in both directions.** Piper (speech out) and faster-whisper (speech in) both run on-device; no audio and no transcript is ever sent to a speech service. A transcript is treated exactly like typed text: it faces the same planner and the same permission gate, so speaking a command earns no privilege that typing it would not.
- MCP execution is off unless enabled, and then only for servers pinned as trusted, with per-server call budgets.

## Known Limitations

- Voice works in both directions and hands-free (wake word -> speech-to-text -> reply -> speech), all locally. The wake phrase is `hey_jarvis`: openWakeWord ships pretrained models for a handful of phrases and "hey nova" is not one of them, so a custom phrase needs a trained model. Set `EVA_WAKE_WORD` to pick another.
- The default speech-to-text model is `base`, which fumbles proper nouns (it hears "NOVA" as "Nola"); set `EVA_STT_MODEL=small` for better accuracy at ~250MB.
- There is no native shell yet — it runs as a local web app.
- OpenRouter and CLoD are currently non-functional (dead key / bad model id); run `llm doctor` for live status.
- Proactivity has no background ticker: rules are evaluated on startup and on demand.
- Learned-skill proposals are mined from traces and require your approval; there is no natural-language rule creation yet.
- Verification evidence is checkout-specific and must be refreshed before any release review.
- The permission gate is the security model. It has not been externally audited.

## Non-Goals

- Unrestricted autonomy or self-modifying code.
- Silent background monitoring.
- Production-security certification.
- Automatic publication or deployment.
- Automatic messaging, purchasing, submitting, or destructive file actions.
- Claims that locked or preview-only features are real execution capabilities.

## License

N.O.V.A is source-available under the PolyForm Noncommercial License 1.0.0.

Non-commercial use is allowed. Commercial use, resale, paid redistribution, hosted commercial services, or selling modified versions requires separate written permission from the author.
