from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DesktopReadinessStatus(StrEnum):
    READY_FOR_DESIGN_ONLY = "ready_for_design_only"
    READY_FOR_FUTURE_OBSERVATION_GATE = "ready_for_future_observation_gate"
    BLOCKED_MISSING_SAFETY_LAYER = "blocked_missing_safety_layer"
    BLOCKED_EXECUTION_NOT_ALLOWED = "blocked_execution_not_allowed"
    LOCKED_BY_POLICY = "locked_by_policy"
    PHASE14_COMPLETE_LOCKED = "phase14_complete_locked"


@dataclass(frozen=True)
class DesktopReadinessCheck:
    name: str
    status: str
    evidence: str


@dataclass(frozen=True)
class DesktopReadinessGap:
    name: str
    reason: str
    required_before_enablement: str


@dataclass(frozen=True)
class DesktopLockedCapabilitySummary:
    real_desktop_observation_enabled: bool
    real_desktop_control_enabled: bool
    approvals_unlock_execution: bool
    locked_actions: tuple[str, ...]
    summary: str


@dataclass(frozen=True)
class DesktopLockedReadinessProof:
    status: DesktopReadinessStatus
    real_desktop_observation_enabled: bool
    real_desktop_control_enabled: bool
    approvals_unlock_execution: bool
    completed_layers: tuple[str, ...]
    checks: tuple[DesktopReadinessCheck, ...]
    gaps: tuple[DesktopReadinessGap, ...]
    locked_capabilities: DesktopLockedCapabilitySummary
    future_requirements: tuple[str, ...]
    next_phase: str
    phase12_boundary: str
    summary: str


DesktopPhase14ProofResult = DesktopLockedReadinessProof


def build_desktop_readiness_proof() -> DesktopLockedReadinessProof:
    checks = (
        DesktopReadinessCheck("safety model", "present", "DesktopAgent policy, status, blocked actions, and capability previews exist as local status surfaces."),
        DesktopReadinessCheck("app/window/session preview", "present", "Preview-only session and app/window/active-context schemas exist without real inspection."),
        DesktopReadinessCheck("screen observation policy", "present", "Screen, sensitive-screen, redaction, and capture-gate policy surfaces exist with capture locked."),
        DesktopReadinessCheck("keyboard/mouse action dry-run", "present", "Desktop action plans are text-only dry runs with no mouse, keyboard, clipboard, app launch, or file-dialog action."),
        DesktopReadinessCheck("desktop risk scoring", "present", "Deterministic string-only risk and approval previews exist without execution."),
        DesktopReadinessCheck("human approval model", "present", "Approval and confirmation phrase previews exist, and never unlock execution."),
        DesktopReadinessCheck("locked execution policy", "enforced", "Real observation and control remain disabled across all DesktopAgent status surfaces."),
        DesktopReadinessCheck("Control Center agreement", "present", "Control Center exposes the same locked DesktopAgent boundary and Phase 14 proof status."),
        DesktopReadinessCheck("BrowserAgent boundary", "unchanged", "BrowserAgent remains locked; DesktopAgent proof does not enable browser or network actions."),
        DesktopReadinessCheck("Phase 12L write boundary", "unchanged", "Only the narrow approved create-new-text-file gate is a real write path."),
    )
    return DesktopLockedReadinessProof(
        status=DesktopReadinessStatus.PHASE14_COMPLETE_LOCKED,
        real_desktop_observation_enabled=False,
        real_desktop_control_enabled=False,
        approvals_unlock_execution=False,
        completed_layers=tuple(check.name for check in checks[:6]),
        checks=checks,
        gaps=get_desktop_readiness_gaps(),
        locked_capabilities=get_locked_desktop_capability_summary(),
        future_requirements=get_future_desktop_requirements(),
        next_phase="Phase 15 LLM Router + Structured Reasoning Core. Phase 16 Context Assembly Engine, Phase 17 LLM Threat Defense + Prompt Injection Guard, and Phase 18 Agent Loop v1 are core architecture phases.",
        phase12_boundary="Phase 12L narrow real create remains a gated write path: approved brand-new .md/.txt files under docs/ or samples/ with exact confirmation.",
        summary="DesktopAgent Phase 14 is complete as a locked safety/readiness foundation. Real desktop observation and real desktop control are not enabled.",
    )


def get_desktop_readiness_gaps() -> tuple[DesktopReadinessGap, ...]:
    return (
        DesktopReadinessGap("explicit observation gate", "No real screen, window, app, or active-context observation is enabled.", "A separate user-commanded local observation gate with privacy classification and a verified source."),
        DesktopReadinessGap("sensitive-screen protection", "Policy and redaction design exist, but no live observation pipeline applies them.", "A future local redaction verifier that excludes credentials, tokens, chats, email, browser sessions, and private documents."),
        DesktopReadinessGap("verified UI targeting", "No real target detector or confidence verifier exists.", "A future verified UI target model that stops on low confidence and never accepts arbitrary coordinates."),
        DesktopReadinessGap("approval-to-execution boundary", "Approval models are previews only and intentionally do not execute actions.", "A separately approved, auditable, per-action permission session; confirmation alone must never bypass safety policy."),
        DesktopReadinessGap("observation and action verification", "There is no live desktop state to verify or repair.", "A future target-aware verifier, local audit trail, and safe rollback design before any controlled action is considered."),
    )


def get_locked_desktop_capability_summary() -> DesktopLockedCapabilitySummary:
    return DesktopLockedCapabilitySummary(
        real_desktop_observation_enabled=False,
        real_desktop_control_enabled=False,
        approvals_unlock_execution=False,
        locked_actions=(
            "screen capture, screenshots, OCR, and image analysis",
            "real window, app, and active-context inspection",
            "mouse movement, clicking, dragging, keyboard typing, and hotkeys",
            "clipboard read/write, app launching, and file-dialog automation",
            "terminal, shell, and package execution",
            "browser/desktop automation, PyAutoGUI, Playwright, MCP, and cloud calls",
            "reading .env, .env.local, secrets, tokens, cookies, passwords, and browser sessions",
        ),
        summary="All real DesktopAgent observation and control capabilities remain locked by policy. Approval previews do not change that boundary.",
    )


def get_future_desktop_requirements() -> tuple[str, ...]:
    return (
        "explicit user command for each future desktop task",
        "local privacy classification before any observation",
        "no secret, credential, cookie, password, token, browser-session, or unrelated private-content access",
        "verified UI target confidence before any future visible UI action",
        "per-action permission and confirmation that cannot override forbidden behavior",
        "local observation evidence, target-aware verification, and honest stop-on-uncertainty behavior",
        "auditable, narrowly scoped rollback only where a verified reversible action exists",
    )
