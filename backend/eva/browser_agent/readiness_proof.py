from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BrowserReadinessStatus(StrEnum):
    READY_FOR_DESIGN_ONLY = "ready_for_design_only"
    READY_FOR_FUTURE_READONLY_GATE = "ready_for_future_readonly_gate"
    BLOCKED_MISSING_SAFETY_LAYER = "blocked_missing_safety_layer"
    BLOCKED_EXECUTION_NOT_ALLOWED = "blocked_execution_not_allowed"
    LOCKED_BY_POLICY = "locked_by_policy"


@dataclass(frozen=True)
class BrowserReadinessCheck:
    name: str
    status: str
    evidence: str


@dataclass(frozen=True)
class BrowserReadinessGap:
    name: str
    reason: str
    required_before_readonly: str


@dataclass(frozen=True)
class BrowserReadOnlyReadinessProof:
    status: BrowserReadinessStatus
    real_readonly_enabled: bool
    completed_layers: tuple[str, ...]
    checks: tuple[BrowserReadinessCheck, ...]
    gaps: tuple[BrowserReadinessGap, ...]
    locked_execution: tuple[str, ...]
    future_requirements: tuple[str, ...]
    next_phase: str
    phase12_boundary: str
    summary: str


BrowserReadinessProofResult = BrowserReadOnlyReadinessProof


def build_browser_readiness_proof() -> BrowserReadOnlyReadinessProof:
    checks = (
        BrowserReadinessCheck("safety model", "present", "BrowserAgent status, policy, blocked actions, and action-safety previews exist."),
        BrowserReadinessCheck("session preview", "present", "Preview-only session records and lifecycle status exist without launching a browser."),
        BrowserReadinessCheck("observation/page summary design", "present", "Page/text/DOM summary schemas, redaction policy, and observation readiness exist as preview-only surfaces."),
        BrowserReadinessCheck("action dry-run", "present", "Browser action plans, risks, approvals, and readiness are text-only dry-run surfaces."),
        BrowserReadinessCheck("domain/site-risk model", "present", "Domain strings can be classified locally without DNS, network, or browser access."),
        BrowserReadinessCheck("locked execution policy", "enforced", "Live read-only mode and real browser control remain disabled."),
        BrowserReadinessCheck("Control Center agreement", "present", "Control Center exposes BrowserAgent safety, session, observation, action, and domain-risk panels."),
        BrowserReadinessCheck("Phase 12L write boundary", "unchanged", "Only the narrow approved create-new-text-file gate is a real write path."),
    )
    completed_layers = tuple(check.name for check in checks[:5])
    gaps = get_browser_readiness_gaps()
    return BrowserReadOnlyReadinessProof(
        status=BrowserReadinessStatus.READY_FOR_DESIGN_ONLY,
        real_readonly_enabled=False,
        completed_layers=completed_layers,
        checks=checks,
        gaps=gaps,
        locked_execution=get_locked_browser_execution_summary(),
        future_requirements=get_future_readonly_requirements(),
        next_phase="Future BrowserAgent read-only gate with explicit user command, domain policy, observation source limits, redaction, verification, and audit.",
        phase12_boundary="Phase 12L narrow real create remains a gated write path: approved brand-new .md/.txt files under docs/ or samples/ with exact confirmation.",
        summary="BrowserAgent is ready for design/proof status only. Real browser read-only mode is not enabled.",
    )


def get_browser_readiness_gaps() -> tuple[BrowserReadinessGap, ...]:
    return (
        BrowserReadinessGap("live observation gate", "No live page read, DOM read, screenshot, or browser-state probe is enabled.", "A future local read-only observation adapter with explicit user command and privacy checks."),
        BrowserReadinessGap("domain-gated read-only policy", "Domain/site-risk classification exists, but it is not connected to real navigation or page reads.", "A future allow/ask/block gate that runs before any read-only browser observation."),
        BrowserReadinessGap("redaction verification", "Redaction rules are design-only and have not been applied to live page text.", "A future verifier proving secrets, cookies, tokens, passwords, chats, and account data are excluded."),
        BrowserReadinessGap("target-aware verification", "There is no live browser target to verify yet.", "A future check that the observed page matches the user-requested URL/domain and is not stale."),
        BrowserReadinessGap("human-in-the-loop transition", "No confirmation flow exists for sensitive private, account, file-transfer, payment, or external-send pages.", "A future permission session that asks before any sensitive read-only observation."),
    )


def get_locked_browser_execution_summary() -> tuple[str, ...]:
    return (
        "browser launch",
        "navigation or URL opening",
        "DNS/network calls",
        "live website fetch/read",
        "screenshots or screen capture",
        "DOM access",
        "cookies/localStorage/session/profile/password/token reads",
        "click/type/submit/login/payment/upload/download",
        "Playwright/browser-use/Stagehand/Maxun execution",
        "shell/package/cloud/MCP/PyAutoGUI/desktop calls",
    )


def get_future_readonly_requirements() -> tuple[str, ...]:
    return (
        "explicit user command for each read-only browser task",
        "domain/site-risk gate before observation",
        "no cookies, passwords, tokens, localStorage, sessions, or browser profile reads",
        "local redaction and output minimization before summaries",
        "target-aware verification that the observed page matches the requested domain",
        "Control Center and WorkSession audit evidence for every read-only observation",
        "clear refusal for login, payment, file-transfer, messaging, harmful, or private pages unless a future policy explicitly allows status-only handling",
    )
