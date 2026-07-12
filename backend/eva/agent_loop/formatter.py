from __future__ import annotations

from .loop_policy import BLOCKED_ACTION_TYPES, ALLOWED_PREVIEW_ACTION_TYPES, loop_policy_text
from .runner import run_agent_loop_preview
from .status import get_agent_loop_status
from .step_limiter import get_step_limit_policy, step_limit_policy_text


def _boundary() -> list[str]:
    return [
        "No live LLM call was made.",
        "Agent loop is local/mock preview only.",
        "Actions are preview-only.",
        "Tools are not executed.",
        "Secrets/config/session data are blocked.",
        "Browser/desktop/shell/cloud/MCP execution remains locked.",
    ]


def format_agent_loop_status() -> str:
    status = get_agent_loop_status()
    return "\n".join(
        [
            "Agent Loop v1 status",
            *_boundary(),
            f"Status: {status.status}.",
            f"Provider SDKs enabled: {status.provider_sdks_enabled}.",
            f"Arbitrary file reads enabled: {status.arbitrary_file_reads_enabled}.",
            f"New write paths enabled: {status.new_write_paths_enabled}.",
            f"Next phase: {status.next_phase}.",
        ]
    )


def format_agent_loop_policy() -> str:
    return loop_policy_text()


def format_agent_loop_run_preview(request: str = "run agent loop preview") -> str:
    return run_agent_loop_preview(request).format()


def format_agent_loop_steps() -> str:
    policy = get_step_limit_policy()
    lines = [
        "Agent Loop v1 stages and step limits",
        *_boundary(),
        "Stages:",
        "1. receive request",
        "2. classify route intent",
        "3. assemble safe context preview",
        "4. run threat-defense preview",
        "5. create bounded plan preview",
        "6. create action previews only",
        "7. create mock observations only",
        "8. verify plan/action safety",
        "9. produce final status/report",
        "10. stop safely",
        f"Default max steps: {policy.default_max_steps}.",
        f"Hard max steps: {policy.hard_max_steps}.",
        "Step limits, runaway detection, repeated-step detection, and no-progress stop behavior are enforced.",
    ]
    return "\n".join(lines)


def format_agent_loop_action_previews() -> str:
    lines = [
        "Agent Loop v1 action preview model",
        *_boundary(),
        "Allowed preview action types:",
    ]
    lines.extend(f"- {item}" for item in ALLOWED_PREVIEW_ACTION_TYPES)
    lines.append("Blocked action types:")
    lines.extend(f"- {item}" for item in BLOCKED_ACTION_TYPES)
    lines.append("Every action preview uses execution status: preview_only.")
    return "\n".join(lines)


def format_agent_loop_safety_report(request: str = "run agent loop preview") -> str:
    state = run_agent_loop_preview(request)
    return "\n".join(
        [
            "Agent Loop v1 safety report",
            *_boundary(),
            f"Final status: {state.final_status}.",
            f"Stop reason: {state.stop_reason}.",
            f"Blocked actions: {len(state.blocked_actions)}.",
            "Verification/finalizer behavior: previews are checked for no live LLM calls, no tool execution, blocked secrets, and locked execution surfaces.",
            state.format(),
        ]
    )


def format_agent_loop_stop_reasons() -> str:
    return "\n".join(
        [
            "Agent Loop v1 stop reasons",
            *_boundary(),
            step_limit_policy_text(),
            "Stop reasons: completed_preview, step_limit_exceeded, repeated_step_detected, no_progress_detected.",
            "Repeated/no-progress loops stop safely with a human-readable report.",
        ]
    )


def format_agent_loop_readiness() -> str:
    return "\n".join(
        [
            "Agent Loop v1 readiness",
            *_boundary(),
            "Ready for local deterministic preview/status/report use.",
            "Not connected to live LLM/API/provider calls.",
            "No provider SDKs are used.",
            "No .env, .env.local, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read.",
            "Arbitrary file reads are blocked.",
            "All actions are preview-only; agent loop cannot execute tools.",
            "Phase 12L narrow approved new .md/.txt creation remains a gated write path.",
            "Next phase: Phase 19 Agentic Workflow Planner.",
        ]
    )
