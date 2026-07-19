"""Post-condition verification — the heart of verification-first execution (Phase 38).

Until now a tool call was reported "done" the moment its handler returned
without raising. That conflates *ran* with *worked*: a write handler can return
a tidy ``{"ok": true}`` while the file on disk is unchanged. Phase 38 closes that
gap by giving every action a **declared post-condition** and checking it against
real state *after* the handler runs, so Eva never claims an unproven effect.

The load-bearing idea here is **provenance** — how much we actually know:

  * ``independent`` — verified against real OS/file state we read ourselves
    (the file exists / is gone / contains the expected text, or — Phase 64 —
    the real foreground window matches the one we just tried to focus). This
    is proof.
  * ``self_reported`` — we only trust the tool's own success flag (e.g. a local
    read returning a dict). Fine for reads, but not proof of a world change.
  * ``observed`` — reserved for a local UI/network effect (a click, a
    keystroke, a launch) independently confirmed via perception. Nothing in
    this codebase can do that yet, so no verification method currently
    produces this provenance (see Phase 64: it used to be claimed anyway —
    see ``unverified`` below).
  * ``unverified`` — no verification method applies, *or* one applies in
    principle but nothing here can independently check it (e.g. "does this
    screen now show the typed text") — either way we say so plainly rather
    than borrow confidence from the tool's own self-report.

Only ``independent`` failure is treated as a hard "the action did not happen";
the weaker classes never *upgrade* confidence into a false claim of success.
Everything here is pure (no registry import → no import cycle) and fail-safe.

Phase 64 note: before this phase, every ``_OBSERVED_METHODS`` entry (including
``app_window_active``) reported ``provenance="observed"`` with ``verified``
silently borrowed from the tool's own self-reported ``ok`` — so a tool that
itself lied about success (e.g. the old ``focus_window``, see
``eva.desktop.windows``) had that lie laundered into an apparent
independent-looking "verified" confirmation. ``app_window_active`` now has a
real independent check (below); everything else in ``_OBSERVED_METHODS``
instead honestly reports ``unverified`` and ``verified=False`` — it was never
actually observed, so it no longer claims to have been.

Phase 64 follow-up (the mirror-image regression): giving ``app_window_active``
a real independent check initially broke ``app.open``, which also declared
that method. "Opened" is not "focused" — an app can launch correctly without
taking the foreground (another process holding the foreground lock is the
*ordinary* case, not an edge case) — so a real foreground check made a
perfectly successful launch independently fail, demoting ``ok`` to ``False``
for work that actually worked. The fix is **not** a name heuristic bolted onto
``app_window_active`` (that already happened once for ``app.close_request``
below, and piling a third case onto it was exactly the wrong direction): each
tool now declares the ``verification_method`` that actually describes its own
postcondition — ``app.open`` → ``app_window_open`` (a window now exists,
independent of focus), ``app.focus`` → ``app_window_active`` (foreground IS
the postcondition), ``app.close_request`` → ``command_result_success``
(nothing here independently checks "window now absent" yet, so it declares
what it actually gets rather than routing through a method that does not
apply). No tool-name sniffing is needed for any of the three.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROVENANCE_INDEPENDENT = "independent"
PROVENANCE_SELF_REPORTED = "self_reported"
PROVENANCE_OBSERVED = "observed"
PROVENANCE_UNVERIFIED = "unverified"

# Verification methods (from ToolSpec.verification_method) that describe a
# local UI/network effect nothing here can independently confirm (no
# perception capability is wired up to check them). ``app_window_active`` is
# deliberately NOT in this set: Phase 64 gave it a real independent check (see
# verify_postcondition below), because "is this window the foreground window"
# is something we CAN read from the OS ourselves.
_OBSERVED_METHODS = {
    "screen_state_changed",
    "text_field_contains",
    "url_opened",
    "message_draft_prepared",
    "message_sent_likely",
}


@dataclass(frozen=True)
class PostCondition:
    """What must be true after an action for it to count as done."""

    method: str
    params: dict[str, Any]
    description: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PostConditionResult:
    """The outcome of independently checking a post-condition."""

    method: str
    verified: bool
    independent: bool
    provenance: str
    confidence: float
    detail: str
    remediation: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _first(args: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = args.get(key)
        if value:
            return str(value)
    return ""


def derive_postcondition(tool_name: str, verification_method: str, args: dict[str, Any]) -> PostCondition:
    """Turn a tool's declared verification_method + call args into a concrete
    post-condition. File semantics are derived from the *tool*, not blindly from
    the metadata: a delete's real post-condition is that the file is now gone,
    even though its declared method is ``file_exists``.
    """
    name = (tool_name or "").lower()
    method = (verification_method or "command_result_success").strip()

    if "delete" in name:
        path = _first(args, "path", "target")
        return PostCondition("file_absent", {"path": path}, f"{path or 'target'} no longer exists")

    if method == "file_contains":
        path = _first(args, "path", "target")
        text = _first(args, "content", "replace", "new_text", "new", "text")
        if text:
            return PostCondition("file_contains", {"path": path, "text": text}, f"{path or 'file'} contains the written text")
        # A patch/write with no recoverable expected text degrades to existence.
        return PostCondition("file_exists", {"path": path}, f"{path or 'file'} exists after write")

    if method == "file_exists":
        # copy/move target is the destination; a bare write target is the path.
        path = _first(args, "dst", "dest", "destination", "target", "path")
        return PostCondition("file_exists", {"path": path}, f"{path or 'file'} exists")

    if method == "app_window_open":
        # app.open declares this: "opened" means a window now exists, NOT
        # that it took the foreground (that would be app_window_active, and
        # conflating the two was a real regression -- an app can launch
        # correctly while another process holds the foreground lock, which
        # is the ordinary case, not an edge case).
        query = _first(args, "app", "query", "target")
        return PostCondition("app_window_open", {"query": query}, f"{query or 'the requested app'} has an open window")

    if method == "app_window_active":
        # Only app.focus declares this now (app.open uses app_window_open
        # above; app.close_request declares command_result_success directly
        # on its ToolSpec, since a successful close's postcondition -- the
        # window is now ABSENT -- is the opposite of "still focused" and
        # nothing here independently checks that yet). No name sniffing
        # needed: each tool declares the verification_method that actually
        # applies to it, rather than this function guessing from the name.
        query = _first(args, "query", "app", "target")
        return PostCondition("app_window_active", {"query": query}, f"{query or 'the requested window'} is the active foreground window")

    if method in _OBSERVED_METHODS:
        return PostCondition(method, {}, "local UI/network effect (not independently verifiable)")

    if method in {"no_verification_available", "none", ""}:
        return PostCondition("no_verification_available", {}, "no verification method available")

    return PostCondition("command_result_success", {}, "tool reported success")


def _result_reports_success(result: Any) -> bool:
    """Whether a tool's own return value indicates success (self-report)."""
    if isinstance(result, dict):
        if result.get("ok") is False:
            return False
        if result.get("hard_blocked") or result.get("requires_confirmation"):
            return False
        if result.get("error"):
            return False
    return True


