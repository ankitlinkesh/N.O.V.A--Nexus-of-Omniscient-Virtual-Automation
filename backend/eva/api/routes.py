from __future__ import annotations

import json
import os
import re
import time
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from ..agent.executor import ToolExecutor, ToolExecutionResult
from ..agent.action_model import AgentAction
from ..agent.planner import PlannerDecision, PlannerError, ToolCallPlanner
from ..agent.runner import run_agentic_task
from ..agent.policies import is_agentic_intent
from ..browser.skills import ask_chatgpt_in_chrome, verify_browser_target
from ..core.fast_commands import maybe_handle_fast_command
from ..core.fast_responses import maybe_handle_fast_response
from ..core.intent_router import classify_capability_intent
from ..core.operator_commands import handle_operator_command
from ..core.persona import ASSISTANT_NAME, PERSONA_STYLE, STARTUP_GREETING, USER_NAME
from ..core.provenance import remember_answer_provenance
from ..core.web_context import remember_web_results
from ..diagnostics.health import explain_workflows, get_eva_health_summary
from ..diagnostics.providers import format_provider_health
from ..llm.router import complete_with_fallback
from ..models.gemini import GeminiClient
from ..models.ollama import OllamaClient
from ..models.router import ModelRoute
from ..permissions.ledger import create_pending_action
from ..permissions.pending_actions import EvaPendingAction
from ..screen.capture import capture_primary_screen_jpeg
from ..security.action_types import ActionType
from ..security.permission_gate import PermissionContext, evaluate_action
from ..tools.registry import ToolRegistry
from ..vision import vision_status
from ..voice.piper import piper_status, synthesize_piper_wav


router = APIRouter()
tools = ToolRegistry()
executor = ToolExecutor(tools)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    source: str
    requires_confirmation: bool = False
    action: str | None = None


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


def _json_line(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _source(route: ModelRoute) -> str:
    return f"{route.provider}:{route.model} ({route.reason})"


def _decision_payload(decision: PlannerDecision) -> dict:
    return {
        "type": decision.type,
        "reason": decision.reason,
        "tool_calls": [{"tool": call.tool, "args": call.args} for call in decision.tool_calls],
        "final_response": decision.final_response,
        "requires_confirmation": decision.requires_confirmation,
        "action": decision.action,
        "continue_after_tools": decision.continue_after_tools,
    }


def _results_payload(results: list[ToolExecutionResult]) -> list[dict]:
    return [result.as_dict() for result in results]


def _session_context(request: Request, session_id: str) -> dict:
    runtime = getattr(request.app.state, "eva_runtime", None)
    if not isinstance(runtime, dict):
        runtime = {"sessions": {}}
        request.app.state.eva_runtime = runtime
    sessions = runtime.setdefault("sessions", {})
    return sessions.setdefault(session_id, {})


def _operator_context(session_context: dict) -> dict:
    return {"registry": tools, "executor": executor, "session_context": session_context}


def _remember_web_results_from_tools(session_context: dict, results: list[ToolExecutionResult]) -> None:
    for result in results:
        if result.tool in {"web_search", "browser_search"} and result.ok:
            remember_web_results(session_context, result.result)


def _remember_final_source(session_context: dict | None, source: str, results: list[ToolExecutionResult] | None = None) -> None:
    tools_used = [result.tool for result in results or []]
    remember_answer_provenance(session_context, source=source, tools=tools_used)


def _persist_and_log(
    memory,
    session_id: str,
    session_context: dict,
    started_at: float,
    message: str,
    reply: str,
    source: str,
    *,
    log_kind: str,
    log_payload: dict,
    matched_event: str,
    matched_fields: dict | None = None,
    provenance: str = "final",
    provenance_tools: list[str] | None = None,
) -> None:
    """Shared finalization for the deterministic pre-LLM stages (fast command,
    casual response, capability route). Both /chat and /chat/stream use this so
    memory writes, logging, and timing stay identical across the two endpoints."""
    memory.add_message(session_id, "user", message)
    memory.add_message(session_id, "assistant", reply)
    _safe_log(memory, session_id, log_kind, log_payload)
    _timing_log(session_id, matched_event, started_at, **(matched_fields or {}))
    _timing_log(session_id, "response_ready", started_at, source=source, total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
    if provenance == "answer":
        remember_answer_provenance(session_context, source=source, tools=provenance_tools or [])
    else:
        _remember_final_source(session_context, source)


def _simple_stream_events(session_id: str, source: str, reply: str, route: str | None = None) -> list[str]:
    """The meta/token/done triple a deterministic stage emits when streaming."""
    meta = {"type": "meta", "session_id": session_id, "source": source}
    if route is not None:
        meta["route"] = route
    return [
        _json_line(meta),
        _json_line({"type": "token", "text": reply}),
        _json_line({"type": "done", "reply": reply}),
    ]


def _safe_log(memory, session_id: str, kind: str, payload: dict) -> None:
    try:
        memory.log_event(session_id, kind, payload)
    except Exception:
        # Logging should never break command execution.
        return


def _timing_log(session_id: str, event: str, started_at: float, **payload: object) -> None:
    fields = " ".join(f"{key}={value}" for key, value in payload.items() if value is not None)
    elapsed = (time.perf_counter() - started_at) * 1000
    suffix = f" {fields}" if fields else ""
    try:
        print(f"[EvaTiming] session={session_id} event={event} elapsed_ms={elapsed:.1f}{suffix}", flush=True)
    except Exception:
        # Timing logs are useful, but they should never break chat when stdout is unavailable.
        return


async def _chat_with_route(message: str, history: list[dict[str, str]], route: ModelRoute, settings) -> str:
    if route.provider == "gemini":
        return await GeminiClient(settings.models).chat(message, history=history, model=route.model)
    return await OllamaClient(settings.models).chat(message, history=history, model=route.model)


async def _stream_with_route(message: str, history: list[dict[str, str]], route: ModelRoute, settings) -> AsyncIterator[str]:
    if route.provider == "gemini":
        # Use the reliable non-SSE Gemini endpoint first; local Ollama still streams token-by-token.
        yield await GeminiClient(settings.models).chat(message, history=history, model=route.model)
        return
    async for token in OllamaClient(settings.models).stream_chat(message, history=history, model=route.model):
        yield token


def _local_fallback_route(settings) -> ModelRoute:
    return ModelRoute("ollama", settings.models.fast_model or settings.models.ollama_model, "fallback-local-ollama")


async def _fallback_answer(message: str, history: list[dict[str, str]], settings) -> tuple[str, str]:
    route = _local_fallback_route(settings)
    try:
        return await _chat_with_route(message, history, route, settings), _source(route)
    except RuntimeError as exc:
        fallback = ModelRoute("ollama", settings.models.fast_model, "fallback-local")
        try:
            return await _chat_with_route(message, history, fallback, settings), f"{_source(fallback)} after {_source(route)} failed"
        except RuntimeError:
            return f"I tried the smart brain and local fallback, but both failed. First error: {exc}", "model-error"


async def _synthesize_tool_response(message: str, results: list[ToolExecutionResult], history: list[dict[str, str]], settings) -> tuple[str, str]:
    if any(result.tool == "analyze_screen" for result in results):
        return _local_tool_summary(results), "tool-summary"

    payload = _results_payload(results)
    prompt = (
        "You are Eva. Summarize these tool execution results naturally and briefly. "
        "Be honest about failures and do not claim unavailable capabilities. "
        "If web_search or browser_search returned Tavily/browser results, summarize only the provided answer/results, list the top 3 to 5 titles with URLs. If browser tools returned page/title/link/summary data, report only that safe observed browser context and mention when page reading was blocked. If analyze_screen returned vision results, explain what is visible, any likely issue, and suggested next steps, "
        "If workspace tools returned results, include what was inspected, the relevant safe file paths, what was found, and a practical next step. "
        "If research tools returned results, distinguish saved local knowledge from fresh web results, include source URLs, and offer a useful next action. "
        "If desktop/window tools returned results, state the active window/open windows/action verification plainly and briefly. "
        "and mention browser fallback only when the result says fallback=browser. Do not invent facts not present in the tool JSON or screenshot analysis.\n\n"
        f"User request: {message}\n"
        f"Tool results JSON: {json.dumps(payload, ensure_ascii=False)}"
    )
    routed = await complete_with_fallback(
        [
            {"role": "system", "content": "You are Eva. Write concise final user-facing responses from safe local tool results."},
            {"role": "user", "content": prompt},
        ],
        settings.models,
        purpose="final_response",
        temperature=0.2,
        max_tokens=700,
    )
    if routed.response.ok and routed.response.text.strip():
        return routed.response.text.strip(), f"{routed.response.provider}:{routed.response.model} (tool-synthesis)"
    return _local_tool_summary(results), "tool-summary"


def _format_tavily_summary(result: dict) -> str:
    query = result.get("query") or "your search"
    if result.get("ok") and result.get("provider") == "tavily":
        lines = [f"I searched Tavily for: {query}."]
        answer = str(result.get("answer") or "").strip()
        if answer:
            lines.append(answer)
        items = result.get("results") or []
        if isinstance(items, list) and items:
            lines.append("Top results:")
            for item in items[:5]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "Untitled")
                url = str(item.get("url") or "")
                lines.append(f"- {title}: {url}" if url else f"- {title}")
        return "\n".join(lines)
    if result.get("fallback") == "browser":
        reason = result.get("error") or "unavailable"
        return f"Tavily search was {reason}, so I opened a browser search for: {query}."
    return str(result)



def _format_vision_summary(result: dict) -> str:
    if not result.get("ok"):
        summary = str(result.get("summary") or "").strip()
        if result.get("rate_limited") and summary:
            return summary
        return f"Screen analysis failed: {result.get('error') or 'unknown error'}."
    lines = []
    summary = str(result.get("summary") or "").strip()
    if summary:
        lines.append(summary)
    detected_text = str(result.get("detected_text") or "").strip()
    if detected_text:
        lines.append(f"Visible text: {detected_text}")
    possible_issue = str(result.get("possible_issue") or "").strip()
    if possible_issue:
        lines.append(f"Possible issue: {possible_issue}")
    actions = result.get("suggested_actions") or []
    if isinstance(actions, list) and actions:
        lines.append("Suggested next steps: " + "; ".join(str(item) for item in actions[:4] if str(item).strip()))
    return " ".join(lines) or "I analyzed the screen, but the image was unclear."


def _format_workspace_summary(tool: str, result: dict) -> str:
    if not result.get("ok"):
        return f"{tool} refused safely: {result.get('error') or 'unknown error'}."
    if tool == "workspace_search":
        matches = result.get("matches") or []
        if not matches:
            return f"I searched the workspace for {result.get('query')}, but did not find a safe match."
        lines = [f"I searched the workspace for {result.get('query')}. Relevant files:"]
        for item in matches[:8]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('path')}:{item.get('line')} - {item.get('snippet')}")
        return "\n".join(lines)
    if tool == "workspace_read_file":
        content = str(result.get("content") or "")[:3000]
        return f"I read {result.get('path')} safely. Key snippet:\n```text\n{content}\n```"
    if tool == "workspace_project_summary":
        lines = ["I inspected Eva's project layout:"]
        for section in result.get("sections") or []:
            if isinstance(section, dict):
                lines.append(f"- {section.get('folder')}: {section.get('description')}")
        return "\n".join(lines)
    if tool == "workspace_list_files":
        files = result.get("files") or []
        lines = [f"I listed {len(files)} safe workspace files:"]
        for item in files[:25]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('path')}")
        return "\n".join(lines)
    if tool == "workspace_summarize_file":
        return str(result.get("summary") or result)
    return json.dumps(result, indent=2)


