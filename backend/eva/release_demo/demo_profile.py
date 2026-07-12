from __future__ import annotations

from .capability_map import CAPABILITY_MAP
from .demo_commands import DEMO_COMMANDS
from .known_limitations import KNOWN_LIMITATIONS
from .models import ReleaseDemoProfile
from .release_readiness import VERIFICATION_COMMANDS
from .safety_proof import SAFETY_PROOF


def build_demo_profile() -> ReleaseDemoProfile:
    return ReleaseDemoProfile(
        release_demo_id="eva-phase29-public-demo",
        release_phase="Phase 29 Public Demo / Release",
        demo_readiness_status="ready_for_local_demo_review",
        verified_milestone_summary=(
            "Phases 12 through 28 expose bounded, verifier-backed status and preview foundations.",
            "Phase 29 adds a public-facing local report/status/demo profile without execution.",
        ),
        capability_map_summary=CAPABILITY_MAP,
        demo_command_list=DEMO_COMMANDS,
        safety_proof_summary=SAFETY_PROOF,
        known_limitations=KNOWN_LIMITATIONS,
        verification_summary=tuple(f"Run manually: {command}" for command in VERIFICATION_COMMANDS),
        blocked_feature_summary=(
            "Publishing, uploading, packaging, installer creation, and git release operations.",
            "Browser/desktop control, shell/test/package/git, cloud/MCP, and tool execution.",
            "CodingAgent source editing, unrestricted crawling, and broad filesystem mutation.",
            "Secret/config/session access and raw private runtime dumps.",
        ),
        public_facing_disclaimer=(
            "Eva is a source-available local-first agent foundation. The public demo shows "
            "deterministic reports and bounded previews, not unrestricted autonomous execution."
        ),
        next_safe_step="user-approved commit execution outside Eva or a separate explicit commit-approval phase",
        final_readiness_status="ready_for_local_demo_review_not_published",
        no_secret_exposure_statement="No secrets were read or exposed.",
        no_real_provider_call_statement="No live LLM/API/provider call was made.",
        no_browser_control_statement="No browser control is enabled.",
        no_desktop_control_statement="No desktop control is enabled.",
        no_source_edit_statement="No CodingAgent source editing is enabled.",
        no_shell_execution_statement="No shell/test/package/git execution is enabled.",
        no_unrestricted_crawler_statement="No unrestricted crawler is enabled.",
        no_new_write_path_statement="Phase 12L remains a gated write path.",
    )
