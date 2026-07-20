"""The currently-active delegated role (Phase 72).

WHY THIS IS AMBIENT AND NOT AN ARGUMENT -- the load-bearing design decision:

`registry.run` strips `confirmed`, `_approved` and `content_args` from caller
kwargs, because each is a signal that REDUCES friction and so must never come
from the caller. The active role is the same kind of signal in reverse: it
constrains what may be called, so a caller able to CHOOSE its own role could
simply claim whichever role unlocks the tool it wants. Injected page content
asking to "switch to the desktop role" would then be self-authorization.

So the role is ambient state, set only by the delegation boundary in source
(see `role_scope`), never read from tool arguments. `registry.run` additionally
strips any caller-supplied `role`/`_role`/`agent_role` kwarg for the same reason
it strips `confirmed`.

NO ACTIVE ROLE MEANS NO ROLE RESTRICTION. Ordinary typed-console and planner
calls run with no role set and are completely unaffected by Phase 72 -- this
module adds a constraint inside delegated sub-tasks, it does not re-gate the
existing product. Untrusted content cannot clear the role either: it is set and
reset by `role_scope` around the sub-task, not by anything the model emits.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

# A STACK, not a single role. Delegation must only ever NARROW capability:
# if a research sub-task could open a `desktop` scope inside its own, it would
# gain exactly the screen access its role exists to deny. So every enclosing
# role stays in force and the most restrictive tier wins (see
# role_policy.effective_tier). This is the same shape as Phase 55's
# only-ever-escalates rule -- a nested scope can subtract capability, never add
# it -- and it is why nesting is an intersection rather than a replacement.
_active_roles: ContextVar[tuple[str, ...]] = ContextVar("eva_active_agent_roles", default=())

# Caller-supplied spellings that must never be honoured as a role declaration.
ROLE_KWARG_NAMES = frozenset({"role", "_role", "agent_role"})


def active_roles() -> tuple[str, ...]:
    """Every role currently in force, outermost first. Empty at top level."""
    return _active_roles.get()


def active_role() -> str | None:
    """The innermost active role, for reporting. Authorization must use
    `active_roles()` -- reading only the innermost role is precisely the
    containment escape this stack exists to prevent."""
    roles = _active_roles.get()
    return roles[-1] if roles else None


def set_active_roles(roles: tuple[str, ...]) -> Token:
    return _active_roles.set(roles)


def reset_active_roles(token: Token) -> None:
    _active_roles.reset(token)


# Refusals recorded during the current delegated sub-task. A RED refusal is
# evidence -- a research role reaching for screen.click means content it read
# tried to reach an actuator -- and evidence that dies inside the sub-task is
# wasted, so the scope collects it for the caller to surface. A shared mutable
# list (rather than a re-set ContextVar) so appends from nested async tasks
# reach the same collector.
_denials: ContextVar[list[dict[str, str]] | None] = ContextVar("eva_role_denials", default=None)


def record_denial(role: str, tool: str) -> None:
    """Note that `role` was refused `tool`. Never raises; recording must not
    become a way to break the refusal path it is observing."""
    sink = _denials.get()
    if sink is not None:
        sink.append({"role": role, "tool": tool})


def denials() -> tuple[dict[str, str], ...]:
    sink = _denials.get()
    return tuple(sink or ())


@contextmanager
def role_scope(role: str | None) -> Iterator[tuple[str, ...]]:
    """Run a delegated sub-task under `role`, in addition to any enclosing role.

    The reset is in a `finally` so a raising sub-task cannot leak its role to
    the caller -- a leaked role would silently restrict subsequent top-level
    calls, which fails safe, but a leaked role after an EXCEPTION is exactly the
    confusing state that makes such a bug hard to find.
    """
    current = _active_roles.get()
    # A `None` role adds no grant and must not clear the enclosing stack.
    nested = current if role is None else current + (role,)
    token = _active_roles.set(nested)
    # A nested scope keeps reporting into the OUTER collector, so a refusal
    # raised deep in a sub-sub-task still reaches whoever started the work.
    sink = _denials.get()
    denial_token = _denials.set(sink if sink is not None else [])
    try:
        yield nested
    finally:
        _active_roles.reset(token)
        _denials.reset(denial_token)
