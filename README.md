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
| **GUI grounding** (click/fill by label via the accessibility tree) | opt-in, gated | `EVA_GUI_GROUNDING_ENABLED` |
| **Credential vault** (saved logins/personal fields, DPAPI-encrypted; never reaches the model) | opt-in | `EVA_VAULT_ENABLED` |
| **Real mouse/keyboard input** | opt-in, gated | `EVA_ENABLE_REAL_INPUT` |
| **Real browser control** (Playwright) | opt-in, gated | `EVA_V2_PLAYWRIGHT_ENABLED` |
| **MCP servers** (external tools) | opt-in, gated | `EVA_MCP_ENABLED` |
| **Text-to-speech** — real, fully local (Piper, bundled exe + on-disk voice model; no audio leaves the machine) | on | `EVA_TTS_PROVIDER=piper` |
| **Speech-to-text** — real, fully local (faster-whisper/CTranslate2, no torch; no audio leaves the machine) | opt-in | `EVA_VOICE_INPUT_ENABLED` |
| **Wake word + mic capture** — real, fully local (openWakeWord ONNX; nothing is transcribed before the wake word) | opt-in | `EVA_VOICE_INPUT_ENABLED` |
| **Hands-free voice turn** (`POST /api/chat/voice`: wake → transcribe → same chat pipeline) | opt-in | `EVA_VOICE_INPUT_ENABLED` |

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
llm doctor
```

Typed-console entries that create or drive real work. These are **deliberately not planner tools**, so untrusted content (a web page, a file, an MCP result) can never reach them:

```text
remind me every morning to summarize my news     (creates a proactive rule)
rules                    pause rule <id>         enable rule <id>
delete rule <id>
vault status             vault list             forget vault <name>
save to vault work_login = <value>
fill form preview: Email=@vault:email; Note=Following up
fill form: Email=@vault:email; Note=Following up; submit=click:Sign in
```

A created rule only ever **proposes**: when it fires, the work faces the gate exactly like anything else.

Form filling takes **one approval for the whole form** — you confirm filling every field *and* submitting, in a single step, rather than approving each keystroke. What you approve shows the binding, never the secret:

```text
Fill and submit a form in "Sign in - Example - Chrome":
  1. Email  <- saved: email
  2. Note   <- "Following up"
  Then: click "Sign in"
```

A `@vault:name` reference is resolved from the encrypted vault **after** you approve, immediately before the value is typed. The value is never written to the approval record, the ledger, or a trace, and is never placed in the model's context. `vault list` shows names only; there is deliberately no command that prints a stored value.

The *status* commands above return deterministic local text and neither publish nor unlock restricted features. The rule, vault and form-fill entries in this last block are different: they create persistent state or drive real input, and they run under the same gate and flags as everything else (`fill form` additionally needs `EVA_GUI_GROUNDING_ENABLED` and `EVA_ENABLE_REAL_INPUT`).

## Safe Local Demo

Use `eva release smoke test` to show the demo-smoke checklist and `eva release post push sync` to show the post-push sync status. These are report/status/checklist only and add **no new execution path**.

To verify Eva without enabling unsafe features:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_post_push_demo_smoke.py
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --quick --timeout 90
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --full --timeout 90
```

The verifier suite makes no real LLM/API/provider calls and reads no `.env`, `.env.local`, secrets, tokens, cookies, or browser sessions. With no flags set, browser/desktop/MCP execution stays off.

## Phase 33-42 Roadmap Foundations (RC-era numbering)

> **Numbering note.** This section describes the *original* Phase 33–42 roadmap — the release-candidate hardening work. The July 2026 pivot renumbered the program, so the Phase 33–42 listed under "What Has Been Built" is **different, later work**. The two schemes collide by number only.

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

The project was built in numbered phases. **Three numbering schemes exist**, and this document keeps them apart rather than pretending they form one clean sequence:

- **The main build, Phases 1–30** (below) — foundation through release-candidate hardening.
- **The July 2026 pivot, Phases 31 onward** (below) — which restarted the numbering.
- **A `v2 …` sub-numbering** used inside the disabled-by-default v2 runtime work (its own "Phase 1–6": runtime scaffolding, dry-run previews, the safe execution bridge, read-only skill delegation, the pending-action ledger, Safe Code Index v2). These are *not* the main Phases 1–6.

So the RC-era "Phase 33–42 roadmap foundations" (see the section above) is *not* the same work as Phase 33–42 below, and the `v2` Phase 5 ledger is not the main Phase 5 planner.

### Era 1 — Foundation through release candidate (Phases 1–30)

