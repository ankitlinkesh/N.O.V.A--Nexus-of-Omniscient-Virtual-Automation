from __future__ import annotations


def boundary_lines() -> tuple[str, ...]:
    return (
        "No live LLM call was made.",
        "AI OS dashboard is local/status only.",
        "Preview-only features do not execute.",
        "Tools are not executed.",
        "Browser/desktop/shell/cloud/MCP execution remains locked.",
        "Secrets/config/session data are blocked.",
        "Phase 12L remains a gated write path.",
    )


def safety_boundaries_text() -> str:
    return "\n".join(
        [
            "AI OS safety boundaries",
            *boundary_lines(),
            "No provider SDK, web server, browser launch, desktop UI, or background daemon is used.",
            "No microphone, audio, ASR, or TTS runtime is used.",
            "Arbitrary filesystem reads and writes remain blocked.",
            "Raw WorkSession and memory database dumps remain blocked.",
            "Dashboard output is report/status metadata and grants no authority.",
            "The boundary lines above describe this dashboard. For the exact, code-derived",
            "picture of which tools Eva executes and which require confirmation, run `eva capability truth`.",
        ]
    )
