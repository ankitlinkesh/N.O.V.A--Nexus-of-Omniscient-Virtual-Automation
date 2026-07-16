"""Data model for learned skills (Phase 47).

The single most important design decision in this package is encoded here: a
learned skill is **a sequence of calls to tools that already exist**, not code.

``SkillStep.tool`` is a tool *name* that must resolve in the live
:class:`~eva.tools.registry.ToolRegistry`. There is no field for a code body, a
shell command, an import, or an ``action_type`` — deliberately. A skill
therefore cannot express any capability Eva did not already have, and cannot
describe itself as safer than the tool it calls. See
:mod:`eva.self_improvement.synthesis` for why.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Lifecycle. A skill Eva proposes is INERT until a human approves it.
PROPOSED = "proposed"
APPROVED = "approved"
REJECTED = "rejected"

SKILL_STATUSES = frozenset({PROPOSED, APPROVED, REJECTED})

MAX_SKILL_STEPS = 12
MAX_NAME_LEN = 80


@dataclass(frozen=True)
class SkillStep:
    """One step of a learned skill: call an EXISTING tool with these args.

    Note what is absent: no code, no shell, no action_type. A step can only ever
    name a tool the registry already exposes, and the permission gate classifies
    that tool from its real ToolSpec — never from anything written here.
    """

    tool: str
    args: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearnedSkill:
    """A named, reusable workflow Eva learned by watching what actually worked."""

    id: str
    name: str
    description: str
    steps: tuple[SkillStep, ...]
    status: str = PROPOSED
    source_trace_id: str = ""
    observed_count: int = 1     # how many traces showed this sequence
    uses: int = 0               # how many times it has been run since approval
    created_at: str = ""
    approved_at: str | None = None

    @property
    def is_runnable(self) -> bool:
        """Only an approved skill may ever be executed."""
        return self.status == APPROVED

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [step.as_dict() for step in self.steps]
        data["is_runnable"] = self.is_runnable
        return data


__all__ = [
    "SkillStep",
    "LearnedSkill",
    "PROPOSED",
    "APPROVED",
    "REJECTED",
    "SKILL_STATUSES",
    "MAX_SKILL_STEPS",
    "MAX_NAME_LEN",
]
