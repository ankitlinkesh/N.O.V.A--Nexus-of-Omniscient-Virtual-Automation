from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from ..screen.capture import capture_primary_screen_jpeg
from ..screen.screen_tools import screen_click, screen_hotkey, screen_observe, screen_press, screen_scroll, screen_type_text, screen_wait
from ..vision import analyze_screen_image_sync
from ..workspace import safe_list_files, safe_read_file, search_workspace, summarize_file, summarize_workspace, workspace_status
from ..code import (
    build_code_index,
    code_explain_feature,
    code_project_map,
    code_status,
    debug_traceback,
    find_symbol,
    plan_code_change,
    search_code,
)
from ..research import research_recall, research_save_note, research_start_topic, research_status, research_summary, research_web
from ..media import (
    next_spotify,
    pause_spotify,
    play_spotify_desktop,
    play_spotify_query,
    previous_spotify,
    previous_spotify_track,
    restart_current_spotify_track,
    search_spotify,
    search_spotify_desktop,
    spotify_now_playing_status,
    spotify_status,
)
from ..browser import (
    activate_top_youtube_result,
    ask_chatgpt_in_chrome,
    browser_current_page,
    browser_extract_links,
    browser_observe,
    browser_open_result_and_verify,
    browser_open_url,
    browser_save_page_to_research,
    browser_search,
    browser_status,
    browser_summarize_page,
    recover_browser_target,
    search_site_and_verify,
    verify_browser_target,
    chrome_back,
    chrome_close_tab,
    chrome_copy_current_url,
    chrome_focus_address_bar,
    chrome_forward,
    chrome_new_tab,
    chrome_open_web_app,
    chrome_reload,
    chrome_search_site,
    open_web_app_and_verify,
)
from ..desktop import (
    active_window,
    close_window_safe,
    desktop_observe,
    focus_window_safe,
    list_windows,
    maximize_window_safe,
    minimize_window_safe,
    verify_last_action,
)
from .app_control_tools import app_close_request, app_focus, app_open, browser_open_url_tool, browser_search_tool
from .desktop import close_app, media_key, open_app, open_folder, open_url, system_power, system_status, web_search
from .message_tools import message_confirm_send, message_prepare, message_send_via_ui
from .safe_file_tools import file_copy, file_delete, file_list_dir, file_move, file_patch_text, file_read_text, file_write_text
from ..security import tool_gate

