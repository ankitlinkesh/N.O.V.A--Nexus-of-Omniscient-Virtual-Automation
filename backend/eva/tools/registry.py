from __future__ import annotations

import inspect
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from ..screen.capture import capture_primary_screen_jpeg
from ..screen.screen_tools import screen_click, screen_hotkey, screen_observe, screen_press, screen_scroll, screen_submit_form, screen_type_text, screen_wait
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
from .app_control_tools import app_focus, browser_open_url_tool, browser_search_tool
from .desktop import close_app, media_key, open_app, open_folder, open_url, system_power, system_status, web_search
from .message_tools import message_confirm_send, message_prepare, message_send_via_ui
from .safe_file_tools import file_copy, file_delete, file_list_dir, file_move, file_write_text
from ..browser_automation import playwright_driver
from ..security import tool_gate

SafetyLevel = Literal["safe", "sensitive", "dangerous"]

# Shared cache of MCP-derived tool specs, populated (only when the MCP
# subsystem is explicitly enabled and configured) via register_mcp_tool_specs()
# below. ToolRegistry() is constructed in multiple places (routes.py,
# confirmation.py's run_approved, runner.py) so this module-level cache is how
# MCP tools become visible to every instance. Empty by default => no-op.
_MCP_TOOL_SPECS: dict[str, "ToolSpec"] = {}


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
    # Argument names whose VALUES must never be written to the pending-action
    # ledger or any other durable record -- masked to "[HIDDEN]" in the
    # payload summary / redacted_payload while the real values still reach
    # execution (see _create_gated_pending). Empty by default: no behavior
    # change for tools that don't declare any.
    sensitive_args: tuple[str, ...] = ()
    # Phase 65: argument names that are pure CONTENT -- the tool stores,
    # displays, or logs the value but never dereferences it (never opens it,
    # resolves it, or uses it to select a target). Phase 55's risk escalation
    # (see permissions/risk_signals.py) skips these keys when scanning for a
    # sensitive target, so a message body that happens to mention a system
    # path (e.g. "I saved it under C:/Windows/System32/...") does not get
    # scanned as if the path were the thing being acted on. Declare an
    # argument here ONLY after reading the handler's implementation and
    # confirming it never dereferences the value -- an argument's NAME is not
    # proof (see message_tools.py::message_prepare vs. debugger.py's
    # `traceback`, which parses and reads file paths out of the text despite
    # "looking like" free-form content). Empty by default; this can only
    # REDUCE friction, so under-declaring is always the safe direction.
    content_args: tuple[str, ...] = ()

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

# Tools that perform a UI / navigation / media action, not a read. They were
# historically labeled SAFE_LOCAL_READ; the honest action_type is SAFE_LOCAL_UI.
# Both are allow-class in the gate, so this changes labels, not gate behavior.
_UI_ACTION_TOOLS = frozenset({
    "open_app", "close_app", "open_folder", "open_url",
    "browser_open_url", "browser_save_page_to_research", "browser_open_result_and_verify",
    "chrome_open_web_app", "chrome_open_web_app_and_verify", "chrome_search_site",
    "chrome_search_site_and_verify", "chrome_activate_top_youtube_result", "chrome_copy_current_url",
    "chrome_new_tab", "chrome_close_tab", "chrome_reload", "chrome_back", "chrome_forward",
    "chrome_focus_address_bar", "media_control", "media_key",
    "spotify_play_desktop", "spotify_play_query", "spotify_pause", "spotify_next",
    "spotify_previous", "spotify_search", "spotify_search_desktop", "spotify_restart_current",
    "window_focus", "window_close_safe", "window_minimize", "window_maximize", "lock_laptop",
})
# Power tools whose honest action_type is POWER_ACTION. They stay override-class
# in the gate via safety_level="dangerous" (override is checked before confirm).
_POWER_TOOLS = frozenset({"system_power", "guarded_power_action"})


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


def _web_target(
    target: dict[str, Any] | None,
    selector: str | None,
    role: str | None,
    name: str | None,
    text: str | None,
) -> dict[str, Any]:
    """Build a Playwright locator target dict from an explicit `target` object
    or from individual selector/role/name/text locator hints."""
    if isinstance(target, dict) and target:
        return target
    built: dict[str, Any] = {}
    if selector:
        built["selector"] = selector
    if role:
        built["role"] = role
    if name:
        built["name"] = name
    if text:
        built["text"] = text
    return built


def _status() -> dict[str, Any]:
    return asdict(system_status())


