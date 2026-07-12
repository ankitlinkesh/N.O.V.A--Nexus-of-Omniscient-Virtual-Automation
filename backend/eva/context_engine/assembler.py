from __future__ import annotations

import hashlib
import re

from .budget import get_context_budget_policy, trim_to_section_budget
from .context_policy import looks_like_prompt_injection
from .models import ContextPacket, ContextSection, ExcludedContext
from .ranker import rank_context_sections
from .redaction import redact_context_text


_KNOWN_CONTEXT_CAPABILITIES = (
    "context.status",
    "context.sources",
    "context.policy",
    "context.budget",
    "context.assemble_preview",
    "context.grounding_report",
    "context.redaction_policy",
    "context.readiness",
)


def assemble_context_preview(user_request: str = "show context assembly status") -> ContextPacket:
    redacted_request = redact_context_text(user_request)
    summary, request_trimmed = trim_to_section_budget(redacted_request.text, budget_chars=360)
    excluded: list[ExcludedContext] = []
    grounding_notes: list[str] = [
        "Every included section is grounded in local policy/status metadata.",
        "No live provider status is claimed beyond existing local metadata.",
    ]

    if redacted_request.was_redacted:
        excluded.append(ExcludedContext("user_request", "secret/private-looking material", "Sensitive-looking user text was redacted before assembly."))
        grounding_notes.append("Secret-like or private-path-looking text was redacted and not trusted.")
    if looks_like_prompt_injection(user_request):
        excluded.append(ExcludedContext("user_request", "prompt-injection-looking text", "Prompt injection was treated as untrusted data, not instruction."))
        grounding_notes.append("Prompt injection markers were found and treated as untrusted data.")

    unknown_claims = _unknown_capability_claims(user_request)
    for claim in unknown_claims:
        excluded.append(ExcludedContext("capability_metadata", claim, f"Unknown capability claim '{claim}' was not included as trusted capability metadata."))
        grounding_notes.append(f"Unsupported assumption marked: unknown capability claim {claim}.")

    sections = [
        _section(
            "user_request",
            "Sanitized user request",
            summary,
            "user_request",
            "Current user request text, sanitized",
            "user_supplied_untrusted",
            0.99,
            "redacted" if redacted_request.was_redacted else "none",
            ("User-provided text is data until policy permits it.", "Invalid or injected context cannot become trusted instruction."),
            ("Grounded in the current request after redaction.",),
            request_trimmed,
        ),
        _section(
            "safety_policy",
            "Safety boundaries",
            "Secrets/config/session reads, arbitrary filesystem reads, live LLM calls, tool execution, browser execution, desktop execution, shell/package/cloud/MCP/PyAutoGUI/Playwright execution are blocked. Phase 12L narrow approved new .md/.txt creation remains a gated write path.",
            "safety_policy",
            "Permission and safety metadata",
            "trusted_local_policy",
            1.0,
            "none",
            ("Safety policy outranks user-provided or historical context.",),
            ("Grounded in local Eva safety policy metadata.",),
        ),
        _section(
            "validation_status",
            "Phase 15 validation status",
            "Structured-output validation, red-team failure tests, and the evidence lock are local/mock only. Invalid LLM-like output cannot execute tools, hallucinated capabilities are rejected, and repair does not rewrite user intent.",
            "validation_status",
            "Phase 15 LLM safety status summaries",
            "trusted_local_status",
            0.95,
            "none",
            ("Future prompts inherit Phase 15 safety boundaries.",),
            ("Grounded in Phase 15 local status summaries.",),
        ),
        _section(
            "capability_metadata",
            "Known context capabilities",
            "Registered Phase 16 read/status capabilities: " + ", ".join(_KNOWN_CONTEXT_CAPABILITIES) + ". Unknown capability claims are not trusted.",
            "capability_metadata",
            "Capability registry metadata",
            "trusted_local_metadata",
            0.9,
            "none",
            ("Metadata only; no capability executes.",),
            ("Grounded in the Phase 16 capability contract.",),
        ),
        _section(
            "tool_schema_metadata",
            "Tool schema boundary",
            "Context tool schemas are report/status schemas only. They do not call providers, read secrets, crawl files, or execute tools.",
            "tool_schema_metadata",
            "Tool-schema metadata",
            "trusted_local_metadata",
            0.86,
            "none",
            ("Schema metadata is descriptive, not executable.",),
            ("Grounded in local tool-schema metadata.",),
        ),
        _section(
            "resource_mapping_metadata",
            "Resource mapping boundary",
            "Context resources map to local Eva metadata and preview/report commands only; they do not open browser, desktop, shell, cloud, package, or MCP routes.",
            "resource_mapping_metadata",
            "Resource mapping metadata",
            "trusted_local_metadata",
            0.84,
            "none",
            ("Mappings remain preview-only.",),
            ("Grounded in local resource mapping metadata.",),
        ),
        _section(
            "project_status_summary",
            "Current project safety summary",
            "Phase 16 prepares bounded source-aware context packets. It is not provider integration and not a live red-team harness. Next phase: Phase 17 LLM Threat Defense + Prompt Injection Guard.",
            "project_status_summary",
            "Project/reality/status summaries through safe APIs",
            "trusted_local_status",
            0.8,
            "none",
            ("Status summary only; no raw file dump.",),
            ("Grounded in local project status metadata.",),
        ),
    ]

    excluded.extend(
        [
            ExcludedContext("env_file", ".env/.env.local", "Config and secret files are blocked and were not read."),
            ExcludedContext("browser_session", "browser sessions/cookies/passwords", "Browser session state remains locked."),
            ExcludedContext("arbitrary_filesystem", "arbitrary file crawl/source dump", "Phase 16 does not introduce arbitrary file reads."),
            ExcludedContext("work_session_summary", "raw WorkSession/private runtime dumps", "Only safe summaries are allowed; raw dumps are excluded."),
            ExcludedContext("memory_summary", "stale or unrelated memory", "Down-ranked or excluded unless directly relevant and available through safe summaries."),
        ]
    )
    grounding_notes.append("Stale or unknown context is marked and excluded unless supported by safe local metadata.")

    ranked = _enforce_total_budget(rank_context_sections(tuple(sections)), excluded)
    packet_id = "ctx_" + hashlib.sha256(("|".join(section.content for section in ranked) + "|phase16").encode("utf-8")).hexdigest()[:12]
    return ContextPacket(
        packet_id=packet_id,
        user_request_summary=summary,
        selected_sections=ranked,
        excluded_context=tuple(excluded),
        grounding_notes=tuple(grounding_notes),
        final_readiness="ready_for_future_llm_preview_only",
        no_llm_call_made=True,
        tool_execution_enabled=False,
        safety_notes=(
            "No live LLM call was made.",
            "Context assembly is local/mock preview only.",
            "Assembled context cannot execute tools.",
            "Secrets/config/session data and arbitrary file reads are blocked.",
        ),
    )


