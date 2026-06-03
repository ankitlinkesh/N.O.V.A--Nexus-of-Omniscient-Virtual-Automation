# Eva Current State

Last updated: 2026-06-01

This is a repo-local handoff for future Codex runs. Treat the working tree as active integration work: inspect files and tests before changing behavior, do not rebuild, and do not undo existing systems.

## Implemented Systems

- Agentic v2: `backend/eva/agent/runner.py`, `backend/eva/agent/planner.py`, `backend/eva/agent/policies.py`, `backend/eva/agent/state.py`, `backend/eva/agent/task.py`, verified by `scripts/verify_agentic_v2.py` and `scripts/verify_agent_runner.py`.
- Eva v2 Runtime Skeleton and explicit preview/execution path:
  - Phase 1: optional, disabled-by-default scaffolding in `backend/eva/runtime/`, specialist agents in `backend/eva/agents/`, typed schemas in `backend/eva/schemas/`, guardrail hooks in `backend/eva/guardrails/`, local traces in `backend/eva/observability/`, vector-memory interfaces in `backend/eva/vector_memory/`, optional adapters in `backend/eva/browser_automation/` and `backend/eva/desktop_automation/`, and promptfoo configs in `backend/eva/evals/promptfoo/`.
  - Phase 2: explicit dry-run/plan/route previews through `eva v2 dry run ...`, `eva v2 plan ...`, and `eva v2 route ...`.
  - Phase 2.5: catalog-only resource registry and MCP/open-source policy in `backend/eva/resources/`, documented in `docs/EVA_RESOURCE_REGISTRY.md` and `docs/EVA_MCP_POLICY.md`.
  - Phase 3: safe execution bridge in `backend/eva/runtime/execution_bridge.py` and policy in `backend/eva/runtime/execution_policy.py`.
  - Phase 3.1: resource/MCP wording and WhatsApp/message safety hardening.
  - Phase 4: read-only skill delegation in `backend/eva/runtime/read_only_delegates.py`.
  - Phase 5: pending action ledger and permission-session UX in `backend/eva/permissions/`.
  - Phase 6: Safe Code Index v2 in `backend/eva/code_index/`, with local metadata-only cache under `backend/eva/data/code_index/`.
- Laptop operator mode: deterministic command handling in `backend/eva/core/operator_commands.py` and `backend/eva/core/fast_commands.py`, with tools in `backend/eva/tools/registry.py`.
- Desktop Agent Core: desktop observation/window/action helpers in `backend/eva/desktop/` and desktop tools in `backend/eva/tools/desktop.py`, verified by `scripts/verify_desktop_agent_core.py`.
- Browser Agent Core: safe browser status, URL opening, page summaries, link extraction, and research save flow in `backend/eva/browser/`, verified by `scripts/verify_browser_agent_core.py`.
- Code Intelligence v1: safe code indexing/search/feature explanation in `backend/eva/code/`, verified by `scripts/verify_code_intelligence.py`.
- Safe Code Index v2: metadata-only local code scanner/search/symbol/file-summary package in `backend/eva/code_index/`, verified by `scripts/verify_eva_code_index_v2.py`. It skips secrets/runtime data and does not store full file contents.
- Workspace Skills: safe workspace list/read/search/summary tools in `backend/eva/workspace/`, verified by `scripts/verify_workspace_skills.py`.
- NVIDIA NIM provider: OpenAI-compatible provider in `backend/eva/llm/providers/nvidia_nim.py` with router integration in `backend/eva/llm/router.py`, verified by `scripts/verify_nvidia_nim_provider.py`.
- Research Knowledge SQLite: local research topic/source/note storage in `backend/eva/research/`, defaulting under `backend/eva/data/`, verified by `scripts/verify_research_knowledge.py`.
- Self-diagnostics and provider diagnostics: capability routing in `backend/eva/core/intent_router.py`, diagnostics in `backend/eva/diagnostics/`, and health/provider formatting in `backend/eva/api/routes.py`, verified by `scripts/verify_self_diagnostics.py` and `scripts/verify_capability_routing.py`.
- Tavily web search: search/fallback logic in `backend/eva/tools/tavily_search.py`, verified by `scripts/verify_tavily_search.py`.
- Screen vision: one-shot explicit screenshot analysis in `backend/eva/vision/` and screen tools in `backend/eva/tools/registry.py`, verified by `scripts/verify_screen_vision.py`.
- Memory SQLite: conversation/event/fact storage in `backend/eva/memory/store.py`; runtime database files are ignored.
- Push-to-talk/browser voice UI: frontend voice controls in `frontend/` and Piper status/synthesis in `backend/eva/voice/piper.py`, verified by `scripts/verify_voice_ui.py`.
- Ollama fallback and provider fallback/rate-limit handling: model/provider routers in `backend/eva/models/` and `backend/eva/llm/`, verified by `scripts/verify_llm_router.py` and `scripts/verify_rate_limits.py`.

## Safety Rules

