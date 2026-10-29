"""Show the planner a short, relevant tool menu instead of all ~90 tools.

A 4B planner reads the whole registry on every step (several thousand tokens) and has to
pick one tool out of ~90, so it is slow and picks wrong. This keeps the tools whose names
or descriptions overlap the user's goal, the tools in the keyword groups the goal touches,
the tools already used this task, and a small always-on core. The rest are simply not
shown.

It only chooses what is SHOWN. The planner's output is still validated against the whole
registry and every call still goes through the permission gate, so a tool left off the menu
costs a worse answer at worst, never a safety gap. If the goal gives nothing to match (empty
or no hits) the full list is returned unchanged, and ``EVA_TOOL_MENU_LIMIT=0`` turns this off.

The selection depends on the goal (and tools already used), never on the latest observation,
so within one task the menu is stable and llama.cpp's prefix cache stays warm.
"""

from __future__ import annotations

import math
import os
import re
from typing import Any, Iterable

DEFAULT_LIMIT = 24

# Always shown: cheap, broadly useful, and the usual first step of a task.
CORE = ("open_app", "open_url", "web_search", "system_time", "desktop_observe", "window_focus")
# Tools that exist only when a task opened a scope for them (typing/click offers, sandbox
# focus). If they are in the list at all, the task is meant to see them.
ALWAYS_PREFIXES = ("screen.",)

# goal words -> tool names or prefixes (a trailing "." or "_" matches a family).
GROUPS: tuple[tuple[frozenset[str], tuple[str, ...]], ...] = (
    (frozenset({"spotify", "song", "music", "playlist", "track", "album", "play", "pause", "next", "skip", "previous"}),
     ("spotify_", "media_")),
    (frozenset({"youtube", "video", "videos", "watch", "stream"}),
     ("chrome_activate_top_youtube_result", "chrome_search_site", "chrome_open_web_app", "browser_open_result_and_verify")),
    (frozenset({"volume", "mute", "unmute", "louder", "quieter", "sound", "loud", "quiet"}), ("system_volume", "media_control")),
    (frozenset({"brightness", "dim", "dimmer", "brighter", "bright"}), ("display_brightness",)),
    (frozenset({"dark", "light", "theme", "mode"}), ("theme_mode",)),
    (frozenset({"wifi", "wi", "fi", "bluetooth", "internet", "network", "ethernet"}), ("radio_",)),
    (frozenset({"email", "mail", "gmail", "inbox", "compose", "draft"}), ("email.", "message.", "chrome_open_web_app")),
    (frozenset({"whatsapp", "message", "text", "dm", "send", "tell"}), ("message.", "email.")),
    (frozenset({"file", "files", "folder", "folders", "document", "documents", "read", "copy", "move", "delete", "write", "save", "download", "downloads", "desktop", "rename"}),
     ("file.", "workspace_", "open_folder", "share.")),
    (frozenset({"click", "type", "typing", "press", "key", "keys", "scroll", "button", "buttons", "enter", "fill", "form"}),
     ("screen.", "window_", "app.", "desktop_observe")),
    (frozenset({"screen", "screenshot", "see", "look", "display", "showing"}), ("capture_screen", "analyze_screen", "desktop_observe", "screen.")),
    (frozenset({"window", "windows", "minimize", "maximize", "close", "quit", "focus", "switch"}), ("window_", "close_app", "app.")),
    (frozenset({"weather", "temperature", "forecast", "rain", "raining", "humid", "humidity", "hot", "cold"}), ("weather_forecast",)),
    (frozenset({"search", "google", "web", "news", "latest", "find", "lookup"}),
     ("web_search", "browser_search", "research_", "weather_forecast")),
    (frozenset({"code", "function", "bug", "repo", "project", "traceback", "class", "module", "symbol"}), ("code_", "workspace_")),
    (frozenset({"research", "topic", "note", "notes", "summarize", "summary", "remember", "recall"}),
     ("research_", "browser_summarize_page", "browser_save_page_to_research")),
    (frozenset({"terminal", "linux", "command", "shell", "script", "bash", "python", "run", "execute", "sandbox"}), ("sandbox_run", "shell.")),
    (frozenset({"clipboard", "paste", "copied"}), ("clipboard.",)),
    (frozenset({"lock", "power", "shutdown", "sleep", "restart", "reboot", "hibernate"}), ("lock_laptop", "system_power", "guarded_power_action")),
    (frozenset({"page", "browser", "tab", "tabs", "chrome", "website", "site", "url", "link", "links", "web"}), ("browser_", "chrome_", "web.")),
    (frozenset({"open", "launch", "start"}), ("open_app", "open_folder", "open_url", "chrome_open_web_app")),
    (frozenset({"battery", "disk", "memory", "ram", "cpu", "space", "status", "storage"}), ("status", "system_status")),
    (frozenset({"time", "date", "today", "clock", "day"}), ("system_time",)),
    (frozenset({"remind", "reminder", "timer", "alarm"}), ("reminder", "timer")),
    (frozenset({"pdf", "docx", "word", "excel", "spreadsheet", "powerpoint", "ocr", "image", "photo", "picture", "png", "jpg", "jpeg", "scan", "scanned"}), ("ocr_image", "file.")),
    (frozenset({"rss", "feed", "feeds", "headline", "headlines", "news"}), ("rss_headlines",)),
    (frozenset({"transcript", "subtitles", "captions"}), ("youtube_transcript",)),
)

