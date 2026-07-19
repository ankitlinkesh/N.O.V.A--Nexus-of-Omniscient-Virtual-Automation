"""Standalone verifier for Phase 64: the agent being lied to by its own
infrastructure.

Four defects, confirmed by running the real code, all sharing one shape -- a
layer reports success for something that did not happen. For a multi-step
agent this compounds: it proceeds to step 2 believing step 1 worked.

  * **Defect 1** -- ``eva.desktop.windows.focus_window`` used a bare
    ``user32.SetForegroundWindow(hwnd)``, which Windows' foreground lock
    blocks from a background process. Measured from a forced clean state
    (Notepad foreground, asked to focus Chrome): the focus never took effect.
    Fixed with the standard AttachThreadInput dance
    (``_try_set_foreground``), plus polling ``get_active_window()`` over a
    short bounded settle window (``_wait_for_focus``) instead of reading it
    immediately -- an immediate read races the window manager and can see a
    real, completed focus change as if it had not happened.
  * **Defect 2** -- ``focus_window`` returned ``ok: True`` regardless of
    whether focus actually happened. Every caller in this codebase treats
    ``result.get("ok") is True`` as proof of success, so this was read as
    success everywhere. Fixed: ``ok`` is now tied to the independently
    verified outcome, with a clear ``error`` and the real foreground window
    in the payload on failure. ``_show_window`` (minimize/maximize/restore)
    had the same pattern (trusting ``ShowWindow``'s return value, which is
    not a success flag -- it reports the window's PREVIOUS visibility) and
    got the same fix.
  * **Defect 3** -- ``eva.tools.postconditions`` declared
    ``app_window_active``/``screen_state_changed``/``text_field_contains``/
    ``url_opened`` as verifiable, but none of them had real logic: all of
    them derived ``verified`` from the tool's own self-reported ``ok`` while
    claiming ``provenance="observed"`` -- laundering a lying tool's lie (like
    the old ``focus_window``) into an apparently independent-looking
    confirmation, returned to the model in every tool result. Fixed:
    ``app_window_active`` now performs a REAL independent check (reads the
    actual foreground window); every other now-honest method reports
    ``provenance="unverified"`` and ``verified=False`` rather than claiming
    an observation nothing here can actually make. ``ToolExecutor`` still
    never fabricates a failure for these (only an INDEPENDENT failure may
    demote ``ok`` -- that logic is untouched).
  * **Defect 4** -- ``ToolExecutor.execute_all`` sliced planned calls with a
    hardcoded, unnamed ``calls[:3]``; anything beyond the third call was
    dropped with no error, no warning, and nothing told to the model or the
    user. Fixed: the cap is now named and configurable
    (``max_tools_per_step()`` / ``EVA_MAX_TOOLS_PER_STEP``, default
    unchanged at 3), and when it actually truncates a plan, an explicit
    result is appended saying so.

Also wires the previously-orphaned ``app.focus`` tool (registered, allow-class,
but reachable from nowhere in backend/eva) into exactly two places: the
typed-console "focus"/"focus window" command, and a focus-restore attempt
inside ``screen_submit_form`` before it aborts on a staged-window mismatch --
the abort remains the fallback if the restore does not fix it.

Fully offline: no network, no LLM, no real mouse/keyboard movement, no real
window is ever focused (every win32-touching seam is monkeypatched), and the
vault + pending-action ledger are redirected to a throwaway temp directory
before anything that reads those env vars is imported, following
scripts/verify_eva_phase63_live_fixes.py's house skeleton.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> int:
    tmpdir = tempfile.TemporaryDirectory(prefix="eva-phase64-verify-")
    tmp_path = Path(tmpdir.name)
    os.environ["EVA_VAULT_PATH"] = str(tmp_path / "vault.json")
    os.environ["EVA_VAULT_ENABLED"] = "1"
    os.environ["EVA_PENDING_ACTION_LEDGER_PATH"] = str(tmp_path / "pending_actions.jsonl")
    os.environ["EVA_GUI_GROUNDING_ENABLED"] = "1"
    try:
        return _run()
    finally:
        tmpdir.cleanup()


# -- Defects 1+2: focus_window actually focuses, and ok reflects reality ----


def _verify_focus_window_honesty() -> None:
    from backend.eva.desktop import windows as windows_module

    chrome = windows_module.WindowInfo(hwnd=1, title="Google Chrome", process_id=1, process_name="chrome.exe", executable=r"C:\chrome\chrome.exe")
    notepad = windows_module.WindowInfo(hwnd=2, title="Untitled - Notepad", process_id=2, process_name="notepad.exe", executable=r"C:\Windows\notepad.exe")

    saved_find_window = windows_module.find_window
    saved_try_set_foreground = windows_module._try_set_foreground
    saved_get_active_window = windows_module.get_active_window
    try:
        windows_module.find_window = lambda query, limit=1: [chrome]
        windows_module._try_set_foreground = lambda hwnd: None

        # The exact CONFIRMED regression: focus never actually takes effect
        # (Notepad stays foreground) -- ok must be False, with a clear error
        # and the REAL foreground window in the payload.
        windows_module.get_active_window = lambda: notepad
        result = windows_module.focus_window("chrome", settle_timeout=0.05, settle_interval=0.01)
        check(result["ok"] is False, f"focus_window must report ok=False when focus never took effect, got {result}")
        check(result.get("error") == "focus_failed", f"expected error='focus_failed', got {result}")
        check(result["active_window"]["title"] == "Untitled - Notepad", f"the real foreground window must be in the payload: {result}")

        # ok is True only when the foreground window really matches.
        windows_module.get_active_window = lambda: chrome
        result = windows_module.focus_window("chrome", settle_timeout=0.05, settle_interval=0.01)
        check(result["ok"] is True, f"focus_window must report ok=True when focus really happened, got {result}")
        check(result["verified"] is True, result)

        # An immediate read races the window manager -- polling must recover
        # a real, late-landing focus change instead of a false negative.
        reads = {"n": 0}

        def flaky() -> object:
            reads["n"] += 1
            return notepad if reads["n"] < 3 else chrome

        windows_module.get_active_window = flaky
        result = windows_module.focus_window("chrome", settle_timeout=0.3, settle_interval=0.01)
        check(result["ok"] is True, f"a late-landing real focus change must not read as a false negative: {result}")
        check(reads["n"] >= 3, "must poll more than once before succeeding")
    finally:
        windows_module.find_window = saved_find_window
        windows_module._try_set_foreground = saved_try_set_foreground
        windows_module.get_active_window = saved_get_active_window


# -- Defect 3: app_window_active is really independent; the rest are honest -


def _verify_postcondition_honesty() -> None:
    from backend.eva.desktop import verifier as desktop_verifier
    from backend.eva.desktop.windows import WindowInfo
    from backend.eva.tools.postconditions import derive_postcondition, verify_tool_effect
    from backend.eva.tools.registry import ToolRegistry

    chrome = WindowInfo(hwnd=1, title="Google Chrome", process_id=1, process_name="chrome.exe", executable=r"C:\chrome\chrome.exe")
    notepad = WindowInfo(hwnd=2, title="Untitled - Notepad", process_id=2, process_name="notepad.exe", executable=r"C:\Windows\notepad.exe")

    saved_get_active_window = desktop_verifier.get_active_window
    try:
        # The exact CONFIRMED lying payload from focus_window's old behavior:
        # ok=True, focused=False, verified=False. app_window_active must
        # independently discover the mismatch and fail -- it must not trust
        # the payload's own ok flag (or any other field) at all.
        desktop_verifier.get_active_window = lambda: notepad
        lying_payload = {
            "ok": True, "focused": False, "verified": False,
            "window": {"title": "Google Chrome"}, "active_window": {"title": "Untitled - Notepad"},
        }
        outcome = verify_tool_effect("app.focus", "app_window_active", {"query": "chrome"}, lying_payload)
        check(outcome.provenance == "independent", f"expected independent provenance, got {outcome.provenance!r}")
        check(outcome.independent is True, outcome.as_dict())
        check(outcome.verified is False, f"app_window_active must independently catch the lying payload: {outcome.as_dict()}")

        # And it passes when focus really happened.
        desktop_verifier.get_active_window = lambda: chrome
        honest_payload = {"ok": True, "focused": True, "verified": True}
        outcome = verify_tool_effect("app.focus", "app_window_active", {"query": "chrome"}, honest_payload)
        check(outcome.verified is True, f"app_window_active must pass when focus really happened: {outcome.as_dict()}")

        # Ignores the tool's self-report entirely, in both directions.
        outcome = verify_tool_effect("app.focus", "app_window_active", {"query": "chrome"}, {"ok": False, "error": "whatever"})
        check(outcome.verified is True, "app_window_active must not defer to a self-reported failure when the real window matches")

        # A focus that lands on a LATER read (verify_window_focused now
        # retries, matching verify_app_opened's already-established pattern)
        # must not be reported as a false failure.
        reads = {"n": 0}

        def flaky_get_active_window():
            reads["n"] += 1
            return notepad if reads["n"] == 1 else chrome

        desktop_verifier.get_active_window = flaky_get_active_window
        outcome = verify_tool_effect("app.focus", "app_window_active", {"query": "chrome"}, {"ok": True})
        check(outcome.verified is True, f"a focus landing on the 2nd read must not be a false failure: {outcome.as_dict()}")
        check(reads["n"] >= 2, "verify_window_focused must retry, not read once")
    finally:
        desktop_verifier.get_active_window = saved_get_active_window

    # -- Regression fix: app_window_active is the WRONG postcondition for
    # app.open ("opened" is not "focused" -- an app can launch correctly
    # without taking the foreground, which is the ordinary case, not an edge
    # case). Rather than grow a tool-name heuristic on app_window_active to a
    # third case, each tool now declares the verification_method that
    # actually applies to it -- pinned directly at the registry.
    registry = ToolRegistry()
    open_spec = registry.get("app.open")
    check(open_spec is not None and open_spec.verification_method == "app_window_open", "app.open must declare app_window_open, not app_window_active")
    focus_spec = registry.get("app.focus")
    check(focus_spec is not None and focus_spec.verification_method == "app_window_active", "app.focus must keep app_window_active -- foreground IS the postcondition for focus")
    close_spec = registry.get("app.close_request")
    check(
        close_spec is not None and close_spec.verification_method == "command_result_success",
        f"a close-shaped tool must not use the focus-based check: {close_spec.verification_method if close_spec else None!r}",
    )

    post = derive_postcondition("app.open", "app_window_open", {"app": "chrome"})
    check(post.method == "app_window_open" and post.params["query"] == "chrome", post.as_dict())

    # app_window_open is a real independent check of the RIGHT thing (open,
    # not focus): verifies when a window exists, regardless of foreground.
    saved_find_window = desktop_verifier.find_window
    try:
        desktop_verifier.find_window = lambda query, limit=3: [notepad]
        outcome = verify_tool_effect("app.open", "app_window_open", {"app": "notepad"}, {"ok": True})
        check(outcome.provenance == "independent" and outcome.independent is True, outcome.as_dict())
        check(outcome.verified is True, f"app_window_open must verify when a window exists: {outcome.as_dict()}")

        desktop_verifier.find_window = lambda query, limit=3: []
        outcome = verify_tool_effect("app.open", "app_window_open", {"app": "nothing_ever_opened_xyz"}, {"ok": True})
        check(outcome.independent is True and outcome.verified is False, f"app_window_open must fail when no window is ever found: {outcome.as_dict()}")
    finally:
        desktop_verifier.find_window = saved_find_window

    # Every other formerly-"observed" method is now honestly unverified --
    # even when the tool SELF-REPORTS success, because that self-report is
    # exactly what cannot be trusted.
    from backend.eva.tools.postconditions import verify_tool_effect as _verify_tool_effect

    for method in ("screen_state_changed", "text_field_contains", "url_opened", "message_draft_prepared", "message_sent_likely"):
        outcome = _verify_tool_effect("screen.type_text", method, {"text": "hi", "reason": "eval"}, {"ok": True})
        check(outcome.provenance == "unverified", f"{method}: expected unverified, got {outcome.provenance!r}")
        check(outcome.verified is False, f"{method}: must not claim verified=True from a self-report alone")
        check(outcome.independent is False, f"{method}: must not claim independent")


def _verify_app_open_regression_end_to_end() -> None:
    """The centerpiece: the exact regression, measured on a real machine,
    driven through the REAL ToolExecutor + ToolRegistry (not just the
    postcondition function directly) -- app.open succeeds (the window
    genuinely exists) while another process holds the foreground lock, and
    this must NOT be reported as a failure. Never launches a real process:
    app_control_tools.open_app (the seam app.open's handler actually calls)
    is stubbed out."""
    from backend.eva.agent.executor import ToolExecutor
    from backend.eva.agent.planner import PlannedToolCall
    from backend.eva.desktop import verifier as desktop_verifier
    from backend.eva.desktop.windows import WindowInfo
    from backend.eva.tools import app_control_tools
    from backend.eva.tools.registry import ToolRegistry

    notepad = WindowInfo(hwnd=3, title="Untitled - Notepad", process_id=3, process_name="notepad.exe", executable=r"C:\Windows\notepad.exe")
    saved_open_app = app_control_tools.open_app
    saved_find_window = desktop_verifier.find_window
    try:
        app_control_tools.open_app = lambda app: f"Opening {app}."
        desktop_verifier.find_window = lambda query, limit=3: [notepad]

        executor = ToolExecutor(ToolRegistry())
        result = executor.execute(PlannedToolCall(tool="app.open", args={"app": "notepad"}))

        check(result.verification is not None and result.verification["method"] == "app_window_open", result.as_dict())
        check(result.verification["independent"] is True, result.as_dict())
        check(result.verification["verified"] is True, f"the window exists, so this must verify even though it is not foreground: {result.as_dict()}")
        check(result.ok is True, f"a successful open must not be demoted just because the app is not foreground: {result.as_dict()}")
    finally:
        app_control_tools.open_app = saved_open_app
        desktop_verifier.find_window = saved_find_window


def _verify_executor_demotion_invariant() -> None:
    from backend.eva.agent.executor import ToolExecutor
    from backend.eva.agent.planner import PlannedToolCall
    from backend.eva.desktop import verifier as desktop_verifier
    from backend.eva.desktop import windows as windows_module
    from backend.eva.desktop.windows import WindowInfo
    from backend.eva.tools.registry import ToolRegistry

    # Non-fabrication: screen.click is allow-class with verification_method
    # "screen_state_changed" (now unverified). Called with no target/label,
    # the REAL handler self-reports failure (ui_target_required) before
    # touching grounding or pyautogui -- fully offline. Even though the tool
    # itself refused, ok must NOT be demoted for a non-independent method.
    executor = ToolExecutor(ToolRegistry())
    result = executor.execute(PlannedToolCall(tool="screen.click", args={"reason": "phase64 probe"}))
    check(result.verification is not None and result.verification["independent"] is False, result.as_dict())
    check(result.ok is True, f"ToolExecutor must not fabricate a demotion for a non-independent method: {result.as_dict()}")

    # The other half: a genuine INDEPENDENT failure (app_window_active) DOES
    # demote -- proving the non-fabrication test above is meaningful rather
    # than the executor simply never demoting anything.
    notepad = WindowInfo(hwnd=2, title="Untitled - Notepad", process_id=2, process_name="notepad.exe", executable=r"C:\Windows\notepad.exe")
    saved_find_window = windows_module.find_window
    saved_get_active_window = desktop_verifier.get_active_window
    try:
        windows_module.find_window = lambda query, limit=1: []
        desktop_verifier.get_active_window = lambda: notepad
        result = executor.execute(PlannedToolCall(tool="app.focus", args={"query": "chrome"}))
        check(result.verification is not None and result.verification["independent"] is True, result.as_dict())
        check(result.ok is False, f"a genuine independent postcondition failure must demote ok: {result.as_dict()}")
    finally:
        windows_module.find_window = saved_find_window
        desktop_verifier.get_active_window = saved_get_active_window


# -- Defect 4: truncation is reported, not silent ----------------------------


def _verify_truncation_reported() -> None:
    from backend.eva.agent.executor import ToolExecutor
    from backend.eva.agent.planner import PlannedToolCall
    from backend.eva.agent.policies import max_tools_per_step
    from backend.eva.tools.registry import ToolRegistry

    saved_env = os.environ.get("EVA_MAX_TOOLS_PER_STEP")
    try:
        os.environ["EVA_MAX_TOOLS_PER_STEP"] = "3"
        check(max_tools_per_step() == 3, "the default per-step cap must stay 3 -- no behavior change out of the box")

        executor = ToolExecutor(ToolRegistry())
        calls = [PlannedToolCall(tool="workspace_status", args={}) for _ in range(5)]
        results = executor.execute_all(calls)
        check(len(results) == 4, f"3 executed + 1 truncation notice, got {[r.tool for r in results]}")
        check(all(r.ok is True for r in results[:3]), f"the calls within the cap must have actually run: {[r.as_dict() for r in results[:3]]}")
        notice = results[-1]
        check(notice.tool == "plan_truncated" and notice.ok is False, f"truncation must be reported, not silent: {notice.as_dict()}")
        check(notice.result["truncated"] is True and notice.result["limit"] == 3, notice.result)
        check(notice.result["skipped_tools"] == ["workspace_status", "workspace_status"], notice.result)

        # Configurable via env.
        os.environ["EVA_MAX_TOOLS_PER_STEP"] = "2"
        check(max_tools_per_step() == 2, "EVA_MAX_TOOLS_PER_STEP must override the default")
        results = executor.execute_all(calls)
        check(len(results) == 3, f"2 executed + 1 truncation notice, got {[r.tool for r in results]}")
        check(results[-1].result["limit"] == 2, results[-1].result)
    finally:
        if saved_env is None:
            os.environ.pop("EVA_MAX_TOOLS_PER_STEP", None)
        else:
            os.environ["EVA_MAX_TOOLS_PER_STEP"] = saved_env


# -- Wiring: app.focus gets a real caller, without becoming planner-reachable


def _verify_app_focus_console_wiring() -> None:
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.tools.registry import ToolRegistry

    class DryRegistry(ToolRegistry):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[dict] = []

        def run(self, name, **kwargs):
            self.calls.append({"tool": name, "args": dict(kwargs)})
            if name == "app.focus":
                return {
                    "ok": True, "focused": True, "verified": True,
                    "window": {"title": "Google Chrome"}, "active_window": {"title": "Google Chrome"},
                }
            return super().run(name, **kwargs)

    registry = DryRegistry()
    reply = maybe_handle_fast_command("focus window chrome", registry, {})
    check(reply is not None, "'focus window chrome' must be handled as a fast command")
    check(bool(registry.calls) and registry.calls[-1]["tool"] == "app.focus", f"must route through app.focus: {registry.calls}")
    check(registry.calls[-1]["args"].get("query") == "chrome", f"'focus window chrome' must extract 'chrome': {registry.calls[-1]}")

    registry2 = DryRegistry()
    maybe_handle_fast_command("switch to chrome", registry2, {})
    check(registry2.calls and registry2.calls[-1]["tool"] == "app.focus", f"'switch to' synonym must also route through app.focus: {registry2.calls}")

    planner_names = {str(spec.get("name", "")) for spec in ToolRegistry().planner_specs()}
    check("app.focus" not in planner_names, "app.focus must stay OUT of planner_specs() -- console/internal-only")


# -- Wiring: screen_submit_form attempts a focus restore before aborting ----


def _verify_form_submit_focus_restore() -> None:
    from backend.eva.agent.action_model import AgentObservation
    from backend.eva.permissions.ledger import confirm_pending_action
    from backend.eva.screen import form_filler, grounding, screen_controller
    from backend.eva.screen.form_filler import FormField, SubmitSpec, stage_form
    from backend.eva.tools.registry import ToolRegistry

    class _Recorder:
        def __init__(self, obs_cls) -> None:
            self._obs = obs_cls
            self.clicks: list[tuple[int, int]] = []
            self.typed: list[str] = []

        def click(self, x, y, reason, action_id: str = "screen.click"):
            self.clicks.append((int(x), int(y)))
            return self._obs(action_id=action_id, success=True, raw_observation={"x": int(x), "y": int(y)}, summary="fake click")

        def type_text(self, text, reason, action_id: str = "screen.type_text"):
            self.typed.append(str(text))
            return self._obs(action_id=action_id, success=True, raw_observation={"chars": len(str(text))}, summary="fake type")

        def press(self, key, reason, action_id: str = "screen.press"):
            self.typed.append(f"KEY:{key}")
            return self._obs(action_id=action_id, success=True, raw_observation={"key": key}, summary="fake press")

    recorder = _Recorder(AgentObservation)
    saved_provider = grounding._default_provider
    saved_click = screen_controller.click
    saved_type_text = screen_controller.type_text
    saved_press = screen_controller.press
    saved_title_fn = form_filler.foreground_window_title
    saved_restore_fn = form_filler.restore_window_focus

    grounding._default_provider = lambda: [grounding.RawElement(name="Email", role="Edit", left=50, top=100, width=80, height=20)]
    screen_controller.click = recorder.click
    screen_controller.type_text = recorder.type_text
    screen_controller.press = recorder.press

    def confirm_and_execute(spec_id: str, reason: str) -> dict:
        registry = ToolRegistry()
        gate_result = registry.run("screen.submit_form", spec_id=spec_id, reason=reason)
        check(gate_result.get("requires_confirmation") is True, f"submission must stay confirm-gated: {gate_result}")
        pending_id = gate_result["pending_id"]
        confirmed = confirm_pending_action(pending_id, override=bool(gate_result.get("risk_class") == "override"))
        check(confirmed.success is True, f"ledger confirmation must succeed: {confirmed}")
        executed = registry.run_approved(pending_id)
        check(isinstance(executed, dict), f"run_approved must return the outcome dict, got {executed!r}")
        return executed

    try:
        # 1. Restore succeeds -> the fill proceeds (never possible before
        # Phase 64, since focus_window did not reliably work).
        state = {"focused": False}
        staged_title = "Sign in - Google Chrome"
        form_filler.foreground_window_title = lambda: staged_title if state["focused"] else "Untitled - Notepad"
        form_filler.restore_window_focus = lambda title: state.__setitem__("focused", True)
        staged = stage_form([FormField("Email", "me@example.com")], reason="phase64 restore succeeds", submit=SubmitSpec("none"), window_title=staged_title)
        outcome = confirm_and_execute(staged.spec_id, staged.reason)
        check(outcome["ok"] is True, f"a successful restore must let the fill proceed: {outcome}")
        check(recorder.clicks == [(90, 110)] and recorder.typed == ["me@example.com"], (recorder.clicks, recorder.typed))

        # 2. Restore attempted but fails -> abort, nothing typed. The abort
        # remains the fallback: restoring focus makes this usable, it must
        # not make it permissive.
        recorder.clicks.clear()
        recorder.typed.clear()
        restore_calls: list[str] = []
        form_filler.foreground_window_title = lambda: "Untitled - Notepad"
        form_filler.restore_window_focus = lambda title: restore_calls.append(title)
        staged = stage_form([FormField("Email", "me@example.com")], reason="phase64 restore fails", submit=SubmitSpec("none"), window_title="Sign in - Google Chrome")
        outcome = confirm_and_execute(staged.spec_id, staged.reason)
        check(restore_calls == ["Sign in - Google Chrome"], f"a restore attempt must have been made: {restore_calls}")
        check(outcome["ok"] is False, f"the abort must remain the fallback when the restore attempt does not work: {outcome}")
        check(outcome["steps"][-1]["status"] == "window_changed", outcome)
        check(recorder.clicks == [] and recorder.typed == [], "nothing may be typed when the window is still unconfirmed")
        check("me@example.com" not in str(outcome), "the outcome must stay value-free on this abort path")
    finally:
        grounding._default_provider = saved_provider
        screen_controller.click = saved_click
        screen_controller.type_text = saved_type_text
        screen_controller.press = saved_press
        form_filler.foreground_window_title = saved_title_fn
        form_filler.restore_window_focus = saved_restore_fn


def _run() -> int:
    from scripts import verify_eva_all

    _verify_focus_window_honesty()
    _verify_postcondition_honesty()
    _verify_app_open_regression_end_to_end()
    _verify_executor_demotion_invariant()
    _verify_truncation_reported()
    _verify_app_focus_console_wiring()
    _verify_form_submit_focus_restore()

    # Registration.
    name = "verify_eva_phase64_honest_effects.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 64 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 64 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 64 verifier")

    print(
        "PASS: Phase 64 honest effects -- four defects sharing one shape (infrastructure reporting success for "
        "something that did not happen) are fixed and pinned. (1)+(2) focus_window actually attempts the focus "
        "change (the AttachThreadInput dance) and polls get_active_window() over a bounded settle window instead "
        "of reading it immediately, and ok now reflects the independently VERIFIED outcome, never the raw OS "
        "call's claim -- the exact CONFIRMED regression (ok=True, focused=False, verified=False while Notepad "
        "stayed foreground) now reports ok=False with error='focus_failed' and the real foreground window in the "
        "payload. (3) app_window_active gets a real independent postcondition check (reads the real foreground "
        "window itself, ignoring the tool's own self-report entirely); every other formerly-'observed' method now "
        "honestly reports unverified instead of a fabricated 'observed' provenance borrowed from the tool's "
        "self-reported ok, and ToolExecutor still never fabricates a demotion for a non-independent verification "
        "(only a genuine independent failure demotes -- both halves of that invariant are proven). (4) "
        "execute_all's per-step cap is named and configurable (max_tools_per_step/EVA_MAX_TOOLS_PER_STEP, default "
        "unchanged at 3), and truncation beyond it is now reported as an explicit result instead of silently "
        "dropped. Also: the previously-orphaned app.focus tool now has a real caller (the console "
        "'focus'/'focus window' command) while staying OUT of planner_specs(), and screen_submit_form attempts "
        "one focus restore before aborting on a staged-window mismatch -- proceeding if the restore fixes it, "
        "still aborting with nothing typed if it does not. Follow-up regression fix: giving app_window_active a "
        "real independent check initially broke app.open, which also declared that method -- 'opened' is not "
        "'focused' (another process holding the foreground lock is the ordinary case, not an edge case), so a "
        "perfectly successful launch was independently demoted to ok=False. Fixed by modelling, not by growing a "
        "tool-name heuristic further: app.open now declares app_window_open (a real independent check that a "
        "window exists, via the already-retrying verify_app_opened), app.focus keeps app_window_active (foreground "
        "IS its postcondition), and app.close_request declares command_result_success directly. "
        "verify_window_focused also gained the same retry/settle behaviour its siblings already had, so a focus "
        "landing a moment late is not a false failure either."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
