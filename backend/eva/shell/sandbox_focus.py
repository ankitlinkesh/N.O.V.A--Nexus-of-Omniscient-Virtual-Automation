"""Phase 133: "use your terminal to check disk space" must answer about NOVA's box.

Live, that request reached the agent loop and the planner called `system_status`,
which describes the USER'S PC (C:/D: drives). NOVA's terminal is `sandbox_run`.
Phase 130 added planner-prompt rules saying so; the model ignored them in three
live runs. A rule is not an enforcement.

So, like the GUI scope (screen/gui_scope.py): when the user's own goal says
"your terminal/sandbox/box", a scope is open for that task and

  * the host-status tools are REMOVED from the planner's view
    (`ToolRegistry.planner_specs`), and
  * if the planner emits one anyway, the runner refuses it and tells the planner
    to use `sandbox_run` (`runner._run_step`).

Only these two status tools are hidden; files, web and everything else stay.
The scope only narrows -- it grants nothing and never touches the gate.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

# Tools whose answers describe the user's PC, not NOVA's sandbox.
SANDBOX_FOCUS_HIDDEN: frozenset[str] = frozenset({"system_status", "status"})

_FOCUS: ContextVar[bool] = ContextVar("nova_sandbox_focus", default=False)


def wants_sandbox_focus(goal: str) -> bool:
    """True when the goal asks to use NOVA's own terminal/sandbox/box."""
    from ..agent.policies import is_sandbox_request

    text = " ".join(str(goal or "").lower().strip().split())
    return bool(text) and is_sandbox_request(text)


def sandbox_focus_open() -> bool:
    return _FOCUS.get()


@contextmanager
def open_sandbox_focus() -> Iterator[None]:
    token = _FOCUS.set(True)
    try:
        yield
    finally:
        _FOCUS.reset(token)


def refusal_message(tool: str) -> str:
    return (
        f"`{tool}` describes the user's PC, not your sandbox, and this task asked about your own "
        f"terminal. Use `sandbox_run` instead, e.g. `df -h` for disk, `free -m` for memory, "
        f"`uname -a` or `cat /etc/os-release` for the OS."
    )
