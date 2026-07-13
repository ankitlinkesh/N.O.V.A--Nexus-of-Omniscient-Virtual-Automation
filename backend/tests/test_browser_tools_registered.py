"""Registry wiring for the real Playwright DOM-automation driver (Phase 32).

The driver (backend.eva.browser_automation.playwright_driver) already exists
and is disabled unless EVA_V2_PLAYWRIGHT_ENABLED=true. These tests only check
that the 7 web.* tools are registered with the correct gate class -- they must
never set EVA_V2_PLAYWRIGHT_ENABLED, so no real browser is ever launched here.
"""
from __future__ import annotations

from backend.eva.tools.registry import ToolRegistry


ALL_WEB_TOOLS = [
    "web.open_url",
    "web.snapshot",
    "web.locate",
    "web.verify",
    "web.click",
    "web.type",
    "web.close",
]

ALLOW_CLASS_TOOLS = ["web.open_url", "web.snapshot", "web.locate", "web.verify"]


def test_all_web_tools_are_registered():
    registry = ToolRegistry()
    for name in ALL_WEB_TOOLS:
        assert registry.get(name) is not None, f"{name} is not registered in ToolRegistry"


def test_web_click_is_confirm_class_and_gated():
    registry = ToolRegistry()
    result = registry.run("web.click", selector="a")
    assert result.get("requires_confirmation") is True, f"unexpected result: {result}"
    assert result.get("risk_class") == "confirm", f"unexpected result: {result}"
    assert result.get("pending_id"), f"gate result missing pending_id: {result}"


def test_web_type_is_confirm_class_and_gated():
    registry = ToolRegistry()
    result = registry.run("web.type", selector="input", text_value="hello")
    assert result.get("requires_confirmation") is True, f"unexpected result: {result}"
    assert result.get("risk_class") == "confirm", f"unexpected result: {result}"
    assert result.get("pending_id"), f"gate result missing pending_id: {result}"


def test_read_and_nav_web_tools_are_allow_class():
    from backend.eva.security import tool_gate

    registry = ToolRegistry()
    for name in ALLOW_CLASS_TOOLS:
        spec = registry.get(name)
        assert spec is not None, f"{name} is not registered in ToolRegistry"
        assert tool_gate.classify_tool_call(spec) == "allow", f"{name} should be allow-class"


def test_name_argument_does_not_collide_with_run_signature():
    """A tool arg literally called 'name' (web.* locator hint) must reach the
    handler, not collide with ToolRegistry.run(name, ...). Regression for the
    positional-only `name` parameter; caught only by driving the real call."""
    registry = ToolRegistry()
    # allow-class: dispatches to the handler (returns a dict, disabled w/o flag).
    located = registry.run("web.locate", role="link", name="Some Link")
    assert isinstance(located, dict)
    # confirm-class: name= is carried into the gated pending without colliding.
    gated = registry.run("web.click", name="Some Link")
    assert gated.get("requires_confirmation") is True