def verify_postcondition(post: PostCondition, result: Any) -> PostConditionResult:
    """Independently check a post-condition against real state where we can.

    Fail-safe: any error reading the filesystem yields an ``unverified`` result
    rather than raising into the caller.
    """
    method = post.method
    try:
        if method == "file_exists":
            path = str(post.params.get("path") or "")
            ok = bool(path) and Path(path).exists()
            return PostConditionResult(
                method, ok, True, PROVENANCE_INDEPENDENT,
                0.97 if ok else 0.05, f"file_exists({path})={ok}",
                None if ok else "the file was not created; restore checkpoint or retry",
            )
        if method == "file_absent":
            path = str(post.params.get("path") or "")
            ok = bool(path) and not Path(path).exists()
            return PostConditionResult(
                method, ok, True, PROVENANCE_INDEPENDENT,
                0.97 if ok else 0.05, f"file_absent({path})={ok}",
                None if ok else "the file still exists; the delete did not take effect",
            )
        if method == "file_contains":
            path = str(post.params.get("path") or "")
            text = str(post.params.get("text") or "")
            exists = bool(path) and Path(path).exists()
            ok = exists and text in Path(path).read_text(encoding="utf-8", errors="replace")
            return PostConditionResult(
                method, ok, True, PROVENANCE_INDEPENDENT,
                0.95 if ok else 0.1, f"file_contains({path})={ok}",
                None if ok else "expected content not found; restore checkpoint or rewrite",
            )
        if method == "app_window_open":
            # Regression fix: "opened" is not "focused". Uses
            # verify_app_opened -- which already retries/settles, because a
            # launch can take a moment to produce a window -- and checks
            # OPEN, not FOREGROUND. Ignores `result` entirely on purpose,
            # same as app_window_active below: this is proof, not a
            # self-report.
            query = str(post.params.get("query") or "")
            if not query:
                return PostConditionResult(
                    method, False, False, PROVENANCE_UNVERIFIED, 0.2,
                    "app_window_open: no target app was recorded to verify against", "verify manually",
                )
            from ..desktop.verifier import verify_app_opened

            outcome = verify_app_opened(query)
            ok = bool(outcome.get("verified"))
            return PostConditionResult(
                method, ok, True, PROVENANCE_INDEPENDENT,
                0.95 if ok else 0.1, f"app_window_open({query})={ok}",
                None if ok else f"no window found for '{query}' after opening it",
            )
        if method == "app_window_active":
            # Phase 64: independently check the REAL foreground window rather
            # than trusting the tool's self-reported ok (that self-report is
            # exactly what was False-positive for the old focus_window bug --
            # see backend/tests for the regression pin using that exact
            # payload). Ignores `result` entirely on purpose: this is proof,
            # not a self-report.
            query = str(post.params.get("query") or "")
            if not query:
                # Defensive only: every currently-registered app_window_active
                # tool requires query/app as an arg, so this should not be
                # reachable in practice. Without a target we have nothing to
                # check -- that is "we don't know", not "we proved it failed",
                # so this stays unverified rather than independently False
                # (which would fabricate a demotion in ToolExecutor).
                return PostConditionResult(
                    method, False, False, PROVENANCE_UNVERIFIED, 0.2,
                    "app_window_active: no target window was recorded to verify against", "verify manually",
                )
            from ..desktop.verifier import verify_window_focused

            outcome = verify_window_focused(query)
            ok = bool(outcome.get("verified"))
            active = outcome.get("active_window") if isinstance(outcome.get("active_window"), dict) else {}
            foreground_title = str(active.get("title") or "") if isinstance(active, dict) else ""
            return PostConditionResult(
                method, ok, True, PROVENANCE_INDEPENDENT,
                0.97 if ok else 0.05, f"app_window_active({query})={ok} (foreground={foreground_title or 'unknown'})",
                None if ok else f"'{query}' is not the active foreground window (foreground is {foreground_title or 'unknown'})",
            )
    except Exception as exc:  # filesystem/OS hiccup — be honest, don't crash
        return PostConditionResult(
            method, False, False, PROVENANCE_UNVERIFIED, 0.2,
            f"verification error: {type(exc).__name__}: {exc}", "verify manually",
        )

    if method in _OBSERVED_METHODS:
        # Phase 64: this used to derive `verified` from the tool's own
        # self-reported `ok` while still labeling it PROVENANCE_OBSERVED --
        # i.e. claiming an independent-looking observation that never
        # happened (nothing here has a perception capability wired up to
        # actually look). Say so plainly instead: unverified, not observed,
        # and never verified=True on the strength of a self-report alone.
        return PostConditionResult(
            method, False, False, PROVENANCE_UNVERIFIED,
            0.2, f"{method}: cannot be independently verified (no perception capability wired up)",
            "confirm the visible state yourself (Eva cannot prove this without perception)",
        )

    if method == "no_verification_available":
        return PostConditionResult(
            method, False, False, PROVENANCE_UNVERIFIED, 0.2,
            "no verification method available for this action", "verify manually",
        )

    # command_result_success — trust the tool's own success flag only.
    ok = _result_reports_success(result)
    return PostConditionResult(
        method, ok, False, PROVENANCE_SELF_REPORTED,
        0.6 if ok else 0.3, "tool self-reported success" if ok else "tool self-reported failure",
        None if ok else "the tool reported an error",
    )


def verify_tool_effect(tool_name: str, verification_method: str, args: dict[str, Any], result: Any) -> PostConditionResult:
    """Derive a post-condition for a tool call and verify it. Fail-safe."""
    try:
        post = derive_postcondition(tool_name, verification_method, args)
        return verify_postcondition(post, result)
    except Exception as exc:
        return PostConditionResult(
            "error", False, False, PROVENANCE_UNVERIFIED, 0.2,
            f"could not derive/verify post-condition: {type(exc).__name__}: {exc}", "verify manually",
        )
