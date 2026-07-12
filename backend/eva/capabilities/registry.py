from __future__ import annotations

from dataclasses import dataclass

from .models import Capability
from .provider import BaseCapabilityProvider


@dataclass(frozen=True)
class StaticCapabilityProvider:
    provider_id: str
    provider_name: str
    capabilities: tuple[Capability, ...]

    def list_capabilities(self) -> list[Capability]:
        return list(self.capabilities)


class CapabilityRegistry:
    def __init__(self, providers: list[BaseCapabilityProvider] | None = None) -> None:
        self._providers = list(providers or [])
        self._capabilities: list[Capability] = []
        for provider in self._providers:
            self._capabilities.extend(provider.list_capabilities())

    def list_capabilities(
        self,
        *,
        provider: str | None = None,
        category: str | None = None,
        risk_level: str | None = None,
        status: str | None = None,
        enabled: bool | None = None,
    ) -> list[Capability]:
        capabilities = self._capabilities
        if provider is not None:
            capabilities = [cap for cap in capabilities if cap.provider == provider]
        if category is not None:
            capabilities = [cap for cap in capabilities if cap.category == category]
        if risk_level is not None:
            capabilities = [cap for cap in capabilities if cap.risk_level == risk_level]
        if status is not None:
            capabilities = [cap for cap in capabilities if cap.status == status]
        if enabled is not None:
            capabilities = [cap for cap in capabilities if cap.enabled_by_default is enabled]
        return list(capabilities)

    def get(self, capability_id: str) -> Capability | None:
        normalized = str(capability_id or "").strip()
        return next((cap for cap in self._capabilities if cap.id == normalized), None)

    def providers(self) -> list[str]:
        return sorted({provider.provider_id for provider in self._providers})

    def provider_names(self) -> dict[str, str]:
        return {provider.provider_id: provider.provider_name for provider in self._providers}

    def validate_unique_ids(self) -> bool:
        ids = [capability.id for capability in self._capabilities]
        return len(ids) == len(set(ids))


def build_default_registry() -> CapabilityRegistry:
    return CapabilityRegistry(
        [
            StaticCapabilityProvider("research_memory", "Research Memory", tuple(_research_memory_capabilities())),
            StaticCapabilityProvider("eva_v2", "Eva v2", tuple(_eva_v2_capabilities())),
            StaticCapabilityProvider("public_release", "Public Release", tuple(_public_release_capabilities())),
            StaticCapabilityProvider("file_agent", "FileAgent", tuple(_file_agent_capabilities())),
            StaticCapabilityProvider("browser_agent", "BrowserAgent", tuple(_browser_agent_capabilities())),
            StaticCapabilityProvider("desktop_agent", "DesktopAgent", tuple(_desktop_agent_capabilities())),
            StaticCapabilityProvider("coding_agent", "CodingAgent", tuple(_coding_agent_capabilities())),
            StaticCapabilityProvider("release_demo", "Public Demo / Release", tuple(_release_demo_capabilities())),
            StaticCapabilityProvider("release_candidate", "Release Candidate Hardening", tuple(_release_candidate_capabilities())),
            StaticCapabilityProvider("roadmap", "Roadmap Foundations", tuple(_roadmap_capabilities())),
            StaticCapabilityProvider("eva_core", "Eva Core", tuple(_eva_core_capabilities())),
        ]
    )


def get_capability(capability_id: str) -> Capability | None:
    return build_default_registry().get(capability_id)


def format_capability_summary(
    registry: CapabilityRegistry | None = None,
    *,
    safe_only: bool = False,
    experimental_only: bool = False,
) -> str:
    registry = registry or build_default_registry()
    if safe_only:
        title = "Safe enabled capabilities"
        capabilities = [
            cap
            for cap in registry.list_capabilities(enabled=True)
            if cap.risk_level in {"low", "medium"} and cap.status == "stable" and not cap.requires_confirmation
        ]
    elif experimental_only:
        title = "Experimental capabilities"
        capabilities = registry.list_capabilities(status="experimental")
    else:
        title = "Eva capabilities"
        capabilities = registry.list_capabilities()

    lines = [title, "", f"Count: {len(capabilities)}"]
    if not capabilities:
        lines.extend(["", "No matching capabilities are registered in this safe metadata view."])
    else:
        for cap in capabilities:
            flags = []
            flags.append("enabled" if cap.enabled_by_default else "disabled")
            flags.append("read-only" if cap.read_only else "local-write")
            if cap.requires_confirmation:
                flags.append("confirmation")
            lines.append(f"- {cap.id}: {cap.name} ({cap.provider}, {cap.risk_level}, {', '.join(flags)})")
    lines.extend(
        [
            "",
            "Scope:",
            "Metadata/discovery only. No tools were executed and no private runtime data was read.",
        ]
    )
    return "\n".join(lines)


def format_capability_providers(registry: CapabilityRegistry | None = None) -> str:
    registry = registry or build_default_registry()
    names = registry.provider_names()
    lines = ["Capability providers", "", f"Count: {len(names)}"]
    for provider_id in sorted(names):
        count = len(registry.list_capabilities(provider=provider_id))
        lines.append(f"- {provider_id}: {names[provider_id]} ({count} capabilities)")
    lines.extend(["", "Scope: catalog view only; no provider action was executed."])
    return "\n".join(lines)


def format_capability_detail(registry: CapabilityRegistry | None, capability_id: str) -> str:
    registry = registry or build_default_registry()
    capability = registry.get(capability_id)
    if capability is None:
        return "\n".join(
            [
                "Capability detail",
                "",
                f"Capability `{capability_id}` was not found.",
                "Use `eva capabilities` to list available metadata.",
            ]
        )
    enabled = "yes" if capability.enabled_by_default else "no"
    read_only = "yes" if capability.read_only else "no"
    confirmation = "yes" if capability.requires_confirmation else "no"
    verifier = capability.verifier_name or "not specified"
    from .permissions import format_permission_summary_line
    from .tool_schemas import capability_to_tool_schema

    schema_status = "available" if capability_to_tool_schema(capability.id) else "not registered"
    resource_lines: list[str] = []
    try:
        from .resource_mapping import resolve_capability

        resolution = resolve_capability(capability.id)
        resource_lines = [
            f"Resource: {resolution.resource_id or 'none'}",
            f"Resolution status: {resolution.final_status}",
            f"Execution path: {resolution.execution_path}",
        ]
    except Exception:
        resource_lines = ["Resource: mapping unavailable"]
    return "\n".join(
        [
            "Capability detail",
            "",
            f"ID: {capability.id}",
            f"Name: {capability.name}",
            f"Provider: {capability.provider}",
            f"Category: {capability.category}",
            f"Risk: {capability.risk_level}",
            f"Status: {capability.status}",
            f"Enabled by default: {enabled}",
            f"Read-only: {read_only}",
            f"Requires confirmation: {confirmation}",
            f"Verifier: {verifier}",
            format_permission_summary_line(capability.id),
            f"Tool schema preview: {schema_status}",
            *resource_lines,
            "",
            "Description:",
            capability.description,
            "",
            "Safety:",
            capability.safety_notes,
            "",
            "Scope:",
            "Metadata only. Inspecting this capability does not execute the underlying command.",
        ]
    )


def _cap(
    capability_id: str,
    name: str,
    description: str,
    provider: str,
    category: str,
    *,
    risk_level: str = "low",
    read_only: bool = True,
    requires_confirmation: bool = False,
    enabled_by_default: bool = True,
    status: str = "stable",
    safety_notes: str = "Uses existing safe Eva command surfaces only.",
    verifier_name: str | None = None,
) -> Capability:
    return Capability(
        id=capability_id,
        name=name,
        description=description,
        provider=provider,
        category=category,
        risk_level=risk_level,
        read_only=read_only,
        requires_confirmation=requires_confirmation,
        enabled_by_default=enabled_by_default,
        status=status,
        safety_notes=safety_notes,
        verifier_name=verifier_name,
    )


def _research_memory_capabilities() -> list[Capability]:
    verifier = "verify_eva_research_memory_help.py"
    local_notes = "Local Research Memory metadata only; no private page scraping, cloud embeddings, or path output."
    return [
        _cap("research_memory.status", "Research Memory Status", "Show local Research Memory status.", "research_memory", "research_memory", verifier_name=verifier, safety_notes=local_notes),
        _cap("research_memory.help", "Research Memory Help", "Show Research Memory command help.", "research_memory", "research_memory", verifier_name=verifier, safety_notes=local_notes),
        _cap("research_memory.recent", "Recent Research Notes", "List recent sanitized research notes.", "research_memory", "research_memory", verifier_name=verifier, safety_notes=local_notes),
        _cap("research_memory.topics", "Research Topics", "List saved research topics.", "research_memory", "research_memory", verifier_name=verifier, safety_notes=local_notes),
        _cap("research_memory.search", "Search Research Memory", "Lexically search saved local research notes.", "research_memory", "research_memory", verifier_name=verifier, safety_notes=local_notes),
        _cap("research_memory.retrieve", "Retrieve Research Memory", "Retrieve ranked local research snippets.", "research_memory", "research_memory", verifier_name="verify_eva_research_memory_retrieval.py", safety_notes=local_notes),
        _cap("research_memory.topic_summary", "Research Topic Summary", "Summarize a saved research topic from local notes.", "research_memory", "research_memory", verifier_name=verifier, safety_notes=local_notes),
        _cap("research_memory.import_note", "Import Research Note", "Import a user-provided local note after sanitization.", "research_memory", "research_memory", risk_level="medium", read_only=False, verifier_name="verify_eva_research_memory_io.py", safety_notes="Writes only a sanitized local note through the existing Research Memory command."),
        _cap("research_memory.export_json", "Export Research Memory JSON", "Export sanitized saved research to local runtime export storage.", "research_memory", "research_memory", risk_level="medium", read_only=False, verifier_name="verify_eva_research_memory_io.py", safety_notes="Exports sanitized stored notes only and normal output shows filenames, not private paths."),
        _cap("research_memory.stats", "Research Memory Stats", "Show path-free storage statistics.", "research_memory", "research_memory", verifier_name="verify_eva_research_memory_io.py", safety_notes=local_notes),
        _cap("research_memory.tags", "Research Memory Tags", "List normalized tags with counts.", "research_memory", "research_memory", verifier_name="verify_eva_research_memory_quality.py", safety_notes=local_notes),
        _cap("research_memory.quality", "Research Memory Quality", "Preview low-value or duplicate-like notes.", "research_memory", "research_memory", verifier_name="verify_eva_research_memory_quality.py", safety_notes=local_notes),
        _cap("research_memory.duplicates_preview", "Research Memory Duplicates Preview", "Preview duplicate groups without deleting anything.", "research_memory", "research_memory", verifier_name="verify_eva_research_memory_quality.py", safety_notes="Preview only; no merge or delete action is performed."),
        _cap("research_memory.ranking_status", "Research Memory Ranking Status", "Show local ranking, recency, penalty, and diversity status.", "research_memory", "research_memory", verifier_name="verify_eva_research_memory_ranking.py", safety_notes="Read-only ranking status; no notes are changed."),
        _cap("research_memory.recall_stats", "Research Memory Recall Stats", "Show local recall counts without raw queries.", "research_memory", "research_memory", verifier_name="verify_eva_research_memory_ranking.py", safety_notes="Read-only recall metadata; raw query strings are not shown."),
        _cap("research_memory.promote_candidates", "Research Memory Promotion Candidates", "Preview useful long-term note candidates without promotion.", "research_memory", "research_memory", verifier_name="verify_eva_research_memory_ranking.py", safety_notes="Preview only; no auto-promotion or auto-write is performed."),
        _cap("research_memory.review_memory", "Research Memory Review", "Show a local memory review with safe next commands.", "research_memory", "research_memory", verifier_name="verify_eva_research_memory_ranking.py", safety_notes="Read-only review; no delete, merge, or promotion action is performed."),
    ]


