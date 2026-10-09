from __future__ import annotations

import json
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


def main() -> int:
    failures = 0

    try:
        from backend.eva.resources.models import EvaResource
        from backend.eva.resources.registry import (
            evaluate_resource_by_id,
            get_all_resources,
            get_resource,
            resource_registry_status,
        )
        from backend.eva.resources.risk_policy import evaluate_resource
        from backend.eva.resources.status import (
            format_mcp_policy_status,
            format_open_source_tools_status,
            format_resource_detail,
            format_resource_registry_status,
        )
    except Exception as exc:
        failures += emit("resources_package_imports", False, error=str(exc))
        print(json.dumps({"overall_pass": False, "failures": failures}, indent=2))
        return 1

    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.tools.registry import ToolRegistry

    failures += emit("resources_package_imports", True)

    resources = get_all_resources()
    by_id = {resource.id: resource for resource in resources}
    failures += emit("get_all_resources_non_empty", bool(resources), count=len(resources))

    expected_open_source = {
        "langgraph",
        "promptfoo",
        "langfuse",
        "chromadb",
        "qdrant",
        "playwright-python",
        "pyautogui",
    }
    failures += emit("open_source_entries_present", expected_open_source.issubset(by_id), missing=sorted(expected_open_source - set(by_id)))

    expected_mcp = {"official-mcp-servers-registry", "github-mcp-server", "playwright-mcp", "context7-mcp"}
    failures += emit("mcp_entries_present", expected_mcp.issubset(by_id), missing=sorted(expected_mcp - set(by_id)))

    mcp_resources = [resource for resource in resources if resource.kind == "mcp_server"]
    failures += emit("all_mcp_default_disabled", bool(mcp_resources) and all(not resource.default_enabled for resource in mcp_resources), mcp=[resource.id for resource in mcp_resources])
    failures += emit("github_mcp_not_default_enabled", get_resource("github-mcp-server") is not None and not get_resource("github-mcp-server").default_enabled)
    failures += emit("playwright_mcp_not_default_enabled", get_resource("playwright-mcp") is not None and not get_resource("playwright-mcp").default_enabled)

    pyautogui_decision = evaluate_resource_by_id("pyautogui")
    failures += emit(
        "pyautogui_high_risk_or_permission_required",
        pyautogui_decision.risk_level in {"high", "critical"} or pyautogui_decision.permission_required,
        decision=pyautogui_decision.as_dict(),
    )
    playwright = get_resource("playwright-python")
    failures += emit("playwright_python_not_default_enabled", playwright is not None and not playwright.default_enabled)

    hidden = EvaResource(
        id="camera-always-on-hidden-monitoring",
        name="Hidden Monitor",
        category="unsafe",
        provider="test",
        kind="local_adapter",
        license_hint=None,
        homepage=None,
        repo=None,
        local_only=True,
        cloud_capable=False,
        requires_api_key=False,
        requires_network=False,
        can_read_files=False,
        can_write_files=False,
        can_execute_code=False,
        can_control_browser=False,
        can_control_desktop=True,
        can_send_external_messages=False,
        can_delete_or_modify_system=False,
        default_enabled=False,
        feature_flag=None,
        risk_level="critical",
        status="blocked",
        notes="unsafe hidden monitoring test",
    )
    shell = EvaResource(
        id="arbitrary-shell-runner",
        name="Shell Runner",
        category="unsafe",
        provider="test",
        kind="local_adapter",
        license_hint=None,
        homepage=None,
        repo=None,
        local_only=True,
        cloud_capable=False,
        requires_api_key=False,
        requires_network=False,
        can_read_files=True,
        can_write_files=True,
        can_execute_code=True,
        can_control_browser=False,
        can_control_desktop=False,
        can_send_external_messages=False,
        can_delete_or_modify_system=True,
        default_enabled=False,
        feature_flag=None,
        risk_level="critical",
        status="blocked",
        notes="unsafe arbitrary shell test",
    )
    failures += emit("hidden_monitoring_style_resource_blocked", evaluate_resource(hidden).allowed is False)
    failures += emit("arbitrary_shell_style_resource_blocked", evaluate_resource(shell).allowed is False)

    status = resource_registry_status()
    registry_text = format_resource_registry_status()
    mcp_text = format_mcp_policy_status()
    open_source_text = format_open_source_tools_status()
    detail_text = format_resource_detail("github-mcp-server")
    failures += emit(
        "resource_registry_status_human_readable",
        status.total_resources == len(resources)
        and "Eva resource registry status" in registry_text
        and "{'" not in registry_text
        and "EvaResource(" not in registry_text,
        status=status.as_dict(),
        text=registry_text,
    )
    failures += emit(
        "mcp_status_text_disabled_by_default",
        "disabled by default" in mcp_text.lower() and "MCP" in mcp_text and "{'" not in mcp_text,
        text=mcp_text,
    )
    failures += emit("open_source_status_text_clean", "Open-source tool catalog" in open_source_text and "{'" not in open_source_text, text=open_source_text)
    failures += emit(
        "resource_detail_github_mcp_clean",
        "github-mcp-server" in detail_text and "default enabled: no" in detail_text.lower() and "{'" not in detail_text and "EvaResource(" not in detail_text,
        text=detail_text,
    )

    tools = ToolRegistry()
    command_cases = {
        "resource registry status": "Eva resource registry status",
        "resources status": "Eva resource registry status",
        "mcp status": "MCP policy status",
        "mcp policy status": "MCP policy status",
        "open source tools status": "Open-source tool catalog",
        "resource detail github-mcp-server": "github-mcp-server",
    }
    for command, expected in command_cases.items():
        handled = maybe_handle_fast_command(command, tools, {})
        text = handled[0] if handled else ""
        failures += emit(
            f"command_{command.replace(' ', '_')}",
            handled is not None and expected in text and "{'" not in text and "EvaResource(" not in text,
            response=text,
        )

    dry = maybe_handle_fast_command("eva v2 plan inspect my repo with GitHub MCP", tools, {})
    dry_text = dry[0] if dry else ""
    failures += emit(
        "dry_run_plan_includes_resource_hint",
        "Resource hint:" in dry_text and "github-mcp-server" in dry_text and "disabled by default" in dry_text.lower(),
        response=dry_text,
    )

    source_roots = [ROOT / "backend" / "eva" / "resources", ROOT / "backend" / "eva" / "core" / "fast_commands.py"]
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace").lower()
        for root in source_roots
        for path in ([root] if root.is_file() else root.rglob("*.py"))
    )
    failures += emit("no_env_local_read", "open('.env.local" not in source_text and 'open(".env.local' not in source_text)
    from _source_guard import no_network, no_package_install, no_shell

    # Real imports/calls only; the old substring scan matched help text and "ordinary requests." in a comment.
    install = no_package_install(source_roots)[0] + no_shell(source_roots)[0]
    failures += emit("no_package_install_attempt", not install, found=[str(f) for f in install])
    network = no_network(source_roots)[0]
    failures += emit("no_network_call_attempt", not network, found=[str(f) for f in network])

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
