from __future__ import annotations

from .action_dry_run import BLOCKED_BROWSER_EXECUTION, create_browser_action_dry_run, create_browser_action_plan_preview, get_browser_action_approval_requirements
from .action_safety import evaluate_browser_action_safety, list_blocked_browser_actions
from .domain_policy import get_default_domain_policy
from .domain_rules import evaluate_domain_policy, get_domain_policy_result, get_domain_rules, get_sensitive_action_markers
from .observation_policy import evaluate_observation_safety, get_browser_observation_policy, get_browser_redaction_rules
from .page_summary import create_extraction_preview, create_mock_page_summary_preview, create_mock_text_summary_preview, create_schema_dom_summary_preview
from .phase13_final import build_browser_phase13_final_proof
from .policy import get_browser_session_policy
from .readiness import get_browser_session_readiness
from .readiness_proof import build_browser_readiness_proof, get_browser_readiness_gaps, get_locked_browser_execution_summary
from .risk import evaluate_browser_action_risk
from .session import BrowserSessionPreview, create_preview_session, planned_session_preview
from .session_registry import get_latest_preview_session, list_preview_sessions
from .site_risk import classify_site_risk
from .status import get_browser_agent_status


def format_browser_status() -> str:
    status = get_browser_agent_status()
    lines = [
        "BrowserAgent status",
        "",
        f"Phase: {status.phase}",
        f"Status: {status.status}",
        "Real browser control: locked",
        "Execution enabled: no",
        "",
        "Allowed now:",
    ]
    lines.extend(f"- {item}" for item in status.allowed_now)
    lines.extend(
        [
            "",
            "Blocked now:",
            "- launching browser, navigating real pages, clicking, typing, submitting forms",
            "- login, payments, file uploads/downloads, external sends",
            "- cookie, localStorage, password, session, and browser profile reads",
            "- screenshots, screen watching, Playwright/browser-use/Stagehand/Maxun execution, MCP, PyAutoGUI, shell, package, and cloud calls",
            "",
            f"Next phase: {status.next_phase}",
            "Execution: status only. No real browser control was enabled or attempted.",
        ]
    )
    return "\n".join(lines)


def format_browser_policy() -> str:
    policy = get_browser_session_policy()
    return "\n".join(
        [
            "BrowserAgent policy",
            "",
            "Current mode: safety model only.",
            f"Real browser control: {'enabled' if policy.real_browser_control_enabled else 'locked'}",
            f"Launch browser: {'allowed' if policy.launch_browser_allowed else 'blocked'}",
            f"Navigate real pages: {'allowed' if policy.navigate_allowed else 'blocked'}",
            f"Click: {'allowed' if policy.click_allowed else 'blocked'}",
            f"Type: {'allowed' if policy.type_allowed else 'blocked'}",
            f"Submit forms: {'allowed' if policy.submit_allowed else 'blocked'}",
            f"Screenshots: {'allowed' if policy.screenshot_allowed else 'blocked'}",
            f"Always-on screen watching: {'allowed' if policy.screen_watch_allowed else 'blocked'}",
            "",
            "Allowed now:",
            *_bullets(policy.allowed_status_actions),
            "",
            "Automation backends:",
            "- none enabled; Playwright, browser-use, Stagehand, Maxun, MCP, and PyAutoGUI stay locked.",
            "",
            "Execution: policy preview only. No browser, page, session, profile, cookie, localStorage, password, or token data was read.",
        ]
    )


def format_browser_blocked_actions() -> str:
    lines = ["BrowserAgent blocked actions", ""]
    for item in list_blocked_browser_actions():
        lines.append(f"- {item.action}: {item.reason}")
    lines.extend(
        [
            "",
            "Reason:",
            "Phase 13A defines the safety model first. Real browser control needs future domain policy, observation limits, human confirmation gates, and verification.",
            "Real browser control: locked.",
            "",
            "Execution: blocked-action summary only. No browser action was executed.",
        ]
    )
    return "\n".join(lines)


