from __future__ import annotations

from .conflict_detection import conflict_policy_text
from .context_rules import context_rules_text
from .freshness import freshness_policy_text
from .memory_policy import boundary_lines, memory_policy_text
from .privacy_filter import privacy_policy_text
from .retrieval_preview import retrieval_preview_text
from .source_model import source_model_text
from .status import get_memory_v3_status


def format_memory_v3_status() -> str:
    status = get_memory_v3_status()
    return "\n".join(
        [
            "Memory v3 status",
            *boundary_lines(),
            f"Status: {status.status}.",
            f"Mode: {status.mode}.",
            f"Provider SDKs enabled: {status.provider_sdks_enabled}.",
            f"Cloud memory enabled: {status.cloud_memory_enabled}.",
            f"Remote sync enabled: {status.remote_sync_enabled}.",
            f"Arbitrary file reads enabled: {status.arbitrary_file_reads_enabled}.",
            f"Arbitrary file writes enabled: {status.arbitrary_file_writes_enabled}.",
            f"Raw memory DB dumps enabled: {status.raw_memory_db_dumps_enabled}.",
            f"Next phase: {status.next_phase}.",
        ]
    )


def format_memory_v3_policy() -> str:
    return memory_policy_text()


def format_memory_v3_sources() -> str:
    return source_model_text()


def format_memory_v3_privacy() -> str:
    return privacy_policy_text()


def format_memory_v3_freshness() -> str:
    return freshness_policy_text()


def format_memory_v3_conflicts() -> str:
    return conflict_policy_text()


def format_memory_v3_retrieval_preview() -> str:
    return "\n".join([context_rules_text(), "", retrieval_preview_text()])


def format_memory_v3_readiness() -> str:
    return "\n".join(
        [
            "Memory v3 readiness",
            *boundary_lines(),
            "Ready for deterministic local memory policy/status/retrieval-preview use.",
            "No provider SDKs are used.",
            "No cloud memory or remote sync is used.",
            "No .env, .env.local, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read.",
            "Raw memory database dumps are blocked.",
            "Arbitrary file reads/writes are blocked.",
            "Memory is source-aware, trust-aware, freshness-aware, privacy-aware, conflict-aware, and grounding-aware.",
            "Sensitive, injected, stale, conflicting, or ungrounded memories are excluded or marked.",
            "Browser/desktop/shell/cloud/MCP execution remains locked.",
            "Phase 12L narrow approved new .md/.txt creation remains a gated file write path.",
            "Next phase: Phase 22 Voice Assistant.",
        ]
    )
