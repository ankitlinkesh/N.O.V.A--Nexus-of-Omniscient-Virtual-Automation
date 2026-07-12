from __future__ import annotations

import dataclasses
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CAPABILITIES = tuple(
    f"release.{name}"
    for name in (
        "status",
        "demo",
        "commands",
        "capability_map",
        "safety_proof",
        "readiness",
        "limitations",
        "verification",
    )
)

COMMANDS = (
    "eva release status",
    "eva release demo",
    "eva release commands",
    "eva release capability map",
    "eva release safety proof",
    "eva release readiness",
    "eva release limitations",
    "eva release verification",
)

ASK_ROUTES = {
    "show release status": "release_status",
    "show public demo": "release_demo",
    "show demo commands": "release_commands",
    "show capability map": "release_capability_map",
    "show safety proof": "release_safety_proof",
    "show release readiness": "release_readiness",
    "show known limitations": "release_limitations",
    "is Eva ready for demo": "release_readiness",
    "what can Eva do": "release_capability_map",
    "what can Eva not do": "release_limitations",
}

REQUIRED_MODEL_FIELDS = (
    "release_demo_id",
    "release_phase",
    "demo_readiness_status",
    "verified_milestone_summary",
    "capability_map_summary",
    "demo_command_list",
    "safety_proof_summary",
    "known_limitations",
    "verification_summary",
    "blocked_feature_summary",
    "public_facing_disclaimer",
    "next_safe_step",
    "final_readiness_status",
    "no_secret_exposure_statement",
    "no_real_provider_call_statement",
    "no_browser_control_statement",
    "no_desktop_control_statement",
    "no_source_edit_statement",
    "no_shell_execution_statement",
    "no_unrestricted_crawler_statement",
    "no_new_write_path_statement",
)

BOUNDARIES = (
    "no publishing was performed",
    "no commit was made",
    "no secrets were read or exposed",
    "no live llm/api/provider call was made",
    "no browser control is enabled",
    "no desktop control is enabled",
    "no codingagent source editing is enabled",
    "no shell/test/package/git execution is enabled",
    "no unrestricted crawler is enabled",
    "phase 12l remains a gated write path",
)


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def check_human_safe(text: str) -> None:
    lowered = text.lower()
    check(text.strip() and len(text.splitlines()) >= 4, "output is not human-readable")
    for phrase in BOUNDARIES:
        check(phrase in lowered, f"missing boundary: {phrase}")
    for token in ("traceback", "{'", "c:\\users\\", "token=", "password=", "dataclass("):
        check(token not in lowered, f"unsafe output token: {token}")


