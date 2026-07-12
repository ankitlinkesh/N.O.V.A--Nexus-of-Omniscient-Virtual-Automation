from __future__ import annotations

from .action_dry_run import (
    BLOCKED_DESKTOP_ACTION_EXECUTION,
    create_desktop_action_dry_run,
    create_desktop_action_plan_preview,
    get_desktop_action_approval_requirements,
)
from .approval_audit import get_desktop_approval_audit_status
from .approval_model import DesktopApprovalLevel, preview_desktop_approval_request
from .approval_policy import get_desktop_approval_policy, list_desktop_forbidden_action_classes
from .action_safety import evaluate_desktop_action_safety, list_blocked_desktop_actions
from .app_preview import create_active_context_preview, create_app_status_preview
from .app_risk import classify_desktop_app_risk
from .capability_policy import list_desktop_capability_previews
from .policy import get_desktop_capability_policy
from .readiness import get_desktop_observation_readiness
from .redaction_policy import get_desktop_screen_redaction_rules
from .risk_scoring import RISK_FACTOR_NAMES, list_high_risk_desktop_actions, score_desktop_action_risk
from .safety_matrix import build_desktop_safety_matrix
from .confirmation_phrases import preview_desktop_confirmation_phrase
from .screen_observation import create_screen_observation_preview, get_desktop_screen_capture_gate
from .screen_policy import (
    evaluate_screen_observation_safety,
    get_desktop_screen_observation_readiness,
    get_desktop_screen_policy,
    list_sensitive_screen_categories,
)
from .session import DesktopSessionPreview, create_preview_session, planned_session_preview
from .session_registry import get_latest_preview_session, list_preview_sessions
from .status import get_desktop_agent_status
from .window_preview import create_window_status_preview
from .risk import evaluate_desktop_action_risk


def format_desktop_status() -> str:
    status = get_desktop_agent_status()
    lines = [
        "DesktopAgent status",
        "",
        f"Phase: {status.phase}",
        f"Status: {status.status}",
        "Real screen observation: locked",
        "Real desktop control: locked",
        "Execution enabled: no",
        "",
        "Allowed now:",
    ]
    lines.extend(f"- {item}" for item in status.allowed_now)
    lines.extend(
        [
            "",
            "Blocked now:",
            *_bullets(status.blocked_now),
            "",
            f"Next phase: {status.next_phase}",
            "Execution: status only. No screen capture, no screenshot, no window inspection, no app launch, no mouse action, no keyboard action, no clipboard access, no file dialog automation, no terminal/shell execution, no package install, and no cloud action was executed.",
        ]
    )
    return "\n".join(lines)


def format_desktop_policy() -> str:
    policy = get_desktop_capability_policy()
    return "\n".join(
        [
            "DesktopAgent policy",
            "",
            "Current mode: safety model only.",
            f"Real screen observation: {'enabled' if policy.real_screen_observation_enabled else 'locked'}",
            f"Real desktop control: {'enabled' if policy.real_desktop_control_enabled else 'locked'}",
            f"Screen capture: {'allowed' if policy.screen_capture_allowed else 'blocked'}",
            f"Screenshots: {'allowed' if policy.screenshot_allowed else 'blocked'}",
            f"Window inspection: {'allowed' if policy.window_inspection_allowed else 'blocked'}",
            f"App launch: {'allowed' if policy.app_launch_allowed else 'blocked'}",
            f"Mouse actions: {'allowed' if policy.mouse_allowed else 'blocked'}",
            f"Keyboard actions: {'allowed' if policy.keyboard_allowed else 'blocked'}",
            f"Clipboard access: {'allowed' if policy.clipboard_allowed else 'blocked'}",
            f"File dialog automation: {'allowed' if policy.file_dialog_allowed else 'blocked'}",
            f"Terminal/shell execution: {'allowed' if policy.terminal_allowed else 'blocked'}",
            f"Package installs: {'allowed' if policy.package_install_allowed else 'blocked'}",
            "",
            "Allowed now:",
            *_bullets(policy.allowed_status_actions),
            "",
            "Automation backends:",
            "- none enabled; PyAutoGUI, Playwright, MCP, desktop control, shell, package, and cloud execution stay locked.",
            "",
            "Execution: policy preview only. No screen, screenshot, window, app, keyboard, mouse, clipboard, terminal, package, or private app state was read or changed.",
        ]
    )


def format_desktop_blocked_actions() -> str:
    lines = ["DesktopAgent blocked actions", ""]
    for item in list_blocked_desktop_actions():
        lines.append(f"- {item.action}: {item.reason}")
    lines.extend(
        [
            "",
            "Reason:",
            "Phase 14A defines the safety model first. Real desktop observation/control needs future app risk policy, human confirmation gates, target verification, and rollback/audit design.",
            "Real screen observation: locked.",
            "Real desktop control: locked.",
            "",
            "Execution: blocked-action summary only. No desktop action was executed.",
        ]
    )
    return "\n".join(lines)


