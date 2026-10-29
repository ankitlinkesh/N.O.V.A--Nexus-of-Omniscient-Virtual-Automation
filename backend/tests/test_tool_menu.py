"""The planner's per-goal tool menu: recall on the tools the planner can see, and its escape hatches."""

import pytest

from backend.eva.agent import planner as planner_module
from backend.eva.agent.tool_menu import DEFAULT_LIMIT, select_specs
from backend.eva.tools.registry import ToolRegistry

SPECS = ToolRegistry().planner_specs()
NAMES = {spec["name"] for spec in SPECS}

# (goal, a tool the planner must be offered for it)
CASES = [
    ("play pavazhamalli on spotify", "spotify_play_desktop"), ("pause the music", "media_control"),
    ("set the volume to 30", "system_volume"), ("dim the screen", "display_brightness"),
    ("switch to dark mode", "theme_mode"), ("is wifi on", "radio_status"), ("turn bluetooth off", "radio_set"),
    ("open calculator and type 12+7=", "open_app"), ("read Downloads/note.txt and tell me the code", "file.read_text"),
    ("copy Downloads/a.txt to my Documents folder", "file.copy"), ("how much free space is on my C drive", "system_status"),
    ("what time is it", "system_time"), ("search the web for the best budget gpu", "web_search"),
    ("play lofi beats on youtube", "chrome_activate_top_youtube_result"), ("open gmail", "chrome_open_web_app"),
    ("write an email to my professor", "email.draft_gmail"), ("what's on my screen", "analyze_screen"),
    ("take a screenshot", "capture_screen"), ("minimize the chrome window", "window_minimize"),
    ("lock the pc", "lock_laptop"), ("find where triage_request is defined", "code_find_symbol"),
    ("summarize this page", "browser_summarize_page"), ("run uname -a in your terminal", "sandbox_run"),
    ("copy this text to the clipboard", "clipboard.write"), ("open the downloads folder", "open_folder"),
    ("list the files in my project", "workspace_list_files"), ("reload the page", "chrome_reload"),
    ("will it rain in chennai tomorrow", "weather_forecast"), ("how hot is it in delhi", "weather_forecast"),
    ("show me the latest bbc headlines", "rss_headlines"), ("get the transcript of this youtube video", "youtube_transcript"),
    ("read the text in the image on my desktop", "ocr_image"), ("what does this screenshot png say", "ocr_image"),
]


@pytest.mark.parametrize("goal,tool", [case for case in CASES if case[1] in NAMES])
def test_menu_keeps_the_tool_the_goal_needs(goal, tool):
    assert tool in {spec["name"] for spec in select_specs(goal, SPECS)}


def test_menu_is_much_shorter_than_the_registry():
    sizes = sorted(len(select_specs(goal, SPECS)) for goal, _ in CASES)
    assert sizes[len(sizes) // 2] <= DEFAULT_LIMIT and sizes[len(sizes) // 2] < len(SPECS) / 2


def test_core_tools_and_used_tools_are_always_kept():
    names = {spec["name"] for spec in select_specs("play a song on spotify", SPECS, used=("code_status",))}
    assert {"open_app", "web_search", "system_time"} <= names and "code_status" in names


def test_no_match_or_empty_goal_shows_everything():
    assert select_specs("", SPECS) == SPECS
    assert select_specs("zzqxv blorp", SPECS) == SPECS


def test_limit_zero_turns_it_off(monkeypatch):
    monkeypatch.setenv("EVA_TOOL_MENU_LIMIT", "0")
    assert select_specs("play a song on spotify", SPECS) == SPECS


def test_selection_keeps_registry_order_and_never_invents_tools():
    chosen = select_specs("play a song on spotify", SPECS)
    order = [spec["name"] for spec in SPECS]
    assert [spec["name"] for spec in chosen] == [name for name in order if name in {s["name"] for s in chosen}]


def test_planner_prompt_carries_the_filtered_registry():
    registry = ToolRegistry()
    shown = planner_module._registry_json(registry, "play a song on spotify")
    everything = planner_module._registry_json(registry, "")
    assert "spotify_play_desktop" in shown and len(shown) < len(everything) / 2
    assert "radio_set" not in shown and "radio_set" in everything
