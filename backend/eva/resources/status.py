from __future__ import annotations

from .registry import evaluate_resource_by_id, get_all_resources, get_resource, list_resources, resource_registry_status


def format_resource_registry_status() -> str:
    status = resource_registry_status()
    mcp_count = len(list_resources(kind="mcp_server"))
    external_default_enabled = sum(1 for resource in get_all_resources() if resource.provider != "Eva" and resource.default_enabled)
    return "\n".join(
        [
            "Eva resource registry status",
            "",
            f"Total resources: {status.total_resources}",
            f"Allowed resources: {status.allowed_count}",
            f"Experimental resources: {status.experimental_count}",
            f"Reference-only resources: {status.reference_only_count}",
            f"Blocked resources: {status.blocked_count}",
            f"High-risk resources: {status.high_risk_count}",
            f"Default enabled resources: {status.default_enabled_count}",
            f"Default enabled external tools: {external_default_enabled}",
            f"MCP servers cataloged: {mcp_count}",
            "MCP servers enabled: 0",
            "",
            "Policy:",
            "MCP tools are cataloged but disabled by default.",
            "Browser/desktop automation requires permission.",
            "Send/delete/system-changing tools require confirmation or override.",
            "The registry does not install packages, run servers, call the network, or read secrets.",
        ]
    )


def format_mcp_policy_status() -> str:
    resources = list_resources(kind="mcp_server")
    experimental = [resource.id for resource in resources if resource.status == "experimental"]
    reference = [resource.id for resource in resources if resource.status == "reference_only"]
    return "\n".join(
        [
            "MCP policy status",
            "",
            f"MCP servers cataloged: {len(resources)}",
            "MCP servers enabled: 0",
            "Default policy: disabled by default.",
            "",
            "Trust model:",
            "No MCP server is auto-installed, auto-run, or trusted by catalog presence.",
            "No MCP server may receive secrets by default.",
            "Repo write, PR, merge, delete, send, submit, or system-changing actions require confirmation or override.",
            "",
            "Experimental entries: " + (", ".join(experimental) if experimental else "none"),
            "Reference-only entries: " + (", ".join(reference) if reference else "none"),
        ]
    )


def format_open_source_tools_status() -> str:
    resources = [resource for resource in get_all_resources() if resource.kind != "mcp_server"]
    experimental = [resource.id for resource in resources if resource.status == "experimental"]
    allowed = [resource.id for resource in resources if evaluate_resource_by_id(resource.id).allowed]
    return "\n".join(
        [
            "Open-source tool catalog",
            "",
            f"Cataloged non-MCP resources: {len(resources)}",
            f"Allowed existing/internal resources: {len(allowed)}",
            f"Experimental external resources: {len(experimental)}",
            "New external packages are not installed or enabled by this registry.",
            "Desktop/browser automation adapters remain disabled unless explicitly configured and tested.",
            "",
            "Experimental: " + (", ".join(experimental) if experimental else "none"),
        ]
    )


def format_resource_detail(resource_id: str) -> str:
    resource = get_resource(resource_id)
    decision = evaluate_resource_by_id(resource_id)
    if resource is None:
        return "\n".join(["Resource detail", "", f"Resource id: {resource_id}", "Cataloged: no", "Registry status: unknown or blocked", "Executable now: no", f"Reason: {decision.reason}"])
    return "\n".join(
        [
            "Resource detail",
            "",
            f"ID: {resource.id}",
            f"Name: {resource.name}",
            "Cataloged: yes",
            f"Category: {resource.category}",
            f"Kind: {resource.kind}",
            f"Provider: {resource.provider}",
            f"Registry status: {decision.status}",
            f"Risk level: {decision.risk_level}",
            f"Default enabled: {'yes' if resource.default_enabled else 'no'}",
            f"Executable now: {'yes' if decision.executable_now else 'no'}",
            f"Permission required: {'yes' if decision.permission_required else 'no'}",
            f"Override required: {'yes' if decision.override_required else 'no'}",
            f"Feature flag: {resource.feature_flag or 'none'}",
            f"Policy decision: {'catalog-allowed' if decision.allowed else 'not executable'}",
            f"Reason: {decision.reason}",
            f"Notes: {resource.notes}",
        ]
    )


def format_resources_by_status(status: str) -> str:
    wanted = str(status or "").strip().lower()
    labels = {
        "safe": "Safe resources",
        "experimental": "Experimental resources",
        "blocked": "Blocked resources",
    }
    if wanted == "safe":
        resources = [resource for resource in get_all_resources() if evaluate_resource_by_id(resource.id).allowed and resource.risk_level == "low"]
    elif wanted == "experimental":
        resources = [resource for resource in get_all_resources() if resource.status == "experimental"]
    elif wanted == "blocked":
        resources = [resource for resource in get_all_resources() if not evaluate_resource_by_id(resource.id).allowed]
    else:
        resources = []
    lines = [labels.get(wanted, "Resources"), "", f"Count: {len(resources)}"]
    if resources:
        for resource in sorted(resources, key=lambda item: (item.category, item.id))[:40]:
            decision = evaluate_resource_by_id(resource.id)
            lines.append(f"- {resource.id}: {resource.name} ({resource.category}, risk {decision.risk_level}, {decision.status})")
    else:
        lines.append("No matching resources are currently cataloged.")
    lines.extend(["", "Explorer scope: catalog view only; no tools were run and no network call was made."])
    return "\n".join(lines)


def format_resource_categories() -> str:
    counts: dict[str, int] = {}
    for resource in get_all_resources():
        counts[resource.category] = counts.get(resource.category, 0) + 1
    lines = ["Resource categories", "", f"Categories: {len(counts)}"]
    for category, count in sorted(counts.items()):
        lines.append(f"- {category}: {count}")
    lines.extend(["", "Explorer scope: catalog view only; no tools were run and no network call was made."])
    return "\n".join(lines)