def format_browser_domain_policy() -> str:
    policy = get_default_domain_policy()
    lines = [
        "BrowserAgent domain policy",
        "",
        f"Policy: {policy.policy_name}",
        f"Default domain mode: {policy.default_domain_mode}",
        f"Public page preview: {'allowed' if policy.public_page_preview_allowed else 'blocked'}",
        f"Private page preview: {'allowed' if policy.private_page_preview_allowed else 'blocked'}",
        f"Logged-in page preview: {'allowed' if policy.logged_in_page_preview_allowed else 'blocked'}",
        f"Cookie access: {'allowed' if policy.cookies_allowed else 'blocked'}",
        f"localStorage access: {'allowed' if policy.local_storage_allowed else 'blocked'}",
        f"Profile access: {'allowed' if policy.profile_access_allowed else 'blocked'}",
        f"Password/session reads: {'allowed' if policy.passwords_allowed else 'blocked'}",
        "",
        "Notes:",
    ]
    lines.extend(f"- {item}" for item in policy.notes)
    lines.extend(["", "Real browser control: locked.", "Execution: domain policy preview only. No page or browser state was read."])
    return "\n".join(lines)


def format_browser_action_safety(action: str) -> str:
    decision = evaluate_browser_action_safety(action)
    allowed = "yes" if decision.allowed_now else "no"
    return "\n".join(
        [
            "BrowserAgent action safety",
            "",
            f"Action: {decision.action}",
            f"Category: {decision.category.value}",
            f"Decision: {decision.decision}",
            f"Allowed now: {allowed}",
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
            "Execution: action safety preview only. No real browser control was attempted.",
        ]
    )


def format_browser_readiness() -> str:
    readiness = get_browser_session_readiness()
    return "\n".join(
        [
            "BrowserAgent readiness",
            "",
            "Status: not ready for real browser control.",
            f"Session preview: {readiness.status}.",
            "Ready now: policy/readiness/action safety previews.",
            "Real browser control: locked.",
            "",
            "Missing before execution:",
            *_bullets(readiness.gaps),
            "",
            "Phase 12L boundary still stands: a gated write path is approved new .md/.txt creation under docs/ or samples/.",
            "Execution: readiness status only. No browser action was executed.",
        ]
    )


def format_browser_session_status() -> str:
    readiness = get_browser_session_readiness()
    latest = get_latest_preview_session()
    lines = [
        "Browser Session Preview status",
        "",
        "Status: preview only.",
        "Real browser control: locked.",
        f"Preview records: {'available' if readiness.ready_for_preview_records else 'unavailable'}",
        f"Read-only mode ready: {'yes' if readiness.ready_for_readonly_mode else 'no'}",
        f"Real control ready: {'yes' if readiness.ready_for_real_browser_control else 'no'}",
        "",
        "Latest preview session:",
    ]
    if latest:
        lines.extend(_format_session_summary(latest))
    else:
        lines.append("- none yet; use `eva browser session preview` to create a preview-only record.")
    lines.extend(
        [
            "",
            "Allowed now:",
            *_bullets(readiness.allowed_now),
            "",
            "Blocked now:",
            *_bullets(planned_session_preview().blocked_now),
            "",
            "Execution: session status only. No browser was launched, navigated, observed, or controlled.",
        ]
    )
    return "\n".join(lines)


def format_browser_sessions() -> str:
    sessions = list_preview_sessions()
    lines = [
        "Browser Session Preview records",
        "",
        "Mode: preview/status only.",
        "Real browser control: locked.",
        "",
    ]
    if not sessions:
        lines.append("No preview browser sessions have been created in this Eva process yet.")
    else:
        for session in sessions:
            lines.extend(_format_session_summary(session))
    lines.extend(["", "Execution: list preview records only. No browser action was executed."])
    return "\n".join(lines)


def format_browser_session_preview(label: str = "Browser session preview") -> str:
    session = create_preview_session(label)
    lines = [
        "Browser Session Preview created",
        "",
        "This is a preview-only session record.",
        "Real browser control: locked.",
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
            "Execution: preview record only. No browser was launched, navigated, observed, or controlled.",
        ]
    )
    return "\n".join(lines)


def format_browser_session_latest() -> str:
    latest = get_latest_preview_session()
    lines = [
        "Latest Browser Session Preview",
        "",
        "Real browser control: locked.",
        "",
    ]
    if latest:
        lines.extend(_format_session_summary(latest))
    else:
        lines.append("No preview browser session exists yet. Use `eva browser session preview` to create a preview-only record.")
    lines.extend(["", "Execution: latest preview status only. No browser action was executed."])
    return "\n".join(lines)


