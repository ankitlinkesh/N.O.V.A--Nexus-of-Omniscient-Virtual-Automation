from __future__ import annotations

import os
import re
from typing import Any

from ..core.web_context import summarize_web_result
from .planner import PlannedToolCall

DEFAULT_MAX_AGENT_STEPS = 6
DEFAULT_MAX_TOOLS_PER_TASK = 10
DEFAULT_MAX_WEB_SEARCHES_PER_TASK = 4
DEFAULT_MAX_SCREEN_CAPTURES_PER_TASK = 2
# Phase 64: how many planned tool calls ToolExecutor.execute_all() will run in
# one batch. This used to be a hardcoded `calls[:3]` with no name and no way
# to configure it; the default stays 3 (no behavior change out of the box),
# but it is now named and overridable, and — critically — execute_all() now
# REPORTS when this cap actually truncates a plan instead of silently
# dropping the rest (see executor.py). Distinct from max_tools_per_task(),
# which is the whole-task budget enforced in runner.py; this is the smaller
# per-batch slice within a single non-agentic chat turn.
DEFAULT_MAX_TOOLS_PER_STEP = 3
# Phase 39 reliability budgets: how many consecutive failed steps to tolerate
# (attempting recovery/replan between them) before stopping honestly, and how
# many steps without progress before declaring a stall.
DEFAULT_MAX_CONSECUTIVE_FAILURES = 2
DEFAULT_MAX_STEPS_WITHOUT_PROGRESS = 3

POWER_TOOLS = {"guarded_power_action", "system_power"}
WORKSPACE_TOOLS = {"workspace_status", "workspace_list_files", "workspace_read_file", "workspace_search", "workspace_summarize_file", "workspace_project_summary"}
CODE_TOOLS = {"code_status", "code_reindex", "code_search", "code_find_symbol", "code_project_map", "code_explain_feature", "code_debug_traceback", "code_plan_change"}
RESEARCH_TOOLS = {"research_start_topic", "research_web", "research_save_note", "research_recall", "research_summary", "research_status"}
WINDOW_TOOLS = {"desktop_observe", "window_list", "window_active", "window_focus", "window_close_safe", "window_minimize", "window_maximize", "verify_last_action"}
BROWSER_TOOLS = {
    "browser_status",
    "browser_open_url",
    "browser_search",
    "browser_current_page",
    "browser_summarize_page",
    "browser_extract_links",
    "browser_save_page_to_research",
    "browser_observe",
    "chrome_open_web_app",
    "chrome_search_site",
    "chrome_copy_current_url",
    "chrome_new_tab",
    "chrome_close_tab",
    "chrome_reload",
    "chrome_back",
    "chrome_forward",
    "chrome_focus_address_bar",
    "browser_open_result_and_verify",
}
SPOTIFY_TOOLS = {"spotify_status", "spotify_search", "spotify_play_query", "spotify_search_desktop", "spotify_play_desktop", "spotify_pause", "spotify_next", "spotify_previous", "spotify_restart_current"}
DESKTOP_ACTION_TOOLS = {"open_app", "open_folder", "open_url", "web_search", "media_control", "media_key", "lock_laptop", "capture_screen", "analyze_screen", *WINDOW_TOOLS, *BROWSER_TOOLS, *WORKSPACE_TOOLS, *CODE_TOOLS, *RESEARCH_TOOLS, *SPOTIFY_TOOLS}
AGENTIC_PREFIXES = (
    "agent mode:",
    "research:",
    "compare:",
    "find and summarize:",
)
AGENTIC_TASK_MARKERS = (
    "find and summarize",
    "research",
    "compare",
    "figure out",
    "fix this error",
    "inspect eva project",
    "summarize the backend",
    "summarize backend",
    "explain the architecture",
    "debug this error in eva",
    "what changed in eva",
    "help me add",
    "continue this project",
    "what should we build next in eva",
    "build a knowledge base",
    "make eva a superbrain",
    "find and remember",
    "inspect code",
    "fix this error",
    "plan change",
    "make a patch plan",
    "find dead code",
    "find todos",
)
WORKSPACE_INTENT_MARKERS = (
    "eva project",
    "project structure",
    "workspace",
    "backend architecture",
    "agent runner",
    "llm router",
    "web_search",
    "tavily",
    "where is",
    "where are",
    "code",
    "symbol",
    "traceback",
    "patch plan",
)


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def max_agent_steps() -> int:
    return max(1, env_int("MAX_AGENT_STEPS", DEFAULT_MAX_AGENT_STEPS))


def max_tools_per_task() -> int:
    return max(1, env_int("MAX_TOOLS_PER_TASK", DEFAULT_MAX_TOOLS_PER_TASK))


def max_tools_per_step() -> int:
    return max(1, env_int("EVA_MAX_TOOLS_PER_STEP", DEFAULT_MAX_TOOLS_PER_STEP))


