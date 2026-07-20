"""Executable spec for per-role tool containment (Phase 72).

The security-facing, end-to-end invariants live in
scripts/verify_eva_phase72_role_policy.py (GREEN is not a bypass, ORANGE
survives Phase 42, role kwargs carry no authority, the refusal does not echo
arguments). This file pins the smaller units underneath them, so a regression
names the specific rule it broke rather than only failing an integration check.

The through-line: every default here points at RED. A role declares what it may
use and nothing else, so the failure mode of forgetting to declare something is
a refusal, never an unnoticed grant. That is the Phase 51 lesson (a missing
`action_type` silently meaning auto-allow) applied one layer up.
"""

from __future__ import annotations

import pytest

from eva.agents.role_context import active_role, active_roles, role_scope
from eva.agents.role_policy import (
    ROLE_POLICIES,
    RolePolicy,
    RoleTier,
    describe_role,
    effective_tier,
    escalate_one_step,
    known_roles,
    tier_for,
)


class TestFailClosed:
    """Anything not explicitly granted must be refused."""

    def test_undeclared_tool_is_red(self) -> None:
        policy = RolePolicy(name="probe", description="", green=frozenset({"a"}), orange=frozenset({"b"}))
        assert policy.tier_for("a") is RoleTier.GREEN
        assert policy.tier_for("b") is RoleTier.ORANGE
        # The whole design rests on this line: registering a new tool must not
        # silently make it available to every existing role.
        assert policy.tier_for("something_new") is RoleTier.RED

    def test_unknown_role_is_red_on_everything(self) -> None:
        """A typo'd or injected role name must never widen access."""
        for tool in ("status", "screen.click", "file.delete"):
            assert tier_for("desktop-please", tool) is RoleTier.RED
            assert tier_for("", tool) is RoleTier.RED
            assert tier_for(None, tool) is RoleTier.RED

    def test_no_role_declares_file_delete(self) -> None:
        """Deletion is never delegated. The human deletes from the console."""
        for role in known_roles():
            assert tier_for(role, "file.delete") is RoleTier.RED


class TestContainmentIsReal:
    """The policy must actually separate roles, not merely look like it does."""

    def test_research_cannot_reach_an_actuator(self) -> None:
        """The core containment claim: a role reading untrusted web content
        cannot drive the screen, write files, or send messages -- so a poisoned
        page has no actuator to reach even if it convinces the model."""
        for tool in (
            "screen.click",
            "screen.type_text",
            "screen.submit_form",
            "file.write_text",
            "file.delete",
            "message.send_via_ui",
            "web.click",
            "system_power",
        ):
            assert tier_for("research", tool) is RoleTier.RED, tool

    def test_desktop_cannot_reach_the_network(self) -> None:
        """The mirror: a role that can see the screen cannot exfiltrate it."""
        for tool in ("web.open_url", "web_search", "research_web", "message.send_via_ui", "browser_open_url"):
            assert tier_for("desktop", tool) is RoleTier.RED, tool

    def test_code_role_cannot_write(self) -> None:
        for tool in ("file.write_text", "file.copy", "file.move", "file.delete"):
            assert tier_for("code", tool) is RoleTier.RED, tool

    def test_roles_do_not_all_collapse_to_the_same_grant(self) -> None:
        """If every role allowed the same set, the layer would be decoration."""
        grants = {name: (p.green | p.orange) for name, p in ROLE_POLICIES.items()}
        assert grants["research"] != grants["desktop"]
        assert not (grants["research"] & {"screen.click", "file.write_text"})
        assert "screen.click" in grants["desktop"]


