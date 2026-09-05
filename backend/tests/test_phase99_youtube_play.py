"""Phase 99: "play X on YouTube" searched, claimed success, and played nothing.

Reported from real use: *"i said open youtube and play pavazhamalli but NOVA
opened yt and searched for pavazhamalli did not click and play it tho"*.

Two independent bugs, and the first is the one that made it confusing rather than
merely broken.

**The verification could not fail.** `target_verifier` decided a play request had
succeeded with::

    ok = "youtube.com" in observed_domain and (
        "/watch" in observed_url or "youtube" in observed_title.lower()
    )

EVERY YouTube page has "YouTube" in its title -- the results page is titled
"pavazhamalli - YouTube" -- so the second disjunct is always true and the
`/watch` test decided nothing. Measured live: `verified: True`, message "Done, I
opened the top YouTube result", browser sitting on
`/results?search_query=pavazhamalli`. A check that cannot fail is not a check.

**And the activation never worked.** `chrome_activate_first_visible_result` sends
one TAB then ENTER; on a YouTube results page one tab lands on "Skip navigation",
not the first video. It reported `ok: True` every time and activated nothing.
Rather than guess at a tab count that changes whenever YouTube reshuffles its
layout, the video is now resolved by search and its URL opened directly:
deterministic, verifiable, and needing no synthetic input at all.
"""

from __future__ import annotations

import pytest

from backend.eva.agent.target_verifier import is_youtube_player_url
from backend.eva.browser.skills import _is_youtube_watch_url, _resolve_youtube_watch_url


# ------------------------------------------- the verification that could not fail


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc123",
        "https://www.youtube.com/watch?v=abc&list=PL123",
        "https://www.youtube.com/shorts/xyz",
        "https://youtu.be/abc123",
    ],
)
def test_player_urls_are_recognised(url):
    assert is_youtube_player_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/results?search_query=pavazhamalli",
        "https://www.youtube.com/",
        "https://www.youtube.com/feed/subscriptions",
        "",
    ],
)
def test_a_results_page_is_not_a_player(url):
    """The exact page Eva sat on while reporting it had played something."""
    assert is_youtube_player_url(url) is False


def test_the_page_title_no_longer_decides_playback():
    """The whole defect in one assertion, checked by BEHAVIOUR.

    The results page's title contains "YouTube", and that used to be enough to
    report success. Driving `verify_target` with exactly that state is stronger
    than searching the source -- and the source search failed on its own comment
    explaining the fix, which is the third time this session a test has matched
    its own prose.
    """
    from backend.eva.agent.target_verifier import verify_target
    from backend.eva.agent.task_context import TaskContext

    # The real dataclass, not a stand-in: the first version used a hand-rolled
    # fake and failed on a field it did not know about, which tests the fake
    # rather than the code.
    context = TaskContext(
        task_id="t1",
        user_request="open youtube and play pavazhamalli",
        active_intent="play",
        target_app="chrome",
        target_platform="youtube",
        target_query="pavazhamalli",
        target_url="https://www.youtube.com/results?search_query=pavazhamalli",
        target_domain="youtube.com",
        expected_result="youtube watch page or visible player",
        needs_activation=True,
    )
    observed = {
        "ok": True,
        "url": "https://www.youtube.com/results?search_query=pavazhamalli",
        "title": "(239) pavazhamalli - YouTube - Google Chrome",
        "domain": "youtube.com",
        "source": "live_probe",
    }
    assert verify_target(context, observed).verified is False, (
        "a play request sitting on the search results page must NOT verify, however much its title "
        "says YouTube -- this is exactly the state that reported 'Done, I opened the top YouTube result'"
    )

    playing = dict(observed, url="https://www.youtube.com/watch?v=abc123")
    assert verify_target(context, playing).verified is True, "a real watch page must still verify"


# ------------------------------------------------------- resolving a watch URL


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc",
        "https://music.youtube.com/watch?v=abc",
        "https://m.youtube.com/watch?v=abc",
        "https://youtu.be/abc",
        "https://www.youtube.com/shorts/abc",
    ],
)
def test_youtube_watch_urls_are_accepted(url):
    assert _is_youtube_watch_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.com/watch?v=abc",
        "https://youtube.com.evil.com/watch?v=abc",
        "https://notyoutube.com/watch",
        "javascript:alert(1)",
        "file:///C:/windows/system32",
        "https://www.youtube.com/results?search_query=x",
        "",
    ],
)
def test_non_youtube_or_non_player_urls_are_refused(url):
    """The host check is the security half.

    Candidates come from a web search -- untrusted content -- and "the top result
    for what the user asked" is exactly the slot an attacker wants. A poisoned
    result may at worst send the user to the wrong VIDEO, never off YouTube.
    """
    assert _is_youtube_watch_url(url) is False


def test_resolution_picks_the_first_youtube_player_url(monkeypatch):
    monkeypatch.setattr(
        "backend.eva.tools.tavily_search.tavily_search_sync",
        lambda q: {
            "ok": True,
            "results": [
                {"url": "https://evil.com/watch?v=bad"},
                {"url": "https://www.youtube.com/channel/UC123"},
                {"url": "https://www.youtube.com/watch?v=good"},
                {"url": "https://www.youtube.com/watch?v=later"},
            ],
        },
    )
    assert _resolve_youtube_watch_url("song") == "https://www.youtube.com/watch?v=good"


