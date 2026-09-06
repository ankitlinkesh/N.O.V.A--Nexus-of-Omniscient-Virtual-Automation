from __future__ import annotations

import os
import re
from typing import Any

from ..agent.executor import ToolExecutor, ToolExecutionResult
from ..agent.planner import PlannedToolCall
from ..tools.desktop import close_app_allowlist
from ..tools.registry import ToolRegistry
from .web_context import (
    last_web_results,
    profile_key_from_message,
    profile_urls,
    remember_web_results,
    result_reference_from_message,
    summarize_web_result,
    wants_previous_result,
)


APP_ALIASES = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "spotify": "spotify",
    "vscode": "vscode",
    "vs code": "vscode",
    "visual studio code": "vscode",
    "codex": "codex",
    "settings": "settings",
    "notepad": "notepad",
    "terminal": "terminal",
    "powershell": "powershell",
    "cmd": "cmd",
}

FOLDER_ALIASES = {
    "downloads": "downloads",
    "download": "downloads",
    "documents": "documents",
    "document": "documents",
    "desktop": "desktop",
    "eva folder": "eva folder",
    "eva": "eva folder",
    "project folder": "eva folder",
}

MEDIA_ALIASES = {
    "volume up": "volume_up",
    "increase volume": "volume_up",
    "turn volume up": "volume_up",
    "volume down": "volume_down",
    "decrease volume": "volume_down",
    "turn volume down": "volume_down",
    "mute": "mute",
    "unmute": "mute",
    "play pause": "play_pause",
    "play/pause": "play_pause",
    "play": "play_pause",
    "pause": "play_pause",
    "next song": "next",
    "next track": "next",
    "previous song": "previous",
    "previous track": "previous",
}

POWER_ACTIONS = {
    "shutdown": ("shutdown", "shut down", "turn off"),
    "restart": ("restart", "reboot"),
    "sleep": ("sleep",),
    "sign_out": ("sign out", "log out", "logout"),
}


def _normalize(message: str) -> str:
    return " ".join(message.lower().strip().split())


def _enabled() -> bool:
    return os.environ.get("EVA_OPERATOR_MODE", "true").strip().lower() not in {"0", "false", "no", "off"}


def _power_requires_confirmation() -> bool:
    return os.environ.get("EVA_OPERATOR_CONFIRM_POWER", "true").strip().lower() not in {"0", "false", "no", "off"}


def _screen_allowed() -> bool:
    return os.environ.get("EVA_OPERATOR_ALLOW_SCREEN_ON_REQUEST", "true").strip().lower() not in {"0", "false", "no", "off"}


def _after_prefix(text: str, prefixes: tuple[str, ...]) -> str | None:
    for prefix in prefixes:
        if text.startswith(prefix):
            value = text[len(prefix):].strip(" :")
            if value:
                return value
    return None


def _window_name_after(text: str, prefixes: tuple[str, ...]) -> str | None:
    """`_after_prefix`, but only when what follows is a NAME rather than an errand.

    Phase 103. This dispatcher runs ahead of the fast-command layer and holds a
    second copy of the same window prefixes, so guarding only the other copy
    changed nothing measurable: "focus the notepad window and type NOVA-... into
    it" still arrived here, was taken whole as a window name, matched the
    Calculator through the `WindowsApps` in its executable path, and came back
    "Done, focused the notepad window and type nova-... into it." -- wrong
    window, typing clause dropped, reported as success. One rule written in two
    places, and the copy nobody guarded was the one that decided the behaviour.
    """
    from .fast_command_helpers import _looks_like_an_instruction

    value = _after_prefix(text, prefixes)
    if value is None or _looks_like_an_instruction(value):
        return None
    return value


def _safe_tool_names(registry: ToolRegistry) -> list[str]:
    try:
        specs = registry.list_tools()
    except Exception:
        return []
    names = []
    for spec in specs:
        if isinstance(spec, dict) and spec.get("safety_level") == "safe":
            names.append(str(spec.get("name")))
    return sorted(name for name in names if name)