_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset("a an the and or to of for in on at is it my me i you your please can could would what how do does with from that this then".split())


def menu_limit() -> int:
    raw = os.environ.get("EVA_TOOL_MENU_LIMIT", "").strip()
    try:
        return max(0, int(raw)) if raw else DEFAULT_LIMIT
    except ValueError:
        return DEFAULT_LIMIT


def _stem(word: str) -> str:
    for suffix in ("ing", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _tokens(text: str) -> list[str]:
    return [_stem(w) for w in _WORD.findall(str(text or "").lower()) if w not in _STOP and len(w) > 1]


def _matches(name: str, pattern: str) -> bool:
    if pattern.endswith((".", "_")):
        return name.startswith(pattern)
    return name == pattern or name.startswith(pattern + "_") or name.startswith(pattern + ".")


def select_specs(goal: str, specs: list[dict[str, Any]], *, used: Iterable[str] = (), limit: int | None = None) -> list[dict[str, Any]]:
    """The tools to show for `goal`, keeping the registry's own order."""
    limit = menu_limit() if limit is None else limit
    if limit <= 0 or len(specs) <= limit:
        return specs
    goal_words = _tokens(goal)
    if not goal_words:
        return specs
    goal_set = set(goal_words)
    raw_words = set(_WORD.findall(str(goal or "").lower()))

    docs = {spec["name"]: set(_tokens(spec["name"].replace("_", " ").replace(".", " ") + " " + str(spec.get("description") or ""))) for spec in specs}
    doc_freq: dict[str, int] = {}
    for words in docs.values():
        for word in words:
            doc_freq[word] = doc_freq.get(word, 0) + 1
    total = len(docs)

    scores: dict[str, float] = {}
    for name, words in docs.items():
        overlap = goal_set & words
        scores[name] = sum(math.log(1 + total / doc_freq[word]) for word in overlap)

    chosen: dict[str, float] = {}
    for name in docs:
        if name in CORE or name.startswith(ALWAYS_PREFIXES) or name in set(used):
            chosen[name] = 1e9
    matched_group = False
    for words, patterns in GROUPS:
        if raw_words & words or goal_set & {_stem(w) for w in words}:
            for name in docs:
                if any(_matches(name, pattern) for pattern in patterns):
                    matched_group = True
                    scores[name] = scores.get(name, 0.0) + 5.0
    if not matched_group and not any(scores.values()):
        return specs

    ranked = sorted((n for n in docs if n not in chosen and scores.get(n, 0.0) > 0), key=lambda n: -scores[n])
    for name in ranked:
        if len(chosen) >= limit:
            break
        chosen[name] = scores[name]
    return [spec for spec in specs if spec["name"] in chosen]
