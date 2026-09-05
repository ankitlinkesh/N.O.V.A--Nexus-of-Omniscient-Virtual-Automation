from __future__ import annotations

import time

from typing import Any

from ..agent.target_verifier import verify_target
from ..agent.task_context import get_current_task_context, update_task_context
from ..privacy.cloud_context_firewall import CloudContextFirewall, CloudContextRequest
from ..research.store import ResearchStore
from .controller import (
    chrome_back as controller_chrome_back,
    chrome_close_tab as controller_chrome_close_tab,
    chrome_copy_current_url_to_clipboard,
    chrome_focus_address_bar as controller_chrome_focus_address_bar,
    chrome_forward as controller_chrome_forward,
    chrome_activate_first_visible_result,
    discover_current_url,
    chrome_new_tab as controller_chrome_new_tab,
    chrome_reload as controller_chrome_reload,
    get_browser_status,
    open_search,
    open_url,
    open_url_in_chrome,
)
from .reader import current_page_observation, extract_links_from_page, summarize_current_page
from .safety import normalize_public_url
from .state import current_state
from .web_apps import build_site_search_url, resolve_web_app


def _verification_user_message(result: Any) -> str:
    expected = getattr(result, "expected_target", {}) or {}
    platform = str(expected.get("platform") or expected.get("domain") or "target").strip()
    platform_name = platform or "target"
    platform_lc = platform_name.lower()
    query = " ".join(str(expected.get("query") or "").strip().split())
    target_label = platform_name
    if platform_lc == "youtube":
        target_label = "YouTube"
    elif platform_lc == "github":
        target_label = "GitHub"
    elif platform_lc in {"hugging face", "huggingface"}:
        target_label = "Hugging Face"
    elif platform_lc == "chatgpt":
        target_label = "ChatGPT"

    if getattr(result, "verified", False):
        if target_label == "YouTube" and query and not expected.get("needs_activation"):
            return f"Verified. The YouTube search results for {query} are open."
        if query:
            return f"Verified. The {target_label} target for {query} is open."
        return f"Verified. The {target_label} target is open."

    failure = str(getattr(result, "failure_reason", "") or "")
    source = str(getattr(result, "source", "") or "")
    stale = bool(getattr(result, "stale", False))
    if stale or failure == "cache_only_target_unverified" or source == "cache":
        if target_label == "YouTube" and query:
            return f"I can't verify the YouTube results right now because I couldn't read the live browser page."
        return f"I can't verify the {target_label} target right now because I couldn't read the live browser page."
    if "active Chrome tab is Eva" in failure:
        if target_label == "YouTube" and query:
            return "I can't verify the YouTube results because the active Chrome tab is not YouTube. I can reopen the YouTube search if you want."
        return f"I can't verify the {target_label} results because the active Chrome tab is not {target_label}. I can reopen the target page if you want."
    if failure in {"active_target_mismatch", "target_query_unverified", "youtube_results_unverified", "youtube_activation_unverified"}:
        if target_label == "YouTube" and query:
            return "I can't verify the YouTube results because the active Chrome tab is not YouTube. I can reopen the YouTube search if you want."
        return f"I couldn't verify the {target_label} target from the current browser page. I can reopen it if you want."
    if target_label == "YouTube" and query:
        return f"I couldn't verify the YouTube results for {query} right now."
    return f"I couldn't verify the {target_label} target right now."


def browser_status() -> dict[str, Any]:
    return get_browser_status()


def browser_open_url(url: str) -> dict[str, Any]:
    return open_url(url)


def browser_search(query: str) -> dict[str, Any]:
    return open_search(query)


def browser_current_page() -> dict[str, Any]:
    return current_page_observation(include_tabs=False, include_page_summary=False, include_links=False)


def browser_summarize_page(url: str = "") -> dict[str, Any]:
    return summarize_current_page(url or None)


def browser_extract_links(url: str = "", limit: int = 40) -> dict[str, Any]:
    return extract_links_from_page(url or None, limit=limit)


