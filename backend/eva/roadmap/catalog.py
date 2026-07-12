from __future__ import annotations

from .models import (
    CapabilityDescriptor,
    CommandDescriptor,
    ExecutionBoundary,
    ExecutionClass,
    PhaseRoadmapEntry,
    VerifierDescriptor,
)


PHASE33_VERIFIER = "verify_eva_phase33_roadmap_foundations.py"
PHASE32_VERIFIER = "verify_eva_post_push_demo_smoke.py"


def get_execution_boundary_catalog() -> tuple[ExecutionBoundary, ...]:
    verifier = PHASE33_VERIFIER
    return (
        ExecutionBoundary(
            "release.demo_status",
            ExecutionClass.REPORT_ONLY,
            "static formatter only",
            PHASE32_VERIFIER,
            "Release demo and smoke commands produce local report text only.",
        ),
        ExecutionBoundary(
            "roadmap.status",
            ExecutionClass.REPORT_ONLY,
            "static typed catalog",
            verifier,
            "Roadmap commands expose phase/status metadata and do not call tools.",
        ),
        ExecutionBoundary(
            "workspace_read_file",
            ExecutionClass.READ_ONLY,
            "workspace allowlist and secret filter",
            "verify_eva_file_agent_readonly.py",
            "Safe workspace reads are bounded and refuse secret/config/session surfaces.",
            tool_id="workspace_read_file",
        ),
        ExecutionBoundary(
            "browser_observe",
            ExecutionClass.READ_ONLY,
            "public URL/session isolation policy",
            "verify_eva_browser_readonly_mode.py",
            "Browser observation is read-only and must not use private logged-in sessions.",
            tool_id="browser_observe",
        ),
        ExecutionBoundary(
            "web_search",
            ExecutionClass.READ_ONLY,
            "provider availability and safe output redaction",
            "verify_eva_news_web_intelligence_dashboard.py",
            "Web search is read-oriented and cannot submit forms or control a browser.",
            tool_id="web_search",
        ),
        ExecutionBoundary(
            "file_agent.sandbox_apply",
            ExecutionClass.SANDBOX_ONLY,
            "ignored sandbox path only",
            "verify_eva_file_agent_sandbox_apply.py",
            "Sandbox apply may write only ignored sandbox artifacts, never tracked project files.",
        ),
        ExecutionBoundary(
            "file_agent.phase12l_create",
            ExecutionClass.PHASE12L_WRITE,
            "exact approval and new docs/samples text file only",
            "verify_eva_file_agent_real_create_gate.py",
            "Phase 12L remains a gated project write path: new .md/.txt under docs or samples.",
        ),
        ExecutionBoundary(
            "file.write_text",
            ExecutionClass.GATED_REAL_ACTION,
            "not routed by release/roadmap surfaces; requires explicit gate where used",
            verifier,
            "Raw tool registry write surfaces must stay behind explicit confirmation or remain unreachable.",
            tool_id="file.write_text",
        ),
        ExecutionBoundary(
            "file.patch_text",
            ExecutionClass.GATED_REAL_ACTION,
            "not routed by release/roadmap surfaces; requires explicit gate where used",
            verifier,
            "Patch surfaces must not become a broad source-edit path.",
            tool_id="file.patch_text",
        ),
        ExecutionBoundary(
            "file.delete",
            ExecutionClass.GATED_REAL_ACTION,
            "destructive override gate",
            verifier,
            "Delete surfaces are destructive and must remain blocked or explicitly gated.",
            tool_id="file.delete",
        ),
        ExecutionBoundary(
            "message.send_via_ui",
            ExecutionClass.GATED_REAL_ACTION,
            "external-send confirmation gate",
            verifier,
            "External sends require confirmation and are not part of public demo or roadmap commands.",
            tool_id="message.send_via_ui",
        ),
        ExecutionBoundary(
            "screen.click",
            ExecutionClass.GATED_REAL_ACTION,
            "desktop/browser control gate",
            verifier,
            "Click actions are real control and must not be exposed by safe demo commands.",
            tool_id="screen.click",
        ),
        ExecutionBoundary(
            "screen.type_text",
            ExecutionClass.GATED_REAL_ACTION,
            "desktop/browser control gate",
            verifier,
            "Typing actions are real control and must not be exposed by safe demo commands.",
            tool_id="screen.type_text",
        ),
        ExecutionBoundary(
            "app.open",
            ExecutionClass.GATED_REAL_ACTION,
            "local app-control gate",
            verifier,
            "Opening apps is a real local action and stays outside safe roadmap/demo commands.",
            tool_id="app.open",
        ),
        ExecutionBoundary(
            "secrets.sessions.config",
            ExecutionClass.BLOCKED,
            "hard refusal",
            "verify_eva_llm_threat_defense_prompt_injection.py",
            "Secrets, cookies, passwords, browser sessions, and config secrets are never read for these surfaces.",
        ),
    )


