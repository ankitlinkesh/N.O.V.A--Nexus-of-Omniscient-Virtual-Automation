BOUNDARIES = (
    "Dashboard is local/mock or safe-read-only only.", "No unrestricted crawler.",
    "No login/session/cookie/profile access.", "No browser control.",
    "No background monitoring unless a future explicit scheduler gate exists.",
    "No live LLM call was made.", "No tool execution.",
    "Phase 12L remains a gated write path.",
)
def news_policy_text() -> str:
    return "\n".join(("News / Web Intelligence policy", "Public URLs only; sources are never absolute truth.", *BOUNDARIES))
