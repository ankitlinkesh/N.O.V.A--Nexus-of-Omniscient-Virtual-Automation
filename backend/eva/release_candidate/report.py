from __future__ import annotations

from .checklist import RELEASE_CANDIDATE_CHECKLIST
from .commit_plan import COMMIT_GROUPING_PLAN
from .hardening import KNOWN_WARNINGS
from .manifest import (
    AUDITED_HEAD,
    CHANGED_AREA_GROUPS,
    DIRTY_TREE_SUMMARY,
    UNTRACKED_AREA_GROUPS,
)
from .models import ReleaseCandidateReport


def build_release_candidate_report() -> ReleaseCandidateReport:
    return ReleaseCandidateReport(
        release_candidate_id="eva-phase30-rc1",
        phase="Phase 30 Release Candidate Hardening / Commit Planning",
        head_reference=AUDITED_HEAD,
        dirty_tree_summary=DIRTY_TREE_SUMMARY,
        milestone_summary=(
            "Phases 12 through 29 are preserved on the audited 4f364d2 baseline.",
            "Phase 30 adds deterministic release-candidate hardening and commit planning only.",
        ),
        changed_area_groups=CHANGED_AREA_GROUPS,
        untracked_area_groups=UNTRACKED_AREA_GROUPS,
        commit_grouping_plan=COMMIT_GROUPING_PLAN,
        verification_status="focused, quick, full, compile, diff, and status checks required",
        docs_consistency_status="Phase 30 status and safety claims aligned",
        safety_boundary_status="unchanged; all unsafe execution classes remain locked",
        known_warnings=KNOWN_WARNINGS,
        blocking_issues=(),
        non_blocking_warnings=KNOWN_WARNINGS,
        release_candidate_checklist=RELEASE_CANDIDATE_CHECKLIST,
        recommended_next_action=(
            "user-approved commit execution outside Eva or a separate explicit commit-approval phase"
        ),
        final_readiness_status="ready_for_user_review_not_committed",
        no_commit_statement="No commit was made for Phase 30.",
        no_tag_statement="No tag was made for Phase 30.",
        no_push_statement="No push was made for Phase 30.",
        no_publish_statement="No publishing/uploading was performed for Phase 30.",
        no_secret_read_statement="No secrets were read or exposed.",
        no_runtime_execution_unlock_statement="No runtime execution feature was unlocked.",
        no_new_write_path_statement="Phase 12L remains a gated write path.",
    )
