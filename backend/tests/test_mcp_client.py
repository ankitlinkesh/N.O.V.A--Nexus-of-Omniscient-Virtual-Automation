"""Tests for the MCP (Model Context Protocol) client subsystem under
backend/eva/mcp/.

Default-inert behavior is the primary contract here: without EVA_MCP_ENABLED
set truthy, nothing connects to any process or network endpoint, and no new
tools appear in ToolRegistry. The "gate join" test is the important one: it
proves that MCP-discovered tools flow into a FRESH ToolRegistry() instance
(via the shared module-level cache in backend.eva.tools.registry) and that
the permission gate classifies them as confirm-class, never auto-executing.
"""

from __future__ import annotations

import os
import sys

import pytest

from backend.eva.mcp.config import McpServerConfig, load_mcp_config, mcp_enabled


@pytest.fixture(autouse=True)
def _clear_mcp_spec_cache():
    """Keep backend.eva.tools.registry._MCP_TOOL_SPECS from leaking between
    tests in this file, and between this file and the rest of the suite."""
    import backend.eva.tools.registry as registry_module

    registry_module._MCP_TOOL_SPECS.clear()
    yield
    registry_module._MCP_TOOL_SPECS.clear()


def test_mcp_enabled_false_by_default(monkeypatch):
    monkeypatch.delenv("EVA_MCP_ENABLED", raising=False)
    assert mcp_enabled() is False


@pytest.mark.parametrize("value", ["", "0", "off", "false", "No", "OFF"])
def test_mcp_enabled_falsy_values(monkeypatch, value):
    monkeypatch.setenv("EVA_MCP_ENABLED", value)
    assert mcp_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "True", "yes"])
def test_mcp_enabled_truthy_values(monkeypatch, value):
    monkeypatch.setenv("EVA_MCP_ENABLED", value)
    assert mcp_enabled() is True


def test_load_mcp_config_returns_empty_when_file_absent(monkeypatch, tmp_path):
    missing_path = tmp_path / "does_not_exist" / "mcp_servers.json"
    monkeypatch.setenv("EVA_MCP_CONFIG_PATH", str(missing_path))
    assert load_mcp_config() == []


def test_load_mcp_tools_noop_when_disabled(monkeypatch):
    from backend.eva.mcp.registration import load_mcp_tools

    monkeypatch.delenv("EVA_MCP_ENABLED", raising=False)

    result = load_mcp_tools()

    assert result == {"enabled": False, "loaded": 0}

    import backend.eva.tools.registry as registry_module

    assert registry_module._MCP_TOOL_SPECS == {}


def test_gate_join_mcp_tool_is_confirm_class_and_does_not_execute(monkeypatch):
    """The important test: an MCP-discovered tool must reach a FRESH
    ToolRegistry() via the shared spec cache, be classified confirm-class by
    the permission gate, and refuse to execute without a ledger confirmation.
    """
    import backend.eva.mcp.client as client_module
    from backend.eva.mcp.config import McpServerConfig
    from backend.eva.mcp.registration import build_mcp_tool_specs
    from backend.eva.security import tool_gate
    from backend.eva.tools.registry import ToolRegistry, register_mcp_tool_specs

    fake_tools = [
        {
            "name": "echo",
            "description": "Echo",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        }
    ]
    monkeypatch.setattr(client_module, "discover_tools", lambda server: fake_tools)
    monkeypatch.setenv("EVA_MCP_ENABLED", "1")

    server = McpServerConfig(name="ex", transport="stdio", command="x")
    specs = build_mcp_tool_specs([server])
    register_mcp_tool_specs(specs)

    registry = ToolRegistry()

    spec = registry.get("mcp.ex.echo")
    assert spec is not None, "mcp.ex.echo did not reach a freshly constructed ToolRegistry"

    assert tool_gate.classify_tool_call(spec) == "confirm", "MCP tools must be confirm-class, never allow-class"

    result = registry.run("mcp.ex.echo", text="hi")

    assert result.get("requires_confirmation") is True, f"MCP tool executed without confirmation: {result}"
    assert isinstance(result.get("pending_id"), str) and result["pending_id"], f"missing pending_id: {result}"
    assert result.get("ok") is False


def test_default_off_registers_no_tools(monkeypatch):
    """Sanity: with the flag unset, build_mcp_tool_specs is never even
    reached by load_mcp_tools, so the registry's tool count is unchanged."""
    from backend.eva.mcp.registration import load_mcp_tools
    from backend.eva.tools.registry import ToolRegistry

    monkeypatch.delenv("EVA_MCP_ENABLED", raising=False)

    before = ToolRegistry()
    before_count = len(before.list_tools())

    load_mcp_tools()

    after = ToolRegistry()
    after_count = len(after.list_tools())

    assert before_count == after_count
    assert after.get("mcp.ex.echo") is None


@pytest.mark.skipif(not os.environ.get("EVA_RUN_MCP_LIVE"), reason="Set EVA_RUN_MCP_LIVE=1 to run the live example MCP server test")
def test_live_example_server_discover_and_call():
    """Opt-in live test: spawns the real example_server.py over stdio via the
    installed mcp SDK, discovers its tools, and calls one for real."""
    from backend.eva.mcp import client
    from backend.eva.mcp.config import McpServerConfig

    server = McpServerConfig(
        name="example",
        transport="stdio",
        command=sys.executable,
        args=("-m", "backend.eva.mcp.example_server"),
    )

    discovered = client.discover_tools(server)
    names = {tool["name"] for tool in discovered}
    assert "echo" in names
    assert "add" in names

    result = client.call_tool(server, "add", {"a": 2, "b": 3})
    assert result.get("ok") is True, f"live add call failed: {result}"
    assert "5" in result.get("content", ""), f"unexpected content: {result}"
