"""Filling a form — chaining locate -> click -> type, safely (Phase 58).

Phase 56 made a single field clickable by label and Phase 57 made the screen
observable. This composes them into the thing people actually ask for: "fill in
this form." For each (label, value) it clicks the field to focus it and types the
value — going through the ordinary gated tools every step, so it inherits the
confidence gate, the real-input gate, and the Phase 55 risk escalation. It adds
no new authority; it is pure orchestration over tools NOVA already has.

Three safety commitments:

  * **It never records the values.** A form value is often a password or a
    payment detail. A :class:`FillStep` carries only the field label, whether the
    value looked like a live secret, and the outcome — never the value itself.
    Nothing here logs, traces, or returns the typed text.
  * **It stops rather than blunders.** The moment a field cannot be found (or a
    click/type is refused, e.g. real input is off), it stops and reports where —
    it does not keep typing values into the wrong places on a half-understood
    form.
  * **It is driven only from the trusted console.** Like NL rule creation, this
    is reached from a typed fast-command, never wired as a planner tool — so
    untrusted content (Phase 40) cannot make NOVA type attacker-chosen values
    into a form.

The executor is injectable, so the orchestration is tested without a real
desktop; the default routes every step through the real ToolRegistry gate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Sequence

Executor = Callable[..., dict]


@dataclass(frozen=True)
class FormField:
    """One field to fill. ``value`` is sensitive and never leaves this object."""

    label: str
    value: str


@dataclass(frozen=True)
class FillStep:
    """The outcome of one field — deliberately value-free."""

    label: str
    status: str          # filled | not_found | click_refused | type_refused
    secret: bool = False  # did the value look like a live secret?
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FillOutcome:
    steps: list[FillStep] = field(default_factory=list)
    filled: int = 0
    ok: bool = False
    stopped_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"steps": [s.as_dict() for s in self.steps], "filled": self.filled, "ok": self.ok, "stopped_reason": self.stopped_reason}


def _looks_like_secret(value: str) -> bool:
    try:
        from ..privacy.secrets_broker import contains_secret_leak

        return bool(contains_secret_leak(value))
    except Exception:
        # Fail cautious: if we cannot tell, treat it as sensitive (mask it).
        return True


def _ok(result: object) -> bool:
    return isinstance(result, dict) and result.get("ok") is True


def _error_of(result: object) -> str:
    if isinstance(result, dict):
        return str(result.get("error") or "") + " " + str(result.get("message") or "")
    return ""


def _default_executor() -> Executor:
    from ..tools.registry import ToolRegistry

    registry = ToolRegistry()

    def run(tool: str, **kwargs: Any) -> dict:
        result = registry.run(tool, **kwargs)
        return result if isinstance(result, dict) else {"ok": False, "error": "non_dict_result"}

    return run


def fill_form(
    fields: Sequence[FormField | tuple[str, str]],
    *,
    reason: str,
    executor: Executor | None = None,
) -> FillOutcome:
    """Fill each field in order via gated click+type. Stops at the first failure.

    Returns a value-free :class:`FillOutcome`. ``executor(tool, **kwargs)`` is the
    seam — it defaults to routing through the real ToolRegistry gate, so every
    click and keystroke faces the same permission checks as a typed command.
    """
    run = executor or _default_executor()
    normalized = [f if isinstance(f, FormField) else FormField(str(f[0]), str(f[1])) for f in fields]

    steps: list[FillStep] = []
    filled = 0
    for spec in normalized:
        label = spec.label.strip()
        secret = _looks_like_secret(spec.value)
        if not label:
            steps.append(FillStep("", "not_found", secret, "empty field label"))
            return FillOutcome(steps, filled, False, "a field had no label")

        # 1. Focus the field. The gated tool resolves the label via grounding and
        #    enforces the confidence + real-input gates; we only read its verdict.
        click = run("screen.click", reason=reason, label=label)
        if not _ok(click):
            err = _error_of(click).lower()
            if "ambiguous" in err:
                steps.append(FillStep(label, "ambiguous", secret, _error_of(click).strip()[:200]))
                return FillOutcome(steps, filled, False, f"'{label}' matched several fields; be more specific")
            if "ui_target_not_found" in err or "target_required" in err or "low_confidence" in err:
                steps.append(FillStep(label, "not_found", secret, f"could not find field '{label}' on screen"))
                return FillOutcome(steps, filled, False, f"could not find field '{label}'")
            steps.append(FillStep(label, "click_refused", secret, _error_of(click).strip()[:160]))
            return FillOutcome(steps, filled, False, f"click on '{label}' was refused")

        # 2. Type the value. Never store or return the value itself.
        typed = run("screen.type_text", reason=reason, text=spec.value)
        if not _ok(typed):
            steps.append(FillStep(label, "type_refused", secret, _error_of(typed).strip()[:160]))
            return FillOutcome(steps, filled, False, f"typing into '{label}' was refused")

        steps.append(FillStep(label, "filled", secret))
        filled += 1

    return FillOutcome(steps, filled, True, None)


def parse_form_spec(text: str) -> list[FormField]:
    """Parse ``Email=me@x.com; Password=secret; Full Name=John`` into fields.

    Order-preserving. Labels may contain spaces; the split is on the FIRST '='
    of each ';'-separated clause so values may contain '='. Clauses without an
    '=' are skipped. Values are kept verbatim (only outer whitespace trimmed)."""
    fields: list[FormField] = []
    for clause in str(text or "").split(";"):
        if "=" not in clause:
            continue
        label, value = clause.split("=", 1)
        label = label.strip()
        value = value.strip()
        if label and value:
            fields.append(FormField(label, value))
    return fields


__all__ = ["FormField", "FillStep", "FillOutcome", "fill_form", "parse_form_spec"]
