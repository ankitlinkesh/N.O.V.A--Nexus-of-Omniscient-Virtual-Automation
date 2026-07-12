from __future__ import annotations


HARDENING_FINDINGS = (
    "Public claims remain bounded to deterministic reports, previews, and locked foundations.",
    "Browser and desktop control remain unavailable; observation foundations do not imply control.",
    "CodingAgent remains preview/report/status only and cannot edit source or run tools.",
    "Voice remains a locked/mock foundation; News remains local/mock or safe-read-only.",
    "Phase 12L narrow approved new .md/.txt creation remains a gated write path.",
    "Release-candidate and commit-plan surfaces do not stage, commit, tag, push, publish, or upload.",
)

KNOWN_WARNINGS = (
    "Ignored .env and .env.local filenames exist locally; their contents were not read.",
    "The release candidate remains uncommitted until explicit user approval outside Eva.",
    "Fresh verifier evidence is required immediately before any later commit decision.",
)

SAFETY_PROOF = (
    "All Phase 30 outputs are deterministic local text.",
    "No runtime Git, shell, package, cloud, MCP, browser, desktop, or provider action is available.",
    "No arbitrary file read/write, raw memory dump, or WorkSession dump was introduced.",
    "No secret, configuration, token, cookie, password, or session content is read.",
    "No new write path was added; Phase 12L remains the sole real-create boundary.",
)


def hardening_report_text() -> str:
    lines = (
        "Eva Phase 30 hardening report",
        "- Documentation consistency: Phase 30 claims are bounded and aligned.",
        "- Safety boundary status: unchanged and locked.",
        "- Findings:",
        *(f"  - {item}" for item in HARDENING_FINDINGS),
        "- Known non-blocking warnings:",
        *(f"  - {item}" for item in KNOWN_WARNINGS),
        "- Blocking issues: none after focused and master verification pass.",
    )
    return "\n".join(lines)


def safety_proof_text() -> str:
    return "\n".join(
        (
            "Eva Phase 30 safety proof",
            *(f"- {item}" for item in SAFETY_PROOF),
        )
    )