def browser_save_page_to_research(topic: str, url: str = "") -> dict[str, Any]:
    clean_topic = str(topic or "").strip()
    if not clean_topic:
        return {"ok": False, "error": "topic_required"}
    summary = summarize_current_page(url or None)
    if not summary.get("ok"):
        return {
            "ok": False,
            "topic": clean_topic,
            "error": summary.get("error") or "page_summary_unavailable",
            "safety_blocked": bool(summary.get("safety_blocked")),
            "summary": summary.get("summary") or "I could not save this page because it was not safely readable.",
        }
    store = ResearchStore()
    saved = store.save_web_results(
        clean_topic,
        f"current browser page: {summary.get('current_title') or summary.get('current_url')}",
        [
            {
                "title": summary.get("current_title") or "Current browser page",
                "url": summary.get("current_url") or "",
                "source": "browser_current_page",
                "snippet": summary.get("page_summary") or "",
                "content_summary": summary.get("page_summary") or "",
                "credibility_note": "Saved from an explicit current-page browser request.",
            }
        ],
        source="browser_current_page",
    )
    return {
        "ok": True,
        "topic": clean_topic,
        "saved_count": len(saved),
        "saved_results": saved,
        "message": f"Saved the current page to research topic {clean_topic}.",
    }


def browser_observe(include_tabs: bool = False, include_page_summary: bool = False, include_links: bool = False) -> dict[str, Any]:
    return current_page_observation(
        include_tabs=bool(include_tabs),
        include_page_summary=bool(include_page_summary),
        include_links=bool(include_links),
    )


def chrome_open_web_app(app: str) -> dict[str, Any]:
    resolved = resolve_web_app(app)
    if not resolved:
        return {"ok": False, "error": "unsupported_web_app", "app": app}
    result = open_url_in_chrome(str(resolved["url"]))
    update_task_context(
        user_request=f"open {resolved['name']} in Chrome",
        active_intent="open_web_app",
        target_app="chrome",
        target_platform=str(resolved["key"]),
        target_url=str(resolved["url"]),
        target_domain=str(resolved["url"]).replace("https://", "").split("/")[0],
        target_title=str(resolved["name"]),
        expected_result=f"{resolved['name']} open in Chrome",
        last_tool="chrome_open_web_app",
        provenance="chrome_web_app",
    )
    return {
        **result,
        "app": resolved["key"],
        "app_name": resolved["name"],
        "message": f"Done, {resolved['name']} is open in Chrome.",
    }


def open_web_app_and_verify(app: str) -> dict[str, Any]:
    return chrome_open_web_app(app)


def chrome_search_site(site: str, query: str, play: bool = False) -> dict[str, Any]:
    search_url = build_site_search_url(site, query)
    clean_query = " ".join(str(query or "").strip().split())
    clean_site = str(site or "").strip().lower()
    domain = {
        "youtube": "youtube.com",
        "github": "github.com",
        "google": "google.com",
        "stackoverflow": "stackoverflow.com",
        "stack overflow": "stackoverflow.com",
        "hugging face": "huggingface.co",
        "huggingface": "huggingface.co",
    }.get(clean_site, clean_site)
    update_task_context(
        user_request=f"search {site} for {clean_query}",
        active_intent="play" if play else "search",
        target_app="chrome",
        target_platform="youtube" if clean_site in {"youtube", "you tube"} else clean_site,
        target_query=clean_query,
        target_url=search_url,
        target_domain=domain,
        expected_result=("youtube watch page or video playback" if play and clean_site in {"youtube", "you tube"} else f"{site} search results for {clean_query}"),
        needs_activation=bool(play),
        last_tool="chrome_search_site",
        provenance="chrome_web_app",
    )
    wants_play = bool(play) and str(site or "").strip().lower() in {"youtube", "you tube"}

    # When the ask is "play X", go STRAIGHT to the video. Opening the results
    # page first and then the watch page left the user with two tabs of the same
    # song -- the search page was only ever a stepping stone to a click that no
    # longer happens, so once a watch URL resolves there is nothing to search
    # for. The results page is still opened when resolution fails, because then
    # the keyboard fallback needs it.
    watch_url = _resolve_youtube_watch_url(clean_query) if wants_play else None
    if watch_url:
        result = open_url_in_chrome(watch_url)
        activation = _confirm_youtube_playback(watch_url, clean_query) if _ok_dict(result) else None
    else:
        result = open_url_in_chrome(search_url)
        activation = activate_top_youtube_result(clean_query) if wants_play else None
    if activation is not None and activation.get("verified"):
        message = str(activation.get("message") or f"Done, I opened the top YouTube result for {clean_query}.")
    elif activation is not None:
        message = f"I opened YouTube results for {clean_query}, but I couldn't safely activate the top result."
    else:
        message = f"Done, searched {site} for {query} in Chrome."
    return {
        **result,
        "site": site,
        "query": clean_query,
        "search_url": search_url,
        "play_requested": bool(play),
        "activation": activation,
        "play_attempt": activation,
        "message": message,
        "ui_events": [
            {"type": "verifying_target", "target": {"site": site, "query": clean_query}},
            *([{"type": "executing_visible_action", "action": "activate_top_youtube_result"}] if activation is not None else []),
        ],
    }


