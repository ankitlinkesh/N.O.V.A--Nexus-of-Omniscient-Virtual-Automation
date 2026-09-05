from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

from .task_context import TaskContext


@dataclass(frozen=True)
class TargetVerificationResult:
    verified: bool
    confidence: float
    expected_target: dict[str, Any]
    observed_target: dict[str, Any]
    evidence: str
    failure_reason: str | None = None
    suggested_repair: str | None = None
    source: str = "unknown"
    stale: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def _expected(context: TaskContext) -> dict[str, Any]:
    platform = (context.target_platform or "").lower()
    domain = context.target_domain
    if not domain:
        domain = {
            "youtube": "youtube.com",
            "github": "github.com",
            "hugging face": "huggingface.co",
            "huggingface": "huggingface.co",
            "stackoverflow": "stackoverflow.com",
            "stack overflow": "stackoverflow.com",
            "chatgpt": "chatgpt.com",
        }.get(platform)
    return {
        "platform": context.target_platform,
        "domain": domain,
        "query": context.target_query,
        "url": context.target_url,
        "title": context.target_title,
        "expected_result": context.expected_result,
        "needs_activation": context.needs_activation,
    }


def _observed(observation_or_tool_result: Any) -> dict[str, Any]:
    data = observation_or_tool_result if isinstance(observation_or_tool_result, dict) else {}
    url = _clean(data.get("current_url") or data.get("url") or data.get("known_current_url"))
    title = _clean(data.get("current_title") or data.get("title") or data.get("active_window_title"))
    return {
        "url": url or None,
        "domain": _domain(url),
        "title": title or None,
        "source": data.get("source") or "unknown",
        "verified": bool(data.get("verified")),
        "stale": bool(data.get("stale")),
        "raw": {key: data.get(key) for key in ("ok", "url", "current_url", "title", "current_title", "source", "verified", "stale")},
    }


def is_youtube_player_url(url: str) -> bool:
    """Whether this URL is a page that actually plays something.

    `/results?search_query=...` is not, however much its title says "YouTube".
    Shorts and youtu.be links are, and a playlist watch URL is a `/watch` with
    extra parameters, so it is covered by the first test.
    """
    text = str(url or "").lower()
    return "/watch" in text or "/shorts/" in text or "youtu.be/" in text


def verify_target(context: TaskContext | None, observation_or_tool_result: Any) -> TargetVerificationResult:
    if context is None:
        return TargetVerificationResult(
            False,
            0.0,
            {},
            _observed(observation_or_tool_result),
            "No current task target is available.",
            "no_task_context",
            "Ask the user what target to verify.",
        )

    expected = _expected(context)
    observed = _observed(observation_or_tool_result)
    source = str(observed.get("source") or "unknown")
    stale = bool(observed.get("stale")) or source == "cache"
    observed_url = str(observed.get("url") or "")
    observed_title = str(observed.get("title") or "")
    observed_domain = str(observed.get("domain") or "")
    expected_domain = str(expected.get("domain") or "").lower()
    expected_query = str(expected.get("query") or "").lower()

    if stale:
        return TargetVerificationResult(
            False,
            0.25,
            expected,
            observed,
            "Only stale cached browser state is available.",
            "cache_only_target_unverified",
            "Reopen or focus the target page, then verify again.",
            source=source,
            stale=True,
        )

    if observed_url.startswith(("http://127.0.0.1", "http://localhost")) and expected_domain and "localhost" not in expected_domain:
        platform = expected.get("platform") or expected_domain
        return TargetVerificationResult(
            False,
            0.15,
            expected,
            observed,
            f"Expected {platform}, but the active Chrome tab is Eva/localhost.",
            f"I can't verify the {platform} results because the active Chrome tab is Eva, not {platform}.",
            f"I can switch back to the {platform} tab or reopen the search.",
            source=source,
        )

    if expected_domain and expected_domain not in observed_domain:
        return TargetVerificationResult(
            False,
            0.3,
            expected,
            observed,
            f"Observed domain {observed_domain or 'unknown'} did not match expected {expected_domain}.",
            "active_target_mismatch",
            "Reopen the intended target and verify again.",
            source=source,
        )

    platform = str(expected.get("platform") or "").lower()
    if platform == "youtube":
        if context.needs_activation:
            # `needs_activation` means the user asked for something to PLAY, so
            # only a player URL counts. The old test also accepted
            # `"youtube" in observed_title`, which EVERY YouTube page satisfies --
            # the search results page is titled "pavazhamalli - YouTube" -- so the
            # watch-page half could never decide anything. Asked to play a song,
            # Eva activated nothing, sat on the results page, and reported "Done,
            # I opened the top YouTube result". A check that cannot fail is not a
            # check, and this one turned a plain failure into a success claim.
            # The title says which SITE you are on; only the URL says whether
            # anything is playing.
            ok = "youtube.com" in observed_domain and is_youtube_player_url(observed_url)
            return TargetVerificationResult(
                ok,
                0.85 if ok else 0.45,
                expected,
                observed,
                "YouTube watch/player target observed." if ok else "YouTube search was observed, but watch/player state was not confirmed.",
                None if ok else "youtube_activation_unverified",
                None if ok else "Activate the top visible result or reopen the YouTube search.",
                source=source,
            )
        ok = "youtube.com" in observed_domain and ("results" in observed_url or expected_query in observed_url.lower())
        return TargetVerificationResult(ok, 0.85 if ok else 0.45, expected, observed, "YouTube search target matched." if ok else "YouTube search target not confirmed.", None if ok else "youtube_results_unverified", "Reopen the YouTube search.", source=source)

    if expected_domain:
        ok = expected_domain in observed_domain
        query_match = not expected_query or expected_query.replace(" ", "+") in observed_url.lower() or expected_query in observed_title.lower()
        verified = ok and query_match
        return TargetVerificationResult(
            verified,
            0.85 if verified else 0.55 if ok else 0.3,
            expected,
            observed,
            "Target domain and query matched live browser state." if verified else "Target domain matched, but query/result evidence is weak." if ok else "Target domain did not match.",
            None if verified else "target_query_unverified",
            None if verified else "Reopen the target search or ask Eva to switch back to it.",
            source=source,
        )

    if platform == "spotify":
        raw = observation_or_tool_result if isinstance(observation_or_tool_result, dict) else {}
        verified = bool(raw.get("verified"))
        return TargetVerificationResult(
            verified,
            0.8 if verified else 0.35,
            expected,
            observed,
            str(raw.get("message") or "Spotify now-playing metadata was not available."),
            None if verified else "spotify_playback_unverified",
            None if verified else "Ask Eva to retry activation or check the visible Spotify player.",
            source=str(raw.get("source") or "media_session"),
        )

    return TargetVerificationResult(
        False,
        0.2,
        expected,
        observed,
        "No target-specific verification rule matched.",
        "no_verification_rule",
        "Ask user to confirm visible state.",
        source=source,
    )
