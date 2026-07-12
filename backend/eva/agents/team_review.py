from __future__ import annotations

from dataclasses import asdict, field
from typing import Any

from ..planner.models import EvaTaskPlan
from ..planner.critique import detect_missing_information
from ..schemas.modeling import schema_dataclass
from .delegation import dry_run_plan_with_agents
from .quality import AgentCoverageReport, evaluate_plan_agent_coverage


@schema_dataclass
class AgentReviewFinding:
    reviewer: str
    severity: str
    step_id: str | None
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    model_dump = as_dict


@schema_dataclass
class AgentTeamReview:
    plan_id: str
    user_goal: str
    selected_agents: list[str]
    coverage: AgentCoverageReport
    findings: list[AgentReviewFinding] = field(default_factory=list)
    blocked_steps: list[str] = field(default_factory=list)
    confirmation_checkpoints: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    recommended_next_action: str = "Review the dry-run output. No task was executed."

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    model_dump = as_dict


def review_plan_with_agent_team(plan: EvaTaskPlan) -> AgentTeamReview:
    dry_run = dry_run_plan_with_agents(plan, include_quality=False)
    coverage = evaluate_plan_agent_coverage(plan, dry_run.responses)
    selected_agents = sorted({response.agent_name for response in dry_run.responses})
    findings: list[AgentReviewFinding] = []
    blocked_steps: list[str] = []
    confirmation_checkpoints: list[str] = []

    findings.append(
        AgentReviewFinding(
            reviewer="PlannerAgent",
            severity="info",
            step_id=None,
            message=f"Plan has {len(plan.steps)} preview step(s); no execution is enabled.",
        )
    )

    for step in plan.steps:
        if step.permission_status in {"blocked", "override_required"} or step.risk_level == "high":
            blocked_steps.append(step.step_id)
            findings.append(
                AgentReviewFinding(
                    reviewer="SafetyAgent",
                    severity="blocker" if step.permission_status == "blocked" else "warning",
                    step_id=step.step_id,
                    message="Risky step is blocked or override-gated in this phase.",
                )
            )
        elif step.permission_status == "confirmation_required":
            confirmation_checkpoints.append(step.step_id)
            findings.append(
                AgentReviewFinding(
                    reviewer="SafetyAgent",
                    severity="warning",
                    step_id=step.step_id,
                    message="External-visible or guarded action requires explicit confirmation.",
                )
            )

        specialist = _specialist_reviewer_for_step(step.capability_id, step.step_type)
        if specialist:
            findings.append(
                AgentReviewFinding(
                    reviewer=specialist,
                    severity="info",
                    step_id=step.step_id,
                    message=_specialist_message(specialist),
                )
            )

    if coverage.blockers:
        findings.append(
            AgentReviewFinding(
                reviewer="SupervisorAgent",
                severity="blocker",
                step_id=None,
                message="One or more agent assignments need review before any future executor phase.",
            )
        )
    elif coverage.warnings:
        findings.append(
            AgentReviewFinding(
                reviewer="SupervisorAgent",
                severity="warning",
                step_id=None,
                message="Plan is usable as a dry run, with low-confidence assignments noted.",
            )
        )
    else:
        findings.append(
            AgentReviewFinding(
                reviewer="SupervisorAgent",
                severity="info",
                step_id=None,
                message="Agent coverage is acceptable for a dry-run review.",
            )
        )

    missing_information = detect_missing_information(plan.user_goal or plan.normalized_goal, plan)
    recommended = _recommended_action(plan, coverage, blocked_steps, confirmation_checkpoints)
    return AgentTeamReview(
        plan_id=plan.plan_id,
        user_goal=plan.user_goal or plan.normalized_goal,
        selected_agents=selected_agents,
        coverage=coverage,
        findings=findings,
        blocked_steps=blocked_steps,
        confirmation_checkpoints=confirmation_checkpoints,
        missing_information=missing_information,
        recommended_next_action=recommended,
    )


