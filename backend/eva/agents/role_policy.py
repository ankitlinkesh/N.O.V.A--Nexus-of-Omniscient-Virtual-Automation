"""Per-role tool policy (Phase 72).

The permission gate classifies per TOOL, globally: `file.write_text` costs the
same no matter who asks. That is the right default for a single actor, but it
cannot express "a research sub-task may read the web and must never touch the
screen" -- which is exactly the containment a delegated sub-agent needs, because
a research role reads UNTRUSTED CONTENT and a page can ask it to do anything.

This module adds the missing dimension: role x tool -> tier.

    GREEN   this role may attempt the tool. The gate still classifies it
            normally -- an override-class tool stays override-class.
    ORANGE  this role may attempt it, but friction is raised one step
            (allow -> confirm -> override), regardless of trust calibration.
    RED     this role may not call it at all. Refused before the gate is even
            consulted, and surfaced to the user.

THE INVARIANT, inherited from Phase 55 and the reason this is safe to apply
unconditionally: a role tier can ONLY ADD friction, never remove it. GREEN means
"not restricted by role", NOT "pre-approved". If a role could mark a tool green
and skip confirmation, this file would be a self-authorization channel exactly
like the `confirmed`/`_approved`/`content_args` kwargs that `registry.run`
strips -- so GREEN deliberately has no power to lower anything.

FAIL-CLOSED BY CONSTRUCTION: a role declares only what it MAY use; everything
else is RED. Registering a new tool therefore makes it unavailable to every
existing role until someone decides otherwise, rather than silently becoming
available to all of them. This is the Phase 51 lesson (a missing `action_type`
used to mean auto-allow) applied at the role layer, but by construction rather
than by a build check.

RED IS FIXED IN SOURCE and is not runtime-overridable. There is no "approve
this once" path, because the whole point is that untrusted content must not be
able to ASK for one -- a request to lift a restriction is precisely what an
injected page would produce. The escape hatch is the human running the command
themselves from the typed console, which is already this project's trust
boundary for rule creation (Phase 54) and form filling (Phase 58).

Tool names here are cross-checked against the live registry by
scripts/verify_eva_phase72_role_policy.py. A typo must not silently degrade to
RED: a misspelled GREEN entry would leave the intended tool denied while the
policy still looked permissive.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class RoleTier(StrEnum):
    GREEN = "green"
    ORANGE = "orange"
    RED = "red"


@dataclass(frozen=True)
class RolePolicy:
    """What one delegated role may do. Anything unlisted is RED."""

    name: str
    description: str
    green: frozenset[str]
    orange: frozenset[str] = frozenset()

    def tier_for(self, tool: str) -> RoleTier:
        if tool in self.green:
            return RoleTier.GREEN
        if tool in self.orange:
            return RoleTier.ORANGE
        return RoleTier.RED


_WORKSPACE_READS = {
    "workspace_list_files",
    "workspace_project_summary",
    "workspace_read_file",
    "workspace_search",
    "workspace_status",
    "workspace_summarize_file",
}

ROLE_POLICIES: dict[str, RolePolicy] = {
    "research": RolePolicy(
        name="research",
        description="Gathers and summarizes information. Reads the web and the workspace; never drives the screen, writes files, or sends messages.",
        green=frozenset(
            {
                "research_recall",
                "research_status",
                "research_summary",
                "research_web",
                "web_search",
                "browser_status",
                "status",
                "system_status",
            }
            | _WORKSPACE_READS
        ),
        # Writes into research memory: permitted, but always confirmed, because
        # this role's input is untrusted page content.
        orange=frozenset({"research_save_note", "research_start_topic", "browser_save_page_to_research"}),
    ),
    "desktop": RolePolicy(
        name="desktop",
        description="Drives the local GUI: observes the screen, clicks, types, manages windows. Never reaches the network or the file system.",
        green=frozenset(
            {
                "screen.observe",
                "screen.click",
                "screen.press",
                "screen.hotkey",
                "screen.scroll",
                "screen.type_text",
                "screen.wait",
                "window_active",
                "window_list",
                "window_focus",
                "window_maximize",
                "window_minimize",
                "window_close_safe",
                "app.focus",
                "open_app",
                "open_folder",
                "desktop_observe",
                "capture_screen",
                "analyze_screen",
                "verify_last_action",
                "status",
                "system_status",
            }
        ),
        # submit_form commits a whole staged form; close_app can discard unsaved
        # work (the open Phase 73 debt) -- both stay confirmed for a sub-task.
        orange=frozenset({"screen.submit_form", "close_app"}),
    ),
    "file": RolePolicy(
        name="file",
        description="Reads and organizes files in the workspace. Can write, copy and move under confirmation; can never delete.",
        green=frozenset({"file.list_dir", "open_folder", "status"} | _WORKSPACE_READS),
        orange=frozenset({"file.write_text", "file.copy", "file.move"}),
        # file.delete is deliberately absent -> RED. A delegated sub-task never
        # deletes; the human deletes from the console.
    ),
    "code": RolePolicy(
        name="code",
        description="Reads and explains the codebase. Never edits, runs, or executes anything.",
        green=frozenset(
            {
                "code_debug_traceback",
                "code_explain_feature",
                "code_find_symbol",
                "code_plan_change",
                "code_project_map",
                "code_search",
                "code_status",
                "status",
            }
            | _WORKSPACE_READS
        ),
        orange=frozenset({"code_reindex"}),
    ),
    "media": RolePolicy(
        name="media",
        description="Controls music and media playback only.",
        green=frozenset(
            {
                "media_control",
                "media_key",
                "spotify_next",
                "spotify_now_playing_status",
                "spotify_pause",
                "spotify_play_desktop",
                "spotify_play_query",
                "spotify_previous",
                "spotify_restart_current",
                "spotify_search",
                "spotify_search_desktop",
                "spotify_status",
                "status",
            }
        ),
    ),
}


# One step up the friction ladder. `hard_block` is deliberately absent: like
# Phase 55, this layer never touches it (there is nothing above it, and a
# blocked action must not be reachable by any escalation arithmetic).
_ONE_STEP_UP = {"allow": "confirm", "confirm": "override", "override": "override"}


def escalate_one_step(decision: str) -> str:
    """Raise friction one tier. Never lowers, never alters `hard_block`."""
    return _ONE_STEP_UP.get(decision, decision)


def known_roles() -> tuple[str, ...]:
    return tuple(sorted(ROLE_POLICIES))


def tier_for(role: str | None, tool: str) -> RoleTier:
    """Tier for a (role, tool) pair.

    An unknown role is RED on everything: a typo'd or injected role name must
    not silently widen access. Callers with NO active role are not routed here
    at all -- see role_context.active_role() -- so ordinary console and planner
    use is unaffected by this module.
    """
    policy = ROLE_POLICIES.get(str(role or ""))
    if policy is None:
        return RoleTier.RED
    return policy.tier_for(tool)


# Most restrictive first. Used to intersect a stack of nested roles.
_RESTRICTIVENESS = {RoleTier.RED: 2, RoleTier.ORANGE: 1, RoleTier.GREEN: 0}


def effective_tier(roles: Sequence[str], tool: str) -> RoleTier | None:
    """The tier for a tool under EVERY role currently in force.

    Returns the most restrictive tier across the stack, so a nested delegation
    can only ever subtract capability. `None` means no role is active at all,
    which is the top-level case where this layer does not apply -- deliberately
    distinct from GREEN, which is an active decision that a role may proceed.

    A research sub-task that opens a `desktop` scope must NOT thereby gain
    screen access; intersecting rather than replacing is what prevents that.
    """
    if not roles:
        return None
    return max((tier_for(role, tool) for role in roles), key=lambda tier: _RESTRICTIVENESS[tier])


def describe_role(role: str) -> str:
    policy = ROLE_POLICIES.get(role)
    if policy is None:
        return f"Unknown role `{role}`. Known roles: {', '.join(known_roles())}."
    lines = [
        f"Role: {policy.name}",
        policy.description,
        "",
        f"Allowed ({len(policy.green)}): {', '.join(sorted(policy.green))}",
    ]
    if policy.orange:
        lines.append(f"Allowed with confirmation ({len(policy.orange)}): {', '.join(sorted(policy.orange))}")
    lines.append("Everything else is refused for this role.")
    return "\n".join(lines)
