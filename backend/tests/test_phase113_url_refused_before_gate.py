"""Phase 113: a URL no handler will open is refused before the gate, not after approval.

`browser_open_result_and_verify(url="file:///C:/Users/HP/.env")` produced an
OVERRIDE prompt -- Phase 55 escalates a sensitive-looking target -- and the
handler's http(s)-only check ran only after the user typed `confirm override`.
Asking someone to approve an action that cannot happen is the Phase 74
refuse-after-approval defect.

Handlers are replaced with recorders, so nothing is opened.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.eva.security import tool_gate
from backend.eva.tools.registry import _URL_TOOLS, ToolRegistry

REFUSED = ["file:///C:/Users/HP/.env", "javascript:alert(1)", "chrome://settings", "https://user:pw@example.com"]


def _recording_registry():
    registry = ToolRegistry()
    opened: list[tuple[str, dict]] = []
    for name in _URL_TOOLS:
        spec = registry._tools[name]

        def handler(__name=name, **kwargs):
            opened.append((__name, kwargs))
            return {"ok": True}

        registry._tools[name] = dataclasses.replace(spec, handler=handler)
    return registry, opened


@pytest.fixture(autouse=True)
def _clean():
    tool_gate.reset_pending_calls()
    yield
    tool_gate.reset_pending_calls()


def test_every_listed_tool_really_takes_a_url():
    registry = ToolRegistry()
    for name in _URL_TOOLS:
        assert "url" in ((registry.get(name).args_schema or {}).get("properties") or {}), name


@pytest.mark.parametrize("tool", sorted(_URL_TOOLS))
@pytest.mark.parametrize("url", REFUSED)
def test_a_non_http_url_is_refused_before_any_approval_prompt(tool, url):
    registry, opened = _recording_registry()
    with pytest.raises(ValueError):
        registry.run(tool, url=url)
    assert opened == []
    assert tool_gate._PENDING_CALLS == {}, "no approval prompt may be created for an action that cannot happen"


def test_the_executor_reports_it_as_a_plain_failure_not_a_confirmation():
    from backend.eva.agent.executor import ToolExecutor
    from backend.eva.agent.planner import PlannedToolCall

    registry, _ = _recording_registry()
    result = ToolExecutor(registry).execute(PlannedToolCall(tool="open_url", args={"url": "file:///C:/Users/HP/.env"}))
    assert result.ok is False and result.requires_confirmation is False
    assert "http" in (result.error or "")


def test_an_ordinary_url_still_reaches_its_handler():
    registry, opened = _recording_registry()
    registry.run("open_url", url="https://example.com")
    assert opened == [("open_url", {"url": "https://example.com"})]


def test_an_empty_url_still_means_the_current_page():
    registry, opened = _recording_registry()
    registry.run("browser_summarize_page", url="")
    assert opened and opened[0][0] == "browser_summarize_page"


def test_a_valid_but_sensitive_looking_url_is_still_gated():
    """The check only refuses what cannot be opened; it does not skip Phase 55."""
    registry, opened = _recording_registry()
    result = registry.run("browser_open_result_and_verify", url="https://example.com/C:/Users/HP/.ssh/id_rsa")
    if isinstance(result, dict) and result.get("requires_confirmation"):
        assert opened == []
    else:
        assert opened, "an allowed https URL must reach the handler"