def _format_research_summary(tool: str, result: dict) -> str:
    if not result.get("ok"):
        return f"{tool} failed safely: {result.get('error') or 'unknown error'}."
    if tool == "research_status":
        return (
            "Research status: local SQLite research knowledge is available. "
            f"Topics: {result.get('topic_count', 0)}. Sources: {result.get('item_count', 0)}. "
            f"Notes: {result.get('note_count', 0)}. Sessions: {result.get('session_count', 0)}. "
            "Say `research status raw` if you want debug JSON."
        )
    if tool == "research_web":
        lines = [f"Saved fresh research for {result.get('topic')}: {result.get('query')}"]
        answer = str(result.get("answer") or "").strip()
        if answer:
            lines.append(answer)
        saved = result.get("saved_results") or []
        if isinstance(saved, list) and saved:
            lines.append("Sources saved:")
            for item in saved[:5]:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('title')}: {item.get('url')}")
        return "\n".join(lines)
    if tool == "research_recall":
        matches = result.get("matches") or []
        if not matches:
            return f"I do not have saved research for {result.get('topic')} yet."
        lines = [f"Saved local research for {result.get('topic')}:"]
        for item in matches[:5]:
            if isinstance(item, dict):
                if item.get("type") == "source":
                    lines.append(f"- {item.get('title')}: {item.get('url')} - {item.get('text')}")
                else:
                    lines.append(f"- {item.get('text')}")
        return "\n".join(lines)
    if tool == "research_summary":
        return str(result.get("summary") or result)
    if tool in {"research_start_topic", "research_save_note"}:
        return str(result.get("message") or result)
    return json.dumps(result, indent=2)


