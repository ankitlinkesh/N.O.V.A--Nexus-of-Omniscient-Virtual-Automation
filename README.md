# Eva Agent

Eva is a local desktop-assistant project with a Python/FastAPI backend, browser UI, bounded agent planning, local memory/research stores, provider diagnostics, and public-safe demo tooling.

Eva uses local data/control where possible, but LLM reasoning may use API-backed providers when configured.

## What Is Eva?

- A modular assistant for local laptop workflows.
- A bounded agent with plan, permission, observe, verify, and stop/repair concepts.
- A local Research Memory system for saved notes, lexical retrieval, tags, exports, quality checks, and demo imports.
- A public/community demo surface that shows capabilities without executing risky actions.

## Public/Community Mode

Public/community mode is meant for source-available demos and review. It exposes status, simulated workflows, safety checks, resource registry views, and setup diagnostics.

Useful commands:

```text
eva release status
eva public checklist
eva public hardening status
eva demo scenarios
eva demo run whatsapp-confirmation
eva safety test read .env.local
eva doctor public
research memory import demo
```

Demo mode does not send messages, delete files, run MCP tools, control the desktop, run Playwright, or read private browser/session data.

## Safety Model

- No arbitrary shell path by default.
- No camera.
- No always-on screen watching.
- Power actions require confirmation.
- Message sending requires confirmation and remains unavailable in public demo mode.
- Destructive file actions require override and remain unavailable in public demo mode.
- MCP, Playwright, and PyAutoGUI execution remain disabled unless a later gated private phase explicitly enables them.
- Private browser, email, chat, cookie, token, localStorage, sessionStorage, and password reads are refused.

## Research Memory

Research Memory stores sanitized local notes in runtime storage. It supports status, recent items, topics, search, retrieval, import/export, tags, duplicate previews, quality warnings, vector-readiness status, and fake public demo notes.

Vector search is prepared but disabled by default. Chroma/Qdrant and cloud embedding/summarization paths are not active in this public phase.

## Run Locally

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.eva.main:app --host 0.0.0.0 --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

Create private settings by copying `.env.example` to `.env.local`, then fill in only the providers you use. Never commit `.env.local`.

## Public Release Readiness

Before publishing:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_public_release_hardening.py
```

Also run:

```powershell
.\.venv\Scripts\python.exe scripts\verify_eva_public_release.py
.\.venv\Scripts\python.exe scripts\verify_eva_stabilization_v1.py
```

## License

Eva is source-available under the PolyForm Noncommercial License 1.0.0.

Non-commercial use is allowed. Commercial use, resale, paid redistribution, hosted commercial services, or selling modified versions requires separate written permission from the author.
