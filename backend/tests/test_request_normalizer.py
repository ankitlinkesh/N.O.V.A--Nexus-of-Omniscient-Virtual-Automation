from unittest.mock import MagicMock

import pytest

from backend.eva.core.fast_commands import maybe_handle_fast_command
from backend.eva.core.request_normalizer import canonicalize_request


@pytest.mark.parametrize(
    "message, expected",
    [
        ("can you pause the music please", "pause"),
        ("pause the music", "pause"),
        ("Hey Nova, resume the song", "play"),
        ("skip this song", "next track"),
        ("could you skip the track for me?", "next track"),
        ("play the previous song", "previous track"),
        ("turn the volume up", "volume up"),
        ("make it quieter", "volume down"),
        ("make it brighter", "make the screen brighter"),
        ("open the calculator", "open calculator"),
        ("can you open spotify for me", "open spotify"),
        ("put on some lofi", "play lofi"),
        # Untouched: commands that already start with eva/nova, and ordinary text.
        ("eva control center", "eva control center"),
        ("open my downloads", "open my downloads"),
        ("what is the capital of france", "what is the capital of france"),
        ("play despacito on spotify", "play despacito on spotify"),
        ("", ""),
    ],
)
def test_canonicalize_request(message, expected):
    assert canonicalize_request(message) == expected


def _route(message):
    tools = MagicMock()
    calls = []
    tools.run.side_effect = lambda name, **kw: calls.append((name, kw)) or {"ok": True}
    maybe_handle_fast_command(message, tools, {}, MagicMock(), "s1")
    return [(n, kw) for n, kw in calls if n != "verify_last_action"]


def test_loose_phrasing_reaches_the_same_tool_as_the_canonical_phrase():
    assert _route("can you pause the music please") == _route("pause")
    assert _route("turn the volume up") == _route("volume up")
    assert _route("skip this song") == _route("next track")
    assert _route("can you open spotify for me") == _route("open spotify")


def test_go_to_a_bare_word_is_not_opened_as_a_url():
    assert _route("go to github") == [("open_url", {"url": "https://github.com"})]
    assert _route("go to mars") == []
    assert _route("go to example.com") == [("open_url", {"url": "example.com"})]


def test_open_my_x_is_only_a_folder_when_x_is_a_folder():
    assert _route("open my gmail") == [("open_url", {"url": "https://mail.google.com"})]
    assert _route("open my downloads") == [("open_folder", {"folder_name": "downloads"})]
