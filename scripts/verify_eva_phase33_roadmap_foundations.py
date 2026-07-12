from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


EXECUTION_VALUES = {
    "report-only",
    "read-only",
    "sandbox-only",
    "phase12l-write",
    "gated-real-action",
    "blocked",
}

RISKY_TOOL_EXPECTATIONS = {
    "file.write_text": "gated-real-action",
    "file.patch_text": "gated-real-action",
    "file.delete": "gated-real-action",
    "message.send_via_ui": "gated-real-action",
    "screen.click": "gated-real-action",
    "screen.type_text": "gated-real-action",
    "app.open": "gated-real-action",
    "browser_observe": "read-only",
    "workspace_read_file": "read-only",
    "web_search": "read-only",
}

ROADMAP_PHASES = tuple(range(33, 43))

ROADMAP_COMMANDS = {
    "eva roadmap status": "roadmap_status",
    "eva execution boundaries": "execution_boundaries",
    "eva catalog status": "catalog_status",
    "eva frontend truth status": "frontend_truth_status",
    "eva grounded answer status": "grounded_answer_status",
    "eva voice reliability status": "voice_reliability_status",
    "eva verifier dashboard status": "verifier_dashboard_status",
}

ASK_ROUTES = {
    "show Eva roadmap status": "roadmap_status",
    "show execution boundaries": "execution_boundaries",
    "what can Eva actually execute safely": "execution_boundaries",
    "show frontend truth status": "frontend_truth_status",
    "show grounded answer status": "grounded_answer_status",
    "show voice reliability status": "voice_reliability_status",
    "show verifier dashboard status": "verifier_dashboard_status",
}

REQUIRED_DOCS = (
    "EVA_CURRENT_STATE.md",
    "EVA_VERIFICATION.md",
    "EVA_RELEASE_READINESS.md",
    "EVA_BUG_QUEUE.md",
    "EVA_CAPABILITIES.md",
    "EVA_CAPABILITY_MAP.md",
)

FORBIDDEN_NEW_SOURCE_TOKENS = (
    "import subprocess",
    "from subprocess",
    "os.system(",
    "requests.",
    "httpx.",
    "urllib.request",
    "playwright",
    "selenium",
    "pyautogui",
    ".write_text(",
    ".write_bytes(",
    "git push",
    "git commit",
    "git tag",
    "gh release",
)


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def _assert_human_report(text: str, title: str) -> None:
    lowered = text.lower()
    check(title.lower() in lowered, f"missing title in {title}")
    check("phase 33" in lowered, f"phase 33 missing in {title}")
    check("phase 42" in lowered, f"phase 42 missing in {title}")
    check("no new execution path" in lowered, f"execution boundary missing in {title}")
    check("phase 12l" in lowered, f"phase 12L write boundary missing in {title}")
    for token in ("traceback", "token=", "password=", "cookie=", "c:\\users\\"):
        check(token not in lowered, f"unsafe output token in {title}: {token}")


