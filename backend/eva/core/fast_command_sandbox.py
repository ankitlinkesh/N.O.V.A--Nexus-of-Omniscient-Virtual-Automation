"""Typed-console entry for NOVA's sandbox terminal (Phase 130).

    box: ls -la
    sandbox: python3 -c "print(2+2)"

Runs the text after the prefix as a Linux command in NOVA's own isolated WSL box
(never on the Windows host). It goes through ``tools.run("sandbox_run")`` rather than
calling the runner directly, so the registry's role policy and audit trail apply to
the console path too.

THE PREFIX IS ANCHORED AND WHOLE-WORD: ``box`` or ``sandbox`` at the very start of the
message, then a colon. "send the box to mom", "inbox: 3 new" and "the sandbox: is it
safe?" (not at the start) never match; the colon is what keeps ordinary prose out.
Natural phrasings ("in your terminal, make a folder called test") are NOT handled here:
they reach the agent path, where the planner chooses ``sandbox_run``.
"""

from __future__ import annotations

import re
from typing import Any

from .fast_command_instant import _run

# Phase 131: only spaces/tabs between the word and the colon ("box\n: x" was a
# match). A typed message that STARTS "Box: ..." still runs as a command, by
# design: it is the user's own text and the box is isolated.
_PREFIX = re.compile(r"^\s*(?:box|sandbox)[ \t]*:\s*(?P<command>.*)$", re.I | re.S)

_USAGE = (
    "Usage: box: <linux command>\n\n"
    "It runs in my own sandbox terminal, not on your PC. I can only see the files in /mnt/share "
    "(your nova-share folder on D:), and my workspace is /home/nova/workspace."
)


def match_sandbox_command(message: str) -> str | None:
    """Pure: the command text after an anchored ``box:``/``sandbox:`` prefix, '' for a bare
    prefix, or None when the message is not a sandbox command."""
    m = _PREFIX.match(str(message or ""))
    if not m:
        return None
    return m.group("command").strip()


def maybe_handle_sandbox_command(message: str, tools: Any, session_context: dict | None = None) -> tuple[str, str] | None:
    command = match_sandbox_command(message)
    if command is None:
        return None
    if not command:
        return _USAGE, "fast-command"
    result, early = _run(tools, "sandbox_run", command=command)
    if early:
        return early, "fast-command"
    if isinstance(result, dict):
        text = result.get("text")
        if isinstance(text, str) and text.strip():
            return text, "fast-command"
        return str(result.get("error") or "My sandbox returned nothing."), "fast-command"
    return str(result), "fast-command"
