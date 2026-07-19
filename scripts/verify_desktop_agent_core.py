from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.eva.agent.executor import ToolExecutor
from backend.eva.core.fast_commands import maybe_handle_fast_command
from backend.eva.core.operator_commands import handle_operator_command
from backend.eva.desktop.observer import get_desktop_snapshot
from backend.eva.desktop.windows import get_active_window, list_open_windows
import backend.eva.tools.desktop as desktop
from backend.eva.tools.registry import ToolRegistry


class DryRegistry(ToolRegistry):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []

    def run(self, name: str, **kwargs: Any) -> Any:
        self.calls.append({"tool": name, "args": kwargs})
        if name == "open_app":
            return f"Opening {kwargs.get('app') or kwargs.get('app_name')}."
        if name == "open_folder":
            return f"Opening folder {kwargs.get('folder') or kwargs.get('folder_name')}."
        if name == "verify_last_action":
            return {
                "ok": True,
                "verified": True,
                "target": kwargs.get("target", ""),
                "tool": kwargs.get("tool", ""),
                "message": f"{kwargs.get('target', 'target')} verified.",
            }
        if name == "window_active":
            return {"ok": True, "window": {"title": "Eva Agent", "process_name": "chrome.exe"}}
        if name == "window_list":
            return {
                "ok": True,
                "count": 2,
                "windows": [
                    {"title": "Eva Agent", "process_name": "chrome.exe"},
                    {"title": "Windows PowerShell", "process_name": "powershell.exe"},
                ],
            }
        if name == "window_focus":
            return {"ok": True, "verified": True, "window": {"title": kwargs.get("query", "chrome"), "process_name": "chrome.exe"}}
        if name == "app.focus":
            # Phase 64: the typed-console "focus"/"switch to" command now routes
            # through app.focus (console/internal-only) instead of the
            # planner-visible window_focus; same result shape either way.
            return {"ok": True, "verified": True, "window": {"title": kwargs.get("query", "chrome"), "process_name": "chrome.exe"}}
        if name == "desktop_observe":
            return {
                "ok": True,
                "active_window_title": "Eva Agent",
                "active_process": "chrome.exe",
                "open_windows": [{"title": "Eva Agent", "process_name": "chrome.exe"}],
                "screen_capture_available": False,
                "notes": [],
            }
        if name == "close_app":
            return super().run(name, **kwargs)
        if name == "system_power":
            return super().run(name, **kwargs)
        return super().run(name, **kwargs)


def emit(case: str, passed: bool, **payload: Any) -> int:
    print(json.dumps({"case": case, "pass": passed, **payload}, indent=2, ensure_ascii=False))
    return 0 if passed else 1


def fast(message: str, registry: DryRegistry, session_context: dict[str, Any]) -> tuple[str, str] | None:
    return maybe_handle_fast_command(message, registry, session_context)


def operator(message: str, registry: DryRegistry, executor: ToolExecutor, session_context: dict[str, Any]) -> dict[str, Any] | None:
    return handle_operator_command(message, {"registry": registry, "executor": executor, "session_context": session_context})


def main() -> int:
    failures = 0
    registry = DryRegistry()
    executor = ToolExecutor(registry)
    session_context: dict[str, Any] = {}

    active = get_active_window()
    failures += emit(
        "active_window_safe_object",
        active is None or isinstance(active.as_dict(), dict),
        active=active.as_dict() if active else None,
    )

    windows = list_open_windows(limit=5)
    failures += emit(
        "list_windows_safe_list",
        isinstance(windows, list) and all(isinstance(item.as_dict(), dict) for item in windows),
        count=len(windows),
        windows=[item.as_dict() for item in windows[:3]],
    )

    registry.calls.clear()
    active_response = fast("what window am I on", registry, session_context)
    failures += emit(
        "what_window_routes_window_active",
        bool(active_response and registry.calls and registry.calls[-1]["tool"] == "window_active"),
        response=active_response,
        calls=registry.calls,
    )

    registry.calls.clear()
    list_response = fast("what is open", registry, session_context)
    failures += emit(
        "what_is_open_routes_window_list",
        bool(list_response and registry.calls and registry.calls[-1]["tool"] == "window_list"),
        response=list_response,
        calls=registry.calls,
    )

    registry.calls.clear()
    focus_response = fast("switch to chrome", registry, session_context)
    failures += emit(
        # Phase 64: redirected from window_focus to app.focus (same
        # underlying eva.desktop.windows.focus_window; app.focus is the
        # console/internal-scoped tool, not planner-visible).
        "switch_to_chrome_routes_app_focus",
        bool(focus_response and registry.calls and registry.calls[-1]["tool"] == "app.focus" and registry.calls[-1]["args"].get("query") == "chrome"),
        response=focus_response,
        calls=registry.calls,
    )

    registry.calls.clear()
    open_response = fast("open chrome", registry, session_context)
    failures += emit(
        "open_chrome_verifies",
        bool(
            open_response
            and any(call["tool"] == "open_app" for call in registry.calls)
            and any(call["tool"] == "verify_last_action" for call in registry.calls)
        ),
        response=open_response,
        calls=registry.calls,
    )

    previous_allowlist = os.environ.get("EVA_CLOSE_APP_ALLOWLIST")
    os.environ["EVA_CLOSE_APP_ALLOWLIST"] = "chrome,notepad"
    original_subprocess_run = desktop.subprocess.run
    kill_calls: list[list[str]] = []

    class FakeCompletedProcess:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_subprocess_run(command: list[str], *args: Any, **kwargs: Any) -> FakeCompletedProcess:
        kill_calls.append(command)
        return FakeCompletedProcess()

    desktop.subprocess.run = fake_subprocess_run  # type: ignore[assignment]
    try:
        registry.calls.clear()
        refused = fast("close unknownapp", registry, session_context)
        failures += emit(
            "close_unknownapp_refused",
            bool(refused and "safe close allowlist" in refused[0].lower() and not kill_calls),
            response=refused,
            calls=registry.calls,
            kill_calls=kill_calls,
        )
    finally:
        desktop.subprocess.run = original_subprocess_run  # type: ignore[assignment]
        if previous_allowlist is None:
            os.environ.pop("EVA_CLOSE_APP_ALLOWLIST", None)
        else:
            os.environ["EVA_CLOSE_APP_ALLOWLIST"] = previous_allowlist

    observe_no_screen = get_desktop_snapshot(include_windows=False, include_screen=False)
    failures += emit(
        "desktop_observe_no_screen_does_not_capture",
        bool(observe_no_screen.get("ok") and observe_no_screen.get("screen_capture_available") is False and not observe_no_screen.get("screen_capture_path")),
        result=observe_no_screen,
    )

    observe_blocked_screen = get_desktop_snapshot(include_windows=False, include_screen=True, explicit_screen_intent=False)
    notes = " ".join(str(item) for item in observe_blocked_screen.get("notes") or [])
    failures += emit(
        "desktop_observe_screen_requires_explicit_intent",
        bool(observe_blocked_screen.get("ok") and observe_blocked_screen.get("screen_capture_available") is False and "explicitly ask" in notes),
        result=observe_blocked_screen,
    )

    registry.calls.clear()
    shutdown = operator("shutdown my laptop", registry, executor, session_context)
    failures += emit(
        "shutdown_still_requires_confirmation",
        bool(shutdown and shutdown.get("requires_confirmation") is True and shutdown.get("action") == "shutdown" and not registry.calls),
        result=shutdown,
        calls=registry.calls,
    )

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