def _format_desktop_summary(tool: str, result: dict) -> str:
    if not result.get("ok"):
        return f"{tool} failed safely: {result.get('error') or 'unknown error'}."
    if tool == "window_active":
        window = result.get("window") or {}
        if isinstance(window, dict):
            title = window.get("title") or "Unknown window"
            process = window.get("process_name") or "unknown process"
            return f"You are currently on {title} ({process})."
    if tool == "window_list":
        windows = result.get("windows") or []
        if not windows:
            return "I did not find any visible app windows."
        lines = [f"I found {len(windows)} visible window{'' if len(windows) == 1 else 's'}:"]
        for item in windows[:8]:
            if isinstance(item, dict):
                title = item.get("title") or "Untitled"
                process = item.get("process_name") or "unknown"
                lines.append(f"- {title} ({process})")
        return "\n".join(lines)
    if tool == "desktop_observe":
        active = result.get("active_window_title") or "unknown"
        process = result.get("active_process") or "unknown"
        count = len(result.get("open_windows") or [])
        notes = result.get("notes") or []
        suffix = " ".join(str(note) for note in notes[:2]) if isinstance(notes, list) else ""
        return f"Desktop observed. Active window: {active} ({process}). Open windows seen: {count}. {suffix}".strip()
    if tool == "verify_last_action":
        message = str(result.get("message") or "").strip()
        verified = bool(result.get("verified"))
        return message or ("Verified the action." if verified else "I tried to verify the action, but it was inconclusive.")
    if tool in {"window_focus", "window_minimize", "window_maximize", "window_close_safe"}:
        window = result.get("window") or {}
        title = window.get("title") if isinstance(window, dict) else None
        action = {
            "window_focus": "focused",
            "window_minimize": "minimized",
            "window_maximize": "maximized",
            "window_close_safe": "closed",
        }.get(tool, "updated")
        return f"Done, {action} {title or 'the matching window'}."
    return json.dumps(result, indent=2)


def _format_browser_summary(tool: str, result: dict) -> str:
    if not result.get("ok"):
        summary = str(result.get("summary") or "").strip()
        error = str(result.get("error") or "unknown error")
        return summary or f"{tool} failed safely: {error}."
    if tool == "browser_status":
        title = result.get("active_window_title") or "no active browser window"
        detected = "detected" if result.get("browser_detected") else "not detected"
        if result.get("verified") and result.get("url"):
            return f"Browser {detected}. Active browser window: {title}. Current verified URL: {result.get('url')}."
        known = result.get("known_current_url")
        suffix = f" Last known page was {known}." if known else ""
        return f"Browser {detected}. Active browser window: {title}. I can't verify the current Chrome page right now.{suffix}"
    if tool == "browser_search":
        lines = [f"I searched the browser for: {result.get('query')}."]
        answer = str(result.get("answer") or "").strip()
        if answer:
            lines.append(answer)
        items = result.get("results") or []
        if isinstance(items, list) and items:
            lines.append("Top results:")
            for item in items[:5]:
                if isinstance(item, dict):
                    title = str(item.get("title") or "Untitled")
                    url = str(item.get("url") or "")
                    lines.append(f"- {title}: {url}" if url else f"- {title}")
        elif result.get("fallback") == "browser":
            lines.append("I opened a browser search fallback.")
        return "\n".join(lines)
    if tool == "browser_open_url":
        url = result.get("url") or "the URL"
        verified = " and verified it" if result.get("verified") else ""
        return f"Done, opened {url}{verified}."
    if tool == "browser_current_page":
        title = result.get("current_title") or result.get("active_window_title") or "unknown page"
        url = result.get("current_url")
        if result.get("verified") is False or result.get("stale"):
            message = str(result.get("message") or "").strip()
            if message:
                return message
            return "I can't verify the current Chrome page right now."
        return f"Current browser page: {title}" + (f" ({url})." if url else ".")
    if tool == "browser_summarize_page":
        title = result.get("current_title") or "current page"
        summary = str(result.get("page_summary") or result.get("summary") or "").strip()
        return f"{title}: {summary}" if summary else f"I could not extract a useful summary for {title}."
    if tool == "browser_extract_links":
        links = result.get("extracted_links") or []
        if not links:
            return "I did not find safe public links on that page."
        lines = [f"I found {len(links)} link{'' if len(links) == 1 else 's'}:"]
        for item in links[:8]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('text') or 'Link'}: {item.get('url')}")
        return "\n".join(lines)
    if tool == "browser_save_page_to_research":
        topic = result.get("topic") or "that topic"
        count = result.get("saved_count") or 0
        return f"Saved {count} current-page source{'' if count == 1 else 's'} to research topic {topic}."
    if tool == "browser_observe":
        title = result.get("current_title") or result.get("active_window_title") or "unknown"
        url = result.get("current_url")
        notes = result.get("notes") or []
        suffix = " ".join(str(note) for note in notes[:2]) if isinstance(notes, list) else ""
        return f"Browser observed. Current page: {title}" + (f" ({url}). " if url else ". ") + suffix
    if tool == "chrome_open_web_app":
        message = str(result.get("message") or "").strip()
        if message:
            return message
        app_name = str(result.get("app_name") or "that web app").strip()
        base = f"Done, {app_name} is open in Chrome."
        if result.get("verified") is False:
            return base + " I couldn't verify the exact browser URL from Windows, but the open action completed."
        return base
    if tool == "chrome_search_site":
        message = str(result.get("message") or "").strip()
        if message:
            return message
        site = str(result.get("site") or "that site").strip()
        query = str(result.get("query") or "your query").strip()
        return f"Done, searched {site} for {query} in Chrome."
    if tool in {"browser_verify_target", "verify_browser_target", "chrome_activate_top_youtube_result"}:
        message = str(result.get("message") or "").strip()
        if message:
            return message
        return "Target verification complete." if result.get("verified") else "I could not verify the intended target."
    if tool == "chrome_copy_current_url":
        return str(result.get("message") or f"Copied {result.get('url') or 'the current URL'}.")
    if tool in {"chrome_new_tab", "chrome_close_tab", "chrome_reload", "chrome_back", "chrome_forward", "chrome_focus_address_bar"}:
        return str(result.get("message") or "Browser action complete.")
    return json.dumps(result, indent=2)


def _local_tool_summary(results: list[ToolExecutionResult]) -> str:
    if not results:
        return "I did not run any tools."
    chunks = []
    for result in results:
        if result.requires_confirmation:
            chunks.append(f"{result.tool} needs confirmation before {result.action}.")
        elif result.ok:
            if result.tool == "web_search" and isinstance(result.result, dict):
                chunks.append(_format_tavily_summary(result.result))
            elif result.tool == "analyze_screen" and isinstance(result.result, dict):
                chunks.append(_format_vision_summary(result.result))
            elif result.tool.startswith("workspace_") and isinstance(result.result, dict):
                chunks.append(_format_workspace_summary(result.tool, result.result))
            elif result.tool.startswith("research_") and isinstance(result.result, dict):
                chunks.append(_format_research_summary(result.tool, result.result))
            elif result.tool.startswith("window_") and isinstance(result.result, dict):
                chunks.append(_format_desktop_summary(result.tool, result.result))
            elif result.tool in {"desktop_observe", "verify_last_action"} and isinstance(result.result, dict):
                chunks.append(_format_desktop_summary(result.tool, result.result))
            elif (result.tool.startswith("browser_") or result.tool.startswith("chrome_")) and isinstance(result.result, dict):
                chunks.append(_format_browser_summary(result.tool, result.result))
            else:
                if isinstance(result.result, dict):
                    chunks.append(str(result.result.get("message") or result.result.get("summary") or f"{result.tool} completed."))
                else:
                    chunks.append(str(result.result))
        else:
            if isinstance(result.result, dict):
                message = str(
                    result.result.get("user_message")
                    or result.result.get("message")
                    or result.result.get("summary")
                    or ""
                ).strip()
                if message:
                    chunks.append(message)
                    continue
            chunks.append(f"{result.tool} failed." if not result.error else f"{result.tool} failed: {result.error}")
    if len(chunks) == 1 and chunks[0].startswith(("Done,", "Copied ")):
        return chunks[0]
    if chunks and chunks[0].startswith(("Verified.", "I can't", "I could not", "I couldn't")):
        return " ".join(chunks)
    return "Done. " + " ".join(chunks)