def max_web_searches_per_task() -> int:
    return max(0, env_int("MAX_WEB_SEARCHES_PER_TASK", DEFAULT_MAX_WEB_SEARCHES_PER_TASK))


def max_screen_captures_per_task() -> int:
    return max(0, env_int("MAX_SCREEN_CAPTURES_PER_TASK", DEFAULT_MAX_SCREEN_CAPTURES_PER_TASK))


def max_consecutive_failures() -> int:
    return max(1, env_int("EVA_AGENT_MAX_CONSECUTIVE_FAILURES", DEFAULT_MAX_CONSECUTIVE_FAILURES))


def max_steps_without_progress() -> int:
    return max(1, env_int("EVA_AGENT_MAX_STEPS_WITHOUT_PROGRESS", DEFAULT_MAX_STEPS_WITHOUT_PROGRESS))


def agentic_goal(message: str) -> str:
    clean = message.strip()
    lowered = clean.lower()
    for prefix in AGENTIC_PREFIXES:
        if lowered.startswith(prefix):
            return clean.split(":", 1)[1].strip() or clean
    return clean


def is_agentic_intent(message: str) -> bool:
    text = " ".join(message.lower().strip().split())
    if any(text.startswith(prefix) for prefix in AGENTIC_PREFIXES):
        return True
    if text.startswith(("find ", "search ", "look up ")) and "summarize" in text:
        return True
    if any(marker in text for marker in WORKSPACE_INTENT_MARKERS) and any(
        action in text for action in ("inspect", "summarize", "explain", "find", "where", "debug", "changed", "build next", "implemented")
    ):
        return True
    if any(text.startswith(marker) for marker in AGENTIC_TASK_MARKERS):
        return True
    return False


def explicitly_requests_screen(message: str) -> bool:
    text = " ".join(message.lower().strip().split())
    verbs = ("look at", "check", "inspect", "analyze", "analyse", "capture", "see", "view", "show")
    nouns = ("screen", "display", "what is open", "what's open", "error")
    return any(verb in text for verb in verbs) and any(noun in text for noun in nouns)


def tool_signature(call: PlannedToolCall) -> str:
    args = call.args or {}
    if call.tool in {"web_search", "research_web", "browser_search"}:
        return f"{call.tool}:{str(args.get('topic') or '')}:{str(args.get('query') or '').strip().lower()}"
    if call.tool == "open_app":
        return f"open_app:{str(args.get('app') or args.get('app_name') or '').strip().lower()}"
    if call.tool == "open_folder":
        return f"open_folder:{str(args.get('folder') or args.get('folder_name') or '').strip().lower()}"
    if call.tool in POWER_TOOLS:
        return f"{call.tool}:{str(args.get('action') or '').strip().lower()}"
    return f"{call.tool}:{repr(sorted(args.items()))}"