def format_browser_session_plan() -> str:
    session = planned_session_preview()
    lines = [
        "Browser Session Preview plan",
        "",
        "Current mode: preview/status only.",
        "Real browser control: locked.",
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
            "Execution: lifecycle plan only. No browser was launched, navigated, observed, or controlled.",
        ]
    )
    return "\n".join(lines)


def format_browser_page_summary_policy() -> str:
    policy = get_browser_observation_policy()
    lines = [
        "Browser Page Summary policy",
        "",
        "Mode: design preview only.",
        "Live browser observation is locked.",
        f"Live page reads: {'allowed' if policy.live_page_reads_allowed else 'locked'}",
        f"Browser launch: {'allowed' if policy.browser_launch_allowed else 'locked'}",
        f"Screenshots: {'allowed' if policy.screenshots_allowed else 'locked'}",
        "",
        "Allowed now:",
        *_bullets(policy.allowed_now),
        "",
        "Blocked now:",
        *_bullets(policy.blocked_now),
        "",
        "Future read-only requirements:",
        *_bullets(policy.future_requirements),
        "",
        "Execution: policy preview only. No live page, browser, screenshot, DOM, cookie, localStorage, profile, password, session, or token data was read.",
    ]
    return "\n".join(lines)


def format_browser_page_summary_preview() -> str:
    preview = create_mock_page_summary_preview("Browser summary design", "User-provided mock text can become a short page summary with sections and redaction notes.")
    extraction = create_extraction_preview()
    lines = [
        "Browser Page Summary preview",
        "",
        "Mode: mock-text preview only.",
        "Live browser observation is locked.",
        f"Title: {preview.title}",
        f"Source: {preview.source}",
        f"Live page read: {'yes' if preview.live_page_read else 'no'}",
        f"Summary: {preview.summary}",
        "",
        "Possible output fields:",
        *_bullets(extraction.output_fields),
        "",
        "Sections:",
        *_bullets(preview.sections),
        "",
        "Notes:",
        *_bullets(preview.notes),
        "",
        "Execution: preview from user-provided mock text only. No live webpage was opened or read.",
    ]
    return "\n".join(lines)


def format_browser_dom_summary_policy() -> str:
    dom = create_schema_dom_summary_preview()
    decision = evaluate_observation_safety("dom_read")
    lines = [
        "Browser DOM Summary policy",
        "",
        "Mode: schema design only.",
        "Live browser observation is locked.",
        f"DOM access now: {decision.decision}",
        f"Live DOM read: {'yes' if dom.live_dom_read else 'no'}",
        "",
        "Future summary fields:",
        *_bullets(dom.schema_fields),
        "",
        "Never included:",
        *_bullets(dom.blocked_fields),
        "",
        "Notes:",
        *_bullets(dom.notes),
        "",
        "Execution: DOM policy preview only. No DOM, page, browser, screenshot, cookie, localStorage, session, profile, password, or token data was read.",
    ]
    return "\n".join(lines)


def format_browser_text_extraction_policy() -> str:
    text_preview = create_mock_text_summary_preview()
    extraction = create_extraction_preview()
    lines = [
        "Browser Text Extraction policy",
        "",
        "Mode: mock-text/schema preview only.",
        "Live browser observation is locked.",
        f"Live extraction enabled: {'yes' if extraction.live_extraction_enabled else 'no'}",
        "",
        "Allowed sources:",
        *_bullets(extraction.allowed_sources),
        "",
        "Blocked sources:",
        *_bullets(extraction.blocked_sources),
        "",
        "Mock text blocks:",
        *_bullets(text_preview.detected_blocks),
        "",
        "Execution: text extraction policy only. No live site, DOM, screenshot, or browser state was read.",
    ]
    return "\n".join(lines)


def format_browser_observation_readiness() -> str:
    policy = get_browser_observation_policy()
    lines = [
        "Browser Observation readiness",
        "",
        "Status: not ready for live browser observation.",
        "Live browser observation is locked.",
        "Page reads: locked.",
        "DOM reads: locked.",
        "Screenshots: locked.",
        "Real browser control: locked.",
        "",
        "Missing before any future read-only observation:",
        *_bullets(policy.future_requirements),
        "",
        "Still blocked:",
        *_bullets(policy.blocked_now),
        "",
        "Execution: readiness preview only. No browser observation or control was attempted.",
    ]
    return "\n".join(lines)