def _run_bounded_command(command: str, args: list[str] | tuple[str, ...] | None = None, timeout: int | None = None) -> dict[str, Any]:
    """Phase 74. All policy lives in bounded_runner.validate, which is pure and
    exhaustively tested; this is only the registry seam."""
    from ..shell.bounded_runner import run_bounded

    result = run_bounded(command, tuple(args or ()), timeout=timeout)
    return {
        "ok": result.ok,
        "refused": result.refused,
        "command": result.command,
        "args": list(result.args),
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "truncated": result.truncated,
        "timed_out": result.timed_out,
        "error": result.error,
        "untrusted": True,
        "text": result.as_text(),
    }


def _media_control(action: str) -> str:
    normalized = action.strip().lower().replace(" ", "_")
    if normalized not in MEDIA_ACTIONS:
        raise ValueError(f"Unsupported media action: {action}")
    return media_key(normalized)


def _lock_laptop() -> str:
    return system_power("lock")


def _handler_accepts_confirmed(handler: Callable[..., Any]) -> bool:
    """True if `handler` declares a `confirmed` parameter (directly or via
    **kwargs). Used only by run_approved to re-inject the ledger-confirmed
    flag; a handler that does not accept it (e.g. the file lambdas that drop
    it) is left untouched so we never raise TypeError."""
    try:
        params = inspect.signature(handler).parameters
    except (TypeError, ValueError):
        return False
    if "confirmed" in params:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


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
        "ok": True,
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
            # Phase 74. Deliberately NOT SHELL_ACTION: that action type is
            # hard-blocked in both gates and stays that way. This runs a fixed
            # allowlisted executable with shell=False and a read-only
            # subcommand list, so it is not arbitrary shell execution. It is
            # classified SYSTEM_CHANGE (override-class) anyway -- the heaviest
            # non-blocked tier -- because a first release of process execution
            # should cost more than it probably needs to, not less.
            "shell.run_bounded": ToolSpec(
                name="shell.run_bounded",
                description="Run one allowlisted read-only command (git status/log/diff, python --version, pip list) with no shell.",
                args_schema=_schema({"command": "str", "args": "list[str]"}),
                safety_level="dangerous",
                handler=_run_bounded_command,
                action_type="SYSTEM_CHANGE",
                risk_categories=("SYSTEM_CHANGE",),
                category="system",
            ),
            "open_app": ToolSpec(
                name="open_app",
                description="Open a known desktop app by common name. Supported examples: chrome, spotify, vscode, codex, settings, notepad.",
                args_schema=_schema({"app": {"type": "string", "enum": sorted(KNOWN_APPS)}}, ["app"]),
                safety_level="safe",
                handler=lambda app=None, app_name=None: open_app(str(app or app_name or "")),
                # Phase 70: inherited from the deleted `app.open` (Phase 64's
                # app_window_open postcondition), which duplicated this tool but
                # had no caller (Phase 66). open_app is what the console and
                # planner actually route to, so it must carry the real
                # independent postcondition rather than defaulting to
                # command_result_success (a bare self-report). "opened" means a
                # window now exists, NOT that it took the foreground -- see
                # app.focus's app_window_active below for the contrasting case,
                # and tools/postconditions.py for why the two must stay separate
                # methods. The `app` argument name matches what
                # derive_postcondition's app_window_open branch extracts
                # (_first(args, "app", "query", "target")), confirmed by reading
                # both sides rather than assumed.
                verification_method="app_window_open",
            ),
            "close_app": ToolSpec(
                name="close_app",
                description="Close a configurable safe allowlist of common apps. Never kills arbitrary or system processes.",
                args_schema=_schema({"app": {"type": "string"}, "app_name": {"type": "string"}}, []),
                safety_level="sensitive",
                # Phase 82: close_app was allow-class (auto-run, zero friction)
                # even though closing an app can DISCARD UNSAVED WORK -- unlike
                # open_app, which is harmless. `safety_level="sensitive"` alone
                # did nothing at the gate (only "dangerous"/"safe" are read), and
                # the SYSTEM_CHANGE action_type of the deleted `app.close_request`
                # was never carried over (see the note near message.prepare). It
                # now asks first, matching screen.submit_form (also SAFE_LOCAL_UI
                # but confirm-class because it can commit/lose data). A delegated
                # desktop sub-task escalates this one step further to override
                # (role_policy ORANGE), which is why it is confirm and not
                # override on the direct path -- proportionate to closing an
                # allowlisted user app rather than a destructive system change.
                requires_confirmation=True,
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
                description="Click a visible UI element during an active task. Give a text `label` (e.g. 'Submit') to locate it via GUI grounding, or a verified `target`. Raw coordinates are refused.",
                args_schema=_schema(
                    {
                        "target": {"type": "object"},
                        "label": {"type": "string"},
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "reason": {"type": "string"},
                        "required_confidence": {"type": "number"},
                    },
                    ["reason"],
                ),
                safety_level="safe",
                handler=lambda reason, target=None, label=None, x=None, y=None, required_confidence=0.75: screen_click(
                    x=int(x) if x is not None else None,
                    y=int(y) if y is not None else None,
                    reason=str(reason),
                    target=target if isinstance(target, dict) else None,
                    required_confidence=float(required_confidence or 0.75),
                    label=str(label) if label else None,
                ),
                category="screen",
                risk="low",
                action_type="SAFE_LOCAL_UI",
                risk_categories=("SAFE_LOCAL_UI",),
                verification_method="screen_state_changed",
                # Phase 65: `reason` is content, not a target -- screen_tools.py
                # ::screen_click only checks it is non-empty (reason_required),
                # then logs it; `label` is deliberately NOT declared here, since
                # it feeds grounding.resolve() as an actual target selector.
                content_args=("reason",),
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
                sensitive_args=("text",),
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
                sensitive_args=("keys",),
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
                # Phase 65: `reason` is content, not a target. screen_controller.py
                # ::scroll only interpolates it into a log/summary string
                # (f"Scrolled for reason: {reason}."); it is never opened,
                # resolved, or used to pick a target.
                content_args=("reason",),
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
                # Phase 65: same proof as screen.scroll above -- screen_controller.py
                # ::wait only interpolates `reason` into a summary string, never
                # dereferences it.
                content_args=("reason",),
            ),
            "screen.submit_form": ToolSpec(
                name="screen.submit_form",
                description="Fill and submit a form staged from the trusted console. Takes only a console-issued spec id; it carries no field values and is inert without one.",
                args_schema=_schema({"spec_id": {"type": "string"}, "reason": {"type": "string"}}, ["spec_id", "reason"]),
                safety_level="sensitive",
                handler=lambda spec_id, reason: screen_submit_form(str(spec_id), str(reason)),
                category="screen",
                risk="medium",
                action_type="SAFE_LOCAL_UI",
                risk_categories=("SAFE_LOCAL_UI",),
                requires_confirmation=True,
                verification_method="screen_state_changed",
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
                # For focus specifically, "is this the foreground window" IS
                # the real postcondition -- unlike open_app's app_window_open
                # above (opened is not focused; see that ToolSpec's comment).
                verification_method="app_window_active",
            ),
            # Phase 70: `app.open` and `app.close_request` were deleted here.
            # Phase 66 found both registered, gated, and callable via
            # /api/tools but reachable from nowhere in the shipped product --
            # `open_app` (above) and `close_app` (eva/tools/app_control_tools.py
            # equivalent, registered near the top of this file) were what the
            # console and planner actually routed to. `app.open`'s only extra
            # value (a real app_window_open postcondition, Phase 64) was moved
            # onto `open_app` before deletion so verification did not regress
            # on the routed path. `app.close_request`'s SYSTEM_CHANGE
            # action_type was NOT carried over to `close_app` (which stays the
            # less-gated SAFE_LOCAL_UI) -- that asymmetry is a real, separate
            # risk-classification question this phase deliberately left alone.
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
                # Phase 65: `message` is the draft BODY -- pure content.
                # message_tools.py::message_prepare stores it into the _DRAFTS
                # dict and returns it; it is never opened, resolved, or used to
                # select a target. This is the case that motivated the phase: a
                # draft whose text merely MENTIONED a system path escalated
                # allow -> override, the heaviest tier, for writing a sentence.
                # `recipient` is deliberately NOT declared -- it is the key the
                # draft is filed under, i.e. an actual target.
                content_args=("message",),
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
            "web.open_url": ToolSpec(
                name="web.open_url",
                description="Open a URL in the Playwright-controlled browser session for real DOM automation. Disabled unless EVA_V2_PLAYWRIGHT_ENABLED=true.",
                args_schema=_schema({"url": {"type": "string"}}, ["url"]),
                safety_level="safe",
                handler=lambda url: playwright_driver.open_url(str(url)),
                category="web",
                risk="low",
                action_type="NETWORK_ACTION",
                risk_categories=("NETWORK_ACTION",),
            ),
            "web.snapshot": ToolSpec(
                name="web.snapshot",
                description="Get a text snapshot (URL, title, visible text) of the current Playwright page. Disabled unless EVA_V2_PLAYWRIGHT_ENABLED=true.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=playwright_driver.get_page_snapshot,
                category="web",
                risk="low",
                action_type="NETWORK_ACTION",
                risk_categories=("NETWORK_ACTION",),
            ),
            "web.locate": ToolSpec(
                name="web.locate",
                description="Locate an element on the current Playwright page by role, name, or text without interacting with it. Disabled unless EVA_V2_PLAYWRIGHT_ENABLED=true.",
                args_schema=_schema({"role": {"type": "string"}, "name": {"type": "string"}, "text": {"type": "string"}}, []),
                safety_level="safe",
                handler=lambda role=None, name=None, text=None: playwright_driver.locate_element(role=role, name=name, text=text),
                category="web",
                risk="low",
                action_type="NETWORK_ACTION",
                risk_categories=("NETWORK_ACTION",),
            ),
            "web.verify": ToolSpec(
                name="web.verify",
                description="Verify the current Playwright page against an expected URL, title, or visible text. Disabled unless EVA_V2_PLAYWRIGHT_ENABLED=true.",
                args_schema=_schema(
                    {
                        "expected_url": {"type": "string"},
                        "expected_title": {"type": "string"},
                        "expected_text": {"type": "string"},
                    },
                    [],
                ),
                safety_level="safe",
                handler=lambda expected_url=None, expected_title=None, expected_text=None: playwright_driver.verify_page(
                    expected_url=expected_url, expected_title=expected_title, expected_text=expected_text
                ),
                category="web",
                risk="low",
                action_type="NETWORK_ACTION",
                risk_categories=("NETWORK_ACTION",),
            ),
            "web.click": ToolSpec(
                name="web.click",
                description="Click an element in the Playwright-controlled browser via real DOM automation. Can submit forms or navigate, so it requires confirmation. Disabled unless EVA_V2_PLAYWRIGHT_ENABLED=true.",
                args_schema=_schema(
                    {
                        "target": {"type": "object"},
                        "selector": {"type": "string"},
                        "role": {"type": "string"},
                        "name": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    [],
                ),
                safety_level="sensitive",
                handler=lambda target=None, selector=None, role=None, name=None, text=None: playwright_driver.click_element(
                    _web_target(target, selector, role, name, text)
                ),
                category="web",
                risk="medium",
                action_type="EXTERNAL_POST",
                risk_categories=("EXTERNAL_POST",),
                requires_confirmation=True,
            ),
            "web.type": ToolSpec(
                name="web.type",
                description="Type text into an element in the Playwright-controlled browser via real DOM automation. Can submit data, so it requires confirmation. `text_value` is the text typed into the page; selector/role/name/text are locator hints. Disabled unless EVA_V2_PLAYWRIGHT_ENABLED=true.",
                args_schema=_schema(
                    {
                        "target": {"type": "object"},
                        "selector": {"type": "string"},
                        "role": {"type": "string"},
                        "name": {"type": "string"},
                        "text_value": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    ["text_value"],
                ),
                safety_level="sensitive",
                handler=lambda text_value, target=None, selector=None, role=None, name=None, text=None: playwright_driver.type_text(
                    _web_target(target, selector, role, name, text), str(text_value)
                ),
                category="web",
                risk="medium",
                action_type="EXTERNAL_POST",
                risk_categories=("EXTERNAL_POST",),
                requires_confirmation=True,
            ),
            "web.close": ToolSpec(
                name="web.close",
                description="Close the Playwright browser session if one is open. Disabled unless EVA_V2_PLAYWRIGHT_ENABLED=true.",
                args_schema=_schema({}),
                safety_level="safe",
                handler=playwright_driver.close_browser,
                category="web",
                risk="low",
                action_type="NETWORK_ACTION",
                risk_categories=("NETWORK_ACTION",),
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
            # Grabbing the screen is a PRIVACY_SCREEN_READ, exactly like
            # screen.observe. These two used to default to SAFE_LOCAL_READ, which
            # made them allow-class: they captured the whole screen to disk with
            # no confirmation, AND they were planner-reachable while the properly
            # gated screen.observe was not — the gate was inverted. Worse, the
            # Phase 40 injection defense only escalates *privileged* tools, so an
            # allow-class screen grab was invisible to it: injected web content
            # could steer the planner into screenshotting the user. Classified
            # honestly, they are now override-class and covered by that defense.
            "capture_screen": ToolSpec(
                name="capture_screen",
                description="Capture one on-demand screenshot only when the user explicitly asks Eva to look at, check, analyze, or inspect the screen.",
                args_schema=_schema({}),
                safety_level="sensitive",
                handler=_capture_screen,
                action_type="PRIVACY_SCREEN_READ",
                risk_categories=("PRIVACY_SCREEN_READ",),
                requires_confirmation=True,
            ),
            "analyze_screen": ToolSpec(
                name="analyze_screen",
                description="Capture one on-demand screenshot and analyze it with Gemini Vision only when the user explicitly asks Eva to understand the screen or visible error.",
                args_schema=_schema({"question": {"type": "string"}}, []),
                safety_level="sensitive",
                handler=_analyze_screen,
                action_type="PRIVACY_SCREEN_READ",
                risk_categories=("PRIVACY_SCREEN_READ",),
                requires_confirmation=True,
            ),
            # METADATA ONLY — this tool must never grab pixels. It used to accept
            # include_screen + explicit_screen_intent and capture the screen when
            # both were true. Because the gate classifies a call by TOOL, not by
            # args, that pixel path rode through as allow-class ("safe") with no
            # confirmation — and the unlocking flag, explicit_screen_intent, was
            # supplied by the CALLER, i.e. the LLM authorized its own screen
            # capture. That is the same self-approval bug the `confirmed` argument
            # once had. The screen arguments are gone and capture is hard-wired
            # off here: pixels are only reachable through the override-class
            # capture_screen / analyze_screen / screen.observe, and window
            # metadata has its own proper home in eva.perception.
            "desktop_observe": ToolSpec(
                name="desktop_observe",
                description="Observe active/open desktop windows (window metadata only, never a screenshot). Use capture_screen or analyze_screen to look at the screen; those require confirmation.",
                args_schema=_schema({"include_windows": {"type": "boolean"}}, []),
                safety_level="safe",
                handler=lambda include_windows=True: desktop_observe(
                    include_windows=bool(include_windows),
                    include_screen=False,
                    explicit_screen_intent=False,
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
                # Phase 65: `note` and `tags` are content -- research/store.py
                # ::save_note passes both through _clean_text() straight into a
                # SQLite INSERT. Neither is ever dereferenced. `topic` is NOT
                # declared: it goes to get_or_create_topic() as a lookup key,
                # which is target-shaped.
                content_args=("note", "tags"),
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
        self._normalize_action_types()
        # Merge in any MCP-derived tool specs registered via
        # register_mcp_tool_specs(). Empty by default, so this is a no-op
        # unless the MCP subsystem has been explicitly enabled/configured.
        self._tools.update(_MCP_TOOL_SPECS)

    def _normalize_action_types(self) -> None:
        """Correct action_type metadata so it honestly reflects what each tool
        does. Gate class is preserved: SAFE_LOCAL_UI and NETWORK_ACTION are
        allow-class like the old SAFE_LOCAL_READ, and POWER_ACTION tools stay
        override-class via their dangerous safety_level.

        Phase 51 extends this to network and local-write tools. SAFE_LOCAL_READ
        is the *default*, so anything that forgot to declare an action_type
        inherited it — which meant tools that hit the network or wrote local
        state were describing themselves as safe local reads. Relabelling them
        does not change what the gate does; it stops the metadata lying, and it
        lets the Phase 51 audit tell a reviewed auto-allow from a forgotten one.
        """
        from ..security.action_audit import LOCAL_WRITE_TOOLS, NETWORK_TOOLS

        for name, spec in list(self._tools.items()):
            if spec.action_type != "SAFE_LOCAL_READ":
                continue
            if name in _UI_ACTION_TOOLS:
                self._tools[name] = replace(spec, action_type="SAFE_LOCAL_UI", risk_categories=("SAFE_LOCAL_UI",))
            elif name in _POWER_TOOLS:
                self._tools[name] = replace(spec, action_type="POWER_ACTION", risk_categories=("POWER_ACTION",))
            elif name in NETWORK_TOOLS:
                self._tools[name] = replace(spec, action_type="NETWORK_ACTION", risk_categories=("NETWORK_ACTION",))
            elif name in LOCAL_WRITE_TOOLS:
                self._tools[name] = replace(spec, action_type="SAFE_LOCAL_UI", risk_categories=("SAFE_LOCAL_UI",))

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
        specs = [self._public_spec(self._tools[name]) for name in visible if name in self._tools]

        # Browser DOM tools are planner-reachable only when Playwright is enabled
        # (they exist in the registry always, but are inert unless the flag is on).
        from ..runtime.feature_flags import get_v2_feature_flags
        if get_v2_feature_flags().playwright_enabled:
            specs.extend(self._public_spec(self._tools[name]) for name in sorted(self._tools) if name.startswith("web."))

        # MCP tools are planner-reachable whenever the MCP subsystem has loaded
        # them (their specs are only present in self._tools when enabled+configured).
        specs.extend(self._public_spec(self._tools[name]) for name in sorted(self._tools) if name.startswith("mcp."))

        return specs

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def run(self, name: str, /, **kwargs: Any) -> Any:
        # `name` is positional-only so a tool argument literally called "name"
        # (e.g. the web.* locator hint) doesn't collide with the tool-name param.
        spec = self._tools.get(name)
        if spec is None:
            raise KeyError(f"Unknown tool: {name}")

        # The `confirmed`/`_approved` flags carry no authority. Approval only
        # ever comes from a ledger-confirmed pending action via run_approved().
        # Strip them so a planner LLM or HTTP client cannot self-approve.
        # `content_args` is stripped for the identical reason (Phase 65): it
        # is a friction-REDUCING signal, so it must come only from the
        # ToolSpec declared in source, never from a caller-supplied argument
        # -- otherwise it becomes a self-authorization channel exactly like
        # `confirmed`/`_approved`. See assess_friction() below, which is
        # always passed spec.content_args, never anything from kwargs.
        # `role`/`_role`/`agent_role` are stripped for the same reason: the
        # active role CONSTRAINS what may be called, so a caller that could
        # name its own role would simply claim whichever role unlocks the tool
        # it wants. The role is ambient, set by the delegation boundary in
        # source (agents/role_context.role_scope), never taken from arguments.
        from ..agents.role_context import ROLE_KWARG_NAMES, active_roles

        call_args = {
            key: value
            for key, value in kwargs.items()
            if key not in ({"confirmed", "_approved", "content_args"} | ROLE_KWARG_NAMES)
        }

        # Phase 72 role containment. Only applies INSIDE a delegated sub-task;
        # with no active role this block is a single None check and ordinary
        # console/planner behavior is unchanged.
        # Authorization reads the WHOLE stack, never just the innermost role:
        # a nested scope may only subtract capability, so a research sub-task
        # that opens a `desktop` scope does not thereby gain screen access.
        roles = active_roles()
        if roles:
            from ..agents.role_policy import RoleTier, effective_tier
            from ..observability.context import trace_gate_decision

            role = roles[-1]
            role_tier = effective_tier(roles, name)
            if role_tier is RoleTier.RED:
                # Name the role that actually denied it, which under nesting is
                # not necessarily the innermost one -- an outer role holding the
                # line is the interesting fact, not the one that asked.
                from ..agents.role_policy import tier_for

                denying = next((r for r in roles if tier_for(r, name) is RoleTier.RED), role)
                trace_gate_decision(name, "role_denied", spec)
                # Surface the attempt to whoever started the sub-task. A refusal
                # that dies inside the sub-task wastes the signal.
                from ..agents.role_context import record_denial

                record_denial(denying, name)
                # Deliberately reports the ROLE and the TOOL only. The arguments
                # are not echoed: a refusal triggered by injected content must
                # not become a channel for relaying that content to the user
                # (the Phase 68 lesson behind confirmation.py's explicit key
                # list, where a result can carry page text or a decrypted value).
                return {
                    "ok": False,
                    "role_denied": True,
                    "role": denying,
                    "role_stack": list(roles),
                    "tool": name,
                    "injection_signal": True,
                    "message": (
                        f"Refused: the `{denying}` sub-task may not call `{name}`. "
                        f"This restriction is fixed in source and cannot be granted at runtime. "
                        f"If you did not ask for this, treat it as a signal — content this sub-task "
                        f"read may have tried to make it act. Run `{name}` yourself from the console "
                        f"if you intended it."
                    ),
                }
        else:
            role_tier = None

        decision = tool_gate.classify_tool_call(spec)
        # Flight recorder: record the gate's classification. Inert (no-op, no
        # file write) unless EVA_TRACING_ENABLED and an active trace exist; it
        # never raises and never influences the gate's control flow below.
        from ..observability.context import trace_gate_decision

        trace_gate_decision(name, decision, spec)

        # Phase 55 argument-aware risk escalation: the gate classifies per-TOOL,
        # blind to WHERE the action points. Look at the actual arguments and raise
        # friction when a target is sensitive (e.g. listing ~/.ssh, writing into a
        # system directory). This can ONLY ever escalate — allow->confirm->override,
        # never the reverse — so it is unconditional and fails safe. It runs before
        # the Phase 42 de-escalation below and strictly dominates it: an action the
        # risk layer raises is never then trust-auto-allowed.
        from ..permissions.risk_signals import assess_friction

        friction = assess_friction(
            base_decision=decision,
            action_type=str(getattr(spec, "action_type", "") or ""),
            args=call_args,
            content_args=tuple(getattr(spec, "content_args", ()) or ()),
        )
        if friction.escalated:
            decision = friction.decision
            trace_gate_decision(name, "risk_escalated", spec)

        # Phase 42 calibrated autonomy: a confirm-class action that the user has
        # approved enough times before may auto-allow — but ONLY when trust
        # policies are explicitly enabled, and NEVER for override/hard_block
        # (those cannot be de-escalated here). Guarded by the flag so the default
        # path is byte-identical: no ledger read, no behavior change, when off.
        #
        # Phase 55's dominance over this block is subtler than "escalation moved
        # it off confirm", which is FALSE in general: a sensitive-target READ
        # (SAFE_LOCAL_READ, allow-class) escalates allow->confirm and lands
        # EXACTLY here. Dominance holds instead because of a disjointness: the
        # only trust-eligible action type (MCP_TOOL_CALL) escalates confirm->
        # override on a sensitive target — off confirm, so this block is skipped —
        # while the reading types that stop AT confirm are deliberately NOT in
        # TRUST_ELIGIBLE_ACTION_TYPES. That is the real invariant, and it is
        # pinned by verify_eva_phase78 / test_trust_eligibility_pin: if a reading
        # type were ever added to the allowlist, a risk-escalated read of ~/.ssh
        # could be trust-de-escalated back to allow, undoing the escalation.
        if decision == "confirm":
            from ..permissions.trust_policy import calibrate, count_approvals, trust_policies_enabled

            if trust_policies_enabled():
                target = str(call_args.get("path") or call_args.get("target") or call_args.get("dst") or call_args.get("recipient") or "")
                calibrated = calibrate(
                    base_decision="confirm",
                    action_type=str(getattr(spec, "action_type", "") or ""),
                    approvals=count_approvals(name, target),
                )
                if calibrated.auto_allowed:
                    decision = "allow"
                    trace_gate_decision(name, "trusted_auto_allow", spec)

        # Phase 72 ORANGE: raise friction one step for a tool this role may use
        # but should never use unattended. Applied LAST, after the Phase 42
        # de-escalation, so it strictly dominates: a role-escalated action can
        # never be handed back to trust calibration and auto-allowed. Like
        # Phase 55 this only ever raises, so it is unconditional and fails safe.
        if role_tier is not None and role_tier is RoleTier.ORANGE:
            from ..agents.role_policy import escalate_one_step

            escalated = escalate_one_step(decision)
            if escalated != decision:
                decision = escalated
                trace_gate_decision(name, "role_escalated", spec)

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
        # Phase 88: re-inject the `confirmed=True` flag that registry.run STRIPS
        # at the untrusted entry (self-approval defense, see line ~1554). A few
        # gated handlers self-guard on `confirmed` as a SECOND check beyond the
        # gate -- system_power/guarded_power_action (returns "say confirm ...")
        # and message.send_via_ui (re-evaluates the gate with user_confirmed).
        # Because the flag was stripped, run_approved replayed them WITHOUT it,
        # so an override-approved shutdown/restart/sleep/message did not execute
        # -- it just re-asked for confirmation forever. run_approved is the ONE
        # trusted path: it is unreachable unless action.status is already
        # `confirmed` (checked above), so a real ledger confirmation HAS
        # occurred and re-adding the flag here faithfully represents it. Only
        # injected for handlers that actually accept a `confirmed` parameter, so
        # handlers whose lambda drops it (file.write_text/copy/move/delete --
        # gate is their sole enforcement) are byte-identical to before.
        args = dict(stored["args"])
        if "confirmed" not in args and _handler_accepts_confirmed(spec.handler):
            args["confirmed"] = True
        # Phase 86: a gated call can be missing a required arg (e.g. screen.observe
        # without `reason`) yet still create a pending -- args_schema is never
        # checked before gating. Approving it used to reach spec.handler(**args)
        # and raise TypeError, an unhandled crash AFTER the user already approved.
        # Convert that into a clean, reported failure; the normal (ungated) run
        # path still calls _invoke directly and is unaffected.
        try:
            return self._invoke(spec, args)
        except Exception as exc:
            return {"ok": False, "error": f"execution failed: {type(exc).__name__}: {exc}"}

    def _invoke(self, spec: ToolSpec, args: dict[str, Any]) -> Any:
        result = spec.handler(**args)
        payload = asdict(result) if hasattr(result, "__dataclass_fields__") else result
        # Flight recorder: record the actual invocation and a compact result
        # summary. Inert unless tracing is enabled with an active trace; wrapped
        # helper never raises, so it cannot affect the value returned to callers.
        from ..observability.context import summarize_result, trace_tool_call, tracing_enabled, trace_verification

        trace_tool_call(spec.name, args, summarize_result(payload))
        # Verification-first (Phase 38): independently check the action's declared
        # post-condition against real state and record it. This is purely
        # observational here (it never mutates `payload`), so it covers both
        # allow-class runs and confirmed writes without touching gate control flow.
        # Gated on tracing so the default (tracing-off) hot path does no extra I/O.
        if tracing_enabled():
            try:
                from .postconditions import verify_tool_effect

                verification = verify_tool_effect(spec.name, spec.verification_method, args, payload)
                trace_verification(spec.name, verification.as_dict())
            except Exception:
                pass
        return payload

    def _create_gated_pending(self, name: str, spec: ToolSpec, decision: str, args: dict[str, Any]) -> dict[str, Any]:
        from ..permissions.ledger import create_pending_action
        from ..permissions.pending_actions import EvaPendingAction

        requires_override = decision == "override"
        risk_level = "high" if spec.safety_level == "dangerous" else "medium"
        target = str(args.get("path") or args.get("target") or args.get("dst") or args.get("recipient") or "")
        # Mask declared sensitive arguments (e.g. screen.type_text's `text`)
        # before anything durable is written. redact_secrets/sanitize_payload
        # downstream only catch STRUCTURED secrets (API keys, emails) -- an
        # arbitrary password typed into a form is plain text to them, so this
        # per-tool allowlist is the only thing standing between it and disk.
        safe_args = {k: ("[HIDDEN]" if k in spec.sensitive_args else v) for k, v in args.items()}
        action = EvaPendingAction.new(
            action_type=name,
            risk_level=risk_level,
            risk_category=spec.action_type,
            summary=f"{name}: {spec.description}",
            target=target or None,
            payload_summary=", ".join(f"{key}={value}" for key, value in safe_args.items()) or None,
            requires_confirmation=not requires_override,
            requires_override=requires_override,
            source="tool_gate",
            executor_available=True,
            executor_name=name,
            safety_reason=f"{name} is classified as {decision}-class by the tool gate.",
            redacted_payload=safe_args,
        )
        create_pending_action(action)
        # IMPORTANT: register_pending_call must receive the REAL `args`, not
        # `safe_args` -- run_approved() replays this exact dict to actually
        # perform the action later. Only the ledger/durable record above is
        # masked; execution must never see "[HIDDEN]" in place of a real value.
        tool_gate.register_pending_call(action.id, name, args)
        phrase = f"confirm override {action.id}" if requires_override else f"confirm {action.id}"
        # Phase 75: the deterministic half of the explanation ships with every
        # approval prompt. It is assembled from source of truth (the spec's own
        # description and declared action_type) with no model involved, so it
        # costs nothing, cannot fail, and cannot be talked into saying something
        # false. `safe_args` is the masked form -- an explanation must never be
        # the thing that prints a password the ledger was careful to hide.
        from ..agents.explainer import explain_action

        explanation = explain_action(
            tool=name,
            description=spec.description,
            action_type=str(spec.action_type),
            decision=decision,
            args=safe_args,
        )
        return {
            "ok": False,
            "requires_confirmation": True,
            "pending_id": action.id,
            "risk_class": decision,
            "explanation": explanation.as_text(),
            "message": (
                f"{explanation.as_text()}\n\n"
                f"Say `{phrase}` to approve this exact action, or `explain {action.id}` for more."
            ),
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


def register_mcp_tool_specs(specs: dict[str, ToolSpec]) -> None:
    """Populate the shared MCP spec cache so every ToolRegistry instance
    (including the fresh one that executes confirmations) exposes them."""
    _MCP_TOOL_SPECS.update(specs)

