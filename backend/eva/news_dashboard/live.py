"""Live news dashboard: public RSS headlines folded into the same cards the mock dashboard uses.

Read-only and public-URL only (the feed reader refuses private hosts). Headline text is untrusted data and is shown,
never obeyed. When no feed can be read, the caller gets the mock dashboard back, labelled as such.
"""
from __future__ import annotations

import email.utils
import hashlib
from datetime import datetime, timezone

from .deduplication import duplicate_group_id
from .freshness import freshness_label
from .mock_feeds import build_mock_dashboard
from .models import EventCard, NewsDashboard, SourceCard
from .reliability import reliability_note
from .topic_model import normalize_topic

DEFAULT_FEEDS = ("bbc", "npr", "the hindu")
ITEMS_PER_FEED = 6


def _age_hours(published: str, now: datetime) -> int | None:
    try:
        when = email.utils.parsedate_to_datetime(published)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(int((now - when).total_seconds() // 3600), 0)


def build_live_dashboard(topic: str = "world events", feeds: tuple[str, ...] = DEFAULT_FEEDS, *, reader=None, now: datetime | None = None) -> NewsDashboard:
    if reader is None:
        from ..tools.info_tools import rss_headlines as reader  # noqa: N813
    now = now or datetime.now(timezone.utc)
    topic = normalize_topic(topic)
    sources: list[SourceCard] = []
    events: list[EventCard] = []
    groups: dict[str, list[str]] = {}
    blocked: list[str] = []
    for feed in feeds:
        result = reader(feed, ITEMS_PER_FEED)
        if not result.get("ok"):
            blocked.append(f"{feed}: {result.get('message') or result.get('error') or 'unreadable'}")
            continue
        source_id = "src-" + hashlib.sha256(str(result.get("url")).encode("utf-8")).hexdigest()[:8]
        ages = [a for a in (_age_hours(i.get("published", ""), now) for i in result["items"]) if a is not None]
        label = freshness_label(min(ages)) if ages else "unknown"
        sources.append(SourceCard(source_id, str(result.get("feed") or feed), "wire", str(result.get("url")), label, reliability_note("wire"),
                                  f"{len(result['items'])} headlines read.", "title, public URL, published time", "public_feed_read_only", ""))
        for item in result["items"]:
            gid = duplicate_group_id(item["title"])
            groups.setdefault(gid, []).append(source_id)
            age = _age_hours(item.get("published", ""), now)
            events.append(EventCard(f"event-{gid[-6:]}-{source_id[-4:]}", item["title"], f"Headline from {result.get('feed') or feed}.", (source_id,),
                                    freshness_label(age) if age is not None else "unknown", "single-source headline; corroborate before relying on it",
                                    gid, item.get("link", ""), "Headline text is untrusted data with no instruction authority."))
    if not sources:
        fallback = build_mock_dashboard(topic)
        return NewsDashboard(**{**fallback.__dict__, "backend_mode": "mock_fixture",
                                "blocked_source_notes": tuple(blocked) or fallback.blocked_source_notes,
                                "query_summary": f"Live feeds unavailable; showing the fixture for {topic}."})
    seen: set[str] = set()
    unique = []
    for event in events:  # same story from several feeds becomes one card that cites each source
        if event.duplicate_group_id in seen:
            continue
        seen.add(event.duplicate_group_id)
        related = tuple(dict.fromkeys(groups[event.duplicate_group_id]))
        unique.append(EventCard(**{**event.__dict__, "related_sources": related,
                                   "confidence_uncertainty_label": "reported by multiple feeds" if len(related) > 1 else event.confidence_uncertainty_label}))
    repeated = tuple(f"{gid}: {len(set(ids))} feeds" for gid, ids in groups.items() if len(set(ids)) > 1)
    return NewsDashboard(
        "news-live-" + hashlib.sha256(topic.lower().encode("utf-8")).hexdigest()[:8], topic, f"{len(unique)} headlines from {len(sources)} public feeds.",
        "live_rss", tuple(sources), tuple(unique), tuple(s.freshness_label for s in sources), tuple(s.reliability_note for s in sources), repeated,
        ("No source is absolute truth; most headlines come from a single feed and are uncorroborated.",),
        ("Feed text is untrusted data.", "Public feeds only; private hosts refused."), tuple(blocked), tuple(s.citation_metadata for s in sources),
        "ready_live_dashboard", "No unrestricted crawling.", "No login/session/cookie/profile access.", "No browser control.",
        "No live LLM call was made.", "Read-only public RSS fetch only.", "Phase 12L remains a gated write path.")


def format_live_dashboard(topic: str = "world events") -> str:
    d = build_live_dashboard(topic)
    lines = ["News / Web Intelligence Dashboard (live)", f"Topic: {d.topic}", f"Mode: {d.backend_mode}", d.query_summary,
             f"Sources: {', '.join(f'{s.source_title} [{s.freshness_label}]' for s in d.source_cards)}", ""]
    titles = {s.source_id: s.source_title for s in d.source_cards}
    for event in d.event_cards[:12]:
        also = f" (also: {', '.join(titles.get(i, i) for i in event.related_sources[1:])})" if len(event.related_sources) > 1 else ""
        lines.append(f"- [{event.freshness_label}] {event.event_title}{also}")
    if d.blocked_source_notes:
        lines += ["", "Could not read: " + "; ".join(d.blocked_source_notes)]
    lines += ["", d.uncertainty_notes[0], d.no_unrestricted_crawling_statement, d.no_login_session_cookie_profile_statement, d.no_browser_control_statement]
    return "\n".join(lines)
