"""Running a learned skill — every step through the gate (Phase 47).

This is where the composition design earns its keep. Executing a skill is not a
special execution path: it is an ordinary sequence of ``ToolRegistry.run`` calls.
That single fact carries the whole safety argument.

  * The gate classifies each step from the tool's **real** ToolSpec, so a
    confirm/override-class step inside a skill is still confirm/override-class.
    A skill has no way to say "run this without asking" — there is nowhere to
    write it down (see :mod:`eva.self_improvement.models`).
  * A gated step does not execute; ``run`` returns a pending descriptor and the
    skill **stops there** rather than barrelling on through a workflow whose
    precondition never happened.
  * Only an ``approved`` skill runs at all. A proposed skill is inert.

So a learned skill is convenience, never capability: it can do exactly what the
user could already have authorized step by step, and nothing else.
"""

from __future__ import annotations

from typing import Any

from .models import LearnedSkill
from .synthesis import validate_steps


def _is_gated_result(result: Any) -> bool:
    """Whether the gate held this call for confirmation instead of running it."""
    return isinstance(result, dict) and bool(result.get("requires_confirmation"))


def run_skill(skill: LearnedSkill, registry: Any, *, store: Any = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute an approved skill's steps through the permission gate.

    Returns a report: which steps ran, where it stopped and why. Never raises.
    Refuses outright unless the skill is approved and every step still resolves
    to a real registry tool (a tool can be removed after a skill is approved —
    revalidate every run rather than trusting approval-time state).
    """
    report: dict[str, Any] = {
        "skill": getattr(skill, "name", ""),
        "ran": [],
        "ok": False,
        "stopped_reason": "",
        "gated_step": "",
        "note": "Every step runs through the permission gate; a gated step stops the skill and waits for you.",
    }
    try:
        if skill is None:
            report["stopped_reason"] = "no_skill"
            return report
        # Only an approved skill may run. A proposal is inert.
        if not skill.is_runnable:
            report["stopped_reason"] = f"skill_not_approved:{skill.status}"
            return report

        # Revalidate against the LIVE registry: approval is not a permanent
        # licence, and a tool may have been removed since.
        ok, reason = validate_steps(skill.steps, registry)
        if not ok:
            report["stopped_reason"] = f"invalid_steps:{reason}"
            return report

        for step in skill.steps:
            args = dict(step.args or {})
            if overrides:
                args.update(overrides.get(step.tool) or {})
            try:
                result = registry.run(step.tool, **args)
            except Exception as exc:
                report["stopped_reason"] = f"step_error:{step.tool}:{str(exc)[:120]}"
                return report

            if _is_gated_result(result):
                # The gate held it. Stop: the rest of the workflow assumed this
                # step happened, and it did not.
                report["gated_step"] = step.tool
                report["stopped_reason"] = f"awaiting_confirmation:{step.tool}"
                return report

            report["ran"].append({"tool": step.tool, "args": args})

        report["ok"] = True
        report["stopped_reason"] = "completed"
        if store is not None:
            try:
                store.record_use(skill.id)
            except Exception:
                pass
        return report
    except Exception as exc:
        report["stopped_reason"] = f"error:{str(exc)[:120]}"
        return report


__all__ = ["run_skill"]
