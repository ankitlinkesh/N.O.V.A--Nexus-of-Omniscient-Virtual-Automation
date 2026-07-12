from __future__ import annotations


def defense_policy_text() -> str:
    return "\n".join(
        [
            "Threat Defense Policy",
            "",
            "Phase 17 scans user requests, context packets, memory-like text, tool-output-like text, and other untrusted content before any future LLM call.",
            "Threat defense is local/mock preview only.",
            "No live LLM/API/provider calls happen, and no provider SDKs are used.",
            "System/developer policy and Eva safety policy outrank user text, quoted text, memory-like text, tool-like text, and retrieved context.",
            "Untrusted context cannot override trusted policy/instruction hierarchy.",
            "Prompt-injection-like content is treated as untrusted data.",
            "Secrets/config/session data are blocked.",
            "Exfiltration and tool-request attempts fail safely.",
            "Defended context cannot execute tools.",
            "Arbitrary file reads, browser execution, desktop execution, shell/package/cloud/MCP execution, and new write paths remain blocked.",
            "Phase 12L narrow approved new .md/.txt creation remains a gated application write path.",
            "No live LLM call was made.",
        ]
    )