def format_agent_team_review(review: AgentTeamReview) -> str:
    lines = [
        "Agent team review",
        "",
        f"Goal: {review.user_goal}",
        f"Selected agents: {', '.join(review.selected_agents) if review.selected_agents else 'none'}",
        f"Coverage score: {review.coverage.coverage_score:.2f}",
        f"Risk: {review.coverage.risk_score}",
        "",
        "Findings:",
    ]
    for finding in review.findings[:12]:
        step = f" ({finding.step_id})" if finding.step_id else ""
        lines.append(f"- {finding.reviewer}{step}: {finding.severity}; {finding.message}")
    if review.blocked_steps:
        lines.extend(["", "Blocked or override-gated steps:"])
        lines.extend(f"- {step_id}" for step_id in review.blocked_steps)
    if review.confirmation_checkpoints:
        lines.extend(["", "Confirmation checkpoints:"])
        lines.extend(f"- {step_id}" for step_id in review.confirmation_checkpoints)
    if review.missing_information:
        lines.extend(["", "Missing information:"])
        lines.extend(f"- {item}" for item in review.missing_information[:6])
    lines.extend(["", "Recommendation:", review.recommended_next_action])
    lines.extend(["", "Execution: no task was executed. This is an agent-team dry-run review only."])
    return "\n".join(lines)


