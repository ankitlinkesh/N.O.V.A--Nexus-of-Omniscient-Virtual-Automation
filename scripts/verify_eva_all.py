from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FULL_VERIFIERS = [
    "verify_eva_smoke.py",
    "verify_eva_phase12_stabilization.py",
    "verify_eva_phase12_ready.py",
    "verify_eva_golden_workflows.py",
    "verify_eva_golden_workflow_e2e.py",
    "verify_eva_control_center.py",
    "verify_eva_control_center_v1.py",
    "verify_eva_work_sessions_audit.py",
    "verify_eva_skill_specialist_workflows.py",
    "verify_eva_golden_workflow_ux.py",
    "verify_eva_project_reality_workflow.py",
    "verify_eva_browser_agent_safety.py",
    "verify_eva_browser_session_preview.py",
    "verify_eva_browser_page_summary_design.py",
    "verify_eva_browser_action_dry_run.py",
    "verify_eva_browser_domain_policy.py",
    "verify_eva_browser_readiness_proof.py",
    "verify_eva_browser_phase13_hardening.py",
    "verify_eva_desktop_agent_safety.py",
    "verify_eva_desktop_session_preview.py",
    "verify_eva_desktop_screen_observation_policy.py",
    "verify_eva_desktop_action_dry_run.py",
    "verify_eva_desktop_action_risk_scoring.py",
    "verify_eva_desktop_approval_model.py",
    "verify_eva_desktop_phase14_readiness.py",
    "verify_eva_llm_router_contracts.py",
    "verify_eva_llm_router_fallbacks_limits.py",
    "verify_eva_llm_structured_output_core.py",
    "verify_eva_llm_structured_output_commands.py",
    "verify_eva_llm_structured_output_wiring.py",
    "verify_eva_llm_structured_output_closeout.py",
    "verify_eva_llm_red_team_failure_tests.py",
    "verify_eva_llm_red_team_evidence_lock.py",
    "verify_eva_context_assembly_engine.py",
    "verify_eva_llm_threat_defense_prompt_injection.py",
    "verify_eva_agent_loop_v1.py",
    "verify_eva_agentic_workflow_planner.py",
    "verify_eva_controlled_execution_gates.py",
    "verify_eva_memory_v3.py",
    "verify_eva_voice_assistant_foundation.py",
    "verify_eva_ai_os_control_center_upgrade.py",
    "verify_eva_browser_readonly_mode.py",
    "verify_eva_desktop_observation_mode.py",
    "verify_eva_desktop_control_gate.py",
    "verify_eva_news_web_intelligence_dashboard.py",
    "verify_eva_coding_agent_foundation.py",
    "verify_eva_public_demo_release.py",
    "verify_eva_release_candidate_hardening.py",
    "verify_eva_post_push_demo_smoke.py",
    "verify_eva_phase33_roadmap_foundations.py",
    "verify_eva_file_agent_real_apply_gate.py",
    "verify_eva_file_agent_real_create_gate.py",
    "verify_eva_file_agent_sandbox_apply.py",
    "verify_eva_file_agent_approval_ledger.py",
    "verify_eva_file_agent_write_safety.py",
    "verify_eva_file_agent_draft_preview.py",
    "verify_eva_file_agent_understanding.py",
    "verify_eva_file_agent_readonly.py",
    "verify_eva_agent_framework_quality.py",
    "verify_eva_planner_v3_quality.py",
    "verify_eva_capability_resource_mapping.py",
    "verify_eva_stabilization_v1.py",
    "verify_eva_phase36_observability.py",
    "verify_eva_phase36_evals.py",
    "verify_eva_phase37_activation.py",
    "verify_eva_phase37_exercise.py",
    "verify_eva_phase38_verification.py",
    "verify_eva_phase39_reliability.py",
    "verify_eva_phase40_adversarial.py",
    "verify_eva_phase40c_hardening.py",
    "verify_eva_phase41_critic.py",
    "verify_eva_phase42_calibration.py",
    "verify_eva_phase43_memory.py",
    "verify_eva_phase44_perception.py",
    "verify_eva_phase45_durable.py",
    "verify_eva_phase46_proactivity.py",
]