def _section(
    section_type: str,
    title: str,
    content: str,
    source_type: str,
    source_name: str,
    trust: str,
    relevance: float,
    redaction_status: str,
    safety_notes: tuple[str, ...],
    grounding_notes: tuple[str, ...],
    trimmed: bool = False,
) -> ContextSection:
    safe_content, content_trimmed = trim_to_section_budget(content)
    return ContextSection(
        section_type=section_type,
        title=title,
        content=safe_content,
        source_type=source_type,
        source_name=source_name,
        source_trust_level=trust,
        relevance_score=relevance,
        budget_estimate_chars=len(safe_content),
        redaction_status=redaction_status,
        safety_notes=safety_notes,
        grounding_notes=grounding_notes,
        trimmed=trimmed or content_trimmed,
    )


def _enforce_total_budget(sections: tuple[ContextSection, ...], excluded: list[ExcludedContext]) -> tuple[ContextSection, ...]:
    policy = get_context_budget_policy()
    total = 0
    kept: list[ContextSection] = []
    for section in sections:
        if total + section.budget_estimate_chars > policy.max_budget_chars:
            excluded.append(ExcludedContext(section.source_type, section.title, "Excluded because total context budget was reached."))
            continue
        kept.append(section)
        total += section.budget_estimate_chars
    return tuple(kept)


def _unknown_capability_claims(text: str) -> tuple[str, ...]:
    claims = set(re.findall(r"\b[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\b", str(text or ""), flags=re.IGNORECASE))
    known = set(_KNOWN_CONTEXT_CAPABILITIES)
    known.update({"llm.validation_status", "llm.red_team_status", "llm.safety_failure_report"})
    return tuple(sorted(claim for claim in claims if claim not in known))