def search_site_and_verify(site: str, query: str) -> dict[str, Any]:
    result = chrome_search_site(site, query, play=False)
    verification = verify_browser_target()
    return {**result, "target_verification": verification}


_YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"})


def _is_youtube_watch_url(url: str) -> bool:
    """A player URL, on a YouTube host. Both halves matter.

    The host check is the security half: candidate URLs come from a web search,
    which is untrusted content, and "the top result for what the user asked for"
    is exactly the position an attacker would want to occupy. Restricting to
    YouTube's own hosts means a poisoned result can at worst send the user to the
    wrong VIDEO, never to an arbitrary site.
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(str(url or ""))
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        return False
    path_and_query = f"{parsed.path}?{parsed.query}".lower()
    return host == "youtu.be" or "/watch" in path_and_query or "/shorts/" in path_and_query


def _resolve_youtube_watch_url(query: str) -> str | None:
    """Find a real watch URL, so playing needs no clicking at all.

    The keyboard route below sends one TAB then ENTER, which on a YouTube results
    page lands on "Skip navigation" rather than the first video -- measured, it
    activated nothing every time while reporting ok. Rather than guess at a tab
    count that changes whenever YouTube reshuffles its layout, resolve the video
    by search and open its URL: deterministic, verifiable (the URL either is a
    player page or is not), and it needs no synthetic input at all.
    """
    try:
        from ..tools.tavily_search import tavily_search_sync

        result = tavily_search_sync(f"{query} site:youtube.com")
    except Exception:
        return None
    if not isinstance(result, dict) or not result.get("ok"):
        return None
    for item in result.get("results") or []:
        url = str((item or {}).get("url") or "")
        if _is_youtube_watch_url(url):
            return url
    return None


def _ok_dict(result: Any) -> bool:
    return isinstance(result, dict) and bool(result.get("ok"))


def _await_player_url(timeout: float = 6.0, interval: float = 0.4) -> dict[str, Any]:
    """Read the live URL, giving Chrome time to actually navigate first.

    The first version read it immediately after opening the tab and usually saw
    the PREVIOUS page, so a video that opened fine was reported as "I couldn't
    confirm it is playing". That is not a cautious verification, it is a race:
    the answer depended on whether Chrome had finished navigating within a few
    milliseconds. Polling until the URL becomes a player -- or the timeout
    expires -- makes an unverified result mean "it really did not get there",
    which is the only thing a caution is worth reporting for.
    """
    from ..agent.target_verifier import is_youtube_player_url

    deadline = time.monotonic() + max(0.0, float(timeout))
    observed = discover_current_url()
    while time.monotonic() < deadline:
        if is_youtube_player_url(str((observed or {}).get("url") or "")):
            return observed
        time.sleep(interval)
        observed = discover_current_url()
    return observed


def _confirm_youtube_playback(watch_url: str, query: str) -> dict[str, Any]:
    """Record and verify that the player page is really what is open now."""
    observed = _await_player_url()
    context = update_task_context(
        active_intent="play",
        target_platform="youtube",
        target_query=query,
        target_domain="youtube.com",
        target_url=watch_url,
        expected_result="youtube watch page or visible player",
        needs_activation=True,
        last_action="open_youtube_watch_url",
        last_tool="chrome_activate_top_youtube_result",
        last_observation=observed,
    )
    verification = verify_target(context, observed)
    return {
        "ok": True,
        "activated": True,
        "method": "resolved_watch_url",
        "watch_url": watch_url,
        "verified": verification.verified,
        "observed_url": str((observed or {}).get("url") or ""),
        "message": (
            f"Playing the top YouTube result for {query}."
            if verification.verified
            else f"I opened a YouTube video page for {query}, but could not confirm the player state."
        ),
        "ui_events": [
            {"type": "locating_ui_target", "target": "top_youtube_result"},
            {"type": "executing_visible_action", "action": "open_watch_url"},
        ],
    }


def activate_top_youtube_result(query: str, task_id: str | None = None) -> dict[str, Any]:
    clean = " ".join(str(query or "").strip().split())
    if not clean:
        return {"ok": False, "error": "query_required", "message": "I need a YouTube query before activating a result."}

    # Resolve-and-open first, because it actually works where the keyboard route
    # never did. The keyboard attempt is kept below as the fallback for when no
    # watch URL can be resolved (no search provider configured, or nothing but
    # playlist and channel links came back).
    # Already playing? Then do nothing. Without this, a caller that searches with
    # play=True and then also calls this tool opens the SAME video in a second
    # tab -- which is exactly what the user saw: "it worked but nova opened two
    # tabs playing the same song". Opening a tab is not idempotent, so the check
    # has to happen before the open, not be cleaned up after it.
    from ..agent.target_verifier import is_youtube_player_url

    current = discover_current_url()
    current_url = str((current or {}).get("current_url") or (current or {}).get("url") or "")
    if is_youtube_player_url(current_url):
        return {
            "ok": True,
            "activated": True,
            "method": "already_playing",
            "watch_url": current_url,
            "verified": True,
            "observed_url": current_url,
            "message": f"That is already playing for {clean}; I left it alone rather than opening it twice.",
            "ui_events": [{"type": "verifying_target", "target": {"platform": "youtube", "query": clean}}],
        }

    watch_url = _resolve_youtube_watch_url(clean)
    if watch_url:
        opened = open_url_in_chrome(watch_url)
        if _ok_dict(opened):
            return _confirm_youtube_playback(watch_url, clean)

    action = chrome_activate_first_visible_result()
    if not action.get("ok"):
        return {
            "ok": False,
            "activated": False,
            "activation": action,
            "message": f"I opened YouTube results for {clean}, but I couldn't safely activate the top result.",
            "verification_note": "No random coordinates were clicked; bounded visible keyboard activation failed.",
            "ui_events": [
                {"type": "locating_ui_target", "target": "top_youtube_result"},
                {"type": "verification_failed", "target": "youtube_activation"},
            ],
        }
    observed = discover_current_url()
    context = update_task_context(
        active_intent="play",
        target_platform="youtube",
        target_query=clean,
        target_domain="youtube.com",
        expected_result="youtube watch page or visible player",
        needs_activation=True,
        last_action="activate_top_youtube_result",
        last_tool="chrome_activate_top_youtube_result",
        last_observation=observed,
    )
    verification = verify_target(context, observed)
    return {
        "ok": True,
        "activated": True,
        "activation": action,
        "verified": verification.verified,
        "confidence": verification.confidence,
        "url": observed.get("url"),
        "target_verification": verification.as_dict(),
        "message": (
            f"Done, I opened the top YouTube result for {clean}."
            if verification.verified
            else f"I opened YouTube results for {clean}, but I couldn't safely verify playback yet."
        ),
        "verification_note": "Verification expects a youtube.com/watch URL or visible player evidence; cache-only state is not accepted.",
        "ui_events": [
            {"type": "locating_ui_target", "target": "top_youtube_result"},
            {"type": "executing_visible_action", "action": "bounded_keyboard_activation"},
            {"type": "verifying_target", "target": "youtube_watch"},
            {"type": "verification_passed" if verification.verified else "verification_failed", "confidence": verification.confidence},
        ],
    }


def activate_top_search_result() -> dict[str, Any]:
    action = chrome_activate_first_visible_result()
    observed = discover_current_url() if action.get("ok") else {}
    return {"ok": bool(action.get("ok")), "activation": action, "observation": observed, "message": "Activated the top visible browser result." if action.get("ok") else "I could not safely activate the top visible result."}


def verify_browser_target(session_context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = get_current_task_context(session_context)
    observed = discover_current_url()
    result = verify_target(context, observed)
    user_message = _verification_user_message(result)
    if context is not None:
        update_task_context(session_context, last_verification=result.as_dict(), last_observation=observed)
    return {
        "ok": result.verified,
        "verified": result.verified,
        "confidence": result.confidence,
        "expected_target": result.expected_target,
        "observed_target": result.observed_target,
        "evidence": result.evidence,
        "failure_reason": result.failure_reason,
        "suggested_repair": result.suggested_repair,
        "source": result.source,
        "stale": result.stale,
        "user_message": user_message,
        "message": user_message,
        "internal_error": result.failure_reason,
        "ui_events": [
            {"type": "verifying_target", "expected_target": result.expected_target},
            {"type": "verification_passed" if result.verified else "verification_failed", "confidence": result.confidence},
            *([{"type": "repair_suggested", "suggestion": result.suggested_repair}] if result.suggested_repair else []),
        ],
    }


def recover_browser_target(session_context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = get_current_task_context(session_context)
    if context is None:
        return {"ok": False, "error": "no_task_context", "message": "I do not have a remembered browser target to recover."}
    if context.target_url:
        result = open_url_in_chrome(context.target_url)
        return {"ok": bool(result.get("ok")), "message": "Reopened the remembered target page.", "result": result}
    if context.target_platform and context.target_query:
        return chrome_search_site(context.target_platform, context.target_query, play=context.needs_activation)
    return {"ok": False, "error": "target_incomplete", "message": "I remember the task, but not enough target detail to recover it."}


def ask_chatgpt_in_chrome(prompt: str, user_confirmed_private_cloud_share: bool = False) -> dict[str, Any]:
    clean = " ".join(str(prompt or "").strip().split())
    update_task_context(
        user_request=f"ask ChatGPT in Chrome {clean}",
        active_intent="ask_chatgpt",
        target_app="chrome",
        target_platform="chatgpt",
        target_url="https://chatgpt.com",
        target_domain="chatgpt.com",
        expected_result="visible ChatGPT response",
        last_tool="chatgpt_in_chrome",
        provenance="pending_chatgpt_in_chrome",
    )
    private_hint = bool(clean and ("c:\\" in clean.lower() or "local file" in clean.lower() or "my document" in clean.lower() or "screenshot" in clean.lower()))
    firewall = CloudContextFirewall()
    cloud = firewall.prepare(
        CloudContextRequest(
            user_request=clean or "ask ChatGPT",
            candidate_context={"prompt": clean},
            context_sources=["user_request"],
            purpose="chatgpt_in_chrome_prompt",
            contains_private_content=private_hint,
            contains_raw_file=private_hint,
            contains_raw_chat=False,
            contains_raw_screenshot=False,
            user_confirmed_private_cloud_share=user_confirmed_private_cloud_share,
        )
    )
    if cloud.needs_confirmation:
        return {
            "ok": False,
            "requires_confirmation": True,
            "message": cloud.confirmation_message,
            "blocked_reason": cloud.blocked_reason,
            "ui_events": cloud.ui_events,
            "provenance": "not_executed",
        }
    return {
        "ok": False,
        "workflow_available": False,
        "message": "I can open ChatGPT, but I can't yet reliably type, submit, and read the result inside Chrome on this machine.",
        "provenance": "not_executed",
    }


def chrome_copy_current_url() -> dict[str, Any]:
    return chrome_copy_current_url_to_clipboard()


def chrome_new_tab() -> dict[str, Any]:
    return controller_chrome_new_tab()


def chrome_close_tab() -> dict[str, Any]:
    return controller_chrome_close_tab()


def chrome_reload() -> dict[str, Any]:
    return controller_chrome_reload()


def chrome_back() -> dict[str, Any]:
    return controller_chrome_back()


def chrome_forward() -> dict[str, Any]:
    return controller_chrome_forward()


def chrome_focus_address_bar() -> dict[str, Any]:
    return controller_chrome_focus_address_bar()


def browser_open_result_and_verify(url: str = "", result_index: int | None = None) -> dict[str, Any]:
    target = str(url or "").strip()
    index = int(result_index or 0)
    if not target and index > 0:
        results = current_state().get("last_results") or []
        if isinstance(results, list) and 1 <= index <= len(results):
            item = results[index - 1]
            if isinstance(item, dict):
                target = str(item.get("url") or "").strip()
    target = normalize_public_url(target)
    result = open_url_in_chrome(target)
    return {
        **result,
        "result_index": index or None,
        "message": "Opened the result in Chrome." if result.get("ok") else "I could not open that result safely.",
    }
