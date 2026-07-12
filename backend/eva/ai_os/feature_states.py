from __future__ import annotations

from .safety_boundaries import boundary_lines


FEATURE_STATE_CLASSES = (
    "available_status_only",
    "available_preview_only",
    "available_readonly_observation",
    "available_observation_only",
    "dry_run_gate_only",
    "available_existing_narrow_gate",
    "locked_future_gate",
    "blocked_by_policy",
    "not_implemented",
    "needs_user_confirmation",
    "needs_future_safety_phase",
)


def feature_states_text() -> str:
    descriptions = (
        ("available_status_only", "human-readable local status/report is available"),
        ("available_preview_only", "deterministic preview is available but cannot execute"),
        ("available_readonly_observation", "validated public-URL observation/report output is available without browser actions"),
        ("available_observation_only", "explicit one-shot redacted desktop observation/report output is available without desktop control"),
        ("dry_run_gate_only", "local/mock desktop-control policy, risk, approval, confirmation, and dry-run reports are available without control"),
        ("available_existing_narrow_gate", "only an already implemented narrow approved gate may act"),
        ("locked_future_gate", "future gate is described but remains locked"),
        ("blocked_by_policy", "request is denied by current safety policy"),
        ("not_implemented", "no implementation or runtime path exists"),
        ("needs_user_confirmation", "confirmation metadata is required but is never sufficient alone"),
        ("needs_future_safety_phase", "requires a later dedicated safety phase and verifier"),
    )
    return "\n".join(
        [
            "AI OS feature states",
            *boundary_lines(),
            "- Coding Specialist / CodingAgent Foundation: Phase 28 preview/report/status only.",
            "- CodingAgent source editing and patch application: locked.",
            "- CodingAgent shell, test, package, git, arbitrary file, and tool execution: locked.",
            "- CodingAgent Phase 28 handoff: Phase 29 Public Demo / Release is complete.",
            "- Public Demo / Release: Phase 29 report/status/profile only.",
            "- Public Demo / Release publishing, upload, package, commit, tag, push, and external actions: locked.",
            "- Release Candidate Hardening: Phase 30 report/status/planning only.",
            "- Release Candidate Hardening commit planning is text-only.",
            "- Release Candidate Hardening allows no Git operations and no publishing.",
            "- Release Candidate Hardening next safe step: user-approved commit execution outside Eva or a separate explicit commit-approval phase.",
            "- Roadmap Foundations: Phase 33 execution boundary audit is report/status/catalog only.",
            "- Roadmap Foundations cover Phase 33 through Phase 42 without enabling a new execution path.",
            "- Phase 41 safe real-capability pilot remains blocked until a later explicit approval phase.",
            "- Phase 42 Release Candidate v2 Hardening is documentation/verification hardening only.",
        ]
        + [f"- {name}: {description}." for name, description in descriptions]
    )


def locked_features_text() -> str:
    return "\n".join(
        [
            "AI OS locked future gates",
            *boundary_lines(),
            "- Real Browser Read-Only Mode: available for validated public-URL observation/report only; safe backend currently unavailable.",
            "- Browser control: locked; no click, type, forms, downloads, uploads, login, cookies, sessions, or profiles.",
            "- Real Desktop Observation Mode: available for explicit one-shot redacted observation/report only; safe backend currently unavailable.",
            "- Real Desktop Control Gate: dry-run gate only; no mouse, click, type, hotkey, clipboard, app/window control, automation, monitoring, or screenshot saving.",
            "- Voice microphone, playback, ASR, and TTS: local/mock foundation only.",
            "- Live LLM/provider routing: locked.",
            "- Shell, package, cloud, MCP, coding execution, and news/network retrieval: locked.",
            "- Broad file mutation: blocked; only the existing Phase 12L narrow gate is real.",
        ]
    )
