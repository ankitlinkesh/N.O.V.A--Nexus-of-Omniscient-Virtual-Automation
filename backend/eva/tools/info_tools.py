"""Key-free information tools: weather, RSS headlines, YouTube transcripts, and image OCR.

Everything here runs in-process with open libraries and needs no account or API key:

  * ``weather_forecast``  Open-Meteo (geocoding + forecast), free for non-commercial use.
  * ``rss_headlines``     any public RSS/Atom feed, or a few named ones, through ``feedparser``.
  * ``youtube_transcript`` captions of a public video through ``youtube-transcript-api``
    (it uses an undocumented endpoint, so it can break; a failure is reported, never faked).
  * ``ocr_image``         text in an image file, through RapidOCR (ONNX, local, no network).

The text these return came from outside NOVA (a feed, a video's captions, a picture), so the
taint tracker treats it as untrusted data: it can inform an answer but never instruct an action.
All network calls are bounded (timeout, size cap), HTTPS-or-HTTP only, and refuse private hosts.
"""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

from ..browser.safety import is_local_or_private_host, normalize_public_url

TIMEOUT = 10.0
MAX_FEED_BYTES = 2_000_000
UA = {"User-Agent": "NOVA-desktop-agent/1.0 (personal assistant; +local)"}

NAMED_FEEDS = {
    "bbc": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "bbc world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "hacker news": "https://hnrss.org/frontpage",
    "hn": "https://hnrss.org/frontpage",
    "npr": "https://feeds.npr.org/1001/rss.xml",
    "the hindu": "https://www.thehindu.com/news/national/feeder/default.rss",
}

# WMO weather interpretation codes, as returned by Open-Meteo.
_WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "heavy freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "heavy freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers", 81: "showers",
    82: "violent showers", 85: "snow showers", 86: "heavy snow showers", 95: "thunderstorm",
    96: "thunderstorm with hail", 99: "severe thunderstorm with hail",
}


def _fail(error: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error": error, "message": message, **extra}


def _get_json(url: str, params: dict[str, Any]) -> Any:
    response = httpx.get(url, params=params, timeout=TIMEOUT, headers=UA)
    response.raise_for_status()
    return response.json()


# --- weather ------------------------------------------------------------------------------

# "weather in chennai", "what's the forecast for mumbai": needs a place, so a bare "weather" goes to the model.
WEATHER_REQUEST = re.compile(
    r"^(?:(?:what(?:'s| is)|how(?:'s| is)) (?:the )?)?(?P<kind>weather|forecast|temperature)(?: like)?"
    r"(?: (?:in|at|for|of))? (?P<place>[a-z][a-z .,'-]{1,60}?)(?: (?:today|now|right now|tomorrow))?$",
    re.IGNORECASE,
)


def parse_weather_request(text: str) -> tuple[str, int] | None:
    """(place, days) for a plain weather question, else None."""
    cleaned = " ".join(str(text or "").split()).rstrip(" .!?")
    found = WEATHER_REQUEST.match(cleaned)
    if not found or found.group("place").strip().lower() in {"me", "it", "here", "outside", "today", "now", "like", "the", "a", "out", "tomorrow", "there", "this", "that", "in", "at", "for", "of"}:
        return None
    days = 3 if found.group("kind").lower() == "forecast" else (2 if cleaned.lower().endswith("tomorrow") else 1)
    return found.group("place").strip(), days

def weather_forecast(place: str, days: int = 1) -> dict[str, Any]:
    place = " ".join(str(place or "").split())[:80]
    if not place:
        return _fail("empty_place", "Tell me which city or place you want the weather for.")
    days = max(1, min(int(days or 1), 7))
    try:
        found = _get_json("https://geocoding-api.open-meteo.com/v1/search", {"name": place, "count": 1, "language": "en", "format": "json"})
        hits = (found or {}).get("results") or []
        if not hits:
            return _fail("place_not_found", f"I couldn't find a place called {place}.", place=place)
        spot = hits[0]
        data = _get_json(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": spot["latitude"], "longitude": spot["longitude"], "timezone": "auto", "forecast_days": days,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            },
        )
    except httpx.HTTPError as exc:
        return _fail("weather_unavailable", "I couldn't reach the weather service just now.", detail=exc.__class__.__name__)
    except (KeyError, ValueError, TypeError):
        return _fail("weather_unreadable", "The weather service answered in a form I couldn't read.")

    name = ", ".join(part for part in (spot.get("name"), spot.get("admin1"), spot.get("country")) if part)
    current = (data or {}).get("current") or {}
    units = (data or {}).get("current_units") or {}
    daily = (data or {}).get("daily") or {}
    if "temperature_2m" not in current:
        return _fail("weather_unreadable", "The weather service answered without current conditions.")
    sky = _WMO.get(int(current.get("weather_code", -1)), "unknown conditions")
    t_unit, w_unit = units.get("temperature_2m", "°C"), units.get("wind_speed_10m", "km/h")
    summary = (
        f"{name}: {current['temperature_2m']}{t_unit}, {sky}"
        f" (feels like {current.get('apparent_temperature')}{t_unit}), humidity {current.get('relative_humidity_2m')}%,"
        f" wind {current.get('wind_speed_10m')} {w_unit}."
    )
    forecast = []
    for i, day in enumerate(daily.get("time") or []):
        forecast.append({
            "date": day,
            "sky": _WMO.get(int((daily.get("weather_code") or [-1])[i]), "unknown"),
            "high": (daily.get("temperature_2m_max") or [None])[i],
            "low": (daily.get("temperature_2m_min") or [None])[i],
            "rain_chance_percent": (daily.get("precipitation_probability_max") or [None])[i],
        })
    if days > 1 and forecast:
        summary += " " + "; ".join(f"{d['date']}: {d['sky']}, {d['low']}–{d['high']}{t_unit}, rain {d['rain_chance_percent']}%" for d in forecast) + "."
    elif forecast:
        today = forecast[0]
        summary += f" Today: {today['low']}–{today['high']}{t_unit}, rain chance {today['rain_chance_percent']}%."
    return {"ok": True, "place": name, "current": current, "forecast": forecast, "source": "open-meteo.com", "message": summary, "summary": summary}


# --- RSS ----------------------------------------------------------------------------------

def rss_headlines(feed: str, limit: int = 8) -> dict[str, Any]:
    raw = " ".join(str(feed or "").split())
    url = NAMED_FEEDS.get(raw.lower(), raw)
    limit = max(1, min(int(limit or 8), 20))
    try:
        url = normalize_public_url(url)
    except ValueError as exc:
        return _fail("bad_feed_url", f"That is not a usable feed address ({exc}). Name a feed ({', '.join(sorted(set(NAMED_FEEDS)))}) or give a public http(s) URL.")
    if is_local_or_private_host(urllib.parse.urlparse(url).hostname or ""):
        return _fail("private_host", "I only read public feeds, not addresses on this computer or your network.")
    try:
        import feedparser

        with httpx.stream("GET", url, timeout=TIMEOUT, headers=UA, follow_redirects=True) as response:
            response.raise_for_status()
            body = b""
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) > MAX_FEED_BYTES:
                    break
        parsed = feedparser.parse(body[:MAX_FEED_BYTES])
    except ImportError:
        return _fail("feedparser_missing", "RSS reading needs the feedparser package, which is not installed.")
    except httpx.HTTPError as exc:
        return _fail("feed_unreachable", "I couldn't download that feed.", detail=exc.__class__.__name__, url=url)
    items = []
    for entry in (parsed.entries or [])[:limit]:
        title = " ".join(str(entry.get("title") or "").split())[:200]
        if title:
            items.append({"title": title, "link": str(entry.get("link") or "")[:400], "published": str(entry.get("published") or entry.get("updated") or "")[:40]})
    if not items:
        return _fail("empty_feed", "That feed had no readable entries.", url=url)
    title = " ".join(str((parsed.feed or {}).get("title") or url).split())[:100]
    summary = f"{title}: " + " | ".join(item["title"] for item in items[:5])
    return {"ok": True, "feed": title, "url": url, "items": items, "message": summary, "summary": summary}


