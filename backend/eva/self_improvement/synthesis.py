"""Skill synthesis — Eva learns from what actually worked (Phase 47).

This is the capstone: Eva improving herself. It is also the single most
dangerous thing in the project, so the shape of it matters more than the
cleverness.

**What we deliberately did NOT build.** The obvious reading of "tool synthesis"
is: Eva writes Python, we sandbox it, we register it as a tool. Reject that. A
tool is a callable behind the permission gate; if Eva can author the callable,
she has arbitrary code execution, and every other defense becomes decoration —
the Phase 40 taint moat, the Phase 42 trust policies, the Phase 46
propose-never-authorize rule are all bypassed by one synthesized tool that
shells out. Sandboxing generated code is a containment problem nobody wins by
default, and it would be the only place in Eva where safety rests on a sandbox
rather than on the gate.

**What we built instead: composition.** A learned skill is an ordered list of
calls to tools *that already exist in the registry*. Learning a skill therefore
adds convenience, never capability:

  * Every step names an existing tool. :func:`validate_steps` rejects any step
    naming a tool the live registry does not expose, so Eva cannot invent
    ``run_shell`` by writing it down.
  * Executing a skill calls ``ToolRegistry.run`` per step, so the gate
    classifies each one from its *real* ToolSpec. A confirm-class step inside a
    skill is still confirm-class; a skill cannot relabel it.
  * A skill can express nothing a user could not already have asked for
    directly, one step at a time. The privilege ceiling is unchanged, by
    construction rather than by inspection.

**The learning loop.** Phase 36 gave Eva a flight recorder; this reads it. A
sequence of tool calls that appears in several traces is a workflow worth
naming. That is the whole insight: the evidence for "this is a real skill" is
that it already happened, repeatedly, and worked.

Proposals are INERT — :mod:`eva.self_improvement.store` keeps them ``proposed``
until a human approves. Nothing here executes anything.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from .models import MAX_SKILL_STEPS, SkillStep

# A sequence must be at least this long to be worth naming, and must have been
# seen at least this many times to count as a habit rather than a coincidence.
MIN_SEQUENCE_LEN = 2
MIN_OBSERVATIONS = 2

# A workflow worth naming has to *go somewhere*. The same tool polled several
# times in a row (status, status, status...) is noise, not a skill — real traces
# are full of it. Require genuine variety.
MIN_DISTINCT_TOOLS = 2

# Tools that must never be baked into a learned skill, regardless of how often
# they appear. These are one-shot, explicitly-requested, or privacy-sensitive
# actions whose whole point is that a human asks for them *each time*; silently
# folding them into a reusable macro would launder that intent.
NEVER_LEARN_TOOLS = frozenset(
    {
        "screen.observe",
        "analyze_screen",
        "capture_screen",
        "file.delete",
        "file_delete",
        "power_action",
        "shutdown",
        "restart",
    }
)


def _tool_calls_in_trace(trace: dict[str, Any]) -> list[str]:
    """The ordered tool names of the successful tool calls in one trace."""
    names: list[str] = []
    for event in trace.get("events") or []:
        if event.get("type") != "tool_call":
            continue
        payload = event.get("payload") or {}
        name = str(payload.get("tool_name") or "").strip()
        if not name:
            continue
        # A step is only evidence if it actually ran. A gated call that was held
        # for confirmation never executed, so it is not proof of a workflow.
        summary = str(payload.get("result_summary") or "").lower()
        if "requires_confirmation" in summary or "error" in summary:
            continue
        names.append(name)
    return names


def _windows(names: list[str], size: int) -> Iterable[tuple[str, ...]]:
    for i in range(len(names) - size + 1):
        yield tuple(names[i : i + size])


def validate_steps(steps: Iterable[SkillStep], registry: Any) -> tuple[bool, str]:
    """The load-bearing check: every step must name a tool that already exists.

    This is what stops a "synthesized" skill from being a privilege escalation.
    Eva cannot conjure a capability by naming it — if the live registry does not
    expose the tool, the skill is rejected outright. Fail-closed: if the registry
    cannot be consulted, nothing validates.
    """
    items = list(steps)
    if not items:
        return False, "a skill must have at least one step"
    if len(items) > MAX_SKILL_STEPS:
        return False, f"a skill may have at most {MAX_SKILL_STEPS} steps"
    try:
        for step in items:
            name = str(getattr(step, "tool", "") or "").strip()
            if not name:
                return False, "a step must name a tool"
            if name in NEVER_LEARN_TOOLS:
                return False, f"tool '{name}' may never be baked into a learned skill"
            if registry is None or registry.get(name) is None:
                return False, f"unknown tool '{name}' — a skill may only compose tools that already exist"
    except Exception as exc:  # registry unavailable/broken
        return False, f"could not validate steps against the registry: {str(exc)[:120]}"
    return True, "all steps name existing registry tools"


def propose_skills_from_traces(traces: list[dict[str, Any]], registry: Any) -> list[dict[str, Any]]:
    """Mine traces for repeated, already-successful tool sequences worth naming.

    Returns candidate dicts ``{name, description, steps, observed_count,
    source_trace_id}``. Pure: proposes only, persists nothing, executes nothing.
    Every candidate is validated against the live registry first.
    """
    try:
        sequences: Counter = Counter()
        first_seen: dict[tuple[str, ...], str] = {}

        for trace in traces or []:
            names = _tool_calls_in_trace(trace)
            if len(names) < MIN_SEQUENCE_LEN:
                continue
            trace_id = str(trace.get("trace_id") or "")
            # Count each distinct sequence once per trace, so a loop inside a
            # single trace can't masquerade as a repeated habit.
            seen_here: set[tuple[str, ...]] = set()
            for size in range(MIN_SEQUENCE_LEN, min(len(names), MAX_SKILL_STEPS) + 1):
                for window in _windows(names, size):
                    if window in seen_here:
                        continue
                    seen_here.add(window)
                    sequences[window] += 1
                    first_seen.setdefault(window, trace_id)

        candidates: list[dict[str, Any]] = []
        for window, count in sequences.most_common():
            if count < MIN_OBSERVATIONS:
                continue
            # Reject degenerate "habits" like status -> status -> status: a
            # repeated poll of one tool is noise, not a workflow worth naming.
            if len(set(window)) < MIN_DISTINCT_TOOLS:
                continue
            steps = [SkillStep(tool=name, args={}) for name in window]
            ok, _reason = validate_steps(steps, registry)
            if not ok:
                continue
            candidates.append(
                {
                    "name": _skill_name(window),
                    "description": f"Learned workflow seen in {count} traces: {' -> '.join(window)}.",
                    "steps": steps,
                    "observed_count": count,
                    "source_trace_id": first_seen.get(window, ""),
                }
            )

        # Prefer the longest, most-observed workflows, and drop any candidate
        # that is merely a sub-sequence of one we already took — the longer
        # workflow is the better description of the habit.
        candidates.sort(key=lambda c: (-len(c["steps"]), -c["observed_count"]))
        kept: list[dict[str, Any]] = []
        for candidate in candidates:
            tools = tuple(step.tool for step in candidate["steps"])
            if any(_is_subsequence(tools, tuple(s.tool for s in k["steps"])) for k in kept):
                continue
            kept.append(candidate)
        return kept
    except Exception:
        return []


def _skill_name(window: tuple[str, ...]) -> str:
    """A readable name for a learned workflow, never truncated mid-token."""
    full = "_then_".join(window)
    if len(full) <= 80:
        return full
    # Too long to spell out: name it by where it starts and ends.
    return f"{window[0]}_to_{window[-1]}_{len(window)}steps"[:80]


def _is_subsequence(needle: tuple[str, ...], haystack: tuple[str, ...]) -> bool:
    if len(needle) >= len(haystack):
        return False
    return any(haystack[i : i + len(needle)] == needle for i in range(len(haystack) - len(needle) + 1))


__all__ = [
    "propose_skills_from_traces",
    "validate_steps",
    "NEVER_LEARN_TOOLS",
    "MIN_OBSERVATIONS",
    "MIN_SEQUENCE_LEN",
]