def format_team_review(goal_text: str) -> str:
    from ..planner.decomposer import create_task_plan
    from ..control_center.status import format_locked_features_text, format_next_safe_step_text
    from ..work_sessions.formatter import format_work_sessions_status
    from ..skills.project_inspection import format_project_next_step
    from ..skills.reality_check import format_reality_check
    from ..skills.selector import select_skills_for_request, select_workflow_for_request
    from ..skills.workflow_state import classify_next_fileagent_step, format_workflow_next_step, summarize_fileagent_workflow_state
    from ..specialists.selector import select_specialists_for_request

    review = format_agent_team_review(review_plan_with_agent_team(create_task_plan(goal_text)))
    specialists = select_specialists_for_request(goal_text)
    skills = select_skills_for_request(goal_text)
    workflow = select_workflow_for_request(goal_text)
    state = summarize_fileagent_workflow_state()
    next_step = classify_next_fileagent_step(goal_text)
    route_lines = [
        "",
        "Specialist workflow route:",
        f"- Specialists: {', '.join(item.id for item in specialists[:5]) if specialists else 'none'}",
        f"- Skills: {', '.join(item.id for item in skills[:5]) if skills else 'none'}",
        f"- Workflow: {workflow.id if workflow else 'none'}",
        f"- Workflow state: pending {state.pending_approval_count}; approved {state.approved_for_future_apply_count}; ambiguity {state.ambiguity_status}",
        f"- Latest evidence: sandbox {state.latest_sandbox_apply.status}; real create {state.latest_real_create.status}; rollback {state.latest_rollback_available.status}",
        f"- Exact next safe step: {next_step.title}",
        "",
        format_workflow_next_step(next_step),
        "",
        "Project/reality route:",
        "- Interpreted request: read-only project/reality review when applicable.",
        "- Authority decision: status/proof/next-step surfaces only; no verifier or executor was run.",
        "- Routed specialist: reality_checker, evidence_collector, test_results_analyzer, safety_reviewer, or codebase_onboarding_specialist depending on the request.",
        "- Project next-step preview:",
        format_project_next_step().splitlines()[4] if len(format_project_next_step().splitlines()) > 4 else "Review current project status.",
        "- Reality-check preview:",
        format_reality_check().splitlines()[4] if len(format_reality_check().splitlines()) > 4 else "Fresh verifier evidence is required before completion claims.",
        "",
        "Control Center/status route:",
        "- Interpreted request: dashboard/status lookup when applicable.",
        "- Authority decision: read-only status; no subprocess verifier, browser, desktop, shell, MCP, package, cloud, or tool execution.",
        "- Locked-feature explanations: existing edits, source edits, browser/desktop, shell, MCP, CodingAgent, BrowserAgent, and News Dashboard remain locked or planned.",
        "- Locked preview:",
        format_locked_features_text().splitlines()[2] if len(format_locked_features_text().splitlines()) > 2 else "Locked features stay status-only.",
        "- Next safe step preview:",
        format_next_safe_step_text().splitlines()[4] if len(format_next_safe_step_text().splitlines()) > 4 else "Review Control Center status.",
        "- Execution: route review only; no workflow step was executed.",
        "",
        "LLM Router contract route:",
        "- Interpreted request: LLM router status, provider contracts, routing/fallback policy, limits, structured-output rules, or mock route preview.",
        "- Authority decision: proof/status only; live LLM/API/network calls and tool execution are locked.",
        "- Routed specialist: PlannerAgent with SafetyAgent boundary review.",
        "- Degraded mode: mock/status only. No secret/config read or provider SDK is used by Phase 15A.",
        "- Execution: LLM Router contract route only; no provider or tool was called.",
        "- Phase 15B: fallback, degraded-mode, limits, routing-audit, and failure behavior is deterministic mock/dry-run only; no provider SDK, secret/config read, LLM-output tool execution, browser, or desktop action is enabled.",
        "- Phase 15C: structured-output validation is mock/local only; invalid LLM output cannot execute tools; live LLM calls remain locked; repair does not execute or rewrite user intent.",
        "- Phase 15C boundary: browser/desktop execution remains locked. Phase 12L narrow real create remains a gated write path.",
        "- Phase 15D: tests are local/mock only; unsafe LLM-like outputs cannot execute tools; live LLM/API calls and secret/config/session reads remain locked.",
        "- Phase 15D boundary: browser/desktop execution remains locked; Phase 12L narrow real create remains a gated write path; Phase 16 Context Assembly Engine is next.",
        "- Phase 16: context assembly is local/mock only; no live LLM/API calls are made; secrets/config/session reads remain blocked; arbitrary file reads remain blocked.",
        "- Phase 16 boundary: assembled context cannot execute tools; prompt-injection-like context is treated as untrusted data; browser/desktop execution remains locked; Phase 12L narrow real create remains a gated write path.",
        "- Phase 16 next: Phase 17 LLM Threat Defense + Prompt Injection Guard is next.",
        "- Phase 17: threat defense is local/mock only; no live LLM/API calls are made; secrets/config/session reads remain blocked; arbitrary file reads remain blocked.",
        "- Phase 17 boundary: untrusted context cannot override trusted instruction hierarchy; defended context cannot execute tools; browser/desktop execution remains locked; Phase 12L narrow real create remains a gated write path.",
        "- Phase 17 next: Phase 18 Agent Loop v1 is next.",
        "- Phase 18: Agent Loop v1 is local/mock only; no live LLM/API calls are made; actions are preview-only; tools are not executed.",
        "- Phase 18 boundary: secrets/config/session reads remain blocked; arbitrary file reads remain blocked; browser/desktop execution remains locked; repeated/no-progress loops stop safely.",
        "- Phase 18 next: Phase 19 Agentic Workflow Planner is next.",
        "- Phase 19: Workflow Planner v1 is local/mock only; no live LLM/API calls are made; workflow steps are preview-only; tools are not executed.",
        "- Phase 19 boundary: secrets/config/session reads remain blocked; arbitrary file reads/writes remain blocked; browser/desktop execution remains locked; dependency cycles and unsupported workflows fail safely.",
        "- Phase 19 next: Phase 20 Controlled Execution Gates is next.",
        "- Phase 20: Controlled Execution Gates are local/mock policy preview only; no live LLM/API calls are made; tools are not executed.",
        "- Phase 20 approval boundary: approval alone does not execute; confirmation alone does not execute unless an existing implemented gate accepts it.",
        "- Phase 20 safety boundary: secrets/config/session reads remain blocked; arbitrary file reads/writes remain blocked; browser/desktop/shell/cloud/MCP execution remains locked.",
        "- Phase 20 write boundary: Phase 12L narrow real-create remains a gated write path.",
        "- Phase 20 next: Phase 21 Memory v3 is next.",
        "- Phase 21: Memory v3 is local-only; no live LLM/API calls are made; no cloud memory is used.",
        "- Phase 21 policy boundary: memory cannot override safety policy; memory cannot execute tools.",
        "- Phase 21 privacy boundary: secrets/config/session data remain blocked; raw memory DB dumps remain blocked; arbitrary file reads/writes remain blocked.",
        "- Phase 21 execution boundary: browser/desktop execution remains locked; Phase 12L narrow real-create remains a gated file write path.",
        "- Phase 21 next: Phase 22 Voice Assistant is next.",
        "- Phase 22: Voice Assistant Foundation is local/mock preview only; no microphone access happens; no audio playback happens; no live ASR/TTS happens.",
        "- Phase 22 call boundary: no live LLM/API calls are made; voice commands cannot execute tools.",
        "- Phase 22 privacy boundary: secrets/config/session reads remain blocked; arbitrary file reads/writes remain blocked.",
        "- Phase 22 execution boundary: browser/desktop execution remains locked; Phase 12L narrow real-create remains a gated file write path.",
        "- Phase 22 next: Phase 23 AI OS / Control Center Upgrade is next.",
        "- Phase 23: AI OS / Control Center Upgrade is local/status only; no live LLM/API calls are made.",
        "- Phase 23 dashboard boundary: dashboard output does not execute tools; preview-only features remain preview-only; locked future gates remain locked.",
        "- Phase 23 privacy boundary: secrets/config/session reads remain blocked; arbitrary file reads/writes remain blocked.",
        "- Phase 23 execution boundary: browser/desktop execution remains locked; Phase 12L narrow real-create remains a gated file write path.",
        "- Phase 23 next: Phase 24 Real Browser Read-Only Mode is next.",
        "- Phase 24: Real Browser Read-Only Mode is public-URL read-only observation only.",
        "- Phase 24 action boundary: no clicking/typing/forms/downloads/uploads happen.",
        "- Phase 24 session boundary: no cookies/sessions/browser profiles are accessed; logged-in browser access remains blocked.",
        "- Phase 24 control boundary: browser control remains locked; tools are not executed.",
        "- Phase 24 privacy boundary: secrets/config/session reads remain blocked; arbitrary file reads/writes remain blocked.",
        "- Phase 24 execution boundary: desktop execution remains locked; Phase 12L narrow real-create remains a gated file write path.",
        "- Phase 24 next: Phase 25 Real Desktop Observation Mode is next.",
        "- Phase 25: Real Desktop Observation Mode is observation-only.",
        "- Phase 25 action boundary: no clicking/typing/hotkeys happen.",
        "- Phase 25 control boundary: no app/window control happens.",
        "- Phase 25 monitoring boundary: no continuous monitoring happens.",
        "- Phase 25 capture boundary: no screenshot files are saved.",
        "- Phase 25 sensitive-screen boundary: sensitive screens are classified/redacted/blocked.",
        "- Phase 25 tool boundary: desktop observations cannot execute tools.",
        "- Phase 25 privacy boundary: secrets/config/session reads remain blocked; arbitrary file reads/writes remain blocked.",
        "- Phase 25 execution boundary: browser control remains locked; desktop control remains locked.",
        "- Phase 25 write boundary: Phase 12L narrow real-create remains a gated file write path.",
        "- Phase 25 next: Phase 26 Real Desktop Control Gate is next.",
        "- Phase 26: Real Desktop Control Gate is local/mock dry-run only.",
        "- Phase 26 control boundary: real desktop control is not enabled.",
        "- Phase 26 action boundary: no clicking/typing/hotkeys happen.",
        "- Phase 26 clipboard boundary: no clipboard access happens.",
        "- Phase 26 app/window boundary: no app/window control happens.",
        "- Phase 26 approval boundary: approval alone does not execute.",
        "- Phase 26 confirmation boundary: confirmation alone does not execute.",
        "- Phase 26 privacy boundary: secrets/config/session reads remain blocked; arbitrary file reads/writes remain blocked.",
        "- Phase 26 browser boundary: browser control remains locked.",
        "- Phase 26 observation boundary: desktop observation remains observation-only.",
        "- Phase 26 write boundary: Phase 12L narrow real-create remains a gated file write path.",
        "- Phase 26 next: Phase 27 News/Web Intelligence Dashboard is next.",
        "- Phase 27: News/Web Intelligence Dashboard is dashboard/report/status only.",
        "- Phase 27 crawler boundary: no unrestricted crawling happens.",
        "- Phase 27 privacy boundary: no login/session/cookie/profile access happens.",
        "- Phase 27 control boundary: no browser control happens; no tool execution happens.",
        "- Phase 27 call boundary: no live LLM/API calls are made.",
        "- Phase 27 file boundary: arbitrary file reads/writes remain blocked.",
        "- Phase 27 evidence: source freshness/reliability/uncertainty are reported.",
        "- Phase 27 write boundary: Phase 12L narrow real-create remains a gated file write path.",
        "- Phase 27 next: Phase 28 Coding Specialist / CodingAgent is next.",
        "- Phase 28: Coding Specialist / CodingAgent Foundation is preview/report/status only.",
        "- Phase 28 source boundary: no source-code edits happen; no patches are applied.",
        "- Phase 28 execution boundary: no shell/test/package/git execution happens; no tool execution happens.",
        "- Phase 28 call boundary: no live LLM/API calls are made.",
        "- Phase 28 file boundary: no arbitrary file reads/writes happen.",
        "- Phase 28 privacy boundary: no secret/config/session reads happen.",
        "- Phase 28 control boundary: browser/desktop/cloud/MCP execution remains locked.",
        "- Phase 28 write boundary: Phase 12L narrow real-create remains a gated file write path.",
        "- Phase 28 next: Phase 29 Public Demo / Release is next.",
        "- Phase 29: Public Demo / Release is documentation/report/status/profile only.",
        "- Phase 29 publication boundary: no publishing happens; no commit/tag/push happens.",
        "- Phase 29 source boundary: no source-code edits happen through CodingAgent.",
        "- Phase 29 control boundary: no browser/desktop control happens.",
        "- Phase 29 execution boundary: no shell/test/package/git execution happens; no tool execution happens.",
        "- Phase 29 call boundary: no live LLM/API calls are made.",
        "- Phase 29 file boundary: no arbitrary file reads/writes happen.",
        "- Phase 29 privacy boundary: no secret/config/session reads happen.",
        "- Phase 29 write boundary: Phase 12L narrow real-create remains a gated file write path.",
        "- Phase 30: Release Candidate Hardening is report/status/planning only.",
        "- Phase 30 commit boundary: commit plan is text only; no git commit/add/tag/push happens.",
        "- Phase 30 publication boundary: no publishing happens.",
        "- Phase 30 source boundary: no source-code edits happen through CodingAgent.",
        "- Phase 30 control boundary: no browser/desktop control happens.",
        "- Phase 30 execution boundary: no shell/test/package/git execution happens through Eva.",
        "- Phase 30 tool boundary: no tool execution happens.",
        "- Phase 30 call boundary: no live LLM/API calls are made.",
        "- Phase 30 file boundary: no arbitrary file reads/writes happen.",
        "- Phase 30 privacy boundary: no secret/config/session reads happen.",
        "- Phase 30 write boundary: Phase 12L narrow real-create remains a gated file write path.",
        "- Phase 30 next safe step: user-approved commit execution outside Eva or a separate explicit commit-approval phase.",
        "",
        "WorkSession/audit route:",
        "- Interpreted request: local session/timeline lookup when applicable.",
        "- Authority decision: read-only audit/status; no verifier subprocess, browser, desktop, shell, MCP, package, cloud, or tool execution.",
        "- Routed specialist: ControlCenterAgent with SafetyAgent review for blocked-action visibility.",
        "- Latest session preview:",
        format_work_sessions_status().splitlines()[4] if len(format_work_sessions_status().splitlines()) > 4 else "No work sessions recorded yet.",
        "- Execution: audit route review only; no workflow step was executed.",
        "",
        "Phase 12 readiness route:",
        "- Interpreted request: Phase 12 checkpoint readiness, summary, limits, or proof lookup.",
        "- Authority decision: read-only status/proof surface; no verifier subprocess, browser, desktop, shell, MCP, package, cloud, message, or file action.",
        "- Routed specialist: VerifierAgent with SafetyAgent boundary review.",
        "- Boundary: Phase 12L narrow real create remains a gated write path; broad/source/existing-file edits stay locked.",
        "- Execution: readiness route review only; no verifier command was run.",
        "",
        "BrowserAgent safety route:",
        "- Interpreted request: BrowserAgent status, policy, domain policy, readiness, or action-safety preview.",
        "- Authority decision: status/safety only; no browser launch, navigation, click, type, submit, login, upload, download, cookie/localStorage/profile read, screenshot, Playwright, MCP, PyAutoGUI, shell, package, cloud, or desktop action.",
        "- Routed specialist: BrowserAgent with SafetyAgent boundary review.",
        "- Real browser control: locked.",
        "- Execution: BrowserAgent route review only; no browser action was executed.",
        "",
        "BrowserAgent session preview route:",
        "- Interpreted request: browser session status, preview record, latest session, lifecycle plan, or readiness lookup.",
        "- Authority decision: preview/status only; no browser launch, URL opening, navigation, screenshot, DOM read, click, type, submit, login, upload, download, cookie/localStorage/profile/session/password read, Playwright, MCP, PyAutoGUI, shell, package, cloud, or desktop action.",
        "- Routed specialist: BrowserAgent with SafetyAgent boundary review.",
        "- Real browser control: locked.",
        "- Execution: session preview route only; no browser action was executed.",
        "",
        "BrowserAgent observation preview route:",
        "- Interpreted request: page summary policy, page summary preview, DOM summary policy, text extraction policy, observation readiness, or redaction policy.",
        "- Authority decision: preview/status only; no browser launch, URL opening, navigation, screenshot, DOM read, live page extraction, click, type, submit, login, upload, download, cookie/localStorage/profile/session/password read, Playwright, MCP, PyAutoGUI, shell, package, cloud, or desktop action.",
        "- Routed specialist: BrowserAgent with SafetyAgent privacy/redaction review.",
        "- Live browser observation: locked.",
        "- Execution: observation design route only; no browser or page data was read.",
        "",
        "BrowserAgent action dry-run route:",
        "- Interpreted request: browser action dry-run, action plan preview, risk lookup, approval requirements, dry-run policy, or action readiness.",
        "- Authority decision: dry-run/status only; no browser launch, navigation, screenshot, DOM read, live page extraction, click, type, submit, login, upload, download, cookie/localStorage/profile/session/password read, Playwright, MCP, PyAutoGUI, shell, package, cloud, or desktop action.",
        "- Routed specialist: BrowserAgent with SafetyAgent risk/approval review.",
        "- Real browser execution: locked.",
        "- Execution: action dry-run route only; no browser action was executed.",
        "",
        "BrowserAgent domain risk route:",
        "- Interpreted request: domain check, site risk, sensitive-site category, domain approval, or domain readiness lookup.",
        "- Authority decision: policy/status only; no DNS, network, browser launch, navigation, page fetch, screenshot, DOM read, click, type, submit, login, upload, download, cookie/localStorage/profile/session/password read, Playwright, browser-use, Stagehand, Maxun, MCP, PyAutoGUI, shell, package, cloud, or desktop action.",
        "- Routed specialist: BrowserAgent with SafetyAgent domain/category review.",
        "- Real browser access: locked.",
        "- Execution: domain risk route only; no browser or network action was executed.",
        "",
        "BrowserAgent read-only readiness proof route:",
        "- Interpreted request: browser read-only readiness, safety proof, locked status, readiness gaps, or Phase 13 proof.",
        "- Authority decision: proof/status only; no browser launch, navigation, DNS/network call, live page fetch/read, screenshot, DOM access, click, type, submit, login, upload, download, cookie/localStorage/profile/session/password/token read, Playwright, browser-use, Stagehand, Maxun, MCP, PyAutoGUI, shell, package, cloud, or desktop action.",
        "- Routed specialist: BrowserAgent with SafetyAgent proof review.",
        "- Real browser read-only mode: Phase 24 public-URL observation/report only; safe backend unavailable and mock fixture ready.",
        "- Execution: readiness proof route only; no browser action was executed.",
        "",
        "BrowserAgent Phase 13 hardening route:",
        "- Interpreted request: final Phase 13 status, summary, limits, ready check, or final proof.",
        "- Authority decision: proof/status only; Phase 13 remains the historical safety foundation for the Phase 24 read-only gate.",
        "- Routed specialist: BrowserAgent with SafetyAgent final proof review.",
        "- Real browser control is not enabled; network/DNS/live page read/DOM/screenshot/action execution are locked.",
        "- Phase 24 supplies the separate public-URL read-only gate; Phase 12L narrow real create remains a gated write path.",
        "- Execution: Phase 13 hardening route only; no browser, network, page, DOM, screenshot, shell, package, MCP, PyAutoGUI, desktop, or cloud action was executed.",
        "",
        "DesktopAgent Phase 14 readiness proof route:",
        "- Interpreted request: final Phase 14 status, summary, limits, ready check, final proof, locked status, or readiness gaps.",
        "- Authority decision: proof/status only; approvals do not unlock real desktop execution.",
        "- Routed specialist: DesktopAgent with SafetyAgent final proof review.",
        "- Phase 14 remains the historical locked safety foundation. Phase 25 separately permits observation-only output; real desktop control is not enabled.",
        "- Browser/network execution remains locked; Phase 12L narrow real create remains a gated write path.",
        "- Execution: Phase 14 readiness proof route only; no desktop, browser, network, shell, package, MCP, PyAutoGUI, Playwright, or cloud action was executed.",
        "",
        "DesktopAgent session preview route:",
        "- Interpreted request: desktop session status, preview record, latest session, lifecycle plan, app/window schema preview, active context schema preview, or observation readiness lookup.",
        "- Authority decision: preview/status only; no screen capture, screenshot, real window enumeration, app inspection, active app detection, app launch, mouse, keyboard, clipboard, file dialog, terminal, package, MCP, PyAutoGUI, Playwright, browser, desktop, shell, or cloud action.",
        "- Routed specialist: DesktopAgent with SafetyAgent privacy and target-confidence review.",
        "- Real desktop observation: locked.",
        "- Real desktop control: locked.",
        "- Execution: session preview route only; no desktop observation/control was executed.",
        "",
        "DesktopAgent screen observation policy route:",
        "- Interpreted request: screen policy, screen observation policy, sensitive-screen categories, redaction policy, capture gate, or screen readiness.",
        "- Authority decision: policy/status only; no screen capture, screenshot, OCR, image analysis, window/app inspection, active app detection, mouse, keyboard, clipboard, file dialog, terminal, package, MCP, PyAutoGUI, Playwright, browser, desktop, shell, or cloud action.",
        "- Routed specialist: DesktopAgent with SafetyAgent privacy/redaction review.",
        "- Real screen observation: locked.",
        "- Real desktop control: locked.",
        "- Execution: screen observation policy route only; no desktop observation/control was executed.",
        "",
        "DesktopAgent action dry-run route:",
        "- Interpreted request: desktop action dry-run, action plan preview, risk lookup, approval requirements, dry-run policy, or action readiness.",
        "- Authority decision: dry-run/status only; no screen capture, screenshot, window/app inspection, app launch, mouse movement, clicking, dragging, keyboard typing, hotkeys, clipboard access, file dialog automation, terminal/package execution, MCP, PyAutoGUI, Playwright, browser, desktop, shell, network, or cloud action.",
        "- Routed specialist: DesktopAgent with SafetyAgent target-confidence and approval review.",
        "- Real desktop observation: locked.",
        "- Real desktop control: locked.",
        "- Execution: action dry-run route only; no desktop action was executed.",
        "",
        "DesktopAgent risk scoring route:",
        "- Interpreted request: desktop action risk score, risk factors, approval requirement, safety matrix, high-risk actions, or risk readiness.",
        "- Authority decision: risk/status only; no screen capture, screenshot, window/app inspection, active app detection, app launch, mouse movement, clicking, dragging, keyboard typing, hotkeys, clipboard access, file dialog automation, terminal/package execution, MCP, PyAutoGUI, Playwright, browser, desktop, shell, network, or cloud action.",
        "- Routed specialist: DesktopAgent with SafetyAgent approval-level review.",
        "- Real desktop observation: locked.",
        "- Real desktop control: locked.",
        "- Execution: risk scoring route only; no desktop action was executed.",
        "",
        "DesktopAgent human approval route:",
        "- Interpreted request: desktop approval policy, approval levels, approval preview, confirmation phrase preview, forbidden actions, audit status, or approval readiness.",
        "- Authority decision: approval-policy/status only; approvals and phrases do not unlock real desktop execution.",
        "- Routed specialist: DesktopAgent with SafetyAgent authority and forbidden-action review.",
        "- Real desktop observation: locked.",
        "- Real desktop control: locked.",
        "- Execution: human approval route only; no desktop action was executed.",
        "",
        "DesktopAgent safety route:",
        "- Interpreted request: desktop status, policy, blocked action list, action safety preview, app risk, or readiness.",
        "- Authority decision: safety/status only; no screen capture, screenshot, window/app inspection, app launch, mouse, keyboard, clipboard, file dialog, terminal, package, MCP, PyAutoGUI, Playwright, browser, desktop, shell, or cloud action.",
        "- Routed specialist: DesktopAgent with SafetyAgent risk review.",
        "- Real screen observation: locked.",
        "- Real desktop control: locked.",
        "- Execution: DesktopAgent safety route only; no desktop observation/control was executed.",
    ]
    return review + "\n" + "\n".join(route_lines)


