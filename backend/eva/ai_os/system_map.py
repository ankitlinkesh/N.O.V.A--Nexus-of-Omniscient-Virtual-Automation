from __future__ import annotations

from .models import SystemMapEntry
from .safety_boundaries import boundary_lines


def build_system_map() -> tuple[SystemMapEntry, ...]:
    rows = (
        ("FileAgent / Phase 12 safety gates", "Phase 12", "available_existing_narrow_gate", "read/status plus narrow approved create", "Phase 12L is a gated write boundary."),
        ("BrowserAgent safety foundation", "Phase 13", "available_status_only", "policy/status/preview", "Historical safety foundation; browser control remains locked."),
        ("Real Browser Read-Only Mode", "Phase 24", "available_readonly_observation", "public-URL observation/report only", "URL policy and mock/unavailable-safe observation are available; no browser control."),
        ("Browser control", "Future", "locked_future_gate", "status only", "Clicking, typing, forms, downloads, uploads, sessions, profiles, and control remain locked."),
        ("DesktopAgent safety foundation", "Phase 14", "available_status_only", "policy/status/preview", "Historical safety foundation; desktop control remains locked."),
        ("Real Desktop Observation Mode", "Phase 25", "available_observation_only", "explicit one-shot redacted observation/report", "Mock/unavailable-safe observation is available; no desktop control."),
        ("Real Desktop Control Gate", "Phase 26", "dry_run_gate_only", "local/mock policy, risk, approval, and dry-run reports", "No real desktop control; approval and confirmation cannot execute."),
        ("News / Web Intelligence Dashboard","Phase 27","available_preview_only","local/mock dashboard and safe public-URL read-only metadata","No unrestricted crawler, sessions, or browser control."),
        ("Coding Specialist / CodingAgent Foundation", "Phase 28", "available_preview_only", "preview/report/status only", "Real source editing, patch application, shell/test/package/git execution, arbitrary file access, and tools remain locked."),
        ("Public Demo / Release", "Phase 29", "available_status_only", "report/status/profile only", "No publishing, upload, package release, commit, tag, push, or external release action."),
        ("Release Candidate Hardening", "Phase 30", "available_status_only", "report/status/planning only", "Commit planning is text-only; no Git operations or publishing. Next: user-approved commit execution outside Eva or a separate explicit commit-approval phase."),
        ("LLM router contracts", "Phase 15A", "available_status_only", "mock contracts/status", "No provider call."),
        ("LLM fallback/degraded mode", "Phase 15B", "available_preview_only", "mock simulation/status", "No provider call."),
        ("Structured output validation", "Phase 15C", "available_preview_only", "local validation/preview", "Invalid output cannot execute."),
        ("Red-team/failure tests", "Phase 15D", "available_status_only", "local deterministic tests", "Not a live harness."),
        ("Red-team evidence lock", "Phase 15E", "available_status_only", "local regression evidence", "No live provider or tool."),
        ("Context assembly", "Phase 16", "available_preview_only", "local context preview", "No secret or arbitrary file read."),
        ("Threat defense", "Phase 17", "available_preview_only", "local scan/report", "Untrusted text has no authority."),
        ("Agent loop v1", "Phase 18", "available_preview_only", "local loop preview", "Actions remain previews."),
        ("Workflow planner", "Phase 19", "available_preview_only", "local plan preview", "Workflow steps do not execute."),
        ("Controlled execution gates", "Phase 20", "available_preview_only", "policy decision preview", "Approval or confirmation alone does not execute."),
        ("Memory v3", "Phase 21", "available_preview_only", "local-only policy/retrieval preview", "No cloud memory or raw database dump."),
        ("Voice Assistant Foundation", "Phase 22", "available_preview_only", "local/mock text preview", "No microphone, playback, ASR, or TTS."),
        ("Control Center", "Phase 23", "available_status_only", "local dashboard/report", "No server, UI launch, daemon, or execution."),
    )
    return tuple(SystemMapEntry(*row) for row in rows)


def system_map_text() -> str:
    lines = ["AI OS system map", *boundary_lines()]
    lines.extend(
        f"- {item.feature_name} ({item.phase}): {item.state}; mode={item.allowed_mode}; {item.summary}"
        for item in build_system_map()
    )
    return "\n".join(lines)