def _eva_v2_capabilities() -> list[Capability]:
    notes = "Explicit v2 command metadata only; normal chat is not routed through v2."
    return [
        _cap("eva_v2.agent_status", "Agent Status", "Show bounded agent status.", "eva_v2", "v2", verifier_name="verify_eva_stabilization_v1.py", safety_notes=notes),
        _cap("eva_v2.route_preview", "Route Preview", "Preview an explicit v2 route without executing it.", "eva_v2", "v2", verifier_name="verify_eva_v2_dry_run.py", safety_notes=notes),
        _cap("eva_v2.plan_preview", "Plan Preview", "Preview an explicit v2 plan without executing it.", "eva_v2", "v2", verifier_name="verify_eva_v2_dry_run.py", safety_notes=notes),
        _cap("eva_v2.dry_run", "Dry Run", "Run explicit v2 dry-run planning with no risky execution.", "eva_v2", "v2", verifier_name="verify_eva_v2_dry_run.py", safety_notes=notes),
        _cap("eva_v2.read_only_delegation_status", "Read-only Delegation Status", "Show read-only delegation availability.", "eva_v2", "v2", verifier_name="verify_eva_v2_readonly_delegation.py", safety_notes=notes),
    ]


def _public_release_capabilities() -> list[Capability]:
    notes = "Public/community surface only; no real send, delete, browser automation, desktop automation, or external tool execution."
    return [
        _cap("public_release.public_status", "Public Release Status", "Show public/community release status.", "public_release", "public_release", verifier_name="verify_eva_public_release.py", safety_notes=notes),
        _cap("public_release.hardening_audit", "Public Hardening Audit", "Run repo-local public hardening checks.", "public_release", "public_release", verifier_name="verify_eva_public_release_hardening.py", safety_notes="Reads repo source/docs only; secret files are reported by name and not read."),
        _cap("public_release.ready_check", "Public Ready Check", "Summarize push readiness from the hardening audit.", "public_release", "public_release", verifier_name="verify_eva_public_repo_cleanup.py", safety_notes="Readiness summary only; no staging, commit, push, or network action."),
        _cap("public_release.demo_scenarios", "Demo Scenarios", "List safe simulated public demo scenarios.", "public_release", "public_release", verifier_name="verify_eva_public_release.py", safety_notes=notes),
        _cap("public_release.safety_simulator", "Safety Simulator", "Preview public-mode safety decisions for risky requests.", "public_release", "public_release", verifier_name="verify_eva_public_release.py", safety_notes="Simulation only; no real risky action is executed."),
        _cap("public_release.resource_registry_listing", "Resource Registry Listing", "Show catalog-only resource registry views.", "public_release", "public_release", verifier_name="verify_eva_resource_registry.py", safety_notes="Catalog view only; MCP and external tools remain disabled by default."),
    ]


def _file_agent_capabilities() -> list[Capability]:
    notes = "FileAgent v1 is repo-scoped and read-only; sensitive, secret, runtime, and whole-drive paths are refused."
    understand_notes = "FileAgent v1 uses deterministic local heuristics only; no cloud, LLM, writes, secret reads, or whole-drive scans."
    draft_notes = "FileAgent draft mode is preview-only output; no file is created, written, edited, deleted, moved, copied, or renamed."
    apply_notes = "FileAgent apply-readiness is planning-only; no file is written, backed up, restored, or rolled back."
    approval_notes = "FileAgent approval ledger is metadata-only; approvals are for future apply and do not write, back up, restore, or apply files."
    sandbox_notes = "FileAgent sandbox apply harness writes only ignored runtime sandbox files; real project files are never written, backed up, restored, or applied."
    real_create_notes = "Phase 12L narrow real apply gate: create-new-text-file only; create a new .md/.txt file directly under docs/ or samples/ after exact approved confirmation; no overwrite, existing-file edit, source/config/runtime write, broad delete, move, or rename."
    verifier = "verify_eva_file_agent_readonly.py"
    understand_verifier = "verify_eva_file_agent_understanding.py"
    draft_verifier = "verify_eva_file_agent_draft_preview.py"
    return [
        _cap("file.inspect_path", "Inspect Path", "Inspect safe file or folder metadata.", "file_agent", "file_system", risk_level="medium", verifier_name=verifier, safety_notes=notes),
        _cap("file.list_folder", "List Folder", "List limited entries in an allowed project folder.", "file_agent", "file_system", risk_level="medium", verifier_name=verifier, safety_notes=notes),
        _cap("file.search_name", "Search File Names", "Search filenames only inside the allowed project scope.", "file_agent", "file_system", risk_level="medium", verifier_name=verifier, safety_notes=notes),
        _cap("file.preview_text", "Preview Text File", "Preview safe text/code/docs files with size limits.", "file_agent", "file_system", risk_level="medium", verifier_name=verifier, safety_notes=notes),
        _cap("file.explain_project_structure", "Explain Project Structure", "Show a limited project tree and basic structure summary.", "file_agent", "file_system", risk_level="medium", verifier_name=verifier, safety_notes=notes),
        _cap("file.understand_text", "Understand Text File", "Summarize a safe text/code/docs file with deterministic local heuristics.", "file_agent", "file_system", risk_level="medium", verifier_name=understand_verifier, safety_notes=understand_notes),
        _cap("file.summarize_text", "Summarize Text File", "Alias capability for read-only heuristic text summaries.", "file_agent", "file_system", risk_level="medium", verifier_name=understand_verifier, safety_notes=understand_notes),
        _cap("file.project_inventory", "Project Inventory", "Build a bounded read-only project inventory.", "file_agent", "file_system", risk_level="medium", verifier_name=understand_verifier, safety_notes=understand_notes),
        _cap("file.project_explain", "Project Explanation", "Explain what a repo appears to be from safe filenames and small key files.", "file_agent", "file_system", risk_level="medium", verifier_name=understand_verifier, safety_notes=understand_notes),
        _cap("file.project_missing", "Project Missing Checklist", "Show common missing docs/config checklist items.", "file_agent", "file_system", risk_level="medium", verifier_name=understand_verifier, safety_notes=understand_notes),
        _cap("file.project_dependencies", "Project Dependencies", "Detect dependency and config files with shallow local hints.", "file_agent", "file_system", risk_level="medium", verifier_name=understand_verifier, safety_notes=understand_notes),
        _cap("file.draft_create_preview", "Draft Create Preview", "Generate proposed new file content in chat output only.", "file_agent", "file_system", risk_level="medium", verifier_name=draft_verifier, safety_notes=draft_notes),
        _cap("file.draft_append_preview", "Draft Append Preview", "Generate an append preview and diff in chat output only.", "file_agent", "file_system", risk_level="medium", verifier_name=draft_verifier, safety_notes=draft_notes),
        _cap("file.draft_replace_preview", "Draft Replace Preview", "Generate a replacement preview and diff in chat output only.", "file_agent", "file_system", risk_level="medium", verifier_name=draft_verifier, safety_notes=draft_notes),
        _cap("file.diff_preview", "Diff Preview", "Generate a unified diff preview without applying it.", "file_agent", "file_system", risk_level="medium", verifier_name=draft_verifier, safety_notes=draft_notes),
        _cap("file.draft_readme_section", "Draft README Section", "Generate a README section draft in chat output only.", "file_agent", "file_system", risk_level="medium", verifier_name=draft_verifier, safety_notes=draft_notes),
        _cap("file.draft_project_summary", "Draft Project Summary", "Generate a project summary draft from read-only inventory.", "file_agent", "file_system", risk_level="medium", verifier_name=draft_verifier, safety_notes=draft_notes),
        _cap("file.draft_report_outline", "Draft Report Outline", "Generate a report outline draft in chat output only.", "file_agent", "file_system", risk_level="medium", verifier_name=draft_verifier, safety_notes=draft_notes),
        _cap("file.draft_project_todo", "Draft Project TODO", "Generate project TODO recommendations from read-only inventory.", "file_agent", "file_system", risk_level="medium", verifier_name=draft_verifier, safety_notes=draft_notes),
        _cap("file.apply_readiness", "Apply Readiness", "Evaluate future confirmed apply readiness for a draft without writing files.", "file_agent", "file_system", risk_level="medium", verifier_name="verify_eva_file_agent_write_safety.py", safety_notes=apply_notes),
        _cap("file.write_safety_policy", "Write Safety Policy", "Explain FileAgent future write safety policy for a path.", "file_agent", "file_system", risk_level="medium", verifier_name="verify_eva_file_agent_write_safety.py", safety_notes=apply_notes),
        _cap("file.rollback_plan", "Rollback Plan", "Generate a future rollback plan without creating backups or restoring files.", "file_agent", "file_system", risk_level="medium", verifier_name="verify_eva_file_agent_write_safety.py", safety_notes=apply_notes),
        _cap("file.verification_plan", "Verification Plan", "Generate a future write verification checklist without applying changes.", "file_agent", "file_system", risk_level="medium", verifier_name="verify_eva_file_agent_write_safety.py", safety_notes=apply_notes),
        _cap("file.approval_status", "File Approval Ledger Status", "Show FileAgent approval ledger status.", "file_agent", "file_system", risk_level="medium", verifier_name="verify_eva_file_agent_approval_ledger.py", safety_notes=approval_notes),
        _cap("file.approval_request_create", "Create File Approval Request", "Create local approval metadata for a future file apply.", "file_agent", "file_system", risk_level="medium", read_only=False, enabled_by_default=False, verifier_name="verify_eva_file_agent_approval_ledger.py", safety_notes=approval_notes),
        _cap("file.approval_list_pending", "List Pending File Approvals", "List pending FileAgent approval metadata.", "file_agent", "file_system", risk_level="medium", verifier_name="verify_eva_file_agent_approval_ledger.py", safety_notes=approval_notes),
        _cap("file.approval_view", "View File Approval", "View one FileAgent approval metadata record.", "file_agent", "file_system", risk_level="medium", verifier_name="verify_eva_file_agent_approval_ledger.py", safety_notes=approval_notes),
        _cap("file.approval_approve_future", "Approve File Request For Future Apply", "Mark an approval record as approved for future apply only.", "file_agent", "file_system", risk_level="medium", read_only=False, requires_confirmation=True, enabled_by_default=False, verifier_name="verify_eva_file_agent_approval_ledger.py", safety_notes=approval_notes),
        _cap("file.approval_deny", "Deny File Approval", "Mark a FileAgent approval record as denied.", "file_agent", "file_system", risk_level="medium", read_only=False, enabled_by_default=False, verifier_name="verify_eva_file_agent_approval_ledger.py", safety_notes=approval_notes),
        _cap("file.approval_cancel", "Cancel File Approval", "Mark a FileAgent approval record as cancelled.", "file_agent", "file_system", risk_level="medium", read_only=False, enabled_by_default=False, verifier_name="verify_eva_file_agent_approval_ledger.py", safety_notes=approval_notes),
        _cap("file.approval_events", "File Approval Events", "Show audit-style events for a FileAgent approval record.", "file_agent", "file_system", risk_level="medium", verifier_name="verify_eva_file_agent_approval_ledger.py", safety_notes=approval_notes),
        _cap("file.approval_expire", "Expire File Approvals", "Expire old pending FileAgent approval records.", "file_agent", "file_system", risk_level="medium", read_only=False, enabled_by_default=False, verifier_name="verify_eva_file_agent_approval_ledger.py", safety_notes=approval_notes),
        _cap("file.apply_executor_status", "File Apply Executor Status", "Show FileAgent sandbox apply executor status.", "file_agent", "file_system", risk_level="medium", verifier_name="verify_eva_file_agent_sandbox_apply.py", safety_notes=sandbox_notes),
        _cap("file.sandbox_apply_policy", "File Sandbox Apply Policy", "Explain sandbox-only apply policy.", "file_agent", "file_system", risk_level="medium", verifier_name="verify_eva_file_agent_sandbox_apply.py", safety_notes=sandbox_notes),
        _cap("file.sandbox_apply_approved", "Sandbox Apply Approved File Change", "Apply approved metadata inside the FileAgent sandbox harness only.", "file_agent", "file_system", risk_level="high", read_only=False, requires_confirmation=True, enabled_by_default=False, verifier_name="verify_eva_file_agent_sandbox_apply.py", safety_notes=sandbox_notes),
        _cap("file.sandbox_verify_apply", "Sandbox Verify File Apply", "Verify a FileAgent sandbox apply result.", "file_agent", "file_system", risk_level="medium", read_only=False, enabled_by_default=False, verifier_name="verify_eva_file_agent_sandbox_apply.py", safety_notes=sandbox_notes),
        _cap("file.sandbox_rollback_apply", "Sandbox Rollback File Apply", "Roll back FileAgent sandbox state only.", "file_agent", "file_system", risk_level="high", read_only=False, requires_confirmation=True, enabled_by_default=False, verifier_name="verify_eva_file_agent_sandbox_apply.py", safety_notes=sandbox_notes),
        _cap("file.real_apply_policy", "Real Apply Policy", "Explain the Phase 12L narrow real apply policy.", "file_agent", "file_system", risk_level="medium", verifier_name="verify_eva_file_agent_real_apply_gate.py", safety_notes=real_create_notes),
        _cap("file.real_apply_eligibility", "Real Apply Eligibility", "Check whether one approved FileAgent record is eligible for narrow real create-new-text-file.", "file_agent", "file_system", risk_level="medium", verifier_name="verify_eva_file_agent_real_apply_gate.py", safety_notes=real_create_notes),
        _cap("file.real_create_new_text_file", "Real Create New Text File", "Create one new approved .md/.txt file in docs/ or samples/ after exact confirmation.", "file_agent", "file_system", risk_level="high", read_only=False, requires_confirmation=True, enabled_by_default=False, verifier_name="verify_eva_file_agent_real_apply_gate.py", safety_notes=real_create_notes),
        _cap("file.real_verify_new_text_file", "Verify Real New Text File", "Verify the created file still matches the approved content hash.", "file_agent", "file_system", risk_level="medium", verifier_name="verify_eva_file_agent_real_apply_gate.py", safety_notes=real_create_notes),
        _cap("file.real_rollback_new_text_file", "Rollback Real New Text File", "Remove only an unchanged Eva-created text file after exact rollback confirmation.", "file_agent", "file_system", risk_level="high", read_only=False, requires_confirmation=True, enabled_by_default=False, verifier_name="verify_eva_file_agent_real_apply_gate.py", safety_notes=real_create_notes),
        _cap("file.real_create_eligibility", "Real Create Eligibility", "Compatibility alias for Phase 12L real apply eligibility.", "file_agent", "file_system", risk_level="medium", verifier_name="verify_eva_file_agent_real_create_gate.py", safety_notes=real_create_notes),
        _cap("file.real_create_safe_text", "Real Create Safe Text File", "Compatibility alias for creating one new approved .md/.txt file after exact confirmation.", "file_agent", "file_system", risk_level="high", read_only=False, requires_confirmation=True, enabled_by_default=False, verifier_name="verify_eva_file_agent_real_create_gate.py", safety_notes=real_create_notes),
        _cap("file.real_create_verify", "Verify Real Created File", "Compatibility alias for verifying the created file content hash.", "file_agent", "file_system", risk_level="medium", verifier_name="verify_eva_file_agent_real_create_gate.py", safety_notes=real_create_notes),
        _cap("file.real_create_rollback", "Rollback Real Created File", "Compatibility alias for removing only an unchanged Eva-created file after exact rollback confirmation.", "file_agent", "file_system", risk_level="high", read_only=False, requires_confirmation=True, enabled_by_default=False, verifier_name="verify_eva_file_agent_real_create_gate.py", safety_notes=real_create_notes),
    ]


