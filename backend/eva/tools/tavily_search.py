from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from ..core.data_paths import data_path

TAVILY_ENDPOINT = "https://api.tavily.com/search"
STATE_PATH = Path(__file__).resolve().parents[1] / "data" / "tavily_usage_state.json"
MAX_QUERY_LENGTH = 400


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _minute_bucket() -> int:
    return int(time.time()) // 60


def _day_bucket() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def _load_state() -> dict[str, Any]:
    if not data_path(STATE_PATH).exists():
        return {}
    try:
        return json.loads(data_path(STATE_PATH).read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    data_path(STATE_PATH).parent.mkdir(parents=True, exist_ok=True)
    data_path(STATE_PATH).write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _usage_entry(state: dict[str, Any]) -> dict[str, Any]:
    entry = state.setdefault("tavily", {})
    minute = _minute_bucket()
    day = _day_bucket()
    if entry.get("last_reset_minute") != minute:
        entry["last_reset_minute"] = minute
        entry["requests_this_minute"] = 0
    if entry.get("last_reset_day") != day:
        entry["last_reset_day"] = day
        entry["requests_today"] = 0
    entry.setdefault("blocked_until", 0)
    entry.setdefault("last_error", None)
    return entry


def _can_call() -> tuple[bool, str | None]:
    state = _load_state()
    entry = _usage_entry(state)
    now = int(time.time())
    rpm = _env_int("TAVILY_SOFT_RPM", 20)
    rpd = _env_int("TAVILY_SOFT_RPD", 1000)
    if int(entry.get("blocked_until") or 0) > now:
        _save_state(state)
        return False, "blocked_until"
    if int(entry.get("requests_this_minute") or 0) >= rpm:
        _save_state(state)
        return False, "soft_rpm_exhausted"
    if int(entry.get("requests_today") or 0) >= rpd:
        _save_state(state)
        return False, "soft_rpd_exhausted"
    _save_state(state)
    return True, None


def _record_success() -> None:
    state = _load_state()
    entry = _usage_entry(state)
    entry["requests_this_minute"] = int(entry.get("requests_this_minute") or 0) + 1
    entry["requests_today"] = int(entry.get("requests_today") or 0) + 1
    entry["last_error"] = None
    _save_state(state)


def _record_failure(error: str, *, rate_limited: bool = False, retry_after_seconds: int | None = None) -> None:
    state = _load_state()
    entry = _usage_entry(state)
    entry["last_error"] = error[:300]
    if rate_limited:
        entry["blocked_until"] = int(time.time()) + int(retry_after_seconds or 60)
    _save_state(state)


def _safe_query(query: str) -> tuple[str | None, str | None]:
    clean = " ".join(query.strip().split())
    if not clean:
        return None, "empty_query"
    return clean[:MAX_QUERY_LENGTH], None


def _max_results(value: int | None = None) -> int:
    if value is not None:
        return max(1, min(10, int(value)))
    return _env_int("TAVILY_MAX_RESULTS", 5, minimum=1, maximum=10)


def _request_payload(query: str, max_results: int | None = None) -> dict[str, Any]:
    return {
        "query": query,
        "search_depth": os.environ.get("TAVILY_SEARCH_DEPTH", "basic").strip() or "basic",
        "include_answer": _env_bool("TAVILY_INCLUDE_ANSWER", True),
        "include_raw_content": _env_bool("TAVILY_INCLUDE_RAW_CONTENT", False),
        "max_results": _max_results(max_results),
    }


def _error(query: str, error: str, *, rate_limited: bool = False) -> dict[str, Any]:
    return {
        "ok": False,
        "provider": "tavily",
        "query": query,
        "error": error,
        "rate_limited": rate_limited,
        "fallback": "browser",
    }


def _retry_after(headers: httpx.Headers) -> int | None:
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(1, int(float(raw)))
    except ValueError:
        return None


def _normalize(data: dict[str, Any], query: str) -> dict[str, Any]:
    raw_results = data.get("results")
    if raw_results is None:
        raw_results = []
    if not isinstance(raw_results, list):
        raise ValueError("malformed_results")

    results = []
    for item in raw_results[:_max_results()]:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "title": str(item.get("title") or "Untitled")[:240],
                "url": str(item.get("url") or "")[:800],
                "content": str(item.get("content") or "")[:1200],
                "score": float(item.get("score") or 0.0),
            }
        )

    answer = data.get("answer")
    return {
        "ok": True,
        "provider": "tavily",
        "query": query,
        "answer": str(answer)[:1600] if answer else "",
        "results": results,
    }