def describe_tool_observation(tool: str, result: Any) -> str:
    if isinstance(result, dict):
        if tool == "web_search":
            query = result.get("query") or "search"
            count = len(result.get("results") or []) if isinstance(result.get("results"), list) else 0
            if result.get("ok") and result.get("provider") == "tavily":
                return summarize_web_result(result, include_prompt=True)
            if result.get("fallback") == "browser":
                return f"web_search opened browser fallback for {query} because Tavily was {result.get('error') or 'unavailable'}."
        if tool == "browser_search":
            query = result.get("query") or "search"
            count = len(result.get("results") or []) if isinstance(result.get("results"), list) else 0
            return f"browser_search opened browser search for {query} and observed {count} Tavily result(s)."
        if tool == "browser_current_page":
            return f"browser_current_page title={result.get('current_title') or result.get('active_window_title') or 'unknown'} url={result.get('current_url') or 'unknown'}."
        if tool == "browser_summarize_page":
            if result.get("ok"):
                return f"browser_summarize_page observed: {str(result.get('page_summary') or '')[:320]}"
            return f"browser_summarize_page blocked or failed: {result.get('error') or 'unknown error'}."
        if tool == "browser_extract_links":
            return f"browser_extract_links found {len(result.get('extracted_links') or [])} links."
        if tool == "browser_save_page_to_research":
            return str(result.get("message") or f"browser_save_page_to_research saved {result.get('saved_count', 0)} source(s).")
        if tool == "browser_observe":
            return f"browser_observe title={result.get('current_title') or 'unknown'} links={len(result.get('extracted_links') or [])}."
        if tool == "capture_screen":
            return "capture_screen stored one screenshot for inspection."
        if tool == "analyze_screen":
            if result.get("ok"):
                summary = str(result.get("summary") or "screen analyzed").strip()
                return f"analyze_screen observed: {summary[:240]}"
            summary = str(result.get("summary") or "").strip()
            if result.get("rate_limited") and summary:
                return summary
            return f"analyze_screen failed: {result.get('error') or 'unknown error'}."
        if tool == "workspace_search":
            count = len(result.get("matches") or []) if isinstance(result.get("matches"), list) else 0
            query = result.get("query") or "workspace"
            matches = result.get("matches") or []
            lines = [f"workspace_search found {count} safe matches for {query}."]
            for item in matches[:6] if isinstance(matches, list) else []:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('path')}:{item.get('line')} - {item.get('snippet')}")
            return "\n".join(lines)
        if tool == "workspace_list_files":
            count = len(result.get("files") or []) if isinstance(result.get("files"), list) else 0
            return f"workspace_list_files listed {count} safe files."
        if tool == "workspace_read_file":
            return f"workspace_read_file safely read {result.get('path')} ({result.get('line_count')} lines)."
        if tool == "workspace_project_summary":
            sections = result.get("sections") or []
            folders = [str(item.get("folder")) for item in sections if isinstance(item, dict) and item.get("folder")]
            return "workspace_project_summary inspected: " + ", ".join(folders[:8])
        if tool == "workspace_summarize_file":
            return f"workspace_summarize_file: {str(result.get('summary') or '')[:300]}"
        if tool == "code_status":
            return f"code_status indexed={result.get('indexed')} files={result.get('indexed_files')}."
        if tool == "code_reindex":
            return f"code_reindex indexed {result.get('indexed_files', 0)} safe files."
        if tool == "code_search":
            return f"code_search found {len(result.get('matches') or [])} matches for {result.get('query')}."
        if tool == "code_find_symbol":
            return f"code_find_symbol found {len(result.get('matches') or [])} matches for {result.get('symbol')}."
        if tool == "code_project_map":
            modules = result.get("modules") or []
            names = [str(item.get("folder")) for item in modules if isinstance(item, dict) and item.get("folder")]
            return "code_project_map inspected: " + ", ".join(names[:10])
        if tool == "code_explain_feature":
            files = result.get("related_files") or []
            return f"code_explain_feature found {len(files) if isinstance(files, list) else 0} related files for {result.get('feature')}."
        if tool == "code_debug_traceback":
            return f"code_debug_traceback parsed {result.get('exception_type') or 'error'} and suggested {len(result.get('likely_files') or [])} file(s)."
        if tool == "code_plan_change":
            return f"code_plan_change produced a read-only patch plan for {result.get('goal')}."
        if tool == "research_recall":
            matches = result.get("matches") or []
            return f"research_recall found {len(matches) if isinstance(matches, list) else 0} saved local matches for {result.get('topic')}."
        if tool == "research_web":
            saved = result.get("saved_results") or []
            if result.get("ok"):
                lines = [f"research_web saved {len(saved) if isinstance(saved, list) else 0} fresh sources for {result.get('topic')}."]
                for item in saved[:5] if isinstance(saved, list) else []:
                    if isinstance(item, dict):
                        lines.append(f"- {item.get('title')}: {item.get('url')} - {item.get('content_summary') or item.get('snippet')}")
                return "\n".join(lines)
            return f"research_web failed for {result.get('topic')}: {result.get('error') or 'unknown error'}."
        if tool == "research_summary":
            return str(result.get("summary") or f"research_summary completed for {result.get('topic')}.")[:1200]
        if tool == "research_save_note":
            return str(result.get("message") or f"research_save_note saved note for {result.get('topic')}.")
        if tool == "research_start_topic":
            return str(result.get("message") or "research_start_topic completed.")
        if tool == "desktop_observe":
            return f"desktop_observe active={result.get('active_window_title') or 'unknown'} windows={len(result.get('open_windows') or [])}."
        if tool == "window_list":
            return f"window_list found {len(result.get('windows') or [])} visible windows."
        if tool == "window_active":
            window = result.get("window") if isinstance(result.get("window"), dict) else {}
            return f"window_active observed {window.get('title') or 'unknown window'}."
        if tool in {"window_focus", "window_minimize", "window_maximize", "window_close_safe"}:
            if result.get("ok"):
                window = result.get("window") if isinstance(result.get("window"), dict) else {}
                return f"{tool} completed for {window.get('title') or result.get('query') or 'window'}."
            return f"{tool} failed: {result.get('error') or 'unknown error'}."
        if tool == "verify_last_action":
            return str(result.get("message") or ("verified" if result.get("verified") else "verification inconclusive"))
    return f"{tool} returned {str(result)[:300]}"


def is_unsupported_capability(message: str) -> bool:
    text = " ".join(message.lower().split())
    unsupported_patterns = (
        r"\bemail\b",
        r"\bsend (a )?message\b",
        r"\bbook\b.*\bcalendar\b",
        r"\bcall\b.*\bphone\b",
    )
    return any(re.search(pattern, text) for pattern in unsupported_patterns)
