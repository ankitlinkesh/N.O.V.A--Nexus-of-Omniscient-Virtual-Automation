from __future__ import annotations

from .models import PostPushSyncReport


def build_post_push_sync_report() -> PostPushSyncReport:
    return PostPushSyncReport(
        sync_report_id="post-push-sync-phase32-e226b96",
        current_phase="Phase 32 Post-Push Sync + Demo Smoke Test Hardening",
        expected_pushed_commit="e226b96",
        remote_url_status="origin uses https://github.com/ankitlinkesh/eva-community.git, the moved repository location.",
        sync_status="Local main is expected to match origin/main at e226b96 after the checkpoint push; use git status -sb and git fetch --dry-run origin for fresh terminal evidence.",
        dry_run_status="The safe remote check is git fetch --dry-run origin only; no pull, merge, rebase, checkout, reset, or force operation is part of this report.",
        local_status_summary="Phase 32 records post-push hygiene and demo smoke readiness without changing release state.",
        known_warnings=(
            "Network/auth failures can block dry-run fetch evidence without changing local files.",
            "This report does not create a tag, release, package, installer, or publication.",
        ),
        blocking_issues=(),
        final_status="Post-push sync status is ready for local review when the dry-run fetch and verifier sweep pass.",
        no_commit_statement="No commit was made by Phase 32.",
        no_push_statement="No push was made by Phase 32.",
        no_tag_release_statement="No tag or release was created by Phase 32.",
        no_secret_read_statement="No secrets were read: `.env`, `.env.local`, tokens, cookies, passwords, browser sessions, and config contents stay untouched.",
        no_execution_unlock_statement="Browser/desktop/shell/cloud/MCP execution remains locked; CodingAgent remains preview/report/status only; Phase 12L remains the only real write path.",
    )


def _bullets(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {item}" for item in items)


def post_push_sync_text() -> str:
    report = build_post_push_sync_report()
    return "\n".join(
        (
            "Eva Phase 32 post-push sync status",
            f"Demo-smoke ID: demo-smoke-phase32-e226b96",
            f"Sync report ID: {report.sync_report_id}",
            f"Current phase: {report.current_phase}.",
            f"Expected pushed commit: {report.expected_pushed_commit}.",
            f"Remote URL status: {report.remote_url_status}",
            f"Sync status: {report.sync_status}",
            f"Dry-run status: {report.dry_run_status}",
            f"README/demo-doc status: safe local demo docs are expected to reference the Phase 32 smoke commands.",
            "Safe demo commands:",
            "- eva release smoke test",
            "- eva release post push sync",
            "Verification commands:",
            r"- .\.venv\Scripts\python.exe scripts\verify_eva_post_push_demo_smoke.py",
            r"- .\.venv\Scripts\python.exe scripts\verify_eva_all.py --quick --timeout 90",
            r"- .\.venv\Scripts\python.exe scripts\verify_eva_all.py --full --timeout 90",
            "First-run checklist:",
            "- Confirm branch/status in a terminal before demo claims.",
            "- Run the report-only smoke command before showing locked features.",
            "- Keep all unsafe execution surfaces locked.",
            "Known warnings:",
            _bullets(report.known_warnings),
            "Blocking issues:",
            _bullets(report.blocking_issues) if report.blocking_issues else "- None.",
            f"Final readiness: {report.final_status}",
            report.no_commit_statement,
            report.no_push_statement,
            report.no_tag_release_statement,
            report.no_secret_read_statement,
            "No live LLM/API/provider call was made.",
            "No browser control is enabled.",
            "No desktop control is enabled.",
            "No CodingAgent source editing is enabled.",
            "No shell/test/package/git execution is enabled through Eva.",
            "No unrestricted crawler is enabled.",
            "No new write path was added; Phase 12L remains the only real write path.",
            report.no_execution_unlock_statement,
        )
    )
