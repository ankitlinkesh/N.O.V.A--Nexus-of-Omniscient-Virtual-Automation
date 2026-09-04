from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

TaskStatus = Literal["planning", "running", "reflecting", "waiting_for_confirmation", "done", "failed", "cancelled"]
StepStatus = Literal["planned", "running", "done", "failed", "skipped"]
ReflectionStatus = Literal["continue", "complete", "blocked", "needs_confirmation"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentStep:
    index: int
    thought_summary: str
    planned_action: str
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    observation: str = ""
    status: StepStatus = "planned"
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentReflection:
    step_index: int
    summary: str
    status: ReflectionStatus = "continue"
    confidence: float = 0.5
    next_focus: str = ""
    created_at: str = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentTask:
    user_goal: str
    id: str = field(default_factory=lambda: uuid4().hex)
    status: TaskStatus = "planning"
    plan: list[str] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    reflections: list[AgentReflection] = field(default_factory=list)
    memory_notes: list[str] = field(default_factory=list)
    final_response: str = ""
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    max_steps: int = 6
    max_tool_calls: int = 10
    max_web_searches: int = 4
    max_screen_captures: int = 2

    def touch(self) -> None:
        self.updated_at = utc_now()

    def add_step(self, step: AgentStep) -> None:
        self.steps.append(step)
        self.touch()

    def add_observation(self, observation: str) -> None:
        self.observations.append(observation)
        self.touch()

    def add_reflection(self, reflection: AgentReflection) -> None:
        self.reflections.append(reflection)
        self.touch()

    def add_memory_note(self, note: str) -> None:
        self.memory_notes.append(note)
        self.touch()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_goal": self.user_goal,
            "status": self.status,
            "plan": list(self.plan),
            "steps": [step.as_dict() for step in self.steps],
            "observations": list(self.observations),
            "reflections": [reflection.as_dict() for reflection in self.reflections],
            "memory_notes": list(self.memory_notes),
            "final_response": self.final_response,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "max_steps": self.max_steps,
            "max_tool_calls": self.max_tool_calls,
            "max_web_searches": self.max_web_searches,
            "max_screen_captures": self.max_screen_captures,
        }


_UNTRUSTED_OPEN = "[UNTRUSTED "
_UNTRUSTED_CLOSE = "[END UNTRUSTED "
_MAX_REPORTED_CHARS = 400


def readable_observation(observation: str) -> tuple[str, bool]:
    """An observation as a person should read it, plus whether it was wrapped.

    Tool output is fenced in an explicit trust-boundary banner for the *model's*
    benefit. Showing that banner to a person is noise, but silently dropping the
    fact that the text is quoted external data would be worse than noise -- so the
    wrapper is stripped and the flag is returned instead.

    Lives here rather than in ``runner`` because ``cognition`` needs it too and
    ``runner`` imports ``cognition``; ``task`` is imported by both and imports
    neither.
    """
    text = (observation or "").strip()
    untrusted = text.startswith(_UNTRUSTED_OPEN)
    if untrusted:
        _, _, rest = text.partition("]\n")
        text = rest or text
        cut = text.find(_UNTRUSTED_CLOSE)
        if cut != -1:
            text = text[:cut]
    text = " ".join(text.split())
    if len(text) > _MAX_REPORTED_CHARS:
        text = text[:_MAX_REPORTED_CHARS].rstrip() + "..."
    return text, untrusted
