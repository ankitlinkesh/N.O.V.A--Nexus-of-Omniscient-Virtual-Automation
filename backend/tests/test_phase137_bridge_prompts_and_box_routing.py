"""Phase 137: two small fixes left from Phase 134.

1. The file-bridge approval prompts showed only the raw call and the tool's generic
   description. They now name the file and say where it goes and why it matters.
2. "add it to your box of tools" was routed as a request about NOVA's box.
"""
from __future__ import annotations

import pytest

from backend.eva.agent.policies import is_agentic_intent, is_sandbox_request
from backend.eva.agents.explainer import explain_action


def _what(tool, args):
    return explain_action(tool, "Generic description.", "SANDBOX_TRANSFER", "confirm", args).what_it_does


def test_to_box_prompt_names_the_file_folder_and_the_internet_risk():
    text = _what("share.to_box", {"path": "Downloads/report.pdf"})
    assert "`report.pdf`" in text and "your Downloads folder" in text
    assert "/mnt/share/report.pdf" in text and "internet" in text
    assert "Your original stays where it is" in text


def test_to_box_prompt_handles_a_full_windows_path():
    text = _what("share.to_box", {"path": r"C:\Users\HP\Documents\notes.txt"})
    assert "`notes.txt`" in text and "your Documents folder" in text


def test_from_box_prompt_names_the_file_destination_and_the_care_needed():
    text = _what("share.from_box", {"name": "out/result.csv", "folder": "documents"})
    assert "`result.csv`" in text and "your Documents folder" in text
    assert "nothing is overwritten" in text and "made inside his box" in text


def test_from_box_prompt_defaults_to_downloads():
    assert "your Downloads folder" in _what("share.from_box", {"name": "squares.txt"})


def test_other_tools_are_unchanged():
    assert _what("file.copy", {"src": "a", "dst": "b"}) == "Generic description."


def test_the_full_prompt_still_carries_the_raw_call():
    text = explain_action("share.to_box", "d", "SANDBOX_TRANSFER", "confirm", {"path": "Downloads/x.txt"}).as_text()
    assert "Command: share.to_box(path='Downloads/x.txt')" in text and "THIS CALL copies `x.txt`" in text


@pytest.mark.parametrize("message", ["add it to your box of tools", "put it in your box of chocolates"])
def test_a_box_of_something_is_not_novas_box(message):
    assert not is_sandbox_request(message)


@pytest.mark.parametrize("message", [
    "put report.txt into your box", "in your box, count the words", "use your sandbox of course",
    "in your linux box of choice", "in your terminal, make a folder",
])
def test_real_box_requests_still_route(message):
    assert is_sandbox_request(message) and is_agentic_intent(message)
