from __future__ import annotations

import re
import time
from typing import Any

from ..agent.task_context import get_current_task_context, resolve_followup_reference, update_task_context
from .capabilities import get_capability
from ..browser.web_apps import resolve_web_app, supported_search_sites


_PROVIDER_ALIASES = {
    "openrouter": ("openrouter", "open router"),
    "nvidia_nim": ("nvidia nim", "nim", "nvidia"),
    "gemini": ("gemini", "google ai"),
    "groq": ("groq",),
    "clod": ("clod", "clōd"),
    "ollama": ("ollama", "qwen", "llama", "mistral", "local model"),
}

_CORRECTION_MARKERS = (
    "no i mean",
    "no, i mean",
    "not maps",
    "not that",
    "i mean",
    "built in within",
    "built into you",
)


def _norm(message: str) -> str:
    return re.sub(r"\s+", " ", str(message or "").strip().lower())


def _contains_any(text: str, phrases: tuple[str, ...] | list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _provider_from_text(text: str) -> str | None:
    if "clōd" in text or "clod" in text:
        return "clod"
    for provider, aliases in _PROVIDER_ALIASES.items():
        if any(alias in text for alias in aliases):
            return provider
    return None


def _strip_spotify_query(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip())
    cleaned = re.sub(r"^(please\s+)?(open\s+spotify\s+and\s+)?play\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(please\s+)?search\s+spotify\s+for\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+on\s+spotify$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" .?!")


def _strip_browser_query(value: str, prefixes: tuple[str, ...]) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip())
    for prefix in prefixes:
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    return cleaned.strip(" .?!")


def _save_page_topic(value: str) -> str:
    match = re.search(r"\bsave\s+this\s+page\s+to\s+research\s+topic\s+(.+)$", str(value or ""), flags=re.IGNORECASE)
    return match.group(1).strip(" .?!") if match else ""


def _chatgpt_in_chrome_prompt(value: str) -> str:
    patterns = (
        r"^\s*ask\s+chatgpt\s+(?:on|in)\s+(?:my\s+)?chrome\s+(?:for|to)?\s*(.+)$",
        r"^\s*use\s+chatgpt\s+(?:on|in)\s+(?:my\s+)?chrome\s+to\s+(.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, str(value or ""), flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" .?!")
    return ""


def _whatsapp_message_parts(value: str) -> tuple[str, str] | None:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    patterns = (
        r"^send\s+whatsapp\s+to\s+(.+?)\s+saying\s+(.+)$",
        r"^send\s+(?:a\s+)?whatsapp\s+message\s+to\s+(.+?)\s+saying\s+(.+)$",
        r"^send\s+(?:a\s+)?whatsapp\s+message\s+saying\s+(.+?)\s+to\s+(.+)$",
        r"^send\s+(.+?)\s+to\s+(.+?)\s+on\s+whatsapp$",
        r"^whatsapp\s+(.+?)\s+(.+)$",
    )
    recipient_first = patterns[:2]
    for pattern in recipient_first:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            recipient, message = match.group(1).strip(" .?!'\""), match.group(2).strip(" .?!'\"")
            if message and recipient:
                return recipient, message
    for pattern in patterns[2:]:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            message, recipient = match.group(1).strip(" .?!'\""), match.group(2).strip(" .?!'\"")
            if message and recipient:
                return recipient, message
    return None


def _whatsapp_web_message_parts(value: str) -> tuple[str, str] | None:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    patterns = (
        r"^open\s+whatsapp(?:\s+web)?(?:\s+(?:on|in)\s+chrome)?\s+and\s+send\s+(.+?)\s+to\s+(.+)$",
        r"^open\s+whatsapp(?:\s+web)?\s+on\s+chrome\s+and\s+send\s+(.+?)\s+to\s+(.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            message, recipient = match.group(1).strip(" .?!'\""), match.group(2).strip(" .?!'\"")
            if message and recipient:
                return recipient, message
    return None


def _message_send_followup(text: str) -> bool:
    return text in {
        "open and send the message",
        "open and send it",
        "send it",
        "send now",
        "yes send",
        "confirm send",
        "confirm",
    }


def _youtube_play_query(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    patterns = (
        r"^(?:please\s+)?play\s+(.+?)\s+(?:from|on|in)\s+youtube$",
        r"^(?:please\s+)?open\s+youtube\s+and\s+play\s+(.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" .?!")
    return ""


def _site_domain(site: str) -> str:
    clean = str(site or "").strip().lower()
    return {
        "youtube": "youtube.com",
        "you tube": "youtube.com",
        "github": "github.com",
        "stackoverflow": "stackoverflow.com",
        "stack overflow": "stackoverflow.com",
        "hugging face": "huggingface.co",
        "huggingface": "huggingface.co",
        "google": "google.com",
        "chatgpt": "chatgpt.com",
        "spotify": "spotify",
        "whatsapp": "whatsapp",
    }.get(clean, clean)


def _base_result(
    matched: bool,
    *,
    capability: str | None = None,
    confidence: float = 0.0,
    reason: str = "",
    suggested_route: str | None = None,
    **extra: Any,
) -> dict:
    result = {
        "matched": matched,
        "capability": capability,
        "confidence": round(float(confidence), 2),
        "reason": reason,
        "suggested_route": suggested_route,
    }
    result.update(extra)
    return result


def _remember_correction(text: str, context: dict | None) -> bool:
    if context is None:
        return False
    correction = _contains_any(text, _CORRECTION_MARKERS)
    if correction:
        context["last_misinterpreted_topic"] = None
        context["last_correction_at"] = int(time.time())
    return correction


def classify_capability_intent(message: str, context: dict | None = None) -> dict:
    """Classify broad Eva capabilities without calling a cloud model.

    This layer is intentionally small and semantic. It grounds questions like
    "how are you built" to code/workspace tools, while leaving normal chat and
    broad educational questions to the usual planner/LLM path.
    """

    text = _norm(message)
    if not text:
        return _base_result(False, reason="empty_message")

    if text in {
        "eva v2 status",
        "eva runtime status",
        "eva v2 runtime status",
        "agents status",
        "guardrails status",
        "vector memory status",
        "traces status",
        "automation adapters status",
    }:
        return _base_result(True, capability="eva_v2_runtime", confidence=0.95, reason="Eva v2 runtime status request.", suggested_route=text.replace(" ", "_"))

    correction = _remember_correction(text, context)
    followup = resolve_followup_reference(message, get_current_task_context(context))
    if followup:
        if followup.get("intent") == "play" and followup.get("target_platform") == "youtube":
            query = str(followup.get("target_query") or "")
            update_task_context(context, active_intent="play", target_platform="youtube", target_query=query, target_domain="youtube.com", needs_activation=True, unresolved_followup=message)
            return _base_result(True, capability="browser_agent", confidence=0.93, reason="Follow-up play intent resolved to the remembered YouTube target.", suggested_route="chrome_search_site", site="youtube", query=query, play=True)
        if followup.get("intent") == "play" and followup.get("target_platform") == "spotify":
            query = str(followup.get("target_query") or "")
            update_task_context(context, active_intent="play", target_platform="spotify", target_query=query, needs_activation=True, unresolved_followup=message)
            return _base_result(True, capability="media_music_control", confidence=0.9, reason="Follow-up play intent resolved to the remembered Spotify target.", suggested_route="spotify_play_desktop", query=query)
        if followup.get("intent") == "verify":
            return _base_result(
                True,
                capability="browser_agent",
                confidence=0.9,
                reason="Follow-up verification resolved to the remembered task target.",
                suggested_route="verify_browser_target",
                target_domain=followup.get("target_domain"),
                target_query=followup.get("target_query"),
                target_url=followup.get("target_url"),
            )

    if text.startswith(("search web for ", "web search ", "google ", "look up online ")):
        return _base_result(False, reason="explicit_web_search")

    chatgpt_prompt = _chatgpt_in_chrome_prompt(message)
    if chatgpt_prompt or re.match(r"^\s*ask\s+chatgpt\s+(?:on|in)\s+(?:my\s+)?chrome\b", message, flags=re.IGNORECASE):
        update_task_context(context, user_request=message, active_intent="ask_chatgpt", target_app="chrome", target_platform="chatgpt", target_domain="chatgpt.com", target_url="https://chatgpt.com", target_query=chatgpt_prompt, expected_result="visible ChatGPT response", provenance="pending_chatgpt_in_chrome")
        return _base_result(
            True,
            capability="browser_agent",
            confidence=0.94,
            reason="ChatGPT-in-Chrome workflow requested.",
            suggested_route="chatgpt_in_chrome",
            prompt=chatgpt_prompt,
        )

    if re.search(r"\bdelete\s+(?:my\s+)?downloads\b", text):
        return _base_result(
            True,
            capability="permission_gate",
            confidence=0.95,
            reason="Destructive Downloads folder request.",
            suggested_route="destructive_file_request",
            target="Downloads",
            action="delete",
        )

    whatsapp_web_parts = _whatsapp_web_message_parts(message)
    if whatsapp_web_parts:
        recipient, body = whatsapp_web_parts
        update_task_context(
            context,
            user_request=message,
            active_intent="prepare_message",
            target_app="chrome",
            target_platform="whatsapp",
            target_url="https://web.whatsapp.com",
            target_domain="web.whatsapp.com",
            target_contact=recipient,
            target_message=body,
            expected_result="WhatsApp Web draft prepared; send requires confirmation",
            provenance="message_workflow",
        )
        return _base_result(
            True,
            capability="message_workflow",
            confidence=0.92,
            reason="WhatsApp Web message workflow requested.",
            suggested_route="whatsapp_message_prepare",
            recipient=recipient,
            message=body,
            requested_web=True,
            requires_confirmation=True,
        )

    whatsapp_parts = _whatsapp_message_parts(message)
    if whatsapp_parts:
        recipient, body = whatsapp_parts
        update_task_context(context, user_request=message, active_intent="prepare_message", target_app="whatsapp", target_platform="whatsapp", target_contact=recipient, target_message=body, expected_result="WhatsApp draft prepared; send requires confirmation", provenance="message_workflow")
        return _base_result(
            True,
            capability="message_workflow",
            confidence=0.91,
            reason="WhatsApp message workflow requested.",
            suggested_route="whatsapp_message_prepare",
            recipient=recipient,
            message=body,
            requires_confirmation=True,
        )

    if _message_send_followup(text):
        current = get_current_task_context(context)
        return _base_result(
            True,
            capability="message_workflow",
            confidence=0.9,
            reason="External message send follow-up requires confirmation and verified draft state.",
            suggested_route="message_send_followup",
            recipient=getattr(current, "target_contact", None) if current else None,
            message=getattr(current, "target_message", None) if current else None,
            channel=getattr(current, "target_platform", None) if current else None,
            requires_confirmation=True,
        )

    if text in {"copy current url", "copy current link", "copy this url", "copy this page url"}:
        return _base_result(True, capability="browser_agent", confidence=0.93, reason="Explicit browser URL copy request.", suggested_route="chrome_copy_current_url")

    if text in {"new chrome tab", "open new chrome tab", "new tab"}:
        return _base_result(True, capability="browser_agent", confidence=0.86, reason="Chrome new tab request.", suggested_route="chrome_new_tab")
    if text in {"close chrome tab", "close current tab", "close tab"}:
        return _base_result(True, capability="browser_agent", confidence=0.86, reason="Chrome close tab request.", suggested_route="chrome_close_tab")
    if text in {"reload chrome", "reload page", "refresh page", "refresh chrome"}:
        return _base_result(True, capability="browser_agent", confidence=0.86, reason="Chrome reload request.", suggested_route="chrome_reload")
    if text in {"chrome back", "go back", "back in chrome"}:
        return _base_result(True, capability="browser_agent", confidence=0.84, reason="Chrome back request.", suggested_route="chrome_back")
    if text in {"chrome forward", "go forward", "forward in chrome"}:
        return _base_result(True, capability="browser_agent", confidence=0.84, reason="Chrome forward request.", suggested_route="chrome_forward")
    if text in {"focus address bar", "focus chrome address bar", "chrome address bar"}:
        return _base_result(True, capability="browser_agent", confidence=0.84, reason="Chrome address-bar request.", suggested_route="chrome_focus_address_bar")

    save_topic = _save_page_topic(message)
    if save_topic:
        return _base_result(
            True,
            capability="browser_agent",
            confidence=0.92,
            reason="Save current browser page to research requested.",
            suggested_route="browser_save_page_to_research",
            topic=save_topic,
        )

    site_search_patterns = (
        ("open youtube and search ", "youtube"),
        ("search youtube for ", "youtube"),
        ("search github for ", "github"),
        ("open github and search ", "github"),
        ("search stack overflow for ", "stackoverflow"),
        ("search stackoverflow for ", "stackoverflow"),
        ("search hugging face for ", "hugging face"),
        ("search huggingface for ", "hugging face"),
        ("google search for ", "google"),
    )
    for prefix, site in site_search_patterns:
        if text.startswith(prefix):
            query = _strip_browser_query(message, (prefix,))
            # The query is "everything after the prefix", so a SECOND request
            # rides along inside it: `search github for fastapi and open the
            # first result` searched GitHub for the literal string "fastapi and
            # open the first result" -- a wrong search -- and then answered
            # "Done, searched github for fastapi and open the first result",
            # claiming both halves. A one-shot route cannot honour a second
            # request, so decline the match and let the agent loop take the whole
            # message in as many steps as it needs. Declining is the honest
            # answer: trimming the query alone would fix the search and still
            # drop the second half in silence.
            from ..agent.policies import split_trailing_request

            if split_trailing_request(query)[1]:
                break
            update_task_context(context, user_request=message, active_intent="search", target_app="chrome", target_platform=site, target_query=query, target_domain=_site_domain(site), expected_result=f"{site} search results for {query}", needs_activation=False, provenance="chrome_web_app")
            return _base_result(
                True,
                capability="browser_agent",
                confidence=0.93,
                reason=f"{site} site-search request.",
                suggested_route="chrome_search_site",
                site=site,
                query=query,
            )

    youtube_play = _youtube_play_query(message)
    if youtube_play:
        update_task_context(context, user_request=message, active_intent="play", target_app="chrome", target_platform="youtube", target_query=youtube_play, target_domain="youtube.com", expected_result="youtube watch page or video playback", needs_activation=True, provenance="chrome_web_app")
        return _base_result(
            True,
            capability="browser_agent",
            confidence=0.94,
            reason="Explicit YouTube play intent.",
            suggested_route="chrome_search_site",
            site="youtube",
            query=youtube_play,
            play=True,
        )

    if text.startswith("open ") and _contains_any(text, (" on chrome", " in chrome", " in browser", " on browser")):
        app_text = re.sub(r"^open\s+", "", text)
        app_text = re.sub(r"\s+(on|in)\s+(chrome|browser)$", "", app_text).strip()
        resolved = resolve_web_app(app_text)
        if resolved:
            return _base_result(
                True,
                capability="browser_agent",
                confidence=0.92,
                reason="Cataloged Chrome web app request.",
                suggested_route="chrome_open_web_app",
                app=resolved["key"],
                url=resolved["url"],
            )

    for app_candidate in ("youtube", "github", "openrouter", "nvidia build", "hugging face", "stackoverflow"):
        if text == f"open {app_candidate}":
            resolved = resolve_web_app(app_candidate)
            if resolved:
                return _base_result(
                    True,
                    capability="browser_agent",
                    confidence=0.9,
                    reason="Cataloged web app request.",
                    suggested_route="chrome_open_web_app",
                    app=resolved["key"],
                    url=resolved["url"],
                )

    if text in {"start over", "restart song", "restart current song", "play from beginning"}:
        return _base_result(True, capability="media_music_control", confidence=0.9, reason="Spotify restart-current intent.", suggested_route="spotify_restart_current")

    if text in {"previous song", "previous track", "go to previous song", "play previous song", "play previous track"}:
        return _base_result(True, capability="media_music_control", confidence=0.9, reason="Spotify previous-track intent.", suggested_route="spotify_previous")

    if text in {"next song", "next track", "go to next song", "play next song", "play next track"}:
        return _base_result(True, capability="media_music_control", confidence=0.9, reason="Spotify next-track intent.", suggested_route="spotify_next")

    if "spotify" in text:
        if text.startswith("search spotify for "):
            query = _strip_spotify_query(message)
            update_task_context(context, user_request=message, active_intent="search", target_app="spotify", target_platform="spotify", target_query=query, expected_result=f"Spotify search results for {query}", provenance="tool_result")
            return _base_result(
                True,
                capability="media_music_control",
                confidence=0.94,
                reason="Spotify search intent.",
                suggested_route="spotify_search_desktop",
                query=query,
            )
        if text.startswith(("play ", "open spotify and play ")):
            query = _strip_spotify_query(message)
            update_task_context(context, user_request=message, active_intent="play", target_app="spotify", target_platform="spotify", target_query=query, expected_result=f"Spotify playing {query}", needs_activation=True, provenance="tool_result")
            return _base_result(
                True,
                capability="media_music_control",
                confidence=0.94,
                reason="Spotify play intent.",
                suggested_route="spotify_play_desktop",
                query=query,
            )
        if text in {"pause spotify", "spotify pause", "pause music on spotify"}:
            return _base_result(True, capability="media_music_control", confidence=0.9, reason="Spotify pause intent.", suggested_route="spotify_pause")
        if text in {"next spotify", "spotify next", "next song on spotify", "next track on spotify"}:
            return _base_result(True, capability="media_music_control", confidence=0.9, reason="Spotify next-track intent.", suggested_route="spotify_next")
        if text in {"previous spotify", "spotify previous", "previous song on spotify", "previous track on spotify"}:
            return _base_result(True, capability="media_music_control", confidence=0.9, reason="Spotify previous-track intent.", suggested_route="spotify_previous")

    if text.startswith("play ") and len(text.split()) > 1 and not text.startswith(("play pause", "play/pause")):
        query = _strip_spotify_query(message)
        update_task_context(context, user_request=message, active_intent="play", target_app="spotify", target_platform="spotify", target_query=query, expected_result=f"Spotify playing {query}", needs_activation=True, provenance="tool_result")
        return _base_result(
            True,
            capability="media_music_control",
            confidence=0.82,
            reason="Music play intent without another target; route to Spotify skill.",
            suggested_route="spotify_play_desktop",
            query=query,
        )

    # OpenRouter is Eva's LLM provider. OpenRoute/OpenRouteService is a map
    # routing concept and should not leak into provider diagnostics.
    if "openrouter" in text or "open router" in text:
        if any(word in text for word in ("test", "check", "working", "api", "provider", "built", "within", "you")) or correction:
            return _base_result(
                True,
                capability="provider_diagnostics",
                confidence=0.95,
                reason="OpenRouter is an Eva LLM provider, not a map routing API.",
                suggested_route="provider_status",
                provider="openrouter",
                correction=correction,
            )
    if "openrouteservice" in text or ("openroute" in text and "openrouter" not in text):
        if context is not None:
            context["last_misinterpreted_topic"] = "openroute_maps"
        return _base_result(False, reason="openroute_maps_not_openrouter")

    provider = _provider_from_text(text)
    if provider and any(word in text for word in ("test", "check", "working", "status", "api", "quota", "rate", "provider")):
        return _base_result(
            True,
            capability="provider_diagnostics",
            confidence=0.9,
            reason=f"{provider} provider diagnostics requested.",
            suggested_route="provider_status",
            provider=provider,
        )

    if (
        _contains_any(text, ("full architecture", "your architecture", "eva architecture", "system architecture"))
        or _contains_any(text, ("how are you built", "how were you built", "how are u built", "how were u built"))
        or _contains_any(text, ("what systems do you have", "what systems are built into you", "what capabilities do you have"))
        or _contains_any(text, ("show your system design", "show system design"))
    ):
        return _base_result(
            True,
            capability="self_architecture",
            confidence=0.94,
            reason="Question asks how Eva itself is built.",
            suggested_route="self_architecture_summary",
        )

    if _contains_any(
        text,
        (
            "explain your workflows",
            "explain your agent workflows",
            "how do your workflows work",
            "how do you process commands",
            "explain workflows",
        ),
    ):
        return _base_result(
            True,
            capability="self_architecture",
            confidence=0.93,
            reason="Question asks for Eva's real workflow paths.",
            suggested_route="workflow_explanation",
        )

    if _contains_any(
        text,
        (
            "what part of you is broken",
            "what is broken in you",
            "what is working in you",
            "diagnose yourself",
            "diagnose your brain",
            "system health",
            "health check",
            "full diagnostics",
            "what is degraded",
        ),
    ):
        return _base_result(
            True,
            capability="self_diagnostics",
            confidence=0.92,
            reason="User asked for Eva subsystem/provider health.",
            suggested_route="health_summary",
        )

    if text.startswith(("where is ", "where are ")) and _contains_any(
        text,
        ("implemented", "provider", "agent", "runner", "router", "browser", "desktop", "nim", "research", "voice", "code", "tool"),
    ):
        return _base_result(True, capability="code_intelligence", confidence=0.86, reason="Implementation location requested.", suggested_route="code_explain_feature")

    if text.startswith(("find symbol ", "plan change ", "explain feature ", "debug this", "what does this error mean")):
        route = "code_find_symbol" if text.startswith("find symbol ") else "code_plan_change" if text.startswith("plan change ") else "code_debug_traceback" if "debug" in text or "error" in text else "code_explain_feature"
        return _base_result(True, capability="code_intelligence", confidence=0.86, reason="Code intelligence request.", suggested_route=route)

    if text.startswith(("what do we know about ", "what saved sources", "summarize research topic ")) or re.match(r"^research\s+[^:]+", text):
        return _base_result(True, capability="research_knowledge", confidence=0.82, reason="Research knowledge request.", suggested_route="research_recall")

    if _contains_any(text, ("what page am i on", "what website is open", "current browser page", "summarize this page", "extract links from this page")):
        route = "browser_summarize_page" if "summarize" in text else "browser_extract_links" if "extract links" in text else "browser_current_page"
        return _base_result(True, capability="browser_agent", confidence=0.9, reason="Browser state/page request.", suggested_route=route)

    if _contains_any(text, ("what window am i on", "active window", "what app am i on")):
        return _base_result(True, capability="desktop_agent", confidence=0.9, reason="Active desktop window requested.", suggested_route="window_active")

    if text in {"what is open", "what windows are open", "list open windows", "what apps are open"}:
        return _base_result(True, capability="desktop_agent", confidence=0.88, reason="Open desktop windows requested.", suggested_route="window_list")

    if _contains_any(text, ("look at my screen", "analyze my screen", "what is on my screen", "what error is visible")):
        return _base_result(True, capability="screen_vision", confidence=0.88, reason="Explicit one-shot screen understanding requested.", suggested_route="analyze_screen")

    return _base_result(False, reason="no_capability_match")


def capability_metadata(name: str) -> dict | None:
    capability = get_capability(name)
    if capability is None:
        return None
    return {
        "name": capability.name,
        "description": capability.description,
        "trigger_concepts": list(capability.trigger_concepts),
        "related_tools": list(capability.related_tools),
        "example_intents": list(capability.example_intents),
        "route_type": capability.route_type,
    }
