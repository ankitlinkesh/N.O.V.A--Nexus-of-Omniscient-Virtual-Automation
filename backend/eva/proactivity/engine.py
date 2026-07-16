"""The proactivity engine — Eva acting when nobody asked (Phase 46).

Every safety mechanism built so far assumed a human at the keyboard: the gate
holds a privileged action and *someone* answers the confirmation. Proactivity
breaks that assumption — a rule can fire at 3am with nobody watching. So this
engine is built around one rule, the exact parallel of the Phase 40 moat
("untrusted content PROPOSES, never AUTHORIZES"):

    **A trigger PROPOSES work. It never AUTHORIZES it.**

Concretely, when a rule fires this engine does exactly two things:

  1. **Enqueues** the rule's request onto the Phase 45 durable queue — which
     persists a *request*, never an approval.
  2. **Records a notification** for the user to read.

It never executes a tool, never calls the runner, never touches the gate. Work
only ever runs later, through the ordinary gate-governed path, where a
privileged action still waits in the confirmation ledger for a human. An
unattended trigger therefore cannot perform a destructive or external action on
its own — the worst a compromised or buggy rule can do is put a *suggestion* in
a queue.

Runaway protection is layered on top, because a proactive loop that misfires is
a denial-of-service on the user's attention:

  * a per-rule ``cooldown_seconds`` floor between fires;
  * a per-rule ``max_fires_per_day`` budget (clamped by the store's ceiling);
  * a per-tick global cap on how many proposals a single tick may make.

Default-off (``EVA_PROACTIVITY_ENABLED``) and fail-safe: one broken rule can
never stop the others or raise into the caller.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import ProactiveRule
from .store import ProactivityStore
from .triggers import parse_iso, should_fire

# No single tick may propose more than this, whatever the rules say.
MAX_PROPOSALS_PER_TICK = 10


class ProactivityEngine:
    """Evaluates standing rules and proposes work. Executes nothing, ever."""

    def __init__(self, store: ProactivityStore, queue: Any | None = None) -> None:
        self.store = store
        # The Phase 45 DurableTaskQueue. Without one the engine still evaluates
        # and notifies, but has nowhere to propose work to.
        self.queue = queue

    def _within_cooldown(self, rule: ProactiveRule, now: datetime) -> bool:
        if rule.cooldown_seconds <= 0:
            return False
        last = parse_iso(rule.last_fired_at)
        if last is None:
            return False
        return (now - last).total_seconds() < rule.cooldown_seconds

    def _over_daily_budget(self, rule: ProactiveRule, day: str) -> bool:
        if rule.fires_day != day:
            return False  # counter belongs to another day; today is fresh
        return rule.fires_today >= rule.max_fires_per_day

    def tick(self, now: datetime | None = None) -> dict[str, Any]:
        """Evaluate every enabled rule once and propose work for those that fire.

        Returns a summary: what was proposed, what was suppressed and why. Pure
        with respect to execution — the only side effects are an enqueue, a
        notification, and the rule's own bookkeeping.
        """
        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        day = moment.date().isoformat()

        proposed: list[dict[str, str]] = []
        suppressed: list[dict[str, str]] = []
        evaluated = 0

        for rule in self.store.list_rules(enabled_only=True):
            if len(proposed) >= MAX_PROPOSALS_PER_TICK:
                suppressed.append({"rule": rule.name, "reason": "tick_proposal_cap"})
                continue
            evaluated += 1
            try:
                fires, new_state = should_fire(rule, moment)
            except Exception:
                continue
            if not fires:
                # A trigger may update bookkeeping without firing (e.g. a file
                # watcher taking its first baseline) — persist that.
                if new_state != (rule.state or {}):
                    self.store.update_state(rule.id, new_state)
                continue
            if self._within_cooldown(rule, moment):
                suppressed.append({"rule": rule.name, "reason": "cooldown"})
                continue
            if self._over_daily_budget(rule, day):
                suppressed.append({"rule": rule.name, "reason": "daily_budget"})
                continue

            # FIRE: propose only — enqueue + notify. Never execute.
            queued_id = ""
            if self.queue is not None:
                try:
                    task = self.queue.enqueue(rule.request, source=f"proactive:{rule.id[:8]}")
                    queued_id = task.id if task is not None else ""
                except Exception:
                    queued_id = ""
            message = f"{rule.name}: queued '{rule.request}' for your approval."
            try:
                self.store.add_notification(rule.id, message)
            except Exception:
                pass
            self.store.record_fire(rule.id, fired_at=moment.isoformat(), state=new_state, day=day)
            proposed.append({"rule": rule.name, "rule_id": rule.id, "request": rule.request, "task_id": queued_id})

        return {
            "at": moment.isoformat(),
            "evaluated": evaluated,
            "proposed": proposed,
            "suppressed": suppressed,
            "note": "Proactive rules only propose work; every task still runs through the permission gate.",
        }


__all__ = ["ProactivityEngine", "MAX_PROPOSALS_PER_TICK"]