def main() -> int:
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.core.natural_router import route_natural_request
    from backend.eva.roadmap.catalog import (
        get_capability_catalog,
        get_command_catalog,
        get_execution_boundary_catalog,
        get_phase_roadmap,
        get_verifier_catalog,
    )
    from backend.eva.roadmap.formatter import (
        format_catalog_status,
        format_execution_boundary_audit,
        format_frontend_truth_status,
        format_grounded_answer_status,
        format_phase_roadmap,
        format_verifier_dashboard_status,
        format_voice_reliability_status,
    )
    from backend.eva.roadmap.models import (
        CapabilityDescriptor,
        CommandDescriptor,
        ExecutionBoundary,
        ExecutionClass,
        PhaseRoadmapEntry,
        VerifierDescriptor,
    )
    from backend.eva.tools.registry import ToolRegistry
    from backend.eva.capabilities.resource_mapping import resolve_capability
    from scripts import verify_eva_all

    execution_values = {item.value for item in ExecutionClass}
    check(EXECUTION_VALUES.issubset(execution_values), "ExecutionClass values are incomplete")

    boundaries = get_execution_boundary_catalog()
    check(boundaries and all(isinstance(item, ExecutionBoundary) for item in boundaries), "execution boundary catalog missing typed entries")
    by_tool = {item.tool_id: item for item in boundaries if item.tool_id}
    for tool_name, expected_class in RISKY_TOOL_EXPECTATIONS.items():
        boundary = by_tool.get(tool_name)
        check(boundary is not None, f"missing execution boundary for {tool_name}")
        check(boundary.execution_class.value == expected_class, f"wrong execution class for {tool_name}")
        check(boundary.gate and boundary.verifier, f"boundary for {tool_name} lacks gate/verifier")

    catalog = get_capability_catalog()
    check(catalog and all(isinstance(item, CapabilityDescriptor) for item in catalog), "capability catalog missing typed entries")
    capability_ids = {item.capability_id for item in catalog}
    for capability_id in (
        "release.demo_smoke",
        "release.post_push_sync",
        "roadmap.execution_boundary_audit",
        "roadmap.command_catalog",
        "roadmap.capability_catalog",
        "roadmap.frontend_truth",
        "roadmap.grounded_answers",
        "roadmap.voice_reliability",
        "roadmap.verifier_dashboard",
        "roadmap.release_candidate_v2",
    ):
        check(capability_id in capability_ids, f"missing roadmap capability: {capability_id}")

    for capability_id in (
        "roadmap.execution_boundary_audit",
        "roadmap.command_catalog",
        "roadmap.capability_catalog",
        "roadmap.frontend_truth",
        "roadmap.grounded_answers",
        "roadmap.voice_reliability",
        "roadmap.verifier_dashboard",
        "roadmap.release_candidate_v2",
    ):
        resolution = resolve_capability(capability_id)
        check(resolution.final_status == "preview_only", f"roadmap capability is not report/preview-only: {capability_id}")
        check(resolution.allowed_in_public_mode and resolution.risk_level == "low", f"roadmap capability permission drifted: {capability_id}")
    pilot = resolve_capability("roadmap.safe_real_pilot")
    check(pilot.final_status == "blocked" and not pilot.allowed_in_public_mode, "Phase 41 pilot should remain blocked")

    commands = get_command_catalog()
    check(commands and all(isinstance(item, CommandDescriptor) for item in commands), "command catalog missing typed entries")
    by_command = {item.command: item for item in commands}
    for command, intent in ROADMAP_COMMANDS.items():
        descriptor = by_command.get(command)
        check(descriptor is not None, f"missing roadmap command descriptor: {command}")
        check(descriptor.intent == intent, f"wrong intent for command {command}")
        check(descriptor.execution_class.value in {"report-only", "read-only"}, f"unsafe command execution class: {command}")

    verifiers = get_verifier_catalog()
    check(verifiers and all(isinstance(item, VerifierDescriptor) for item in verifiers), "verifier catalog missing typed entries")
    verifier_names = {item.script for item in verifiers}
    check("verify_eva_phase33_roadmap_foundations.py" in verifier_names, "new verifier descriptor missing")
    check("verify_eva_post_push_demo_smoke.py" in verifier_names, "Phase 32 verifier descriptor missing")
    for verifier in verifiers:
        check(verifier.profile in {"quick", "full", "focused"}, f"unknown verifier profile: {verifier.script}")
        check(not verifier.mutates_repo_tracked_files, f"verifier must not mutate tracked files: {verifier.script}")

    phases = get_phase_roadmap()
    check(phases and all(isinstance(item, PhaseRoadmapEntry) for item in phases), "phase roadmap missing typed entries")
    phase_numbers = {item.phase for item in phases}
    for phase in ROADMAP_PHASES:
        check(phase in phase_numbers, f"roadmap phase missing: {phase}")

    outputs = (
        (format_phase_roadmap(), "Eva phase improvement roadmap"),
        (format_execution_boundary_audit(), "Eva execution boundary audit"),
        (format_catalog_status(), "Eva catalog status"),
        (format_frontend_truth_status(), "Eva frontend truth status"),
        (format_grounded_answer_status(), "Eva grounded answer status"),
        (format_voice_reliability_status(), "Eva voice reliability status"),
        (format_verifier_dashboard_status(), "Eva verifier dashboard status"),
    )
    for output, title in outputs:
        _assert_human_report(output, title)

    tools = ToolRegistry()
    for command in ROADMAP_COMMANDS:
        result = maybe_handle_fast_command(command, tools)
        check(result is not None, f"fast command missing: {command}")
        _assert_human_report(result[0], "Eva")

    for prompt, expected_intent in ASK_ROUTES.items():
        route = route_natural_request(prompt)
        check(route.intent == expected_intent, f"natural route intent mismatch: {prompt}")
        check(route.suggested_command in ROADMAP_COMMANDS, f"natural route command mismatch: {prompt}")
        check(not route.real_execution_requested, f"natural route requested real execution: {prompt}")
        result = maybe_handle_fast_command(f"eva ask {prompt}", tools)
        check(result is not None, f"eva ask route missing: {prompt}")

    for doc_name in REQUIRED_DOCS:
        text = (ROOT / "docs" / doc_name).read_text(encoding="utf-8").lower()
        check("phase 33" in text and "phase 42" in text, f"roadmap phases missing in {doc_name}")
        check("execution boundary audit" in text, f"execution boundary audit missing in {doc_name}")
        check("no new execution path" in text, f"new execution boundary missing in {doc_name}")
        check("phase 12l" in text, f"phase 12L boundary missing in {doc_name}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    for phrase in (
        "phase 33",
        "phase 42",
        "eva roadmap status",
        "eva execution boundaries",
        "safe local demo",
        "no new execution path",
    ):
        check(phrase in readme, f"README roadmap phrase missing: {phrase}")

    frontend_index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8").lower()
    frontend_app = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8").lower()
    for phrase in (
        "safe demo",
        "report-only",
        "execution boundaries",
        "voice diagnostics",
        "eva release smoke test",
        "eva roadmap status",
    ):
        check(phrase in frontend_index or phrase in frontend_app, f"frontend truth phrase missing: {phrase}")
    check("open chrome" not in frontend_index, "unsafe quick chip still exposes open chrome")
    check("show screen" not in frontend_index, "unsafe quick chip still exposes show screen")
    check("operator + agentic" not in frontend_index, "overbroad status label remains in HTML")

    verifier_name = "verify_eva_phase33_roadmap_foundations.py"
    check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full profile is missing Phase 33 roadmap verifier")
    check(verifier_name in verify_eva_all.QUICK_VERIFIERS, "quick profile is missing Phase 33 roadmap verifier")
    check(hasattr(verify_eva_all, "VERIFIER_DESCRIPTORS"), "master verifier descriptors missing")
    descriptors = getattr(verify_eva_all, "VERIFIER_DESCRIPTORS")
    check(verifier_name in descriptors, "master verifier descriptor missing new verifier")
    check("phase33" in descriptors[verifier_name].get("tags", ()), "new verifier tags missing phase33")

    roadmap_source = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (ROOT / "backend" / "eva" / "roadmap").glob("*.py")
    )
    for token in FORBIDDEN_NEW_SOURCE_TOKENS:
        check(token not in roadmap_source, f"forbidden roadmap source token: {token}")

    print("PASS: Phase 33 Roadmap Foundations expose audited boundaries, catalogs, truthful UI/docs, and verifier metadata without enabling new execution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
