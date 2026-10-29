"""Weather, RSS, YouTube transcript and OCR tools (network and OCR engine faked)."""

import httpx
import pytest

from backend.eva.core.fast_commands import maybe_handle_fast_command
from backend.eva.core.routing_mode import must_stay_deterministic
from backend.eva.threat_defense.taint import source_type_for_tool
from backend.eva.tools import info_tools
from backend.eva.tools.registry import ToolRegistry


def test_weather_questions_are_parsed_and_bare_ones_are_not():
    assert info_tools.parse_weather_request("weather in chennai") == ("chennai", 1)
    assert info_tools.parse_weather_request("what's the weather in New York today") == ("New York", 1)
    assert info_tools.parse_weather_request("forecast for mumbai") == ("mumbai", 3)
    assert info_tools.parse_weather_request("how is the weather in delhi tomorrow") == ("delhi", 2)
    for text in ("weather", "what's the weather", "weather like", "weather in", "play the weather song", "temperature me"):
        assert info_tools.parse_weather_request(text) is None, text


def _fake_get(monkeypatch, geocode, forecast):
    def get(url, params=None, **kw):
        body = geocode if "geocoding" in url else forecast
        request = httpx.Request("GET", url)
        return httpx.Response(200, json=body, request=request)

    monkeypatch.setattr(info_tools.httpx, "get", get)


GEO = {"results": [{"name": "Chennai", "admin1": "Tamil Nadu", "country": "India", "latitude": 13.08, "longitude": 80.27}]}
FORECAST = {
    "current": {"temperature_2m": 27.1, "apparent_temperature": 30.9, "relative_humidity_2m": 76, "weather_code": 0, "wind_speed_10m": 9.3},
    "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h"},
    "daily": {"time": ["2026-10-29"], "weather_code": [3], "temperature_2m_max": [32.7], "temperature_2m_min": [24.9], "precipitation_probability_max": [2]},
}


def test_weather_summary_names_place_conditions_and_range(monkeypatch):
    _fake_get(monkeypatch, GEO, FORECAST)
    result = info_tools.weather_forecast("chennai")
    assert result["ok"] and "Chennai, Tamil Nadu, India: 27.1°C, clear sky" in result["summary"] and "24.9–32.7" in result["summary"]


def test_unknown_place_and_unreachable_service_are_reported(monkeypatch):
    _fake_get(monkeypatch, {"results": []}, {})
    assert info_tools.weather_forecast("zzzz")["error"] == "place_not_found"

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(info_tools.httpx, "get", boom)
    assert info_tools.weather_forecast("chennai")["error"] == "weather_unavailable"
    assert info_tools.weather_forecast("  ")["error"] == "empty_place"


def test_weather_command_runs_without_a_model(monkeypatch):
    _fake_get(monkeypatch, GEO, FORECAST)
    reply = maybe_handle_fast_command("what's the weather in chennai", ToolRegistry(), {})
    assert reply and "Chennai" in reply[0] and reply[1] == "weather-tool"
    monkeypatch.setenv("EVA_ROUTING", "llm_first")
    assert must_stay_deterministic("weather in chennai") is True
    assert must_stay_deterministic("what's a good laptop") is False


def test_rss_refuses_private_hosts_and_bad_schemes_without_fetching(monkeypatch):
    monkeypatch.setattr(info_tools.httpx, "stream", lambda *a, **k: (_ for _ in ()).throw(AssertionError("fetched")))
    assert info_tools.rss_headlines("http://127.0.0.1:8080/")["error"] == "private_host"
    assert info_tools.rss_headlines("http://192.168.0.1/feed")["error"] == "private_host"
    assert info_tools.rss_headlines("ftp://example.com/feed")["error"] == "bad_feed_url"


def test_rss_parses_entries_from_a_feed(monkeypatch):
    xml = b"<?xml version='1.0'?><rss version='2.0'><channel><title>Demo</title><item><title>First  story</title><link>https://e.x/1</link></item><item><title>Second</title></item></channel></rss>"

    class Stream:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_bytes(self): yield xml

    monkeypatch.setattr(info_tools.httpx, "stream", lambda *a, **k: Stream())
    result = info_tools.rss_headlines("https://example.com/feed", limit=5)
    assert result["ok"] and [i["title"] for i in result["items"]] == ["First story", "Second"] and result["feed"] == "Demo"


def test_youtube_transcript_rejects_non_links_and_reports_failures(monkeypatch):
    assert info_tools.youtube_transcript("hello there")["error"] == "bad_video"

    import youtube_transcript_api as lib

    class Api:
        def fetch(self, video_id, languages=None):
            raise RuntimeError("captions disabled")

    monkeypatch.setattr(lib, "YouTubeTranscriptApi", Api)
    assert info_tools.youtube_transcript("https://youtu.be/dQw4w9WgXcQ")["error"] == "no_transcript"


def test_ocr_refuses_non_images_and_missing_files():
    assert info_tools.ocr_image("Downloads/definitely_not_here_123.png")["ok"] is False
    assert info_tools.ocr_image("Downloads/notes.txt")["ok"] is False


def test_tools_are_registered_and_their_output_is_untrusted():
    names = {tool["name"] for tool in ToolRegistry().list_tools()}
    assert {"weather_forecast", "rss_headlines", "youtube_transcript", "ocr_image"} <= names
    assert source_type_for_tool("rss_headlines") == "web_result" and source_type_for_tool("youtube_transcript") == "web_result"
    assert source_type_for_tool("ocr_image") == "file_content"
