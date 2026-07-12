from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReleaseDemoProfile:
    release_demo_id: str
    release_phase: str
    demo_readiness_status: str
    verified_milestone_summary: tuple[str, ...]
    capability_map_summary: tuple[str, ...]
    demo_command_list: tuple[str, ...]
    safety_proof_summary: tuple[str, ...]
    known_limitations: tuple[str, ...]
    verification_summary: tuple[str, ...]
    blocked_feature_summary: tuple[str, ...]
    public_facing_disclaimer: str
    next_safe_step: str
    final_readiness_status: str
    no_secret_exposure_statement: str
    no_real_provider_call_statement: str
    no_browser_control_statement: str
    no_desktop_control_statement: str
    no_source_edit_statement: str
    no_shell_execution_statement: str
    no_unrestricted_crawler_statement: str
    no_new_write_path_statement: str


@dataclass(frozen=True)
class ReleaseDemoStatus:
    available: bool
    mode: str
    publishing_enabled: bool
    external_upload_enabled: bool
    git_release_enabled: bool
    readiness: str
    next_safe_step: str


@dataclass(frozen=True)
class DemoSmokeReport:
    demo_smoke_id: str
    current_phase: str
    expected_pushed_commit: str
    remote_url_status: str
    sync_status: str
    readme_demo_doc_status: str
    safe_demo_command_list: tuple[str, ...]
    verification_command_list: tuple[str, ...]
    first_run_checklist: tuple[str, ...]
    known_warnings: tuple[str, ...]
    blocking_issues: tuple[str, ...]
    final_readiness_status: str
    no_secret_read_statement: str
    no_live_provider_call_statement: str
    no_browser_control_statement: str
    no_desktop_control_statement: str
    no_source_edit_statement: str
    no_shell_execution_through_eva_statement: str
    no_unrestricted_crawler_statement: str
    no_new_write_path_statement: str


@dataclass(frozen=True)
class PostPushSyncReport:
    sync_report_id: str
    current_phase: str
    expected_pushed_commit: str
    remote_url_status: str
    sync_status: str
    dry_run_status: str
    local_status_summary: str
    known_warnings: tuple[str, ...]
    blocking_issues: tuple[str, ...]
    final_status: str
    no_commit_statement: str
    no_push_statement: str
    no_tag_release_statement: str
    no_secret_read_statement: str
    no_execution_unlock_statement: str
