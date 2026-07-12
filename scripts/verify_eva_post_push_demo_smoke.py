from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


COMMANDS = (
    "eva release smoke test",
    "eva release post push sync",
)

ASK_ROUTES = {
    "show demo smoke test": "release_demo_smoke",
    "show post push sync status": "release_post_push_sync",
    "is Eva synced with GitHub": "release_post_push_sync",
    "how do I demo Eva safely": "release_demo_smoke",
    "what should I run in the demo": "release_demo_smoke",
}

REQUIRED_SMOKE_FIELDS = (
    "demo_smoke_id",
    "current_phase",
    "expected_pushed_commit",
    "remote_url_status",
    "sync_status",
    "readme_demo_doc_status",
    "safe_demo_command_list",
    "verification_command_list",
    "first_run_checklist",
    "known_warnings",
    "blocking_issues",
    "final_readiness_status",
    "no_secret_read_statement",
    "no_live_provider_call_statement",
    "no_browser_control_statement",
    "no_desktop_control_statement",
    "no_source_edit_statement",
    "no_shell_execution_through_eva_statement",
    "no_unrestricted_crawler_statement",
    "no_new_write_path_statement",
)

REQUIRED_BOUNDARIES = (
    "phase 32 post-push sync + demo smoke test hardening",
    "demo-smoke id",
    "expected pushed commit: e226b96",
    "remote url status",
    "sync status",
    "safe demo commands",
    "verification commands",
    "first-run checklist",
    "known warnings",
    "blocking issues",
    "final readiness",
    "no secrets were read",
    "no live llm/api/provider call was made",
    "no browser control is enabled",
    "no desktop control is enabled",
    "no codingagent source editing is enabled",
    "no shell/test/package/git execution is enabled through eva",
    "no unrestricted crawler is enabled",
    "no new write path was added",
    "phase 12l remains a gated write path",
)

FORBIDDEN_OUTPUT_TOKENS = (
    "traceback",
    "{'",
    "dataclass(",
    "token=",
    "password=",
    "cookie=",
    "c:\\users\\",
)

FORBIDDEN_SOURCE_TOKENS = (
    "import subprocess",
    "from subprocess",
    "os.system(",
    "requests.",
    "httpx.",
    "urllib.request",
    "playwright",
    "selenium",
    "pyautogui",
    "open(",
    ".read_text(",
    ".write_text(",
    ".write_bytes(",
    "provider_sdk",
    "pip install",
    "git push",
    "git commit",
    "git tag",
    "gh release",
)


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def check_human_safe(text: str) -> None:
    lowered = text.lower()
    check(text.strip() and len(text.splitlines()) >= 12, "Phase 32 output is not human-readable")
    for phrase in REQUIRED_BOUNDARIES:
        check(phrase in lowered, f"Phase 32 output boundary missing: {phrase}")
    for token in FORBIDDEN_OUTPUT_TOKENS:
        check(token not in lowered, f"unsafe Phase 32 output token: {token}")


def main() -> int:
    from backend.eva.release_demo.demo_smoke import build_demo_smoke_report, demo_smoke_text
    from backend.eva.release_demo.formatter import format_release_demo_smoke, format_release_post_push_sync
    from backend.eva.release_demo.models import DemoSmokeReport, PostPushSyncReport
    from backend.eva.release_demo.post_push_sync import build_post_push_sync_report, post_push_sync_text
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.core.natural_router import route_natural_request
    from backend.eva.tools.registry import ToolRegistry
    from scripts import verify_eva_all

    smoke = build_demo_smoke_report()
    sync = build_post_push_sync_report()
    check(isinstance(smoke, DemoSmokeReport), "demo smoke report type mismatch")
    check(isinstance(sync, PostPushSyncReport), "post-push sync report type mismatch")
    check(smoke.expected_pushed_commit == "e226b96", "expected pushed commit drifted")
    check("https://github.com/ankitlinkesh/eva-community.git" in sync.remote_url_status, "remote URL status missing moved URL")
    check(smoke.blocking_issues == (), "demo smoke report has blocking issues")

    fields = set(getattr(smoke, "__dataclass_fields__", {}).keys())
    for field in REQUIRED_SMOKE_FIELDS:
        check(field in fields, f"demo smoke model field missing: {field}")

    outputs = (
        demo_smoke_text(),
        post_push_sync_text(),
        format_release_demo_smoke(),
        format_release_post_push_sync(),
    )
    for output in outputs:
        check_human_safe(output)

    for command in COMMANDS:
        result = maybe_handle_fast_command(command, ToolRegistry())
        check(result is not None, f"Phase 32 command missing: {command}")
        check_human_safe(result[0])

    for prompt, expected_intent in ASK_ROUTES.items():
        route = route_natural_request(prompt)
        check(
            route.intent == expected_intent and not route.real_execution_requested,
            f"unsafe Phase 32 ask route: {prompt}",
        )
        result = maybe_handle_fast_command(f"eva ask {prompt}", ToolRegistry())
        check(result is not None, f"Phase 32 ask command missing: {prompt}")
        check_human_safe(result[0])

    for doc_name in (
        "EVA_DEMO_SMOKE_TEST.md",
        "EVA_POST_PUSH_SYNC.md",
        "EVA_CURRENT_STATE.md",
        "EVA_VERIFICATION.md",
        "EVA_RELEASE_READINESS.md",
        "EVA_BUG_QUEUE.md",
    ):
        text = (ROOT / "docs" / doc_name).read_text(encoding="utf-8")
        lowered = text.lower()
        check("phase 32 post-push sync + demo smoke test hardening is complete after this pass" in lowered, f"Phase 32 completion missing: {doc_name}")
        for phrase in (
            "https://github.com/ankitlinkesh/eva-community.git",
            "no commit/push/tag/release was performed in phase 32",
            "demo smoke test is report/status/checklist only",
            "no provider sdks or package installs",
            "no real llm/api/provider calls happen",
            "no secrets, tokens, cookies, passwords, browser sessions, or config contents are read",
            "browser/desktop/shell/cloud/mcp execution remains locked",
            "codingagent remains preview/report/status only",
            "phase 12l",
        ):
            check(phrase in lowered, f"Phase 32 doc boundary missing in {doc_name}: {phrase}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    for phrase in (
        "safe local demo",
        "eva release smoke test",
        "eva release post push sync",
        "verify eva without enabling unsafe features",
    ):
        check(phrase in readme, f"README safe demo instruction missing: {phrase}")

    verifier_name = "verify_eva_post_push_demo_smoke.py"
    check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full profile is missing Phase 32")
    check(verifier_name in verify_eva_all.QUICK_VERIFIERS, "quick profile is missing Phase 32")

    source_text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (ROOT / "backend" / "eva" / "release_demo").glob("*.py")
    )
    for token in FORBIDDEN_SOURCE_TOKENS:
        check(token not in source_text, f"forbidden Phase 32 runtime surface: {token}")

    print("PASS: Phase 32 Post-Push Sync + Demo Smoke Test Hardening is local, report-only, and execution-locked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
