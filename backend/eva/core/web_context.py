from __future__ import annotations

import os
import re
import time
from typing import Any


def normalize_web_results(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    results = raw.get("results")
    if not isinstance(results, list):
        return []
    normalized: list[dict[str, Any]] = []
    provider = str(raw.get("provider") or "web")
    for index, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        normalized.append(
            {
                "index": index,
                "title": title or url,
                "url": url,
                "content": str(item.get("content") or item.get("snippet") or "").strip(),
                "source": provider,
            }
        )
    return normalized


def remember_web_results(session_context: dict[str, Any] | None, raw: Any) -> None:
    if session_context is None:
        return
    results = normalize_web_results(raw)
    if not results:
        return
    session_context["last_web_query"] = str(raw.get("query") or "").strip() if isinstance(raw, dict) else ""
    session_context["last_web_results"] = results
    session_context["last_web_results_at"] = int(time.time())


def last_web_results(session_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(session_context, dict):
        return []
    results = session_context.get("last_web_results")
    return results if isinstance(results, list) else []


def profile_urls() -> dict[str, str]:
    return {
        "profile": os.environ.get("EVA_PROFILE_URL", "").strip(),
        "instagram": os.environ.get("EVA_INSTAGRAM_URL", "").strip(),
        "github": os.environ.get("EVA_GITHUB_URL", "").strip(),
        "linkedin": os.environ.get("EVA_LINKEDIN_URL", "").strip(),
    }


def profile_key_from_message(message: str) -> str | None:
    text = " ".join(message.lower().strip().split())
    if not any(word in text for word in ("profile", "instagram", "github", "linkedin")):
        return None
    if not any(word in text for word in ("my", "ankit", "ankit l")):
        return None
    if "instagram" in text:
        return "instagram"
    if "github" in text:
        return "github"
    if "linkedin" in text or "linked in" in text:
        return "linkedin"
    return "profile"


def result_reference_from_message(message: str, results: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    text = " ".join(message.lower().strip().split())
    if not results:
        return None, [], "no_results"

    ordinal_map = {
        "first": 1,
        "1st": 1,
        "second": 2,
        "2nd": 2,
        "two": 2,
        "third": 3,
        "3rd": 3,
        "three": 3,
        "fourth": 4,
        "4th": 4,
        "fifth": 5,
        "5th": 5,
    }
    index_match = re.search(r"\b(?:result\s*)?([1-5])\b", text)
    if index_match:
        wanted = int(index_match.group(1))
        for result in results:
            if int(result.get("index") or 0) == wanted:
                return result, [result], None

    for word, wanted in ordinal_map.items():
        if word in text:
            for result in results:
                if int(result.get("index") or 0) == wanted:
                    return result, [result], None

    if any(phrase in text for phrase in ("that", "this one", "the one")) and len(results) == 1:
        return results[0], [results[0]], None

    content_words = [word for word in re.findall(r"[a-z0-9]+", text) if len(word) >= 3]
    ignored = {"open", "result", "profile", "chrome", "browser", "that", "this", "one", "the", "link", "site", "page"}
    keywords = [word for word in content_words if word not in ignored]
    matches = []
    for result in results:
        blob = f"{result.get('title', '')} {result.get('url', '')} {result.get('content', '')}".lower()
        if any(keyword in blob for keyword in keywords):
            matches.append(result)
    if len(matches) == 1:
        return matches[0], matches, None
    if len(matches) > 1:
        return None, matches, "ambiguous"
    return None, [], "no_match"


_PREVIOUS_RESULT_WORDS = re.compile(
    r"\b(?:first|second|third|fourth|fifth|results?|that|instagram|github|linkedin|profile|one)\b"
)


def wants_previous_result(message: str) -> bool:
    """"open the second one", "open that result", "open my github".

    Phase 121: these were substring tests, so "one" matched inside "done" and
    "phone" and "result" matched any errand that mentioned one. Live, "open
    calculator and tell me the result of 9 times 9" answered "Which one do you
    want me to open: Python (programming language) - Wikipedia, ..." from an
    earlier search. Whole words only, and a message that carries a second
    request is an errand for the agent, not a reference to a search result.
    """
    text = " ".join(message.lower().strip().split())
    if not text.startswith("open ") or not _PREVIOUS_RESULT_WORDS.search(text):
        return False
    from ..agent.policies import split_trailing_request

    return not split_trailing_request(text)[1]


def summarize_web_result(raw: Any, *, include_prompt: bool = False) -> str:
    if not isinstance(raw, dict):
        return str(raw)
    query = str(raw.get("query") or "your search").strip()
    results = normalize_web_results(raw)
    if raw.get("fallback") == "browser":
        return f"I opened a browser search for {query} because Tavily was {raw.get('error') or 'unavailable'}."
    if not results:
        return f"I searched for {query}, but I did not get usable results."
    lines = [f"Here are the top results for {query}:"]
    for item in results[:5]:
        content = str(item.get("content") or "").strip()
        why = f" - {content[:180]}" if content else ""
        lines.append(f"{item['index']}. {item['title']} - {item['url']}{why}")
    if include_prompt:
        lines.append("Want me to open one of these?")
    return "\n".join(lines)