| Phase | Name |
|---|---|
| 1 | Project foundation & architecture |
| 2 | FastAPI backend foundation |
| 3 | API routing & command framework |
| 4 | Capability registry v1 |
| 5 | Planner foundation |
| 6 | Intent detection & natural-language routing |
| 7 | Research memory v1 |
| 8 | FileAgent read-only foundation |
| 9 | Control Center foundation |
| 10 | Agent framework foundation |
| 11 | Verification & safety infrastructure |
| 12A–12L | **The write-boundary series** — the longest and most cautious stretch of the project, taking file writing from "not allowed" to "narrowly allowed". In order: safe file operations, approval workflow, draft preview, write validation, rollback, audit logging, apply pipeline, sandbox apply executor, the approval ledger, execution-safety refinement, final write-boundary preparation, and `12L`'s narrow approved `.md`/`.txt` real-create gate. Twelve phases to earn the right to create one kind of file. |
| 13 | Capability system expansion |
| 14 | Planner v2 & workflow improvements |
| 15 | Team review & quality layer |
| 16 | Verification framework expansion |
| 17 | LLM threat defense & prompt-injection guard |
| 18 | Agent loop v1 |
| 19 | Agentic workflow planner |
| 20 | Controlled execution gates |
| 21 | Memory v3 |
| 22 | Voice assistant foundation |
| 23 | AI OS / Control Center upgrade |
| 24 | Browser read-only intelligence |
| 25 | Real desktop observation mode |
| 26 | Desktop control gate |
| 27 | News / web intelligence dashboard |
| 28 | Coding specialist / CodingAgent foundation |
| 29 | Public demo / release |
| 30 | Release-candidate hardening |

Also from this era, outside the phase numbering: the agentic v2 loop, laptop operator mode, desktop/browser/workspace/code-intelligence cores, Tavily search, one-shot screen vision, SQLite memory, the NVIDIA NIM provider, Ollama fallback, and push-to-talk voice UI with Piper.

Then came a **full security review and hardening pass** (the central `ToolRegistry.run()` gate, the `_safe_path` allowlist, header-guarded local API, and an adversarial pytest suite), a docs-truth pass (`eva capability truth`, generated from code rather than hand-maintained), and the pivot that set the program below.

### Era 2 — The "final boss" program (Phases 31–62)

Delivered in dependency order after the July 2026 pivot. Each shipped with tests, an offline eval, and a dedicated verifier, and was merged only on a green full suite.

| Phase | What it added |
|---|---|
| 31 | De-bloating the report-only packages — deliberately **not** a blocking phase; done opportunistically, because those packages have live importers and are not dead shells. |
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
| 49a | **Speech-to-text** — local faster-whisper/CTranslate2 (no torch). |
| 49b | **Wake word + bounded mic loop** — local openWakeWord ONNX. Nothing is transcribed before the wake word fires. |
| 50 | **Native shell** (tray app + global hotkey) — **deferred, not built.** |
| 51 | **The auto-allow audit** — a missing `action_type` used to silently mean allow-class; it now breaks the build. |
| 52 | **A bigger planner model** — measured, and shipped **no change**: the model was never the bottleneck. |
| 53 | **The background scheduler** — finally *runs* the inert Phases 45/46. Safe because it decides nothing: a queued override-class action parks at the gate. |
| 54 | **Natural-language rule creation** — a typed sentence becomes a persisted proactive rule via a deterministic, LLM-free parser. Console-only, never a planner tool. |
| 55 | **Argument-aware risk escalation** — the gate classifies per *tool* and is blind to *arguments*; this reads the actual arguments and raises friction for sensitive targets. Only ever escalates. |
| 56 | **GUI grounding** — the eyes. A text label becomes a specific on-screen target with coordinates and a confidence; it declines rather than clicking the wrong thing. |
| 57 | **Grounded observation** — `screen.observe` reports the clickable controls, not just the window title, closing the observe→act loop. |
| 58 | **Form filling** — click-to-focus then type, per field. Stops at the first field it cannot find, and never stores the typed values. Its gated path was **dead on arrival** and stayed that way until Phase 62; see below. |
| 59 | **Disambiguation** — two controls matching a label equally well produce a refusal with both candidates, not a coin flip. |
| 60 | **Click accuracy** — two bugs found only by driving a *real* click: a double-centred coordinate that landed half a control away, and missing DPI awareness. |
| 61 | **The voice loop, wired** — `listen_once()` had existed since 49b with nothing calling it. A transcript now routes through the same pipeline as typed text. Also fixed a wake word that could never fire. |
| 62 | **Credential vault + single-approval form submission** — an OS-encrypted store for saved logins and personal fields, and one approval covering a whole form instead of each keystroke. Fixed two defects a fully green suite had missed: form filling could never fill a field, and typed values were persisted to disk in plaintext. |

Phases 56–60 are validated on real hardware, not only in tests. Phase 61's wake and speech-to-text path is validated with synthesized speech driving the real models; firing on a human voice through a physical microphone is not covered. Phase 62's vault encryption and gate behaviour are covered by tests that drive the real permission gate; typing into real browser inputs and DPAPI failing under a genuinely different Windows account are not.

