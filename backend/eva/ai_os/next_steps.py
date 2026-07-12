from __future__ import annotations

from .safety_boundaries import boundary_lines


def next_safe_step_text() -> str:
    return "\n".join(
        [
            "AI OS next safe step",
            *boundary_lines(),
            "Recommended next phase: continue Phase 33 Execution Boundary Audit / Roadmap Foundations before any real capability graduation.",
            "Phase 33 through Phase 42 are safety/catalog/quality hardening phases.",
            "Phase 41 safe real-capability pilot remains blocked until a later explicit approval phase.",
            "Phase 42 Release Candidate v2 Hardening is documentation/verification hardening only.",
            "No new execution path is enabled; Phase 12L remains the only real write boundary.",
            "The dashboard recommendation is metadata only and starts no work automatically.",
        ]
    )