# --- YouTube transcript -------------------------------------------------------------------

_VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})")


def youtube_transcript(url: str, max_chars: int = 6000) -> dict[str, Any]:
    text = str(url or "").strip()
    found = _VIDEO_ID.search(text)
    video_id = found.group(1) if found else (text if re.fullmatch(r"[A-Za-z0-9_-]{11}", text) else "")
    if not video_id:
        return _fail("bad_video", "I need a YouTube video link (or its 11-character id).")
    max_chars = max(500, min(int(max_chars or 6000), 20000))
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        fetched = YouTubeTranscriptApi().fetch(video_id, languages=["en", "en-US", "en-GB", "hi", "ta"])
        pieces = [str(getattr(snippet, "text", "") or snippet.get("text", "")) if not isinstance(snippet, dict) else str(snippet.get("text", "")) for snippet in fetched]
    except ImportError:
        return _fail("transcript_lib_missing", "Transcripts need the youtube-transcript-api package, which is not installed.")
    except Exception as exc:  # captions disabled, video private, YouTube changed its endpoint, rate limit
        return _fail("no_transcript", "I couldn't get captions for that video (they may be off, or YouTube refused).", detail=exc.__class__.__name__, video_id=video_id)
    full = " ".join(" ".join(piece.split()) for piece in pieces if piece.strip())
    if not full:
        return _fail("no_transcript", "That video's captions were empty.", video_id=video_id)
    clipped = full[:max_chars]
    return {"ok": True, "video_id": video_id, "chars": len(full), "truncated": len(full) > max_chars, "transcript": clipped,
            "message": f"Got {len(full)} characters of captions for {video_id}" + (f" (showing the first {max_chars})." if len(full) > max_chars else ".")}


# --- OCR ----------------------------------------------------------------------------------

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
_OCR_ENGINE: Any = None


def ocr_image(path: str) -> dict[str, Any]:
    from .safe_file_tools import _safe_path, read_path_refusal

    refusal = read_path_refusal(path)
    if refusal is not None:
        return refusal
    target: Path = _safe_path(path)
    if not target.exists() or not target.is_file():
        return _fail("not_found", f"I couldn't find an image at {target}.")
    if target.suffix.lower() not in _IMAGE_SUFFIXES:
        return _fail("not_an_image", "OCR works on image files (png, jpg, bmp, webp, tiff).")
    global _OCR_ENGINE
    try:
        if _OCR_ENGINE is None:
            from rapidocr_onnxruntime import RapidOCR

            _OCR_ENGINE = RapidOCR()
        result, _elapsed = _OCR_ENGINE(str(target))
    except ImportError:
        return _fail("ocr_missing", "Reading text from images needs the rapidocr-onnxruntime package, which is not installed.")
    except Exception as exc:
        return _fail("ocr_failed", "I couldn't read that image.", detail=exc.__class__.__name__)
    lines = [str(row[1]).strip() for row in (result or []) if len(row) >= 2 and str(row[1]).strip()]
    if not lines:
        return {"ok": True, "path": str(target), "lines": [], "text": "", "message": f"I found no readable text in {target.name}."}
    text = "\n".join(lines)[:8000]
    return {"ok": True, "path": str(target), "lines": lines[:200], "text": text, "message": f"Read {len(lines)} line(s) of text from {target.name}."}