def _browser_agent_capabilities() -> list[Capability]:
    notes = "Phase 13A-13F BrowserAgent safety foundation only. Status, policy, domain/site-risk policy, readiness proof, action-safety, session-preview, page/text/DOM summary design, and action dry-run previews do not launch, navigate, click, type, submit, read browser sessions, observe live pages, control pages, use MCP, or call Playwright/PyAutoGUI/cloud."
    read_notes = "Phase 24 Real Browser Read-Only Mode: validated public-URL observation/report output only; sessionless, credentialless, no-cookie, no-profile, no click/type/forms/download/upload/login/control, no arbitrary file reads/writes, no tool execution, and Phase 12L remains the only real write path."
    verifier = "verify_eva_browser_agent_safety.py"
    session_verifier = "verify_eva_browser_session_preview.py"
    observation_verifier = "verify_eva_browser_page_summary_design.py"
    action_verifier = "verify_eva_browser_action_dry_run.py"
    domain_verifier = "verify_eva_browser_domain_policy.py"
    proof_verifier = "verify_eva_browser_readiness_proof.py"
    return [
        _cap("browser.status", "BrowserAgent Status", "Show BrowserAgent safety-model status.", "browser_agent", "browser", verifier_name=verifier, safety_notes=notes),
        _cap("browser.policy", "BrowserAgent Policy", "Show current browser session policy and locked execution boundary.", "browser_agent", "browser", verifier_name=verifier, safety_notes=notes),
        _cap("browser.blocked_actions", "BrowserAgent Blocked Actions", "List blocked browser actions and reasons.", "browser_agent", "browser", verifier_name=verifier, safety_notes=notes),
        _cap("browser.domain_policy", "BrowserAgent Domain Policy", "Show domain/privacy policy preview.", "browser_agent", "browser", verifier_name=verifier, safety_notes=notes),
        _cap("browser.action_safety_preview", "Browser Action Safety Preview", "Preview whether a requested browser action is allowed.", "browser_agent", "browser", verifier_name=verifier, safety_notes=notes),
        _cap("browser.readiness", "BrowserAgent Readiness", "Show what is missing before real browser control can be enabled.", "browser_agent", "browser", verifier_name=verifier, safety_notes=notes),
        _cap("browser.session_status", "Browser Session Status", "Show preview-only browser session status.", "browser_agent", "browser", verifier_name=session_verifier, safety_notes=notes),
        _cap("browser.session_preview", "Browser Session Preview", "Create a preview-only browser session record without launching a browser.", "browser_agent", "browser", verifier_name=session_verifier, safety_notes=notes),
        _cap("browser.sessions_list", "Browser Sessions List", "List preview-only browser session records.", "browser_agent", "browser", verifier_name=session_verifier, safety_notes=notes),
        _cap("browser.session_plan", "Browser Session Plan", "Show future browser session lifecycle plan.", "browser_agent", "browser", verifier_name=session_verifier, safety_notes=notes),
        _cap("browser.session_readiness", "Browser Session Readiness", "Show read-only browser session readiness gaps.", "browser_agent", "browser", verifier_name=session_verifier, safety_notes=notes),
        _cap("browser.page_summary_policy", "Browser Page Summary Policy", "Show page summary design policy without live page reads.", "browser_agent", "browser", verifier_name=observation_verifier, safety_notes=notes),
        _cap("browser.page_summary_preview", "Browser Page Summary Preview", "Show a mock-text page summary preview without reading a live webpage.", "browser_agent", "browser", verifier_name=observation_verifier, safety_notes=notes),
        _cap("browser.dom_summary_policy", "Browser DOM Summary Policy", "Show DOM summary schema policy without DOM access.", "browser_agent", "browser", verifier_name=observation_verifier, safety_notes=notes),
        _cap("browser.text_extraction_policy", "Browser Text Extraction Policy", "Show text extraction policy without live extraction.", "browser_agent", "browser", verifier_name=observation_verifier, safety_notes=notes),
        _cap("browser.observation_readiness", "Browser Observation Readiness", "Show gaps before any future live browser observation.", "browser_agent", "browser", verifier_name=observation_verifier, safety_notes=notes),
        _cap("browser.redaction_policy", "Browser Redaction Policy", "Show local redaction rules for future browser observation.", "browser_agent", "browser", verifier_name=observation_verifier, safety_notes=notes),
        _cap("browser.action_dry_run", "Browser Action Dry-Run", "Create a text-only browser action dry-run plan.", "browser_agent", "browser", verifier_name=action_verifier, safety_notes=notes),
        _cap("browser.action_plan_preview", "Browser Action Plan Preview", "Show a dry-run browser action plan without execution.", "browser_agent", "browser", verifier_name=action_verifier, safety_notes=notes),
        _cap("browser.action_risk", "Browser Action Risk", "Show risk level for a browser action.", "browser_agent", "browser", verifier_name=action_verifier, safety_notes=notes),
        _cap("browser.action_approvals", "Browser Action Approvals", "Show future approval requirements for browser action types.", "browser_agent", "browser", verifier_name=action_verifier, safety_notes=notes),
        _cap("browser.dry_run_policy", "Browser Dry-Run Policy", "Show browser action dry-run policy.", "browser_agent", "browser", verifier_name=action_verifier, safety_notes=notes),
        _cap("browser.action_readiness", "Browser Action Readiness", "Show gaps before browser action execution can exist.", "browser_agent", "browser", verifier_name=action_verifier, safety_notes=notes),
        _cap("browser.domain_check", "Browser Domain Check", "Classify a domain string with the BrowserAgent policy model without network access.", "browser_agent", "browser", verifier_name=domain_verifier, safety_notes=notes),
        _cap("browser.site_risk", "Browser Site Risk", "Preview site risk category and approval requirements from a domain string.", "browser_agent", "browser", verifier_name=domain_verifier, safety_notes=notes),
        _cap("browser.domain_rules", "Browser Domain Rules", "Show BrowserAgent domain risk rules.", "browser_agent", "browser", verifier_name=domain_verifier, safety_notes=notes),
        _cap("browser.sensitive_sites", "Browser Sensitive Sites", "Show sensitive browser site categories and markers.", "browser_agent", "browser", verifier_name=domain_verifier, safety_notes=notes),
        _cap("browser.domain_approvals", "Browser Domain Approvals", "Show future approval requirements for sensitive site categories.", "browser_agent", "browser", verifier_name=domain_verifier, safety_notes=notes),
        _cap("browser.domain_readiness", "Browser Domain Readiness", "Show readiness gaps for future domain-gated browser observation.", "browser_agent", "browser", verifier_name=domain_verifier, safety_notes=notes),
        _cap("browser.readonly_readiness", "Browser Read-Only Readiness", "Show BrowserAgent read-only readiness proof status.", "browser_agent", "browser", verifier_name=proof_verifier, safety_notes=notes),
        _cap("browser.readiness_proof", "Browser Readiness Proof", "Show checklist proof for BrowserAgent safety layers.", "browser_agent", "browser", verifier_name=proof_verifier, safety_notes=notes),
        _cap("browser.safety_proof", "Browser Safety Proof", "Prove browser control remains locked while safety layers exist.", "browser_agent", "browser", verifier_name=proof_verifier, safety_notes=notes),
        _cap("browser.readiness_gaps", "Browser Readiness Gaps", "Show what is missing before future browser read-only mode.", "browser_agent", "browser", verifier_name=proof_verifier, safety_notes=notes),
        _cap("browser.locked_status", "Browser Locked Status", "Show locked browser execution status.", "browser_agent", "browser", verifier_name=proof_verifier, safety_notes=notes),
        _cap("browser.phase13_proof", "Browser Phase 13 Proof", "Summarize Phase 13 BrowserAgent proof layers.", "browser_agent", "browser", verifier_name=proof_verifier, safety_notes=notes),
        _cap("browser.phase13_status", "Browser Phase 13 Status", "Show final Phase 13 safety/readiness-only status.", "browser_agent", "browser", verifier_name="verify_eva_browser_phase13_hardening.py", safety_notes=notes),
        _cap("browser.phase13_summary", "Browser Phase 13 Summary", "Summarize final BrowserAgent Phase 13 safety/readiness scope.", "browser_agent", "browser", verifier_name="verify_eva_browser_phase13_hardening.py", safety_notes=notes),
        _cap("browser.phase13_limits", "Browser Phase 13 Limits", "Show final Phase 13 browser limits and locked execution categories.", "browser_agent", "browser", verifier_name="verify_eva_browser_phase13_hardening.py", safety_notes=notes),
        _cap("browser.phase13_ready", "Browser Phase 13 Ready Check", "Show whether BrowserAgent Phase 13 is complete as a safety/readiness foundation.", "browser_agent", "browser", verifier_name="verify_eva_browser_phase13_hardening.py", safety_notes=notes),
        _cap("browser.phase13_final_proof", "Browser Phase 13 Final Proof", "Show final proof that Phase 13 enables no real browser observation/control.", "browser_agent", "browser", verifier_name="verify_eva_browser_phase13_hardening.py", safety_notes=notes),
        _cap("browser_read.status", "Browser Read-Only Status", "Show Phase 24 public-URL read-only observation status.", "browser_agent", "browser", verifier_name="verify_eva_browser_readonly_mode.py", safety_notes=read_notes),
        _cap("browser_read.policy", "Browser Read-Only Policy", "Show Phase 24 observation, session, backend, and action boundaries.", "browser_agent", "browser", verifier_name="verify_eva_browser_readonly_mode.py", safety_notes=read_notes),
        _cap("browser_read.url_policy", "Browser Read-Only URL Policy", "Show public URL validation and blocked URL classes.", "browser_agent", "browser", verifier_name="verify_eva_browser_readonly_mode.py", safety_notes=read_notes),
        _cap("browser_read.observe", "Browser Read-Only Observe", "Return observation/report status for a validated public URL without browser control.", "browser_agent", "browser", verifier_name="verify_eva_browser_readonly_mode.py", safety_notes=read_notes),
        _cap("browser_read.mock_observe", "Browser Read-Only Mock Observe", "Return a deterministic redacted local fixture observation.", "browser_agent", "browser", verifier_name="verify_eva_browser_readonly_mode.py", safety_notes=read_notes),
        _cap("browser_read.safety_report", "Browser Read-Only Safety Report", "Show URL, redaction, threat-defense, and execution-gate safety results.", "browser_agent", "browser", verifier_name="verify_eva_browser_readonly_mode.py", safety_notes=read_notes),
        _cap("browser_read.blocked_urls", "Browser Read-Only Blocked URLs", "List URL classes blocked before observation.", "browser_agent", "browser", verifier_name="verify_eva_browser_readonly_mode.py", safety_notes=read_notes),
        _cap("browser_read.readiness", "Browser Read-Only Readiness", "Show Phase 24 readiness and the locked browser-control boundary.", "browser_agent", "browser", verifier_name="verify_eva_browser_readonly_mode.py", safety_notes=read_notes),
    ]