def format_desktop_action_safety(action: str) -> str:
    decision = evaluate_desktop_action_safety(action)
    allowed = "yes" if decision.allowed_now else "no"
    return "\n".join(
        [
            "DesktopAgent action safety",
            "",
            f"Action: {decision.action}",
            f"Category: {decision.category.value}",
            f"Decision: {decision.decision}",
            f"Allowed now: {allowed}",
            "Real screen observation: locked",
            "Real desktop control: locked",
            "",
            "Reason:",
            decision.reason,
            "",
            "Future gate:",
            decision.required_future_gate,
            "",
            "Safe alternative:",
            decision.safe_alternative,
            "",
            "Execution: safety preview only. No screen, screenshot, window, app, mouse, keyboard, clipboard, file dialog, terminal, package, or cloud action was executed.",
        ]
    )


def format_desktop_app_risk(app_or_category: str) -> str:
    risk = classify_desktop_app_risk(app_or_category)
    return "\n".join(
        [
            "DesktopAgent app risk",
            "",
            f"Input: {risk.query}",
            f"Category: {risk.category.value}",
            f"Risk level: {risk.risk_level.value}",
            f"Allowed for control now: {'yes' if risk.allowed_for_control_now else 'no'}",
            "Real screen observation: locked",
            "Real desktop control: locked",
            "",
            "Reason:",
            risk.reason,
            "",
            "Safe alternative:",
            risk.safe_alternative,
            "",
            "Execution: app risk string classification only. No screen, no desktop control, no real app, no window, no file, no terminal, no package, and no private state was inspected.",
        ]
    )


def format_desktop_readiness() -> str:
    return "\n".join(
        [
            "DesktopAgent readiness",
            "",
            "Status: not ready for real desktop observation or control.",
            "Real screen observation: locked",
            "Real desktop control: locked",
            "",
            "Ready now:",
            "- desktop status",
            "- desktop policy summary",
            "- blocked action explanations",
            "- desktop action safety preview",
            "- app risk string classification",
            "- Control Center locked panel",
            "",
            "Still missing before future desktop execution:",
            "- explicit user-commanded observation gate",
            "- private-window and app-risk policy",
            "- high-confidence UI target model",
            "- permission and confirmation sessions",
            "- verification and rollback design",
            "- audit evidence in WorkSession/Control Center",
            "",
            "Execution: readiness status only. No screen capture, screenshot, window inspection, app launch, mouse action, keyboard action, clipboard access, terminal/shell execution, package install, desktop automation, MCP, browser, or cloud action was executed.",
        ]
    )


def format_desktop_capability_previews() -> str:
    lines = ["DesktopAgent capability previews", ""]
    for item in list_desktop_capability_previews():
        lines.append(f"- {item.capability_id}: {item.execution_status}. {item.safety_notes}")
    lines.extend(["", "Execution: capability preview only. No desktop observation/control was executed."])
    return "\n".join(lines)


def format_desktop_action_dry_run(request: str) -> str:
    dry_run = create_desktop_action_dry_run(request)
    lines = [
        "Desktop Action Dry-Run",
        "",
        f"Request: {dry_run.request}",
        "Mode: dry-run text only.",
        "Real desktop control is locked.",
        "",
        "Planned preview steps:",
    ]
    for step in dry_run.steps:
        lines.append(f"- {step.step_id}: {step.action_type} | risk {step.risk.level.value} | execute now: no")
    lines.extend(
        [
            "",
            "Blocked execution:",
            *_bullets(dry_run.blocked_execution),
            "",
            "Execution: dry-run/status only. No screen was observed, no app or window was inspected, and no mouse, keyboard, clipboard, file dialog, terminal, browser, package, network, or cloud action was executed.",
        ]
    )
    return "\n".join(lines)


def format_desktop_action_plan(request: str) -> str:
    plan = create_desktop_action_plan_preview(request)
    lines = [
        "Desktop Action Plan Preview",
        "",
        f"Request: {plan.request}",
        f"Mode: {plan.mode}",
        f"Real desktop execution: {plan.real_desktop_execution}",
        "",
        "Steps:",
    ]
    for step in plan.steps:
        lines.append(f"- {step.action_type}: {step.description} Risk: {step.risk.level.value}. Approval: {step.required_approval}.")
    lines.extend(
        [
            "",
            "Approval gates:",
            *_bullets(tuple(f"{item.action_type}: {item.requirement} ({item.status})" for item in plan.approvals)),
            "",
            f"Next phase: {plan.next_phase}",
            "Execution: plan preview only. No desktop action was executed.",
        ]
    )
    return "\n".join(lines)


def format_desktop_action_risk(action: str) -> str:
    risk = evaluate_desktop_action_risk(action)
    return "\n".join(
        [
            "Desktop Action Risk",
            "",
            f"Action: {risk.action}",
            f"Preview type: {risk.action_type}",
            f"Risk level: {risk.level.value}",
            f"Executable now: {'yes' if risk.executable_now else 'no'}",
            f"Blocked now: {'yes' if risk.blocked_now else 'no'}",
            f"Approval requirement: {risk.approval_required}",
            "",
            "Reason:",
            risk.reason,
            "",
            "Execution: risk preview only. Real desktop control is locked.",
        ]
    )


