from __future__ import annotations


RELEASE_CANDIDATE_CHECKLIST = (
    "Dirty tree grouped by milestone and module.",
    "Public demo claims checked for locked browser, desktop, shell, provider, and source-edit boundaries.",
    "Phase 12L documented as a gated write path.",
    "Commit plan kept text-only with no staging or Git execution.",
    "Control Center, AI OS, capability, planner, and team-review states aligned.",
    "Release-candidate docs contain no user-specific private paths.",
    "Ignored environment filenames noted without reading their contents.",
    "Focused, quick, full, compile, and diff checks scheduled for fresh evidence.",
)


def checklist_text() -> str:
    return "\n".join(
        (
            "Eva Phase 30 release-candidate checklist",
            *(f"- [x] {item}" for item in RELEASE_CANDIDATE_CHECKLIST),
            "- Final human gate: user reviews the complete diff and explicitly authorizes any later commit.",
        )
    )
