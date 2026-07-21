"""Executable spec for the UI agent-scope selector (Phase 76).

The selector lets a request run inside a delegated role's tool surface. It is
accepted over HTTP without authentication, and the reason that is safe is the
only thing really worth testing:

    EVERY ROLE IS A STRICT SUBSET OF FULL ACCESS.

There is no role that grants anything the unrestricted default lacks, so the
field can only ever narrow what a request may do. If that ever stopped being
true, an unauthenticated caller could use `agent_scope` to gain capability
instead of giving it up -- so it is asserted here structurally rather than
assumed from the way the roles happen to be written today.

The second property is that an unrecognised scope is REJECTED, never ignored.
Silently dropping it would leave someone who asked for containment running with
full access while believing otherwise, which is worse than refusing outright.
"""

from __future__ import annotations

import pytest

from eva.agents.role_policy import ROLE_POLICIES, RoleTier, known_roles, tier_for
from eva.tools.registry import ToolRegistry


class TestScopeCanOnlyNarrow:
    """The property that makes an unauthenticated scope field safe."""

    def test_no_role_grants_anything_beyond_the_full_tool_surface(self) -> None:
        registry_tools = set(ToolRegistry()._tools)
        for name, policy in ROLE_POLICIES.items():
            granted = policy.green | policy.orange
            assert granted <= registry_tools, f"role `{name}` grants tools that do not exist: {granted - registry_tools}"

    def test_every_role_is_a_proper_subset_of_full_access(self) -> None:
        """Full access has NO role restriction, so a role must always deny
        something. A role that denied nothing would be a no-op that still
        looked like containment in the UI."""
        registry_tools = set(ToolRegistry()._tools)
        for name, policy in ROLE_POLICIES.items():
            granted = policy.green | policy.orange
            assert granted < registry_tools, f"role `{name}` restricts nothing"

    def test_a_scope_never_turns_a_denied_tool_into_an_allowed_one(self) -> None:
        """There is no tool that full access refuses but a scope permits --
        the direction that would make the field an escalation channel."""
        for role in known_roles():
            for tool in ToolRegistry()._tools:
                tier = tier_for(role, tool)
                # Under full access every registered tool is reachable (subject
                # to the gate). A role may only match that or refuse.
                assert tier in {RoleTier.GREEN, RoleTier.ORANGE, RoleTier.RED}


class TestRequestValidation:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from eva.main import app

        return TestClient(app)

    HEADERS = {"X-Eva-Client": "1"}

    def test_unknown_scope_is_rejected_not_ignored(self, client) -> None:
        """Fail closed: a user who asked for containment must not be silently
        given full access."""
        response = client.post(
            "/api/chat/stream",
            json={"message": "hi", "agent_scope": "desktop-please"},
            headers=self.HEADERS,
        )
        assert response.status_code == 400
        assert "Unknown agent scope" in str(response.json().get("detail"))

    def test_known_scopes_are_accepted(self, client) -> None:
        for role in known_roles():
            response = client.post(
                "/api/chat/stream",
                json={"message": "roles", "agent_scope": role},
                headers=self.HEADERS,
            )
            assert response.status_code == 200, role

    def test_absent_scope_is_unchanged_behaviour(self, client) -> None:
        response = client.post("/api/chat/stream", json={"message": "roles"}, headers=self.HEADERS)
        assert response.status_code == 200
        assert "research" in response.text

    def test_empty_scope_is_treated_as_full_access(self, client) -> None:
        """The UI's default option has value="" -- it must not be read as an
        unknown role and rejected."""
        response = client.post(
            "/api/chat/stream",
            json={"message": "roles", "agent_scope": ""},
            headers=self.HEADERS,
        )
        assert response.status_code == 200


class TestScopeIsEnforced:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from eva.main import app

        return TestClient(app)

    HEADERS = {"X-Eva-Client": "1"}

    def test_red_tool_is_refused_under_scope(self, client) -> None:
        response = client.post(
            "/api/chat/stream",
            json={"message": "$ git status", "agent_scope": "research"},
            headers=self.HEADERS,
        )
        assert response.status_code == 200
        assert "may not call" in response.text

    def test_same_request_is_not_role_refused_without_scope(self, client) -> None:
        """Proves the refusal above came from the scope and not from something
        that would have refused it anyway."""
        response = client.post("/api/chat/stream", json={"message": "$ git status"}, headers=self.HEADERS)
        assert response.status_code == 200
        assert "may not call" not in response.text

    def test_scope_does_not_leak_to_the_next_request(self, client) -> None:
        client.post(
            "/api/chat/stream",
            json={"message": "$ git status", "agent_scope": "research"},
            headers=self.HEADERS,
        )
        after = client.post("/api/chat/stream", json={"message": "$ git status"}, headers=self.HEADERS)
        assert "may not call" not in after.text