def format_desktop_action_approvals() -> str:
    approvals = get_desktop_action_approval_requirements()
    lines = [
        "Desktop Action Approval Requirements",
        "",
        "Mode: dry-run/status only.",
        "Real desktop control is locked.",
        "",
        "Approval requirements:",
    ]
    lines.extend(f"- {item.action_type}: {item.requirement}. Status: {item.status}." for item in approvals)
    lines.extend(["", "Execution: approval policy only. No desktop action was executed."])
    return "\n".join(lines)


def format_desktop_dry_run_policy() -> str:
    return "\n".join(
        [
            "Desktop Action Dry-Run policy",
            "",
            "Allowed now:",
            "- create dry-run plan text only",
            "- explain desktop action risks",
            "- explain future approval requirements",
            "- show what would be blocked",
            "- show action plan preview from user request",
            "",
            "Blocked now:",
            *_bullets(BLOCKED_DESKTOP_ACTION_EXECUTION),
            "",
            "Risk levels:",
            "- low_status_only",
            "- medium_future_observation",
            "- high_user_confirmation_required",
            "- critical_blocked",
            "- forbidden",
            "",
            "Execution: dry-run policy only. Real desktop control is locked.",
        ]
    )


def format_desktop_action_readiness() -> str:
    return "\n".join(
        [
            "Desktop Action Readiness",
            "",
            "Mode: dry-run readiness only.",
            "Status: not ready for real desktop action execution.",
            "Real desktop control is locked.",
            "",
            "Missing before execution:",
            "- active user-commanded observation gate",
            "- verified UI target model with confidence thresholds",
            "- app and sensitive-screen risk gates",
            "- human confirmation for click/type/hotkey/clipboard/app/file-dialog actions",
            "- WorkSession audit, target-aware verification, and rollback/repair design",
            "",
            "Phase 12L boundary still stands: a gated write path is approved new .md/.txt creation under docs/ or samples/.",
            "Execution: readiness status only. No desktop action was executed.",
        ]
    )


def format_desktop_risk_score(request: str) -> str:
    result = score_desktop_action_risk(request)
    return "\n".join(
        [
            "Desktop Action Risk Score",
            "",
            f"Request: {result.request}",
            f"Score: {result.score.points}/100",
            f"Risk level: {result.score.level.value}",
            f"Approval level: {result.approval.level.value}",
            "Real desktop execution is locked.",
            "",
            "Top factors:",
            *_bullets(tuple(f"{factor.name}: {factor.points} points. {factor.reason}" for factor in result.factors[:5])),
            "",
            "Execution: risk/status only. No screen, window, app, mouse, keyboard, clipboard, file dialog, terminal, package, browser, network, or cloud action was executed.",
        ]
    )


def format_desktop_risk_factors(request: str) -> str:
    result = score_desktop_action_risk(request)
    lines = [
        "Desktop Action Risk Factors",
        "",
        f"Request: {result.request}",
        "Risk factor model:",
    ]
    lines.extend(f"- {name}" for name in RISK_FACTOR_NAMES)
    lines.extend(["", "Detected factors:"])
    lines.extend(f"- {factor.name}: {factor.level.value}, {factor.points} points. {factor.reason}" for factor in result.factors)
    lines.extend(["", "Execution: factor explanation only. Real desktop execution is locked."])
    return "\n".join(lines)


def format_desktop_approval_required(request: str) -> str:
    result = score_desktop_action_risk(request)
    return "\n".join(
        [
            "Desktop Action Approval Required",
            "",
            f"Request: {result.request}",
            f"Risk level: {result.score.level.value}",
            f"Approval level: {result.approval.level.value}",
            f"Available now: {'yes' if result.approval.available_now else 'no'}",
            f"Required phrase: {result.approval.phrase}",
            "",
            "Reason:",
            result.approval.reason,
            "",
            "Execution: approval/risk status only. Real desktop control is locked.",
        ]
    )


def format_desktop_safety_matrix() -> str:
    matrix = build_desktop_safety_matrix()
    lines = [
        "Desktop Safety Matrix",
        "",
        f"Status: {matrix.status}",
        "Real desktop execution is locked.",
        "",
        "Decisions:",
    ]
    lines.extend(f"- {item.action_type}: {item.risk_level.value}; approval {item.approval_level.value}; {item.execution_status}. {item.reason}" for item in matrix.decisions)
    lines.extend(["", "Forbidden action classes:", *_bullets(matrix.forbidden_action_classes), "", f"Next phase: {matrix.next_phase}", "Execution: safety matrix only. No desktop action was executed."])
    return "\n".join(lines)


