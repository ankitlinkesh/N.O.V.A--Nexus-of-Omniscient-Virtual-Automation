from __future__ import annotations

from collections import Counter

from .catalog import (
    get_capability_catalog,
    get_command_catalog,
    get_execution_boundary_catalog,
    get_phase_roadmap,
    get_verifier_catalog,
)
from .models import ExecutionClass


BOUNDARY_FOOTER = (
    "Roadmap scope: Phase 33 through Phase 42 are safety/catalog/quality hardening phases.",
    "No new execution path is enabled by these roadmap commands.",
    "Phase 12L remains the only real project write boundary.",
    "No secrets, cookies, passwords, browser sessions, config secrets, package publishing, tag, release, push, or upload is performed.",
)


def _bullets(items: tuple[str, ...] | list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _output(title: str, body: str) -> str:
    return "\n".join((title, body, "", *BOUNDARY_FOOTER))


def format_phase_roadmap() -> str:
    phases = get_phase_roadmap()
    lines = [
        "Eva phase improvement roadmap",
        "Phase 33 is the current implemented foundation for execution-boundary and catalog truth.",
        "Phase 42 remains release-candidate v2 hardening and is not a publication action.",
        "",
        "Phase plan:",
    ]
    for item in phases:
        lines.append(f"- Phase {item.phase}: {item.title} ({item.status}) — {item.goal}")
    lines.extend(
        [
            "",
            "Acceptance themes:",
            "- Execution boundary audit before capability graduation.",
            "- Command and capability descriptors before router expansion.",
            "- Frontend/demo/status surfaces must say report-only when they are report-only.",
            "- Verifier metadata grows without breaking existing quick/full profiles.",
        ]
    )
    return _output("Eva phase improvement roadmap", "\n".join(lines))


def format_execution_boundary_audit() -> str:
    boundaries = get_execution_boundary_catalog()
    counts = Counter(item.execution_class.value for item in boundaries)
    lines = [
        "Eva execution boundary audit",
        "Phase 33 classifies runtime surfaces before any execution expansion.",
        "Phase 42 release-candidate v2 hardening still depends on these boundaries staying truthful.",
        "",
        "Execution classes:",
    ]
    for cls in ExecutionClass:
        lines.append(f"- {cls.value}: {counts.get(cls.value, 0)} surfaces")
    lines.extend(["", "Audited surfaces:"])
    for item in boundaries:
        label = item.tool_id or item.surface_id
        lines.append(f"- {label}: {item.execution_class.value}; gate: {item.gate}; verifier: {item.verifier}")
    lines.extend(
        [
            "",
            "Current decision:",
            "- Risky tool-registry surfaces are cataloged as gated-real-action, not safe-demo commands.",
            "- Secrets/session/config access remains blocked.",
            "- The optional Phase 41 pilot is blocked until a later explicit approval phase.",
        ]
    )
    return _output("Eva execution boundary audit", "\n".join(lines))


def format_catalog_status() -> str:
    capabilities = get_capability_catalog()
    commands = get_command_catalog()
    verifiers = get_verifier_catalog()
    phases = get_phase_roadmap()
    phase_counts = Counter(item.phase for item in capabilities)
    class_counts = Counter(item.execution_class.value for item in capabilities)
    lines = [
        "Eva catalog status",
        "Phase 33 adds typed descriptors for roadmap execution boundaries.",
        "Phase 42 remains represented as a planned hardening capability, not a release action.",
        "",
        f"Capability descriptors: {len(capabilities)}",
        f"Command descriptors: {len(commands)}",
        f"Verifier descriptors: {len(verifiers)}",
        f"Roadmap phases: {len(phases)}",
        "",
        "Capability execution classes:",
    ]
    for name, count in sorted(class_counts.items()):
        lines.append(f"- {name}: {count}")
    lines.extend(["", "Capability phases:"])
    for phase, count in sorted(phase_counts.items()):
        lines.append(f"- Phase {phase}: {count} capabilities")
    lines.extend(
        [
            "",
            "Drift-control rule:",
            "- New roadmap commands should add a command descriptor, capability descriptor, verifier descriptor, and docs/verifier coverage together.",
        ]
    )
    return _output("Eva catalog status", "\n".join(lines))


def format_frontend_truth_status() -> str:
    lines = [
        "Eva frontend truth status",
        "Phase 37 foundation is active: the UI should describe safe demo/report-only state plainly.",
        "Phase 33 execution boundary language is visible before Phase 42 hardening.",
        "",
        "Frontend truth rules:",
        "- Prefer Safe Demo / Report-only labels over broad operator claims.",
        "- Safe quick chips should use `eva release smoke test`, `eva roadmap status`, and `eva execution boundaries`.",
        "- Locked features need plain explanations instead of optimistic badges.",
        "- Voice diagnostics should be visible without enabling a live provider.",
    ]
    return _output("Eva frontend truth status", "\n".join(lines))


def format_grounded_answer_status() -> str:
    lines = [
        "Eva grounded answer status",
        "Phase 38 foundation is active: capability and architecture questions should route to catalog-backed text.",
        "Phase 33 provides the first source of truth, and Phase 42 should only refresh public claims after verification.",
        "",
        "Grounding rules:",
        "- `what can Eva execute safely` routes to execution boundaries.",
        "- `show Eva roadmap status` routes to the typed phase roadmap.",
        "- Provider names should be described as configured routes, not guessed credentials.",
        "- Generic LLM fallback should not be the first answer for Eva capability, safety, or architecture questions.",
    ]
    return _output("Eva grounded answer status", "\n".join(lines))


def format_voice_reliability_status() -> str:
    lines = [
        "Eva voice reliability status",
        "Phase 39 foundation is active: voice work is tracked as QA/report-only unless explicitly upgraded.",
        "Phase 33 and Phase 42 both keep voice provider changes behind verification.",
        "",
        "Voice QA targets:",
        "- Track queued, speaking, interrupted, complete, and failed states.",
        "- Keep transcript mismatch and mic-support diagnostics visible.",
        "- Add pronunciation handling for technical terms before broad voice demos.",
        "- Do not enable a new ASR/TTS provider from a roadmap/status command.",
    ]
    return _output("Eva voice reliability status", "\n".join(lines))


def format_verifier_dashboard_status() -> str:
    verifiers = get_verifier_catalog()
    tag_counts: Counter[str] = Counter()
    for verifier in verifiers:
        tag_counts.update(verifier.tags)
    lines = [
        "Eva verifier dashboard status",
        "Phase 40 foundation is active: verifier metadata exists while quick/full behavior stays stable.",
        "Phase 33 adds the focused roadmap verifier; Phase 42 hardening should reuse this metadata.",
        "",
        f"Tracked verifier descriptors: {len(verifiers)}",
        "Tags:",
    ]
    for tag, count in sorted(tag_counts.items()):
        lines.append(f"- {tag}: {count}")
    lines.extend(
        [
            "",
            "Verifier rules:",
            "- Focused phase verifier first.",
            "- Master quick profile before completion claims.",
            "- Full profile before any checkpoint commit.",
            "- Verifiers in this catalog must not mutate repo-tracked files.",
        ]
    )
    return _output("Eva verifier dashboard status", "\n".join(lines))
