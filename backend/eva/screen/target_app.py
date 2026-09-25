"""Which app's window a screen-input pending action should be gated against
(Phase 117 round 4).

Round 3 closed the gap between "the runner planned a keystroke" and "the
approved keystroke lands somewhere" by recording a target window when the
pending action is CREATED and restoring it before replay. It got the MOMENT
right and the SOURCE wrong: it recorded `desktop.windows.get_active_window()`
-- "whatever is foreground right now" -- which is exactly the value round 3
existed to stop trusting. Live-driving "open calculator and type the sum of
five and six into it" with the user actually working in Chrome recorded
Chrome's window: Calculator was open and verified, but not in front, because
`runner._target_in_front` correctly saw the browser had focus and the call
fell through to the ordinary gate -- which then asked `get_active_window()`
the same wrong question.

THE RULE: the foreground window at gate time is never trusted as the target.
The target must be the window of the app the TASK ITSELF opened and verified
(`runner`'s `loop_vars["typing_target"]`, set only after an `open_app` /
`window_focus` call's result was independently verified). This module is how
that app name crosses from the runner (which knows it) to
`registry._create_gated_pending` (which needs it) without threading it
through every call signature between them.

A ContextVar, opened by the runner around exactly the ONE `executor.execute`
call for a screen-input tool, on the coroutine that makes that call --
deliberately never around a thread hop. That is the Phase 103 lesson this
whole project keeps re-learning: a scope opened around `mcp.runner.run_async`
is a silent no-op on the worker thread the coroutine actually runs on. There
is no thread hop here -- `executor.execute` -> `registry.run` ->
`_create_gated_pending` is one synchronous call stack on the coroutine that
opened the scope -- so this is safe by construction, not by care taken at
each call site.

No app in scope (an ordinary allow-class call, a console path that creates no
scope, a tainted/undelegated context) reads as `None`, which
`_create_gated_pending` treats as "record no target window" -- never a
fallback to the foreground. A caller with a real, task-verified target is the
ONLY way a screen-input pending action ever gets a target window at all.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_verified_target_app: ContextVar[str | None] = ContextVar("eva_verified_target_app", default=None)


@contextmanager
def open_target_app_scope(app: str | None) -> Iterator[str | None]:
    """Declare `app` as the task-verified target for screen-input calls made
    inside this block. `app` is the same string `open_app`/`window_focus`
    args carry (e.g. "calculator") -- resolved to a window via
    `desktop.windows.find_window` only at the point a pending action is
    actually created, never here.

    `app=None` is a valid, common case (no verified app yet, e.g. before the
    task has opened anything) and simply means "no target" downstream -- it
    is not an error and does not need a caller-side branch to avoid.
    """
    token = _verified_target_app.set(app)
    try:
        yield app
    finally:
        _verified_target_app.reset(token)


def verified_target_app() -> str | None:
    """The app name the CURRENT screen-input call was verified against, or
    `None` if no task-verified target is in scope. Read by
    `registry._create_gated_pending`; never guesses, never reads the
    foreground window."""
    return _verified_target_app.get()