def format_desktop_high_risk_actions() -> str:
    return "\n".join(
        [
            "Desktop High Risk Actions",
            "",
            "High-risk or forbidden classes:",
            *_bullets(list_high_risk_desktop_actions()),
            "",
            "Real desktop execution is locked.",
            "Execution: high-risk action list only. No desktop action was executed.",
        ]
    )


def format_desktop_risk_readiness() -> str:
    matrix = build_desktop_safety_matrix()
    return "\n".join(
        [
            "Desktop Risk Readiness",
            "",
            "Status: not ready for real desktop action execution.",
            "Real desktop control is locked.",
            "",
            "Readiness gaps:",
            *_bullets(matrix.readiness_gaps),
            "",
            "Approval levels:",
            "- none_status_only",
            "- user_preview_required",
            "- explicit_user_confirmation_required",
            "- elevated_confirmation_required",
            "- forbidden_no_approval_available",
            "",
            f"Next phase: {matrix.next_phase}",
            "Phase 12L boundary still stands: a gated write path is approved new .md/.txt creation under docs/ or samples/.",
            "Execution: readiness status only. No desktop action was executed.",
        ]
    )


def format_desktop_approval_policy() -> str:
    policy = get_desktop_approval_policy()
    return "\n".join(
        [
            "Desktop Human Approval Model policy",
            "",
            f"Status: {policy.status}",
            "The approval model does not unlock real desktop execution.",
            f"Real execution unlocked: {'yes' if policy.real_execution_unlocked else 'no'}",
            f"Future expiration policy: {policy.expiration_seconds} seconds",
            "",
            "Approval levels:",
            *_bullets(tuple(level.value for level in policy.approval_levels)),
            "",
            "Forbidden action classes:",
            *_bullets(tuple(item.action_class for item in policy.forbidden_classes)),
            "",
            "Execution: approval policy/status only. No desktop action was executed.",
        ]
    )


def format_desktop_approval_levels() -> str:
    return "\n".join(
        [
            "Desktop Approval Levels",
            "",
            "The approval model does not unlock real desktop execution.",
            "",
            "Levels:",
            *_bullets(tuple(level.value for level in DesktopApprovalLevel)),
            "",
            "Meaning:",
            "- none_status_only: status output only",
            "- preview_required: future preview gate only",
            "- explicit_confirmation_required: future exact confirmation plus target verification",
            "- elevated_confirmation_required: future elevated confirmation plus audit and rollback/repair policy",
            "- repeated_confirmation_required: future repeated confirmation for very sensitive actions",
            "- forbidden_no_approval_available: no approval path",
            "",
            "Execution: approval-level explanation only. Real desktop control is locked.",
        ]
    )


def format_desktop_approval_model_preview(request: str) -> str:
    preview = preview_desktop_approval_request(request)
    return "\n".join(
        [
            "Desktop Approval Preview",
            "",
            f"Request: {preview.request}",
            f"Risk level: {preview.risk_level}",
            f"Approval level: {preview.decision.approval_level.value}",
            f"State: {preview.decision.state.value}",
            f"Future gate only: {'yes' if preview.future_gate_only else 'no'}",
            f"Execution unlocked: {'yes' if preview.decision.execution_unlocked else 'no'}",
            "The approval model does not unlock real desktop execution.",
            "",
            "Confirmation phrase preview:",
            f"- {preview.decision.confirmation_phrase.preview_phrase}",
            "",
            "Reason:",
            preview.decision.reason,
            "",
            "Execution: approval preview only. No desktop action was executed.",
        ]
    )


def format_desktop_confirmation_phrase(request: str) -> str:
    phrase = preview_desktop_confirmation_phrase(request)
    return "\n".join(
        [
            "Desktop Confirmation Phrase Preview",
            "",
            f"Phrase type: {phrase.phrase_type.value}",
            f"Preview phrase: {phrase.preview_phrase}",
            f"Unlocks execution: {'yes' if phrase.unlocks_execution else 'no'}",
            "The confirmation phrase does not unlock real desktop execution.",
            "",
            "Note:",
            phrase.note,
            "",
            "Execution: confirmation phrase preview only. No desktop action was executed.",
        ]
    )


def format_desktop_forbidden_actions() -> str:
    classes = list_desktop_forbidden_action_classes()
    lines = [
        "Desktop Forbidden Actions",
        "",
        "Forbidden action classes:",
    ]
    lines.extend(f"- {item.action_class}: {item.reason} Approval available: {'yes' if item.approval_available else 'no'}." for item in classes)
    lines.extend(["", "The approval model does not unlock forbidden desktop execution.", "Execution: forbidden-action policy only. No desktop action was executed."])
    return "\n".join(lines)


def format_desktop_approval_audit_status() -> str:
    audit = get_desktop_approval_audit_status()
    return "\n".join(
        [
            "Desktop Approval Audit Status",
            "",
            f"Status: {audit.status}",
            f"Records: {audit.records_count}",
            f"Storage enabled: {'yes' if audit.storage_enabled else 'no'}",
            "Schema fields:",
            *_bullets(audit.schema_fields),
            "",
            audit.summary,
            "Execution: audit schema/status only. No approval record was created and no desktop action was executed.",
        ]
    )


