from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class ExecutionClass(str, Enum):
    REPORT_ONLY = "report-only"
    READ_ONLY = "read-only"
    SANDBOX_ONLY = "sandbox-only"
    PHASE12L_WRITE = "phase12l-write"
    GATED_REAL_ACTION = "gated-real-action"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ExecutionBoundary:
    surface_id: str
    execution_class: ExecutionClass
    gate: str
    verifier: str
    notes: str
    tool_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["execution_class"] = self.execution_class.value
        return payload


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    name: str
    phase: int
    execution_class: ExecutionClass
    command: str
    verifier: str
    status: str
    notes: str

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["execution_class"] = self.execution_class.value
        return payload


@dataclass(frozen=True)
class CommandDescriptor:
    command: str
    intent: str
    capability_id: str
    execution_class: ExecutionClass
    verifier: str
    notes: str

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["execution_class"] = self.execution_class.value
        return payload


@dataclass(frozen=True)
class VerifierDescriptor:
    script: str
    phase: int
    subsystem: str
    profile: str
    risk: str
    requires_network: bool
    mutates_repo_tracked_files: bool
    tags: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PhaseRoadmapEntry:
    phase: int
    title: str
    goal: str
    status: str
    verifier: str
    acceptance: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)
