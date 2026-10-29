from datetime import datetime, timezone

from backend.eva.news_dashboard.live import build_live_dashboard

NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


def _feeds(feed, limit):
    if feed == "down":
        return {"ok": False, "message": "unreachable"}
    return {"ok": True, "feed": feed.upper(), "url": f"https://example.com/{feed}", "items": [
        {"title": "Shared Story", "link": "", "published": "Thu, 29 Oct 2026 08:00:00 GMT"},
        {"title": f"{feed} exclusive", "link": "", "published": "Mon, 20 Oct 2026 08:00:00 GMT"}]}


def test_same_story_from_two_feeds_is_one_card_citing_both():
    d = build_live_dashboard(feeds=("a", "b"), reader=_feeds, now=NOW)
    shared = [e for e in d.event_cards if e.event_title == "Shared Story"]
    assert len(shared) == 1 and len(shared[0].related_sources) == 2
    assert d.backend_mode == "live_rss" and d.duplicate_grouping_notes


def test_freshness_comes_from_the_published_time():
    d = build_live_dashboard(feeds=("a",), reader=_feeds, now=NOW)
    labels = {e.event_title: e.freshness_label for e in d.event_cards}
    assert labels["Shared Story"] == "fresh" and labels["a exclusive"] == "stale"


def test_unreadable_feed_is_reported_and_all_down_falls_back_to_the_fixture():
    d = build_live_dashboard(feeds=("a", "down"), reader=_feeds, now=NOW)
    assert any("down" in note for note in d.blocked_source_notes)
    d = build_live_dashboard(feeds=("down",), reader=_feeds, now=NOW)
    assert d.backend_mode == "mock_fixture" and d.blocked_source_notes