Three times now, a phase has shipped green and been found dead when driven for real: memory that was assembled and discarded before the model saw it, a wake word that could never fire, and form filling that could never type. Each was hidden by a test double more permissive than the real system. The Phase 62 tests deliberately drive the real gate rather than a stand-in, and were checked by breaking the fix to confirm they fail.

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
- **Desktop and screen input (click/type/hotkey) require explicit confirmation** and are not planner-reachable. Clicking by label (GUI grounding) changes how a target is *found*, never who may act: it still passes the confidence floor, the real-input flag, and the gate. When a label matches two controls about equally it **refuses and shows both** rather than guessing, and form filling stops at the first field it cannot resolve instead of typing the remaining values into the wrong places.
- **Saved credentials never enter the model's context.** The vault is not a tool the planner can call, and its existence is not described to the model, so injected content cannot ask for a stored value — it cannot name what it cannot see. Form submission is driven by a reference (`@vault:name`) that is resolved only after your approval, immediately before typing; the value never appears in the approval record, the ledger, a trace, or a prompt. Encryption is Windows DPAPI, tied to your account: the vault file is useless if copied to another machine. It protects the file at rest, **not** against other programs already running as you.
- **A form submission is approved as one action, not as keystrokes.** Approving shows which stored item goes into which field, in which window — the bindings an attacker would have to change — while hiding the values themselves.
- **Sensitive arguments raise friction, they do not lower it.** The gate classifies per *tool*, which leaves it blind to a dangerous *argument*; a separate check reads the actual arguments and escalates for sensitive targets (reading one asks, mutating one requires override). It can only ever escalate — never de-escalate, and never past a hard block.
- **No broad filesystem mutation:** writes/patches/moves/deletes are gated (require override), path-restricted to the project and Documents/Desktop/Downloads, and deny `.env*`, `.git`, `*.sqlite3`, and key files.
- **No secret exfiltration:** the path allowlist blocks reading secret/config/database files by name, and the secrets broker scrubs live secret values out of anything sent to a model or a trace.
- **No unattended privileged action:** proactive rules and durable-queue recovery replay a *request*, never an approval.
- **No self-written code:** learned skills may only compose tools that already exist.
- **Nothing is transcribed before the wake word.** There *is* a wake word (Phase 49b), so this is stated precisely: while waiting, each audio frame is scored by a local ~1MB ONNX model and **discarded**. There is deliberately no buffer of pre-wake audio to hand to anything — not the transcriber, not the disk, not the network. If the wake word never fires, what was said never became data. The microphone is opt-in via `EVA_VOICE_INPUT_ENABLED`, both ends of the loop are bounded (a wake timeout and a hard recording cap), the device is always released, and **no activation profile may enable the microphone** — like real input and the browser, it is opt-in one flag at a time.
- **Voice is fully local, in both directions.** Piper (speech out) and faster-whisper (speech in) both run on-device; no audio and no transcript is ever sent to a speech service. A transcript is treated exactly like typed text: it faces the same planner and the same permission gate, so speaking a command earns no privilege that typing it would not.
- MCP execution is off unless enabled, and then only for servers pinned as trusted, with per-server call budgets.

## Known Limitations

- Voice works in both directions and hands-free (wake word -> speech-to-text -> reply -> speech), all locally. The wake phrase is `hey_jarvis`: openWakeWord ships pretrained models for a handful of phrases and "hey nova" is not one of them, so a custom phrase needs a trained model. Set `EVA_WAKE_WORD` to pick another.
- Speech-to-text accuracy is the weak link in the voice loop: the default `base` model fumbles proper nouns (it hears "NOVA" as "Nola"), so a *spoken* deterministic command may be misheard and fall through to the LLM path instead of matching. Set `EVA_STT_MODEL=small` for better accuracy at ~250MB.
- There is no native shell yet (Phase 50) — it runs as a local web app.
- Provider health varies; run `llm doctor` for live status rather than trusting this list.
- Learned-skill proposals are mined from traces and require your approval.
- The voice loop is validated with synthesized speech driving the real wake and transcription models. Wake-word reliability on a *human* voice through a physical microphone, across accents and room noise, is not characterized.
- GUI grounding reads the Windows accessibility tree, so it is blind to apps that do not expose one (many Electron, canvas, and game UIs). It declines rather than guessing, so those apps degrade to "cannot find that control" instead of misclicking. A vision fallback is not built.
- The vault defends against injected *content* driving it, **not** against a hostile *window*. Grounding matches labels, not origin: if you have a convincing phishing page open and fill it, `@vault:email` goes to the phisher — with your approval, because you did intend to fill that form. The window title is shown in the approval text so you confirm *where*, not just *what*. Binding a saved value to a specific site would need browser-origin plumbing the accessibility layer does not have.
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
