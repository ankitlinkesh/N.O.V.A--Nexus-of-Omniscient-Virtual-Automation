from __future__ import annotations

from .models import CapabilityMatrixEntry
from .safety_boundaries import boundary_lines


def build_capability_matrix() -> tuple[CapabilityMatrixEntry, ...]:
    rows = (
        ("AI OS dashboard", "Phase 23", "available_status_only", "local dashboard/report", False, False, "none", "none", "Status metadata only.", "Review the next safe step."),
        ("Phase 12L narrow real create", "Phase 12L", "available_existing_narrow_gate", "approved new .md/.txt creation", True, True, "existing approval gate required", "exact existing confirmation required", "Only existing real application write path.", "Use only through the implemented Phase 12L gate."),
        ("Real Browser Read-Only Mode", "Phase 24", "available_readonly_observation", "validated public-URL observation/report only", False, False, "not required for read-only output", "cannot unlock actions", "Sessionless, credentialless, output-redacted; safe backend currently unavailable.", "Use URL policy or deterministic mock observation."),
        ("Browser control", "Future", "locked_future_gate", "status only", False, False, "cannot unlock", "cannot unlock", "Click, type, form, download, upload, login, session, profile, and control remain locked.", "Keep locked pending a future dedicated safety phase."),
        ("Real Desktop Observation Mode", "Phase 25", "available_observation_only", "explicit one-shot redacted observation/report", False, False, "not required for observation output", "cannot unlock actions", "Sensitive-screen-aware, no saved screenshots, monitoring, or control; safe backend currently unavailable.", "Use policy or deterministic mock observation."),
        ("Real Desktop Control Gate", "Phase 26", "dry_run_gate_only", "local/mock policy, eligibility, risk, and dry-run reports", False, False, "metadata only; cannot execute", "metadata only; cannot execute", "No mouse, keyboard, hotkey, clipboard, app/window control, automation, or monitoring.", "Use deterministic dry-run reports only."),
        ("News / Web Intelligence Dashboard","Phase 27","available_preview_only","local/mock dashboard and safe public-URL metadata",False,False,"not applicable","not applicable","No crawler, login/session/cookie/profile access, network in tests, or browser control.","Use deterministic fixture reports."),
        ("Coding Specialist / CodingAgent Foundation", "Phase 28", "available_preview_only", "preview/report/status only", False, False, "not applicable", "cannot unlock execution", "Real source editing, patch application, shell/test/package/git execution, arbitrary file access, and tools remain locked.", "Review deterministic previews only."),
        ("Public Demo / Release", "Phase 29", "available_status_only", "report/status/profile only", False, False, "not applicable", "cannot publish or commit", "No publishing, upload, package release, git release operation, external send, or unsafe execution.", "Review the local public-demo report."),
        ("Release Candidate Hardening", "Phase 30", "available_status_only", "report/status/planning only", False, False, "not applicable", "cannot stage, commit, tag, or push", "Commit planning is text-only; no Git operations, publishing, upload, source editing, or tool execution.", "User-approved commit execution outside Eva or a separate explicit commit-approval phase."),
        ("Roadmap Foundations", "Phase 33", "available_status_only", "report/status/catalog only", False, False, "not applicable", "cannot unlock execution", "Execution boundary audit, command catalog, capability catalog, frontend truth, grounded answers, voice reliability, and verifier metadata are report-only.", "Use `eva roadmap status` and `eva execution boundaries`."),
        ("Safe Real-Capability Pilot", "Phase 41", "blocked_by_policy", "status only", False, False, "not available", "not available", "No real capability is graduated by roadmap/status commands.", "Require a later explicit approval phase."),
        ("Release Candidate v2 Hardening", "Phase 42", "available_status_only", "documentation/verification hardening only", False, False, "not applicable", "cannot publish or release", "No package publishing, tag, release, upload, deployment, or new execution path.", "Refresh public release posture only after verification."),
        ("Controlled execution gates", "Phase 20", "available_preview_only", "policy decision preview", False, False, "preview metadata only", "preview metadata only", "Approval or confirmation alone does not execute.", "Review gate decisions without action."),
        ("Memory v3", "Phase 21", "available_preview_only", "local-only policy/retrieval preview", False, False, "not applicable", "not applicable", "No cloud memory or raw database dump.", "Use safe grounded summaries only."),
        ("Voice Assistant Foundation", "Phase 22", "available_preview_only", "local/mock text preview", False, False, "preview metadata only", "preview metadata only", "No microphone/audio/ASR/TTS runtime.", "Keep live voice locked."),
        ("News and network retrieval", "Future", "blocked_by_policy", "status only", False, False, "not available", "not available", "Network calls are blocked.", "Require a future reviewed network phase."),
        ("Coding source editing and shell execution", "Future", "blocked_by_policy", "status only", False, False, "not available", "not available", "Source editing, patch application, shell, test, package, git, and tool execution are blocked.", "Require a future execution safety phase."),
        ("Cloud and MCP control", "Future", "not_implemented", "status only", False, False, "not available", "not available", "Cloud/MCP execution is unavailable.", "Require explicit implementation and safety review."),
    )
    return tuple(CapabilityMatrixEntry(*row) for row in rows)


def capability_matrix_text() -> str:
    lines = ["AI OS capability matrix", *boundary_lines()]
    for item in build_capability_matrix():
        lines.extend(
            [
                f"- {item.feature_name} ({item.phase})",
                f"  State: {item.current_state}; allowed mode: {item.allowed_mode}.",
                f"  Execution allowed: {item.execution_allowed}; write allowed: {item.write_allowed}.",
                f"  Approval: {item.approval_behavior}; confirmation: {item.confirmation_behavior}.",
                f"  Safety: {item.safety_notes}",
                f"  Next safe action: {item.next_safe_action}",
            ]
        )
    return "\n".join(lines)