def format_desktop_approval_model_readiness() -> str:
    policy = get_desktop_approval_policy()
    return "\n".join(
        [
            "Desktop Approval Readiness",
            "",
            "Status: not ready to unlock desktop actions.",
            "The approval model does not unlock real desktop execution.",
            "",
            "Readiness gaps:",
            "- no real screen/window/app observation",
            "- no verified UI target model",
            "- no approval session storage for real desktop actions",
            "- no action execution, verification, repair, or rollback gate",
            "- no audit trail connected to real desktop execution",
            "",
            f"Forbidden classes tracked: {len(policy.forbidden_classes)}",
            "Next phase: DesktopAgent Locked Readiness Proof",
            "Execution: readiness status only. No desktop action was executed.",
        ]
    )


def format_desktop_session_status() -> str:
    readiness = get_desktop_observation_readiness()
    latest = get_latest_preview_session()
    lines = [
        "Desktop Session Preview status",
        "",
        "Status: preview only.",
        "Real desktop observation: locked.",
        "Real screen observation: locked.",
        "Real desktop control: locked.",
        f"Preview records: {'available' if readiness.ready_for_preview_records else 'unavailable'}",
        f"Real observation ready: {'yes' if readiness.ready_for_real_observation else 'no'}",
        f"Real control ready: {'yes' if readiness.ready_for_real_control else 'no'}",
        "",
        "Latest preview session:",
    ]
    if latest:
        lines.extend(_format_session_summary(latest))
    else:
        lines.append("- none yet; use `eva desktop session preview` to create a preview-only record.")
    lines.extend(
        [
            "",
            "Allowed now:",
            *_bullets(readiness.allowed_now),
            "",
            "Blocked now:",
            *_bullets(planned_session_preview().blocked_now),
            "",
            "Execution: session status only. No screen was captured, no windows were enumerated, no active app was detected, and no desktop action was executed.",
        ]
    )
    return "\n".join(lines)


def format_desktop_sessions() -> str:
    sessions = list_preview_sessions()
    lines = [
        "Desktop Session Preview records",
        "",
        "Mode: preview/status only.",
        "Real desktop observation: locked.",
        "Real desktop control: locked.",
        "",
    ]
    if not sessions:
        lines.append("No preview desktop sessions have been created in this Eva process yet.")
    else:
        for session in sessions:
            lines.extend(_format_session_summary(session))
    lines.extend(["", "Execution: list preview records only. No screen, window, app, mouse, keyboard, clipboard, terminal, package, or cloud action was executed."])
    return "\n".join(lines)


def format_desktop_session_preview(label: str = "Desktop session preview") -> str:
    session = create_preview_session(label)
    lines = [
        "Desktop Session Preview created",
        "",
        "This is a preview-only session record.",
        "Real desktop observation: locked.",
        "Real desktop control: locked.",
        "",
    ]
    lines.extend(_format_session_summary(session))
    lines.extend(
        [
            "",
            "Allowed now:",
            *_bullets(session.allowed_now),
            "",
            "Blocked now:",
            *_bullets(session.blocked_now),
            "",
            "Execution: preview record only. No screen was captured, no windows were enumerated, no app was inspected, launched, or controlled.",
        ]
    )
    return "\n".join(lines)


def format_desktop_session_latest() -> str:
    latest = get_latest_preview_session()
    lines = [
        "Latest Desktop Session Preview",
        "",
        "Real desktop observation: locked.",
        "Real desktop control: locked.",
        "",
    ]
    if latest:
        lines.extend(_format_session_summary(latest))
    else:
        lines.append("No preview desktop session exists yet. Use `eva desktop session preview` to create a preview-only record.")
    lines.extend(["", "Execution: latest preview status only. No screen, window, app, or desktop action was executed."])
    return "\n".join(lines)


def format_desktop_session_plan() -> str:
    session = planned_session_preview()
    lines = [
        "Desktop Session Preview plan",
        "",
        "Current mode: preview/status only.",
        "Real desktop observation: locked.",
        "Real desktop control: locked.",
        "",
        "Future lifecycle:",
    ]
    lines.extend(f"- {note}" for note in session.notes)
    lines.extend(
        [
            "",
            "Allowed now:",
            *_bullets(session.allowed_now),
            "",
            "Still blocked:",
            *_bullets(session.blocked_now),
            "",
            "Next phase: Screen Observation Policy.",
            "Execution: lifecycle plan only. No screen, window, app, mouse, keyboard, clipboard, terminal, package, browser, desktop automation, MCP, PyAutoGUI, Playwright, or cloud action was executed.",
        ]
    )
    return "\n".join(lines)