- Do not commit until the user explicitly asks.
- Do not hardcode, print, summarize, or expose API keys or secrets.
- Secrets stay in `.env.local`; do not read or print `.env.local`.
- `.env.local`, `.env`, `*.env`, local SQLite databases, logs, `.venv/`, and `backend/eva/data/` are ignored by `.gitignore`.
- Runtime/generated folders are ignored: `backend/eva/data/`, `backend/data/checkpoints/`, `data/`, `bin/`, `models/`, `frontend/assets/`, logs, screenshots, caches, SQLite DBs, `.venv/`, and `node_modules/`.
- Do not add arbitrary shell execution.
- No camera support.
- No always-on screen watching. Screen capture and vision must stay one-shot and explicit.
- Power actions require explicit confirmation.
- MCP execution remains disabled.
- Playwright execution remains disabled.
- PyAutoGUI execution remains disabled.
- WhatsApp automatic sending remains disabled; message requests create pending confirmation records only.
- File write/edit/delete execution remains disabled in v2; destructive requests create pending override records only.
- Confirmed risky pending actions still do not execute until a future verified executor phase exists.
- Do not route every issue through fast commands. Prefer capability routing, skill routing, planner/tool integration, and grounded system awareness. Use fast commands only for deterministic controls, safety-critical actions, and lightweight local shortcuts.

## How To Run Eva

From the repo root:

```powershell
cd <repo-root>
.\.venv\Scripts\python.exe -m uvicorn backend.eva.main:app --host 0.0.0.0 --port 8765
```

Or run:

```powershell
.\run.ps1
```

Open locally at:

```text
http://127.0.0.1:8765
```

Open from a phone on the same trusted Wi-Fi at:

```text
http://<laptop-ip>:8765
```

Stop the usual server process with:

```powershell
.\stop.ps1
```

## Key Verification Scripts

Use compile checks plus focused verifiers. The most common baseline is:

```powershell
.\.venv\Scripts\python.exe -m compileall backend
```

Important focused scripts:

- `scripts/verify_eva_code_index_v2.py`
- `scripts/verify_eva_permission_ledger.py`
- `scripts/verify_eva_v2_readonly_delegation.py`
- `scripts/verify_eva_v2_safe_execution_bridge.py`
- `scripts/verify_eva_resource_registry.py`
- `scripts/verify_eva_phase_3_1_safety_hotfix.py`
- `scripts/verify_eva_v2_dry_run.py`
- `scripts/verify_llm_router.py`
- `scripts/verify_rate_limits.py`
- `scripts/verify_nvidia_nim_provider.py`
- `scripts/verify_agentic_v2.py`
- `scripts/verify_eva_v2_runtime_skeleton.py`
- `scripts/verify_agent_runner.py`
- `scripts/verify_operator_commands.py`
- `scripts/verify_desktop_agent_core.py`
- `scripts/verify_browser_agent_core.py`
- `scripts/verify_capability_routing.py`
- `scripts/verify_self_diagnostics.py`
- `scripts/verify_research_knowledge.py`
- `scripts/verify_code_intelligence.py`
- `scripts/verify_workspace_skills.py`
- `scripts/verify_screen_vision.py`
- `scripts/verify_voice_ui.py`
- `scripts/verify_tavily_search.py`

## Current Request Flow

`backend/eva/api/routes.py` currently routes chat through these layers:

1. Lightweight deterministic fast commands/responses.
2. Operator commands for safe desktop/browser/system controls.
3. Capability routing through `backend/eva/core/intent_router.py`.
4. Agentic runner for multi-step agentic intents.
5. Planner/tool execution through `ToolCallPlanner`, `ToolExecutor`, and `ToolRegistry`.
6. LLM fallback through cloud/provider router and local Ollama fallback.

Eva v2 runtime is installed around this flow but is not the default path. `EVA_V2_RUNTIME_ENABLED=false` keeps current Eva behavior active; v2 commands are explicit through `backend/eva/core/fast_commands.py`.

## Current v2 Status

Explicit v2 commands work:

- `eva v2 status`
- `eva runtime status`
- `agents status`
- `guardrails status`
- `vector memory status`
- `traces status`
- `automation adapters status`
- `resources status`
- `mcp status`
- `open source tools status`
- `resource detail <id>`
- `eva v2 route <request>`
- `eva v2 plan <request>`
- `eva v2 dry run <request>`
- `eva v2 execute <request>`

Current v2 execution boundary:

- Can execute low-risk status commands.
- Can open public browser apps through existing Chrome Execution Skills where already allowlisted.
- Can delegate read-only code, research, and memory requests through existing safe helpers.
- Can create pending actions for risky requests such as WhatsApp sends, destructive file requests, and visible desktop control.
- Cannot execute confirmed risky pending actions yet.
- Cannot execute MCP, Playwright, PyAutoGUI, arbitrary shell, WhatsApp send, file write/edit/delete, post/submit/purchase, or destructive/system-changing actions.
- Safe Code Index v2 is local and metadata-only; cache files live under `backend/eva/data/code_index/`.
- Runtime caches, traces, pending action ledgers, SQLite stores, and generated data live under ignored runtime folders such as `backend/eva/data/`.

## Next Phases

- Phase 7: Research Memory v2.
- Phase 8: Browser Verification + Link Extraction.
- Phase 9: User Safety Preferences.
- Phase 10: Permission-gated executor phases.
- Future: LangGraph real activation, LLM Guard real scanner integration, optional Langfuse tracing, Chroma/Qdrant vector memory, gated Playwright/PyAutoGUI execution, and gated MCP/connectors integration.