def _specialist_reviewer_for_step(capability_id: str | None, step_type: str) -> str | None:
    text = f"{capability_id or ''} {step_type}".lower()
    if "research_memory" in text or "retrieve_memory" in text:
        return "ResearchAgent"
    if "browser" in text or "chrome" in text:
        return "BrowserAgent"
    if "desktop" in text or "screen" in text:
        return "DesktopAgent"
    if "control_center" in text or "dashboard" in text or "locked_features" in text or "enabled_features" in text or "next_safe_step" in text or "work_session" in text or "audit_timeline" in text:
        return "ControlCenterAgent"
    if "project_reality" in text or "project_inspect" in text or "done_check" in text or "project_next" in text or "project_proof" in text:
        return "RealityCheckerAgent"
    if "eva.smoke" in text or "eva.verify" in text or "phase12" in text or "ux_status" in text:
        return "VerifierAgent"
    if "golden_workflow" in text or "eva.golden" in text:
        return "FileAgent"
    if "workflow_plan" in text or "skill_selection" in text or "specialist_selection" in text or "eva.workflow" in text or "eva.skill" in text or "eva.specialist" in text:
        return "PlannerAgent"
    if "file." in text or "project_structure" in text or "project_understanding" in text or step_type in {"file_inspect", "file_search", "file_preview", "file_understanding", "project_inventory", "file_draft_preview", "file_apply_readiness", "file_approval", "file_sandbox_apply", "file_real_create"}:
        return "FileAgent"
    if "eva.ask" in text or "natural_request" in text or "authority_decision" in text or "authority" in text:
        return "SafetyAgent"
    if "file.delete" in text or "whatsapp" in text or "email" in text:
        return "SafetyAgent"
    if "eva_v2" in text or "planning" in text or "draft" in text:
        return "PlannerAgent"
    if "verification" in text:
        return "SupervisorAgent"
    return None