def _preflight(query: str) -> tuple[str | None, dict[str, Any] | None]:
    clean, query_error = _safe_query(query)
    display_query = clean or query.strip()
    if query_error:
        return None, _error(display_query, query_error)
    if not os.environ.get("TAVILY_API_KEY", "").strip():
        return clean, _error(clean, "missing_api_key")
    allowed, reason = _can_call()
    if not allowed:
        return clean, _error(clean, reason or "rate_limited", rate_limited=True)
    return clean, None


def _handle_status(response: httpx.Response, query: str) -> dict[str, Any] | None:
    status = response.status_code
    if status < 400:
        return None
    if status in {401, 403}:
        _record_failure("auth_error")
        return _error(query, "auth_error")
    if status == 429:
        retry_after = _retry_after(response.headers)
        _record_failure("rate_limited", rate_limited=True, retry_after_seconds=retry_after)
        return _error(query, "rate_limited", rate_limited=True)
    if status >= 500:
        _record_failure(f"temporary_failure:{status}")
        return _error(query, f"temporary_failure:{status}")
    _record_failure(f"http_error:{status}")
    return _error(query, f"http_error:{status}")


async def tavily_search(query: str, max_results: int | None = None) -> dict[str, Any]:
    clean, preflight_error = _preflight(query)
    if preflight_error is not None:
        return preflight_error
    assert clean is not None

    headers = {"Authorization": f"Bearer {os.environ['TAVILY_API_KEY'].strip()}"}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(TAVILY_ENDPOINT, headers=headers, json=_request_payload(clean, max_results))
    except httpx.RequestError:
        _record_failure("network_error")
        return _error(clean, "network_error")

    status_error = _handle_status(response, clean)
    if status_error is not None:
        return status_error

    try:
        normalized = _normalize(response.json(), clean)
    except (ValueError, TypeError, json.JSONDecodeError):
        _record_failure("malformed_response")
        return _error(clean, "malformed_response")

    _record_success()
    return normalized


def tavily_search_sync(query: str, max_results: int | None = None) -> dict[str, Any]:
    clean, preflight_error = _preflight(query)
    if preflight_error is not None:
        return preflight_error
    assert clean is not None

    headers = {"Authorization": f"Bearer {os.environ['TAVILY_API_KEY'].strip()}"}
    try:
        with httpx.Client(timeout=12) as client:
            response = client.post(TAVILY_ENDPOINT, headers=headers, json=_request_payload(clean, max_results))
    except httpx.RequestError:
        _record_failure("network_error")
        return _error(clean, "network_error")

    status_error = _handle_status(response, clean)
    if status_error is not None:
        return status_error

    try:
        normalized = _normalize(response.json(), clean)
    except (ValueError, TypeError, json.JSONDecodeError):
        _record_failure("malformed_response")
        return _error(clean, "malformed_response")

    _record_success()
    return normalized


def tavily_status() -> dict[str, Any]:
    state = _load_state()
    entry = _usage_entry(state)
    _save_state(state)
    return {
        "tavily_configured": bool(os.environ.get("TAVILY_API_KEY", "").strip()),
        "max_results": _max_results(),
        "search_depth": os.environ.get("TAVILY_SEARCH_DEPTH", "basic").strip() or "basic",
        "include_answer": _env_bool("TAVILY_INCLUDE_ANSWER", True),
        "include_raw_content": _env_bool("TAVILY_INCLUDE_RAW_CONTENT", False),
        "soft_rpm": _env_int("TAVILY_SOFT_RPM", 20),
        "soft_rpd": _env_int("TAVILY_SOFT_RPD", 1000),
        "browser_fallback_enabled": True,
        "usage": {
            "requests_this_minute": int(entry.get("requests_this_minute") or 0),
            "requests_today": int(entry.get("requests_today") or 0),
            "blocked_until": int(entry.get("blocked_until") or 0),
            "last_error": entry.get("last_error"),
        },
    }
