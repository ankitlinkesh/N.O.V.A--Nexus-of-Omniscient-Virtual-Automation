"""Standalone verifier for Phase 65: risk escalation must read TARGETS, not content.

Phase 55 escalates friction when a call's *arguments* reveal a risk the static
tool class cannot see -- the gate classifies per-TOOL and is blind to ARGS.
That is right, but ``_sensitive_targets`` implemented it by passing the ENTIRE
argument value to ``is_sensitive_target()`` whenever the value contained a path
separator anywhere. So prose tripped it. Measured before the fix:

    message.prepare(recipient='bob',
                    message='I saved it under C:/Windows/System32/drivers/etc/hosts')
        allow -> override

The heaviest friction tier -- requiring ``confirm override act_x`` -- for
*writing a sentence that mentions a path*. The marker list is ordinary English
and ordinary paths (``/windows``, ``system32``, ``program files``, ``/etc/``,
``credentials``, ``secrets``), so this was broad. It was also inconsistent:
``C:/Windows/System32/...`` in prose escalated while ``~/.ssh/id_rsa`` in prose
did not, because the whole sentence was tested rather than an extracted token.

The root cause is a category error, not a bad marker list. ``message`` /
``note`` / ``reason`` are CONTENT -- the tool never acts on them.
``message.prepare`` acts on ``recipient``; the body is payload.

The fix is ``ToolSpec.content_args``: argument names the tool's implementation
provably never dereferences, skipped by the sensitive-target scan.

THE RULE, which this verifier enforces:

    Declare an argument as content ONLY if the tool provably never
    dereferences it -- proven by READING THE IMPLEMENTATION, not by the
    argument's name.

That rule killed this phase's most attractive candidate. ``code_debug_traceback``
looks like pure free-form content; it is not. ``eva/code/debugger.py`` parses
file paths out of the traceback and READS them via ``safe_code_read()``. A test
below pins ``traceback`` as target-bearing so a future well-meaning change
cannot "finish the job" by declaring it.

Trust boundary: ``content_args`` LOWERS friction, inverting Phase 55's
only-ever-escalates invariant. It must therefore come from the ToolSpec in
source and never from caller input, or it is a self-authorization channel
exactly like the ``confirmed``/``_approved`` flags that are already stripped.

Also folded in (same family as Phase 64): ``message_prepare`` returned a
hardcoded ``"verification": {"verified": True, "confidence": 0.8}`` for merely
stashing a dict in memory. Nothing was verified.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SENSITIVE = "C:/Windows/System32/drivers/etc/hosts"

# The exact declared set, pinned. Growing this list must be a deliberate act
# with an implementation-read justification -- not something that drifts in.
# Compare EXPECTED_CLASS_COUNTS in verify_eva_phase51_action_type_audit.py.
EXPECTED_CONTENT_ARGS = {
    "clipboard.write": ("text",),  # Phase 128: stored on the clipboard, never opened as a path
    "message.prepare": ("message",),
    "research_save_note": ("note", "tags"),
    "screen.click": ("reason",),
    "screen.scroll": ("reason",),
    "screen.wait": ("reason",),
}


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def _probe(reg, tool: str, **args) -> tuple[str, bool]:
    from backend.eva.permissions.risk_signals import assess_friction
    from backend.eva.security import tool_gate

    spec = reg._tools[tool]
    base = tool_gate.classify_tool_call(spec)
    base = str(getattr(base, "decision", base))
    result = assess_friction(
        base_decision=base,
        action_type=str(getattr(spec, "action_type", "") or ""),
        args=args,
        content_args=tuple(getattr(spec, "content_args", ()) or ()),
    )
    return result.decision, result.escalated


def _verify_declared_set_is_exactly_what_we_audited(reg) -> None:
    actual = {
        name: tuple(spec.content_args)
        for name, spec in reg._tools.items()
        if getattr(spec, "content_args", ())
    }
    check(
        actual == EXPECTED_CONTENT_ARGS,
        "content_args declarations drifted from the audited set.\n"
        f"  expected: {EXPECTED_CONTENT_ARGS}\n"
        f"  actual:   {actual}\n"
        "Every entry must be justified by reading the handler and confirming it "
        "never dereferences the value. If you added one deliberately, update "
        "EXPECTED_CONTENT_ARGS here and say why in the ToolSpec comment.",
    )


def _verify_no_path_argument_is_declared_content(reg) -> None:
    from backend.eva.permissions.risk_signals import _PATH_ARG_KEYS

    for name, spec in reg._tools.items():
        for arg in getattr(spec, "content_args", ()) or ():
            check(
                str(arg).lower() not in _PATH_ARG_KEYS,
                f"{name} declares the conventional path argument '{arg}' as content. "
                "A path-shaped argument name is exactly what the sensitive-target scan "
                "exists to read; exempting it would blind the check it is named after.",
            )


def _verify_the_false_positives_are_gone(reg) -> None:
    for tool, args in (
        ("message.prepare", {"recipient": "bob", "message": f"I saved it under {SENSITIVE}"}),
        ("research_save_note", {"topic": "windows", "note": f"see {SENSITIVE}", "tags": ""}),
        ("screen.click", {"reason": f"clicking the {SENSITIVE} shortcut", "label": "OK"}),
    ):
        decision, escalated = _probe(reg, tool, **args)
        check(
            not escalated and decision == "allow",
            f"{tool}: content that merely MENTIONS a path still escalates "
            f"(decision={decision}). This is the defect Phase 65 removes.",
        )


def _verify_the_true_positives_survive(reg) -> None:
    """These matter more than the false positives. Each pairs a content arg
    with a target arg on the SAME tool, so a blunt 'skip prose' fix fails."""
    cases = (
        ("message.prepare", {"recipient": SENSITIVE, "message": "hello"}, "recipient is the target"),
        ("research_save_note", {"topic": SENSITIVE, "note": "n", "tags": ""}, "topic is a lookup key"),
        ("screen.click", {"reason": "ok", "label": SENSITIVE}, "label feeds grounding.resolve()"),
        ("file.list_dir", {"path": "C:/Users/HP/.ssh"}, "a real path argument"),
        ("file.list_dir", {"path": "docs/../../../Users/HP/.ssh/id_rsa"}, "traversal"),
        (
            "code_debug_traceback",
            {"traceback": f'File "{SENSITIVE}", line 0'},
            "debugger.py parses paths out of the traceback and READS them",
        ),
    )
    for tool, args, why in cases:
        _, escalated = _probe(reg, tool, **args)
        check(escalated, f"{tool}: escalation was lost for a genuine target ({why}).")


def _verify_smuggling_through_an_undeclared_argument_still_escalates() -> None:
    from backend.eva.permissions.risk_signals import assess_friction

    result = assess_friction(
        base_decision="allow",
        action_type="SAFE_LOCAL_READ",
        args={"weird_unknown_name": "C:/Users/HP/.ssh/id_rsa"},
        content_args=(),
    )
    check(
        result.escalated,
        "a sensitive path smuggled through an oddly named argument must still be "
        "caught -- only names a ToolSpec explicitly declares are skipped.",
    )


def _verify_content_args_cannot_come_from_the_caller(reg) -> None:
    """The trust boundary. A model or HTTP client must not be able to exempt
    an argument by passing content_args= itself."""
    import inspect

    from backend.eva.tools import registry as registry_module

    source = inspect.getsource(registry_module.ToolRegistry.run)
    check(
        '"content_args"' in source and "confirmed" in source,
        "registry.run must strip a caller-supplied 'content_args' kwarg alongside "
        "'confirmed'/'_approved' -- it is a friction-REDUCING signal, so accepting "
        "it from the caller would be a self-authorization channel.",
    )

    # This MUST target a non-path argument name. Using a conventional path key
    # proves nothing: the runtime backstop below refuses to skip those whatever
    # content_args says, so such a check passes even when a caller CAN override
    # the spec. Mutation-testing caught exactly that hole here.
    from backend.eva.permissions.risk_signals import _PATH_ARG_KEYS

    check(
        "recipient" not in _PATH_ARG_KEYS
        and "recipient" not in tuple(reg._tools["message.prepare"].content_args),
        "premise broken: this check relies on `recipient` being a real target that "
        "is neither a path key nor declared content.",
    )
    result = reg.run("message.prepare", recipient=SENSITIVE, message="x", content_args=("recipient",))
    check(
        result.get("ok") is not True or result.get("requires_confirmation") is True,
        "a caller-supplied content_args exempted a real target -- registry.run must "
        "pass spec.content_args only, never anything derived from kwargs.",
    )

    from backend.eva.permissions.risk_signals import assess_friction

    backstop = assess_friction(
        base_decision="allow",
        action_type="SAFE_LOCAL_READ",
        args={"path": "C:/Users/HP/.ssh/id_rsa"},
        content_args=("path",),
    )
    check(
        backstop.escalated,
        "runtime backstop failed: a conventional path argument must be scanned "
        "even if content_args wrongly names it.",
    )


def _verify_hard_block_is_untouched() -> None:
    from backend.eva.permissions.risk_signals import assess_friction

    result = assess_friction(
        base_decision="hard_block",
        action_type="CREDENTIAL_ACCESS",
        args={"message": "anything"},
        content_args=("message",),
    )
    check(result.decision == "hard_block" and not result.escalated, "hard_block must be terminal.")


def _verify_message_prepare_stopped_claiming_verification() -> None:
    from backend.eva.tools.message_tools import message_prepare

    result = message_prepare("bob", "hello")
    check(result.get("draft_prepared") is True, "message_prepare should still report the draft was stored.")
    check(
        "verification" not in result,
        "message_prepare still returns a hardcoded verification block. Storing a "
        "dict in memory verifies nothing; this is the same laundering pattern "
        "Phase 64 removed from postconditions.py.",
    )


def _run() -> int:
    from backend.eva.tools.registry import ToolRegistry

    reg = ToolRegistry()

    _verify_declared_set_is_exactly_what_we_audited(reg)
    _verify_no_path_argument_is_declared_content(reg)
    _verify_the_false_positives_are_gone(reg)
    _verify_the_true_positives_survive(reg)
    _verify_smuggling_through_an_undeclared_argument_still_escalates()
    _verify_content_args_cannot_come_from_the_caller(reg)
    _verify_hard_block_is_untouched()
    _verify_message_prepare_stopped_claiming_verification()

    print("PASS verify_eva_phase65_content_args")
    print(
        "Phase 55's argument-aware escalation now reads TARGETS, not content. Before this phase, "
        "message.prepare with a body that merely mentioned C:/Windows/System32/... escalated "
        "allow -> override -- the heaviest tier, for writing a sentence -- because "
        "_sensitive_targets passed the entire argument value to is_sensitive_target() whenever it "
        "contained a separator. ToolSpec.content_args now names arguments the implementation "
        "provably never dereferences, and they are skipped. The declarations are pinned here and "
        "a conventional path-argument name can never be declared (statically forbidden, plus a "
        "runtime backstop), because content_args LOWERS friction and Phase 55's invariant is that "
        "it only ever raises it -- so it comes from the ToolSpec in source and is stripped from "
        "caller input exactly like confirmed/_approved. The tests that matter most are the true "
        "positives preserved, not the false positives removed: within a single tool, message is "
        "content while recipient still escalates, note is content while topic still escalates, and "
        "reason is content while label still escalates. code_debug_traceback's traceback is "
        "deliberately NOT declared -- it looks like free-form prose but debugger.py parses file "
        "paths out of it and reads them, which is exactly why the rule is 'read the implementation', "
        "not 'trust the argument's name'."
    )
    return 0


def main() -> int:
    return _run()


if __name__ == "__main__":
    raise SystemExit(main())
