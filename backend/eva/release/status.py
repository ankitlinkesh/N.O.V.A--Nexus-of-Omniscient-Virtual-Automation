from __future__ import annotations

from dataclasses import dataclass

from .profile import get_release_channel, is_public_mode
from .public_mode import PUBLIC_MODE_LIMITS


@dataclass(frozen=True)
class ReleaseStatus:
    channel: str
    public_mode: bool
    llm_note: str
    data_note: str
    safety_note: str


def release_status() -> ReleaseStatus:
    public = is_public_mode()
    return ReleaseStatus(
        channel=get_release_channel(),
        public_mode=public,
        llm_note="Eva can use API-backed LLM reasoning elsewhere when configured; this status command makes no cloud call.",
        data_note="Research Memory data is local runtime data and must not be included in public releases.",
        safety_note="Community mode keeps risky execution disabled and exposes only status, demo, dry-run, and safety-simulator flows.",
    )


def format_release_status() -> str:
    status = release_status()
    public_text = "enabled" if status.public_mode else "disabled"
    lines = [
        "Eva release status",
        "",
        f"Channel: {status.channel}",
        f"Public/community mode: {public_text}",
        status.llm_note,
        status.data_note,
        status.safety_note,
        "",
        "Public mode disabled actions:",
    ]
    lines.extend(f"- {item}" for item in PUBLIC_MODE_LIMITS)
    lines.extend(
        [
            "",
            "Public release reminder:",
            "- Do not commit secrets, local runtime data, screenshots, traces, personal Research Memory data, or private browser/session data.",
        ]
    )
    return "\n".join(lines)


def format_public_release_checklist() -> str:
    return "\n".join(
        [
            "Eva public release checklist",
            "",
            "Before sharing:",
            "- Confirm API keys are not committed.",
            "- Confirm .env.local is not committed.",
            "- Confirm runtime data folders are ignored.",
            "- Confirm personal Research Memory database files are not included.",
            "- Confirm screenshots, traces, logs, local model files, and private browser/session data are not included.",
            "- Confirm MCP, Playwright, PyAutoGUI, WhatsApp send, and destructive file actions remain disabled.",
            "- Confirm demo scenarios say no real action executed.",
            "- Confirm public docs use: local data/control with API-backed LLM reasoning when configured.",
        ]
    )