def format_browser_redaction_policy() -> str:
    rules = get_browser_redaction_rules()
    lines = [
        "Browser Redaction policy",
        "",
        "Mode: local policy preview only.",
        "Live browser observation is locked.",
        "",
        "Rules:",
    ]
    for rule in rules:
        lines.append(f"- {rule.name}: replace with {rule.replacement}. {rule.note}")
    lines.extend(
        [
            "",
            "Execution: redaction policy only. No live page, DOM, screenshot, browser session, cookie, localStorage, profile, password, or token data was read.",
        ]
    )
    return "\n".join(lines)


def format_browser_action_dry_run(request: str) -> str:
    dry_run = create_browser_action_dry_run(request)
    lines = [
        "Browser Action Dry-Run",
        "",
        f"Request: {dry_run.request}",
        "Mode: dry-run text only.",
        "Real browser execution is locked.",
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
            "Execution: dry-run/status only. No browser was launched, observed, navigated, clicked, typed into, or controlled.",
        ]
    )
    return "\n".join(lines)


def format_browser_action_plan(request: str) -> str:
    plan = create_browser_action_plan_preview(request)
    lines = [
        "Browser Action Plan Preview",
        "",
        f"Request: {plan.request}",
        f"Mode: {plan.mode}",
        f"Real browser execution: {plan.real_browser_execution}",
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
            "Execution: plan preview only. No browser action was executed.",
        ]
    )
    return "\n".join(lines)


def format_browser_action_risk(action: str) -> str:
    risk = evaluate_browser_action_risk(action)
    return "\n".join(
        [
            "Browser Action Risk",
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
            "Execution: risk preview only. Real browser execution is locked.",
        ]
    )


def format_browser_action_approvals() -> str:
    approvals = get_browser_action_approval_requirements()
    lines = [
        "Browser Action Approval Requirements",
        "",
        "Mode: dry-run/status only.",
        "Real browser execution is locked.",
        "",
        "Approval requirements:",
    ]
    lines.extend(f"- {item.action_type}: {item.requirement}. Status: {item.status}." for item in approvals)
    lines.extend(["", "Execution: approval policy only. No browser action was executed."])
    return "\n".join(lines)


def format_browser_dry_run_policy() -> str:
    return "\n".join(
        [
            "Browser Action Dry-Run policy",
            "",
            "Allowed now:",
            "- create dry-run plan text only",
            "- explain risks",
            "- explain required approvals",
            "- show what would be blocked",
            "- show future action lifecycle",
            "- show action plan preview from user request",
            "",
            "Blocked now:",
            *_bullets(BLOCKED_BROWSER_EXECUTION),
            "",
            "Risk levels:",
            "- low_status_only",
            "- medium_readonly_future",
            "- high_user_confirmation_required",
            "- critical_blocked",
            "- forbidden",
            "",
            "Execution: dry-run policy only. Real browser execution is locked.",
        ]
    )


def format_browser_action_readiness() -> str:
    return "\n".join(
        [
            "Browser Action Readiness",
            "",
            "Mode: dry-run readiness only.",
            "Status: not ready for real browser execution.",
            "Real browser execution is locked.",
            "",
            "Missing before execution:",
            "- live observation policy and verifier",
            "- domain and private-page gates",
            "- human confirmation for click/type/submit and external actions",
            "- download/upload safety and path policy",
            "- login/payment refusal or explicit private workflow policy",
            "- WorkSession audit and target-aware verification for browser actions",
            "",
            "Phase 12L boundary still stands: a gated write path is approved new .md/.txt creation under docs/ or samples/.",
            "Execution: readiness status only. No browser action was executed.",
        ]
    )