def get_capability_catalog() -> tuple[CapabilityDescriptor, ...]:
    return (
        CapabilityDescriptor(
            "release.demo_smoke",
            "Phase 32 Demo Smoke Test",
            32,
            ExecutionClass.REPORT_ONLY,
            "eva release smoke test",
            PHASE32_VERIFIER,
            "available",
            "Safe local demo-smoke checklist.",
        ),
        CapabilityDescriptor(
            "release.post_push_sync",
            "Phase 32 Post-Push Sync Status",
            32,
            ExecutionClass.REPORT_ONLY,
            "eva release post push sync",
            PHASE32_VERIFIER,
            "available",
            "Post-push hygiene status without Git operations.",
        ),
        CapabilityDescriptor(
            "roadmap.execution_boundary_audit",
            "Execution Boundary Audit",
            33,
            ExecutionClass.REPORT_ONLY,
            "eva execution boundaries",
            PHASE33_VERIFIER,
            "available",
            "Classifies risky runtime surfaces before any capability graduation.",
        ),
        CapabilityDescriptor(
            "roadmap.command_catalog",
            "Command Catalog",
            34,
            ExecutionClass.REPORT_ONLY,
            "eva catalog status",
            PHASE33_VERIFIER,
            "foundation",
            "Typed command descriptors reduce fast-command routing drift.",
        ),
        CapabilityDescriptor(
            "roadmap.capability_catalog",
            "Capability Catalog Normalization",
            35,
            ExecutionClass.REPORT_ONLY,
            "eva catalog status",
            PHASE33_VERIFIER,
            "foundation",
            "Shared descriptors align registry, planner, docs, and verifiers.",
        ),
        CapabilityDescriptor(
            "roadmap.control_truth_panels",
            "Control Center Truth Panels",
            36,
            ExecutionClass.REPORT_ONLY,
            "eva roadmap status",
            PHASE33_VERIFIER,
            "planned",
            "Dashboards should render capability state from the catalog.",
        ),
        CapabilityDescriptor(
            "roadmap.frontend_truth",
            "Frontend Truth and Demo Polish",
            37,
            ExecutionClass.REPORT_ONLY,
            "eva frontend truth status",
            PHASE33_VERIFIER,
            "available",
            "Frontend labels and safe demo chips reflect report-only state.",
        ),
        CapabilityDescriptor(
            "roadmap.grounded_answers",
            "Grounded Answer Quality",
            38,
            ExecutionClass.REPORT_ONLY,
            "eva grounded answer status",
            PHASE33_VERIFIER,
            "available",
            "Architecture and capability answers should route to catalog-backed text.",
        ),
        CapabilityDescriptor(
            "roadmap.voice_reliability",
            "Voice Reliability Pass",
            39,
            ExecutionClass.REPORT_ONLY,
            "eva voice reliability status",
            PHASE33_VERIFIER,
            "available",
            "Voice lifecycle, diagnostics, and pronunciation remain QA/report-only.",
        ),
        CapabilityDescriptor(
            "roadmap.verifier_dashboard",
            "Verifier Harness Dashboard",
            40,
            ExecutionClass.REPORT_ONLY,
            "eva verifier dashboard status",
            PHASE33_VERIFIER,
            "available",
            "Verifier metadata prepares tag/profile reporting while preserving quick/full.",
        ),
        CapabilityDescriptor(
            "roadmap.safe_real_pilot",
            "Optional Safe Real-Capability Pilot",
            41,
            ExecutionClass.BLOCKED,
            "eva execution boundaries",
            PHASE33_VERIFIER,
            "blocked-until-approved",
            "No capability is graduated without a later explicit approval phase.",
        ),
        CapabilityDescriptor(
            "roadmap.release_candidate_v2",
            "Release Candidate v2 Hardening",
            42,
            ExecutionClass.REPORT_ONLY,
            "eva roadmap status",
            PHASE33_VERIFIER,
            "planned",
            "Public release hardening remains documentation and verification only until separately approved.",
        ),
    )


