from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def emit(case: str, passed: bool, **payload: Any) -> int:
    ok = bool(passed)
    print(json.dumps({"case": case, "pass": ok, **payload}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def clean_output(text: str) -> bool:
    blocked = (
        "{'",
        "Capability(",
        "CapabilityPermission(",
        "ToolSchema(",
        "sqlite3.Row",
        "Traceback",
        "C:\\Users\\",
        "C:/Users/",
        "backend/eva/data",
        "raw_vector",
    )
    return bool(text and not any(marker in text for marker in blocked))


from _nested import run_nested as _shared_run_nested  # noqa: E402


def run_nested(script_name: str) -> tuple[bool, str]:
    # Shared runner: UTF-8 output, one level deep, one timeout (scripts/_nested.py).
    return _shared_run_nested(script_name)


def main() -> int:
    failures = 0
    try:
        from backend.eva.capabilities.permissions import (
            CapabilityPermission,
            evaluate_capability_permission,
            format_capability_permission_detail,
            format_capability_permission_matrix,
            format_threat_model_status,
            get_capability_permission,
        )
        from backend.eva.capabilities.registry import build_default_registry, format_capability_detail
        from backend.eva.capabilities.tool_schemas import (
            capability_to_tool_schema,
            format_tool_schema_catalog,
            format_tool_schema_preview,
        )
        from backend.eva.core.fast_commands import maybe_handle_fast_command
        from backend.eva.resources.registry import get_resource
        from backend.eva.tools.registry import ToolRegistry
    except Exception as exc:
        failures += emit("phase_9b_imports", False, error=str(exc))
        print(json.dumps({"overall_pass": False, "failures": failures}, indent=2))
        return 1

    failures += emit("phase_9b_imports", True)

    registry = build_default_registry()
    retrieve_cap = registry.get("research_memory.retrieve")
    retrieve_permission = get_capability_permission("research_memory.retrieve")
    failures += emit(
        "retrieve_public_readonly_allowed",
        isinstance(retrieve_permission, CapabilityPermission)
        and retrieve_permission.public_mode_allowed
        and retrieve_permission.read_only
        and not retrieve_permission.requires_confirmation,
    )
    failures += emit(
        "evaluate_registered_capability",
        retrieve_cap is not None
        and evaluate_capability_permission(retrieve_cap).allowed
        and evaluate_capability_permission(retrieve_cap).public_mode_allowed,
    )

    import_permission = get_capability_permission("research_memory.import_note")
    failures += emit(
        "import_note_explicit_local_write",
        import_permission.writes_local_data
        and import_permission.explicit_user_action
        and not import_permission.silent_background_write
        and import_permission.public_mode_allowed,
    )

    delete_permission = get_capability_permission("research_memory.delete_item")
    clear_permission = get_capability_permission("research_memory.clear_topic")
    failures += emit(
        "delete_and_clear_are_confirmed_scoped_actions",
        delete_permission.requires_confirmation
        and clear_permission.requires_confirmation
        and clear_permission.confirm_phrase_required
        and delete_permission.writes_local_data
        and clear_permission.writes_local_data,
    )

    blocked_ids = ["shell.arbitrary", "mcp.execution", "browser.control", "playwright.execution", "pyautogui.execution"]
    blocked = [get_capability_permission(item) for item in blocked_ids]
    failures += emit(
        "forbidden_future_execution_blocked",
        all(not item.public_mode_allowed and item.blocked_by_default for item in blocked),
        ids=blocked_ids,
    )

    matrix = format_capability_permission_matrix(registry)
    failures += emit(
        "permission_matrix_human_readable",
        clean_output(matrix)
        and "Capability permission matrix" in matrix
        and "Read-only public-safe" in matrix
        and "Blocked by default" in matrix,
        output=matrix,
    )

    detail = format_capability_detail(registry, "research_memory.retrieve")
    permission_detail = format_capability_permission_detail("research_memory.retrieve")
    failures += emit(
        "capability_detail_mentions_permission",
        clean_output(detail)
        and "Permission summary" in detail
        and clean_output(permission_detail)
        and "Public mode: allowed" in permission_detail,
        output=detail,
    )

    schema = capability_to_tool_schema("research_memory.retrieve")
    schema_preview = format_tool_schema_preview("research_memory.retrieve")
    schema_catalog = format_tool_schema_catalog()
    failures += emit(
        "schema_preview_available",
        schema is not None
        and schema.get("capability_id") == "research_memory.retrieve"
        and clean_output(schema_preview)
        and "Tool schema preview" in schema_preview
        and "query" in schema_preview.lower(),
        output=schema_preview,
    )
    failures += emit(
        "schema_catalog_lists_safe_tools",
        clean_output(schema_catalog)
        and "research_memory.retrieve" in schema_catalog
        and "public_release.demo" in schema_catalog,
        output=schema_catalog,
    )

    aliases = {
        "research_memory.save": "Research Memory Save Note",
        "research_memory.export": "Research Memory Export JSON",
        "eva_v2.plan": "Eva v2 Plan Preview",
        "public_release.demo": "Public Release Demo Scenarios",
        "public_release.safety_test": "Public Release Safety Simulator",
        "public_release.doctor": "Public Release Ready Check",
    }
    for capability_id, expected_name in aliases.items():
        item = capability_to_tool_schema(capability_id)
        failures += emit(
            f"schema_alias_{capability_id.replace('.', '_')}",
            isinstance(item, dict) and item.get("name") == expected_name,
        )

    odysseus = get_resource("odysseus-ai-workspace")
    failures += emit(
        "odysseus_reference_resource_registered",
        odysseus is not None
        and odysseus.status == "reference_only"
        and not odysseus.default_enabled
        and odysseus.risk_level == "medium",
    )

    doc_path = ROOT / "docs" / "EVA_THREAT_MODEL.md"
    doc_text = doc_path.read_text(encoding="utf-8", errors="replace") if doc_path.exists() else ""
    required_doc_phrases = [
        "API-backed LLM reasoning when configured",
        "untrusted content as data",
        ".env.local",
        "cookies",
        "tokens",
        "passwords",
        "normal chat is not routed through v2 by default",
    ]
    failures += emit(
        "threat_model_doc_exists",
        doc_path.exists() and all(phrase in doc_text for phrase in required_doc_phrases),
        missing=[phrase for phrase in required_doc_phrases if phrase not in doc_text],
    )

    threat_status = format_threat_model_status()
    failures += emit(
        "threat_model_status_clean",
        clean_output(threat_status)
        and ".env" not in threat_status
        and "Threat model status" in threat_status,
        output=threat_status,
    )

    tools = ToolRegistry()
    command_cases = {
        "eva capabilities matrix": "Capability permission matrix",
        "eva capability permissions": "Capability permission matrix",
        "eva capability permission research_memory.retrieve": "Public mode: allowed",
        "eva capability schema research_memory.retrieve": "Tool schema preview",
        "eva tool schema preview research_memory.retrieve": "Tool schema preview",
        "eva tool schemas": "Tool schema catalog",
        "eva threat model status": "Threat model status",
    }
    for command, expected in command_cases.items():
        handled = maybe_handle_fast_command(command, tools, {})
        text = handled[0] if handled else ""
        failures += emit(
            f"command_{re.sub(r'[^a-z0-9]+', '_', command.lower()).strip('_')}",
            handled is not None and expected in text and clean_output(text),
            output=text,
        )

    source_paths = [
        ROOT / "backend" / "eva" / "capabilities",
        ROOT / "backend" / "eva" / "resources",
    ]
    from _source_guard import no_browser_drivers, no_browser_secret_reads, no_env_local_read, no_package_install

    # Real imports/calls only; "no ... cookie, localStorage" in a tool description is not a cookie read.
    enablement = []
    for check in (no_env_local_read, no_package_install, no_browser_drivers, no_browser_secret_reads):
        enablement += check(source_paths)[0]
    failures += emit("no_forbidden_enablement_added", not enablement, found=[str(f) for f in enablement])

    nested_scripts = [
        "verify_eva_capabilities.py",
        "verify_eva_resource_registry.py",
        "verify_eva_public_release_hardening.py",
        "verify_eva_stabilization_v1.py",
    ]
    if os.environ.get("EVA_VERIFY_SKIP_NESTED") == "1":
        for script_name in nested_scripts:
            failures += emit(f"nested_{script_name}", True, skipped=True, reason="Skipped inside master verifier profile.")
    else:
        for script_name in nested_scripts:
            ok, output = run_nested(script_name)
            failures += emit(f"nested_{script_name}", ok, tail=output)

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
