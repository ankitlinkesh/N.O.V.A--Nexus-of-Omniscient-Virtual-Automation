"""Characterization test for the exact-match status-command table.

Strategy that avoids circularity: compare the live router
(maybe_handle_fast_command) against the new table (dispatch_status_command)
for every command. Run BEFORE the fast_commands.py blocks are replaced, this
proves the table reproduces the original inline-block behavior exactly; run
AFTER, it confirms the router is wired to the table. Either way, a wrong
mapping in the table makes the router and table disagree and fails here.
"""
from __future__ import annotations

import pytest

from backend.eva.core.fast_commands import maybe_handle_fast_command
from backend.eva.core.fast_command_table import STATUS_COMMANDS, dispatch_status_command
from backend.eva.tools.registry import ToolRegistry


@pytest.mark.parametrize("command", sorted(STATUS_COMMANDS))
def test_router_matches_table(command):
    routed = maybe_handle_fast_command(command, ToolRegistry(), {})
    assert routed is not None, f"router did not handle {command!r}"
    reply, source = routed
    assert source == "fast-command", f"{command!r} routed to unexpected source {source!r}"

    expected = dispatch_status_command(command)
    assert expected is not None, f"table did not resolve {command!r}"
    assert reply == expected, f"router reply for {command!r} differs from table dispatch"


def test_table_covers_only_known_commands():
    # Every table entry resolves to a callable formatter that returns text.
    for command in STATUS_COMMANDS:
        out = dispatch_status_command(command)
        assert isinstance(out, str) and out.strip(), f"empty/invalid output for {command!r}"


def test_unknown_command_returns_none():
    assert dispatch_status_command("eva definitely not a real command") is None
