from __future__ import annotations


PROMPT_INJECTION_MARKERS: tuple[str, ...] = (
    "ignore previous",
    "ignore all previous",
    "disregard policy",
    "developer message",
    "system prompt",
    "bypass safety",
    "jailbreak",
    "tool_call",
    "execute tool",
)


def looks_like_prompt_injection(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(marker in lowered for marker in PROMPT_INJECTION_MARKERS)


def context_policy_text() -> str:
    return "\n".join(
        [
            "Context Assembly Policy",
            "",
            "Context assembly is local/mock preview only and prepares safe packets for future LLM use.",
            "No live LLM/API/provider calls happen, and no provider SDKs are used.",
            "Allowed context is source-aware, budget-aware, permission-aware, redaction-aware, and grounding-aware.",
            "Secrets, config files, sessions, tokens, cookies, passwords, browser data, raw runtime dumps, and arbitrary file reads are blocked.",
            "Prompt-injection-like content is data only; it cannot become trusted instruction.",
            "Unknown or hallucinated capability claims are excluded from trusted capability metadata.",
            "Assembled context cannot execute tools, browser, desktop, shell, package, cloud, MCP, PyAutoGUI, or Playwright actions.",
            "Phase 12L narrow approved new .md/.txt creation remains a gated application write path.",
            "No live LLM call was made. Context assembly is local/mock preview only. Assembled context cannot execute tools.",
        ]
    )