def _status_response(registry: ToolRegistry) -> str:
    payload = {
        "operator_mode": "enabled" if _enabled() else "disabled",
        "voice_commands": "browser push-to-talk when SpeechRecognition is available",
        "screen_vision": "on-request only" if _screen_allowed() else "disabled",
        "workspace": "read-only tools available",
        "dangerous_actions": "confirmation required" if _power_requires_confirmation() else "disabled by policy",
        "safe_tools": _safe_tool_names(registry),
        "safety": {
            "arbitrary_shell": False,
            "camera": False,
            "always_on_screen": False,
            "power_actions_need_confirmation": True,
        },
    }
    lines = [
        f"Operator mode: {payload['operator_mode']}.",
        f"Voice: {payload['voice_commands']}.",
        f"Screen vision: {payload['screen_vision']}.",
        f"Workspace: {payload['workspace']}.",
        f"Power actions: {payload['dangerous_actions']}.",
        "Close-app allowlist: " + ", ".join(close_app_allowlist()),
        "Safe tools: " + ", ".join(payload["safe_tools"][:16]),
    ]
    return "\n".join(lines)


def _tool_response_text(result: ToolExecutionResult) -> str:
    if result.requires_confirmation:
        action = result.action or "that action"
        return result.error or f"This will {action.replace('_', ' ')} your laptop. Confirm?"
    if not result.ok:
        if result.tool == "close_app":
            return result.error or "I can close that if it is in the safe close allowlist."
        return f"I tried, but that failed safely: {result.error or 'unknown error'}."

    if result.tool == "open_app":
        return "Done, opened it."
    if result.tool == "close_app":
        return "Done, closed it."
    if result.tool == "open_folder":
        return "Done, opened that folder."
    if result.tool == "open_url":
        return "Done, opened that in Chrome."
    if result.tool in {"media_control", "media_key"}:
        return "Done."
    if result.tool == "lock_laptop":
        return "Locking the laptop."
    if result.tool == "web_search":
        remember_summary = summarize_web_result(result.result, include_prompt=True)
        return remember_summary
    if result.tool == "analyze_screen":
        data = result.result if isinstance(result.result, dict) else {}
        if not data.get("ok"):
            return str(data.get("summary") or "I captured the screen once, but screen analysis is temporarily unavailable.")
        summary = str(data.get("summary") or "I analyzed the screen.")
        issue = str(data.get("possible_issue") or "").strip()
        actions = data.get("suggested_actions") if isinstance(data.get("suggested_actions"), list) else []
        extra = f" Possible issue: {issue}" if issue else ""
        if actions:
            extra += " Try this: " + "; ".join(str(item) for item in actions[:3] if str(item).strip())
        return summary + extra
    return str(result.result)


def _format_window_list(result: object) -> str:
    if not isinstance(result, dict) or not result.get("ok"):
        return "I couldn't read the open windows from Windows right now."
    windows = result.get("windows") if isinstance(result.get("windows"), list) else []
    if not windows:
        return "I don't see any visible app windows from this context."
    lines = ["Open windows:"]
    for item in windows[:12]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "Untitled")
        process = str(item.get("process_name") or "unknown")
        lines.append(f"- {title} ({process})")
    return "\n".join(lines)


def _format_active_window(result: object) -> str:
    if not isinstance(result, dict) or not result.get("ok"):
        return "I couldn't read the active window from Windows right now."
    window = result.get("window") if isinstance(result.get("window"), dict) else {}
    title = str(window.get("title") or "unknown window")
    process = str(window.get("process_name") or "unknown process")
    return f"You're on: {title} ({process})."


def _format_window_action(result: ToolExecutionResult, verb: str, target: str) -> str:
    if not result.ok:
        return f"I tried to {verb} {target}, but couldn't: {result.error or 'window not found'}."
    data = result.result if isinstance(result.result, dict) else {}
    if verb == "focus" and data.get("verified") is False:
        return f"I tried switching to {target}, but Windows did not confirm focus."
    return f"Done, {verb}ed {target}."


def _verification_response(tool: str, target: str, verify_result: ToolExecutionResult | None, default: str) -> str:
    if verify_result is None or not verify_result.ok or not isinstance(verify_result.result, dict):
        return default
    verified = bool(verify_result.result.get("verified"))
    target_label = target.strip() or "it"
    if tool == "open_app":
        name = target_label.title() if target_label.lower() not in {"vscode", "cmd"} else target_label
        return f"Done, {name} is open." if verified else f"Done, opened {target_label}, but I couldn't verify the window."
    if tool == "open_folder":
        return f"Done, {target_label} is open." if verified else f"Done, opened {target_label}, but I couldn't verify the folder window."
    if tool == "open_url":
        return "Done, opened that in Chrome." if verified else "Done, opened the link, but I couldn't verify the browser URL from Windows."
    return default


