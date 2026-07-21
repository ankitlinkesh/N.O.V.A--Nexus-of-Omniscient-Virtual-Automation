"""Argument-aware risk escalation — the mirror of Phase 42 (Phase 55).

Phase 42 learned to *remove* friction (auto-allow an action the user has approved
many times) and hemmed that in on every side, because removing friction is
dangerous. This is the other half: *adding* friction, which is always safe, so it
is unconditional.

The gap it closes is the one the whole project keeps re-learning: **the gate
classifies per-TOOL, blind to the ARGUMENTS.** ``file.list_dir`` is allow-class,
so listing ``C:\\Windows\\System32`` or ``~/.ssh`` auto-runs and quietly
enumerates a sensitive directory; ``file.copy`` classifies a copy into a system
folder exactly like a copy into a scratch dir. The static class cannot see where
the action points. This layer looks at the call's actual arguments and, when a
target is sensitive, raises the friction the static class deserves.

Two hard invariants make it safe by construction:

  * **It can only ever escalate.** allow -> confirm -> override, never the
    reverse, and it never touches ``hard_block`` (a terminal policy decision).
    A bug here can only ask for *more* confirmation, never less — it fails safe.
  * **It is proportionate.** A *reading* action on a sensitive target escalates
    to ``confirm`` (ask first); a *mutating* action escalates to ``override``
    (the strongest interactive friction). Reading your secrets folder should ask;
    writing into a system directory should demand the override phrase.

Escalation strictly dominates the Phase 42 trust de-escalation: an action the
risk layer raises is never then auto-allowed for having been approved before.
That dominance is not purely from ordering — a sensitive-target READ escalates
allow->confirm and lands where de-escalation can still see it. It holds because
the reading types that stop at ``confirm`` are absent from
``trust_policy.TRUST_ELIGIBLE_ACTION_TYPES`` (pinned by verify_eva_phase78), so
only ``MCP_TOOL_CALL`` is de-escalatable and that escalates confirm->override
(off confirm) on a sensitive target.

Pure and deterministic: string/path reasoning only, no filesystem access (so a
``..`` traversal toward a system dir is caught by the literal path text, not by
resolving it on disk). The sensitive-marker list is curated, not exhaustive — a
miss is merely "no extra confirmation", never an unsafe allow.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..security.action_types import ActionType

# Ordered friction levels. Escalation only ever moves a decision to a higher
# index; hard_block is terminal and never produced or altered here.
_FRICTION_ORDER = {"allow": 0, "confirm": 1, "override": 2, "hard_block": 3}
_BY_ORDER = {value: key for key, value in _FRICTION_ORDER.items()}

# Action types whose call MUTATES its target (or reaches the network) — a
# sensitive target here earns the strongest interactive friction.
_MUTATING_ACTION_TYPES = frozenset({
    ActionType.DESTRUCTIVE_FILE_ACTION.value,
    ActionType.SYSTEM_CHANGE.value,
    ActionType.NETWORK_ACTION.value,
    ActionType.SAFE_LOCAL_UI.value,
})

# Action types that READ their target. A sensitive target here earns a "confirm".
_READING_ACTION_TYPES = frozenset({
    ActionType.SAFE_LOCAL_READ.value,
    ActionType.PRIVACY_FILE_READ.value,
})

_TARGET_ACTING_ACTION_TYPES = _MUTATING_ACTION_TYPES | _READING_ACTION_TYPES

# Argument keys that conventionally name a filesystem target. Any other string
# argument is still scanned, but only if it *looks* like a path (has a separator).
_PATH_ARG_KEYS = frozenset({
    "path", "source", "src", "destination", "dst", "target",
    "file", "filename", "dir", "directory", "folder", "to", "from",
})

# Decisive substrings marking a path as sensitive. Matched case-insensitively
# against a separator-normalized (forward-slash, lowercased) path, so both
# ``C:\Windows\System32`` and ``/windows/system32`` hit, and a ``..`` traversal
# toward one still contains the literal marker. Broad on purpose: this only ADDS
# friction, so over-inclusion is safe and under-inclusion merely misses.
_SENSITIVE_MARKERS = (
    # Windows system + program roots
    "system32", "/windows", "program files", "programdata",
    # POSIX system roots (defensive; the app is Windows-first)
    "/etc/", "/root/", "/boot/", "/usr/bin", "/usr/sbin", "/system/library",
    # keys / credentials / secret stores
    "/.ssh", "id_rsa", "id_ed25519", "known_hosts", "/.aws", "/.gnupg", "/.kube",
    ".env", "credentials", "secrets", "id_dsa",
    # browser + OS credential databases
    "login data", "cookies.sqlite", "key4.db", "logins.json",
    # NOVA's own trust + memory stores (tampering with these is high-stakes)
    "override_events.sqlite3", "eva.sqlite3",
)


@dataclass(frozen=True)
class FrictionAssessment:
    """The gate decision after argument-aware risk escalation."""

    decision: str
    escalated: bool
    signals: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {"decision": self.decision, "escalated": self.escalated, "signals": list(self.signals), "reason": self.reason}


def is_sensitive_target(value: object) -> bool:
    """True if ``value`` names a sensitive filesystem location. Pure, no I/O."""
    text = str(value or "").strip().lower().replace("\\", "/")
    if not text:
        return False
    return any(marker in text for marker in _SENSITIVE_MARKERS)


def _sensitive_targets(args: dict[str, object] | None, content_args: frozenset[str] = frozenset()) -> list[str]:
    """Every argument value that names a sensitive target.

    Scans conventional path arguments by name, plus any other string value that
    looks like a path (contains a separator) — so a sensitive path smuggled
    through an oddly named argument is still caught, without flagging prose.

    Phase 65: keys listed in ``content_args`` are skipped entirely. Those are
    argument names the tool's *implementation* provably never dereferences
    (e.g. a message body that only gets stored/logged) — scanning them was a
    category error: it tested a value the tool never acts on, so a message
    that merely MENTIONS a system path (prose) tripped the same escalation as
    an action that actually TARGETS one.
    """
    hits: list[str] = []
    for key, value in (args or {}).items():
        # Defense in depth: a conventional path-argument NAME is never exempt,
        # even if a ToolSpec mistakenly declared it as content (the audit
        # verifier also forbids this statically; this is the runtime backstop).
        if str(key) in content_args and str(key).lower() not in _PATH_ARG_KEYS:
            continue
        if not isinstance(value, str):
            continue
        looks_pathy = str(key).lower() in _PATH_ARG_KEYS or "/" in value or "\\" in value
        if looks_pathy and is_sensitive_target(value):
            hits.append(value)
    return hits


def _sensitive_floor(action_type: str, base_decision: str) -> str | None:
    """The minimum friction a sensitive target imposes, or None if this action
    does not act on a target we reason about."""
    if action_type in _MUTATING_ACTION_TYPES:
        return "override"
    if action_type in _READING_ACTION_TYPES:
        return "confirm"
    # Unknown type but the tool is already privileged: be conservative.
    if base_decision in {"confirm", "override"}:
        return "override"
    return None


def assess_friction(
    *,
    base_decision: str,
    action_type: str,
    args: dict[str, object] | None,
    content_args: tuple[str, ...] = (),
) -> FrictionAssessment:
    """Escalate ``base_decision`` when the call's arguments reveal a risk the
    static tool class cannot see. Never lowers friction; never touches
    ``hard_block``.

    ``content_args`` (Phase 65) names argument keys the tool provably never
    dereferences (e.g. a message body it only stores) -- those are excluded
    from the sensitive-target scan so prose that merely MENTIONS a path does
    not get treated as if it targeted one. It must come from the ToolSpec in
    source (see registry.py::ToolRegistry.run, which passes
    ``spec.content_args`` and strips any caller-supplied ``content_args`` kwarg
    first) -- never from the call's own arguments, or it would be a
    self-authorization channel that LOWERS friction, which nothing in this
    module is allowed to do based on caller input.
    """
    base = base_decision if base_decision in _FRICTION_ORDER else "confirm"
    if base == "hard_block":
        return FrictionAssessment(base, False, (), "hard_block is terminal; no escalation.")

    action = str(action_type or "")
    level = _FRICTION_ORDER[base]
    signals: list[str] = []
    content_keys = frozenset(content_args or ())

    if action in _TARGET_ACTING_ACTION_TYPES or base in {"confirm", "override"}:
        hits = _sensitive_targets(args, content_keys)
        if hits:
            floor = _sensitive_floor(action, base)
            if floor is not None:
                level = max(level, _FRICTION_ORDER[floor])
                signals.append("sensitive_target")

    final = _BY_ORDER[level]
    escalated = _FRICTION_ORDER[final] > _FRICTION_ORDER[base]
    if not signals:
        return FrictionAssessment(base, False, (), "No risk signals; friction unchanged.")
    verb = "escalated" if escalated else "already at or above"
    reason = f"{', '.join(signals)}: {verb} friction {base} -> {final}."
    return FrictionAssessment(final, escalated, tuple(signals), reason)


__all__ = ["FrictionAssessment", "assess_friction", "is_sensitive_target"]