def main() -> int:
    from backend.eva.release_demo.capability_map import capability_map_text
    from backend.eva.release_demo.demo_commands import demo_commands_text
    from backend.eva.release_demo.demo_profile import build_demo_profile
    from backend.eva.release_demo.formatter import (
        format_release_capability_map,
        format_release_commands,
        format_release_demo,
        format_release_limitations,
        format_release_readiness,
        format_release_safety_proof,
        format_release_status,
        format_release_verification,
    )
    from backend.eva.release_demo.known_limitations import known_limitations_text
    from backend.eva.release_demo.models import ReleaseDemoProfile
    from backend.eva.release_demo.release_readiness import release_readiness_text
    from backend.eva.release_demo.safety_proof import safety_proof_text
    from backend.eva.release_demo.status import get_release_demo_status
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.core.natural_router import route_natural_request
    from backend.eva.tools.registry import ToolRegistry
    from backend.eva.control_center.collector import collect_control_center_status
    from backend.eva.control_center.formatter import format_control_center_status
    from backend.eva.capabilities.registry import get_capability
    from backend.eva.capabilities.resource_mapping import resolve_capability
    from backend.eva.capabilities.tool_schemas import capability_to_tool_schema
    from backend.eva.planner.capability_selector import select_capabilities_for_goal
    from backend.eva.planner.decomposer import create_task_plan
    from backend.eva.agents.team_review import format_team_review
    from scripts import verify_eva_all

    for text in (
        capability_map_text(),
        demo_commands_text(),
        safety_proof_text(),
        release_readiness_text(),
        known_limitations_text(),
    ):
        check(len(text.splitlines()) >= 5, "release-demo component is not human-readable")

    profile = build_demo_profile()
    check(isinstance(profile, ReleaseDemoProfile), "release demo profile type mismatch")
    fields = {field.name for field in dataclasses.fields(profile)}
    for field in REQUIRED_MODEL_FIELDS:
        check(field in fields, f"release demo model field missing: {field}")
    check(profile.demo_command_list and profile.known_limitations, "release demo profile is incomplete")
    check(
        profile.next_safe_step.startswith("user-approved commit execution outside Eva"),
        "next safe step is incorrect",
    )
    check(get_release_demo_status().publishing_enabled is False, "publishing must remain disabled")

    outputs = (
        format_release_status(),
        format_release_demo(),
        format_release_commands(),
        format_release_capability_map(),
        format_release_safety_proof(),
        format_release_readiness(),
        format_release_limitations(),
        format_release_verification(),
    )
    for output in outputs:
        check_human_safe(output)

    for command in COMMANDS:
        result = maybe_handle_fast_command(command, ToolRegistry())
        check(result is not None, f"release command missing: {command}")
        check_human_safe(result[0])
    for prompt, expected_intent in ASK_ROUTES.items():
        route = route_natural_request(prompt)
        check(route.intent == expected_intent and not route.real_execution_requested, f"unsafe release ask route: {prompt}")
        result = maybe_handle_fast_command(f"eva ask {prompt}", ToolRegistry())
        check(result is not None, f"release ask command missing: {prompt}")
        check_human_safe(result[0])

    control = collect_control_center_status()
    check(hasattr(control, "release_demo_summary"), "Control Center release summary is missing")
    control_text = format_control_center_status(control)
    check("Public Demo / Release" in control_text, "Control Center release panel is missing")
    check("Release Candidate Hardening" in control_text, "Control Center next safe step is missing")

    from backend.eva.ai_os.system_map import system_map_text
    from backend.eva.ai_os.capability_matrix import capability_matrix_text
    from backend.eva.ai_os.feature_states import feature_states_text

    ai_os_text = system_map_text() + capability_matrix_text() + feature_states_text()
    for phrase in (
        "Public Demo / Release",
        "report/status/profile only",
        "no publishing",
        "Release Candidate Hardening",
    ):
        check(phrase.lower() in ai_os_text.lower(), f"AI OS release state missing: {phrase}")

    for capability_id in CAPABILITIES:
        check(get_capability(capability_id) is not None, f"release capability missing: {capability_id}")
        resolution = resolve_capability(capability_id)
        check(resolution.execution_path == "fast_command", f"release resource mapping missing: {capability_id}")
        schema = capability_to_tool_schema(capability_id)
        check(schema is not None and schema.get("execution_status") == "report_only", f"release schema missing: {capability_id}")
        schema_text = str(schema).lower()
        for phrase in (
            "no publish/upload",
            "no git commit/tag/push",
            "no source-code edits",
            "no arbitrary filesystem reads/writes",
            "no live llm/api/provider calls",
            "phase 12l",
        ):
            check(phrase in schema_text, f"release schema boundary missing for {capability_id}: {phrase}")

    selected = select_capabilities_for_goal("show release readiness")
    check("release.readiness" in selected, "planner selector is missing release.readiness")
    plan = create_task_plan("show public demo")
    check(any(step.capability_id == "release.demo" for step in plan.steps), "planner release-demo step is missing")
    for step in plan.steps:
        text = f"{step.title} {step.description}".lower()
        for forbidden in ("publish package", "git commit", "git tag", "git push", "run shell", "browser control", "desktop control"):
            check(forbidden not in text, f"planner created release execution step: {forbidden}")

    review = format_team_review("review Phase 29 Public Demo Release")
    for phrase in (
        "documentation/report/status/profile only",
        "no publishing happens",
        "no commit/tag/push happens",
        "no source-code edits happen through CodingAgent",
        "no browser/desktop control happens",
        "no shell/test/package/git execution happens",
        "no tool execution happens",
        "no live LLM/API calls are made",
        "no arbitrary file reads/writes happen",
        "no secret/config/session reads happen",
        "Phase 12L narrow real-create remains a gated file write path",
        "user-approved commit execution outside Eva",
    ):
        check(phrase.lower() in review.lower(), f"team review release boundary missing: {phrase}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_lower = readme.lower()
    for phrase in ("what is eva", "demo commands", "capabilities", "verification", "safety boundaries", "known limitations", "non-goals"):
        check(phrase in readme_lower, f"README public section missing: {phrase}")
    check("c:\\users\\" not in readme_lower, "README exposes a private path")

    required_phase_text = "Phase 29 Public Demo / Release is complete after this pass"
    phase_docs = (
        "EVA_CURRENT_STATE.md",
        "EVA_CAPABILITIES.md",
        "EVA_AGENT_FRAMEWORK.md",
        "EVA_THREAT_MODEL.md",
        "EVA_VERIFICATION.md",
    )
    for doc_name in phase_docs:
        text = (ROOT / "docs" / doc_name).read_text(encoding="utf-8")
        check(required_phase_text in text, f"Phase 29 documentation missing: {doc_name}")

    for doc_name in (
        "EVA_PUBLIC_DEMO.md",
        "EVA_DEMO_SCRIPT.md",
        "EVA_DEMO_COMMANDS.md",
        "EVA_RELEASE_READINESS.md",
        "EVA_SAFETY_PROOF.md",
        "EVA_LIMITATIONS.md",
        "EVA_CAPABILITY_MAP.md",
    ):
        path = ROOT / "docs" / doc_name
        check(path.exists() and len(path.read_text(encoding="utf-8").splitlines()) >= 8, f"public demo doc missing: {doc_name}")

    verifier_name = "verify_eva_public_demo_release.py"
    check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full verifier profile is missing Phase 29")
    check(verifier_name in verify_eva_all.QUICK_VERIFIERS, "quick verifier profile is missing Phase 29")

    source_text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (ROOT / "backend" / "eva" / "release_demo").glob("*.py")
    )
    forbidden_runtime_surfaces = (
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
    )
    for token in forbidden_runtime_surfaces:
        check(token not in source_text, f"forbidden release-demo runtime surface: {token}")

    print("PASS: Phase 29 Public Demo / Release is local, report-only, and publication-locked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