QUICK_VERIFIERS = [
    "verify_eva_smoke.py",
    "verify_eva_phase12_ready.py",
    "verify_eva_golden_workflows.py",
    "verify_eva_control_center.py",
    "verify_eva_skill_specialist_workflows.py",
    "verify_eva_golden_workflow_ux.py",
    "verify_eva_browser_agent_safety.py",
    "verify_eva_browser_session_preview.py",
    "verify_eva_browser_page_summary_design.py",
    "verify_eva_browser_action_dry_run.py",
    "verify_eva_browser_domain_policy.py",
    "verify_eva_browser_readiness_proof.py",
    "verify_eva_browser_phase13_hardening.py",
    "verify_eva_desktop_agent_safety.py",
    "verify_eva_desktop_session_preview.py",
    "verify_eva_desktop_screen_observation_policy.py",
    "verify_eva_desktop_action_dry_run.py",
    "verify_eva_desktop_action_risk_scoring.py",
    "verify_eva_desktop_approval_model.py",
    "verify_eva_desktop_phase14_readiness.py",
    "verify_eva_llm_router_contracts.py",
    "verify_eva_llm_router_fallbacks_limits.py",
    "verify_eva_llm_structured_output_core.py",
    "verify_eva_llm_structured_output_commands.py",
    "verify_eva_llm_structured_output_wiring.py",
    "verify_eva_llm_red_team_failure_tests.py",
    "verify_eva_llm_red_team_evidence_lock.py",
    "verify_eva_context_assembly_engine.py",
    "verify_eva_llm_threat_defense_prompt_injection.py",
    "verify_eva_agent_loop_v1.py",
    "verify_eva_agentic_workflow_planner.py",
    "verify_eva_controlled_execution_gates.py",
    "verify_eva_memory_v3.py",
    "verify_eva_voice_assistant_foundation.py",
    "verify_eva_ai_os_control_center_upgrade.py",
    "verify_eva_browser_readonly_mode.py",
    "verify_eva_desktop_observation_mode.py",
    "verify_eva_desktop_control_gate.py",
    "verify_eva_news_web_intelligence_dashboard.py",
    "verify_eva_coding_agent_foundation.py",
    "verify_eva_public_demo_release.py",
    "verify_eva_release_candidate_hardening.py",
    "verify_eva_post_push_demo_smoke.py",
    "verify_eva_phase33_roadmap_foundations.py",
    "verify_eva_file_agent_real_apply_gate.py",
    "verify_eva_phase36_observability.py",
    "verify_eva_phase36_evals.py",
    "verify_eva_phase37_activation.py",
    "verify_eva_phase37_exercise.py",
    "verify_eva_phase38_verification.py",
    "verify_eva_phase39_reliability.py",
    "verify_eva_phase40_adversarial.py",
    "verify_eva_phase40c_hardening.py",
    "verify_eva_phase41_critic.py",
    "verify_eva_phase42_calibration.py",
    "verify_eva_phase43_memory.py",
    "verify_eva_phase44_perception.py",
    "verify_eva_phase45_durable.py",
    "verify_eva_phase46_proactivity.py",
]

VERIFIERS = FULL_VERIFIERS
PROFILES = {
    "quick": QUICK_VERIFIERS,
    "full": FULL_VERIFIERS,
}

_VERIFIER_TAG_OVERRIDES = {
    "verify_eva_post_push_demo_smoke.py": ("phase32", "release", "demo-smoke"),
    "verify_eva_phase33_roadmap_foundations.py": ("phase33", "roadmap", "safety-boundary", "catalog"),
    "verify_eva_all.py": ("phase40", "verifier-dashboard", "profiles"),
    "verify_eva_phase36_observability.py": ("phase36", "observability", "tracing"),
    "verify_eva_phase36_evals.py": ("phase36", "evals", "benchmarks"),
    "verify_eva_phase37_activation.py": ("phase37", "activation", "turn-on"),
    "verify_eva_phase37_exercise.py": ("phase37", "exercise", "friction"),
    "verify_eva_phase38_verification.py": ("phase38", "verification", "provenance"),
    "verify_eva_phase39_reliability.py": ("phase39", "reliability", "recovery"),
    "verify_eva_phase40_adversarial.py": ("phase40", "adversarial", "injection"),
    "verify_eva_phase40c_hardening.py": ("phase40c", "least-privilege", "secrets-broker"),
    "verify_eva_phase41_critic.py": ("phase41", "critic", "delegation-contract"),
    "verify_eva_phase42_calibration.py": ("phase42", "calibrated-autonomy", "trust-policy"),
    "verify_eva_phase43_memory.py": ("phase43", "memory", "user-model"),
    "verify_eva_phase44_perception.py": ("phase44", "perception", "grounding"),
    "verify_eva_phase45_durable.py": ("phase45", "durable-queue", "crash-recovery"),
    "verify_eva_phase46_proactivity.py": ("phase46", "proactivity", "triggers"),
}