SafetyLevel = Literal["safe", "sensitive", "dangerous"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_schema: dict[str, Any]
    safety_level: SafetyLevel
    handler: Callable[..., Any]
    category: str = "general"
    risk: str | None = None
    requires_explicit_intent: bool = False
    verification_strategy: str = "Tool returns structured success or failure information."
    failure_recovery: str = "Report the failure clearly and avoid unsafe retries."
    action_type: str = "SAFE_LOCAL_READ"
    risk_categories: tuple[str, ...] = ("SAFE_LOCAL_READ",)
    requires_confirmation: bool = False
    supports_rollback: bool = False
    verification_method: str = "command_result_success"

    @property
    def safe_by_default(self) -> bool:
        return self.safety_level == "safe"


POWER_ACTIONS = {"shutdown", "restart", "sleep", "sign_out", "log_out"}
MEDIA_ACTIONS = {"mute", "volume_up", "volume_down", "play_pause", "next", "previous"}
KNOWN_APPS = {
    "calculator",
    "chrome",
    "cmd",
    "codex",
    "discord",
    "edge",
    "explorer",
    "notepad",
    "paint",
    "powershell",
    "settings",
    "spotify",
    "task manager",
    "terminal",
    "vscode",
    "vs code",
    "visual studio code",
    "whatsapp",
    "word",
    "excel",
    "powerpoint",
}
KNOWN_FOLDERS = {"desktop", "documents", "downloads", "pictures", "videos", "music", "eva", "eva folder"}


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


def _status() -> dict[str, Any]:
    return asdict(system_status())


def _media_control(action: str) -> str:
    normalized = action.strip().lower().replace(" ", "_")
    if normalized not in MEDIA_ACTIONS:
        raise ValueError(f"Unsupported media action: {action}")
    return media_key(normalized)


def _lock_laptop() -> str:
    return system_power("lock")


def _guarded_power_action(action: str, confirmed: bool = False) -> str:
    normalized = action.strip().lower().replace(" ", "_")
    if normalized not in POWER_ACTIONS:
        raise ValueError(f"Unsupported power action: {action}")
    return system_power(normalized, confirmed=confirmed)


def _capture_screen() -> dict[str, Any]:
    image = capture_primary_screen_jpeg()
    data_dir = Path(__file__).resolve().parents[3] / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    output_path = data_dir / "latest_screen.jpg"
    output_path.write_bytes(image)
    return {
        "image_path": str(output_path),
        "bytes": len(image),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "note": "One-time screenshot captured. No continuous screen watching is active.",
    }


def _analyze_screen(question: str | None = None) -> dict[str, Any]:
    capture = _capture_screen()
    result = analyze_screen_image_sync(str(capture["image_path"]), user_question=question)
    if isinstance(result, dict):
        result["capture"] = {
            "image_path": capture.get("image_path"),
            "bytes": capture.get("bytes"),
            "captured_at": capture.get("captured_at"),
            "note": capture.get("note"),
        }
    return result

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {
            "status": ToolSpec(
                name="status",
                description="Return basic laptop runtime status.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=_status,
            ),
            "system_status": ToolSpec(
                name="system_status",
                description="Alias for status used by deterministic commands.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=_status,
            ),
            "open_app": ToolSpec(
                name="open_app",
                description="Open a known desktop app by common name. Supported examples: chrome, spotify, vscode, codex, settings, notepad.",
                args_schema=_schema({"app": {"type": "string", "enum": sorted(KNOWN_APPS)}}, ["app"]),
                safety_level="safe",
                handler=lambda app=None, app_name=None: open_app(str(app or app_name or "")),
            ),
            "close_app": ToolSpec(
                name="close_app",
                description="Close a configurable safe allowlist of common apps. Never kills arbitrary or system processes.",
                args_schema=_schema({"app": {"type": "string"}, "app_name": {"type": "string"}}, []),
                safety_level="sensitive",
                handler=lambda app=None, app_name=None: close_app(str(app or app_name or "")),
            ),
            "open_folder": ToolSpec(
                name="open_folder",
                description="Open a known folder: Downloads, Documents, Desktop, Pictures, Videos, Music, or Eva folder.",
                args_schema=_schema({"folder": {"type": "string", "enum": sorted(KNOWN_FOLDERS)}, "folder_name": {"type": "string"}}, []),
                safety_level="safe",
                handler=lambda folder=None, folder_name=None: open_folder(str(folder or folder_name or "")),
            ),
            "open_url": ToolSpec(
                name="open_url",
                description="Open an http or https URL in the default browser.",
                args_schema=_schema({"url": {"type": "string"}}, ["url"]),
                safety_level="safe",
                handler=open_url,
            ),
            "web_search": ToolSpec(
                name="web_search",
                description="Search the web with Tavily when configured, otherwise open a safe browser search fallback.",
                args_schema=_schema({"query": {"type": "string"}}, ["query"]),
                safety_level="safe",
                handler=web_search,
                action_type="NETWORK_ACTION",
                risk_categories=("NETWORK_ACTION",),
            ),
            "screen.observe": ToolSpec(
                name="screen.observe",
                description="Observe the screen once during an active user-requested task. Local only; raw screenshots are not sent to cloud here.",
                args_schema=_schema({"reason": {"type": "string"}}, ["reason"]),
                safety_level="sensitive",
                handler=lambda reason: screen_observe(str(reason)),
                category="screen",
                risk="medium",
                requires_explicit_intent=True,
                action_type="PRIVACY_SCREEN_READ",
                risk_categories=("PRIVACY_SCREEN_READ",),
                requires_confirmation=True,
                supports_rollback=False,
                verification_method="screen_state_changed",
            ),
            "screen.click": ToolSpec(
                name="screen.click",
                description="Click a verified visible UI target during an active task. Raw coordinates without a target are refused.",
                args_schema=_schema(
                    {
                        "target": {"type": "object"},
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "reason": {"type": "string"},
                        "required_confidence": {"type": "number"},
                    },
                    ["reason"],
                ),
                safety_level="safe",
                handler=lambda reason, target=None, x=None, y=None, required_confidence=0.75: screen_click(
                    x=int(x) if x is not None else None,
                    y=int(y) if y is not None else None,
                    reason=str(reason),
                    target=target if isinstance(target, dict) else None,
                    required_confidence=float(required_confidence or 0.75),
                ),
                category="screen",
                risk="low",
                action_type="SAFE_LOCAL_UI",
                risk_categories=("SAFE_LOCAL_UI",),
                verification_method="screen_state_changed",
            ),
            "screen.type_text": ToolSpec(
                name="screen.type_text",
                description="Type text into the focused visible UI during an active task.",
                args_schema=_schema({"text": {"type": "string"}, "reason": {"type": "string"}}, ["text", "reason"]),
                safety_level="sensitive",
                handler=lambda text, reason: screen_type_text(str(text), str(reason)),
                category="screen",
                risk="medium",
                action_type="SAFE_LOCAL_UI",
                risk_categories=("SAFE_LOCAL_UI",),
                requires_confirmation=True,
                verification_method="text_field_contains",
            ),
            "screen.hotkey": ToolSpec(
                name="screen.hotkey",
                description="Send a bounded hotkey to the visible UI during an active task.",
                args_schema=_schema({"keys": {"type": "array"}, "reason": {"type": "string"}}, ["keys", "reason"]),
                safety_level="sensitive",
                handler=lambda keys, reason: screen_hotkey(list(keys or []), str(reason)),
                category="screen",
                risk="medium",
                action_type="SAFE_LOCAL_UI",
                risk_categories=("SAFE_LOCAL_UI",),
                requires_confirmation=True,
                verification_method="screen_state_changed",
            ),
            "screen.press": ToolSpec(
                name="screen.press",
                description="Press one key in the visible UI during an active task.",
                args_schema=_schema({"key": {"type": "string"}, "reason": {"type": "string"}}, ["key", "reason"]),
                safety_level="sensitive",
                handler=lambda key, reason: screen_press(str(key), str(reason)),
                category="screen",
                risk="medium",
                action_type="SAFE_LOCAL_UI",
                risk_categories=("SAFE_LOCAL_UI",),
                requires_confirmation=True,
                verification_method="screen_state_changed",
            ),
            "screen.scroll": ToolSpec(
                name="screen.scroll",
                description="Scroll visible UI during an active task.",
                args_schema=_schema({"amount": {"type": "number"}, "reason": {"type": "string"}}, ["amount", "reason"]),
                safety_level="safe",
                handler=lambda amount, reason: screen_scroll(int(amount), str(reason)),
                category="screen",
                risk="low",
                action_type="SAFE_LOCAL_UI",
                risk_categories=("SAFE_LOCAL_UI",),
                verification_method="screen_state_changed",
            ),
            "screen.wait": ToolSpec(
                name="screen.wait",
                description="Wait briefly during an active task.",
                args_schema=_schema({"seconds": {"type": "number"}, "reason": {"type": "string"}}, ["seconds", "reason"]),
                safety_level="safe",
                handler=lambda seconds, reason: screen_wait(float(seconds), str(reason)),
                category="screen",
                risk="low",
                action_type="SAFE_LOCAL_UI",
                risk_categories=("SAFE_LOCAL_UI",),
                verification_method="command_result_success",
            ),
            "file.read_text": ToolSpec(
                name="file.read_text",
                description="Read a local text file only after privacy permission.",
                args_schema=_schema({"path": {"type": "string"}}, ["path"]),
                safety_level="sensitive",
                handler=lambda path: file_read_text(str(path)),
                category="file",
                risk="medium",
                action_type="PRIVACY_FILE_READ",
                risk_categories=("PRIVACY_FILE_READ",),
                requires_confirmation=True,
                verification_method="command_result_success",
            ),
            "file.write_text": ToolSpec(
                name="file.write_text",
                description="Write a local text file after override; creates checkpoint and verifies read-back.",
                args_schema=_schema({"path": {"type": "string"}, "content": {"type": "string"}, "confirmed": {"type": "boolean"}}, ["path", "content"]),
                safety_level="sensitive",
                handler=lambda path, content: file_write_text(str(path), str(content)),
                category="file",
                risk="high",
                action_type="DESTRUCTIVE_FILE_ACTION",
                risk_categories=("DESTRUCTIVE_FILE_ACTION",),
                requires_confirmation=True,
                supports_rollback=True,
                verification_method="file_contains",
            ),
            "file.patch_text": ToolSpec(
                name="file.patch_text",
                description="Patch a local text file after override; creates checkpoint and verifies read-back.",
                args_schema=_schema({"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}, "confirmed": {"type": "boolean"}}, ["path", "old", "new"]),
                safety_level="sensitive",
                handler=lambda path, old, new: file_patch_text(str(path), str(old), str(new)),
                category="file",
                risk="high",
                action_type="DESTRUCTIVE_FILE_ACTION",
                risk_categories=("DESTRUCTIVE_FILE_ACTION",),
                requires_confirmation=True,
                supports_rollback=True,
                verification_method="file_contains",
            ),
            "file.copy": ToolSpec(
                name="file.copy",
                description="Copy a local file after confirmation; can overwrite an existing destination.",
                args_schema=_schema({"src": {"type": "string"}, "dst": {"type": "string"}, "confirmed": {"type": "boolean"}}, ["src", "dst"]),
                safety_level="sensitive",
                handler=lambda src, dst: file_copy(str(src), str(dst)),
                category="file",
                risk="medium",
                action_type="DESTRUCTIVE_FILE_ACTION",
                risk_categories=("DESTRUCTIVE_FILE_ACTION",),
                requires_confirmation=True,
                supports_rollback=False,
                verification_method="file_exists",
            ),
            "file.move": ToolSpec(
                name="file.move",
                description="Move a local file after override; creates checkpoint when possible.",
                args_schema=_schema({"src": {"type": "string"}, "dst": {"type": "string"}, "confirmed": {"type": "boolean"}}, ["src", "dst"]),
                safety_level="sensitive",
                handler=lambda src, dst: file_move(str(src), str(dst)),
                category="file",
                risk="high",
                action_type="DESTRUCTIVE_FILE_ACTION",
                risk_categories=("DESTRUCTIVE_FILE_ACTION",),
                requires_confirmation=True,
                supports_rollback=True,
                verification_method="file_exists",
            ),
            "file.delete": ToolSpec(
                name="file.delete",
                description="Delete a local file only after override; creates checkpoint when possible.",
                args_schema=_schema({"path": {"type": "string"}, "confirmed": {"type": "boolean"}}, ["path"]),
                safety_level="dangerous",
                handler=lambda path: file_delete(str(path)),
                category="file",
                risk="high",
                action_type="DESTRUCTIVE_FILE_ACTION",
                risk_categories=("DESTRUCTIVE_FILE_ACTION",),
                requires_confirmation=True,
                supports_rollback=True,
                verification_method="file_exists",
            ),
            "file.list_dir": ToolSpec(
                name="file.list_dir",
                description="List a local directory.",
                args_schema=_schema({"path": {"type": "string"}}, ["path"]),
                safety_level="safe",
                handler=lambda path: file_list_dir(str(path)),
                category="file",
                risk="low",
                action_type="SAFE_LOCAL_READ",
                risk_categories=("SAFE_LOCAL_READ",),
                verification_method="command_result_success",
            ),
            "app.open": ToolSpec(
                name="app.open",
                description="Open a known local app.",
                args_schema=_schema({"app": {"type": "string"}}, ["app"]),
                safety_level="safe",
                handler=lambda app: app_open(str(app)),
                category="app",
                risk="low",
                action_type="SAFE_LOCAL_UI",
                risk_categories=("SAFE_LOCAL_UI",),
                verification_method="app_window_active",
            ),
            "app.focus": ToolSpec(
                name="app.focus",
                description="Focus a visible app/window.",
                args_schema=_schema({"query": {"type": "string"}}, ["query"]),
                safety_level="safe",
                handler=lambda query: app_focus(str(query)),
                category="app",
                risk="low",
                action_type="SAFE_LOCAL_UI",
                risk_categories=("SAFE_LOCAL_UI",),
                verification_method="app_window_active",
            ),
            "app.close_request": ToolSpec(
                name="app.close_request",
                description="Request app close with confirmation because unsaved work may exist.",
                args_schema=_schema({"app": {"type": "string"}, "confirmed": {"type": "boolean"}}, ["app"]),
                safety_level="sensitive",
                handler=lambda app, confirmed=False: app_close_request(str(app), bool(confirmed)),
                category="app",
                risk="medium",
                action_type="SYSTEM_CHANGE",
                risk_categories=("SYSTEM_CHANGE",),
                requires_confirmation=True,
                verification_method="app_window_active",
            ),
            "message.prepare": ToolSpec(
                name="message.prepare",
                description="Prepare a visible message draft locally without sending it.",
                args_schema=_schema({"recipient": {"type": "string"}, "message": {"type": "string"}}, ["recipient", "message"]),
                safety_level="safe",
                handler=lambda recipient, message: message_prepare(str(recipient), str(message)),
                category="message",
                risk="low",
                action_type="SAFE_LOCAL_UI",
                risk_categories=("SAFE_LOCAL_UI",),
                verification_method="message_draft_prepared",
            ),
            "message.confirm_send": ToolSpec(
                name="message.confirm_send",
                description="Ask confirmation before sending a message.",
                args_schema=_schema({"recipient": {"type": "string"}, "message": {"type": "string"}}, ["recipient", "message"]),
                safety_level="sensitive",
                handler=lambda recipient, message: message_confirm_send(str(recipient), str(message)),
                category="message",
                risk="medium",
                action_type="EXTERNAL_MESSAGE_SEND",
                risk_categories=("EXTERNAL_MESSAGE_SEND",),
                requires_confirmation=True,
                verification_method="message_sent_likely",
            ),
            "message.send_via_ui": ToolSpec(
                name="message.send_via_ui",
                description="Send a prepared message through visible UI only after explicit confirmation.",
                args_schema=_schema({"recipient": {"type": "string"}, "message": {"type": "string"}, "confirmed": {"type": "boolean"}}, ["recipient", "message"]),
                safety_level="sensitive",
                handler=lambda recipient, message, confirmed=False: message_send_via_ui(str(recipient), str(message), bool(confirmed)),
                category="message",
                risk="medium",
                action_type="EXTERNAL_MESSAGE_SEND",
                risk_categories=("EXTERNAL_MESSAGE_SEND",),
                requires_confirmation=True,
                supports_rollback=False,
                verification_method="message_sent_likely",
            ),
            "browser_status": ToolSpec(
                name="browser_status",
                description="Report safe browser detection, known current URL/title, and browser windows. Does not read cookies, credentials, forms, or private storage.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=browser_status,
            ),
            "browser_open_url": ToolSpec(
                name="browser_open_url",
                description="Open a validated http/https URL in the browser and remember it as Eva's known current browser page.",
                args_schema=_schema({"url": {"type": "string"}}, ["url"]),
                safety_level="safe",
                handler=browser_open_url,
            ),
            "browser_search": ToolSpec(
                name="browser_search",
                description="Open a browser search for a query and collect Tavily results when available for follow-up result opening.",
                args_schema=_schema({"query": {"type": "string"}}, ["query"]),
                safety_level="safe",
                handler=browser_search,
            ),
            "browser_current_page": ToolSpec(
                name="browser_current_page",
                description="Return Eva's known current browser page URL/title and active browser window title when available. Does not inspect private browser storage.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=browser_current_page,
            ),
            "browser_summarize_page": ToolSpec(
                name="browser_summarize_page",
                description="Summarize the known current safe public page, or a provided public URL. Refuses private, login, payment, local, and account pages.",
                args_schema=_schema({"url": {"type": "string"}}, []),
                safety_level="safe",
                handler=lambda url="": browser_summarize_page(str(url or "")),
            ),
            "browser_extract_links": ToolSpec(
                name="browser_extract_links",
                description="Extract links from the known current safe public page, or a provided public URL. Refuses private/sensitive pages.",
                args_schema=_schema({"url": {"type": "string"}, "limit": {"type": "number"}}, []),
                safety_level="safe",
                handler=lambda url="", limit=40: browser_extract_links(str(url or ""), int(limit or 40)),
            ),
            "browser_save_page_to_research": ToolSpec(
                name="browser_save_page_to_research",
                description="Save the current safe public browser page summary as a local research source for a topic.",
                args_schema=_schema({"topic": {"type": "string"}, "url": {"type": "string"}}, ["topic"]),
                safety_level="safe",
                handler=lambda topic, url="": browser_save_page_to_research(str(topic), str(url or "")),
            ),
            "browser_observe": ToolSpec(
                name="browser_observe",
                description="Return a bounded browser observation. Page summaries/links are optional and only for safe public pages.",
                args_schema=_schema(
                    {
                        "include_tabs": {"type": "boolean"},
                        "include_page_summary": {"type": "boolean"},
                        "include_links": {"type": "boolean"},
                    },
                    [],
                ),
                safety_level="safe",
                handler=lambda include_tabs=False, include_page_summary=False, include_links=False: browser_observe(
                    include_tabs=bool(include_tabs),
                    include_page_summary=bool(include_page_summary),
                    include_links=bool(include_links),
                ),
            ),
            "chrome_open_web_app": ToolSpec(
                name="chrome_open_web_app",
                description="Open a supported web app in the installed Chrome desktop app and verify the visible domain when possible.",
                args_schema=_schema({"app": {"type": "string"}}, ["app"]),
                safety_level="safe",
                handler=lambda app: chrome_open_web_app(str(app)),
                category="browser",
                risk="low",
                requires_explicit_intent=True,
                verification_strategy="Uses the web app catalog, opens a public URL in Chrome, and checks visible browser windows.",
                failure_recovery="If the app is unsupported or Chrome cannot open it, report the limitation clearly.",
            ),
            "chrome_open_web_app_and_verify": ToolSpec(
                name="chrome_open_web_app_and_verify",
                description="Open a supported web app in Chrome and verify target domain when possible.",
                args_schema=_schema({"app": {"type": "string"}}, ["app"]),
                safety_level="safe",
                handler=lambda app: open_web_app_and_verify(str(app)),
                category="browser",
                risk="low",
                requires_explicit_intent=True,
                verification_strategy="Uses app catalog and live/visible browser verification.",
                failure_recovery="If verification fails, report the action result without claiming current page success.",
            ),
            "chrome_search_site": ToolSpec(
                name="chrome_search_site",
                description="Open a supported site's public search URL in Chrome for an explicit query.",
                args_schema=_schema({"site": {"type": "string"}, "query": {"type": "string"}, "play": {"type": "boolean"}}, ["site", "query"]),
                safety_level="safe",
                handler=lambda site, query, play=False: chrome_search_site(str(site), str(query), play=bool(play)),
                category="browser",
                risk="low",
                requires_explicit_intent=True,
                verification_strategy="Builds a cataloged public search URL, opens it in Chrome, and checks visible browser windows.",
                failure_recovery="If the site search is unsupported, use browser_search or explain supported sites.",
            ),
            "chrome_search_site_and_verify": ToolSpec(
                name="chrome_search_site_and_verify",
                description="Search a supported site in Chrome and verify the remembered browser target.",
                args_schema=_schema({"site": {"type": "string"}, "query": {"type": "string"}}, ["site", "query"]),
                safety_level="safe",
                handler=lambda site, query: search_site_and_verify(str(site), str(query)),
                category="browser",
                risk="low",
                requires_explicit_intent=True,
                verification_strategy="Opens cataloged search URL and checks TaskContext target against live browser state.",
                failure_recovery="If the live tab is wrong or stale, offer to reopen the target search.",
            ),
            "chrome_activate_top_youtube_result": ToolSpec(
                name="chrome_activate_top_youtube_result",
                description="Activate the top visible YouTube result using bounded visible keyboard input, then verify watch/player state.",
                args_schema=_schema({"query": {"type": "string"}}, ["query"]),
                safety_level="safe",
                handler=lambda query: activate_top_youtube_result(str(query)),
                category="browser",
                risk="medium",
                requires_explicit_intent=True,
                verification_strategy="Uses bounded visible keyboard input and verifies youtube.com/watch or player evidence.",
                failure_recovery="If activation or verification fails, stop and say the top result could not be safely activated.",
            ),
            "browser_verify_target": ToolSpec(
                name="browser_verify_target",
                description="Verify the current live browser state against Eva's remembered TaskContext target.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=verify_browser_target,
                category="browser",
                risk="low",
                verification_strategy="Compares live browser probe against last intended target, not the active page blindly.",
                failure_recovery="If target mismatches, offer to reopen or switch back to the target page.",
            ),
            "browser_recover_target": ToolSpec(
                name="browser_recover_target",
                description="Reopen the remembered browser target when verification shows the active tab is wrong.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=recover_browser_target,
                category="browser",
                risk="low",
                requires_explicit_intent=True,
                verification_strategy="Uses TaskContext target URL/query only.",
                failure_recovery="Ask the user for the target if TaskContext is missing.",
            ),
            "chatgpt_in_chrome": ToolSpec(
                name="chatgpt_in_chrome",
                description="Open ChatGPT in Chrome and run the visible workflow only when it can be verified safely.",
                args_schema=_schema({"prompt": {"type": "string"}, "confirmed": {"type": "boolean"}}, ["prompt"]),
                safety_level="sensitive",
                handler=lambda prompt, confirmed=False: ask_chatgpt_in_chrome(str(prompt), user_confirmed_private_cloud_share=bool(confirmed)),
                category="browser",
                risk="medium",
                requires_explicit_intent=True,
                verification_strategy="Requires visible ChatGPT page/input/response verification before claiming ChatGPT provenance.",
                failure_recovery="If the workflow is unavailable, open ChatGPT or stop honestly without answering directly.",
            ),
            "chrome_copy_current_url": ToolSpec(
                name="chrome_copy_current_url",
                description="Copy the current visible browser URL to the clipboard after an explicit user command.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=chrome_copy_current_url,
                category="browser",
                risk="low",
                requires_explicit_intent=True,
                verification_strategy="Uses browser current URL discovery and writes only that URL to the clipboard.",
                failure_recovery="If the URL cannot be discovered, ask the user to open the page through Eva or paste the URL.",
            ),
            "chrome_new_tab": ToolSpec(
                name="chrome_new_tab",
                description="Open a new visible Chrome tab using a bounded keyboard shortcut.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=chrome_new_tab,
                category="browser",
                risk="low",
            ),
            "chrome_close_tab": ToolSpec(
                name="chrome_close_tab",
                description="Close the current visible Chrome tab using a bounded keyboard shortcut.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=chrome_close_tab,
                category="browser",
                risk="medium",
                requires_explicit_intent=True,
            ),
            "chrome_reload": ToolSpec(
                name="chrome_reload",
                description="Reload the current visible Chrome tab using a bounded keyboard shortcut.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=chrome_reload,
                category="browser",
                risk="low",
            ),
            "chrome_back": ToolSpec(
                name="chrome_back",
                description="Navigate back in the current visible Chrome tab using a bounded keyboard shortcut.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=chrome_back,
                category="browser",
                risk="low",
            ),
            "chrome_forward": ToolSpec(
                name="chrome_forward",
                description="Navigate forward in the current visible Chrome tab using a bounded keyboard shortcut.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=chrome_forward,
                category="browser",
                risk="low",
            ),
            "chrome_focus_address_bar": ToolSpec(
                name="chrome_focus_address_bar",
                description="Focus Chrome's address bar using a bounded keyboard shortcut.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=chrome_focus_address_bar,
                category="browser",
                risk="low",
            ),
            "browser_open_result_and_verify": ToolSpec(
                name="browser_open_result_and_verify",
                description="Open a safe http/https URL or remembered search result in Chrome and verify the visible domain when possible.",
                args_schema=_schema({"url": {"type": "string"}, "result_index": {"type": "number"}}, []),
                safety_level="safe",
                handler=lambda url="", result_index=0: browser_open_result_and_verify(str(url or ""), int(result_index or 0)),
                category="browser",
                risk="low",
                requires_explicit_intent=True,
                verification_strategy="Normalizes public URLs, opens in Chrome, and verifies visible browser windows.",
                failure_recovery="Refuse private/non-http URLs and ask for a safe public URL if needed.",
            ),
            "media_control": ToolSpec(
                name="media_control",
                description="Send media keys: mute, volume_up, volume_down, play_pause, next, previous.",
                args_schema=_schema({"action": {"type": "string", "enum": sorted(MEDIA_ACTIONS)}}, ["action"]),
                safety_level="safe",
                handler=_media_control,
            ),
            "media_key": ToolSpec(
                name="media_key",
                description="Alias for media_control used by deterministic commands.",
                args_schema=_schema({"action": {"type": "string", "enum": sorted(MEDIA_ACTIONS)}}, ["action"]),
                safety_level="safe",
                handler=_media_control,
                category="media",
                risk="low",
            ),
            "spotify_status": ToolSpec(
                name="spotify_status",
                description="Report whether a visible Spotify desktop window is available without reading account data.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=spotify_status,
                category="media",
                risk="low",
                verification_strategy="Uses Desktop Agent Core window detection/focus for Spotify.",
                failure_recovery="Ask the user to install or manually open Spotify.",
            ),
            "spotify_search_desktop": ToolSpec(
                name="spotify_search_desktop",
                description="Open Spotify and search for a requested song or artist using bounded Spotify URI automation.",
                args_schema=_schema({"query": {"type": "string"}}, ["query"]),
                safety_level="safe",
                handler=lambda query: search_spotify_desktop(str(query)),
                category="media",
                risk="medium",
                requires_explicit_intent=True,
                verification_strategy="Opens/focuses Spotify, opens a spotify:search URI, and reports that exact results cannot be verified in v1.",
                failure_recovery="If Spotify cannot be opened or searched safely, stop and explain the limitation.",
            ),
            "spotify_play_desktop": ToolSpec(
                name="spotify_play_desktop",
                description="Open Spotify, search for a requested song, and attempt first-result playback through bounded visible automation.",
                args_schema=_schema({"query": {"type": "string"}}, ["query"]),
                safety_level="safe",
                handler=lambda query: play_spotify_desktop(str(query)),
                category="media",
                risk="medium",
                requires_explicit_intent=True,
                verification_strategy="Searches via spotify:search URI, focuses Spotify, activates the selected visible result, and checks local now-playing/window metadata when available.",
                failure_recovery="If playback cannot be verified, say Spotify was searched but playback could not be safely verified.",
            ),
            "spotify_now_playing_status": ToolSpec(
                name="spotify_now_playing_status",
                description="Best-effort local Spotify now-playing verification without API, OAuth, web player, cookies, or tokens.",
                args_schema=_schema({"expected_query": {"type": "string"}}, []),
                safety_level="safe",
                handler=lambda expected_query="": spotify_now_playing_status(str(expected_query or "")),
                category="media",
                risk="low",
                verification_strategy="Uses visible Spotify window/title metadata if available and otherwise returns graceful unavailable.",
                failure_recovery="If metadata is unavailable, say exact playback cannot be confirmed.",
            ),
            "spotify_search": ToolSpec(
                name="spotify_search",
                description="Compatibility alias for spotify_search_desktop.",
                args_schema=_schema({"query": {"type": "string"}}, ["query"]),
                safety_level="safe",
                handler=lambda query: search_spotify(str(query)),
                category="media",
                risk="medium",
                requires_explicit_intent=True,
                verification_strategy="Alias for Spotify desktop search.",
                failure_recovery="If Spotify cannot be opened or searched safely, stop and explain the limitation.",
            ),
            "spotify_play_query": ToolSpec(
                name="spotify_play_query",
                description="Compatibility alias for spotify_play_desktop.",
                args_schema=_schema({"query": {"type": "string"}}, ["query"]),
                safety_level="safe",
                handler=lambda query: play_spotify_query(str(query)),
                category="media",
                risk="medium",
                requires_explicit_intent=True,
                verification_strategy="Alias for Spotify desktop playback attempt.",
                failure_recovery="If playback cannot be verified, say Spotify was searched but playback could not be safely verified.",
            ),
            "spotify_pause": ToolSpec(
                name="spotify_pause",
                description="Focus/open Spotify and send the play/pause media key.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=pause_spotify,
                category="media",
                risk="low",
                verification_strategy="Uses the existing allowlisted media key after opening/focusing Spotify.",
                failure_recovery="If Spotify cannot be opened, report that clearly without killing processes.",
            ),
            "spotify_next": ToolSpec(
                name="spotify_next",
                description="Focus/open Spotify and send the next-track media key.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=next_spotify,
                category="media",
                risk="low",
                verification_strategy="Uses the existing allowlisted next media key after opening/focusing Spotify.",
                failure_recovery="If Spotify cannot be opened, report that clearly without killing processes.",
            ),
            "spotify_previous": ToolSpec(
                name="spotify_previous",
                description="Focus/open Spotify and send the previous-track media key twice to request the previous song.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=previous_spotify_track,
                category="media",
                risk="low",
                verification_strategy="Uses the existing allowlisted previous media key twice after opening/focusing Spotify.",
                failure_recovery="If Spotify cannot be opened, report that clearly without killing processes.",
            ),
            "spotify_restart_current": ToolSpec(
                name="spotify_restart_current",
                description="Focus/open Spotify and send the previous media key once to restart the current song.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=restart_current_spotify_track,
                category="media",
                risk="low",
                verification_strategy="Uses the existing allowlisted previous media key once after opening/focusing Spotify.",
                failure_recovery="If Spotify cannot be opened, report that clearly without killing processes.",
            ),
            "lock_laptop": ToolSpec(
                name="lock_laptop",
                description="Lock the laptop immediately. This is allowed without confirmation.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=_lock_laptop,
            ),
            "capture_screen": ToolSpec(
                name="capture_screen",
                description="Capture one on-demand screenshot only when the user explicitly asks Eva to look at, check, analyze, or inspect the screen.",
                args_schema=_schema({}),
                safety_level="sensitive",
                handler=_capture_screen,
            ),
            "analyze_screen": ToolSpec(
                name="analyze_screen",
                description="Capture one on-demand screenshot and analyze it with Gemini Vision only when the user explicitly asks Eva to understand the screen or visible error.",
                args_schema=_schema({"question": {"type": "string"}}, []),
                safety_level="sensitive",
                handler=_analyze_screen,
            ),
            "desktop_observe": ToolSpec(
                name="desktop_observe",
                description="Observe active/open desktop windows. Screen capture is off by default and only allowed with explicit screen intent.",
                args_schema=_schema(
                    {
                        "include_windows": {"type": "boolean"},
                        "include_screen": {"type": "boolean"},
                        "explicit_screen_intent": {"type": "boolean"},
                    },
                    [],
                ),
                safety_level="safe",
                handler=lambda include_windows=True, include_screen=False, explicit_screen_intent=False: desktop_observe(
                    include_windows=bool(include_windows),
                    include_screen=bool(include_screen),
                    explicit_screen_intent=bool(explicit_screen_intent),
                ),
            ),
            "window_list": ToolSpec(
                name="window_list",
                description="List visible open windows with titles and process names.",
                args_schema=_schema({"limit": {"type": "number"}}, []),
                safety_level="safe",
                handler=lambda limit=40: list_windows(limit=int(limit or 40)),
            ),
            "window_active": ToolSpec(
                name="window_active",
                description="Return the currently active foreground window.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=active_window,
            ),
            "window_focus": ToolSpec(
                name="window_focus",
                description="Focus/restore a visible window by title or process query.",
                args_schema=_schema({"query": {"type": "string"}}, ["query"]),
                safety_level="safe",
                handler=lambda query: focus_window_safe(str(query)),
            ),
            "window_close_safe": ToolSpec(
                name="window_close_safe",
                description="Close one matched window only if its process is in the safe close allowlist.",
                args_schema=_schema({"query": {"type": "string"}}, ["query"]),
                safety_level="sensitive",
                handler=lambda query: close_window_safe(str(query)),
            ),
            "window_minimize": ToolSpec(
                name="window_minimize",
                description="Minimize a visible window by title or process query.",
                args_schema=_schema({"query": {"type": "string"}}, ["query"]),
                safety_level="safe",
                handler=lambda query: minimize_window_safe(str(query)),
            ),
            "window_maximize": ToolSpec(
                name="window_maximize",
                description="Maximize a visible window by title or process query.",
                args_schema=_schema({"query": {"type": "string"}}, ["query"]),
                safety_level="safe",
                handler=lambda query: maximize_window_safe(str(query)),
            ),
            "verify_last_action": ToolSpec(
                name="verify_last_action",
                description="Best-effort verification for the last safe desktop action such as opening an app, folder, URL, or focusing a window.",
                args_schema=_schema({"action": {"type": "string"}, "tool": {"type": "string"}, "target": {"type": "string"}}, []),
                safety_level="safe",
                handler=lambda action="", tool="", target="": verify_last_action(action=str(action or ""), tool=str(tool or ""), target=str(target or "")),
            ),
            "guarded_power_action": ToolSpec(
                name="guarded_power_action",
                description="Shutdown, restart, sleep, or sign out. Requires explicit confirmation before execution.",
                args_schema=_schema(
                    {
                        "action": {"type": "string", "enum": sorted(POWER_ACTIONS)},
                        "confirmed": {"type": "boolean"},
                    },
                    ["action", "confirmed"],
                ),
                safety_level="dangerous",
                handler=_guarded_power_action,
                category="system",
                risk="high",
                requires_explicit_intent=True,
                verification_strategy="Requires explicit confirmation before any power action.",
                failure_recovery="Ask for confirmation or decline unsupported power actions.",
            ),
            "workspace_status": ToolSpec(
                name="workspace_status",
                description="Show Eva workspace root, enabled state, scan limits, and safety excludes. Never exposes secrets.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=workspace_status,
            ),
            "workspace_list_files": ToolSpec(
                name="workspace_list_files",
                description="List safe files inside Eva's workspace. Read-only and excludes secrets, runtime data, .git, .venv, and caches.",
                args_schema=_schema({"path": {"type": "string"}, "limit": {"type": "number"}}, []),
                safety_level="safe",
                handler=lambda path="", limit=100: safe_list_files(str(path or ""), limit=int(limit or 100)),
            ),
            "workspace_read_file": ToolSpec(
                name="workspace_read_file",
                description="Read one safe text file by relative path inside Eva's workspace. Refuses .env, secrets, runtime DBs, logs, and path traversal.",
                args_schema=_schema({"path": {"type": "string"}}, ["path"]),
                safety_level="safe",
                handler=lambda path: safe_read_file(str(path)),
            ),
            "workspace_search": ToolSpec(
                name="workspace_search",
                description="Search Eva's workspace filenames and safe text files for a query. Read-only and secret-safe.",
                args_schema=_schema({"query": {"type": "string"}, "limit": {"type": "number"}}, ["query"]),
                safety_level="safe",
                handler=lambda query, limit=10: search_workspace(str(query), limit=int(limit or 10)),
            ),
            "workspace_summarize_file": ToolSpec(
                name="workspace_summarize_file",
                description="Summarize one safe source file in Eva's workspace without exposing secrets.",
                args_schema=_schema({"path": {"type": "string"}}, ["path"]),
                safety_level="safe",
                handler=lambda path: summarize_file(str(path)),
            ),
            "workspace_project_summary": ToolSpec(
                name="workspace_project_summary",
                description="Summarize Eva's major project folders and key modules. Read-only.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=summarize_workspace,
            ),
            "code_status": ToolSpec(
                name="code_status",
                description="Show safe code index status, indexed file count, and last index time. Never exposes secrets.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=code_status,
            ),
            "code_reindex": ToolSpec(
                name="code_reindex",
                description="Regenerate Eva's read-only safe code index. Skips secrets, runtime data, .git, .venv, node_modules, logs, DBs, and huge files.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=build_code_index,
            ),
            "code_search": ToolSpec(
                name="code_search",
                description="Search Eva's safe code index by filenames, symbols, imports, endpoints, tool names, and summaries.",
                args_schema=_schema({"query": {"type": "string"}, "limit": {"type": "number"}}, ["query"]),
                safety_level="safe",
                handler=lambda query, limit=10: search_code(str(query), limit=int(limit or 10)),
            ),
            "code_find_symbol": ToolSpec(
                name="code_find_symbol",
                description="Find a function, class, async function, or registered tool symbol in Eva's safe code index.",
                args_schema=_schema({"symbol": {"type": "string"}}, ["symbol"]),
                safety_level="safe",
                handler=lambda symbol: find_symbol(str(symbol)),
            ),
            "code_project_map": ToolSpec(
                name="code_project_map",
                description="Build a file-grounded map of Eva's backend, frontend, tools, agent, LLM, browser, desktop, research, and verifier modules.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=code_project_map,
            ),
            "code_explain_feature": ToolSpec(
                name="code_explain_feature",
                description="Find and explain where a feature is likely implemented using the safe code index.",
                args_schema=_schema({"feature": {"type": "string"}}, ["feature"]),
                safety_level="safe",
                handler=lambda feature: code_explain_feature(str(feature)),
            ),
            "code_debug_traceback": ToolSpec(
                name="code_debug_traceback",
                description="Parse a pasted traceback/error, inspect safe referenced code snippets, and suggest likely files/tests. Read-only.",
                args_schema=_schema({"traceback": {"type": "string"}}, ["traceback"]),
                safety_level="safe",
                handler=lambda traceback: debug_traceback(str(traceback)),
            ),
            "code_plan_change": ToolSpec(
                name="code_plan_change",
                description="Create a read-only patch plan for a requested code change: likely files, steps, tests, risks, and approval note.",
                args_schema=_schema({"goal": {"type": "string"}}, ["goal"]),
                safety_level="safe",
                handler=lambda goal: plan_code_change(str(goal)),
            ),
            "research_start_topic": ToolSpec(
                name="research_start_topic",
                description="Create or update a local SQLite research topic. Does not use cloud APIs.",
                args_schema=_schema({"topic": {"type": "string"}, "description": {"type": "string"}}, ["topic"]),
                safety_level="safe",
                handler=lambda topic, description="": research_start_topic(str(topic), str(description or "")),
            ),
            "research_web": ToolSpec(
                name="research_web",
                description="Search fresh web sources for a topic with Tavily when configured, save normalized results to local research SQLite, and return saved sources.",
                args_schema=_schema({"topic": {"type": "string"}, "query": {"type": "string"}, "max_results": {"type": "number"}}, ["topic", "query"]),
                safety_level="safe",
                handler=lambda topic, query, max_results=5: research_web(str(topic), str(query), max_results=int(max_results or 5)),
            ),
            "research_save_note": ToolSpec(
                name="research_save_note",
                description="Save a local research note for a topic in SQLite. Never stores secrets intentionally.",
                args_schema=_schema({"topic": {"type": "string"}, "note": {"type": "string"}, "tags": {"type": "string"}}, ["topic", "note"]),
                safety_level="safe",
                handler=lambda topic, note, tags="": research_save_note(str(topic), str(note), str(tags or "")),
            ),
            "research_recall": ToolSpec(
                name="research_recall",
                description="Recall saved local research notes and sources for a topic using keyword retrieval. No cloud API required.",
                args_schema=_schema({"topic": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "number"}}, ["topic"]),
                safety_level="safe",
                handler=lambda topic, query="", limit=5: research_recall(str(topic), str(query or ""), limit=int(limit or 5)),
            ),
            "research_summary": ToolSpec(
                name="research_summary",
                description="Summarize saved local research knowledge for a topic.",
                args_schema=_schema({"topic": {"type": "string"}}, ["topic"]),
                safety_level="safe",
                handler=lambda topic: research_summary(str(topic)),
            ),
            "research_status": ToolSpec(
                name="research_status",
                description="Show local research database counts and retrieval mode. Never exposes keys.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=research_status,
            ),
            "system_power": ToolSpec(
                name="system_power",
                description="Alias for lock/guarded power actions used by deterministic commands.",
                args_schema=_schema({"action": {"type": "string"}, "confirmed": {"type": "boolean"}}, ["action"]),
                safety_level="dangerous",
                handler=system_power,
                category="system",
                risk="high",
                requires_explicit_intent=True,
                verification_strategy="Requires confirmation for shutdown/restart/sleep/sign out.",
                failure_recovery="Ask for explicit confirmation before guarded power actions.",
            ),
        }

    def list_tools(self) -> list[dict[str, Any]]:
        return [self._public_spec(spec) for spec in self._tools.values()]

    def planner_specs(self) -> list[dict[str, Any]]:
        visible = [
            "status",
            "open_app",
            "open_folder",
            "open_url",
            "web_search",
            "browser_status",
            "browser_open_url",
            "browser_search",
            "browser_current_page",
            "browser_summarize_page",
            "browser_extract_links",
            "browser_save_page_to_research",
            "browser_observe",
            "chrome_open_web_app",
            "chrome_open_web_app_and_verify",
            "chrome_search_site",
            "chrome_search_site_and_verify",
            "chrome_activate_top_youtube_result",
            "chrome_copy_current_url",
            "chrome_new_tab",
            "chrome_close_tab",
            "chrome_reload",
            "chrome_back",
            "chrome_forward",
            "chrome_focus_address_bar",
            "browser_open_result_and_verify",
            "browser_verify_target",
            "browser_recover_target",
            "chatgpt_in_chrome",
            "media_control",
            "spotify_status",
            "spotify_search_desktop",
            "spotify_play_desktop",
            "spotify_search",
            "spotify_play_query",
            "spotify_pause",
            "spotify_next",
            "spotify_previous",
            "spotify_restart_current",
            "spotify_now_playing_status",
            "lock_laptop",
            "capture_screen",
            "analyze_screen",
            "desktop_observe",
            "window_list",
            "window_active",
            "window_focus",
            "window_close_safe",
            "window_minimize",
            "window_maximize",
            "verify_last_action",
            "workspace_status",
            "workspace_list_files",
            "workspace_read_file",
            "workspace_search",
            "workspace_summarize_file",
            "workspace_project_summary",
            "code_status",
            "code_reindex",
            "code_search",
            "code_find_symbol",
            "code_project_map",
            "code_explain_feature",
            "code_debug_traceback",
            "code_plan_change",
            "research_start_topic",
            "research_web",
            "research_save_note",
            "research_recall",
            "research_summary",
            "research_status",
            "guarded_power_action",
        ]
        return [self._public_spec(self._tools[name]) for name in visible]

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def run(self, name: str, **kwargs: Any) -> Any:
        spec = self._tools.get(name)
        if spec is None:
            raise KeyError(f"Unknown tool: {name}")

        # The `confirmed`/`_approved` flags carry no authority. Approval only
        # ever comes from a ledger-confirmed pending action via run_approved().
        # Strip them so a planner LLM or HTTP client cannot self-approve.
        call_args = {key: value for key, value in kwargs.items() if key not in {"confirmed", "_approved"}}

        decision = tool_gate.classify_tool_call(spec)
        if decision == "hard_block":
            return {
                "ok": False,
                "hard_blocked": True,
                "message": f"{name} is blocked by policy and cannot be overridden.",
            }
        if decision in {"override", "confirm"}:
            return self._create_gated_pending(name, spec, decision, call_args)

        return self._invoke(spec, call_args)

    def run_approved(self, pending_id: str) -> dict[str, Any]:
        from ..permissions.ledger import get_pending_action

        pending_id = str(pending_id or "").strip()
        action = get_pending_action(pending_id)
        if action is None:
            return {"ok": False, "error": f"No pending action `{pending_id}`."}
        if action.status not in {"confirmed", "confirmed_but_executor_unavailable"}:
            return {"ok": False, "error": f"Pending action `{pending_id}` is {action.status}, not confirmed."}

        stored = tool_gate.get_pending_call(pending_id)
        if stored is None:
            return {"ok": False, "error": f"No in-memory call registered for `{pending_id}` (it may have already run)."}

        spec = self._tools.get(stored["tool"])
        if spec is None:
            return {"ok": False, "error": f"Unknown tool for pending action: {stored['tool']}."}

        tool_gate.pop_pending_call(pending_id)
        return self._invoke(spec, dict(stored["args"]))

    def _invoke(self, spec: ToolSpec, args: dict[str, Any]) -> Any:
        result = spec.handler(**args)
        return asdict(result) if hasattr(result, "__dataclass_fields__") else result

    def _create_gated_pending(self, name: str, spec: ToolSpec, decision: str, args: dict[str, Any]) -> dict[str, Any]:
        from ..permissions.ledger import create_pending_action
        from ..permissions.pending_actions import EvaPendingAction

        requires_override = decision == "override"
        risk_level = "high" if spec.safety_level == "dangerous" else "medium"
        target = str(args.get("path") or args.get("target") or args.get("dst") or args.get("recipient") or "")
        action = EvaPendingAction.new(
            action_type=name,
            risk_level=risk_level,
            risk_category=spec.action_type,
            summary=f"{name}: {spec.description}",
            target=target or None,
            payload_summary=", ".join(f"{key}={value}" for key, value in args.items()) or None,
            requires_confirmation=not requires_override,
            requires_override=requires_override,
            source="tool_gate",
            executor_available=True,
            executor_name=name,
            safety_reason=f"{name} is classified as {decision}-class by the tool gate.",
            redacted_payload=args,
        )
        create_pending_action(action)
        tool_gate.register_pending_call(action.id, name, args)
        phrase = f"confirm override {action.id}" if requires_override else f"confirm {action.id}"
        return {
            "ok": False,
            "requires_confirmation": True,
            "pending_id": action.id,
            "risk_class": decision,
            "message": f"{name} needs approval before it runs. Say `{phrase}` to approve this exact action.",
        }

    def _public_spec(self, spec: ToolSpec) -> dict[str, Any]:
        risk = spec.risk or ("high" if spec.safety_level == "dangerous" else "medium" if spec.safety_level == "sensitive" else "low")
        return {
            "name": spec.name,
            "description": spec.description,
            "args_schema": spec.args_schema,
            "safety_level": spec.safety_level,
            "safe_by_default": spec.safe_by_default,
            "category": spec.category,
            "risk": risk,
            "requires_explicit_intent": spec.requires_explicit_intent,
            "verification_strategy": spec.verification_strategy,
            "failure_recovery": spec.failure_recovery,
            "action_type": spec.action_type,
            "risk_categories": list(spec.risk_categories),
            "requires_confirmation": spec.requires_confirmation,
            "supports_rollback": spec.supports_rollback,
            "verification_method": spec.verification_method,
        }

