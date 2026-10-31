"""Recognise "go to the X tab" and "fill the X tab from Notepad" without asking the model.

The small planner cannot reliably chain these steps (it focused Notepad and stopped, opened new
tabs, and made up text to type), and one rule is enough for the phrasing people use.
"""

from __future__ import annotations

import re

_SWITCH = re.compile(
    r"^(?:please )?(?:go|switch|move|jump) (?:back )?to (?:the |my )?(?P<tab>.{2,60}?) tab"
    r"(?: in (?:chrome|brave|edge|(?:the |my )?browser))?$"
)
_TARGET = re.compile(r"(?:^| )(?:go to|switch to|move to|into|to|in|on) (?:the |my )?(?P<tab>[^,;]{2,60}?) tab(?: |$)")
_VERB = re.compile(r"(?:^| )(?:fill|paste|put|type|enter|copy|write)(?: |$)")
_QUESTION = re.compile(r"^(?:how|what|why|when|where|which|who|is|are|does|do|did|should|can i|could i)(?: |$)")
# What the user says -> what find_window searches for.
_SOURCES = (
    ("notepad++", "notepad++"),
    ("notepad", "notepad"),
    ("visual studio code", "visual studio code"),
    ("vs code", "visual studio code"),
    ("vscode", "visual studio code"),
    ("sublime", "sublime"),
)
_NOT_A_TAB = frozenset({"new", "next", "previous", "last", "this", "that", "current", "other", "another", "same", "first"})


def _clean(message: str) -> str:
    return " ".join(str(message or "").lower().split()).strip(" .!?`'\"")


def _tab_name(raw: str) -> str | None:
    # "in notepad to the foo" keeps only "foo".
    name = raw.strip()
    for joiner in (" into the ", " to the ", " into ", " the "):
        if joiner in name:
            name = name.rsplit(joiner, 1)[1].strip()
    words = name.split()
    if not words or words[0] in {"a", "an", "any"} or words[0] in _NOT_A_TAB:
        return None
    if any(word in name for word, _ in _SOURCES):
        return None
    return name


def parse_tab_switch(message: str) -> str | None:
    """The tab named in "go to the X tab", else None."""
    match = _SWITCH.match(_clean(message))
    return _tab_name(match.group("tab")) if match else None


def parse_tab_paste(message: str) -> tuple[str, str] | None:
    """(editor window, tab) for "fill the X tab with what is in Notepad", else None."""
    text = _clean(message)
    if _QUESTION.match(text) or not _VERB.search(text):
        return None
    source = next((query for word, query in _SOURCES if word in text), None)
    if source is None:
        return None
    for match in _TARGET.finditer(text):
        tab = _tab_name(match.group("tab"))
        if tab:
            return source, tab
    return None
