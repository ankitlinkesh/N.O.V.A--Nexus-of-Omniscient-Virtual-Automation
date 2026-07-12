from __future__ import annotations


def boundary_lines() -> tuple[str, ...]:
    return (
        "Voice Assistant is local/mock preview only.",
        "No microphone access happened.",
        "No audio playback happened.",
        "No live ASR/TTS happened.",
        "No live LLM call was made.",
        "Voice commands cannot execute tools.",
        "Secrets/config/session data are blocked.",
        "Browser/desktop/shell/cloud/MCP execution remains locked.",
        "Phase 12L remains a gated write path.",
    )


def voice_policy_text() -> str:
    return "\n".join(
        [
            "Voice Assistant Foundation policy",
            *boundary_lines(),
            "The pipeline accepts bundled mock transcript text only.",
            "Transcript safety runs before any route preview.",
            "Agent-loop, workflow-planner, and execution-gate integration is metadata and preview only.",
            "Unsafe input is redacted, refused, or stopped safely.",
            "Voice output is text preview only.",
            "No new application write path is introduced.",
        ]
    )