class TestEscalationArithmetic:
    """ORANGE may only ever raise friction."""

    @pytest.mark.parametrize(
        "decision,expected",
        [("allow", "confirm"), ("confirm", "override"), ("override", "override")],
    )
    def test_raises_one_step(self, decision: str, expected: str) -> None:
        assert escalate_one_step(decision) == expected

    def test_hard_block_is_terminal(self) -> None:
        """Phase 55 established that a blocked action is never reachable by
        escalation arithmetic; this layer inherits that."""
        assert escalate_one_step("hard_block") == "hard_block"

    def test_never_lowers(self) -> None:
        order = ["allow", "confirm", "override"]
        for decision in order:
            assert order.index(escalate_one_step(decision)) >= order.index(decision)

    def test_unknown_decision_is_passed_through_unchanged(self) -> None:
        """Inventing a tier for an unrecognized decision would be worse than
        leaving it alone -- the gate owns that vocabulary, not this module."""
        assert escalate_one_step("something_else") == "something_else"


class TestRoleScope:
    def test_sets_and_clears(self) -> None:
        assert active_role() is None
        with role_scope("research"):
            assert active_role() == "research"
        assert active_role() is None

    def test_does_not_leak_after_exception(self) -> None:
        """A leaked role would silently restrict later top-level calls. That
        fails safe, but it is a confusing state to debug, so it is pinned."""
        with pytest.raises(RuntimeError):
            with role_scope("research"):
                raise RuntimeError("sub-task failure")
        assert active_role() is None

    def test_nesting_accumulates_rather_than_replaces(self) -> None:
        """Every enclosing role stays in force.

        If a nested scope REPLACED the outer one, a research sub-task could
        open a `desktop` scope and gain exactly the screen access its own role
        exists to deny. Nesting is therefore an intersection.
        """
        with role_scope("research"):
            assert active_roles() == ("research",)
            with role_scope("desktop"):
                assert active_roles() == ("research", "desktop")
                # active_role() reports the innermost for messages only --
                # authorization must never read it alone.
                assert active_role() == "desktop"
            assert active_roles() == ("research",)
        assert active_roles() == ()

    def test_none_role_does_not_clear_the_stack(self) -> None:
        """A no-op scope must not silently drop the containment above it."""
        with role_scope("research"):
            with role_scope(None):
                assert active_roles() == ("research",)


class TestNestingOnlyNarrows:
    """A delegated sub-task may subtract capability, never add it."""

    def test_inner_role_cannot_regain_what_outer_denies(self) -> None:
        """The containment escape: research -> desktop must NOT yield screen access."""
        assert effective_tier(("research", "desktop"), "screen.click") is RoleTier.RED
        assert effective_tier(("desktop",), "screen.click") is RoleTier.GREEN

    def test_inner_role_can_subtract(self) -> None:
        assert effective_tier(("desktop", "research"), "screen.click") is RoleTier.RED

    def test_most_restrictive_wins_for_orange(self) -> None:
        # file.write_text is ORANGE for `file`, RED for `code`.
        assert effective_tier(("file",), "file.write_text") is RoleTier.ORANGE
        assert effective_tier(("file", "code"), "file.write_text") is RoleTier.RED

    def test_empty_stack_is_not_a_tier(self) -> None:
        """No active role is distinct from GREEN: one means this layer does not
        apply, the other is a decision that a role may proceed. Collapsing them
        would make a missing stack look like an affirmative grant."""
        assert effective_tier((), "screen.click") is None

    def test_shared_grant_survives_nesting(self) -> None:
        """Intersection must not deny something BOTH roles allow."""
        assert effective_tier(("research", "code"), "workspace_read_file") is RoleTier.GREEN


class TestPolicyHygiene:
    def test_no_tool_is_both_green_and_orange(self) -> None:
        for name, policy in ROLE_POLICIES.items():
            assert not (policy.green & policy.orange), f"{name} declares a tool twice"

    def test_every_role_has_a_description(self) -> None:
        for name, policy in ROLE_POLICIES.items():
            assert policy.description.strip(), f"{name} has no description"
            assert policy.name == name, f"{name} disagrees with its own key"

    def test_describe_role_reports_unknown_roles_honestly(self) -> None:
        text = describe_role("not-a-role")
        assert "Unknown role" in text
        assert "research" in text  # lists what is actually available

    def test_describe_role_lists_grants(self) -> None:
        text = describe_role("file")
        assert "file.list_dir" in text
        assert "confirmation" in text.lower()
        # file.delete is RED, so it must not appear as a grant.
        assert "file.delete" not in text
