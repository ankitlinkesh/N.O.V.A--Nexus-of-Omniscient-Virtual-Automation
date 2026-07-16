"""Self-improvement — Eva learns new skills from what worked (Phase 47).

The capstone, built so that improving cannot mean escalating:

    **A learned skill COMPOSES tools that already exist. Eva never writes code.**

Learning reads the Phase 36 flight recorder for tool sequences that already
happened, repeatedly, and worked, and proposes naming them. A proposal is inert
until a human approves it, and running one is just ``ToolRegistry.run`` per step
— so the gate governs every action exactly as it always did. A skill is
convenience, never capability.
"""

from __future__ import annotations

import os
from pathlib import Path

from .executor import run_skill
from .models import (
    APPROVED,
    PROPOSED,
    REJECTED,
    LearnedSkill,
    SkillStep,
)
from .store import SkillStore
from .synthesis import NEVER_LEARN_TOOLS, propose_skills_from_traces, validate_steps

_ABSENT = {"", "0", "false", "no", "off"}

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DEFAULT_SKILLS_PATH = _DATA_DIR / "eva_skills.sqlite3"


def self_improvement_enabled(environ: dict[str, str] | None = None) -> bool:
    """Whether skill learning is active (default OFF, empty == off)."""
    env = environ if environ is not None else os.environ
    return env.get("EVA_SELF_IMPROVEMENT_ENABLED", "").strip().lower() not in _ABSENT


def default_skills_path() -> Path:
    return _DEFAULT_SKILLS_PATH


def open_default_store(environ: dict[str, str] | None = None) -> SkillStore | None:
    """Open the learned-skill store, or ``None`` when disabled."""
    try:
        if not self_improvement_enabled(environ):
            return None
        return SkillStore(_DEFAULT_SKILLS_PATH)
    except Exception:
        return None


def learn_from_recent_traces(store: SkillStore, registry, *, limit: int = 25) -> dict[str, object]:
    """The trace-driven learning loop: mine recent traces, propose new skills.

    Proposals only — every candidate lands ``proposed`` and stays inert until a
    human approves it. Fail-safe."""
    result: dict[str, object] = {"scanned": 0, "proposed": [], "note": "Proposed skills are inert until you approve them."}
    try:
        from ..observability.traces import list_traces, read_trace

        summaries = list_traces(limit=limit)
        traces = []
        for summary in summaries:
            trace_id = summary.get("trace_id")
            if not trace_id:
                continue
            traces.append(read_trace(trace_id))
        result["scanned"] = len(traces)

        proposed_names: list[str] = []
        for candidate in propose_skills_from_traces(traces, registry):
            skill = store.propose(
                candidate["name"],
                candidate["description"],
                candidate["steps"],
                source_trace_id=candidate.get("source_trace_id", ""),
                observed_count=candidate.get("observed_count", 1),
            )
            if skill is not None:
                proposed_names.append(skill.name)
        result["proposed"] = proposed_names
    except Exception:
        pass
    return result


__all__ = [
    "SkillStore",
    "LearnedSkill",
    "SkillStep",
    "run_skill",
    "propose_skills_from_traces",
    "validate_steps",
    "learn_from_recent_traces",
    "self_improvement_enabled",
    "default_skills_path",
    "open_default_store",
    "NEVER_LEARN_TOOLS",
    "PROPOSED",
    "APPROVED",
    "REJECTED",
]
