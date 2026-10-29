from backend.eva.browser import skills


def _fake(url, title, *, ok=True, stale=False):
    return lambda: {"ok": ok, "stale": stale, "url": url, "title": title}


WATCH = "https://www.youtube.com/watch?v=abc123"


def test_title_matches_query_ignores_filler_words():
    assert skills._title_matches_query("Interstellar | Official Trailer - YouTube", "the interstellar trailer")
    assert not skills._title_matches_query("You're Losing Gunfights in Valorant - YouTube", "the interstellar trailer")
    assert not skills._title_matches_query("anything", "the")


def test_unrelated_open_video_is_not_already_playing(monkeypatch):
    monkeypatch.setattr(skills, "discover_current_url", _fake(WATCH, "You're Losing Gunfights in Valorant - YouTube"))
    monkeypatch.setattr(skills, "_resolve_youtube_watch_url", lambda q: None)
    monkeypatch.setattr(skills, "chrome_activate_first_visible_result", lambda: {"ok": False})
    assert skills.activate_top_youtube_result("the interstellar trailer").get("method") != "already_playing"


def test_stale_cache_is_not_trusted(monkeypatch):
    monkeypatch.setattr(skills, "discover_current_url", _fake(WATCH, "Interstellar Trailer - YouTube", ok=False, stale=True))
    monkeypatch.setattr(skills, "_resolve_youtube_watch_url", lambda q: None)
    monkeypatch.setattr(skills, "chrome_activate_first_visible_result", lambda: {"ok": False})
    assert skills.activate_top_youtube_result("interstellar trailer").get("method") != "already_playing"


def test_matching_fresh_video_is_left_alone(monkeypatch):
    monkeypatch.setattr(skills, "discover_current_url", _fake(WATCH, "Interstellar | Official Trailer - YouTube"))
    assert skills.activate_top_youtube_result("the interstellar trailer")["method"] == "already_playing"


class _Resp:
    def __init__(self, status, text):
        self.status_code, self.text = status, text


def test_top_video_is_read_from_the_results_page_without_a_search_api(monkeypatch):
    import httpx

    page = '{"adRenderer":{}}...{"videoRenderer":{"videoId":"zSWdZVtXT7E","title":{}}} {"videoRenderer":{"videoId":"AAAAAAAAAAA"}}'
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(200, page))
    assert skills._youtube_top_video_from_results("interstellar trailer") == "https://www.youtube.com/watch?v=zSWdZVtXT7E"


def test_results_page_failure_resolves_nothing(monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(429, "x"))
    assert skills._youtube_top_video_from_results("anything") is None

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", boom)
    assert skills._youtube_top_video_from_results("anything") is None
