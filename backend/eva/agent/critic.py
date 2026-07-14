"""The critic — an independent reviewer that gates "done" (Phase 41).

The planner declares a task finished; the executor runs the tools; but nothing
until now asked a separate question with separate logic: *did this actually
satisfy the goal?* A planner that hallucinates success, or stops after one step
of a three-step job, would still report "done". The critic closes that gap. It
does NOT trust the planner's verdict — it re-derives satisfaction from the real
evidence the run produced (the observations, and the Phase 38 verification
counts) against an explicit delegation contract.

A delegation contract is the goal plus its acceptance test: the success criteria
that must show up in the evidence, whether at least one action must be
independently *verified* (not merely self-reported), and how many times the
critic may hand work back for another attempt. With no contract the critic runs
in advisory mode — it always accepts, so existing single-shot behavior is
unchanged; a contract turns it into an enforcing gate.

Pure and deterministic (no LLM, no I/O) so it is CI-testable and never itself a
source of flakiness. Fail-safe: any internal error accepts rather than wedging
a task (the permission gate and verification layers remain the hard safety
boundaries; the critic is a quality gate on top).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ACCEPT = "accept"
REVISE = "revise"
REPORT_HONESTLY = "report_honestly"


@dataclass(frozen=True)
class DelegationContract:
    """The acceptance test for a delegated task: goal + success criteria."""

    goal: str = ""
    success_criteria: tuple[str, ...] = ()
    require_verified: bool = False
    max_revisions: int = 1

    @property
    def enforcing(self) -> bool:
        """Whether this contract actually gates completion (vs. advisory)."""
        return bool(self.success_criteria) or self.require_verified

    @classmethod
    def of(cls, value: Any) -> "DelegationContract | None":
        """Build a contract from a dict or an existing contract; None → None."""
        if value is None:
            return None
        if isinstance(value, DelegationContract):
            return value
        if isinstance(value, dict):
            try:
                criteria = value.get("success_criteria") or ()
                if isinstance(criteria, str):
                    criteria = [criteria]
                return cls(
                    goal=str(value.get("goal") or ""),
                    success_criteria=tuple(str(c) for c in criteria if str(c).strip()),
                    require_verified=bool(value.get("require_verified", False)),
                    max_revisions=int(value.get("max_revisions", 1)),
                )
            except (TypeError, ValueError):
                return None
        return None


@dataclass(frozen=True)
class CriticVerdict:
    """The critic's independent assessment of whether a task is truly done."""

    satisfied: bool
    confidence: float
    recommendation: str
    reasons: tuple[str, ...]
    unmet_criteria: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "satisfied": self.satisfied,
            "confidence": self.confidence,
            "recommendation": self.recommendation,
            "reasons": list(self.reasons),
            "unmet_criteria": list(self.unmet_criteria),
        }


def review_completion(
    *,
    goal: str,
    final_response: str,
    observations: list[str],
    verified_successes: int,
    failures: int,
    contract: DelegationContract | None,
    revisions_used: int = 0,
) -> CriticVerdict:
    """Independently judge whether a completed task satisfies its contract.

    Satisfaction is derived from the run's own evidence, not the planner's
    claim: every success criterion must appear in the observations/response,
    and — when the contract requires it — at least one action must have been
    independently verified (Phase 38). With no enforcing contract the critic
    accepts (advisory mode), preserving today's behavior.
    """
    try:
        if contract is None or not contract.enforcing:
            return CriticVerdict(
                satisfied=True,
                confidence=0.6,
                recommendation=ACCEPT,
                reasons=("No enforcing contract; critic is advisory and accepts.",),
                unmet_criteria=(),
            )

        evidence = " \n ".join([str(final_response or "")] + [str(o) for o in (observations or [])]).lower()
        unmet = tuple(c for c in contract.success_criteria if str(c).strip().lower() not in evidence)

        reasons: list[str] = []
        verified_ok = (not contract.require_verified) or verified_successes > 0
        if unmet:
            reasons.append(f"Unmet success criteria: {', '.join(unmet)}.")
        if not verified_ok:
            reasons.append("Contract requires an independently verified action, but none was verified.")
        if failures:
            reasons.append(f"{failures} step(s) failed during the task.")

        satisfied = not unmet and verified_ok
        if satisfied:
            return CriticVerdict(
                satisfied=True,
                confidence=0.9,
                recommendation=ACCEPT,
                reasons=("All contract success criteria are met in the evidence.",),
                unmet_criteria=(),
            )

        # Not satisfied: send back for another attempt if the revision budget
        # allows, otherwise require an honest report rather than a false "done".
        can_revise = revisions_used < max(0, contract.max_revisions)
        return CriticVerdict(
            satisfied=False,
            confidence=0.8,
            recommendation=REVISE if can_revise else REPORT_HONESTLY,
            reasons=tuple(reasons) or ("Contract not satisfied.",),
            unmet_criteria=unmet,
        )
    except Exception:
        # Fail open on the QUALITY gate only — safety gates are elsewhere.
        return CriticVerdict(
            satisfied=True,
            confidence=0.3,
            recommendation=ACCEPT,
            reasons=("Critic review errored; accepting (safety gates remain in force).",),
            unmet_criteria=(),
        )


def honest_caveat(verdict: CriticVerdict) -> str:
    """A truthful completion caveat when the critic could not confirm success."""
    if verdict.satisfied:
        return ""
    unmet = ", ".join(verdict.unmet_criteria) if verdict.unmet_criteria else "the goal's success criteria"
    return f" (Note: I could not confirm {unmet}; treating this as attempted, not verified complete.)"
