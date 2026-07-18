"""Filling a form — chaining locate -> click -> type, safely (Phase 58).

Phase 56 made a single field clickable by label and Phase 57 made the screen
observable. This composes them into the thing people actually ask for: "fill in
this form." For each (label, value) it clicks the field to focus it and types the
value — going through the ordinary gated tools every step, so it inherits the
confidence gate, the real-input gate, and the Phase 55 risk escalation. It adds
no new authority; it is pure orchestration over tools NOVA already has.

Three safety commitments:

  * **It never records the values.** A form value is often a password or a
    payment detail. A :class:`FillStep` carries only the field label, whether the
    value looked like a live secret, and the outcome — never the value itself.
    Nothing here logs, traces, or returns the typed text.
  * **It stops rather than blunders.** The moment a field cannot be found (or a
    click/type is refused, e.g. real input is off), it stops and reports where —
    it does not keep typing values into the wrong places on a half-understood
    form.
  * **It is driven only from the trusted console.** Like NL rule creation, this
    is reached from a typed fast-command, never wired as a planner tool — so
    untrusted content (Phase 40) cannot make NOVA type attacker-chosen values
    into a form.

The executor is injectable, so the orchestration is tested without a real
desktop; the default routes every step through the real ToolRegistry gate.

Phase 62 adds a second path alongside ``fill_form``: staging. ``screen.type_text``
is confirm-class, so gating each field individually (as ``fill_form`` does) stalls
a real submission at field 1 asking to confirm typing. ``stage_form`` lets the
trusted console record a whole form (fields -- literal or ``@vault:name``
references -- plus what to do when done) as one ``StagedForm`` behind an opaque
``spec_id``; the gated tool ``screen.submit_form`` (see ``screen_tools.py``) takes
only that id and, after a single approval, performs the whole form. See
``describe_staged_form`` for the value-free manifest the approval reads.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

Executor = Callable[..., dict]

# Phase 62: a field value of this form is a REFERENCE into the vault, not a
# literal. It is safe to carry through staging, the gate's pending-call args,
# and the ledger, because it resolves to plaintext only inside the approved
# submit handler (see screen_tools.screen_submit_form) -- never here.
VAULT_PREFIX = "@vault:"


def is_vault_ref(value: str) -> bool:
    return str(value or "").startswith(VAULT_PREFIX)


def vault_ref_name(value: str) -> str | None:
    """"@vault:email" -> "email". None if ``value`` is not a vault reference."""
    text = str(value or "")
    if not text.startswith(VAULT_PREFIX):
        return None
    name = text[len(VAULT_PREFIX) :].strip()
    return name or None


@dataclass(frozen=True)
class FormField:
    """One field to fill. ``value`` is sensitive and never leaves this object."""

    label: str
    value: str


@dataclass(frozen=True)
class FillStep:
    """The outcome of one field — deliberately value-free."""

    label: str
    status: str          # filled | not_found | click_refused | type_refused
    secret: bool = False  # did the value look like a live secret?
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FillOutcome:
    steps: list[FillStep] = field(default_factory=list)
    filled: int = 0
    ok: bool = False
    stopped_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"steps": [s.as_dict() for s in self.steps], "filled": self.filled, "ok": self.ok, "stopped_reason": self.stopped_reason}


# -- staging a form for one-shot, gated submission (Phase 62) ---------------
#
# `fill_form` above gates every keystroke individually, and `screen.type_text`
# is confirm-class -- so a real call stalls at field 1 asking to confirm typing,
# forever, one field at a time. The fix is to gate the whole submission ONCE:
# the trusted console stages a form (fields, values or vault refs, and what to
# do when done) and gets back an opaque `spec_id`. The gated tool
# `screen.submit_form` takes ONLY that id; the gate gets to see the value-free
# manifest (`describe_staged_form`) and approves the id, never a value. After
# approval the handler pops the staged form (single-use) and does every
# click/type/submit itself, calling the screen_tools functions directly rather
# than re-entering the gate -- see the loud comment in screen_tools.py.
#
# This store mirrors `eva.security.tool_gate._PENDING_CALLS`: a module-level
# dict, single-use pop, and a TTL so a stale id cannot be replayed long after
# the console session that staged it is gone.


@dataclass(frozen=True)
class SubmitSpec:
    """What to do once every field is filled."""

    mode: str          # "click" | "press" | "none"
    label: str = ""    # for "click", e.g. "Submit"
    key: str = ""      # for "press", e.g. "enter"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StagedForm:
    """A form staged from the trusted console, waiting for gate approval.

    ``fields`` may hold literal values or ``@vault:name`` references -- either
    way this object never holds a decrypted secret; a vault ref only resolves
    to plaintext inside the post-approval submit handler.
    """

    spec_id: str
    reason: str
    fields: tuple[FormField, ...]
    submit: SubmitSpec
    window_title: str
    created_at: datetime


_STAGED_FORMS: dict[str, StagedForm] = {}
_STAGE_TTL_SECONDS = 300


def _staging_expired(staged: StagedForm) -> bool:
    age = (datetime.now(timezone.utc) - staged.created_at).total_seconds()
    return age > _STAGE_TTL_SECONDS


def stage_form(
    fields: Sequence[FormField | tuple[str, str]],
    *,
    reason: str,
    submit: SubmitSpec,
    window_title: str = "",
) -> StagedForm:
    """Stage a form for one-shot gated submission. Returns the staged record.

    Called only from the trusted console (mirrors ``fill_form``'s trust
    boundary): the caller decides the fields and the submit action, and gets
    back a ``spec_id`` opaque enough that nothing downstream needs to see a
    value again until an approved handler resolves it.
    """
    normalized = tuple(
        f if isinstance(f, FormField) else FormField(str(f[0]), str(f[1])) for f in fields
    )
    spec_id = "fs_" + uuid.uuid4().hex[:12]
    staged = StagedForm(
        spec_id=spec_id,
        reason=str(reason or ""),
        fields=normalized,
        submit=submit,
        window_title=str(window_title or ""),
        created_at=datetime.now(timezone.utc),
    )
    _STAGED_FORMS[spec_id] = staged
    return staged


def peek_staged_form(spec_id: str) -> StagedForm | None:
    """Look up a staged form WITHOUT consuming it. None if unknown or expired."""
    staged = _STAGED_FORMS.get(str(spec_id or ""))
    if staged is None:
        return None
    if _staging_expired(staged):
        # Expired: drop it here too, so a lookup after the TTL cannot linger.
        _STAGED_FORMS.pop(str(spec_id or ""), None)
        return None
    return staged


def pop_staged_form(spec_id: str) -> StagedForm | None:
    """Consume a staged form -- single use. None if unknown or expired.

    This is the injection defense for ``screen.submit_form``: the tool is
    inert without an id this store actually issued, and once popped the same
    id cannot be replayed.
    """
    staged = _STAGED_FORMS.pop(str(spec_id or ""), None)
    if staged is None:
        return None
    if _staging_expired(staged):
        return None
    return staged


def describe_staged_form(spec: StagedForm) -> str:
    """The value-free manifest a human reads before approving the submission.

    Shows vault NAMES (never vault values) and literal values IN FULL -- the
    user typed the literals seconds ago in the same console session, so they
    are not secret, and seeing them is what makes the approval informed.
    """
    header = (
        f'Fill and submit a form in "{spec.window_title}":'
        if spec.window_title
        else "Fill and submit a form:"
    )
    lines = [header]
    for index, item in enumerate(spec.fields, start=1):
        if is_vault_ref(item.value):
            name = vault_ref_name(item.value) or "?"
            lines.append(f"  {index}. {item.label}  <- saved: {name}  (value hidden)")
        else:
            lines.append(f'  {index}. {item.label}  <- "{item.value}"')
    if spec.submit.mode == "click" and spec.submit.label:
        lines.append(f'  Then: click "{spec.submit.label}"')
    elif spec.submit.mode == "press" and spec.submit.key:
        lines.append(f'  Then: press "{spec.submit.key}"')
    return "\n".join(lines)


def foreground_window_title() -> str:
    """Best-effort title of the current foreground window. Never raises.

    Reuses the same window lookup ``screen.observe`` already relies on (see
    ``screen_observer.get_active_window_title``); returns "" on any failure
    (unsupported platform, no foreground window, import error, ...) so a
    console staging a form never fails just because the title is unavailable.
    """
    try:
        from .screen_observer import get_active_window_title

        return str(get_active_window_title() or "")
    except Exception:
        return ""


# -- re-verifying the window before typing (Phase 63) ------------------------
#
# StagedForm captures window_title at STAGING time, and it is shown in the
# approval manifest -- but between staging, human approval, and execution the
# foreground window can change (a notification, an alt-tab, or -- as happened
# live-driving this against a real browser -- a terminal simply holding
# focus while the human approves in it). Without re-checking, screen_tools
# would type the user's decrypted vault value into whatever window happens to
# be in front. See screen_tools.screen_submit_form for where this is called,
# once before EVERY field (not just once at the start of the run).
#
# The matching rule is deliberately NOT exact string equality on the full
# title. A real web page can legitimately rewrite its own document.title
# while it is being filled in -- the page this defect was found on does
# exactly that -- so an exact-equality check would abort mid-fill on a page
# merely updating itself, which is not the harm this guard exists to catch.
# Browser chrome (and many native apps) appends a STABLE suffix to the page/
# document title -- "<page title> - Google Chrome" -- and a genuine window
# switch (Chrome -> a terminal) changes that suffix, not just the leading
# page-title text. So "same window" here means "same trailing '- App Name'
# segment", which tolerates a live page rewriting its own title while still
# catching a real foreground-window change.
#
# When a title has no " - " to split on, its identity IS the whole title --
# meaning ANY change of that title aborts. That is deliberately the safe
# direction: without a recognizable app suffix to key on, we cannot tell "the
# page renamed itself" from "the window changed", so we treat any drift as a
# potential window change rather than risk typing into the wrong place.
def _window_identity(title: str) -> str:
    text = str(title or "").strip()
    if not text:
        return ""
    if " - " in text:
        return text.rsplit(" - ", 1)[1].strip()
    return text


def verify_staged_window(staged: "StagedForm") -> str | None:
    """``None`` if the current foreground window still matches the one this
    form was staged against; otherwise a human-readable reason it does not.

    Fails SAFE in both directions: an empty staged title means "unknown at
    staging time, cannot verify" and is itself a reason to refuse (never
    silently proceed blind), and any identity mismatch (see
    ``_window_identity``) is reported as a window change. Callers should stop
    the whole run -- and type nothing -- on any non-``None`` return.
    """
    expected = str(staged.window_title or "").strip()
    if not expected:
        return "the target window was not recorded when this form was staged, so it cannot be verified; refusing to type blind"
    current = foreground_window_title()
    if _window_identity(expected) != _window_identity(current):
        return f"the foreground window changed (expected a window matching '{expected}', found '{current or '(no foreground window)'}')"
    return None


def _looks_like_secret(value: str) -> bool:
    try:
        from ..privacy.secrets_broker import contains_secret_leak

        return bool(contains_secret_leak(value))
    except Exception:
        # Fail cautious: if we cannot tell, treat it as sensitive (mask it).
        return True


def _ok(result: object) -> bool:
    return isinstance(result, dict) and result.get("ok") is True


def _error_of(result: object) -> str:
    if isinstance(result, dict):
        return str(result.get("error") or "") + " " + str(result.get("message") or "")
    return ""


def _default_executor() -> Executor:
    from ..tools.registry import ToolRegistry

    registry = ToolRegistry()

    def run(tool: str, **kwargs: Any) -> dict:
        result = registry.run(tool, **kwargs)
        return result if isinstance(result, dict) else {"ok": False, "error": "non_dict_result"}

    return run


def fill_form(
    fields: Sequence[FormField | tuple[str, str]],
    *,
    reason: str,
    executor: Executor | None = None,
) -> FillOutcome:
    """Fill each field in order via gated click+type. Stops at the first failure.

    Returns a value-free :class:`FillOutcome`. ``executor(tool, **kwargs)`` is the
    seam — it defaults to routing through the real ToolRegistry gate, so every
    click and keystroke faces the same permission checks as a typed command.
    """
    run = executor or _default_executor()
    normalized = [f if isinstance(f, FormField) else FormField(str(f[0]), str(f[1])) for f in fields]

    steps: list[FillStep] = []
    filled = 0
    for spec in normalized:
        label = spec.label.strip()
        secret = _looks_like_secret(spec.value)
        if not label:
            steps.append(FillStep("", "not_found", secret, "empty field label"))
            return FillOutcome(steps, filled, False, "a field had no label")

        # 1. Focus the field. The gated tool resolves the label via grounding and
        #    enforces the confidence + real-input gates; we only read its verdict.
        click = run("screen.click", reason=reason, label=label)
        if not _ok(click):
            err = _error_of(click).lower()
            if "ambiguous" in err:
                steps.append(FillStep(label, "ambiguous", secret, _error_of(click).strip()[:200]))
                return FillOutcome(steps, filled, False, f"'{label}' matched several fields; be more specific")
            if "ui_target_not_found" in err or "target_required" in err or "low_confidence" in err:
                steps.append(FillStep(label, "not_found", secret, f"could not find field '{label}' on screen"))
                return FillOutcome(steps, filled, False, f"could not find field '{label}'")
            steps.append(FillStep(label, "click_refused", secret, _error_of(click).strip()[:160]))
            return FillOutcome(steps, filled, False, f"click on '{label}' was refused")

        # 2. Type the value. Never store or return the value itself.
        typed = run("screen.type_text", reason=reason, text=spec.value)
        if not _ok(typed):
            steps.append(FillStep(label, "type_refused", secret, _error_of(typed).strip()[:160]))
            return FillOutcome(steps, filled, False, f"typing into '{label}' was refused")

        steps.append(FillStep(label, "filled", secret))
        filled += 1

    return FillOutcome(steps, filled, True, None)


def parse_form_spec(text: str) -> list[FormField]:
    """Parse ``Email=me@x.com; Password=secret; Full Name=John`` into fields.

    Order-preserving. Labels may contain spaces; the split is on the FIRST '='
    of each ';'-separated clause so values may contain '='. Clauses without an
    '=' are skipped. Values are kept verbatim (only outer whitespace trimmed)."""
    fields: list[FormField] = []
    for clause in str(text or "").split(";"):
        if "=" not in clause:
            continue
        label, value = clause.split("=", 1)
        label = label.strip()
        value = value.strip()
        if label and value:
            fields.append(FormField(label, value))
    return fields


__all__ = [
    "FormField",
    "FillStep",
    "FillOutcome",
    "fill_form",
    "parse_form_spec",
    "VAULT_PREFIX",
    "is_vault_ref",
    "vault_ref_name",
    "SubmitSpec",
    "StagedForm",
    "stage_form",
    "peek_staged_form",
    "pop_staged_form",
    "describe_staged_form",
    "foreground_window_title",
    "verify_staged_window",
]
