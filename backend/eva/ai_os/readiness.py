from __future__ import annotations

from .capability_matrix import build_capability_matrix
from .models import AIOSDashboard
from .system_map import build_system_map


def build_ai_os_dashboard() -> AIOSDashboard:
    matrix = build_capability_matrix()
    systems = build_system_map()
    preview_only = tuple(item.feature_name for item in matrix if item.current_state == "available_preview_only")
    locked = tuple(item.feature_name for item in matrix if item.current_state in {"locked_future_gate", "blocked_by_policy", "not_implemented"})
    return AIOSDashboard(
        dashboard_id="eva-ai-os-phase26-desktop-control-gate",
        current_phase="Phase 26 Real Desktop Control Gate",
        overall_readiness="ready for local/mock control policy, eligibility, risk, approval, confirmation, and dry-run reports; real control locked",
        master_verification_summary="Latest known metadata before this pass: Phase 25 master quick 38/38 and full 55/55; Phase 26 proof is explicit.",
        phase_health_summary="Phases 12-26 have explicit local safety metadata; Phase 26 adds dry-run gate output only.",
        system_map_summary=f"{len(systems)} major systems mapped with explicit state and allowed mode.",
        capability_matrix_summary=f"{len(matrix)} representative capability groups; exactly one existing narrow real write gate.",
        preview_only_features=preview_only,
        existing_narrow_real_gate_summary="Phase 12L narrow approved new .md/.txt creation is a gated application write path.",
        locked_future_gates=locked,
        blocked_action_classes=("browser control", "desktop control", "shell", "package", "cloud", "MCP", "live provider", "broad file write"),
        safety_boundary_summary="Desktop observation grants no action authority; browser control/desktop control/shell/cloud/MCP remain locked.",
        recent_limitation_summary="Safe desktop backend is unavailable; mock fixtures are deterministic; no monitoring, saved screenshots, or actions exist.",
        next_recommended_safe_step="Phase 27 News/Web Intelligence Dashboard.",
        no_live_llm_call_statement="No live LLM call was made.",
        no_tool_execution_statement="Tools are not executed.",
        no_new_write_path_statement="Phase 12L remains a gated write path.",
    )


def readiness_text() -> str:
    from .safety_boundaries import boundary_lines

    return "\n".join(
        [
            "AI OS readiness",
            *boundary_lines(),
            "Ready for deterministic local dashboard, system-map, matrix, feature-state, and safety reports.",
            "Phase health is known metadata and never starts verifiers automatically.",
            "No live capability is inferred from a preview or locked gate.",
            "Real Browser Read-Only Mode is available for validated public-URL observation/report output only.",
            "Browser control remains locked; the safe real backend is unavailable and deterministic mock observation is ready.",
            "Real Desktop Observation Mode is available for explicit one-shot redacted observation/report output only.",
            "Real Desktop Control Gate is available for local/mock dry-run reports only; desktop control remains locked.",
            "Next phase: Phase 27 News/Web Intelligence Dashboard.",
        ]
    )