def format_browser_domain_check(domain_or_url: str) -> str:
    decision = evaluate_domain_policy(domain_or_url)
    return "\n".join(
        [
            "Browser Domain Check",
            "",
            f"Domain: {decision.domain}",
            f"Category: {decision.risk.category.value}",
            f"Risk level: {decision.risk.level.value}",
            f"Decision: {decision.decision}",
            "Real browser access is locked.",
            f"Allowed now: {'yes' if decision.allowed_now else 'no'}",
            f"Approval requirement: {decision.approval_requirement}",
            "",
            "Reason:",
            decision.reason,
            "",
            "Execution: policy/status only. No network, DNS, browser, page, screenshot, DOM, cookie, localStorage, session, profile, password, token, shell, package, desktop, MCP, PyAutoGUI, or cloud call was made.",
        ]
    )


def format_browser_site_risk(domain_or_url: str) -> str:
    risk = classify_site_risk(domain_or_url)
    return "\n".join(
        [
            "Browser Site Risk",
            "",
            f"Domain: {risk.domain}",
            f"Category: {risk.category.value}",
            f"Risk level: {risk.level.value}",
            f"Blocked now: {'yes' if risk.blocked_now else 'policy only'}",
            f"Approval requirement: {risk.approval_requirement}",
            "",
            "Reason:",
            risk.reason,
            "",
            "Real browser access is locked.",
            "Execution: string classification only. No network or browser access was attempted.",
        ]
    )


def format_browser_domain_rules() -> str:
    result = get_domain_policy_result()
    lines = [
        "Browser Domain Rules",
        "",
        f"Status: {result.status}",
        "Real browser access is locked.",
        "",
        "Rules:",
    ]
    lines.extend(f"- {rule.name}: {rule.decision}. {rule.note}" for rule in get_domain_rules())
    lines.extend(["", "Blocked now:", *_bullets(result.blocked_now), "", "Execution: policy/status only. No network, DNS, or browser access was attempted."])
    return "\n".join(lines)


def format_browser_sensitive_sites() -> str:
    markers = get_sensitive_action_markers()
    lines = [
        "Browser Sensitive Sites",
        "",
        "Sensitive categories:",
        "- email and messaging",
        "- banking and payment",
        "- cloud storage and file hosting",
        "- social platforms and external posting",
        "- account, government, shopping, login, and private pages",
        "",
        "Sensitive action markers:",
    ]
    lines.extend(f"- {marker.name}: {', '.join(marker.examples)}. Requirement: {marker.requirement}." for marker in markers)
    lines.extend(["", "Real browser access is locked.", "Execution: policy/status only. No live site was checked."])
    return "\n".join(lines)


def format_browser_domain_approvals() -> str:
    return "\n".join(
        [
            "Browser Domain Approval Requirements",
            "",
            "Real browser access is locked.",
            "",
            "Approval requirements:",
            "- documentation/search/developer sites: future read-only domain gate",
            "- account/email/social/cloud/file-transfer sites: future explicit user confirmation plus privacy gate",
            "- banking/payment sites: blocked for automation; future status may allow policy-only discussion",
            "- harmful/adult/illegal/malware/phishing/piracy sites: blocked",
            "",
            "Execution: approval policy only. No network, DNS, browser, or website access was attempted.",
        ]
    )


def format_browser_domain_readiness() -> str:
    return "\n".join(
        [
            "Browser Domain Readiness",
            "",
            "Status: not ready for real browser access.",
            "Real browser access is locked.",
            "",
            "Ready now:",
            "- classify domain strings only",
            "- show domain risk decisions",
            "- explain why a domain/action is allowed, risky, or blocked",
            "- show future approval requirements",
            "- show policy summary",
            "",
            "Still missing:",
            "- no DNS/network calls",
            "- no browser launch/navigation",
            "- no live website fetch/read",
            "- no screenshot, DOM, cookie, localStorage, session, profile, password, or token reads",
            "- no click/type/submit/login/payment/upload/download",
            "",
            "Execution: readiness status only. No network or browser action was executed.",
        ]
    )


def format_browser_read_only_readiness() -> str:
    proof = build_browser_readiness_proof()
    return "\n".join(
        [
            "Browser Read-Only Readiness",
            "",
            f"Status: {proof.status.value}",
            "Real browser read-only mode: not enabled",
            "Real browser control: locked",
            "",
            "Completed safety layers:",
            *_bullets(proof.completed_layers),
            "",
            "Readiness gaps:",
            *_bullets(tuple(gap.name for gap in proof.gaps)),
            "",
            proof.phase12_boundary,
            "Execution: readiness proof/status only. No browser, network, DNS, page, screenshot, DOM, cookie, localStorage, profile, session, password, token, shell, package, desktop, MCP, PyAutoGUI, or cloud action was executed.",
        ]
    )


