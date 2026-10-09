from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


EXPECTED_SAFE_IDS = {
    "research_memory.status",
    "research_memory.help",
    "research_memory.recent",
    "research_memory.topics",
    "research_memory.search",
    "research_memory.retrieve",
    "research_memory.topic_summary",
    "research_memory.import_note",
    "research_memory.export_json",
    "research_memory.stats",
    "research_memory.tags",
    "research_memory.quality",
    "research_memory.duplicates_preview",
    "eva_v2.agent_status",
    "eva_v2.route_preview",
    "eva_v2.plan_preview",
    "eva_v2.dry_run",
    "eva_v2.read_only_delegation_status",
    "public_release.public_status",
    "public_release.hardening_audit",
    "public_release.ready_check",
    "public_release.demo_scenarios",
    "public_release.safety_simulator",
    "public_release.resource_registry_listing",
}

FORBIDDEN_ENABLED_MARKERS = {
    "mcp.execution",
    "playwright.execution",
    "pyautogui.execution",
    "whatsapp.send",
    "browser.control",
    "screen.watch",
    "shell.arbitrary",
    "cloud_embeddings",
}


def emit(case: str, passed: bool, **payload: Any) -> int:
    ok = bool(passed)
    print(json.dumps({"case": case, "pass": ok, **payload}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def clean_output(text: str) -> bool:
    blocked = ("{'", "Capability(", "sqlite3.Row", "Traceback", "C:\\Users\\", "C:/Users/", ".env.local", ".env", "backend/eva/data")
    return bool(text and not any(marker in text for marker in blocked))


def main() -> int:
    failures = 0
    try:
        from backend.eva.capabilities.models import Capability
        from backend.eva.capabilities.provider import BaseCapabilityProvider
        from backend.eva.capabilities.registry import (
            CapabilityRegistry,
            build_default_registry,
            format_capability_detail,
            format_capability_providers,
            format_capability_summary,
        )
        from backend.eva.core.fast_commands import maybe_handle_fast_command
        from backend.eva.tools.registry import ToolRegistry
    except Exception as exc:
        failures += emit("capability_package_imports", False, error=str(exc))
        print(json.dumps({"overall_pass": False, "failures": failures}, indent=2))
        return 1

    failures += emit("capability_package_imports", True)
    failures += emit("capability_model_exists", hasattr(Capability, "__dataclass_fields__") and "verifier_name" in Capability.__dataclass_fields__)
    failures += emit("provider_protocol_exists", hasattr(BaseCapabilityProvider, "__annotations__"))

    registry = build_default_registry()
    capabilities = registry.list_capabilities()
    by_id = {capability.id: capability for capability in capabilities}
    providers = registry.providers()

    failures += emit("registry_loads", isinstance(registry, CapabilityRegistry) and bool(capabilities), count=len(capabilities))
    failures += emit("capability_ids_unique", registry.validate_unique_ids() and len(by_id) == len(capabilities))
    failures += emit("expected_safe_capabilities_visible", EXPECTED_SAFE_IDS.issubset(by_id), missing=sorted(EXPECTED_SAFE_IDS - set(by_id)))
    failures += emit("providers_visible", {"research_memory", "eva_v2", "public_release"}.issubset(set(providers)), providers=providers)

    research = registry.list_capabilities(provider="research_memory")
    read_only = registry.list_capabilities(enabled=True, risk_level="low")
    public = registry.list_capabilities(category="public_release")
    failures += emit("filter_by_provider_works", {cap.id for cap in research} >= {"research_memory.search", "research_memory.retrieve"})
    failures += emit("filter_by_category_works", {cap.id for cap in public} >= {"public_release.ready_check", "public_release.demo_scenarios"})
    failures += emit("filter_by_enabled_and_risk_works", bool(read_only) and all(cap.enabled_by_default and cap.risk_level == "low" for cap in read_only))

    detail = registry.get("research_memory.search")
    failures += emit("get_capability_by_id", detail is not None and detail.name == "Search Research Memory")

    risky_or_experimental = [cap for cap in capabilities if cap.risk_level in {"high", "critical"} or cap.status == "experimental"]
    failures += emit("risky_or_experimental_disabled_by_default", all(not cap.enabled_by_default for cap in risky_or_experimental), ids=[cap.id for cap in risky_or_experimental])
    enabled_ids = {cap.id for cap in capabilities if cap.enabled_by_default}
    failures += emit("no_forbidden_systems_enabled", not any(marker in enabled_ids for marker in FORBIDDEN_ENABLED_MARKERS), enabled=sorted(enabled_ids))

    summary = format_capability_summary(registry)
    safe_summary = format_capability_summary(registry, safe_only=True)
    experimental_summary = format_capability_summary(registry, experimental_only=True)
    provider_summary = format_capability_providers(registry)
    detail_text = format_capability_detail(registry, "research_memory.search")
    missing_text = format_capability_detail(registry, "missing.capability")
    outputs = [summary, safe_summary, experimental_summary, provider_summary, detail_text, missing_text]
    failures += emit("formatters_human_readable", all(clean_output(text) for text in outputs), outputs=outputs)
    failures += emit("safe_summary_mentions_safe_only", "safe enabled capabilities" in safe_summary.lower() and "Research Memory" in safe_summary)
    failures += emit("experimental_summary_graceful", "Experimental capabilities" in experimental_summary and clean_output(experimental_summary))
    failures += emit("missing_detail_friendly", "not found" in missing_text.lower() and clean_output(missing_text), output=missing_text)

    tools = ToolRegistry()
    command_cases = {
        "eva capabilities": "Eva capabilities",
        "eva capabilities safe": "Safe enabled capabilities",
        "eva capabilities experimental": "Experimental capabilities",
        "eva capability providers": "Capability providers",
        "eva capability research_memory.search": "Search Research Memory",
    }
    for command, expected in command_cases.items():
        handled = maybe_handle_fast_command(command, tools, {})
        text = handled[0] if handled else ""
        failures += emit(
            f"command_{command.replace(' ', '_').replace('.', '_')}",
            handled is not None and expected in text and clean_output(text),
            output=text,
        )

    source_roots = [ROOT / "backend" / "eva" / "capabilities"]
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace").lower()
        for root in source_roots
        for path in ([root] if root.is_file() else root.rglob("*.py"))
    )
    failures += emit("no_env_local_read", "open('.env.local" not in source_text and 'open(\".env.local' not in source_text)
    from _source_guard import no_browser_drivers, no_network, no_package_install, no_shell

    # Real imports/calls only; the old substring scan failed on prose like "no verifier subprocesses".
    install = no_package_install(source_roots)[0] + no_shell(source_roots)[0]
    failures += emit("no_package_install_attempt", not install, found=[str(f) for f in install])
    control = no_network(source_roots)[0] + no_browser_drivers(source_roots)[0]
    failures += emit("no_network_or_browser_control_attempt", not control, found=[str(f) for f in control])
    failures += emit("normal_chat_v2_not_enabled", "EVA_V2_RUNTIME_ENABLED=true" not in source_text)

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
