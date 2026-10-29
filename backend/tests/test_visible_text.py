"""Invisible and look-alike characters are shown, not hidden, in what a person approves."""

from backend.eva.agents.explainer import explain_action
from backend.eva.security.visible_text import note, reveal
from backend.eva.tools.registry import _typing_preview


def test_invisible_characters_become_visible_markers():
    shown, count = reveal("pay\u200b 100 to\u202e evil\u00a0x\u3000y")
    assert count == 4 and "⟦U+200B⟧" in shown and "⟦U+202E⟧" in shown and "⟦U+00A0⟧" in shown and "⟦U+3000⟧" in shown
    assert "\u200b" not in shown and "\u202e" not in shown


def test_ordinary_text_passes_through_unchanged():
    for text in ("14*3=", "hello world", "naïve café", "日本語のテキスト", "tab\tand\nnewline", "emoji 🙂 ok", "தமிழ்"):
        assert reveal(text) == (text, 0) and note(text) == "", text


def test_lookalike_alphabets_inside_latin_text_are_warned_about():
    assert "more than one alphabet" in note("раypal.com")  # Cyrillic а and р among Latin letters
    assert note("привет") == "" and note("Αθήνα") == ""  # a whole word in one script is fine


def test_the_typing_prompt_shows_the_hidden_characters_and_warns():
    prompt = _typing_preview("screen.type_text", {"text": "send\u200b 5"}, {"title": "Notepad"})
    assert "⟦U+200B⟧" in prompt and "\u200b" not in prompt and "WARNING" in prompt and "Notepad" in prompt
    clean = _typing_preview("screen.type_text", {"text": "14*3="}, None)
    assert clean.strip() == "It will type exactly: `14*3=`." and "WARNING" not in clean


def test_the_explanation_warns_about_a_hidden_character_in_any_argument():
    explained = explain_action("file.write_text", "Write a file", "DESTRUCTIVE_FILE_ACTION", "confirm", {"path": "Documents/a.txt", "content": "hi\u202e there"})
    assert "WARNING" in explained.what_it_does
    plain = explain_action("file.write_text", "Write a file", "DESTRUCTIVE_FILE_ACTION", "confirm", {"path": "Documents/a.txt", "content": "hi there"})
    assert "WARNING" not in plain.what_it_does
