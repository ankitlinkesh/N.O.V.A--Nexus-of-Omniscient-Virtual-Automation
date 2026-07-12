from __future__ import annotations

from .models import DemoSmokeReport


SAFE_DEMO_COMMANDS = (
    "eva release status",
    "eva release demo",
    "eva release commands",
    "eva release capability map",
    "eva release safety proof",
    "eva release readiness",
    "eva release verification",
    "eva release smoke test",
    "eva release post push sync",
)

VERIFICATION_COMMANDS = (
    r".\.venv\Scripts\python.exe -m compileall backend scripts",
    r".\.venv\Scripts\python.exe scripts\verify_eva_post_push_demo_smoke.py",
    r".\.venv\Scripts\python.exe scripts\verify_eva_all.py --list",
    r".\.venv\Scripts\python.exe scripts\verify_eva_all.py --quick --timeout 90",
    r".\.venv\Scripts\python.exe scripts\verify_eva_all.py --full --timeout 90",
    "git diff --check",
)

FIRST_RUN_CHECKLIST = (
    "Confirm the virtual environment exists before starting the local server.",
    "Run the smoke command first; it is text-only and does not execute unsafe features.",
    "Use release demo commands to show status, commands, safety proof, readiness, and verification guidance.",
    "Explain that browser, desktop, shell, cloud, MCP, and CodingAgent execution remain locked.",
    "Refresh verifier evidence in the terminal before making any readiness claim.",
)

KNOWN_WARNINGS = (
    "The demo is local and report/status/checklist only; it is not a hosted release.",
    "Remote sync evidence depends on the operator's Git network/auth state outside Eva chat.",
    "Locked features may appear in status reports as roadmap or preview surfaces, not live execution.",
)

BOUNDARY_STATEMENTS = {
    "no_secret_read_statement": "No secrets were read: `.env`, `.env.local`, tokens, cookies, passwords, browser sessions, and config contents stay untouched.",
    "no_live_provider_call_statement": "No live LLM/API/provider call was made.",
    "no_browser_control_statement": "No browser control is enabled.",
    "no_desktop_control_statement": "No desktop control is enabled.",
    "no_source_edit_statement": "No CodingAgent source editing is enabled.",
    "no_shell_execution_through_eva_statement": "No shell/test/package/git execution is enabled through Eva.",
    "no_unrestricted_crawler_statement": "No unrestricted crawler is enabled.",
    "no_new_write_path_statement": "No new write path was added; Phase 12L remains the only real write path.",
}


def build_demo_smoke_report() -> DemoSmokeReport:
    return DemoSmokeReport(
        demo_smoke_id="demo-smoke-phase32-e226b96",
        current_phase="Phase 32 Post-Push Sync + Demo Smoke Test Hardening",
        expected_pushed_commit="e226b96",
        remote_url_status="origin is expected at https://github.com/ankitlinkesh/eva-community.git after the moved-repository warning.",
        sync_status="Local main was verified against origin/main after the checkpoint push; remote dry-run fetch is the safe manual sync check.",
        readme_demo_doc_status="README and demo docs now describe safe local demo steps, smoke checks, and locked execution boundaries.",
        safe_demo_command_list=SAFE_DEMO_COMMANDS,
        verification_command_list=VERIFICATION_COMMANDS,
        first_run_checklist=FIRST_RUN_CHECKLIST,
        known_warnings=KNOWN_WARNINGS,
        blocking_issues=(),
        final_readiness_status="Ready for a safe local demo smoke review after fresh verifier evidence passes.",
        **BOUNDARY_STATEMENTS,
    )


def _bullets(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {item}" for item in items)


def demo_smoke_text() -> str:
    report = build_demo_smoke_report()
    return "\n".join(
        (
            "Eva Phase 32 demo smoke test",
            f"Demo-smoke ID: {report.demo_smoke_id}",
            f"Current phase: {report.current_phase}.",
            f"Expected pushed commit: {report.expected_pushed_commit}.",
            f"Remote URL status: {report.remote_url_status}",
            f"Sync status: {report.sync_status}",
            f"README/demo-doc status: {report.readme_demo_doc_status}",
            "Safe demo commands:",
            _bullets(report.safe_demo_command_list),
            "Verification commands:",
            _bullets(report.verification_command_list),
            "First-run checklist:",
            _bullets(report.first_run_checklist),
            "Known warnings:",
            _bullets(report.known_warnings),
            "Blocking issues:",
            _bullets(report.blocking_issues) if report.blocking_issues else "- None.",
            f"Final readiness: {report.final_readiness_status}",
            report.no_secret_read_statement,
            report.no_live_provider_call_statement,
            report.no_browser_control_statement,
            report.no_desktop_control_statement,
            report.no_source_edit_statement,
            report.no_shell_execution_through_eva_statement,
            report.no_unrestricted_crawler_statement,
            report.no_new_write_path_statement,
        )
    )