def format_browser_readiness_proof() -> str:
    proof = build_browser_readiness_proof()
    lines = [
        "Browser Read-Only Readiness Proof",
        "",
        f"Status: {proof.status.value}",
        "Real browser read-only mode: not enabled",
        "Real browser control: locked",
        "",
        "Safety layer checklist:",
    ]
    lines.extend(f"- {check.name}: {check.status}. {check.evidence}" for check in proof.checks)
    lines.extend(
        [
            "",
            "Locked execution summary:",
            *_bullets(proof.locked_execution),
            "",
            "Future read-only gate requirements:",
            *_bullets(proof.future_requirements),
            "",
            f"Next browser phase: {proof.next_phase}",
            proof.phase12_boundary,
            "Execution: proof/status only. No network or browser observation/control was attempted.",
        ]
    )
    return "\n".join(lines)


def format_browser_safety_proof() -> str:
    proof = build_browser_readiness_proof()
    return "\n".join(
        [
            "Browser Safety Proof",
            "",
            proof.summary,
            "Real browser read-only mode is not enabled.",
            "Real browser control is locked.",
            "",
            "Proof points:",
            *_bullets(tuple(f"{check.name}: {check.status}" for check in proof.checks)),
            "",
            "Still locked:",
            *_bullets(proof.locked_execution),
            "",
            proof.phase12_boundary,
            "Execution: safety proof only. No browser, page, DOM, screenshot, network, shell, package, MCP, PyAutoGUI, desktop, or cloud action was executed.",
        ]
    )


def format_browser_readiness_gaps() -> str:
    gaps = get_browser_readiness_gaps()
    lines = [
        "Browser Readiness Gaps",
        "",
        "Real browser read-only mode is not enabled.",
        "Real browser control is locked.",
        "",
        "Gaps before future read-only mode:",
    ]
    lines.extend(f"- {gap.name}: {gap.reason} Required: {gap.required_before_readonly}" for gap in gaps)
    lines.extend(
        [
            "",
            "Phase 12L boundary still stands: a gated write path is approved new .md/.txt creation under docs/ or samples/.",
            "Execution: gaps/status only. No network or browser action was executed.",
        ]
    )
    return "\n".join(lines)


def format_browser_locked_status() -> str:
    return "\n".join(
        [
            "Browser Locked Status",
            "",
            *_phase13_final_common_lines(),
            "",
            "Locked now:",
            *_bullets(get_locked_browser_execution_summary()),
            "",
            "Allowed now: readiness proof, safety proof, readiness gaps, domain policy, dry-run plans, preview sessions, and status summaries only.",
            "Execution: locked-status summary only. No browser, network, page, DOM, screenshot, shell, package, MCP, PyAutoGUI, desktop, or cloud action was executed.",
        ]
    )


def format_browser_phase13_proof() -> str:
    proof = build_browser_readiness_proof()
    return "\n".join(
        [
            "Browser Phase 13 Proof",
            "",
            "Phase 13A: safety policy/status exists.",
            "Phase 13B: preview-only sessions exist.",
            "Phase 13C: page/text/DOM summary design exists.",
            "Phase 13D: action dry-run planning exists.",
            "Phase 13E: domain/site-risk classification exists.",
            "Phase 13F: read-only readiness proof exists.",
            "",
            f"Current proof status: {proof.status.value}",
            "Real browser read-only mode: not enabled",
            "Real browser control: locked",
            "",
            "Locked execution:",
            *_bullets(proof.locked_execution),
            "",
            proof.phase12_boundary,
            "Execution: Phase 13 proof/status only. No network, DNS, browser, page, screenshot, DOM, cookie, localStorage, profile, session, password, token, shell, package, desktop, MCP, PyAutoGUI, or cloud action was executed.",
        ]
    )


def _phase13_final_common_lines() -> list[str]:
    proof = build_browser_phase13_final_proof()
    return [
        proof.summary,
        "Phase 13 is safety/readiness only.",
        "Real browser read-only mode is not enabled.",
        "Real browser control is not enabled.",
        "network/DNS/live page read/DOM/screenshot/action execution are locked.",
        proof.future_gate,
        "Phase 12L narrow real create remains a gated write path.",
        proof.phase12_boundary,
        "No browser and no network action was executed.",
    ]


