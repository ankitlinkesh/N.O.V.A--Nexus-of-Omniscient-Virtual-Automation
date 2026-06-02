from __future__ import annotations

from .profile import get_release_channel, is_public_mode


PUBLIC_MODE_LIMITS = (
    "No real WhatsApp/message sending.",
    "No MCP execution.",
    "No Playwright execution.",
    "No PyAutoGUI desktop execution.",
    "No private browser, email, chat, cookie, token, or password reading.",
    "No destructive file actions.",
    "No normal chat routing through Eva v2.",
)


def public_mode_summary() -> str:
    mode = "on" if is_public_mode() else "off"
    return "\n".join(
        [
            "Eva public/community mode",
            "",
            f"Release channel: {get_release_channel()}",
            f"Public mode: {mode}",
            "",
            "Public mode keeps demos useful while refusing risky real actions.",
            *[f"- {item}" for item in PUBLIC_MODE_LIMITS],
        ]
    )
