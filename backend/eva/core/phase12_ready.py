from __future__ import annotations


QUICK_VERIFY_COMMAND = r".\.venv\Scripts\python.exe scripts\verify_eva_all.py --quick"
FULL_VERIFY_COMMAND = r".\.venv\Scripts\python.exe scripts\verify_eva_all.py --full"


def format_phase12_ready() -> str:
    return "\n".join(
        [
            "Eva Phase 12 readiness",
            "",
            "Status: ready for checkpoint review when the quick and full verifier profiles pass in the current terminal.",
            "Latest proof requirement: run the verifier commands manually; status surfaces do not run subprocesses.",
            "",
            "Ready surfaces:",
            "- FileAgent safety, approval ledger, sandbox apply, Phase 12L narrow real create, verification, and guarded rollback",
            "- specialists, skills, workflow routing, latest workflow state, Control Center, WorkSession audit timeline, project/reality checks, and golden workflow E2E proof",
            "",
            "Gated write path:",
            "- Phase 12L narrow real create: one approved brand-new .md/.txt file directly under docs/ or samples/ after exact confirmation.",
            "",
            "Locked:",
            "- broad edits, existing file edits, overwrite/append/replace, source/config/runtime writes",
            "- browser control, desktop control, shell/terminal execution, MCP, Playwright, PyAutoGUI",
            "- package installs, cloud calls, message sending, and normal-chat v2 routing",
            "",
            "Manual proof commands:",
            f"- `{QUICK_VERIFY_COMMAND}`",
            f"- `{FULL_VERIFY_COMMAND}`",
            "",
            "Execution: read-only readiness status. Control Center and WorkSession are status/audit only.",
        ]
    )


def format_phase12_summary() -> str:
    return "\n".join(
        [
            "Eva Phase 12 summary",
            "",
            "Phase 12 stabilized Eva around safe local agency: authority routing, FileAgent gates, Control Center visibility, WorkSession audit trails, specialist/skill/workflow routing, project reality checks, and golden workflow proof.",
            "",
            "Current safe UX:",
            "- `eva ask` routes natural requests to existing safe status, preview, approval, sandbox, and exact-confirmation paths.",
            "- explicit commands remain debug/fallback surfaces.",
            "- verifier proof still requires terminal verifier runs.",
            "",
            "Gated write path:",
            "- Phase 12L narrow real create for approved new .md/.txt files directly under docs/ or samples/.",
            "",
            "Still locked:",
            "- broad/source/existing-file edits, browser/desktop/shell/MCP/cloud/package/message execution.",
            "",
            "Execution: summary only. No task was executed.",
        ]
    )


def format_phase12_limits() -> str:
    return "\n".join(
        [
            "Eva Phase 12 limits",
            "",
            "Allowed real write:",
            "- Phase 12L narrow real create only: approved brand-new .md/.txt files directly under docs/ or samples/, exact `confirm real create <approval_id>`, verify hash, guarded rollback.",
            "",
            "Locked real actions:",
            "- broad edits, existing file edits, overwrite, append, replace",
            "- source/config/runtime writes",
            "- delete, move, rename, copy, broad backup/restore",
            "- browser control, desktop control, screen watching",
            "- shell/terminal execution, MCP, Playwright, PyAutoGUI",
            "- package installs, cloud calls, message sending, normal-chat v2 routing",
            "",
            "Status surfaces:",
            "- Control Center is read-only status.",
            "- WorkSession is local audit/status.",
            "- Project reality and golden workflow proof summarize evidence only.",
            "- Verification proof requires terminal verifier runs.",
            "",
            "Execution: limits summary only. No action was executed.",
        ]
    )


def format_phase12_proof() -> str:
    return "\n".join(
        [
            "Eva Phase 12 proof",
            "",
            "Gated write path:",
            "- Phase 12L narrow real create for approved brand-new .md/.txt files directly under docs/ or samples/.",
            "",
            "Proof surfaces:",
            "- `scripts/verify_eva_all.py --quick` for the fast Phase 12 smoke path.",
            "- `scripts/verify_eva_all.py --full` for the full Phase 12/FileAgent/planner sweep.",
            "- `scripts/verify_eva_golden_workflow_e2e.py` for natural golden FileAgent workflow proof.",
            "- Control Center shows current status but does not run verifiers.",
            "- WorkSession shows local audit events but does not execute workflow steps.",
            "",
            "What passing proof means:",
            "- The safe routing/status/approval/sandbox/12L real-create/verification/rollback surfaces are coherent.",
            "- Phase 12L narrow real create remains a gated write path.",
            "",
            "What it does not unlock:",
            "- broad file edits, source edits, existing-file writes, browser/desktop control, shell/MCP/cloud/package/message execution.",
            "",
            "Manual proof commands:",
            f"- `{QUICK_VERIFY_COMMAND}`",
            f"- `{FULL_VERIFY_COMMAND}`",
            "",
            "Execution: proof summary only. No verifier command was run by chat.",
        ]
    )