def _desktop_agent_capabilities() -> list[Capability]:
    notes = "Phase 14A-14G DesktopAgent locked safety foundation only. Status, policy, previews, screen observation policy, action dry runs, risk scoring, human approval model, and final readiness proof do not observe screens, inspect windows/apps, launch apps, move/click/type, use hotkeys, use clipboard, automate file dialogs, run terminal/package commands, use MCP/PyAutoGUI/Playwright, or call cloud services."
    observe_notes = "Phase 25 Real Desktop Observation Mode: explicit one-shot redacted observation/report output only; no click/type/hotkey/app/window control, continuous monitoring, screenshot saving, cookies/sessions/browser profiles, arbitrary file reads/writes, or tool execution. Phase 12L remains the only real write path."
    control_gate_notes = "Phase 26 Real Desktop Control Gate: local/mock policy and dry-run reports only; no click/type/hotkey/clipboard/app/window control, shell/package/cloud/MCP, secret/config/session reads, arbitrary file reads/writes, or tool execution. Phase 12L remains the only real write path."
    news_notes = "Phase 27 local/mock dashboard/report/status only; Phase 24 public-URL policy integration, no crawler, login/session/cookie/profile access, browser control, network in tests, tool execution, arbitrary file reads/writes, or new write path."
    verifier = "verify_eva_desktop_agent_safety.py"
    session_verifier = "verify_eva_desktop_session_preview.py"
    screen_verifier = "verify_eva_desktop_screen_observation_policy.py"
    action_verifier = "verify_eva_desktop_action_dry_run.py"
    risk_verifier = "verify_eva_desktop_action_risk_scoring.py"
    approval_verifier = "verify_eva_desktop_approval_model.py"
    proof_verifier = "verify_eva_desktop_phase14_readiness.py"
    return [
        _cap("desktop.status", "DesktopAgent Status", "Show DesktopAgent safety-model status.", "desktop_agent", "desktop", verifier_name=verifier, safety_notes=notes),
        _cap("desktop.policy", "DesktopAgent Policy", "Show current desktop policy and locked observation/control boundary.", "desktop_agent", "desktop", verifier_name=verifier, safety_notes=notes),
        _cap("desktop.blocked_actions", "DesktopAgent Blocked Actions", "List blocked desktop actions and reasons.", "desktop_agent", "desktop", verifier_name=verifier, safety_notes=notes),
        _cap("desktop.action_safety_preview", "Desktop Action Safety Preview", "Preview whether a requested desktop action is allowed.", "desktop_agent", "desktop", verifier_name=verifier, safety_notes=notes),
        _cap("desktop.app_risk", "Desktop App Risk", "Classify an app/category string without inspecting real apps.", "desktop_agent", "desktop", verifier_name=verifier, safety_notes=notes),
        _cap("desktop.readiness", "DesktopAgent Readiness", "Show what is missing before real desktop observation/control can be enabled.", "desktop_agent", "desktop", verifier_name=verifier, safety_notes=notes),
        _cap("desktop.session_status", "Desktop Session Status", "Show preview-only desktop session status.", "desktop_agent", "desktop", verifier_name=session_verifier, safety_notes=notes),
        _cap("desktop.sessions_list", "Desktop Sessions List", "List preview-only desktop session records.", "desktop_agent", "desktop", verifier_name=session_verifier, safety_notes=notes),
        _cap("desktop.session_preview", "Desktop Session Preview", "Create a preview-only desktop session record without observing or controlling the desktop.", "desktop_agent", "desktop", verifier_name=session_verifier, safety_notes=notes),
        _cap("desktop.session_plan", "Desktop Session Plan", "Show the future desktop session lifecycle plan.", "desktop_agent", "desktop", verifier_name=session_verifier, safety_notes=notes),
        _cap("desktop.app_status_preview", "Desktop App Status Preview", "Show future app status schema without inspecting real apps.", "desktop_agent", "desktop", verifier_name=session_verifier, safety_notes=notes),
        _cap("desktop.window_status_preview", "Desktop Window Status Preview", "Show future window status schema without enumerating real windows.", "desktop_agent", "desktop", verifier_name=session_verifier, safety_notes=notes),
        _cap("desktop.active_context_preview", "Desktop Active Context Preview", "Show future active context schema without detecting real active apps/windows.", "desktop_agent", "desktop", verifier_name=session_verifier, safety_notes=notes),
        _cap("desktop.observation_readiness", "Desktop Observation Readiness", "Show gaps before future desktop observation can exist.", "desktop_agent", "desktop", verifier_name=session_verifier, safety_notes=notes),
        _cap("desktop.screen_policy", "Desktop Screen Policy", "Show locked screen observation policy.", "desktop_agent", "desktop", verifier_name=screen_verifier, safety_notes=notes),
        _cap("desktop.screen_observation_policy", "Desktop Screen Observation Policy", "Show future screen observation schema and locked boundary.", "desktop_agent", "desktop", verifier_name=screen_verifier, safety_notes=notes),
        _cap("desktop.sensitive_screens", "Desktop Sensitive Screens", "List sensitive screen categories and future approval requirements.", "desktop_agent", "desktop", verifier_name=screen_verifier, safety_notes=notes),
        _cap("desktop.screen_redaction_policy", "Desktop Screen Redaction Policy", "Show local screen redaction policy preview.", "desktop_agent", "desktop", verifier_name=screen_verifier, safety_notes=notes),
        _cap("desktop.screen_capture_gate", "Desktop Screen Capture Gate", "Show future capture gate requirements while capture remains locked.", "desktop_agent", "desktop", verifier_name=screen_verifier, safety_notes=notes),
        _cap("desktop.screen_readiness", "Desktop Screen Readiness", "Show gaps before future screen observation can exist.", "desktop_agent", "desktop", verifier_name=screen_verifier, safety_notes=notes),
        _cap("desktop.observation_policy", "Desktop Observation Policy", "Show screen observation policy and safety decision preview.", "desktop_agent", "desktop", verifier_name=screen_verifier, safety_notes=notes),
        _cap("desktop.action_dry_run", "Desktop Action Dry-Run", "Create a text-only desktop action dry-run plan.", "desktop_agent", "desktop", verifier_name=action_verifier, safety_notes=notes),
        _cap("desktop.action_plan_preview", "Desktop Action Plan Preview", "Preview desktop action steps without executing them.", "desktop_agent", "desktop", verifier_name=action_verifier, safety_notes=notes),
        _cap("desktop.action_risk", "Desktop Action Risk", "Classify a desktop action risk without executing it.", "desktop_agent", "desktop", verifier_name=action_verifier, safety_notes=notes),
        _cap("desktop.action_approvals", "Desktop Action Approvals", "Show future approval requirements for desktop actions.", "desktop_agent", "desktop", verifier_name=action_verifier, safety_notes=notes),
        _cap("desktop.dry_run_policy", "Desktop Dry-Run Policy", "Show DesktopAgent action dry-run policy.", "desktop_agent", "desktop", verifier_name=action_verifier, safety_notes=notes),
        _cap("desktop.action_readiness", "Desktop Action Readiness", "Show gaps before real desktop action execution can exist.", "desktop_agent", "desktop", verifier_name=action_verifier, safety_notes=notes),
        _cap("desktop.risk_score", "Desktop Risk Score", "Calculate deterministic desktop action risk from strings only.", "desktop_agent", "desktop", verifier_name=risk_verifier, safety_notes=notes),
        _cap("desktop.risk_factors", "Desktop Risk Factors", "Explain risk factors for a desktop action request.", "desktop_agent", "desktop", verifier_name=risk_verifier, safety_notes=notes),
        _cap("desktop.approval_required", "Desktop Approval Required", "Explain future approval requirements for a desktop action request.", "desktop_agent", "desktop", verifier_name=risk_verifier, safety_notes=notes),
        _cap("desktop.safety_matrix", "Desktop Safety Matrix", "Show DesktopAgent action risk and approval matrix.", "desktop_agent", "desktop", verifier_name=risk_verifier, safety_notes=notes),
        _cap("desktop.high_risk_actions", "Desktop High Risk Actions", "List high-risk and forbidden desktop action classes.", "desktop_agent", "desktop", verifier_name=risk_verifier, safety_notes=notes),
        _cap("desktop.risk_readiness", "Desktop Risk Readiness", "Show gaps before real desktop action risk-gated execution can exist.", "desktop_agent", "desktop", verifier_name=risk_verifier, safety_notes=notes),
        _cap("desktop.approval_policy", "Desktop Approval Policy", "Show DesktopAgent human approval policy without unlocking execution.", "desktop_agent", "desktop", verifier_name=approval_verifier, safety_notes=notes),
        _cap("desktop.approval_levels", "Desktop Approval Levels", "Explain DesktopAgent approval levels and forbidden states.", "desktop_agent", "desktop", verifier_name=approval_verifier, safety_notes=notes),
        _cap("desktop.approval_preview", "Desktop Approval Preview", "Preview future approval level for a desktop request without executing it.", "desktop_agent", "desktop", verifier_name=approval_verifier, safety_notes=notes),
        _cap("desktop.confirmation_phrase", "Desktop Confirmation Phrase", "Preview future confirmation phrase class without unlocking desktop execution.", "desktop_agent", "desktop", verifier_name=approval_verifier, safety_notes=notes),
        _cap("desktop.forbidden_actions", "Desktop Forbidden Actions", "List desktop action classes with no approval path.", "desktop_agent", "desktop", verifier_name=approval_verifier, safety_notes=notes),
        _cap("desktop.approval_audit_status", "Desktop Approval Audit Status", "Show DesktopAgent approval audit schema/status only.", "desktop_agent", "desktop", verifier_name=approval_verifier, safety_notes=notes),
        _cap("desktop.approval_readiness", "Desktop Approval Readiness", "Show gaps before desktop approvals could unlock any future action.", "desktop_agent", "desktop", verifier_name=approval_verifier, safety_notes=notes),
        _cap("desktop.phase14_status", "Desktop Phase 14 Status", "Show final locked DesktopAgent Phase 14 status.", "desktop_agent", "desktop", verifier_name=proof_verifier, safety_notes=notes),
        _cap("desktop.phase14_summary", "Desktop Phase 14 Summary", "Summarize completed Phase 14 safety/readiness layers.", "desktop_agent", "desktop", verifier_name=proof_verifier, safety_notes=notes),
        _cap("desktop.phase14_limits", "Desktop Phase 14 Limits", "Show final DesktopAgent locked limits.", "desktop_agent", "desktop", verifier_name=proof_verifier, safety_notes=notes),
        _cap("desktop.phase14_ready", "Desktop Phase 14 Ready Check", "Show whether DesktopAgent Phase 14 is complete as a locked foundation.", "desktop_agent", "desktop", verifier_name=proof_verifier, safety_notes=notes),
        _cap("desktop.phase14_final_proof", "Desktop Phase 14 Final Proof", "Show final proof that Phase 14 enables no desktop observation or control.", "desktop_agent", "desktop", verifier_name=proof_verifier, safety_notes=notes),
        _cap("desktop.readiness_proof", "Desktop Readiness Proof", "Show the DesktopAgent locked safety/readiness proof.", "desktop_agent", "desktop", verifier_name=proof_verifier, safety_notes=notes),
        _cap("desktop.locked_status", "Desktop Locked Status", "Show the current locked desktop observation/control boundary.", "desktop_agent", "desktop", verifier_name=proof_verifier, safety_notes=notes),
        _cap("desktop.readiness_gaps", "Desktop Readiness Gaps", "Show what is missing before future desktop observation/control gates.", "desktop_agent", "desktop", verifier_name=proof_verifier, safety_notes=notes),
        _cap("desktop_observe.status", "Desktop Observation Status", "Show Phase 25 observation-only status and backend availability.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_observation_mode.py", safety_notes=observe_notes),
        _cap("desktop_observe.policy", "Desktop Observation Policy", "Show the explicit one-shot observation policy and locked control boundary.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_observation_mode.py", safety_notes=observe_notes),
        _cap("desktop_observe.backend", "Desktop Observation Backend", "Show safe desktop observation backend availability without capturing a screen.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_observation_mode.py", safety_notes=observe_notes),
        _cap("desktop_observe.mock", "Desktop Observation Mock", "Run the deterministic redacted mock-screen observation path.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_observation_mode.py", safety_notes=observe_notes),
        _cap("desktop_observe.safety_report", "Desktop Observation Safety Report", "Show desktop observation gates, threat findings, redactions, and boundaries.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_observation_mode.py", safety_notes=observe_notes),
        _cap("desktop_observe.sensitive_screens", "Desktop Observation Sensitive Screens", "List sensitive screen categories and blocking/redaction policy.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_observation_mode.py", safety_notes=observe_notes),
        _cap("desktop_observe.redaction_policy", "Desktop Observation Redaction Policy", "Show local redaction rules for observation output.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_observation_mode.py", safety_notes=observe_notes),
        _cap("desktop_observe.readiness", "Desktop Observation Readiness", "Show Phase 25 readiness and the locked desktop-control boundary.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_observation_mode.py", safety_notes=observe_notes),
        _cap("desktop_control.status", "Desktop Control Gate Status", "Show Phase 26 local/mock gate status.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_control_gate.py", safety_notes=control_gate_notes),
        _cap("desktop_control.policy", "Desktop Control Gate Policy", "Show desktop-control gate policy and no-control boundaries.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_control_gate.py", safety_notes=control_gate_notes),
        _cap("desktop_control.actions", "Desktop Control Action Catalog", "Show deterministic action classes.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_control_gate.py", safety_notes=control_gate_notes),
        _cap("desktop_control.dry_run", "Desktop Control Dry Run", "Build a deterministic local/mock control-gate preview.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_control_gate.py", safety_notes=control_gate_notes),
        _cap("desktop_control.approvals", "Desktop Control Approval Policy", "Show future approval metadata; approval cannot execute.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_control_gate.py", safety_notes=control_gate_notes),
        _cap("desktop_control.confirmations", "Desktop Control Confirmation Policy", "Show future confirmation metadata; confirmation cannot execute.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_control_gate.py", safety_notes=control_gate_notes),
        _cap("desktop_control.blocked_actions", "Desktop Control Blocked Actions", "List denied desktop-control action classes.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_control_gate.py", safety_notes=control_gate_notes),
        _cap("desktop_control.readiness", "Desktop Control Gate Readiness", "Show Phase 26 readiness and locked execution.", "desktop_agent", "desktop", verifier_name="verify_eva_desktop_control_gate.py", safety_notes=control_gate_notes),
        _cap("news.status","News Dashboard Status","Show local/mock status.","desktop_agent","research",verifier_name="verify_eva_news_web_intelligence_dashboard.py",safety_notes=news_notes),
        _cap("news.policy","News Dashboard Policy","Show safe source policy.","desktop_agent","research",verifier_name="verify_eva_news_web_intelligence_dashboard.py",safety_notes=news_notes),
        _cap("news.dashboard","News Dashboard","Show deterministic fixture dashboard.","desktop_agent","research",verifier_name="verify_eva_news_web_intelligence_dashboard.py",safety_notes=news_notes),
        _cap("news.topics","News Topics","Show topic model.","desktop_agent","research",verifier_name="verify_eva_news_web_intelligence_dashboard.py",safety_notes=news_notes),
        _cap("news.sources","News Sources","Show source cards and reliability.","desktop_agent","research",verifier_name="verify_eva_news_web_intelligence_dashboard.py",safety_notes=news_notes),
        _cap("news.freshness","News Freshness","Show freshness policy.","desktop_agent","research",verifier_name="verify_eva_news_web_intelligence_dashboard.py",safety_notes=news_notes),
        _cap("news.safety_report","News Safety Report","Show crawler and session boundaries.","desktop_agent","research",verifier_name="verify_eva_news_web_intelligence_dashboard.py",safety_notes=news_notes),
        _cap("news.readiness","News Readiness","Show Phase 27 readiness.","desktop_agent","research",verifier_name="verify_eva_news_web_intelligence_dashboard.py",safety_notes=news_notes),
    ]


