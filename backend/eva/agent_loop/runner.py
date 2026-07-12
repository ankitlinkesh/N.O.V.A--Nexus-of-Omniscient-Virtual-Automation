from __future__ import annotations

from .action_preview import blocked_action_preview, make_action_preview
from .context_bridge import build_context_summary
from .finalizer import final_status_for_state
from .models import ActionPreview, AgentLoopState
from .observation import make_mock_observations
from .planner_bridge import preview_plan_steps, select_loop_capabilities
from .state import make_loop_id, summarize_request
from .step_limiter import clamp_step_limit
from .threat_bridge import build_threat_summary
from .verifier import verify_action_previews


def run_agent_loop_preview(request: str = "run agent loop preview", *, max_steps: int | None = None) -> AgentLoopState:
    summary = summarize_request(request)
    limit = clamp_step_limit(max_steps)
    selected = select_loop_capabilities(request)
    context_packet, context_summary = build_context_summary(request)
    threat_report, threat_summary, threat_blocked = build_threat_summary(context_packet, source_type="context_packet")
    request_threat_report, request_threat_summary, request_blocked = build_threat_summary(request, source_type="user_request")
    blocked = request_blocked or _requests_blocked_surface(request)
    blocked_reason = _blocked_reason(request, request_threat_summary, threat_summary)
    stop_reason = _stop_reason(request, limit)
    planned_steps = preview_plan_steps(request, selected, blocked=blocked)
    step_count = min(len(planned_steps), limit)
    if stop_reason == "completed_preview" and len(planned_steps) > limit:
        stop_reason = "step_limit_exceeded"
    final_status = final_status_for_state(blocked, stop_reason)
    actions = _build_actions(selected, blocked=blocked, reason=blocked_reason, request=str(request or ""))
    observations = make_mock_observations(context_summary=context_summary, threat_summary=request_threat_summary, selected_capabilities=selected)
    verification_notes = verify_action_previews(actions, blocked=blocked)
    blocked_actions = tuple(action for action in actions if action.blocked_reason)
    return AgentLoopState(
        loop_id=make_loop_id(request),
        request_summary=summary,
        current_stage="final_status_report",
        step_count=step_count,
        max_step_limit=limit,
        selected_capabilities=selected,
        context_packet_summary=context_summary,
        threat_scan_summary=request_threat_summary,
        planned_preview_steps=planned_steps[:limit],
        action_previews=actions,
        mock_observations=observations,
        verification_notes=verification_notes,
        blocked_actions=blocked_actions,
        final_status=final_status,
        stop_reason=stop_reason,
        no_live_llm_call_statement="No live LLM call was made.",
        no_tool_execution_statement="Tools are not executed.",
        safety_notes=(
            "Agent loop is local/mock preview only.",
            "Actions are preview-only.",
            "Secrets/config/session data are blocked.",
            "Browser/desktop/shell/cloud/MCP execution remains locked.",
            "Phase 12L narrow approved new .md/.txt creation remains a gated write path.",
            f"Context threat preview: {threat_summary}",
            f"Request threat preview: {request_threat_report.blocked}; findings={len(request_threat_report.findings)}.",
        ),
    )


def _build_actions(selected: tuple[str, ...], *, blocked: bool, reason: str, request: str) -> tuple[ActionPreview, ...]:
    actions: list[ActionPreview] = [
        make_action_preview(1, "status_check_preview", "agent_loop.status"),
        make_action_preview(2, "context_assembly_preview", "context.assemble_preview"),
        make_action_preview(3, "threat_scan_preview", "threat.scan_preview", risk_level="medium" if blocked else "low", blocked_reason=reason if _looks_injected(request) else ""),
        make_action_preview(4, "validation_preview", "llm.validation_status"),
        make_action_preview(5, "planner_preview", selected[0] if selected else "agent_loop.run_preview"),
    ]
    if blocked:
        actions.append(blocked_action_preview(6, selected[0] if selected else "agent_loop.run_preview", reason))
    else:
        actions.append(make_action_preview(6, "final_response_preview", "agent_loop.run_preview"))
    return tuple(actions)


def _looks_injected(request: str) -> bool:
    text = str(request or "").lower()
    return any(term in text for term in ("ignore previous", "disregard", "system:", "developer:"))


def _requests_blocked_surface(request: str) -> bool:
    text = str(request or "").lower()
    blocked_terms = (
        ".env",
        "api key",
        "token",
        "cookie",
        "password",
        "session",
        "secret",
        "powershell",
        "terminal",
        "command",
        "install",
        "browser",
        "desktop",
        "click",
        "tool",
        "execute",
        "super_execute",
        "credential",
        "raw runtime",
    )
    return any(term in text for term in blocked_terms)


def _blocked_reason(request: str, request_threat_summary: str, context_threat_summary: str) -> str:
    text = str(request or "").lower()
    if any(term in text for term in (".env", "api key", "token", "cookie", "password", "session", "secret", "credential")):
        return "Secrets/config/session data are blocked."
    if any(term in text for term in ("browser", "desktop", "powershell", "terminal", "command", "install", "tool", "execute", "click")):
        return "Browser/desktop/shell/cloud/MCP execution remains locked; tools are not executed."
    if "." in text and "agent_loop." in text:
        return "Unknown or hallucinated capability was rejected."
    if "blocked=true" in request_threat_summary.lower() or "blocked=true" in context_threat_summary.lower():
        return "Threat-defense preview blocked unsafe or injected content."
    return ""


def _stop_reason(request: str, limit: int) -> str:
    text = str(request or "").lower()
    if "repeat same step" in text or "repeat" in text:
        return "repeated_step_detected"
    if "without progress" in text or "no progress" in text or "wait and continue" in text:
        return "no_progress_detected"
    if limit < 4 or "very long plan" in text:
        return "step_limit_exceeded"
    return "completed_preview"