def _run_capability_tool(tool_name: str, **kwargs: object) -> dict:
    try:
        result = tools.run(tool_name, **kwargs)
        return result if isinstance(result, dict) else {"ok": True, "value": result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _format_self_architecture(code_map: dict, workspace_summary: dict) -> str:
    code_ok = bool(code_map.get("ok"))
    workspace_ok = bool(workspace_summary.get("ok"))
    indexed_files = code_map.get("indexed_files") if code_ok else "unknown"
    lines = [
        "Eva system map, grounded in the project files:",
        "",
        "- Frontend/UI: `frontend/index.html`, `frontend/styles.css`, and `frontend/app.js` render the EVA command deck, AI-core UI, brain dropdown, push-to-talk, browser TTS/Piper controls, activity pills, and chat stream handling.",
        "- API/routing layer: `backend/eva/main.py` mounts the FastAPI app, while `backend/eva/api/routes.py` owns health, chat, streaming chat, TTS, tools, and screen snapshot routes.",
        "- Capability router: `backend/eva/core/capabilities.py` defines broad Eva capabilities, and `backend/eva/core/intent_router.py` classifies architecture/provider/code/browser/desktop/system-health intents before generic LLM chat.",
        "- Fast commands/operator layer: `backend/eva/core/fast_commands.py`, `backend/eva/core/operator_commands.py`, and `backend/eva/tools/registry.py` handle deterministic controls before any LLM gets involved.",
        "- Agentic v2 loop: `backend/eva/agent/planner.py`, `backend/eva/agent/executor.py`, `backend/eva/agent/runner.py`, `backend/eva/agent/cognition.py`, `backend/eva/agent/policies.py`, and `backend/eva/agent/state.py` run bounded plan -> act -> observe -> reflect workflows.",
        "- Tool registry/executor: `backend/eva/tools/registry.py` is the whitelist, and `backend/eva/agent/executor.py` validates/executes tool calls. Eva does not get arbitrary shell access.",
        "- Desktop Agent Core: `backend/eva/desktop/windows.py`, `backend/eva/desktop/observer.py`, `backend/eva/desktop/verifier.py`, and `backend/eva/desktop/skills.py` observe windows and verify safe desktop actions.",
        "- Browser Agent Core: `backend/eva/browser/state.py`, `backend/eva/browser/controller.py`, `backend/eva/browser/reader.py`, and `backend/eva/browser/skills.py` track browser state, open/search URLs, summarize safe pages, and save browser context to research.",
        "- Code Intelligence: `backend/eva/code/` builds a safe code index for symbols, feature maps, traceback debugging, and patch planning.",
        "- Workspace Skills: `backend/eva/workspace/` safely lists/searches/reads project files while excluding secrets, runtime data, `.git`, and virtualenvs.",
        "- LLM router/providers: `backend/eva/llm/router.py` routes through NVIDIA NIM, Gemini, OpenRouter, Groq, CLoD, Ollama, and local fallback with provider/model-scoped rate-limit state. The NIM implementation lives in `backend/eva/llm/providers/nvidia_nim.py`.",
        "- Provider order: NVIDIA NIM -> Gemini -> OpenRouter -> Groq -> CLoD -> Ollama. Generic chat is used only after deterministic, operator, capability, agentic, and planner/tool routes do not handle the request.",
        "- Tavily search: `backend/eva/tools/tavily_search.py` gives real web results, with browser fallback when Tavily is unavailable.",
        "- Screen vision: `backend/eva/vision/screen_vision.py` does explicit one-shot Gemini Vision screen analysis with local vision quota protection.",
        "- Research SQLite: `backend/eva/research/store.py` and related research modules store topics, sources, notes, sessions, and keyword fallback retrieval under `backend/eva/data/research_knowledge.sqlite3`.",
        "- Data stores: `backend/eva/data/research_knowledge.sqlite3` holds research knowledge, memory SQLite is managed through `backend/eva/memory/`, and `backend/eva/data/code_index.json` holds the safe code index.",
        "- Memory SQLite: `backend/eva/memory/` or the backend memory layer stores chat/events/facts locally so Eva can remember useful user/project context without exposing secrets.",
        "- Voice system: `frontend/app.js` controls push-to-talk, stable selected voices, final-only speech, and speech cleanup so raw tool/status dumps are not spoken.",
        "- Safety gates: no arbitrary shell, no camera, screen only on request, no always-on screen watching, `.env.local` stays secret/ignored and must not be printed, and power actions require confirmation.",
        "",
        f"Code index status: {indexed_files} safe files indexed." if code_ok else "Code index was unavailable, so I used the built-in architecture map.",
    ]
    if workspace_ok:
        sections = workspace_summary.get("sections") or []
        names = [str(section.get("folder")) for section in sections[:10] if isinstance(section, dict) and section.get("folder")]
        if names:
            lines.append("Workspace summary saw: " + ", ".join(names) + ".")
    return "\n".join(lines)


def _provider_key(provider: str) -> str:
    return "nvidia_nim" if provider in {"nim", "nvidia"} else provider


def _format_provider_diagnostics(provider: str, settings) -> str:
    provider = _provider_key(provider or "")
    return format_provider_health(provider, settings.models)


def _extract_feature_query(message: str) -> str:
    cleaned = re.sub(r"^\s*(where\s+(is|are)|explain\s+feature)\s+", "", message, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+implemented\??$", "", cleaned, flags=re.IGNORECASE).strip(" ?")
    return cleaned or message.strip()


def _format_code_capability(message: str, route: str | None) -> str:
    if route == "code_project_map":
        return _format_code_result("code_project_map", _run_capability_tool("code_project_map"))
    if route == "code_find_symbol":
        symbol = re.sub(r"^\s*(find symbol|where is symbol|search symbol)\s+", "", message, flags=re.IGNORECASE).strip()
        return _format_code_result("code_find_symbol", _run_capability_tool("code_find_symbol", symbol=symbol))
    if route == "code_plan_change":
        goal = re.sub(r"^\s*plan change\s+", "", message, flags=re.IGNORECASE).strip()
        return _format_code_result("code_plan_change", _run_capability_tool("code_plan_change", goal=goal or message))
    feature = _extract_feature_query(message)
    return _format_code_result("code_explain_feature", _run_capability_tool("code_explain_feature", feature=feature))


def _format_code_result(tool_name: str, result: dict) -> str:
    if not result.get("ok"):
        return f"{tool_name} failed safely: {result.get('error') or 'unknown error'}."
    if tool_name == "code_status":
        indexed = "ready" if result.get("indexed") else "not built yet"
        return (
            f"Code status: safe code index is {indexed}. "
            f"Indexed files: {result.get('indexed_files', 0)}. "
            f"Secrets indexed: {'yes' if result.get('secrets_indexed') else 'no'}. "
            "Say `code status raw` if you want debug JSON."
        )
    if tool_name == "code_project_map":
        lines = [f"Project map: {result.get('indexed_files', 0)} indexed files."]
        for module in result.get("modules") or []:
            if isinstance(module, dict):
                lines.append(f"- {module.get('folder')}: {module.get('description')}")
        return "\n".join(lines)
    if tool_name == "code_find_symbol":
        matches = result.get("matches") or []
        if not matches:
            return "I searched the code index but did not find that symbol."
        lines = ["Symbol matches:"]
        for item in matches[:8]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('path')}:{item.get('line')} `{item.get('name')}` ({item.get('kind')})")
        return "\n".join(lines)
    if tool_name == "code_plan_change":
        return str(result.get("plan") or result.get("summary") or json.dumps(result, indent=2))
    if tool_name == "code_explain_feature":
        summary = str(result.get("summary") or "").strip()
        files = result.get("files") or result.get("matches") or []
        lines = [summary or "Here is where that feature appears to be implemented:"]
        for item in (files[:8] if isinstance(files, list) else []):
            if isinstance(item, dict):
                lines.append(f"- {item.get('path')}: {item.get('reason') or item.get('snippet') or item.get('summary') or ''}".rstrip())
        return "\n".join(lines)
    return json.dumps(result, indent=2)


def _format_spotify_result(tool_name: str, result: dict) -> str:
    message = str(result.get("message") or "").strip()
    if not result.get("ok"):
        return message or f"{tool_name} failed safely: {result.get('error') or 'unknown error'}."
    if message:
        return message
    if tool_name == "spotify_status":
        return "Spotify is open." if result.get("open") else "I do not see Spotify open right now."
    return "Spotify command sent, but exact playback cannot be verified in v1."


def _handle_capability_route(
    message: str,
    classification: dict,
    session_context: dict | None,
    memory,
    session_id: str,
    settings=None,
) -> tuple[str, str] | None:
    if not classification.get("matched"):
        return None
    capability = classification.get("capability")
    route = classification.get("suggested_route")

    if capability == "self_architecture":
        if route == "workflow_explanation":
            return explain_workflows(), "capability:workflow_explanation"
        code_map = _run_capability_tool("code_project_map")
        workspace = _run_capability_tool("workspace_project_summary")
        reply = _format_self_architecture(code_map, workspace)
        return reply, "capability:self_architecture"

    if capability == "self_diagnostics":
        reply = get_eva_health_summary(settings.models if settings is not None else None)["text"]
        return reply, "capability:self_diagnostics"

    if capability == "eva_v2_runtime":
        from ..core.fast_commands import maybe_handle_fast_command

        handled = maybe_handle_fast_command(message, ToolRegistry(), session_context)
        if handled is not None:
            return handled
        return "Eva v2 runtime skeleton is installed but disabled by default.", "capability:eva_v2_runtime"

    if capability == "provider_diagnostics" and settings is not None:
        provider = str(classification.get("provider") or "")
        reply = _format_provider_diagnostics(provider, settings)
        return reply, "capability:provider_diagnostics"

    if capability == "code_intelligence":
        return _format_code_capability(message, str(route or "")), "capability:code_intelligence"

    if capability == "browser_agent":
        tool = str(route or "browser_current_page")
        if tool == "chatgpt_in_chrome":
            result = ask_chatgpt_in_chrome(str(classification.get("prompt") or ""))
            reply = str(
                result.get("message")
                or "I can open ChatGPT in Chrome, but I don't yet have a verified workflow to type, submit, and read ChatGPT responses inside Chrome safely."
            )
            if "don't yet have a verified workflow" not in reply and "can't yet reliably" in reply:
                reply = (
                    reply
                    + " I don't yet have a verified workflow to type, submit, and read ChatGPT responses inside Chrome safely."
                )
            reply += " I won't answer directly and pretend it came from ChatGPT."
            return reply, "capability:chatgpt_in_chrome_unavailable"
        if tool == "chrome_open_web_app":
            result = _run_capability_tool(tool, app=str(classification.get("app") or ""))
        elif tool == "chrome_search_site":
            result = _run_capability_tool(
                tool,
                site=str(classification.get("site") or ""),
                query=str(classification.get("query") or ""),
                play=bool(classification.get("play")),
            )
        elif tool == "browser_save_page_to_research":
            result = _run_capability_tool(tool, topic=str(classification.get("topic") or ""))
        elif tool == "browser_open_result_and_verify":
            result = _run_capability_tool(tool, url=str(classification.get("url") or ""), result_index=int(classification.get("result_index") or 0))
        elif tool == "verify_browser_target":
            result = verify_browser_target(session_context)
        else:
            result = _run_capability_tool(tool)
        return _local_tool_summary([ToolExecutionResult(tool=tool, ok=bool(result.get("ok")) if isinstance(result, dict) else True, result=result, error=result.get("error") if isinstance(result, dict) else None)]), f"capability:{capability}"

    if capability == "desktop_agent":
        tool = str(route or "window_active")
        return _local_tool_summary([ToolExecutionResult(tool=tool, ok=True, result=_run_capability_tool(tool))]), f"capability:{capability}"

    if capability == "screen_vision":
        tool = str(route or "analyze_screen")
        result = _run_capability_tool(tool, question=message) if tool == "analyze_screen" else _run_capability_tool(tool)
        return _local_tool_summary([ToolExecutionResult(tool=tool, ok=bool(result.get("ok")), result=result, error=result.get("error"))]), f"capability:{capability}"

    if capability == "media_music_control":
        tool = str(route or "spotify_status")
        query = str(classification.get("query") or "").strip()
        if tool in {"spotify_search", "spotify_play_query", "spotify_search_desktop", "spotify_play_desktop"}:
            result = _run_capability_tool(tool, query=query)
        else:
            result = _run_capability_tool(tool)
        return _format_spotify_result(tool, result), f"capability:{capability}"

    if capability == "permission_gate":
        action = AgentAction(
            tool_name="file.delete",
            action_type=ActionType.DESTRUCTIVE_FILE_ACTION.value,
            description="Delete local Downloads folder",
            params={"target": classification.get("target") or "Downloads"},
            risk_categories=[ActionType.DESTRUCTIVE_FILE_ACTION.value],
            destructive=True,
            rollback={"checkpoint_type": "metadata_only", "target": classification.get("target") or "Downloads"},
            verification={"method": "file_exists"},
        )
        decision = evaluate_action(action, PermissionContext())
        if decision.decision == "ask_override":
            pending = EvaPendingAction.new(
                action_type="file.delete",
                risk_level="high",
                risk_category="destructive_file_action",
                summary=f"Delete {classification.get('target') or 'Downloads'}",
                target=str(classification.get("target") or "Downloads"),
                payload_summary="Destructive file action summary only",
                requires_override=True,
                source="normal_chat",
                safety_reason=decision.reason,
                executor_available=False,
            )
            create_pending_action(pending)
            return (
                "That is a destructive file action, so I did not delete anything. "
                "Eva would need a rollback/checkpoint plan first, then you would have to approve the exact pending action before any delete could run.\n\n"
                "Pending action:\n"
                f"ID: {pending.id}\n"
                f"Status: {pending.status}\n"
                f"Risk: {pending.risk_category}\n"
                f"Summary: {pending.summary}\n\n"
                f"Say `confirm override {pending.id}` only if you understand this is destructive. "
                "This build still cannot delete files through the verified executor phase, so confirmation will not delete anything yet.",
                "capability:permission_gate",
            )
        return decision.reason, "capability:permission_gate"

    if capability == "message_workflow":
        recipient = str(classification.get("recipient") or "").strip()
        body = str(classification.get("message") or "").strip()
        if route == "message_send_followup":
            return (
                "I need a specific pending action ID. Use `pending actions` to see active actions, then say `confirm <id>`. "
                "I did not send anything.",
                "capability:message_workflow",
            )
        result = _run_capability_tool("message.prepare", recipient=recipient, message=body)
        if isinstance(result, dict) and result.get("ok"):
            pending = EvaPendingAction.new(
                action_type="message.send.whatsapp",
                risk_level="medium",
                risk_category="external_message",
                summary=f"Send WhatsApp message to {recipient}: \"{body}\"",
                target=recipient,
                payload_summary=f"Message: {body}",
                requires_confirmation=True,
                source="normal_chat",
                safety_reason="External messages require explicit confirmation.",
                redacted_payload={"recipient": recipient, "message": body},
                executor_available=False,
            )
            create_pending_action(pending)
            if classification.get("requested_web"):
                return (
                    f"I prepared a WhatsApp Web draft request for {recipient}: \"{body}\". I did not send anything.\n\n"
                    "Pending action:\n"
                    f"ID: {pending.id}\n"
                    f"Status: {pending.status}\n"
                    f"Risk: {pending.risk_category}\n"
                    f"Summary: {pending.summary}\n\n"
                    "Sending requires confirmation. "
                    f"Say `confirm {pending.id}` to approve this exact action. "
                    "This build still cannot automatically send WhatsApp until a later verified executor phase.",
                    "capability:message_workflow",
                )
            return (
                f"I prepared a WhatsApp draft for {recipient}: \"{body}\". I did not send anything. "
                "WhatsApp Desktop is the first target, and Eva will not send it silently.\n\n"
                "Pending action:\n"
                f"ID: {pending.id}\n"
                f"Status: {pending.status}\n"
                f"Risk: {pending.risk_category}\n"
                f"Summary: {pending.summary}\n\n"
                "Sending requires confirmation. "
                f"Say `confirm {pending.id}` to approve this exact action. "
                "This build still cannot automatically send WhatsApp until a later verified executor phase.",
                "capability:message_workflow",
            )
        return "I recognized the WhatsApp workflow, but draft preparation is unavailable right now. I did not send anything.", "capability:message_workflow"

    return None


@router.get("/health")
async def health(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "ok": True,
        "name": "Eva",
        "model": settings.models.ollama_model,
        "fast_model": settings.models.fast_model,
        "deep_model": settings.models.deep_model,
        "smart_enabled": settings.models.smart_enabled,
        "smart_provider": settings.models.smart_provider,
        "smart_model": settings.models.smart_model,
        "screen_capture": settings.features.screen_capture,
        "voice_enabled": settings.features.voice_enabled,
        "camera_always_on": settings.features.camera_always_on,
        "assistant_name": os.environ.get("EVA_ASSISTANT_NAME", ASSISTANT_NAME),
        "user_name": os.environ.get("EVA_USER_NAME", USER_NAME),
        "startup_greeting": os.environ.get("EVA_STARTUP_GREETING", STARTUP_GREETING),
        "persona_style": os.environ.get("EVA_PERSONA_STYLE", PERSONA_STYLE),
        "offline_message": "Yo Ankit, backend looks offline right now. Some controls won't work till it's back.",
        "voice": {
            "enabled": os.environ.get("EVA_VOICE_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"},
            "provider": os.environ.get("EVA_TTS_PROVIDER", "browser"),
            "gender": os.environ.get("EVA_VOICE_GENDER", "female"),
            "rate": float(os.environ.get("EVA_VOICE_RATE", "2.35")),
            "pitch": float(os.environ.get("EVA_VOICE_PITCH", "1.04")),
            "volume": float(os.environ.get("EVA_VOICE_VOLUME", "1.0")),
            "preferred_voices": [
                item.strip()
                for item in os.environ.get(
                    "EVA_PREFERRED_VOICES",
                    "Microsoft Aria Online,Microsoft Jenny Online,Microsoft Sonia Online,Microsoft Ava Online,Google US English Female,Google UK English Female,Samantha,Jenny,Aria",
                ).split(",")
                if item.strip()
            ],
            "piper": piper_status(),
        },
        "vision": vision_status(),
    }


@router.post("/tts/piper")
async def tts_piper(payload: TTSRequest) -> Response:
    try:
        audio = synthesize_piper_wav(payload.text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Piper TTS failed: {exc}") from exc
    return Response(content=audio, media_type="audio/wav")


@router.get("/tools")
async def list_tools() -> dict:
    return {"tools": tools.list_tools(), "planner_tools": tools.planner_specs()}


@router.post("/tools/{tool_name}")
async def run_tool(tool_name: str, body: dict | None = None) -> dict:
    try:
        result = tools.run(tool_name, **(body or {}))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"tool": tool_name, "result": result}


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    started_at = time.perf_counter()
    session_id = payload.session_id or uuid4().hex
    memory = request.app.state.memory
    settings = request.app.state.settings
    session_context = _session_context(request, session_id)
    _timing_log(session_id, "route_received", started_at, chars=len(payload.message))

    fast = maybe_handle_fast_command(payload.message, tools, session_context, memory, session_id)
    if fast is not None:
        reply, source = fast
        _persist_and_log(
            memory, session_id, session_context, started_at, payload.message, reply, source,
            log_kind="deterministic_command", log_payload={"source": source, "reply": reply},
            matched_event="fast_command_matched", matched_fields={"source": source},
        )
        return ChatResponse(session_id=session_id, reply=reply, source=source)

    casual = maybe_handle_fast_response(payload.message)
    if casual is not None:
        reply, source = casual
        _persist_and_log(
            memory, session_id, session_context, started_at, payload.message, reply, source,
            log_kind="fast_casual_response", log_payload={"source": source, "reply": reply},
            matched_event="fast_casual_matched",
        )
        return ChatResponse(session_id=session_id, reply=reply, source=source)

    operator = handle_operator_command(payload.message, _operator_context(session_context))
    if operator is not None:
        reply = str(operator.get("response") or "Done.")
        memory.add_message(session_id, "user", payload.message)
        memory.add_message(session_id, "assistant", reply)
        _safe_log(memory, session_id, "operator_command", {key: operator.get(key) for key in ("route", "tool", "args", "requires_confirmation", "action")})
        _timing_log(session_id, "operator_command_matched", started_at, tool=operator.get("tool"))
        _timing_log(session_id, "response_ready", started_at, source="operator-command", total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
        remember_answer_provenance(session_context, source="operator-command", tools=[str(operator.get("tool") or "")] if operator.get("tool") else [])
        return ChatResponse(
            session_id=session_id,
            reply=reply,
            source="operator-command",
            requires_confirmation=bool(operator.get("requires_confirmation")),
            action=operator.get("action"),
        )

    capability = classify_capability_intent(payload.message, session_context)
    capability_reply = _handle_capability_route(payload.message, capability, session_context, memory, session_id, settings)
    if capability_reply is not None:
        reply, source = capability_reply
        _persist_and_log(
            memory, session_id, session_context, started_at, payload.message, reply, source,
            log_kind="capability_route", log_payload={"classification": capability, "source": source},
            matched_event="capability_route_matched",
            matched_fields={"capability": capability.get("capability"), "route": capability.get("suggested_route")},
            provenance="answer", provenance_tools=[str(capability.get("suggested_route") or "")],
        )
        return ChatResponse(session_id=session_id, reply=reply, source=source)

    if is_agentic_intent(payload.message):
        history = memory.recent_messages(session_id)
        memory.add_message(session_id, "user", payload.message)
        result = await run_agentic_task(
            payload.message,
            {
                "settings": settings,
                "registry": tools,
                "executor": executor,
                "memory": memory,
                "session_id": session_id,
                "session_context": session_context,
                "history": history,
                "execute_tools": True,
            },
        )
        reply = result.get("final_response") or "I stopped the task without a final response."
        memory.add_message(session_id, "assistant", reply)
        _safe_log(memory, session_id, "agent_task_result", {"task_id": result.get("task_id"), "status": result.get("status"), "safety_stops": result.get("safety_stops")})
        _timing_log(session_id, "response_ready", started_at, source="agent-runner", total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
        _remember_final_source(session_context, "agent-runner")
        return ChatResponse(
            session_id=session_id,
            reply=reply,
            source="agent-runner",
            requires_confirmation=bool(result.get("requires_confirmation")),
            action=result.get("action"),
        )


    history = memory.recent_messages(session_id)
    memory.add_message(session_id, "user", payload.message)

    try:
        _timing_log(session_id, "planner_started", started_at)
        planner = ToolCallPlanner(settings.models, tools)
        decision = await planner.plan(payload.message, history)
        _safe_log(memory, session_id, "planner_decision", _decision_payload(decision))
        selected_provider = next((item.get("selected_provider") for item in planner.last_llm_attempts if item.get("selected_provider")), None)
        _timing_log(session_id, "provider_selected", started_at, provider=selected_provider or "local_fallback")
    except (PlannerError, RuntimeError) as exc:
        _safe_log(memory, session_id, "planner_error", {"error": str(exc)})
        reply, source = await _fallback_answer(payload.message, history, settings)
        memory.add_message(session_id, "assistant", reply)
        _timing_log(session_id, "response_ready", started_at, source=source, total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
        _remember_final_source(session_context, source)
        return ChatResponse(session_id=session_id, reply=reply, source=source)

    if decision.type in {"answer", "done"}:
        reply = decision.final_response
        memory.add_message(session_id, "assistant", reply)
        _timing_log(session_id, "response_ready", started_at, source="planner-answer", total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
        _remember_final_source(session_context, "planner-answer")
        return ChatResponse(session_id=session_id, reply=reply, source="planner-answer")

    if decision.type == "confirmation_required":
        reply = decision.final_response
        memory.add_message(session_id, "assistant", reply)
        _timing_log(session_id, "response_ready", started_at, source="planner-confirmation", total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
        _remember_final_source(session_context, "planner-confirmation")
        return ChatResponse(session_id=session_id, reply=reply, source="planner-confirmation", requires_confirmation=True, action=decision.action)

    for call in decision.tool_calls:
        _timing_log(session_id, "tool_started", started_at, tool=call.tool)
    results = executor.execute_all(decision.tool_calls)
    _remember_web_results_from_tools(session_context, results)
    _safe_log(memory, session_id, "tool_results", {"results": _results_payload(results)})
    if any(result.requires_confirmation for result in results):
        pending = next(result for result in results if result.requires_confirmation)
        reply = pending.error or "This action requires confirmation."
        memory.add_message(session_id, "assistant", reply)
        _timing_log(session_id, "response_ready", started_at, source="executor-confirmation", total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
        _remember_final_source(session_context, "executor-confirmation", results)
        return ChatResponse(session_id=session_id, reply=reply, source="executor-confirmation", requires_confirmation=True, action=pending.action)

    reply, source = await _synthesize_tool_response(payload.message, results, history, settings)
    memory.add_message(session_id, "assistant", reply)
    _safe_log(memory, session_id, "assistant_response", {"source": source, "reply": reply})
    _timing_log(session_id, "response_ready", started_at, source=source, total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
    _remember_final_source(session_context, source, results)
    return ChatResponse(session_id=session_id, reply=reply, source=source)


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        started_at = time.perf_counter()
        session_id = payload.session_id or uuid4().hex
        memory = request.app.state.memory
        settings = request.app.state.settings
        session_context = _session_context(request, session_id)
        _timing_log(session_id, "route_received", started_at, chars=len(payload.message), stream=True)

        fast = maybe_handle_fast_command(payload.message, tools, session_context, memory, session_id)
        if fast is not None:
            reply, source = fast
            _persist_and_log(
                memory, session_id, session_context, started_at, payload.message, reply, source,
                log_kind="deterministic_command", log_payload={"source": source, "reply": reply},
                matched_event="fast_command_matched", matched_fields={"source": source},
            )
            for line in _simple_stream_events(session_id, source, reply):
                yield line
            return

        casual = maybe_handle_fast_response(payload.message)
        if casual is not None:
            reply, source = casual
            _persist_and_log(
                memory, session_id, session_context, started_at, payload.message, reply, source,
                log_kind="fast_casual_response", log_payload={"source": source, "reply": reply},
                matched_event="fast_casual_matched",
            )
            for line in _simple_stream_events(session_id, source, reply):
                yield line
            return

        operator = handle_operator_command(payload.message, _operator_context(session_context))
        if operator is not None:
            reply = str(operator.get("response") or "Done.")
            memory.add_message(session_id, "user", payload.message)
            memory.add_message(session_id, "assistant", reply)
            _safe_log(memory, session_id, "operator_command", {key: operator.get(key) for key in ("route", "tool", "args", "requires_confirmation", "action")})
            _timing_log(session_id, "operator_command_matched", started_at, tool=operator.get("tool"))
            _timing_log(session_id, "response_ready", started_at, source="operator-command", total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
            remember_answer_provenance(session_context, source="operator-command", tools=[str(operator.get("tool") or "")] if operator.get("tool") else [])
            yield _json_line({"type": "meta", "session_id": session_id, "source": "operator-command"})
            if operator.get("tool"):
                yield _json_line({"type": "tool", "tool": operator.get("tool"), "args": operator.get("args") or {}})
            result = operator.get("result")
            if isinstance(result, dict):
                yield _json_line({"type": "tool_result", **result})
            if operator.get("requires_confirmation"):
                yield _json_line({"type": "confirmation_required", "requires_confirmation": True, "action": operator.get("action"), "message": reply})
            yield _json_line({"type": "token", "text": reply})
            yield _json_line({"type": "done", "reply": reply})
            return

        capability = classify_capability_intent(payload.message, session_context)
        capability_reply = _handle_capability_route(payload.message, capability, session_context, memory, session_id, settings)
        if capability_reply is not None:
            reply, source = capability_reply
            _persist_and_log(
                memory, session_id, session_context, started_at, payload.message, reply, source,
                log_kind="capability_route", log_payload={"classification": capability, "source": source},
                matched_event="capability_route_matched",
                matched_fields={"capability": capability.get("capability"), "route": capability.get("suggested_route")},
                provenance="answer", provenance_tools=[str(capability.get("suggested_route") or "")],
            )
            for line in _simple_stream_events(session_id, source, reply, route=capability.get("suggested_route")):
                yield line
            return

        if is_agentic_intent(payload.message):
            history = memory.recent_messages(session_id)
            memory.add_message(session_id, "user", payload.message)
            yield _json_line({"type": "meta", "session_id": session_id, "source": "agent-runner", "route": "agentic"})
            yield _json_line({"type": "agent_task", "message": "Agent task started"})
            result = await run_agentic_task(
                payload.message,
                {
                    "settings": settings,
                    "registry": tools,
                    "executor": executor,
                    "memory": memory,
                    "session_id": session_id,
                    "session_context": session_context,
                    "history": history,
                    "execute_tools": True,
                },
            )
            for event in result.get("events", []):
                if event.get("type") == "agent_task":
                    continue
                yield _json_line(event)
            reply = result.get("final_response") or "I stopped the task without a final response."
            memory.add_message(session_id, "assistant", reply)
            _safe_log(memory, session_id, "agent_task_result", {"task_id": result.get("task_id"), "status": result.get("status"), "safety_stops": result.get("safety_stops")})
            _timing_log(session_id, "response_ready", started_at, source="agent-runner", total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
            _remember_final_source(session_context, "agent-runner")
            if result.get("requires_confirmation"):
                yield _json_line({"type": "confirmation_required", "requires_confirmation": True, "action": result.get("action"), "message": reply})
            yield _json_line({"type": "token", "text": reply})
            yield _json_line({"type": "done", "reply": reply})
            return


        history = memory.recent_messages(session_id)
        memory.add_message(session_id, "user", payload.message)
        yield _json_line({"type": "planning", "message": "Planning..."})

        try:
            _timing_log(session_id, "planner_started", started_at)
            planner = ToolCallPlanner(settings.models, tools)
            decision = await planner.plan(payload.message, history)
            _safe_log(memory, session_id, "planner_decision", _decision_payload(decision))
            selected_provider = next((item.get("selected_provider") for item in planner.last_llm_attempts if item.get("selected_provider")), None)
            _timing_log(session_id, "provider_selected", started_at, provider=selected_provider or "local_fallback")
        except (PlannerError, RuntimeError) as exc:
            _safe_log(memory, session_id, "planner_error", {"error": str(exc)})
            route = _local_fallback_route(settings)
            reply_parts: list[str] = []
            yield _json_line({"type": "meta", "session_id": session_id, "source": _source(route), "route": route.reason})
            try:
                async for token in _stream_with_route(payload.message, history, route, settings):
                    reply_parts.append(token)
                    yield _json_line({"type": "token", "text": token})
            except RuntimeError as model_exc:
                fallback = ModelRoute("ollama", settings.models.fast_model, "fallback-local")
                yield _json_line({"type": "meta", "session_id": session_id, "source": _source(fallback), "route": fallback.reason})
                try:
                    async for token in _stream_with_route(payload.message, history, fallback, settings):
                        reply_parts.append(token)
                        yield _json_line({"type": "token", "text": token})
                except RuntimeError:
                    message = f"Planner failed, then model fallback failed too. First error: {model_exc}"
                    memory.add_message(session_id, "assistant", message)
                    _timing_log(session_id, "response_ready", started_at, source="model-error", total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
                    yield _json_line({"type": "error", "message": message})
                    return
            reply = "".join(reply_parts).strip() or "I heard you, but the model returned an empty response."
            memory.add_message(session_id, "assistant", reply)
            _timing_log(session_id, "response_ready", started_at, source="model-fallback", total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
            _remember_final_source(session_context, "model-fallback")
            yield _json_line({"type": "done", "reply": reply})
            return

        yield _json_line({"type": "meta", "session_id": session_id, "source": f"planner:{decision.type}", "route": decision.reason})

        if decision.type in {"answer", "done"}:
            reply = decision.final_response
            memory.add_message(session_id, "assistant", reply)
            _timing_log(session_id, "response_ready", started_at, source="planner-answer", total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
            _remember_final_source(session_context, "planner-answer")
            yield _json_line({"type": "token", "text": reply})
            yield _json_line({"type": "done", "reply": reply})
            return

        if decision.type == "confirmation_required":
            reply = decision.final_response
            memory.add_message(session_id, "assistant", reply)
            _timing_log(session_id, "response_ready", started_at, source="planner-confirmation", total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
            _remember_final_source(session_context, "planner-confirmation")
            yield _json_line({"type": "confirmation_required", "requires_confirmation": True, "action": decision.action, "message": reply})
            yield _json_line({"type": "token", "text": reply})
            yield _json_line({"type": "done", "reply": reply})
            return

        results = []
        for call in decision.tool_calls:
            _timing_log(session_id, "tool_started", started_at, tool=call.tool)
            yield _json_line({"type": "tool", "tool": call.tool, "args": call.args})
            result = executor.execute(call)
            results.append(result)
            if result.tool in {"web_search", "browser_search"} and result.ok:
                remember_web_results(session_context, result.result)
            yield _json_line({"type": "tool_result", **result.as_dict()})
            if result.requires_confirmation:
                break

        _safe_log(memory, session_id, "tool_results", {"results": _results_payload(results)})
        if any(result.requires_confirmation for result in results):
            pending = next(result for result in results if result.requires_confirmation)
            reply = pending.error or "This action requires confirmation."
            memory.add_message(session_id, "assistant", reply)
            _timing_log(session_id, "response_ready", started_at, source="executor-confirmation", total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
            _remember_final_source(session_context, "executor-confirmation", results)
            yield _json_line({"type": "confirmation_required", "requires_confirmation": True, "action": pending.action, "message": reply})
            yield _json_line({"type": "token", "text": reply})
            yield _json_line({"type": "done", "reply": reply})
            return

        reply, source = await _synthesize_tool_response(payload.message, results, history, settings)
        memory.add_message(session_id, "assistant", reply)
        _safe_log(memory, session_id, "assistant_response", {"source": source, "reply": reply})
        _timing_log(session_id, "response_ready", started_at, source=source, total_ms=f"{(time.perf_counter() - started_at) * 1000:.1f}")
        _remember_final_source(session_context, source, results)
        yield _json_line({"type": "meta", "session_id": session_id, "source": source})
        yield _json_line({"type": "token", "text": reply})
        yield _json_line({"type": "done", "reply": reply})
 
    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.get("/screen/snapshot")
async def screen_snapshot(request: Request) -> Response:
    settings = request.app.state.settings
    if not settings.features.screen_capture:
        raise HTTPException(status_code=403, detail="Screen capture is disabled.")
    try:
        image = capture_primary_screen_jpeg()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Screen capture failed: {exc}") from exc
    return Response(content=image, media_type="image/jpeg")