def _specialist_message(reviewer: str) -> str:
    if reviewer == "ResearchAgent":
        return "Local Research Memory can be previewed through existing read-only delegates."
    if reviewer == "BrowserAgent":
        return "Phase 24 permits validated public-URL observation/report output only; no Chrome session or page control is executed."
    if reviewer == "DesktopAgent":
        return "Phase 25 permits explicit one-shot redacted desktop observation/report output only; no UI control is executed."
    if reviewer == "FileAgent":
        return "File work remains repo-scoped; heuristic understanding, inventory, draft previews, golden workflows, apply-readiness reviews, approval-ledger metadata, sandbox-only apply tests, and the Phase 12L narrow real apply gate are guarded. Real create needs exact confirmation, high-risk AuthorityDecision review, and only brand-new .md/.txt files directly under docs/ or samples/ are allowed; broad editing, overwrite, source/config writes, secrets, and runtime data are refused."
    if reviewer == "ControlCenterAgent":
        return "Control Center review checks read-only dashboard/status routing, local URL output, and locked future-module boundaries. It does not open a browser or execute tools."
    if reviewer == "VerifierAgent":
        return "Verifier review suggests quick/full local verification commands and status surfaces only. It does not execute shell commands, perform dependency setup, or enable feature execution."
    if reviewer == "RealityCheckerAgent":
        return "Project/reality review uses local status and verifier surfaces only; it does not claim completion without fresh proof."
    if reviewer == "SafetyAgent":
        return "Safety review checks the authority decision, keeps risky actions blocked, and preserves sandbox-only or preview-only boundaries."
    if reviewer == "PlannerAgent":
        return "Planner review checks structure, missing information, and preview-only scope."
    return "Supervisor review represents verification until a dedicated verifier agent exists."


def _recommended_action(
    plan: EvaTaskPlan,
    coverage: AgentCoverageReport,
    blocked_steps: list[str],
    confirmation_checkpoints: list[str],
) -> str:
    if blocked_steps:
        return "Do not execute this plan. Keep it as a dry-run preview until a future permission-gated executor phase."
    if confirmation_checkpoints:
        return "Use this as a draft-only plan; any future external-visible action must ask for exact confirmation."
    if coverage.coverage_score >= 0.75:
        return "Safe to use as a dry-run guide or read-only delegate preview where existing explicit commands allow it."
    return "Review low-confidence assignments before relying on this plan."