def _coding_agent_capabilities() -> list[Capability]:
    verifier = "verify_eva_coding_agent_foundation.py"
    notes = (
        "Phase 28 deterministic preview/report/status only. No source-code edits, patch application, "
        "shell/test/package/git execution, arbitrary filesystem access, secret/config/session reads, "
        "live LLM/API/provider calls, tool execution, or new write path. Phase 12L remains the only "
        "real file-write boundary."
    )
    definitions = (
        ("coding.status", "CodingAgent Status", "Show Phase 28 preview-only status."),
        ("coding.policy", "CodingAgent Policy", "Show coding safety and execution boundaries."),
        ("coding.specialists", "Coding Specialist Catalog", "Show deterministic preview specialist modes."),
        ("coding.task_preview", "Coding Task Preview", "Classify a coding request without execution."),
        ("coding.project_context", "Coding Project Context", "Show safe metadata-only project context."),
        ("coding.patch_plan", "Coding Patch Plan", "Show planning text without creating or applying a patch."),
        ("coding.review_checklist", "Coding Review Checklist", "Show a deterministic human review checklist."),
        ("coding.test_plan", "Coding Test Plan", "Show test instructions without running tests."),
        ("coding.risk_review", "Coding Risk Review", "Show coding safety and blocked-action risks."),
        ("coding.handoff", "Coding Handoff Report", "Show a deterministic implementation handoff preview."),
        ("coding.blocked_actions", "CodingAgent Blocked Actions", "Show blocked execution and privacy classes."),
        ("coding.readiness", "CodingAgent Readiness", "Show Phase 28 readiness and the Phase 29 handoff."),
    )
    return [
        _cap(
            capability_id,
            name,
            description,
            "coding_agent",
            "code",
            verifier_name=verifier,
            safety_notes=notes,
        )
        for capability_id, name, description in definitions
    ]


def _release_demo_capabilities() -> list[Capability]:
    verifier = "verify_eva_public_demo_release.py"
    phase32_verifier = "verify_eva_post_push_demo_smoke.py"
    notes = (
        "Phase 29 and Phase 32 deterministic report/status/demo profile only. No publishing, upload, package release, "
        "commit/tag/push, shell/package/cloud/MCP execution, browser/desktop control, source edits, "
        "arbitrary filesystem access, secret/config/session reads, live provider calls, tool execution, "
        "or new write path. Phase 12L remains the only real file-write boundary."
    )
    definitions = (
        ("release.status", "Release Demo Status", "Show the local Phase 29 release profile status."),
        ("release.demo", "Public Demo Profile", "Show the deterministic public demo walkthrough."),
        ("release.commands", "Release Demo Commands", "Show local report-only demo commands."),
        ("release.capability_map", "Release Capability Map", "Show available and locked capability boundaries."),
        ("release.safety_proof", "Release Safety Proof", "Show deterministic public-demo safety evidence."),
        ("release.readiness", "Release Readiness", "Show local demo readiness without publishing."),
        ("release.limitations", "Release Known Limitations", "Show honest public limitations and non-goals."),
        ("release.verification", "Release Verification Bundle", "Show manual verifier commands without running them."),
    )
    capabilities = [
        _cap(
            capability_id,
            name,
            description,
            "release_demo",
            "public_release",
            verifier_name=verifier,
            safety_notes=notes,
        )
        for capability_id, name, description in definitions
    ]
    capabilities.extend(
        [
            _cap(
                "release.demo_smoke",
                "Release Demo Smoke Test",
                "Show the Phase 32 safe local demo smoke checklist.",
                "release_demo",
                "public_release",
                verifier_name=phase32_verifier,
                safety_notes=notes,
            ),
            _cap(
                "release.post_push_sync",
                "Release Post-Push Sync Status",
                "Show the Phase 32 post-push sync and remote hygiene status.",
                "release_demo",
                "public_release",
                verifier_name=phase32_verifier,
                safety_notes=notes,
            ),
        ]
    )
    return capabilities


def _release_candidate_capabilities() -> list[Capability]:
    verifier = "verify_eva_release_candidate_hardening.py"
    notes = (
        "Phase 30 deterministic report/status/planning only. Commit planning is text only. "
        "No staging, commit, tag, push, publish, upload, shell/package/cloud/MCP execution, "
        "browser/desktop control, source edits, arbitrary filesystem access, secret/config/session "
        "reads, live LLM/API/provider calls, tool execution, or new write path. Phase 12L remains "
        "the only real file-write boundary."
    )
    definitions = (
        ("rc.status", "Release Candidate Status", "Show Phase 30 readiness and locked state."),
        ("rc.manifest", "RC Dirty Tree Manifest", "Show the deterministic audited change grouping."),
        ("rc.commit_plan", "RC Commit Plan", "Show human-reviewable commit candidates as text only."),
        ("rc.hardening_report", "RC Hardening Report", "Show bounded claim and safety findings."),
        ("rc.checklist", "RC Checklist", "Show the release-candidate review checklist."),
        ("rc.readiness", "RC Readiness", "Show safe-to-commit guidance without Git execution."),
        ("rc.safety_proof", "RC Safety Proof", "Show deterministic Phase 30 safety evidence."),
        ("rc.verification", "RC Verification", "Show manual verifier commands without running them."),
    )
    return [
        _cap(
            capability_id,
            name,
            description,
            "release_candidate",
            "public_release",
            verifier_name=verifier,
            safety_notes=notes,
        )
        for capability_id, name, description in definitions
    ]


def _roadmap_capabilities() -> list[Capability]:
    from ..roadmap.catalog import get_capability_catalog
    from ..roadmap.models import ExecutionClass

    capabilities: list[Capability] = []
    for descriptor in get_capability_catalog():
        if not descriptor.capability_id.startswith("roadmap."):
            continue
        blocked = descriptor.execution_class is ExecutionClass.BLOCKED
        read_only = descriptor.execution_class in {ExecutionClass.REPORT_ONLY, ExecutionClass.READ_ONLY, ExecutionClass.BLOCKED}
        risk_level = "medium" if blocked else "low"
        status = "blocked" if blocked else "stable"
        capabilities.append(
            _cap(
                descriptor.capability_id,
                descriptor.name,
                descriptor.notes,
                "roadmap",
                "roadmap",
                risk_level=risk_level,
                read_only=read_only,
                requires_confirmation=False,
                enabled_by_default=not blocked,
                status=status,
                verifier_name=descriptor.verifier,
                safety_notes=(
                    "Phase 33-42 roadmap report/status/catalog metadata only. "
                    "No new execution path is enabled; Phase 12L remains the only real write boundary."
                ),
            )
        )
    return capabilities