def format_browser_phase13_status() -> str:
    proof = build_browser_phase13_final_proof()
    return "\n".join(
        [
            "Browser Phase 13 Status",
            "",
            f"Status: {proof.status}",
            *_phase13_final_common_lines(),
            "",
            f"Next phase: {proof.next_phase}",
            "Execution: status/proof only. No browser, network, page, DOM, screenshot, action, shell, package, MCP, PyAutoGUI, desktop, or cloud action was executed.",
        ]
    )


def format_browser_phase13_summary() -> str:
    proof = build_browser_phase13_final_proof()
    lines = [
        "Browser Phase 13 Summary",
        "",
        *_phase13_final_common_lines(),
        "",
        "Completed layers:",
    ]
    lines.extend(f"- {layer.name}: {layer.proof}" for layer in proof.completed_layers)
    lines.extend(
        [
            "",
            f"Next phase: {proof.next_phase}",
            "Execution: summary/proof only. No browser, network, page, DOM, screenshot, action, shell, package, MCP, PyAutoGUI, desktop, or cloud action was executed.",
        ]
    )
    return "\n".join(lines)


def format_browser_phase13_limits() -> str:
    proof = build_browser_phase13_final_proof()
    lines = [
        "Browser Phase 13 Limits",
        "",
        *_phase13_final_common_lines(),
        "",
        "Still locked:",
    ]
    lines.extend(f"- {limit.name}: {limit.reason}" for limit in proof.limits)
    lines.extend(
        [
            "",
            "Never without explicit user approval: any future live browser read-only gate.",
            "Execution: limits/proof only. No browser, network, page, DOM, screenshot, action, shell, package, MCP, PyAutoGUI, desktop, or cloud action was executed.",
        ]
    )
    return "\n".join(lines)


def format_browser_phase13_ready() -> str:
    proof = build_browser_phase13_final_proof()
    return "\n".join(
        [
            "Browser Phase 13 Ready Check",
            "",
            "Phase 13 is complete as a safety/readiness foundation.",
            *_phase13_final_common_lines(),
            "",
            "Ready now:",
            "- status and proof commands",
            "- policy summaries",
            "- preview-only session, observation, action, and domain-risk surfaces",
            "- Control Center and planner/capability metadata",
            "",
            "Not ready now:",
            "- real browser read-only mode",
            "- real browser control",
            "- network/DNS/live page read/DOM/screenshot/action execution",
            "",
            f"Next phase: {proof.next_phase}",
            "Execution: readiness/proof only. No browser, network, page, DOM, screenshot, action, shell, package, MCP, PyAutoGUI, desktop, or cloud action was executed.",
        ]
    )


def format_browser_phase13_final_proof() -> str:
    proof = build_browser_phase13_final_proof()
    lines = [
        "Browser Phase 13 Final Proof",
        "",
        f"Phase: {proof.phase}",
        f"Status: {proof.status}",
        *_phase13_final_common_lines(),
        "",
        "Completed proof layers:",
    ]
    lines.extend(f"- {layer.name}: {layer.proof}" for layer in proof.completed_layers)
    lines.extend(
        [
            "",
            "Locked execution proof:",
            *_bullets(proof.locked_execution),
            "",
            "Must exist before future real browser read-only mode:",
            "- separate approved gate",
            "- explicit user command per task",
            "- domain policy gate",
            "- redaction and privacy filtering",
            "- target-aware verification",
            "- local audit evidence",
            "",
            f"Next phase: {proof.next_phase}",
            "Execution: final proof/status only. No browser, network, page, DOM, screenshot, action, shell, package, MCP, PyAutoGUI, desktop, or cloud action was executed.",
        ]
    )
    return "\n".join(lines)


def _bullets(items: tuple[str, ...]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- {item}" for item in items]


def _format_session_summary(session: BrowserSessionPreview) -> list[str]:
    return [
        f"- ID: {session.session_id}",
        f"- Label: {session.label}",
        f"- Mode: {session.mode}",
        f"- Status: {session.status}",
        f"- Domain policy: {session.domain_policy_summary}",
        f"- Updated: {session.updated_at}",
    ]
