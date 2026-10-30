"""Which native tools each first-party MCP server owns (Phase 160).

Pure data, imported by both the servers (what to serve) and the client rewiring (what to redirect),
so the two can never disagree about which server a tool lives in.
"""

from __future__ import annotations

DOMAIN_TOOLS: dict[str, tuple[str, ...]] = {
    "spotify": (
        "spotify_status",
        "spotify_search_desktop",
        "spotify_play_desktop",
        "spotify_now_playing_status",
        "spotify_search",
        "spotify_play_query",
        "spotify_pause",
        "spotify_next",
        "spotify_previous",
        "spotify_restart_current",
    ),
    "youtube": (
        "chrome_activate_top_youtube_result",
        "youtube_transcript",
    ),
    "gmail": (
        "email.draft_gmail",
        "email.send_drafted",
    ),
    "whatsapp": (
        "message.prepare",
        "message.confirm_send",
        "message.send_via_ui",
    ),
}


def tool_domain(tool_name: str) -> str | None:
    for domain, names in DOMAIN_TOOLS.items():
        if tool_name in names:
            return domain
    return None
