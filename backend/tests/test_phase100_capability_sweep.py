"""Phase 100: the YouTube bug had a family, found by sweeping the capability routes.

Phase 99 fixed "play X on YouTube". The interesting part was not YouTube: it was
learning that `routes.py` consults the capability classifier BEFORE
`is_agentic_intent`, and that a matched capability runs exactly ONE tool. Any
multi-step request the classifier matches therefore gets half done.

Sweeping the routes with two-part requests turned up one more instance, and it
was worse than the YouTube case::

    "search github for fastapi and open the first result"
      -> capability: browser_agent, route: chrome_search_site
      -> searched GitHub for the literal string "fastapi and open the first result"
      -> replied "Done, searched github for fastapi and open the first result in Chrome."

Three defects in one answer: the query was polluted (so the search itself was
wrong), the second half was silently dropped, and the reply claimed both. The
query is extracted as "everything after the prefix", which is why the second
request rode along inside it.

Fixed by declining rather than trimming. Trimming the query alone would repair
the search and still drop "open the first result" in silence; declining hands the
whole message to the agent loop, which can take as many steps as it needs -- and
does: `web_search` then `browser_open_url`.

Also fixed here, found while retesting: a half-emitted JSON object reached the
user as an answer.

Spotify was checked and needed nothing: `play_spotify_desktop` verifies against
real now-playing state and has three distinct messages for verified,
activated-but-unverified, and could-not-activate.
"""

from __future__ import annotations

import pytest

from backend.eva.agent.planner import _looks_like_broken_serialization
from backend.eva.agent.policies import split_trailing_request
from backend.eva.core.intent_router import classify_capability_intent


# --------------------------------------------- splitting a trailing request


@pytest.mark.parametrize(
    "text,head,tail",
    [
        ("fastapi and open the first result", "fastapi", "open the first result"),
        ("python decorators then open the docs", "python decorators", "open the docs"),
        ("lofi and play it", "lofi", "play it"),
    ],
)
def test_a_trailing_request_is_separated(text, head, tail):
    assert split_trailing_request(text) == (head, tail)


@pytest.mark.parametrize(
    "text",
    [
        "cats and dogs",
        "milk and eggs",
        "fastapi and stars",
        "fastapi",
        "salt and pepper shakers",
        "",
    ],
)
def test_ordinary_conjunctions_are_left_alone(text):
    """"dogs" is not a request, so "cats and dogs" is one search, not two."""
    head, tail = split_trailing_request(text)
    assert tail == ""
    assert head == " ".join(text.split())


# ------------------------------- the one-shot route declines what it cannot do


def test_a_two_part_site_search_is_not_matched_by_the_one_shot_route():
    """The exact request that searched GitHub for its own instructions."""
    result = classify_capability_intent("search github for fastapi and open the first result") or {}
    assert not result.get("matched"), (
        "a one-shot capability route cannot honour a second request; matching it means searching for the "
        "instruction text and then claiming both halves were done"
    )


def test_a_two_part_site_search_reaches_the_agent_loop():
    """Declining is only useful if something else can take the whole request."""
    from backend.eva.agent.policies import is_agentic_intent

    assert is_agentic_intent("search github for fastapi and open the first result") is True


def test_a_plain_site_search_still_takes_the_fast_path():
    """One ask must not start costing three LLM calls."""
    result = classify_capability_intent("search github for fastapi") or {}
    assert result.get("matched") is True
    assert result.get("suggested_route") == "chrome_search_site"
    assert result.get("query") == "fastapi", "the query must be the query, not the whole sentence"


def test_the_query_is_never_the_instruction_text():
    """The bug's signature: the search string contained the second request."""
    for message in (
        "search github for fastapi",
        "search youtube for lofi beats",
        "search stack overflow for asyncio gather",
    ):
        result = classify_capability_intent(message) or {}
        if result.get("matched"):
            query = str(result.get("query") or "")
            assert " and open " not in query and " then " not in query, query


def test_youtube_play_still_routes_through_the_capability_path():
    """Phase 99's fix must not be undone by Phase 100's decline.

    "open youtube and play X" IS two requests, but this route absorbs the second
    one into `play=True`, so it can honour the whole message and should keep it.
    """
    result = classify_capability_intent("open youtube and play pavazhamalli") or {}
    assert result.get("matched") is True
    assert result.get("play") is True
    assert result.get("query") == "pavazhamalli"


# ------------------------------------- a JSON fragment is not an answer


@pytest.mark.parametrize(
    "text",
    [
        'We need to be filled in",   "query": "fastapi github" }',
        "}",
        'foo": "bar",',
        '"query": "x"',
        'stuff }]',
    ],
)
def test_serialization_debris_is_not_offered_as_an_answer(text):
    """One live run answered with the tail of a half-emitted JSON object."""
    assert _looks_like_broken_serialization(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "It is 4:08 AM on Friday.",
        "I opened YouTube and it is playing now.",
        "The file is backend/eva/agent/runner.py (line 226).",
        "Here are your windows: chrome, terminal.",
        "Task complete.",
        "",
    ],
)
def test_real_prose_answers_are_untouched(text):
    """Prose is a valid answer from a native planner (Phase 93) and must survive."""
    assert _looks_like_broken_serialization(text) is False


def test_the_planner_declines_rather_than_answering_with_debris(monkeypatch):
    """Arrival: the guard has to be wired into the decision, not just defined."""
    import asyncio

    from backend.eva.agent import planner as planner_module
    from backend.eva.core.config import ModelSettings
    from backend.eva.llm.types import LLMResponse, RoutedLLMResponse
    from backend.eva.tools.registry import ToolRegistry

    async def fake_complete(*args, **kwargs):
        return RoutedLLMResponse(
            response=LLMResponse(
                provider="p",
                model="m",
                ok=True,
                text='We need to be filled in",   "query": "fastapi github" }',
                tool_calls=[],
            ),
            attempts=[],
        )

    monkeypatch.setattr(planner_module, "complete_with_fallback", fake_complete)
    planner = planner_module.ToolCallPlanner(ModelSettings(), ToolRegistry())
    decision = asyncio.run(planner._native_plan("do a thing", [], mode="single_turn", task_context={}))
    assert decision is None, "debris must be reported as no decision, so the fallback paths get their turn"
