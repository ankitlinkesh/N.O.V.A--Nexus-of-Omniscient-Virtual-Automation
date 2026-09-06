"""Typed-console entry for the deep reasoning model (Phase 106).

    think: why does this deadlock only under load?
    think status

WHY THIS EXISTS AT ALL: Phase 104 fixed the request timeout that made
`deep_reasoning` unusable -- every provider call had a hardcoded 12s budget and
`deepseek-v4-pro` needs a measured 164 seconds -- and then a grep for callers
found there were none. The role was configured, probed, routable and requested
by nothing, which is the reachable-by-grep trap this project has now hit three
times: `doctor.live_probe` (Phase 92), `listen_once` (Phase 61), `app.focus`
(Phase 64). A capability nothing invokes is not a capability.

WHY CONSOLE-ONLY, AND NOT A PLANNER TOOL:

The reason is latency, not authority -- which makes it a different argument from
the `gui:`/`delegate`/`$ ` boundary, and worth stating rather than borrowing.
This call blocks for two to four minutes. A planner that could reach it would
spend an errand's entire wall-clock budget on one step, and untrusted content
that steers a planner toward it becomes a cheap denial-of-service: no
authorization is gained, but the agent stops responding. A person typing
`think:` has decided to wait.

It carries NO tool authority of its own. It cannot act -- it answers. So there
is no gate here beyond the console boundary itself, because there is nothing to
gate: the model sees the question and returns text.

WHAT IT TELLS THE USER BEFORE IT BLOCKS: the measured duration. The first real
use of a three-minute call is indistinguishable from a hang unless the reply
said so up front, and this project has spent two phases on failures that looked
like something they were not.
"""

from __future__ import annotations

import time
from typing import Any

from ..mcp.runner import run_async

# Measured 2026-09-06 against the live endpoint: deepseek-v4-pro answered a
# one-line prompt in 164.3 seconds. A real question is longer, so this is a
# floor rather than an estimate, and it is stated as one.
_MEASURED_FLOOR_SECONDS = 164

# The deep model is for hard questions, not long ones. A generous cap costs real
# minutes per extra token on a model this slow.
_MAX_TOKENS = 1600


def _status_report() -> str:
    from ..llm.providers._openai_compatible import DEEP_REQUEST_TIMEOUT, timeout_for_purpose
    from ..llm.providers.nvidia_nim import nvidia_nim_role_models

    model = nvidia_nim_role_models().get("deep_reasoning") or "(unset)"
    return "\n".join(
        [
            "Deep reasoning status",
            "",
            f"Model   : {model}",
            f"Budget  : {timeout_for_purpose('deep_reasoning'):g}s per request "
            f"(deep purposes get {DEEP_REQUEST_TIMEOUT:g}s; everything else keeps the short default)",
            f"Measured: {_MEASURED_FLOOR_SECONDS}s for a one-line prompt, so expect minutes, not seconds.",
            "",
            "Usage: think: <a question worth waiting for>",
            "It answers; it cannot act. Console-only, because a planner should not be able to",
            "spend an entire errand's wall clock on one step.",
        ]
    )


def _run_deep(question: str) -> str:
    from ..core.config import ModelSettings
    from ..llm.router import complete_with_fallback

    messages = [
        {
            "role": "system",
            "content": (
                "You are answering a question the user chose to wait several minutes for. "
                "Reason it through properly and give the reasoning, not just a verdict. "
                "If the question cannot be answered from what you were given, say what is missing."
            ),
        },
        {"role": "user", "content": question},
    ]
    started = time.time()
    try:
        routed = run_async(
            complete_with_fallback(
                messages,
                ModelSettings(),
                purpose="deep_reasoning",
                temperature=0.2,
                max_tokens=_MAX_TOKENS,
            )
        )
    except Exception as exc:
        return f"The deep model could not be reached: {type(exc).__name__}: {exc}"

    elapsed = time.time() - started
    response = getattr(routed, "response", None) or routed
    text = str(getattr(response, "text", "") or "").strip()
    model = str(getattr(response, "model", "") or "unknown")
    if not getattr(response, "ok", False) or not text:
        # Name the reason. Phase 104 exists because a failure here used to arrive
        # as the empty string, so reporting "it didn't work" without the reason
        # would put back exactly what that phase removed.
        reason = str(getattr(response, "error", "") or "").strip() or "no reason reported"
        return f"The deep model did not answer after {elapsed:.0f}s ({model}): {reason}"
    return f"{text}\n\n({model}, {elapsed:.0f}s)"


def maybe_handle_think_command(
    normalized: str,
    original: str,
    tools: Any = None,
    session_context: Any = None,
    memory: Any = None,
    session_id: str | None = None,
) -> tuple[str, str] | None:
    """`think status` and `think: <question>`; None for anything else.

    The colon is deliberate, the way `gui:` and `$ ` are: "think about it" is
    ordinary prose a person might type, and a bare `think ` prefix would start
    swallowing requests meant for the assistant. A refactor that STARTS handling
    a phrase is as much a regression as one that stops.
    """
    if normalized in {"think status", "deep status", "deep reasoning status"}:
        return _status_report(), "fast-command"

    # Matched on the NORMALIZED text and sliced from the ORIGINAL. `think:` is
    # the first word of a sentence, so a person capitalises it -- "Think: why
    # does..." is the natural way to type this, and matching the raw text would
    # have silently handed it to the LLM instead. The question's own casing has
    # to survive, though, so the prefix is only located case-insensitively; the
    # remainder is taken from what was actually typed.
    question = None
    for prefix in ("think: ", "think : ", "deep: ", "deep : ", "think:", "deep:"):
        if normalized.startswith(prefix):
            question = original[len(prefix) :].strip(" :")
            break
    if question is None:
        return None
    question = question.strip()
    if not question:
        return (
            "Ask me something worth waiting for, e.g. `think: why would this deadlock only under load?`. "
            "Type `think status` to see the model and the time budget.",
            "fast-command",
        )
    return _run_deep(question), "fast-command"