def _eva_core_capabilities() -> list[Capability]:
    notes = "Phase 12G local deterministic router and authority decision metadata; no cloud calls, normal-chat v2 routing, browser control, desktop control, terminal execution, MCP, or real file writes."
    control_notes = "Phase 12P read-only Control Center dashboard/status surface; no browser opening, browser control, desktop control, cloud calls, MCP, terminal execution, verifier subprocesses, package installs, or broad real file writes."
    work_session_notes = "Phase 12Q local WorkSession/audit timeline metadata only; tracks routed requests and status evidence without executing actions."
    golden_notes = "Phase 12J golden workflow orchestration only: draft preview, approval metadata, sandbox apply, narrow real-create eligibility, exact confirmation, verification, and rollback. Broad writes remain disabled."
    verification_notes = "Phase 12K verification metadata only. Commands print manual verifier instructions or read-only status; Eva does not start shell commands from chat."
    specialist_notes = "Phase 12M specialist and skill workflow metadata only. It selects roles, skills, and workflow plans; it does not execute MCP, browser, desktop, terminal, cloud, or broad file write actions."
    project_notes = "Phase 12O read-only project inspection and reality-check workflow. It summarizes local status/evidence only and does not execute verifiers, write files, open browsers, control desktop apps, call cloud services, or enable MCP."
    validation_notes = "Phase 15C mock/local structured-output validation only; live LLM calls remain locked, invalid output cannot execute tools, and repair does not execute or rewrite user intent."
    red_team_notes = "Phase 15D local/mock red-team reports only; no live provider call, tool execution, secret/config/session read, or browser/desktop/shell execution."
    context_notes = "Phase 16 local/mock context preview only; no live LLM/API/provider calls, provider SDKs, secret/config/session reads, arbitrary file reads, tool execution, browser/desktop/shell/cloud/MCP execution, or new write paths."
    threat_notes = "Phase 17 local/mock threat-defense preview only; no live LLM/API/provider calls, provider SDKs, secret/config/session reads, arbitrary file reads, tool execution, browser/desktop/shell/cloud/MCP execution, or new write paths."
    agent_loop_notes = "Phase 18 Agent Loop v1 local/mock preview only; no live LLM/API/provider calls, provider SDKs, secret/config/session reads, arbitrary file reads, tool execution, browser/desktop/shell/cloud/MCP execution, or new write paths."
    workflow_planner_notes = "Phase 19 Agentic Workflow Planner local/mock preview only; no live LLM/API/provider calls, provider SDKs, secret/config/session reads, arbitrary file reads/writes, tool execution, browser/desktop/shell/cloud/MCP execution, or new write paths."
    execution_gates_notes = "Phase 20 Controlled Execution Gates local/mock policy preview only; no live LLM/API/provider calls, provider SDKs, secret/config/session reads, arbitrary file reads/writes, tool execution, browser/desktop/shell/cloud/MCP/package execution, or new write paths. Phase 12L narrow real-create remains the only real write path."
    memory_v3_notes = "Phase 21 Memory v3 local-only policy/status/preview; no live LLM/API/provider calls, provider SDKs, cloud memory, remote sync, secret/config/session reads, arbitrary file reads/writes, raw memory DB dumps, tool execution, browser/desktop/shell/cloud/MCP execution, or new write paths."
    voice_notes = "Phase 22 Voice Assistant Foundation local/mock preview only; no microphone, recording, audio playback, live ASR/TTS, provider SDK, live LLM/API call, secret/config/session read, arbitrary file read/write, tool execution, browser/desktop/shell/cloud/MCP execution, or new write path."
    ai_os_notes = "Phase 23 AI OS / Control Center Upgrade local/status only; no live LLM/API/provider call, provider SDK, server, UI launch, daemon, secret/config/session read, arbitrary file read/write, tool execution, browser/desktop/shell/cloud/MCP execution, or new write path."
    return [
        _cap("llm.status", "LLM Router Status", "Show mock-only LLM router status.", "llm_router", "llm", verifier_name="verify_eva_llm_router_contracts.py", safety_notes="Phase 15A metadata only; no live LLM/API/network calls or tool execution."),
        _cap("llm.providers", "LLM Provider Contracts", "Show provider contract metadata without configuration reads.", "llm_router", "llm", verifier_name="verify_eva_llm_router_contracts.py", safety_notes="Phase 15A metadata only; no live calls."),
        _cap("llm.routing_policy", "LLM Routing Policy", "Show dry-run routing policy.", "llm_router", "llm", verifier_name="verify_eva_llm_router_contracts.py", safety_notes="Mock-only routing preview."),
        _cap("llm.fallback_policy", "LLM Fallback Policy", "Show provider fallback metadata and degraded mode.", "llm_router", "llm", verifier_name="verify_eva_llm_router_contracts.py", safety_notes="Mock-only fallback preview."),
        _cap("llm.limits", "LLM Router Limits", "Show token, cost, timeout, and retry preview limits.", "llm_router", "llm", verifier_name="verify_eva_llm_router_contracts.py", safety_notes="No cost can be incurred in Phase 15A."),
        _cap("llm.structured_output", "LLM Structured Output", "Show mock structured-output contract rules.", "llm_router", "llm", verifier_name="verify_eva_llm_router_contracts.py", safety_notes="Mock validation only."),
        _cap("llm.route_preview", "LLM Route Preview", "Preview a mock-only LLM route without calling a provider.", "llm_router", "llm", verifier_name="verify_eva_llm_router_contracts.py", safety_notes="No live provider call."),
        _cap("llm.readiness", "LLM Router Readiness", "Show Phase 15A readiness and locked boundaries.", "llm_router", "llm", verifier_name="verify_eva_llm_router_contracts.py", safety_notes="Status only."),
        _cap("llm.validation_status", "LLM Validation Status", "Show local structured-output validation status.", "llm_router", "llm", verifier_name="verify_eva_llm_structured_output_wiring.py", safety_notes=validation_notes),
        _cap("llm.schema_registry", "LLM Schema Registry", "Show registered structured-output preview contracts.", "llm_router", "llm", verifier_name="verify_eva_llm_structured_output_wiring.py", safety_notes=validation_notes),
        _cap("llm.validation_policy", "LLM Validation Policy", "Show local invalid-output blocking policy.", "llm_router", "llm", verifier_name="verify_eva_llm_structured_output_wiring.py", safety_notes=validation_notes),
        _cap("llm.repair_policy", "LLM Repair Policy", "Show non-executing repair policy.", "llm_router", "llm", verifier_name="verify_eva_llm_structured_output_wiring.py", safety_notes=validation_notes),
        _cap("llm.validate_mock", "LLM Validate Mock", "Validate bundled local mock previews.", "llm_router", "llm", verifier_name="verify_eva_llm_structured_output_wiring.py", safety_notes=validation_notes),
        _cap("llm.validate_invalid_examples", "LLM Validate Invalid Examples", "Show safe blocked invalid-output examples.", "llm_router", "llm", verifier_name="verify_eva_llm_structured_output_wiring.py", safety_notes=validation_notes),
        _cap("llm.validation_readiness", "LLM Validation Readiness", "Show structured-output validation readiness.", "llm_router", "llm", verifier_name="verify_eva_llm_structured_output_wiring.py", safety_notes=validation_notes),
        _cap("llm.red_team_status", "LLM Red-Team Status", "Show local red-team status.", "llm_router", "llm", verifier_name="verify_eva_llm_red_team_failure_tests.py", safety_notes=red_team_notes),
        _cap("llm.red_team_cases", "LLM Red-Team Cases", "List local red-team case categories.", "llm_router", "llm", verifier_name="verify_eva_llm_red_team_failure_tests.py", safety_notes=red_team_notes),
        _cap("llm.red_team_run", "LLM Red-Team Run", "Run local simulated red-team cases.", "llm_router", "llm", verifier_name="verify_eva_llm_red_team_failure_tests.py", safety_notes=red_team_notes),
        _cap("llm.failure_tests", "LLM Failure Tests", "Show simulated router failure-test policy.", "llm_router", "llm", verifier_name="verify_eva_llm_red_team_failure_tests.py", safety_notes=red_team_notes),
        _cap("llm.safety_failure_report", "LLM Safety Failure Report", "Show local safety failure report.", "llm_router", "llm", verifier_name="verify_eva_llm_red_team_failure_tests.py", safety_notes=red_team_notes),
        _cap("llm.red_team_readiness", "LLM Red-Team Readiness", "Show red-team readiness.", "llm_router", "llm", verifier_name="verify_eva_llm_red_team_failure_tests.py", safety_notes=red_team_notes),
        _cap("context.status", "Context Assembly Status", "Show local Context Assembly Engine status.", "eva_core", "context", verifier_name="verify_eva_context_assembly_engine.py", safety_notes=context_notes),
        _cap("context.sources", "Context Sources", "Show allowed and blocked context sources.", "eva_core", "context", verifier_name="verify_eva_context_assembly_engine.py", safety_notes=context_notes),
        _cap("context.policy", "Context Policy", "Show source, permission, injection, and execution boundaries.", "eva_core", "context", verifier_name="verify_eva_context_assembly_engine.py", safety_notes=context_notes),
        _cap("context.budget", "Context Budget", "Show deterministic context budget and trimming policy.", "eva_core", "context", verifier_name="verify_eva_context_assembly_engine.py", safety_notes=context_notes),
        _cap("context.assemble_preview", "Context Assemble Preview", "Build a sanitized source-aware context packet preview.", "eva_core", "context", verifier_name="verify_eva_context_assembly_engine.py", safety_notes=context_notes),
        _cap("context.grounding_report", "Context Grounding Report", "Show grounding and excluded-context evidence.", "eva_core", "context", verifier_name="verify_eva_context_assembly_engine.py", safety_notes=context_notes),
        _cap("context.redaction_policy", "Context Redaction Policy", "Show secret/private-path redaction policy.", "eva_core", "context", verifier_name="verify_eva_context_assembly_engine.py", safety_notes=context_notes),
        _cap("context.readiness", "Context Readiness", "Show Phase 16 readiness and locked boundaries.", "eva_core", "context", verifier_name="verify_eva_context_assembly_engine.py", safety_notes=context_notes),
        _cap("threat.status", "Threat Defense Status", "Show LLM Threat Defense + Prompt Injection Guard status.", "eva_core", "threat_defense", verifier_name="verify_eva_llm_threat_defense_prompt_injection.py", safety_notes=threat_notes),
        _cap("threat.catalog", "Threat Catalog", "Show local threat categories.", "eva_core", "threat_defense", verifier_name="verify_eva_llm_threat_defense_prompt_injection.py", safety_notes=threat_notes),
        _cap("threat.policy", "Threat Defense Policy", "Show instruction hierarchy and defense policy.", "eva_core", "threat_defense", verifier_name="verify_eva_llm_threat_defense_prompt_injection.py", safety_notes=threat_notes),
        _cap("threat.scan_preview", "Threat Scan Preview", "Scan untrusted text locally and report safe blocking.", "eva_core", "threat_defense", verifier_name="verify_eva_llm_threat_defense_prompt_injection.py", safety_notes=threat_notes),
        _cap("threat.injection_examples", "Prompt Injection Examples", "Show local prompt-injection examples and classifications.", "eva_core", "threat_defense", verifier_name="verify_eva_llm_threat_defense_prompt_injection.py", safety_notes=threat_notes),
        _cap("threat.exfiltration_examples", "Exfiltration Examples", "Show local exfiltration examples and blocking.", "eva_core", "threat_defense", verifier_name="verify_eva_llm_threat_defense_prompt_injection.py", safety_notes=threat_notes),
        _cap("threat.context_guard", "Context Poisoning Guard", "Show untrusted-context handling and poisoning guard.", "eva_core", "threat_defense", verifier_name="verify_eva_llm_threat_defense_prompt_injection.py", safety_notes=threat_notes),
        _cap("threat.readiness", "Threat Defense Readiness", "Show Phase 17 readiness and locked boundaries.", "eva_core", "threat_defense", verifier_name="verify_eva_llm_threat_defense_prompt_injection.py", safety_notes=threat_notes),
        _cap("agent_loop.status", "Agent Loop Status", "Show Agent Loop v1 local preview status.", "eva_core", "agent_loop", verifier_name="verify_eva_agent_loop_v1.py", safety_notes=agent_loop_notes),
        _cap("agent_loop.policy", "Agent Loop Policy", "Show Agent Loop v1 local policy and boundaries.", "eva_core", "agent_loop", verifier_name="verify_eva_agent_loop_v1.py", safety_notes=agent_loop_notes),
        _cap("agent_loop.run_preview", "Agent Loop Run Preview", "Run a deterministic local/mock loop preview.", "eva_core", "agent_loop", verifier_name="verify_eva_agent_loop_v1.py", safety_notes=agent_loop_notes),
        _cap("agent_loop.steps", "Agent Loop Steps", "Show Agent Loop v1 stages and step limits.", "eva_core", "agent_loop", verifier_name="verify_eva_agent_loop_v1.py", safety_notes=agent_loop_notes),
        _cap("agent_loop.action_previews", "Agent Loop Action Previews", "Show preview-only action model.", "eva_core", "agent_loop", verifier_name="verify_eva_agent_loop_v1.py", safety_notes=agent_loop_notes),
        _cap("agent_loop.safety_report", "Agent Loop Safety Report", "Show loop safety report and blocked-action summary.", "eva_core", "agent_loop", verifier_name="verify_eva_agent_loop_v1.py", safety_notes=agent_loop_notes),
        _cap("agent_loop.stop_reasons", "Agent Loop Stop Reasons", "Show step-limit, repeated-step, and no-progress stop behavior.", "eva_core", "agent_loop", verifier_name="verify_eva_agent_loop_v1.py", safety_notes=agent_loop_notes),
        _cap("agent_loop.readiness", "Agent Loop Readiness", "Show Phase 18 readiness and locked boundaries.", "eva_core", "agent_loop", verifier_name="verify_eva_agent_loop_v1.py", safety_notes=agent_loop_notes),
        _cap("workflow_planner.status", "Workflow Planner Status", "Show Agentic Workflow Planner status.", "eva_core", "workflow_planner", verifier_name="verify_eva_agentic_workflow_planner.py", safety_notes=workflow_planner_notes),
        _cap("workflow_planner.catalog", "Workflow Planner Catalog", "Show local workflow template catalog.", "eva_core", "workflow_planner", verifier_name="verify_eva_agentic_workflow_planner.py", safety_notes=workflow_planner_notes),
        _cap("workflow_planner.policy", "Workflow Planner Policy", "Show workflow planner safety policy.", "eva_core", "workflow_planner", verifier_name="verify_eva_agentic_workflow_planner.py", safety_notes=workflow_planner_notes),
        _cap("workflow_planner.preview", "Workflow Planner Preview", "Build a deterministic workflow preview.", "eva_core", "workflow_planner", verifier_name="verify_eva_agentic_workflow_planner.py", safety_notes=workflow_planner_notes),
        _cap("workflow_planner.dependencies", "Workflow Planner Dependencies", "Show dependency validation preview.", "eva_core", "workflow_planner", verifier_name="verify_eva_agentic_workflow_planner.py", safety_notes=workflow_planner_notes),
        _cap("workflow_planner.approvals", "Workflow Planner Approvals", "Show approval requirement previews.", "eva_core", "workflow_planner", verifier_name="verify_eva_agentic_workflow_planner.py", safety_notes=workflow_planner_notes),
        _cap("workflow_planner.rollback", "Workflow Planner Rollback", "Show rollback plan preview.", "eva_core", "workflow_planner", verifier_name="verify_eva_agentic_workflow_planner.py", safety_notes=workflow_planner_notes),
        _cap("workflow_planner.readiness", "Workflow Planner Readiness", "Show Phase 19 readiness and locked boundaries.", "eva_core", "workflow_planner", verifier_name="verify_eva_agentic_workflow_planner.py", safety_notes=workflow_planner_notes),
        _cap("execution_gates.status", "Execution Gates Status", "Show Controlled Execution Gates status.", "eva_core", "execution_gates", verifier_name="verify_eva_controlled_execution_gates.py", safety_notes=execution_gates_notes),
        _cap("execution_gates.policy", "Execution Gates Policy", "Show Controlled Execution Gates safety policy.", "eva_core", "execution_gates", verifier_name="verify_eva_controlled_execution_gates.py", safety_notes=execution_gates_notes),
        _cap("execution_gates.evaluate", "Execution Gates Evaluate", "Evaluate a request against local/mock execution gates.", "eva_core", "execution_gates", verifier_name="verify_eva_controlled_execution_gates.py", safety_notes=execution_gates_notes),
        _cap("execution_gates.approvals", "Execution Gates Approvals", "Show approval policy metadata.", "eva_core", "execution_gates", verifier_name="verify_eva_controlled_execution_gates.py", safety_notes=execution_gates_notes),
        _cap("execution_gates.confirmations", "Execution Gates Confirmations", "Show confirmation phrase policy metadata.", "eva_core", "execution_gates", verifier_name="verify_eva_controlled_execution_gates.py", safety_notes=execution_gates_notes),
        _cap("execution_gates.rollback", "Execution Gates Rollback", "Show rollback metadata policy.", "eva_core", "execution_gates", verifier_name="verify_eva_controlled_execution_gates.py", safety_notes=execution_gates_notes),
        _cap("execution_gates.blocked_actions", "Execution Gates Blocked Actions", "Show blocked action classes.", "eva_core", "execution_gates", verifier_name="verify_eva_controlled_execution_gates.py", safety_notes=execution_gates_notes),
        _cap("execution_gates.readiness", "Execution Gates Readiness", "Show Phase 20 readiness and locked boundaries.", "eva_core", "execution_gates", verifier_name="verify_eva_controlled_execution_gates.py", safety_notes=execution_gates_notes),
        _cap("memory_v3.status", "Memory v3 Status", "Show Memory v3 local-only status.", "eva_core", "memory_v3", verifier_name="verify_eva_memory_v3.py", safety_notes=memory_v3_notes),
        _cap("memory_v3.policy", "Memory v3 Policy", "Show Memory v3 source, trust, privacy, and context policy.", "eva_core", "memory_v3", verifier_name="verify_eva_memory_v3.py", safety_notes=memory_v3_notes),
        _cap("memory_v3.sources", "Memory v3 Sources", "Show Memory v3 source and trust model.", "eva_core", "memory_v3", verifier_name="verify_eva_memory_v3.py", safety_notes=memory_v3_notes),
        _cap("memory_v3.privacy", "Memory v3 Privacy", "Show Memory v3 privacy filter policy.", "eva_core", "memory_v3", verifier_name="verify_eva_memory_v3.py", safety_notes=memory_v3_notes),
        _cap("memory_v3.freshness", "Memory v3 Freshness", "Show Memory v3 freshness policy.", "eva_core", "memory_v3", verifier_name="verify_eva_memory_v3.py", safety_notes=memory_v3_notes),
        _cap("memory_v3.conflicts", "Memory v3 Conflicts", "Show Memory v3 conflict policy.", "eva_core", "memory_v3", verifier_name="verify_eva_memory_v3.py", safety_notes=memory_v3_notes),
        _cap("memory_v3.retrieval_preview", "Memory v3 Retrieval Preview", "Show eligible and excluded memory context summaries.", "eva_core", "memory_v3", verifier_name="verify_eva_memory_v3.py", safety_notes=memory_v3_notes),
        _cap("memory_v3.readiness", "Memory v3 Readiness", "Show Phase 21 readiness and locked boundaries.", "eva_core", "memory_v3", verifier_name="verify_eva_memory_v3.py", safety_notes=memory_v3_notes),
        _cap("voice.status", "Voice Assistant Status", "Show local/mock Voice Assistant Foundation status.", "eva_core", "voice_assistant", verifier_name="verify_eva_voice_assistant_foundation.py", safety_notes=voice_notes),
        _cap("voice.policy", "Voice Assistant Policy", "Show locked voice lifecycle and response policy.", "eva_core", "voice_assistant", verifier_name="verify_eva_voice_assistant_foundation.py", safety_notes=voice_notes),
        _cap("voice.providers", "Voice Provider Policy", "Show locked ASR/TTS provider candidates.", "eva_core", "voice_assistant", verifier_name="verify_eva_voice_assistant_foundation.py", safety_notes=voice_notes),
        _cap("voice.listen_state", "Voice Listen State", "Show mock wake/listen lifecycle state.", "eva_core", "voice_assistant", verifier_name="verify_eva_voice_assistant_foundation.py", safety_notes=voice_notes),
        _cap("voice.transcript_safety", "Voice Transcript Safety", "Show transcript filtering and blocking policy.", "eva_core", "voice_assistant", verifier_name="verify_eva_voice_assistant_foundation.py", safety_notes=voice_notes),
        _cap("voice.route_preview", "Voice Route Preview", "Build a deterministic mock transcript route preview.", "eva_core", "voice_assistant", verifier_name="verify_eva_voice_assistant_foundation.py", safety_notes=voice_notes),
        _cap("voice.confirmations", "Voice Confirmations", "Show confirmation-preview boundaries.", "eva_core", "voice_assistant", verifier_name="verify_eva_voice_assistant_foundation.py", safety_notes=voice_notes),
        _cap("voice.readiness", "Voice Assistant Readiness", "Show Phase 22 readiness and locked boundaries.", "eva_core", "voice_assistant", verifier_name="verify_eva_voice_assistant_foundation.py", safety_notes=voice_notes),
        _cap("ai_os.status", "AI OS Status", "Show local AI OS status and boundaries.", "eva_core", "ai_os", verifier_name="verify_eva_ai_os_control_center_upgrade.py", safety_notes=ai_os_notes),
        _cap("ai_os.dashboard", "AI OS Dashboard", "Show the local AI OS dashboard report.", "eva_core", "ai_os", verifier_name="verify_eva_ai_os_control_center_upgrade.py", safety_notes=ai_os_notes),
        _cap("ai_os.system_map", "AI OS System Map", "Show major Eva systems and current states.", "eva_core", "ai_os", verifier_name="verify_eva_ai_os_control_center_upgrade.py", safety_notes=ai_os_notes),
        _cap("ai_os.capability_matrix", "AI OS Capability Matrix", "Show preview, locked, and existing narrow-gate distinctions.", "eva_core", "ai_os", verifier_name="verify_eva_ai_os_control_center_upgrade.py", safety_notes=ai_os_notes),
        _cap("ai_os.feature_states", "AI OS Feature States", "Show feature-state classifications.", "eva_core", "ai_os", verifier_name="verify_eva_ai_os_control_center_upgrade.py", safety_notes=ai_os_notes),
        _cap("ai_os.safety_boundaries", "AI OS Safety Boundaries", "Show dashboard safety boundaries.", "eva_core", "ai_os", verifier_name="verify_eva_ai_os_control_center_upgrade.py", safety_notes=ai_os_notes),
        _cap("ai_os.locked_features", "AI OS Locked Features", "Show locked future gates and blocked actions.", "eva_core", "ai_os", verifier_name="verify_eva_ai_os_control_center_upgrade.py", safety_notes=ai_os_notes),
        _cap("ai_os.next_safe_step", "AI OS Next Safe Step", "Show the next recommended safety phase.", "eva_core", "ai_os", verifier_name="verify_eva_ai_os_control_center_upgrade.py", safety_notes=ai_os_notes),
        _cap("ai_os.readiness", "AI OS Readiness", "Show Phase 23 readiness and locked boundaries.", "eva_core", "ai_os", verifier_name="verify_eva_ai_os_control_center_upgrade.py", safety_notes=ai_os_notes),
        _cap("llm.fallback_chain", "LLM Fallback Chain", "Show deterministic mock-only fallback chain.", "llm_router", "llm", verifier_name="verify_eva_llm_router_fallbacks_limits.py", safety_notes="No provider call."),
        _cap("llm.fallback_simulate", "LLM Fallback Simulation", "Simulate a named failure without calling a provider.", "llm_router", "llm", verifier_name="verify_eva_llm_router_fallbacks_limits.py", safety_notes="Mock-only."),
        _cap("llm.degraded_mode", "LLM Degraded Mode", "Show safe mock/status degraded behavior.", "llm_router", "llm", verifier_name="verify_eva_llm_router_fallbacks_limits.py", safety_notes="No live calls."),
        _cap("llm.session_limits", "LLM Session Limits", "Show deterministic route/step limits.", "llm_router", "llm", verifier_name="verify_eva_llm_router_fallbacks_limits.py", safety_notes="Policy only."),
        _cap("llm.rate_limits", "LLM Rate Limits", "Show simulated rate-limit policy.", "llm_router", "llm", verifier_name="verify_eva_llm_router_fallbacks_limits.py", safety_notes="Simulation only."),
        _cap("llm.routing_audit_preview", "LLM Routing Audit Preview", "Show secret-free routing audit preview.", "llm_router", "llm", verifier_name="verify_eva_llm_router_fallbacks_limits.py", safety_notes="Local preview only."),
        _cap("llm.failure_modes", "LLM Failure Modes", "Show named router failure scenarios.", "llm_router", "llm", verifier_name="verify_eva_llm_router_fallbacks_limits.py", safety_notes="Status only."),
        _cap("llm.runaway_protection", "LLM Runaway Protection", "Show router preview step limit policy.", "llm_router", "llm", verifier_name="verify_eva_llm_router_fallbacks_limits.py", safety_notes="No execution loop."),
        _cap("eva.ask", "Eva Ask", "Route a natural-language request through existing safe Eva commands.", "eva_core", "routing", risk_level="medium", verifier_name="verify_eva_authority_natural_router.py", safety_notes=notes),
        _cap("eva.natural_router", "Natural Router", "Classify natural-language requests into safe capability routes.", "eva_core", "routing", verifier_name="verify_eva_authority_natural_router.py", safety_notes=notes),
        _cap("eva.authority_status", "Authority Status", "Show the global authority spine status.", "eva_core", "authority", verifier_name="verify_eva_authority_natural_router.py", safety_notes=notes),
        _cap("eva.authority_decision_preview", "Authority Decision Preview", "Preview a global authority decision without execution.", "eva_core", "authority", risk_level="medium", verifier_name="verify_eva_authority_natural_router.py", safety_notes=notes),
        _cap("eva.verify_all", "Eva Verify All", "Run the local verifier sweep through the master verifier script.", "eva_core", "verification", risk_level="medium", verifier_name="verify_eva_all.py", safety_notes="Local verifier runner only; no dependency setup, network calls, or feature execution surfaces are enabled."),
        _cap("eva.smoke_status", "Eva Smoke Status", "Show the Phase 12K smoke/quick verification status and manual commands.", "eva_core", "verification", verifier_name="verify_eva_smoke.py", safety_notes=verification_notes),
        _cap("eva.verify_quick_command", "Eva Verify Quick Command", "Print the manual quick verifier command without running it.", "eva_core", "verification", verifier_name="verify_eva_smoke.py", safety_notes=verification_notes),
        _cap("eva.verify_full_command", "Eva Verify Full Command", "Print the manual full verifier command without running it.", "eva_core", "verification", verifier_name="verify_eva_phase12_stabilization.py", safety_notes=verification_notes),
        _cap("eva.phase12_status", "Eva Phase 12 Status", "Show completed Phase 12 surfaces and locked future modules.", "eva_core", "verification", verifier_name="verify_eva_phase12_stabilization.py", safety_notes=verification_notes),
        _cap("eva.phase12_ready", "Eva Phase 12 Ready", "Show final Phase 12 checkpoint readiness and proof requirements.", "eva_core", "verification", verifier_name="verify_eva_phase12_ready.py", safety_notes=verification_notes),
        _cap("eva.phase12_summary", "Eva Phase 12 Summary", "Summarize Phase 12 systems and current safety posture.", "eva_core", "verification", verifier_name="verify_eva_phase12_ready.py", safety_notes=verification_notes),
        _cap("eva.phase12_limits", "Eva Phase 12 Limits", "Show locked execution areas and the only real write path.", "eva_core", "verification", verifier_name="verify_eva_phase12_ready.py", safety_notes=verification_notes),
        _cap("eva.phase12_proof", "Eva Phase 12 Proof", "Show verifier proof surfaces without running them.", "eva_core", "verification", verifier_name="verify_eva_phase12_ready.py", safety_notes=verification_notes),
        _cap("eva.ux_status", "Eva UX Status", "Show the Phase 12K command UX and response-formatting status.", "eva_core", "verification", verifier_name="verify_eva_phase12_stabilization.py", safety_notes=verification_notes),
        _cap("eva.control_center_status", "Control Center Status", "Show the local Eva Control Center status summary.", "eva_core", "control_center", verifier_name="verify_eva_control_center.py", safety_notes=control_notes),
        _cap("eva.control_center_summary", "Control Center Summary", "Show a compact Control Center status summary.", "eva_core", "control_center", verifier_name="verify_eva_control_center_v1.py", safety_notes=control_notes),
        _cap("eva.locked_features", "Locked Features", "Explain locked features and planned modules without executing them.", "eva_core", "control_center", verifier_name="verify_eva_control_center_v1.py", safety_notes=control_notes),
        _cap("eva.enabled_features", "Enabled Features", "Show currently enabled safe/status features and the only real write path.", "eva_core", "control_center", verifier_name="verify_eva_control_center_v1.py", safety_notes=control_notes),
        _cap("eva.next_safe_step", "Next Safe Step", "Show the recommended next safe phase from Control Center metadata.", "eva_core", "control_center", verifier_name="verify_eva_control_center_v1.py", safety_notes=control_notes),
        _cap("eva.control_center_dashboard", "Control Center Dashboard", "Serve the read-only local dashboard at /control.", "eva_core", "control_center", verifier_name="verify_eva_control_center.py", safety_notes=control_notes),
        _cap("eva.control_center_status_json", "Control Center Status JSON", "Serve safe read-only dashboard status data at /control/status.json.", "eva_core", "control_center", verifier_name="verify_eva_control_center.py", safety_notes=control_notes),
        _cap("eva.dashboard_url", "Dashboard URL", "Show the local Control Center URL without opening a browser.", "eva_core", "control_center", verifier_name="verify_eva_control_center.py", safety_notes=control_notes),
        _cap("eva.work_sessions_status", "Work Sessions Status", "Show local WorkSession status counts and latest request.", "eva_core", "work_sessions", verifier_name="verify_eva_work_sessions_audit.py", safety_notes=work_session_notes),
        _cap("eva.work_sessions_recent", "Recent Work Sessions", "List recent local WorkSession summaries.", "eva_core", "work_sessions", verifier_name="verify_eva_work_sessions_audit.py", safety_notes=work_session_notes),
        _cap("eva.work_session_timeline", "Work Session Timeline", "Show one local WorkSession audit timeline.", "eva_core", "work_sessions", verifier_name="verify_eva_work_sessions_audit.py", safety_notes=work_session_notes),
        _cap("eva.audit_timeline", "Audit Timeline", "Show the latest local WorkSession audit timeline.", "eva_core", "work_sessions", verifier_name="verify_eva_work_sessions_audit.py", safety_notes=work_session_notes),
        _cap("eva.latest_work_session", "Latest Work Session", "Show the latest local WorkSession detail.", "eva_core", "work_sessions", verifier_name="verify_eva_work_sessions_audit.py", safety_notes=work_session_notes),
        _cap("eva.golden_workflows_status", "Golden Workflows Status", "Show safe golden workflow status and next action.", "eva_core", "golden_workflows", verifier_name="verify_eva_golden_workflows.py", safety_notes=golden_notes),
        _cap("eva.golden_workflow_status", "Golden Workflow Status", "Show the current golden workflow status.", "eva_core", "golden_workflows", verifier_name="verify_eva_golden_workflow_e2e.py", safety_notes=golden_notes),
        _cap("eva.golden_workflow_test_plan", "Golden Workflow Test Plan", "Show the end-to-end golden workflow test plan without executing it.", "eva_core", "golden_workflows", verifier_name="verify_eva_golden_workflow_e2e.py", safety_notes=golden_notes),
        _cap("eva.golden_workflow_proof", "Golden Workflow Proof", "Show latest golden workflow evidence, WorkSession records, verification state, and guarded rollback status.", "eva_core", "golden_workflows", verifier_name="verify_eva_golden_workflow_e2e.py", safety_notes=golden_notes),
        _cap("eva.golden_workflow_project_note", "Golden Workflow Project Note", "Orchestrate a safe project-note draft, approval, sandbox, exact real-create, verification, and rollback flow.", "eva_core", "golden_workflows", risk_level="medium", read_only=False, requires_confirmation=True, enabled_by_default=False, verifier_name="verify_eva_golden_workflows.py", safety_notes=golden_notes),
        _cap("eva.golden_workflow_continue", "Golden Workflow Continue", "Continue a golden workflow without treating vague confirmations as real-create approval.", "eva_core", "golden_workflows", risk_level="medium", read_only=False, requires_confirmation=True, enabled_by_default=False, verifier_name="verify_eva_golden_workflows.py", safety_notes=golden_notes),
        _cap("eva.golden_workflow_demo", "Golden Workflow Demo", "Preview the safe project-note workflow for demos and verification.", "eva_core", "golden_workflows", risk_level="medium", read_only=False, requires_confirmation=True, enabled_by_default=False, verifier_name="verify_eva_golden_workflows.py", safety_notes=golden_notes),
        _cap("eva.specialists_status", "Specialists Status", "Show registered specialist roles and safe routing scope.", "eva_core", "specialists", verifier_name="verify_eva_skill_specialist_workflows.py", safety_notes=specialist_notes),
        _cap("eva.specialist_select", "Specialist Select", "Select specialist roles for a request without executing them.", "eva_core", "specialists", verifier_name="verify_eva_skill_specialist_workflows.py", safety_notes=specialist_notes),
        _cap("eva.skills_status", "Skills Status", "Show registered Eva skill workflow metadata.", "eva_core", "skills", verifier_name="verify_eva_skill_specialist_workflows.py", safety_notes=specialist_notes),
        _cap("eva.skill_select", "Skill Select", "Select safe skills for a request without executing them.", "eva_core", "skills", verifier_name="verify_eva_skill_specialist_workflows.py", safety_notes=specialist_notes),
        _cap("eva.workflow_select", "Workflow Select", "Select a safe workflow plan for a request.", "eva_core", "workflows", verifier_name="verify_eva_skill_specialist_workflows.py", safety_notes=specialist_notes),
        _cap("eva.workflow_plan", "Workflow Plan", "Show a step-by-step workflow plan without executing it.", "eva_core", "workflows", risk_level="medium", verifier_name="verify_eva_skill_specialist_workflows.py", safety_notes=specialist_notes),
        _cap("eva.fileagent_project_note_workflow", "FileAgent Project Note Workflow", "Plan a FileAgent project note through draft, approval, sandbox, narrow real-create, verification, and rollback gates.", "eva_core", "workflows", risk_level="medium", read_only=True, requires_confirmation=False, verifier_name="verify_eva_skill_specialist_workflows.py", safety_notes=specialist_notes),
        _cap("eva.workflow_state", "Workflow State", "Summarize current FileAgent workflow state and ambiguity.", "eva_core", "workflows", verifier_name="verify_eva_golden_workflow_ux.py", safety_notes=specialist_notes),
        _cap("eva.workflow_next_step", "Workflow Next Step", "Show the safest next workflow step from latest local state.", "eva_core", "workflows", verifier_name="verify_eva_golden_workflow_ux.py", safety_notes=specialist_notes),
        _cap("eva.workflow_latest_approval", "Latest Workflow Approval", "Show latest pending and approved FileAgent approval candidates.", "eva_core", "workflows", verifier_name="verify_eva_golden_workflow_ux.py", safety_notes=specialist_notes),
        _cap("eva.workflow_latest_apply", "Latest Workflow Apply", "Show latest sandbox, real-create, and rollback state.", "eva_core", "workflows", verifier_name="verify_eva_golden_workflow_ux.py", safety_notes=specialist_notes),
        _cap("eva.workflow_disambiguate", "Workflow Disambiguation", "Explain multiple candidate approvals without guessing.", "eva_core", "workflows", verifier_name="verify_eva_golden_workflow_ux.py", safety_notes=specialist_notes),
        _cap("eva.file_latest_status", "FileAgent Latest Status", "Show latest FileAgent workflow/apply status.", "eva_core", "workflows", verifier_name="verify_eva_golden_workflow_ux.py", safety_notes=specialist_notes),
        _cap("eva.project_inspect", "Project Inspect", "Explain current Eva project state from read-only local status and FileAgent inventory.", "eva_core", "project_reality", verifier_name="verify_eva_project_reality_workflow.py", safety_notes=project_notes),
        _cap("eva.project_reality_check", "Project Reality Check", "Check done/broken claims against local evidence surfaces without overclaiming.", "eva_core", "project_reality", verifier_name="verify_eva_project_reality_workflow.py", safety_notes=project_notes),
        _cap("eva.project_recent_changes", "Project Recent Changes", "Summarize latest known Phase 12 changes from status/docs surfaces.", "eva_core", "project_reality", verifier_name="verify_eva_project_reality_workflow.py", safety_notes=project_notes),
        _cap("eva.project_next_step", "Project Next Step", "Recommend one safe next phase based on current local status.", "eva_core", "project_reality", verifier_name="verify_eva_project_reality_workflow.py", safety_notes=project_notes),
        _cap("eva.project_proof", "Project Proof", "Show evidence and limitations for current completion claims.", "eva_core", "project_reality", verifier_name="verify_eva_project_reality_workflow.py", safety_notes=project_notes),
        _cap("eva.done_check", "Done Check", "Refuse to claim completion without fresh verifier evidence.", "eva_core", "project_reality", verifier_name="verify_eva_project_reality_workflow.py", safety_notes=project_notes),
    ]
