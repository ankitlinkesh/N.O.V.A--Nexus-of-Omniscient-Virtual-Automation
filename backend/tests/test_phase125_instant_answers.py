"""Phase 125: common read-only questions answer with no LLM call."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.eva.agent.executor import ToolExecutionResult
from backend.eva.core.fast_commands import maybe_handle_fast_command

TIME = {"ok": True, "local_time": "14:05:09", "local_time_12h": "2:05 PM", "local_date": "2026-10-01",
        "weekday": "Thursday", "timezone": "Pacific Daylight Time"}
STATUS = {"os_name": "Windows 11", "battery_present": True, "battery_percent": 81, "plugged_in": True,
          "memory_percent_used": 47, "memory_total_gb": 15.8,
          "disks": [{"drive": "C:", "free_gb": 5.1, "total_gb": 237.0}, {"drive": "D:", "free_gb": 145.3, "total_gb": 238.2}]}
WINDOWS = {"ok": True, "count": 7, "windows": [
    {"title": "notes.txt - Notepad", "process_name": "Notepad.exe"},
    {"title": "Settings", "process_name": "SystemSettings.exe"},
    {"title": "Settings", "process_name": "ApplicationFrameHost.exe"},
    {"title": "Cua.AgentCursorOverlay.default", "process_name": "cua-driver.exe"},
    {"title": "Windows Input Experience", "process_name": "TextInputHost.exe"},
    {"title": "Program Manager", "process_name": "explorer.exe"},
    {"title": "Inbox - Mail", "process_name": "chrome.exe"},
]}
LISTING = {"ok": True, "path": "C:\\Users\\HP\\Downloads", "items": ["a.pdf", "b.zip", "c"], "total": 48}


class FakeRegistry:
    def __init__(self):
        self.calls = []

    def run(self, name, **kwargs):
        self.calls.append((name, kwargs))
        return {"system_time": TIME, "system_status": STATUS, "window_list": WINDOWS, "file.list_dir": LISTING}[name]


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("an instant answer must not call the LLM")

    monkeypatch.setattr("backend.eva.llm.router.complete_with_fallback", boom)
    monkeypatch.setattr("backend.eva.api.routes.complete_with_fallback", boom)


def ask(text):
    tools = FakeRegistry()
    return maybe_handle_fast_command(text, tools, {}), tools.calls


@pytest.mark.parametrize("text,tool,needle", [
    ("what time is it", "system_time", "2:05 PM"),
    ("What's the time?", "system_time", "2:05 PM"),
    ("time?", "system_time", "2:05 PM"),
    ("what time is it right now, please", "system_time", "2:05 PM"),
    ("what's the date", "system_time", "October 1, 2026"),
    ("what's today's date", "system_time", "Thursday, October 1, 2026"),
    ("what day is it", "system_time", "Thursday"),
    ("battery", "system_status", "81%"),
    ("what's my battery level?", "system_status", "81%"),
    ("What is my battery percentage", "system_status", "81%"),
    ("how much battery do I have", "system_status", "81%"),
    ("am I plugged in?", "system_status", "plugged in"),
    ("is my laptop charging", "system_status", "plugged in"),
    ("how much free space is on my C drive?", "system_status", "C: has 5.1 GB free of 237.0 GB"),
    ("how much free space on C:", "system_status", "C: has 5.1 GB free"),
    ("how much free space is there on my D drive", "system_status", "D: has 145.3 GB"),
    ("how much free space do I have", "system_status", "C: 5.1 GB free"),
    ("disk space", "system_status", "D: 145.3 GB free"),
    ("storage left", "system_status", "D: 145.3 GB free"),
    ("how much free space is left on my disk", "system_status", "C: 5.1 GB free"),
    ("memory usage", "system_status", "47%"),
    ("how much RAM am I using?", "system_status", "15.8 GB"),
    ("which windows are open", "window_list", "notes.txt - Notepad"),
    ("what's open", "window_list", "Inbox - Mail"),
    ("list open windows", "window_list", "Open windows (3)"),
    ("how many files are in my Downloads folder?", "file.list_dir", "48 items"),
    ("how many files are in Documents", "file.list_dir", "Documents folder"),
    ("how many files are in my desktop", "file.list_dir", "Desktop folder"),
])
def test_phrasing_hits_its_tool_without_llm(text, tool, needle):
    reply, calls = ask(text)
    assert reply is not None, text
    assert reply[1] == "instant-answer"
    assert needle in reply[0], reply
    assert [c[0] for c in calls] == [tool]


def test_folder_count_uses_bare_folder_name_and_true_total():
    reply, calls = ask("how many files are in my downloads folder")
    assert calls == [("file.list_dir", {"path": "Downloads"})]
    assert "48 items" in reply[0]


def test_missing_drive_is_honest_not_invented():
    reply, _ = ask("how much free space is on my Z drive")
    assert "don't see a fixed drive Z:" in reply[0]


def test_windows_list_hides_overlays_and_dedupes():
    text = ask("which windows are open")[0][0]
    for hidden in ("Program Manager", "Windows Input Experience", "Overlay", "cua-driver"):
        assert hidden not in text
    assert text.count("- Settings") == 1


@pytest.mark.parametrize("text", [
    "what time is the meeting tomorrow",
    "is the battery in my car good",
    "what time is it in Tokyo",
    "how much free space does Google Drive give",
    "what time is it and open chrome",
    "how much free space is on my C drive and delete the temp files",
    "how many files are in my Downloads folder older than a week",
    "what's open on the menu",
    "memory",
    "how much ram does a mac have",
    "how much space is on a drive",
])
def test_near_misses_decline(text):
    reply, calls = ask(text)
    assert reply is None, reply
    assert calls == []


def test_trailing_request_guard_is_wired(monkeypatch):
    # Defence in depth: even when a phrasing matches, a detected second request declines.
    monkeypatch.setattr("backend.eva.agent.policies.split_trailing_request", lambda t: ("what time is it", "open chrome"))
    reply, calls = ask("what time is it")
    assert reply is None and calls == []


def test_parked_tool_surfaces_its_confirmation_instead_of_a_template():
    class Parked:
        def run(self, name, **kw):
            return {"requires_confirmation": True, "message": "needs approval"}

    assert maybe_handle_fast_command("what time is it", Parked(), {}) == ("needs approval", "instant-answer")


def test_tool_error_is_reported_not_swallowed():
    class Broken:
        def run(self, name, **kw):
            raise RuntimeError("disk gone")

    reply = maybe_handle_fast_command("how many files are in my downloads", Broken(), {})
    assert "disk gone" in reply[0]


def test_existing_fast_commands_still_win():
    for text in ("who are you", "list my rules", "llm doctor"):
        tools = FakeRegistry()
        reply = maybe_handle_fast_command(text, tools, {})
        assert reply is not None and reply[1] != "instant-answer", text


# ---------------------------------------------------------------- Part B
def _result(tool, data, **kw):
    return ToolExecutionResult(ok=kw.pop("ok", True), tool=tool, result=data, **kw)


def _synth(message, results):
    from backend.eva.api import routes

    return asyncio.run(routes._synthesize_tool_response(message, results, [], SimpleNamespace(models=None)))


def test_single_system_time_call_is_templated_without_llm():
    reply, source = _synth("what time is it", [_result("system_time", TIME)])
    assert source == "tool-template" and "2:05 PM" in reply


@pytest.mark.parametrize("tool,data,msg,needle", [
    ("system_status", STATUS, "battery?", "81%"),
    ("window_list", WINDOWS, "what's open", "Open windows"),
    ("file.list_dir", LISTING, "how many files are in downloads", "48 items"),
])
def test_other_templated_tools_skip_synthesis(tool, data, msg, needle):
    reply, source = _synth(msg, [_result(tool, data)])
    assert source == "tool-template" and needle in reply


def test_listing_template_not_used_for_a_lookup_question():
    from backend.eva.core.fast_command_instant import synthesize_single_result

    assert synthesize_single_result("is resume.pdf in downloads", [_result("file.list_dir", LISTING)]) is None


def test_llm_still_used_for_web_search_failures_and_multi_call(monkeypatch):
    calls = []

    async def fake_llm(*a, **k):
        calls.append(1)
        return SimpleNamespace(response=SimpleNamespace(ok=True, text="LLM sentence", provider="p", model="m"))

    monkeypatch.setattr("backend.eva.api.routes.complete_with_fallback", fake_llm)
    from backend.eva.api import routes

    def run(msg, results):
        return asyncio.run(routes._synthesize_tool_response(msg, results, [], SimpleNamespace(models=None)))

    assert run("search x", [_result("web_search", {"ok": True, "results": []})])[0] == "LLM sentence"
    assert run("time", [_result("system_time", {"ok": False}, ok=False, error="boom")])[0] == "LLM sentence"
    assert run("time and battery", [_result("system_time", TIME), _result("system_status", STATUS)])[0] == "LLM sentence"
    assert len(calls) == 3


def test_count_question_gets_count_only_and_list_question_gets_names():
    from backend.eva.core.fast_command_instant import synthesize_single_result

    count = synthesize_single_result("give me the number of files in Downloads", [_result("file.list_dir", LISTING)])
    assert "48 items" in count and "a.pdf" not in count
    names = synthesize_single_result("list the files in Downloads", [_result("file.list_dir", LISTING)])
    assert "a.pdf" in names and "and 45 more" in names
