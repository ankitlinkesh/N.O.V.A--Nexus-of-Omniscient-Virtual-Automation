from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def assert_true(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_clean(text: str, label: str) -> None:
    markers = ["{'", "Traceback", "AuthorityDecision(", ".env.local", str(ROOT)]
    for marker in markers:
        assert_true(marker not in str(text), f"{label} leaked unsafe marker: {marker}")


def run_fast_command(message: str) -> str:
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.tools.registry import ToolRegistry

    result = maybe_handle_fast_command(message, ToolRegistry())
    assert_true(result is not None, f"command was not handled: {message}")
    return result[0]


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        os.environ["EVA_FILE_AGENT_APPROVAL_LEDGER_PATH"] = str(Path(temp) / "approval_ledger.json")
        os.environ["EVA_FILE_AGENT_SANDBOX_ROOT"] = str(Path(temp) / "sandbox")

        smoke_path = ROOT / "scripts" / "verify_eva_smoke.py"
        assert_true(smoke_path.exists(), "smoke verifier missing")
        importlib.import_module("scripts.verify_eva_smoke")
        smoke = subprocess.run([sys.executable, str(smoke_path)], cwd=str(ROOT), text=True, capture_output=True, timeout=75)
        assert_true(smoke.returncode == 0, "smoke verifier failed")
        assert_true("Result: PASS" in smoke.stdout and "Eva smoke verifier summary" in smoke.stdout, "smoke summary missing")

        import scripts.verify_eva_all as verify_all

        assert_true("quick" in verify_all.PROFILES, "--quick profile missing")
        assert_true("full" in verify_all.PROFILES, "--full profile missing")
        assert_true("verify_eva_smoke.py" in verify_all.PROFILES["quick"], "quick profile missing smoke verifier")
        assert_true("verify_eva_smoke.py" in verify_all.PROFILES["full"], "full profile missing smoke verifier")
        assert_true("verify_eva_phase12_stabilization.py" in verify_all.PROFILES["full"], "full profile missing phase12 verifier")

        listed = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_eva_all.py"), "--list"], cwd=str(ROOT), text=True, capture_output=True, timeout=30)
        assert_true(listed.returncode == 0 and "quick" in listed.stdout and "full" in listed.stdout, "--list did not show profiles")

        if os.environ.get("EVA_VERIFY_SKIP_NESTED") == "1":
            assert_true(len(verify_all.PROFILES["quick"]) >= 1, "quick profile unexpectedly empty")
        else:
            # The quick profile grew to ~140 scripts, so re-running all of it here under
            # 120s could never pass. The master suite runs the whole profile; this proves
            # the runner end to end on the smoke-tagged slice.
            quick = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "verify_eva_all.py"), "--quick", "--tag", "smoke"],
                cwd=str(ROOT), capture_output=True, encoding="utf-8", errors="replace", timeout=300,
            )
            assert_true(quick.returncode == 0, f"--quick failed: {quick.stdout[-1000:]} {quick.stderr[-1000:]}")
            assert_true("Profile: quick" in quick.stdout and "Failed: 0" in quick.stdout and "Ran: 0" not in quick.stdout, "quick summary incomplete")

        from backend.eva.core import ux_messages
        from backend.eva.capabilities.permissions import get_capability_permission
        from backend.eva.capabilities.registry import get_capability
        from backend.eva.capabilities.resource_mapping import resolve_capability
        from backend.eva.capabilities.tool_schemas import capability_to_tool_schema
        from backend.eva.planner.capability_selector import select_capabilities_for_goal
        from backend.eva.agents.team_review import format_team_review

        assert_true(ux_messages.format_quick_status_summary(), "ux helper returned empty output")

        outputs = {
            "inspect": run_fast_command("eva ask inspect this project"),
            "control": run_fast_command("eva ask show control center"),
            "safe": run_fast_command("eva ask what can Eva do safely right now"),
            "note": run_fast_command("eva ask create a project note about Eva"),
            "real": run_fast_command("eva ask real apply the approved file"),
            "vague": run_fast_command("eva ask yes"),
            "delete": run_fast_command("eva ask delete my files"),
            "quick_command": run_fast_command("eva verify quick command"),
            "full_command": run_fast_command("eva verify full command"),
            "phase12": run_fast_command("eva phase 12 status"),
        }
        assert_true("Next safe step" in outputs["note"], "note output missing next safe step")
        assert_true("confirm real create" in outputs["real"].lower() or "eligible" in outputs["real"].lower(), "real apply did not require exact phrase")
        assert_true("exact" in outputs["vague"].lower() or "could not map" in outputs["vague"].lower(), "vague confirmation unsafe")
        assert_true("blocked" in outputs["delete"].lower() or "destructive" in outputs["delete"].lower(), "delete not blocked")
        assert_true("verify_eva_all.py --quick" in outputs["quick_command"], "quick manual command missing")
        assert_true("verify_eva_all.py --full" in outputs["full_command"], "full manual command missing")
        for label, text in outputs.items():
            assert_clean(text, label)

        control = run_fast_command("eva control center status")
        assert_true("Phase 12 Health" in control and "smoke verifier" in control.lower(), "control health missing")
        assert_true("Not run in this dashboard session" in control, "dashboard should not run verifiers automatically")
        assert_clean(control, "control")

        for capability_id in ("eva.smoke_status", "eva.verify_quick_command", "eva.verify_full_command", "eva.phase12_status", "eva.ux_status"):
            assert_true(get_capability(capability_id) is not None, f"capability missing: {capability_id}")
            permission = get_capability_permission(capability_id)
            assert_true(permission.read_only and not permission.writes_local_data, f"permission unsafe: {capability_id}")
            assert_true(resolve_capability(capability_id).resource_id, f"resource missing: {capability_id}")
            assert_true(capability_to_tool_schema(capability_id) is not None, f"schema missing: {capability_id}")

        assert_true("eva.smoke_status" in select_capabilities_for_goal("verify Eva with quick check"), "planner missed verify quick")
        review = format_team_review("verify Eva with quick check")
        assert_true("VerifierAgent" in review or "SafetyAgent" in review, "team review did not route verification safely")
        assert_true("no task was executed" in review.lower(), "team review implies execution")
        assert_clean(review, "team review")

    print("verify_eva_phase12_stabilization: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
