from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> int:
    from backend.eva.agent.executor import ToolExecutor
    from backend.eva.agent.planner import PlannedToolCall
    from backend.eva.evals.harness import run_offline_evals
    from backend.eva.evals.offline_suite import offline_tasks
    from backend.eva.tools.postconditions import derive_postcondition, verify_tool_effect
    from backend.eva.tools.registry import ToolRegistry
    from scripts import verify_eva_all

    scratch = Path(tempfile.mkdtemp(prefix="eva_phase38_"))
    target = scratch / "note.txt"
    target.write_text("phase38 token", encoding="utf-8")

    # Independent file verification is real proof, both ways.
    present = verify_tool_effect("file.write_text", "file_contains", {"path": str(target), "content": "phase38 token"}, {"ok": True})
    check(present.provenance == "independent" and present.verified is True, "present file content must verify independently")
    absent = verify_tool_effect("file.write_text", "file_contains", {"path": str(target), "content": "never written"}, {"ok": True})
    check(absent.independent is True and absent.verified is False, "a false claim about file content must be caught")

    # Delete semantics are derived from the tool, not the (file_exists) metadata.
    check(derive_postcondition("file.delete", "file_exists", {"path": str(target)}).method == "file_absent", "delete must derive a file_absent post-condition")
    still_there = verify_tool_effect("file.delete", "file_exists", {"path": str(target)}, {"ok": True})
    check(still_there.method == "file_absent" and still_there.verified is False, "a delete that left the file must not verify")
    target.unlink()
    gone = verify_tool_effect("file.delete", "file_exists", {"path": str(target)}, {"ok": True})
    check(gone.verified is True, "a delete that removed the file must verify")

    # Weaker provenance classes never fabricate independent proof.
    read = verify_tool_effect("workspace_status", "command_result_success", {}, {"ok": True})
    check(read.provenance == "self_reported" and read.independent is False, "a read must be self_reported, not independent")
    # Phase 64: this used to assert provenance == "observed" -- i.e. that a
    # screen effect nothing in this codebase can actually check was reported
    # as if it had been independently confirmed (verified was silently
    # borrowed from the tool's own self-reported ok). Nothing here has a
    # perception capability wired up to look at the screen, so "observed" was
    # never true; it is honestly "unverified" now, and verified must not be
    # True on the strength of the self-report alone. See
    # scripts/verify_eva_phase64_honest_effects.py for the full Phase 64 spec.
    screen = verify_tool_effect("screen.type_text", "text_field_contains", {"text": "hi"}, {"ok": True})
    check(screen.provenance == "unverified" and screen.independent is False, "a screen effect must be unverified, not independent")
    check(screen.verified is False, "a screen effect must not claim verified=True from a self-report alone")
    unknown = verify_tool_effect("mystery_tool", "no_verification_available", {}, {"ok": True})
    check(unknown.provenance == "unverified", "a tool with no verification method must be unverified")

    # The executor attaches verification and keys ok on independent failure only.
    result = ToolExecutor(ToolRegistry()).execute(PlannedToolCall(tool="workspace_status", args={}))
    check(result.ok is True, "an allow-class read must stay ok")
    check(result.verification and result.verification["provenance"] == "self_reported", "executor must attach self_reported verification")
    check(absent.independent and not absent.verified, "the executor demotes ok exactly when independent and not verified")

    # The gate chokepoint records verification (guarded by tracing) — check both tokens.
    registry_source = (ROOT / "backend" / "eva" / "tools" / "registry.py").read_text(encoding="utf-8")
    check("verify_tool_effect" in registry_source, "registry _invoke must call verify_tool_effect")
    check("trace_verification" in registry_source, "registry _invoke must emit trace_verification")
    check("tracing_enabled" in registry_source, "the verification emit must be guarded by tracing_enabled")

    # The verification-first eval is present and the offline suite stays green.
    task_ids = {task.id for task in offline_tasks()}
    check("post_condition_verification_is_independent" in task_ids, "the verification eval must be registered in the offline suite")
    report = run_offline_evals()
    check(report.all_passed, f"offline eval suite must stay green: {report.summary_text()}")
    check(any(r.task_id == "post_condition_verification_is_independent" and r.passed for r in report.results), "the verification eval must pass")

    # Registered in the master verifier profiles.
    verifier_name = "verify_eva_phase38_verification.py"
    check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 38 verification verifier")
    descriptors = getattr(verify_eva_all, "VERIFIER_DESCRIPTORS")
    check(verifier_name in descriptors, "master verifier descriptor missing the Phase 38 verification verifier")

    os.environ.pop("EVA_TRACING_ENABLED", None)
    print("PASS: Phase 38 verification-first execution independently proves file effects, is honest about self-reported/observed/unverified provenance, records verification in the flight recorder, and gates 'done' on real state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
