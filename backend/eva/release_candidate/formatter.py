from __future__ import annotations

from .checklist import checklist_text
from .commit_plan import commit_plan_text
from .hardening import hardening_report_text, safety_proof_text
from .manifest import dirty_tree_manifest_text
from .readiness import readiness_text, verification_text
from .report import build_release_candidate_report
from .status import get_release_candidate_status


BOUNDARY_LINES = (
    "No commit was made for Phase 30.",
    "No tag was made for Phase 30.",
    "No push was made for Phase 30.",
    "No publishing/uploading was performed for Phase 30.",
    "No secrets were read or exposed.",
    "No live LLM/API/provider call was made.",
    "No browser control is enabled.",
    "No desktop control is enabled.",
    "No CodingAgent source editing is enabled.",
    "No shell/test/package/git execution is enabled through Eva.",
    "No unrestricted crawler is enabled.",
    "No arbitrary file read/write or tool execution is enabled.",
    "Phase 12L remains a gated write path.",
)


def _output(title: str, body: str) -> str:
    return "\n".join((title, body, "", *BOUNDARY_LINES))


def _bullets(items: tuple[str, ...]) -> str:
    if not items:
        return "- None."
    return "\n".join(f"- {item}" for item in items)


def format_rc_status() -> str:
    status = get_release_candidate_status()
    report = build_release_candidate_report()
    body = "\n".join(
        (
            f"Phase: {report.phase}.",
            f"Release-candidate ID: {report.release_candidate_id}.",
            f"Audited HEAD: {report.head_reference}.",
            f"Mode: {status.mode}.",
            f"Readiness: {status.readiness}.",
            f"Git operations enabled: {status.git_operations_enabled}.",
            f"Publishing enabled: {status.publishing_enabled}.",
            f"Runtime execution enabled: {status.runtime_execution_enabled}.",
            f"Next safe step: {status.next_safe_step}.",
        )
    )
    return _output("Eva release-candidate status", body)


def format_rc_manifest() -> str:
    return _output("Eva release-candidate dirty tree manifest", dirty_tree_manifest_text())


def format_rc_commit_plan() -> str:
    return _output("Eva release-candidate commit plan", commit_plan_text())


def format_rc_hardening_report() -> str:
    return _output("Eva release-candidate hardening report", hardening_report_text())


def format_rc_checklist() -> str:
    return _output("Eva release-candidate checklist", checklist_text())


def format_rc_readiness() -> str:
    report = build_release_candidate_report()
    body = "\n".join(
        (
            readiness_text(),
            "Known warnings:",
            _bullets(report.known_warnings),
            "Blocking issues:",
            _bullets(report.blocking_issues),
            f"Final readiness: {report.final_readiness_status}.",
        )
    )
    return _output("Eva release-candidate readiness", body)


def format_rc_safety_proof() -> str:
    return _output("Eva release-candidate safety proof", safety_proof_text())


def format_rc_verification() -> str:
    return _output("Eva release-candidate verification", verification_text())
