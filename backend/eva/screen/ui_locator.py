from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class UiTarget:
    target_id: str
    label: str
    role: str
    x: int
    y: int
    width: int
    height: int
    confidence: float
    method: str
    app: str | None = None
    window_title: str | None = None
    safety_notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "UiTarget":
        return cls(
            target_id=str(value.get("target_id") or uuid4().hex),
            label=str(value.get("label") or "target"),
            role=str(value.get("role") or "unknown"),
            x=int(value.get("x") or 0),
            y=int(value.get("y") or 0),
            width=max(1, int(value.get("width") or 1)),
            height=max(1, int(value.get("height") or 1)),
            confidence=max(0.0, min(1.0, float(value.get("confidence") or 0.0))),
            method=str(value.get("method") or "unknown"),
            app=str(value.get("app") or "") or None,
            window_title=str(value.get("window_title") or "") or None,
            safety_notes=[str(item) for item in value.get("safety_notes") or []],
        )


def locate_by_text_hint(text: str) -> UiTarget | None:
    """Resolve a text label to an on-screen target via GUI grounding (Phase 56).

    Returns ``None`` when grounding is disabled or nothing matches confidently, so
    the behaviour is byte-identical to the old stub whenever grounding is off."""
    try:
        from .grounding import grounding_enabled, locate

        if not grounding_enabled():
            return None
        return locate(str(text or ""))
    except Exception:
        return None


def locate_by_image_template(template_path: str) -> UiTarget | None:
    try:
        import cv2  # type: ignore  # noqa: F401
    except Exception:
        return None
    return None


def locate_ui_targets(observation: Any, hints: list[str] | tuple[str, ...] | None = None) -> list[UiTarget]:
    raw_targets = []
    if isinstance(observation, dict):
        raw_targets = observation.get("ui_targets") or []
    else:
        raw_targets = getattr(observation, "ui_targets", []) or []
    targets = [UiTarget.from_dict(item) for item in raw_targets if isinstance(item, dict)]
    if not hints:
        return targets
    clean_hints = [str(item).lower() for item in hints if str(item).strip()]
    if not clean_hints:
        return targets
    return [target for target in targets if any(hint in target.label.lower() or hint in target.role.lower() for hint in clean_hints)]


def choose_target(observation: Any, goal: str, required_confidence: float = 0.75) -> UiTarget | None:
    hints = [part for part in str(goal or "").lower().split() if len(part) >= 3]
    targets = locate_ui_targets(observation, hints)
    if not targets:
        targets = locate_ui_targets(observation)
    confident = [target for target in targets if target.confidence >= required_confidence]
    if not confident:
        return None
    return sorted(confident, key=lambda target: target.confidence, reverse=True)[0]


def choose_safe_click_target(observation: Any, goal: Any, required_confidence: float = 0.75) -> UiTarget | None:
    target = getattr(goal, "params", {}).get("target") if goal is not None else None
    if isinstance(target, dict):
        candidate = UiTarget.from_dict(target)
        if candidate.confidence >= required_confidence and candidate.method != "raw_coordinate":
            return candidate
        return None
    if isinstance(goal, str):
        return choose_target(observation, goal, required_confidence=required_confidence)
    return None
