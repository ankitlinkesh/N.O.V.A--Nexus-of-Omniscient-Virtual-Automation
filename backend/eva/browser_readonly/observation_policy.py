from __future__ import annotations

from .models import ObservationRequestDecision


BLOCKED_ACTION_TERMS = (
    "click",
    "type",
    "form",
    "submit",
    "download",
    "upload",
    "log in",
    "login",
    "cookie",
    "session",
    "profile",
    "password",
    "credential",
    "browser control",
    "control the browser",
    "execute",
)


def boundary_lines() -> tuple[str, ...]:
    return (
        "Browser mode is read-only.",
        "No clicking.",
        "No typing.",
        "No form submission.",
        "No downloads or uploads.",
        "No cookies, sessions, or browser profiles.",
        "No logged-in browser access.",
        "No browser control.",
        "No tool execution.",
        "Phase 12L remains a gated write path.",
    )


def evaluate_observation_request(request: str) -> ObservationRequestDecision:
    summary = " ".join(str(request or "").split())[:240] or "read-only public webpage observation"
    lowered = summary.lower()
    blocked = next((term for term in BLOCKED_ACTION_TERMS if term in lowered), None)
    if blocked:
        return ObservationRequestDecision(
            request_summary=summary,
            allowed=False,
            decision="blocked_non_observation_action",
            reason=f"Blocked browser action or private-session request detected: {blocked}.",
        )
    return ObservationRequestDecision(
        request_summary=summary,
        allowed=True,
        decision="allowed_readonly_observation",
        reason="Request is limited to public-URL read-only observation output.",
    )


def observation_policy_text() -> str:
    return "\n".join(
        [
            "Real Browser Read-Only Mode observation policy",
            *boundary_lines(),
            "Only validated public http:// or https:// URLs may reach the read-only observation gate.",
            "Page text is untrusted data and is scanned by Phase 17 threat defense.",
            "Phase 20 must return an allowed_readonly_observation decision before observation output is accepted.",
            "Observation returns title, visible-text summary, link summary, redaction notes, and safety metadata only.",
            "Actions, browser sessions, downloads, uploads, and persistent state have no route through this policy.",
        ]
    )