def get_command_catalog() -> tuple[CommandDescriptor, ...]:
    return (
        CommandDescriptor("eva release smoke test", "release_demo_smoke", "release.demo_smoke", ExecutionClass.REPORT_ONLY, PHASE32_VERIFIER, "Safe local demo checklist."),
        CommandDescriptor("eva release post push sync", "release_post_push_sync", "release.post_push_sync", ExecutionClass.REPORT_ONLY, PHASE32_VERIFIER, "Post-push status report only."),
        CommandDescriptor("eva roadmap status", "roadmap_status", "roadmap.control_truth_panels", ExecutionClass.REPORT_ONLY, PHASE33_VERIFIER, "Phase 33-42 roadmap status."),
        CommandDescriptor("eva execution boundaries", "execution_boundaries", "roadmap.execution_boundary_audit", ExecutionClass.REPORT_ONLY, PHASE33_VERIFIER, "Runtime safety boundary summary."),
        CommandDescriptor("eva catalog status", "catalog_status", "roadmap.capability_catalog", ExecutionClass.REPORT_ONLY, PHASE33_VERIFIER, "Descriptor catalog status."),
        CommandDescriptor("eva frontend truth status", "frontend_truth_status", "roadmap.frontend_truth", ExecutionClass.REPORT_ONLY, PHASE33_VERIFIER, "Frontend safe-demo truth status."),
        CommandDescriptor("eva grounded answer status", "grounded_answer_status", "roadmap.grounded_answers", ExecutionClass.REPORT_ONLY, PHASE33_VERIFIER, "Grounded answer quality status."),
        CommandDescriptor("eva voice reliability status", "voice_reliability_status", "roadmap.voice_reliability", ExecutionClass.REPORT_ONLY, PHASE33_VERIFIER, "Voice reliability roadmap status."),
        CommandDescriptor("eva verifier dashboard status", "verifier_dashboard_status", "roadmap.verifier_dashboard", ExecutionClass.REPORT_ONLY, PHASE33_VERIFIER, "Verifier metadata dashboard status."),
    )


def get_verifier_catalog() -> tuple[VerifierDescriptor, ...]:
    return (
        VerifierDescriptor(PHASE32_VERIFIER, 32, "release_demo", "quick", "low", False, False, ("phase32", "release", "demo-smoke")),
        VerifierDescriptor(PHASE33_VERIFIER, 33, "roadmap", "quick", "low", False, False, ("phase33", "roadmap", "safety-boundary", "catalog")),
        VerifierDescriptor("verify_eva_all.py", 40, "verification", "focused", "medium", False, False, ("phase40", "verifier-dashboard", "profiles")),
    )


def get_phase_roadmap() -> tuple[PhaseRoadmapEntry, ...]:
    return (
        PhaseRoadmapEntry(33, "Execution Boundary Audit", "Reconcile docs, runtime tools, planner routes, and safety gates.", "implemented-foundation", PHASE33_VERIFIER, ("Risky runtime tools classified.", "No new execution path enabled.")),
        PhaseRoadmapEntry(34, "Command Router Decomposition", "Move command identity into typed descriptors before deeper migrations.", "foundation", PHASE33_VERIFIER, ("Release and roadmap commands have descriptors.", "Fast-command behavior is preserved.")),
        PhaseRoadmapEntry(35, "Capability Catalog Normalization", "Unify capability metadata across registry, resources, schemas, planner, docs, and verifiers.", "foundation", PHASE33_VERIFIER, ("Phase 32 and roadmap capabilities are represented.", "Catalog drift is verifier-checked.")),
        PhaseRoadmapEntry(36, "Control Center and AI OS Truth Panels", "Render truthful state from normalized safety metadata.", "planned", PHASE33_VERIFIER, ("Dashboard copy distinguishes report-only, locked, and gated real actions.",)),
        PhaseRoadmapEntry(37, "Frontend UX Truth and Demo Polish", "Replace overbroad UI claims with safe demo and boundary language.", "implemented-foundation", PHASE33_VERIFIER, ("Unsafe quick chips are removed.", "Safe demo commands are visible.")),
        PhaseRoadmapEntry(38, "Grounded Answer and Routing Quality", "Route architecture/capability questions to deterministic catalog-backed answers.", "implemented-foundation", PHASE33_VERIFIER, ("Roadmap/grounding status commands are available.", "Natural routes avoid generic fallback for roadmap questions.")),
        PhaseRoadmapEntry(39, "Voice Reliability Pass", "Expose voice lifecycle and diagnostics work as a bounded QA phase.", "implemented-foundation", PHASE33_VERIFIER, ("Voice diagnostics are visible.", "No real provider is enabled by roadmap status.")),
        PhaseRoadmapEntry(40, "Verifier Harness Refactor", "Add verifier metadata while keeping existing quick/full profiles stable.", "implemented-foundation", PHASE33_VERIFIER, ("Verifier descriptors exist.", "Quick/full registration remains stable.")),
        PhaseRoadmapEntry(41, "Optional Safe Real-Capability Pilot", "Keep real capability graduation blocked until explicitly approved.", "blocked-until-approved", PHASE33_VERIFIER, ("No broad writes, clicks, sends, secrets, or browser-session reads.",)),
        PhaseRoadmapEntry(42, "Release Candidate v2 Hardening", "Refresh public release posture after catalog and truth-surface cleanup.", "planned", PHASE33_VERIFIER, ("No tag, release, upload, or publication is implied.",)),
    )
