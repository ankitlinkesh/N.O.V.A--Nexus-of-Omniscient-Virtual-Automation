from __future__ import annotations

from .models import WorkflowVerificationPlan


def build_verification_plan() -> WorkflowVerificationPlan:
    return WorkflowVerificationPlan(
        status="preview_only",
        checks=(
            "Confirm no live LLM call was made.",
            "Confirm workflow steps are preview-only.",
            "Confirm tools are not executed.",
            "Confirm secrets/config/session data are blocked.",
            "Confirm arbitrary file reads/writes are blocked.",
            "Confirm browser/desktop/shell/cloud/MCP execution remains locked.",
            "Confirm Phase 12L remains a gated write path.",
        ),
    )
