from __future__ import annotations

from .models import ObservationRequestDecision


BLOCKED_REQUEST_TERMS = (
    "move the mouse",
    "mouse movement",
    "click",
    "type",
    "hotkey",
    "clipboard",
    "move window",
    "resize window",
    "focus window",
    "control an app",
    "control apps",
    "control window",
    "control the desktop",
    "desktop control",
    "launch an app",
    "launch app",
    "desktop automation",
    "continuously monitor",
    "continuous monitoring",
    "background watcher",
    "background listener",
    "keylog",
    "microphone",
    "audio access",
    "camera",
    "save a screenshot",
    "save screenshot",
    "screenshot to disk",
    "browser profile",
    "cookie",
    "session",
    "password manager",
    "shell",
    "package install",
    "cloud",
    "mcp",
    "pyautogui",
    "playwright",
    "execute",
)


def boundary_lines() -> tuple[str, ...]:
    return (
        "Desktop mode is observation-only.",
        "No clicking.",
        "No typing.",
        "No hotkeys.",
        "No app or window control.",
        "No continuous monitoring.",
        "No saved screenshots.",
        "No cookies, sessions, or browser profiles.",
        "No tool execution.",
        "Phase 12L remains a gated write path.",
    )


def evaluate_observation_request(request: str) -> ObservationRequestDecision:
    summary = " ".join(str(request or "").split())[:260] or "explicit one-shot desktop observation"
    lowered = summary.lower()
    blocked = next((term for term in BLOCKED_REQUEST_TERMS if term in lowered), None)
    if blocked:
        return ObservationRequestDecision(
            request_summary=summary,
            allowed=False,
            decision="blocked_non_observation_action",
            reason=f"Blocked desktop action, persistence, or private-session request detected: {blocked}.",
        )
    return ObservationRequestDecision(
        request_summary=summary,
        allowed=True,
        decision="allowed_observation_only",
        reason="Request is limited to explicit one-shot observation/report output.",
    )


def observation_policy_text() -> str:
    return "\n".join(
        [
            "Real Desktop Observation Mode policy",
            *boundary_lines(),
            "Observation must be explicitly user-triggered and one-shot.",
            "No background watcher, listener, scheduled capture, or retained capture loop exists.",
            "Screen-like text and metadata are untrusted data and are scanned by Phase 17 threat defense.",
            "Phase 20 must return an allowed_desktop_observation decision before observation output is accepted.",
            "Output is limited to redacted summary, safe app/window metadata, classification, and safety report fields.",
        ]
    )