def _build_verifier_descriptors() -> dict[str, dict[str, object]]:
    scripts = sorted(set(FULL_VERIFIERS) | set(QUICK_VERIFIERS))
    descriptors: dict[str, dict[str, object]] = {}
    for script in scripts:
        profiles = tuple(name for name, names in PROFILES.items() if script in names)
        tags = _VERIFIER_TAG_OVERRIDES.get(script, ())
        if not tags:
            stem = script.removeprefix("verify_eva_").removesuffix(".py")
            tags = tuple(part for part in stem.replace("-", "_").split("_") if part)
        descriptors[script] = {
            "profiles": profiles,
            "tags": tags,
            "risk": "low" if script in QUICK_VERIFIERS else "medium",
            "requires_network": False,
            "mutates_repo_tracked_files": False,
        }
    return descriptors


VERIFIER_DESCRIPTORS = _build_verifier_descriptors()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Eva verifier sweep.")
    profile_group = parser.add_mutually_exclusive_group()
    profile_group.add_argument("--quick", action="store_true", help="Run the fast Phase 12 smoke profile.")
    profile_group.add_argument("--full", action="store_true", help="Run the complete verifier profile.")
    parser.add_argument("--continue-on-fail", action="store_true", help="Run remaining verifiers after a failure.")
    parser.add_argument("--list", action="store_true", help="List verifier scripts by profile without running them.")
    parser.add_argument("--tag", help="Run only verifiers in the selected profile that include this metadata tag.")
    parser.add_argument("--metadata", action="store_true", help="Show verifier metadata while listing profiles.")
    parser.add_argument("--timeout", type=float, default=None, help="Optional timeout in seconds per verifier script.")
    args = parser.parse_args(argv)
    profile = "quick" if args.quick else "full"
    verifiers = PROFILES[profile]
    if args.tag:
        verifiers = [script for script in verifiers if args.tag in VERIFIER_DESCRIPTORS.get(script, {}).get("tags", ())]

    if args.list:
        print("Eva verifier sweep")
        for name, scripts in PROFILES.items():
            print(f"{name}:")
            selected = [script for script in scripts if not args.tag or args.tag in VERIFIER_DESCRIPTORS.get(script, {}).get("tags", ())]
            for script in selected:
                if args.metadata:
                    descriptor = VERIFIER_DESCRIPTORS.get(script, {})
                    tags = ", ".join(str(tag) for tag in descriptor.get("tags", ()))
                    print(f"- {script} [{tags}]")
                else:
                    print(f"- {script}")
        return 0

    results: list[tuple[str, int, float]] = []
    skipped = 0
    child_env = os.environ.copy()
    child_env["EVA_VERIFY_SKIP_NESTED"] = "1"
    for script in verifiers:
        path = ROOT / "scripts" / script
        started = time.perf_counter()
        if not path.exists():
            elapsed = time.perf_counter() - started
            print(f"FAIL {script} ({elapsed:.1f}s): missing")
            results.append((script, 1, elapsed))
            if not args.continue_on_fail:
                break
            continue
        try:
            completed = subprocess.run([sys.executable, str(path)], cwd=str(ROOT), text=True, capture_output=True, timeout=args.timeout, env=child_env)
        except subprocess.TimeoutExpired as exc:
            elapsed = time.perf_counter() - started
            print(f"FAIL {script} ({elapsed:.1f}s): timed out after {args.timeout:.1f}s")
            if exc.stdout or exc.stderr:
                tail = "\n".join(((exc.stdout or "") + (exc.stderr or "")).splitlines()[-40:])
                if tail:
                    print(tail)
            results.append((script, 1, elapsed))
            if not args.continue_on_fail:
                break
            continue
        elapsed = time.perf_counter() - started
        status = "PASS" if completed.returncode == 0 else "FAIL"
        print(f"{status} {script} ({elapsed:.1f}s)")
        if completed.returncode != 0:
            tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-40:])
            if tail:
                print(tail)
        results.append((script, completed.returncode, elapsed))
        if completed.returncode != 0 and not args.continue_on_fail:
            break

    failures = [item for item in results if item[1] != 0]
    print("")
    print("Eva verifier summary")
    print(f"Profile: {profile}")
    print(f"Total scripts: {len(verifiers)}")
    print(f"Ran: {len(results)}")
    print(f"Passed: {len(results) - len(failures)}")
    print(f"Failed: {len(failures)}")
    print(f"Skipped: {len(verifiers) - len(results) + skipped}")
    print(f"Elapsed: {sum(item[2] for item in results):.1f}s")
    if failures:
        print(f"Failed script: {failures[0][0]}")
        print("Suggested next command: rerun the failed verifier directly, then rerun this profile.")
    elif profile == "quick":
        print(r"Suggested next command: .\.venv\Scripts\python.exe scripts\verify_eva_all.py --full")
    else:
        print(r"Suggested next command: git diff --check")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