def format_desktop_app_status_preview() -> str:
    preview = create_app_status_preview()
    lines = [
        "Desktop App Status Preview",
        "",
        f"Mode: {preview.mode}.",
        "Real app inspection: locked.",
        "Real desktop observation: locked.",
        "Real desktop control: locked.",
        "",
        "Future schema fields:",
        *_bullets(preview.schema_fields),
        "",
        "Blocked fields:",
        *_bullets(preview.blocked_fields),
        "",
        "Notes:",
        *_bullets(preview.notes),
        "",
        "Execution: schema preview only. No real app, process, window, screen, file, browser session, secret, token, password, cookie, or private state was inspected.",
    ]
    return "\n".join(lines)


def format_desktop_window_status_preview() -> str:
    preview = create_window_status_preview()
    lines = [
        "Desktop Window Status Preview",
        "",
        f"Mode: {preview.mode}.",
        "Real window enumeration: locked.",
        "Real desktop observation: locked.",
        "Real desktop control: locked.",
        "",
        "Future schema fields:",
        *_bullets(preview.schema_fields),
        "",
        "Blocked fields:",
        *_bullets(preview.blocked_fields),
        "",
        "Notes:",
        *_bullets(preview.notes),
        "",
        "Execution: schema preview only. No real windows, titles, bounds, screen pixels, screenshot, app, or private desktop state were inspected.",
    ]
    return "\n".join(lines)


def format_desktop_active_context_preview() -> str:
    preview = create_active_context_preview()
    lines = [
        "Desktop Active Context Preview",
        "",
        f"Mode: {preview.mode}.",
        "Real active app detection: locked.",
        "Real desktop observation: locked.",
        "Real desktop control: locked.",
        "",
        "Future schema fields:",
        *_bullets(preview.schema_fields),
        "",
        "Blocked fields:",
        *_bullets(preview.blocked_fields),
        "",
        "Notes:",
        *_bullets(preview.notes),
        "",
        "Execution: active context schema preview only. No real active app, window, screen, screenshot, clipboard, file, secret, token, password, cookie, or private state was detected or read.",
    ]
    return "\n".join(lines)


def format_desktop_observation_readiness() -> str:
    readiness = get_desktop_observation_readiness()
    lines = [
        "Desktop Observation readiness",
        "",
        f"Status: {readiness.status}.",
        "Real desktop observation: locked.",
        "Real screen observation: locked.",
        "Real desktop control: locked.",
        "Screen capture: locked.",
        "Window/app inspection: locked.",
        "",
        "Ready now:",
        *_bullets(readiness.allowed_now),
        "",
        "Readiness gaps:",
        *_bullets(readiness.gaps),
        "",
        f"Next phase: {readiness.next_phase}",
        "Execution: readiness preview only. No screen capture, screenshot, window enumeration, app inspection, active app detection, app launch, mouse, keyboard, clipboard, file dialog, terminal, package, browser, desktop automation, PyAutoGUI, Playwright, MCP, or cloud action was executed.",
    ]
    return "\n".join(lines)


def format_desktop_screen_policy() -> str:
    policy = get_desktop_screen_policy()
    lines = [
        "Desktop Screen Observation Policy",
        "",
        "DesktopAgent mode: screen policy/status only.",
        f"Mode: {policy.mode}.",
        "Real screen observation: locked.",
        "Real desktop control: locked.",
        "Screen capture: locked.",
        "Screenshots: locked.",
        f"OCR: {'allowed' if policy.ocr_allowed else 'locked'}",
        f"Image analysis: {'allowed' if policy.image_analysis_allowed else 'locked'}",
        f"Cloud screen sharing: {'allowed' if policy.cloud_screen_sharing_allowed else 'locked'}",
        "",
        "Allowed now:",
        *_bullets(policy.allowed_now),
        "",
        "Blocked now:",
        *_bullets(policy.blocked_now),
        "",
        "Future requirements:",
        *_bullets(policy.future_requirements),
        "",
        "Execution: policy preview only. No screen capture, screenshot, OCR, image analysis, window/app inspection, active app detection, mouse, keyboard, clipboard, file dialog, terminal, package, MCP, PyAutoGUI, Playwright, browser, desktop, or cloud action was executed.",
    ]
    return "\n".join(lines)


def format_desktop_screen_observation_policy() -> str:
    preview = create_screen_observation_preview()
    policy = get_desktop_screen_policy()
    lines = [
        "Desktop Screen Observation Policy",
        "",
        "Status: policy/design only.",
        "Real screen observation: locked.",
        "Real desktop control: locked.",
        f"Preview mode: {preview.mode}.",
        f"Real capture performed: {'yes' if preview.real_capture_performed else 'no'}",
        "",
        "Future observation schema fields:",
        *_bullets(preview.schema_fields),
        "",
        "Never included now:",
        *_bullets(preview.blocked_fields),
        "",
        "Sensitive screen categories:",
        *_bullets(policy.sensitive_categories),
        "",
        "Notes:",
        *_bullets(preview.notes),
        "",
        "Execution: observation policy only. No screen, screenshot, OCR, image, window, app, active context, clipboard, file, secret, token, password, cookie, browser session, or private state was read.",
    ]
    return "\n".join(lines)


