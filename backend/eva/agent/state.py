from __future__ import annotations

from dataclasses import dataclass, field

from .planner import PlannedToolCall
from .policies import tool_signature


@dataclass
class AgentRunState:
    tool_calls: int = 0
    web_searches: int = 0
    screen_captures: int = 0
    invalid_json_errors: int = 0
    signatures: list[str] = field(default_factory=list)
    # Phase 39 reliability tracking.
    consecutive_failures: int = 0
    steps_since_progress: int = 0
    verified_successes: int = 0
    successes: int = 0
    failures: int = 0
    last_error: str | None = None
    # Phase 40 taint-tracking: whether injected/untrusted content has entered
    # the task context (so a later privileged action can be escalated, never
    # auto-authorized on the untrusted content's say-so).
    injection_flagged: bool = False
    tainted_sources: list[str] = field(default_factory=list)
    # Phase 41: how many times the critic has sent the task back for revision.
    critic_revisions: int = 0
    # Phase 42: confidence of the most recent reflection (for confidence-aware
    # escalation of the next action).
    last_confidence: float | None = None
    # Phase 119 adaptive step budget: transient, loop-local bookkeeping (the
    # durable, reportable budget facts -- base/ceiling/extensions -- live on
    # `AgentTask` instead, since that is what `_return_task` already threads
    # everywhere a result is built). `last_step_progress` is what the last
    # EXECUTED step (real or a Phase 117 resumed replay) actually achieved,
    # read by the loop only at the instant it reaches its current budget, to
    # decide whether to grant one more step. `consecutive_no_progress` is a
    # separate streak, counting only executed steps (never a planner-JSON
    # retry or a critic-revise iteration, which have their own bounded
    # retries elsewhere) -- two in a row stops the loop early rather than
    # waiting for the budget to run out. Both survive a Phase 117 pause/
    # resume unchanged, because resume reuses this same state object by
    # reference (`PausedTask.env`), never rebuilding it.
    last_step_progress: bool = False
    consecutive_no_progress: int = 0

    def record_critic_revision(self) -> None:
        self.critic_revisions += 1

    def record_step_progress(self, progress: bool) -> None:
        """Called once per EXECUTED step (real or resumed), never for a
        planner-error retry or a critic-revise iteration -- those instead set
        ``last_step_progress`` directly, since they are not the executed-step
        streak this counts."""
        self.last_step_progress = progress
        if progress:
            self.consecutive_no_progress = 0
        else:
            self.consecutive_no_progress += 1

    def no_progress_stalled(self, limit: int = 2) -> bool:
        return self.consecutive_no_progress >= limit

    def repeated_without_progress(self, call: PlannedToolCall) -> bool:
        signature = tool_signature(call)
        return self.signatures.count(signature) >= 2

    def record_tool(self, call: PlannedToolCall) -> None:
        self.tool_calls += 1
        if call.tool in {"web_search", "research_web", "browser_search"}:
            self.web_searches += 1
        if call.tool in {"capture_screen", "analyze_screen"} or (call.tool == "desktop_observe" and bool(call.args.get("include_screen"))):
            self.screen_captures += 1
        self.signatures.append(tool_signature(call))

    def record_invalid_json(self) -> None:
        self.invalid_json_errors += 1

    def record_success(self, verified: bool = False) -> None:
        """A step succeeded: the failure streak and stall counter reset. A step
        whose post-condition was *independently* verified (Phase 38) counts as
        real, proven progress."""
        self.successes += 1
        self.consecutive_failures = 0
        self.steps_since_progress = 0
        if verified:
            self.verified_successes += 1

    def record_failure(self, error: str | None = None) -> None:
        """A step failed: extend the consecutive-failure streak so the loop can
        try to recover a bounded number of times before stopping honestly."""
        self.failures += 1
        self.consecutive_failures += 1
        self.steps_since_progress += 1
        self.last_error = error

    def record_injection(self, source_type: str) -> None:
        """Mark that injected/untrusted content has entered the task context."""
        self.injection_flagged = True
        if source_type and source_type not in self.tainted_sources:
            self.tainted_sources.append(source_type)

    def failure_budget_exceeded(self, limit: int) -> bool:
        return self.consecutive_failures >= limit

    def stalled(self, limit: int) -> bool:
        return self.steps_since_progress >= limit
