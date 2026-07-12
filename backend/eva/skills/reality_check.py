from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class RealityCheckResult:
    question: str
    answer: str
    evidence: tuple[str, ...]
    limitations: tuple[str, ...]
    recommended_next_step: str
    read_only: bool = True
    status: str = "evidence_needed"
    source: str = "local_status_surfaces"
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def build_reality_check(question: str = "are we actually done") -> RealityCheckResult:
    text = " ".join(str(question or "").lower().split())
    evidence = _common_evidence()
    limitations = _common_limitations()
    if "broken" in text or "failing" in text:
        return RealityCheckResult(
            question=question,
            answer="No failing verifier evidence is available in this read-only status view. That is not the same as proving nothing is broken.",
            evidence=evidence,
            limitations=limitations,
            recommended_next_step="Run the quick verifier profile, then inspect the first failing verifier if one appears.",
            status="unknown_without_fresh_verifier",
        )
    if "proof" in text or "done" in text or "actually" in text:
        return RealityCheckResult(
            question=question,
            answer="Do not claim done without fresh verifier output. Current local surfaces show the verifier commands and safety boundaries, but fresh proof requires running the verifier sweep.",
            evidence=evidence,
            limitations=limitations,
            recommended_next_step="Run `scripts/verify_eva_all.py --quick`; if it passes, run the full profile before checkpointing.",
            status="needs_fresh_verification",
        )
    return RealityCheckResult(
        question=question,
        answer="Eva has read-only evidence surfaces for current phase, workflow state, Control Center status, capabilities, and verifier commands.",
        evidence=evidence,
        limitations=limitations,
        recommended_next_step="Use `eva project proof` or run the quick verifier profile for fresh evidence.",
        status="status_summary",
    )


def format_reality_check(result: RealityCheckResult | None = None) -> str:
    result = result or build_reality_check()
    return "\n".join(
        [
            "Project reality check",
            "",
            f"Question: {result.question}",
            f"Answer: {result.answer}",
            f"Status: {result.status}",
            "",
            "Evidence:",
            *_bullets(result.evidence),
            "",
            "Limitations:",
            *_bullets(result.limitations),
            "",
            "Recommended next step:",
            result.recommended_next_step,
            "",
            "Execution: read-gatedity check. No task was executed.",
        ]
    )


def format_done_check() -> str:
    return format_reality_check(build_reality_check("are we actually done"))


def format_project_proof() -> str:
    result = build_reality_check("what proof do we have")
    return "\n".join(
        [
            "Project proof",
            "",
            "Evidence:",
            *_bullets(result.evidence),
            "",
            "What this proves:",
            "- Eva has local status and verifier surfaces wired for the current Phase 12 work.",
            "- FileAgent and Control Center can describe guarded workflows without executing risky actions.",
            "",
            "What this does not prove:",
            "- It does not prove the current tree is passing until the verifier commands are run now.",
            "- It does not unlock broad file edits, browser control, desktop control, MCP, terminal execution, package installs, or cloud calls.",
            "",
            "Next proof step:",
            result.recommended_next_step,
            "",
            "Execution: read-only proof summary. No task was executed.",
        ]
    )


def format_broken_status() -> str:
    result = build_reality_check("what is broken")
    return "\n".join(
        [
            "Broken-status check",
            "",
            result.answer,
            "",
            "Known locked areas:",
            "- broad file editing and source edits",
            "- browser and desktop control",
            "- MCP, Playwright, PyAutoGUI, terminal execution, package installs, and cloud calls",
            "- external sending/posting/submitting",
            "",
            "Fresh failure evidence:",
            "- No failing verifier evidence is available from this read-only command by itself.",
            "- Run the quick/full verifier profiles to identify actual current failures.",
            "",
            "Execution: read-only broken-status check. No task was executed.",
        ]
    )


def _common_evidence() -> tuple[str, ...]:
    from ..skills.workflow_state import summarize_fileagent_workflow_state

    workflow = summarize_fileagent_workflow_state()
    return (
        "Phase 12 status helper lists completed and locked areas.",
        "Control Center status summarizes authority, FileAgent, workflows, capabilities, and verifier commands.",
        f"Workflow state reports pending approvals {workflow.pending_approval_count}, approved records {workflow.approved_for_future_apply_count}, ambiguity {workflow.ambiguity_status}.",
        "Verifier commands are available through `scripts/verify_eva_all.py --quick` and `--full`.",
        "FileAgent remains the enforcement layer for approvals, sandbox, narrow real create, verification, and rollback.",
    )


def _common_limitations() -> tuple[str, ...]:
    return (
        "Fresh pass/fail status is unknown until a verifier profile is run in this workspace.",
        "Status commands summarize local metadata and do not execute verifiers.",
        "No browser/desktop/MCP/terminal/cloud execution is enabled by this workflow.",
        "No broad real file editing is enabled.",
    )


def _bullets(items: tuple[str, ...] | list[str]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- {item}" for item in items]