def format_desktop_sensitive_screens() -> str:
    categories = list_sensitive_screen_categories()
    lines = [
        "Desktop Sensitive Screens",
        "",
        "Mode: category policy preview only.",
        "Real screen observation: locked.",
        "",
        "Sensitive categories:",
    ]
    lines.extend(f"- {item.value}: requires future override or explicit approval before any observation." for item in categories)
    lines.extend(
        [
            "",
            "Execution: sensitive-screen policy only. No screen capture, screenshot, OCR, window/app inspection, active app detection, or desktop action was executed.",
        ]
    )
    return "\n".join(lines)


def format_desktop_screen_redaction_policy() -> str:
    rules = get_desktop_screen_redaction_rules()
    lines = [
        "Desktop Screen Redaction Policy",
        "",
        "Mode: local policy preview only.",
        "Real screen observation: locked.",
        "",
        "Redaction rules:",
    ]
    lines.extend(f"- {rule.name}: replace with {rule.replacement}. {rule.note}" for rule in rules)
    lines.extend(
        [
            "",
            "Execution: redaction policy only. No screen, screenshot, OCR, image analysis, window/app inspection, token, password, cookie, browser session, or private data was read.",
        ]
    )
    return "\n".join(lines)


def format_desktop_screen_capture_gate() -> str:
    gate = get_desktop_screen_capture_gate()
    lines = [
        "Desktop Screen Capture Gate",
        "",
        f"Status: {gate.status}.",
        f"Capture allowed now: {'yes' if gate.capture_allowed_now else 'no'}",
        f"Exact user command required in future: {'yes' if gate.exact_user_command_required else 'no'}",
        f"Confirmation required in future: {'yes' if gate.confirmation_required else 'no'}",
        f"Sensitive-screen override required in future: {'yes' if gate.override_required_for_sensitive_screens else 'no'}",
        "Real screen observation: locked.",
        "Screen capture: locked.",
        "Screenshots: locked.",
        "",
        "Blocked now:",
        *_bullets(gate.blocked_now),
        "",
        "Future gate requirements:",
        *_bullets(gate.future_requirements),
        "",
        gate.summary,
        "Execution: capture gate policy only. No screen capture, screenshot, OCR, image analysis, window/app inspection, desktop control, or cloud action was executed.",
    ]
    return "\n".join(lines)


def format_desktop_screen_readiness() -> str:
    readiness = get_desktop_screen_observation_readiness()
    lines = [
        "Desktop Screen Observation Readiness",
        "",
        f"Status: {readiness.status}.",
        f"Policy preview ready: {'yes' if readiness.ready_for_policy_preview else 'no'}",
        f"Real capture ready: {'yes' if readiness.ready_for_real_capture else 'no'}",
        f"Redacted observation ready: {'yes' if readiness.ready_for_redacted_observation else 'no'}",
        "Real screen observation: locked.",
        "Screen capture: locked.",
        "Screenshots: locked.",
        "",
        "Ready now:",
        *_bullets(readiness.allowed_now),
        "",
        "Readiness gaps:",
        *_bullets(readiness.gaps),
        "",
        f"Next phase: {readiness.next_phase}",
        "Execution: readiness policy only. No screen capture, screenshot, OCR, image analysis, window/app inspection, active app detection, desktop control, or cloud action was executed.",
    ]
    return "\n".join(lines)


def format_desktop_observation_policy() -> str:
    decision = evaluate_screen_observation_safety("screen observation")
    return "\n".join(
        [
            format_desktop_screen_policy(),
            "",
            "Observation safety decision:",
            f"- Decision: {decision.decision}",
            f"- Allowed now: {'yes' if decision.allowed_now else 'no'}",
            f"- Reason: {decision.reason}",
            f"- Future gate: {decision.required_future_gate}",
            f"- Safe alternative: {decision.safe_alternative}",
        ]
    )