def test_resolution_declines_when_nothing_playable_comes_back(monkeypatch):
    monkeypatch.setattr(
        "backend.eva.tools.tavily_search.tavily_search_sync",
        lambda q: {"ok": True, "results": [{"url": "https://www.youtube.com/results?search_query=x"}]},
    )
    assert _resolve_youtube_watch_url("song") is None


def test_resolution_declines_when_search_fails(monkeypatch):
    monkeypatch.setattr(
        "backend.eva.tools.tavily_search.tavily_search_sync", lambda q: {"ok": False, "error": "no_key"}
    )
    assert _resolve_youtube_watch_url("song") is None


def test_resolution_never_raises(monkeypatch):
    def boom(q):
        raise RuntimeError("network down")

    monkeypatch.setattr("backend.eva.tools.tavily_search.tavily_search_sync", boom)
    assert _resolve_youtube_watch_url("song") is None


# --------------------------------------------- routing a two-part request


def test_a_two_part_request_is_treated_as_a_task():
    """A one-shot planner returns one tool call, which cannot satisfy two asks."""
    from backend.eva.agent.policies import is_agentic_intent

    assert is_agentic_intent("open youtube and play pavazhamalli") is True
    assert is_agentic_intent("what time is it and what app is in the foreground") is True
    assert is_agentic_intent("open spotify then play my liked songs") is True


def test_an_ordinary_request_still_takes_the_cheap_path():
    """Routing everything through the loop would cost 3 LLM calls for one ask."""
    from backend.eva.agent.policies import is_agentic_intent

    for message in (
        "tell me about cats and dogs",
        "play pavazhamalli",
        "who are you",
        "remind me to buy milk and eggs",
        "what is the difference between a and b",
    ):
        assert is_agentic_intent(message) is False, message


# ------------------------------- the two problems reported from real use


def test_playing_opens_one_tab_not_two(monkeypatch):
    """"it worked but nova opened two tabs playing the same song".

    Opening the results page and then the watch page left two tabs. The results
    page was only ever a stepping stone to a click that no longer happens, so
    once a watch URL resolves there is nothing to search for.
    """
    from backend.eva.browser import skills

    opened: list[str] = []
    monkeypatch.setattr(skills, "_resolve_youtube_watch_url", lambda q: "https://www.youtube.com/watch?v=ok")
    monkeypatch.setattr(skills, "open_url_in_chrome", lambda url: opened.append(url) or {"ok": True})
    monkeypatch.setattr(
        skills,
        "_confirm_youtube_playback",
        lambda url, q: {"ok": True, "activated": True, "verified": True, "message": f"Playing {q}."},
    )
    skills.chrome_search_site("youtube", "pavazhamalli", play=True)

    assert opened == ["https://www.youtube.com/watch?v=ok"], (
        "a play request must open the video only -- opening the results page too is the second tab"
    )


def test_a_search_without_play_still_opens_the_results_page(monkeypatch):
    """The stepping stone is only skipped when we are going straight to a video."""
    from backend.eva.browser import skills

    opened: list[str] = []
    monkeypatch.setattr(skills, "open_url_in_chrome", lambda url: opened.append(url) or {"ok": True})
    skills.chrome_search_site("youtube", "pavazhamalli", play=False)

    assert len(opened) == 1 and "results" in opened[0]


def test_activation_is_idempotent_when_something_is_already_playing(monkeypatch):
    """A second caller must not open the same video in another tab.

    Opening a tab cannot be undone, so the check has to happen BEFORE the open.
    """
    from backend.eva.browser import skills

    opened: list[str] = []
    monkeypatch.setattr(
        skills, "discover_current_url", lambda: {"ok": True, "url": "https://www.youtube.com/watch?v=already"}
    )
    monkeypatch.setattr(skills, "open_url_in_chrome", lambda url: opened.append(url) or {"ok": True})

    result = skills.activate_top_youtube_result("pavazhamalli")
    assert result["method"] == "already_playing"
    assert result["verified"] is True
    assert opened == [], "nothing may be opened when a player page is already in front"


def test_verification_waits_for_the_navigation_instead_of_racing_it(monkeypatch):
    """"I wasn't able to confirm that the video is currently playing".

    The URL was read immediately after opening the tab, so it usually still saw
    the previous page and reported a working video as unconfirmed. That is a
    race, not a caution: the answer depended on Chrome's timing.
    """
    from backend.eva.browser import skills

    seen = iter(
        [
            {"ok": True, "url": "https://www.youtube.com/results?search_query=x"},
            {"ok": True, "url": "https://www.youtube.com/results?search_query=x"},
            {"ok": True, "url": "https://www.youtube.com/watch?v=arrived"},
        ]
    )
    monkeypatch.setattr(skills, "discover_current_url", lambda: next(seen))
    monkeypatch.setattr(skills.time, "sleep", lambda s: None)

    observed = skills._await_player_url(timeout=5.0, interval=0.01)
    assert "watch?v=arrived" in observed["url"]


def test_waiting_still_gives_up_and_reports_honestly(monkeypatch):
    """A page that never becomes a player must end up unverified, not looped on."""
    from backend.eva.browser import skills

    monkeypatch.setattr(
        skills, "discover_current_url", lambda: {"ok": True, "url": "https://www.youtube.com/results?search_query=x"}
    )
    monkeypatch.setattr(skills.time, "sleep", lambda s: None)

    observed = skills._await_player_url(timeout=0.05, interval=0.01)
    assert "results" in observed["url"]