def _handled(
    *,
    tool: str | None,
    args: dict[str, Any] | None,
    response: str,
    requires_confirmation: bool = False,
    action: str | None = None,
    result: ToolExecutionResult | None = None,
) -> dict[str, Any]:
    return {
        "handled": True,
        "route": "operator-command",
        "tool": tool,
        "args": args or {},
        "response": response,
        "requires_confirmation": requires_confirmation,
        "action": action,
        "result": result.as_dict() if result else None,
    }


def _execute(
    executor: ToolExecutor,
    tool: str,
    args: dict[str, Any] | None = None,
    session_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    call = PlannedToolCall(tool=tool, args=args or {})
    result = executor.execute(call)
    if result.tool == "web_search" and result.ok:
        remember_web_results(session_context, result.result)
    return _handled(
        tool=tool,
        args=args or {},
        response=_tool_response_text(result),
        requires_confirmation=result.requires_confirmation,
        action=result.action,
        result=result,
    )


def _execute_with_verification(
    executor: ToolExecutor,
    tool: str,
    args: dict[str, Any] | None = None,
    session_context: dict[str, Any] | None = None,
    target: str = "",
) -> dict[str, Any]:
    handled = _execute(executor, tool, args or {}, session_context)
    result_payload = handled.get("result")
    if not isinstance(result_payload, dict) or not result_payload.get("ok") or result_payload.get("requires_confirmation"):
        return handled
    verify = executor.execute(PlannedToolCall(tool="verify_last_action", args={"tool": tool, "target": target}))
    result_payload["verification"] = verify.as_dict()
    handled["response"] = _verification_response(tool, target, verify, str(handled.get("response") or "Done."))
    return handled


def _power_confirmation(action: str) -> dict[str, Any]:
    return _handled(
        tool="guarded_power_action",
        args={"action": action, "confirmed": False},
        response=f"This will {action.replace('_', ' ')} your laptop. Confirm?",
        requires_confirmation=True,
        action=action,
    )


def _url_from_message(message: str) -> str | None:
    match = re.search(r"https?://\S+", message, flags=re.IGNORECASE)
    if match:
        return match.group(0).rstrip(".,)")
    domain_match = re.match(r"^(?:open|visit|go to)\s+([a-z0-9-]+(?:\.[a-z0-9-]+)+[^\s]*)$", message.strip(), flags=re.IGNORECASE)
    if domain_match:
        return domain_match.group(1)
    return None


def handle_operator_command(message: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    context = context or {}
    registry = context.get("registry")
    executor = context.get("executor")
    session_context = context.get("session_context")
    if not isinstance(registry, ToolRegistry) or not isinstance(executor, ToolExecutor):
        return None

    text = _normalize(message)
    original = message.strip()
    if not text:
        return None

    if text == "operator status":
        return _handled(tool=None, args={}, response=_status_response(registry))

    if not _enabled():
        return None

    for action, phrases in POWER_ACTIONS.items():
        if any(phrase in text for phrase in phrases):
            if _power_requires_confirmation():
                return _power_confirmation(action)
            return None

    if text in {"lock", "lock laptop", "lock pc", "lock screen"}:
        return _execute(executor, "lock_laptop", {}, session_context)

    if text in {"what window am i on", "what window am i using", "active window", "current window"}:
        result = executor.execute(PlannedToolCall(tool="window_active", args={}))
        return _handled(tool="window_active", args={}, response=_format_active_window(result.result), result=result)

    if text in {"what is open", "what's open", "list windows", "list open windows", "open windows"}:
        result = executor.execute(PlannedToolCall(tool="window_list", args={"limit": 40}))
        return _handled(tool="window_list", args={"limit": 40}, response=_format_window_list(result.result), result=result)

    focused = _window_name_after(text, ("switch to ", "focus ", "go to window ", "bring up "))
    if focused:
        result = executor.execute(PlannedToolCall(tool="window_focus", args={"query": focused}))
        return _handled(tool="window_focus", args={"query": focused}, response=_format_window_action(result, "focus", focused), result=result)

    minimized = _window_name_after(text, ("minimize ", "minimise "))
    if minimized:
        result = executor.execute(PlannedToolCall(tool="window_minimize", args={"query": minimized}))
        return _handled(tool="window_minimize", args={"query": minimized}, response=_format_window_action(result, "minimiz", minimized), result=result)

    maximized = _window_name_after(text, ("maximize ", "maximise "))
    if maximized:
        result = executor.execute(PlannedToolCall(tool="window_maximize", args={"query": maximized}))
        return _handled(tool="window_maximize", args={"query": maximized}, response=_format_window_action(result, "maximiz", maximized), result=result)

    open_check = re.match(r"^(?:is|verify|check)\s+(.+?)\s+open\??$", text)
    if open_check:
        target = open_check.group(1).strip()
        result = executor.execute(PlannedToolCall(tool="verify_last_action", args={"tool": "open_app", "target": target}))
        data = result.result if isinstance(result.result, dict) else {}
        response = f"Yep, {target} looks open." if data.get("verified") else f"I couldn't verify that {target} is open."
        return _handled(tool="verify_last_action", args={"tool": "open_app", "target": target}, response=response, result=result)

    if text.startswith("close "):
        target = _after_prefix(text, ("close ", "quit "))
        if target:
            # Phase 82: refuse a non-allowlisted app before the gate, so it is
            # not confirmed only to be rejected on execution (Phase 74 lesson).
            from ..tools.desktop import close_app_refusal, is_closeable

            if not is_closeable(target):
                return _handled(tool="close_app", args={"app": target}, response=close_app_refusal(target), result=None)
            return _execute(executor, "close_app", {"app": target}, session_context)

    app = _after_prefix(text, ("open app ", "launch app ", "start app ", "open ", "launch ", "start "))
    if app:
        if app in APP_ALIASES:
            return _execute_with_verification(executor, "open_app", {"app": APP_ALIASES[app]}, session_context, APP_ALIASES[app])
        if app in FOLDER_ALIASES:
            return _execute_with_verification(executor, "open_folder", {"folder": FOLDER_ALIASES[app]}, session_context, FOLDER_ALIASES[app])

    folder = _after_prefix(text, ("open folder ", "show folder ", "open my ", "show my "))
    if folder and folder in FOLDER_ALIASES:
        return _execute_with_verification(executor, "open_folder", {"folder": FOLDER_ALIASES[folder]}, session_context, FOLDER_ALIASES[folder])

    url = _url_from_message(original)
    if url:
        return _execute_with_verification(executor, "open_url", {"url": url}, session_context, url)

    profile_key = profile_key_from_message(original)
    if profile_key and text.startswith(("open ", "show ", "launch ")) and "my " in f"{text} ":
        saved_url = profile_urls().get(profile_key, "")
        if saved_url:
            return _execute(executor, "open_url", {"url": saved_url}, session_context)
        label = "profile" if profile_key == "profile" else profile_key
        return _handled(
            tool=None,
            args={},
            response=f"I don't have your {label} URL saved yet. Send me the link once and I'll use it next time.",
        )

    if wants_previous_result(original):
        results = last_web_results(session_context)
        selected, matches, reason = result_reference_from_message(original, results)
        if selected:
            return _execute(executor, "open_url", {"url": str(selected.get("url") or "")}, session_context)
        if reason == "ambiguous" and matches:
            labels = [str(item.get("title") or item.get("url") or "Untitled")[:60] for item in matches[:4]]
            return _handled(tool=None, args={}, response=f"Which one do you want me to open: {', '.join(labels)}?")
        if reason == "no_results":
            return _handled(tool=None, args={}, response="I don't have previous search results to open yet. Search first, then say which result to open.")
        return _handled(tool=None, args={}, response="I found possible matches, but I can't assume which one you mean. Say the result number or name.")

    if profile_key and text.startswith(("open ", "show ", "launch ")):
        label = "profile" if profile_key == "profile" else profile_key
        return _handled(
            tool=None,
            args={},
            response=f"I don't have your {label} URL saved yet. Send me the link once and I'll use it next time.",
        )

    search = _after_prefix(original, ("search web for ", "web search ", "search for ", "google ", "look up "))
    if search:
        return _execute(executor, "web_search", {"query": search}, session_context)

    if text in MEDIA_ALIASES:
        return _execute(executor, "media_control", {"action": MEDIA_ALIASES[text]}, session_context)

    if _screen_allowed() and (
        text in {
            "show screen",
            "show my screen",
            "look at screen",
            "look at my screen",
            "check screen",
            "check my screen",
            "analyze screen",
            "analyze my screen",
            "what is on my screen",
            "what's on my screen",
            "tell me what is open",
            "tell me what's open",
        }
        or ("screen" in text and any(word in text for word in ("show", "look", "check", "analyze", "analyse", "inspect")))
        or ("error" in text and any(word in text for word in ("visible", "screen", "this")))
    ):
        return _execute(executor, "analyze_screen", {"question": original[:800]}, session_context)

    return None