def _bullets(items: tuple[str, ...]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- {item}" for item in items]


def _format_session_summary(session: DesktopSessionPreview) -> list[str]:
    return [
        f"- ID: {session.session_id}",
        f"- Label: {session.label}",
        f"- Mode: {session.mode}",
        f"- Status: {session.status}",
        f"- App/window policy: {session.app_window_policy_summary}",
        f"- Updated: {session.updated_at}",
    ]


def _phase14_common_lines() -> list[str]:
    from .phase14_final import get_desktop_phase14_proof

    proof = get_desktop_phase14_proof()
    return [
        proof.summary,
        "Phase 14 is safety/readiness only.",
        "Real desktop observation is not enabled.",
        "Real desktop control is not enabled.",
        "Approvals do not unlock execution.",
        proof.future_gate,
        "Phase 12L narrow real create remains a gated write path.",
        proof.phase12_boundary,
        "No desktop, browser, network, shell, package, MCP, PyAutoGUI, Playwright, or cloud action was executed.",
    ]


def format_desktop_phase14_status() -> str:
    from .phase14_final import get_desktop_phase14_proof

    proof = get_desktop_phase14_proof()
    return "\n".join([
        "Desktop Phase 14 Status", "", f"Status: {proof.status}", *_phase14_common_lines(), "",
        f"Next phase: {proof.next_phase}",
        "Execution: status/proof only. No desktop action was executed.",
    ])


def format_desktop_phase14_summary() -> str:
    from .phase14_final import get_desktop_phase14_proof

    proof = get_desktop_phase14_proof()
    lines = ["Desktop Phase 14 Summary", "", *_phase14_common_lines(), "", "Completed layers:"]
    lines.extend(f"- {layer.name}: {layer.proof}" for layer in proof.completed_layers)
    lines.extend(["", f"Next phase: {proof.next_phase}", "Execution: summary/proof only. No desktop action was executed."])
    return "\n".join(lines)


def format_desktop_phase14_limits() -> str:
    from .phase14_final import get_desktop_phase14_proof

    proof = get_desktop_phase14_proof()
    lines = ["Desktop Phase 14 Limits", "", *_phase14_common_lines(), "", "Still locked:"]
    lines.extend(f"- {limit.name}: {limit.reason}" for limit in proof.limits)
    lines.extend(["", "Execution: limits/proof only. No desktop action was executed."])
    return "\n".join(lines)


def format_desktop_phase14_ready() -> str:
    from .phase14_final import get_desktop_phase14_proof

    proof = get_desktop_phase14_proof()
    return "\n".join([
        "Desktop Phase 14 Ready Check", "", "Phase 14 is complete as a locked safety/readiness foundation.",
        *_phase14_common_lines(), "", "Ready now:", "- status and proof commands", "- preview-only policy, session, screen, action, risk, and approval surfaces", "- Control Center and planner/capability metadata", "",
        "Not ready now:", "- real desktop observation", "- real desktop control", "- screen/window/app inspection, UI targeting, mouse, keyboard, clipboard, app launch, file dialog, terminal, package, browser, desktop automation, MCP, PyAutoGUI, Playwright, or cloud execution", "",
        f"Next phase: {proof.next_phase}", "Execution: readiness/proof only. No desktop action was executed.",
    ])


def format_desktop_phase14_final_proof() -> str:
    from .phase14_final import get_desktop_phase14_proof

    proof = get_desktop_phase14_proof()
    lines = ["Desktop Phase 14 Final Proof", "", f"Phase: {proof.phase}", f"Status: {proof.status}", *_phase14_common_lines(), "", "Completed proof layers:"]
    lines.extend(f"- {layer.name}: {layer.proof}" for layer in proof.completed_layers)
    lines.extend(["", "Locked execution proof:", *_bullets(proof.locked_execution), "", "Must exist before any future real desktop gate:"])
    lines.extend(f"- {item}" for item in proof.future_gate.split("; "))
    lines.extend(["", f"Next phase: {proof.next_phase}", "Execution: final proof/status only. No desktop action was executed."])
    return "\n".join(lines)


def format_desktop_readiness_proof() -> str:
    from .readiness_proof import build_desktop_readiness_proof

    proof = build_desktop_readiness_proof()
    lines = ["Desktop Locked Readiness Proof", "", f"Status: {proof.status.value}", proof.summary, "Real desktop observation is not enabled.", "Real desktop control is not enabled.", "Approvals do not unlock execution.", "", "Safety checks:"]
    lines.extend(f"- {check.name}: {check.status}; {check.evidence}" for check in proof.checks)
    lines.extend(["", proof.phase12_boundary, "No desktop action was executed."])
    return "\n".join(lines)


def format_desktop_locked_status() -> str:
    from .readiness_proof import get_locked_desktop_capability_summary

    summary = get_locked_desktop_capability_summary()
    return "\n".join([
        "DesktopAgent Locked Status", "", "Phase 14 locked safety/readiness foundation.", summary.summary, "Real desktop observation is not enabled.", "Real desktop control is not enabled.", "Approvals do not unlock execution.", "", "Locked now:", *_bullets(summary.locked_actions), "", "Phase 12L narrow real create remains a gated write path.", "No desktop action was executed.",
    ])


def format_desktop_readiness_gaps() -> str:
    from .readiness_proof import get_desktop_readiness_gaps

    lines = ["DesktopAgent Readiness Gaps", "", "Phase 14 locked safety/readiness foundation.", "Real desktop observation is not enabled.", "Real desktop control is not enabled.", "Approvals do not unlock execution.", "", "What is missing:"]
    lines.extend(f"- {gap.name}: {gap.reason} Required: {gap.required_before_enablement}" for gap in get_desktop_readiness_gaps())
    lines.extend(["", "Phase 12L narrow real create remains a gated write path.", "No desktop action was executed."])
    return "\n".join(lines)
