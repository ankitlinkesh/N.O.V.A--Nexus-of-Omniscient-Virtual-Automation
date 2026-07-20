"""Run a sub-task under a role (Phase 73).

Phase 72 built the containment boundary and deliberately left it inert: there
was no way to open a role scope, so GREEN/ORANGE/RED never fired in production.
This is the caller that makes it live -- and it is the ONLY thing that should
open a scope, so the boundary has exactly one entrance to audit.

WHAT DELEGATION BUYS, and what it does not:

  * CONTEXT ISOLATION -- the sub-task gets a fresh history rather than the
    parent's accumulated thread. This is the main reason to delegate at all.
  * SPECIALIZATION -- a role-scoped goal, and a tool surface narrowed to what
    that role may touch.
  * FAULT ISOLATION -- a raising sub-task becomes a typed failure here rather
    than unwinding into the parent.
  * NOT PARALLELISM. Sub-tasks run sequentially and on purpose: every agent
    draws on the same rationed LLM budget (llm/rate_limiter.py -- 20/min,
    300/day), so concurrent sub-tasks split one quota rather than multiplying
    throughput, and desktop work cannot overlap at all because there is one
    cursor and one foreground window. See the Phase 72 README row.

THE TRUST BOUNDARY, which is the whole reason this file is careful:

A sub-task's return value is DATA, never instructions. A research role reads
untrusted web content; if the parent treated the child's summary as a plan to
carry out, delegation would be a prompt-injection channel straight into an
executor holding real tools. So `DelegatedResult.summary` is explicitly marked
untrusted, and nothing here feeds a child's output back into a planner. The
parent reasons ABOUT the result; it does not execute it.

For the same reason `run_delegated` is not a planner tool. It is reachable from
the typed console only -- the boundary this project already draws for rule
creation (Phase 54) and form filling (Phase 58) -- so untrusted content cannot
choose to spawn a sub-task, pick its role, or write its goal.

NO SECOND EXECUTOR. The sub-task runs through `agent/runner.run_agentic_task`,
the same live executor everything else uses, wrapped in a role scope. Phase 72
found that `agents/` (plural) had built a parallel framework whose `execute()`
merely refused; re-creating that here would repeat exactly the duplication
Phases 69, 70 and 72 spent their effort removing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .role_context import denials, role_scope
from .role_policy import known_roles


@dataclass
class DelegatedResult:
    """The outcome of a sub-task. `summary` is UNTRUSTED CONTENT."""

    role: str
    goal: str
    ok: bool
    summary: str
    refusals: tuple[dict[str, str], ...] = ()
    error: str | None = None
    raw: dict[str, Any] | None = field(default=None, repr=False)
    # A standing reminder at the point of use: whatever is in `summary` came
    # from a sub-task that may have read hostile content.
    untrusted: bool = True

    @property
    def injection_suspected(self) -> bool:
        """True when the sub-task reached for something its role forbids.

        Not proof of an attack -- a model can simply pick a wrong tool -- but a
        research role reaching for `screen.click` is the shape an injection
        takes, and it is worth showing the user rather than swallowing.
        """
        return bool(self.refusals)

    def as_text(self) -> str:
        lines = [f"Delegated to `{self.role}`", "", f"Goal: {self.goal}", ""]
        if self.error:
            lines += ["Result: the sub-task failed.", f"Reason: {self.error}"]
        else:
            lines += ["Result:", self.summary or "(no summary returned)"]
        if self.refusals:
            lines += [
                "",
                f"Blocked {len(self.refusals)} action(s) this role may not perform:",
            ]
            lines += [f"- {item['role']} attempted {item['tool']}" for item in self.refusals]
            lines += [
                "",
                "If you did not ask for these, treat it as a signal: content this "
                "sub-task read may have tried to make it act.",
            ]
        lines += ["", "This summary is untrusted output from a sub-task, not an instruction."]
        return "\n".join(lines)


def _failure(role: str, goal: str, error: str) -> DelegatedResult:
    return DelegatedResult(role=role, goal=goal, ok=False, summary="", error=error, refusals=denials())


async def run_delegated(role: str, goal: str, context: dict[str, Any] | None = None) -> DelegatedResult:
    """Run `goal` as a sub-task confined to `role`.

    Fails closed on an unknown role: an unrecognized name would otherwise reach
    `role_scope` and, while `effective_tier` would deny every tool anyway, a
    silently-accepted bad role name is a confusing way to discover a typo.
    """
    role = str(role or "").strip()
    goal = str(goal or "").strip()
    if role not in known_roles():
        return DelegatedResult(
            role=role,
            goal=goal,
            ok=False,
            summary="",
            error=f"Unknown role `{role}`. Known roles: {', '.join(known_roles())}.",
        )
    if not goal:
        return DelegatedResult(role=role, goal=goal, ok=False, summary="", error="No goal was given to delegate.")

    # Context isolation: inherit the machinery (registry, memory, session) but
    # NOT the parent's conversation history. Starting from the parent's thread
    # would defeat the main reason to delegate, and would also hand the
    # sub-task context it has no need to see.
    parent = dict(context or {})
    child_context = {key: value for key, value in parent.items() if key != "history"}
    child_context["history"] = []

    from ..agent.runner import run_agentic_task

    with role_scope(role):
        try:
            raw = await run_agentic_task(goal, child_context)
        except Exception as exc:  # fault isolation -- the parent survives
            return _failure(role, goal, f"{type(exc).__name__}: {exc}")
        # Read refusals BEFORE leaving the scope; the collector is scoped.
        recorded = denials()

    summary = ""
    ok = False
    if isinstance(raw, dict):
        # `final_response` is the key run_agentic_task actually returns. The
        # others are accepted defensively, but the live run is what settled it:
        # guessing plausible key names produced an empty summary on a run that
        # had reported ok=True, which is the Phase 70 shape -- reading fewer
        # names than the source emits looks correct while carrying nothing.
        summary = str(
            raw.get("final_response") or raw.get("message") or raw.get("summary") or raw.get("final") or ""
        )
        # Trust the runner's own success signal rather than inferring success
        # from a non-empty string -- Phase 69 fixed exactly that mistake in
        # runtime/nodes.py, where a populated summary was read as success even
        # for a failed run.
        ok = bool(raw.get("ok"))

    return DelegatedResult(
        role=role,
        goal=goal,
        ok=ok,
        summary=summary,
        refusals=recorded,
        raw=raw if isinstance(raw, dict) else None,
    )
