from __future__ import annotations

import base64
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from ..llm.providers.gemini import gemini_api_keys
from ..llm.types import retry_after_from_headers


GEMINI_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PROVIDER = "gemini_vision"
VISION_STATE_PATH = Path(__file__).resolve().parents[1] / "data" / "vision_usage_state.json"


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _model_name() -> str:
    return os.environ.get("GEMINI_VISION_MODEL") or os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"


def _now() -> int:
    return int(time.time())


def _minute_bucket() -> int:
    return _now() // 60


def _day_bucket() -> str:
    return time.strftime("%Y-%m-%d", time.localtime(_now()))


def _next_minute_ts() -> int:
    return (_minute_bucket() + 1) * 60


def _next_day_ts() -> int:
    tomorrow = (datetime.fromtimestamp(_now()) + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(tomorrow.timestamp())


def _soft_limits() -> dict[str, int]:
    return {
        "rpm": max(1, _env_int("GEMINI_VISION_SOFT_RPM", 4)),
        "rpd": max(1, _env_int("GEMINI_VISION_SOFT_RPD", 100)),
    }


def _load_state() -> dict[str, Any]:
    if not VISION_STATE_PATH.exists():
        return {}
    try:
        payload = json.loads(VISION_STATE_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    VISION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = VISION_STATE_PATH.with_suffix(VISION_STATE_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(VISION_STATE_PATH)


def _prepare_state(model: str) -> dict[str, Any]:
    state = _load_state()
    if state.get("model") != model:
        state = {}
    state["provider"] = PROVIDER
    state["model"] = model
    minute = _minute_bucket()
    day = _day_bucket()
    if state.get("last_reset_minute") != minute:
        state["last_reset_minute"] = minute
        state["requests_this_minute"] = 0
    if state.get("last_reset_day") != day:
        state["last_reset_day"] = day
        state["requests_today"] = 0
    state.setdefault("requests_this_minute", 0)
    state.setdefault("requests_today", 0)
    state.setdefault("blocked_until", 0)
    state.setdefault("last_error", None)
    return state


def _blocked_response(model: str, blocked_until: int, reason: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "provider": PROVIDER,
        "model": model,
        "error": f"vision_blocked_until:{blocked_until}",
        "rate_limited": True,
        "fallback_available": False,
        "summary": "Screen analysis is temporarily unavailable because Gemini Vision is rate-limited.",
    }
    if reason:
        payload["reason"] = reason
    return payload


def _check_rate_limit(model: str) -> dict[str, Any] | None:
    state = _prepare_state(model)
    limits = _soft_limits()
    now = _now()
    blocked_until = int(state.get("blocked_until") or 0)
    if blocked_until > now:
        _save_state(state)
        return _blocked_response(model, blocked_until, "blocked_until")
    if int(state.get("requests_this_minute") or 0) >= limits["rpm"]:
        state["blocked_until"] = _next_minute_ts()
        state["last_error"] = "soft_limit_exhausted:rpm"
        _save_state(state)
        return _blocked_response(model, int(state["blocked_until"]), "soft_limit_exhausted:rpm")
    if int(state.get("requests_today") or 0) >= limits["rpd"]:
        state["blocked_until"] = _next_day_ts()
        state["last_error"] = "soft_limit_exhausted:rpd"
        _save_state(state)
        return _blocked_response(model, int(state["blocked_until"]), "soft_limit_exhausted:rpd")
    _save_state(state)
    return None


def _record_success(model: str) -> None:
    state = _prepare_state(model)
    state["requests_this_minute"] = int(state.get("requests_this_minute") or 0) + 1
    state["requests_today"] = int(state.get("requests_today") or 0) + 1
    state["last_error"] = None
    _save_state(state)


def _record_failure(model: str, error: str, *, rate_limited: bool = False, retry_after_seconds: int | None = None) -> None:
    state = _prepare_state(model)
    state["last_error"] = error[:200]
    if rate_limited:
        state["blocked_until"] = _now() + int(retry_after_seconds or 60)
    _save_state(state)


def vision_status() -> dict[str, Any]:
    model = _model_name()
    state = _prepare_state(model)
    _save_state(state)
    limits = _soft_limits()
    blocked_until = int(state.get("blocked_until") or 0)
    return {
        "vision_enabled": _env_bool("VISION_ENABLED", True),
        "gemini_vision_key_configured": bool(gemini_api_keys() or os.environ.get("GEMINI_API_KEY")),
        "gemini_vision_keys": len(gemini_api_keys()),
        "provider": PROVIDER,
        "model": model,
        "soft_limits": {"rpm": limits["rpm"], "rpd": limits["rpd"]},
        "usage": {
            "requests_this_minute": int(state.get("requests_this_minute") or 0),
            "requests_today": int(state.get("requests_today") or 0),
            "last_reset_minute": state.get("last_reset_minute"),
            "last_reset_day": state.get("last_reset_day"),
            "blocked_until": blocked_until if blocked_until > _now() else 0,
            "last_error": state.get("last_error"),
        },
    }


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in {".webp"}:
        return "image/webp"
    return "image/jpeg"


def _validate_image(path: str) -> tuple[Path | None, dict[str, Any] | None]:
    if not _env_bool("VISION_ENABLED", True):
        return None, {"ok": False, "provider": PROVIDER, "error": "vision_disabled"}
    image_path = Path(path)
    if not image_path.exists() or not image_path.is_file():
        return None, {"ok": False, "provider": PROVIDER, "error": "image_not_found"}
    max_mb = max(0.1, _env_float("VISION_MAX_IMAGE_MB", 8.0))
    size_mb = image_path.stat().st_size / (1024 * 1024)
    if size_mb > max_mb:
        return None, {"ok": False, "provider": PROVIDER, "error": f"image_too_large:{size_mb:.2f}MB>{max_mb:.2f}MB"}
    if not gemini_api_keys() and not os.environ.get("GEMINI_API_KEY"):
        return None, {"ok": False, "provider": PROVIDER, "error": "missing_api_key"}
    return image_path, None


def _prompt(user_question: str | None) -> str:
    question = (user_question or "Describe what is visible on this screen.").strip()[:800]
    return f"""
You are Eva's on-demand screen understanding module.
Analyze this single screenshot only. Do not imply continuous monitoring.

User question:
{question}

Return JSON only with this shape:
{{
  "summary": "clear concise description of what is visible",
  "detected_text": "important visible text if any",
  "possible_issue": "likely issue if an error/problem is visible, otherwise empty string",
  "suggested_actions": ["short practical next step"]
}}

If the screenshot is unclear, say so. Do not claim certainty beyond the image.
""".strip()


def _extract_text(payload: dict[str, Any]) -> str:
    parts = (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    texts = [str(part.get("text") or "") for part in parts if isinstance(part, dict)]
    return "\n".join(text for text in texts if text).strip()


def _parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return {"summary": cleaned, "detected_text": "", "possible_issue": "", "suggested_actions": []}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"summary": cleaned, "detected_text": "", "possible_issue": "", "suggested_actions": []}
    if isinstance(parsed, str):
        nested = parsed.strip()
        if nested.startswith("```"):
            nested = re.sub(r"^```(?:json)?", "", nested, flags=re.IGNORECASE).strip()
            nested = re.sub(r"```$", "", nested).strip()
        if nested.startswith("{") and nested.endswith("}"):
            try:
                reparsed = json.loads(nested)
                if isinstance(reparsed, dict):
                    return reparsed
            except json.JSONDecodeError:
                pass
    return parsed if isinstance(parsed, dict) else {"summary": str(parsed), "detected_text": "", "possible_issue": "", "suggested_actions": []}


def _clean_nested_json_field(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("{") and text.endswith("}"):
        nested = _parse_json_text(text)
        if isinstance(nested, dict) and nested is not value:
            extracted = str(nested.get(field) or nested.get("summary") or "").strip()
            # Phase 107: `return extracted` DESTROYED any reply that was not
            # shaped like this module's own schema. The vision-click path asks
            # the model for {"found", "x", "y", "confidence", "description"};
            # that JSON has no "summary" key, so this returned the empty string
            # and a correct, complete answer became `unparseable_reply` at the
            # caller. Measured: the model replied
            # {"found": true, "x": 785, ...} and `summary` arrived as "".
            #
            # A normaliser that cannot recognise a payload must pass it through,
            # never delete it. Flattening an unexpected shape to nothing is
            # indistinguishable, downstream, from the model having said nothing.
            return extracted or text
    return text


def _normalize_success(model: str, text: str) -> dict[str, Any]:
    data = _parse_json_text(text)
    suggested = data.get("suggested_actions") or []
    if isinstance(suggested, str):
        suggested = [suggested]
    if not isinstance(suggested, list):
        suggested = []
    return {
        "ok": True,
        "provider": PROVIDER,
        "model": model,
        "summary": _clean_nested_json_field(data.get("summary") or text or "I could not clearly describe the screen.", "summary"),
        "detected_text": _clean_nested_json_field(data.get("detected_text") or "", "detected_text"),
        "possible_issue": _clean_nested_json_field(data.get("possible_issue") or "", "possible_issue"),
        "suggested_actions": [str(item).strip() for item in suggested if str(item).strip()][:6],
    }


def _request_payload(image_path: Path, user_question: str | None) -> dict[str, Any]:
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": _prompt(user_question)},
                    {"inline_data": {"mime_type": _mime_type(image_path), "data": encoded}},
                ],
            }
        ],
        # Phase 107: 900 was never a cap on the ANSWER -- it caps thinking PLUS
        # answer, and gemini-2.5-flash is a reasoning model. Measured on a real
        # localisation call: finishReason=MAX_TOKENS, thoughtsTokenCount=861,
        # candidatesTokenCount=35. Reasoning took 96% of the budget and the JSON
        # was cut mid-string at `"description":`, which the caller reported as
        # `unparseable_reply` -- a healthy model and a correct answer discarded
        # by our own cap, and INTERMITTENTLY, because whether the reply fit
        # depended on how long the model happened to think. Three runs of the
        # identical request gave a good target, a good target, and a parse
        # failure.
        #
        # Third time this project has been bitten by a reasoning model spending
        # a budget meant for the reply: Phase 92 raised `probe_max_tokens` from
        # 16 to 256 for the same reason, and Phase 101 fixed nemotron emitting
        # its chain of thought as the answer. A cap sized for an answer is not
        # sized for a model that thinks first.
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2400},
    }


def analyze_screen_image_sync(image_path: str, user_question: str | None = None) -> dict[str, Any]:
    path, error = _validate_image(image_path)
    if error is not None:
        return error
    assert path is not None
    model = _model_name()
    limited = _check_rate_limit(model)
    if limited is not None:
        return limited
    # Phase 107: EVERY configured key, not just the first. This read
    # `os.environ["GEMINI_API_KEY"]` while the chat path rotated across four --
    # so vision exhausted one key and reported itself rate-limited with three
    # unused keys in the same file. That is what actually blocked vision
    # clicking in practice, and it is one rule about "which keys exist" written
    # down twice with the unwatched copy deciding.
    keys = gemini_api_keys() or [os.environ.get("GEMINI_API_KEY", "")]
    url = GEMINI_GENERATE_URL.format(model=model)
    try:
        response = None
        retry_after = 60
        with httpx.Client(timeout=45) as client:
            for api_key in keys:
                response = client.post(url, params={"key": api_key}, json=_request_payload(path, user_question))
                if response.status_code != 429:
                    break
                # Only a 429 moves to the next key. Any other failure is about
                # the REQUEST, not the key, and retrying it on three more keys
                # would spend three more screenshots to fail the same way.
                retry_after = retry_after_from_headers(dict(response.headers)) or 60
        if response is None or response.status_code == 429:
            _record_failure(model, "gemini_vision_http_429", rate_limited=True, retry_after_seconds=retry_after)
            state = _prepare_state(model)
            return _blocked_response(model, int(state.get("blocked_until") or (_now() + retry_after)), "gemini_vision_http_429")
        if response.status_code >= 400:
            _record_failure(model, f"gemini_vision_http_{response.status_code}")
            return {
                "ok": False,
                "provider": PROVIDER,
                "model": model,
                "error": f"gemini_vision_http_{response.status_code}",
            }
        text = _extract_text(response.json())
        if not text:
            _record_failure(model, "empty_vision_response")
            return {"ok": False, "provider": PROVIDER, "model": model, "error": "empty_vision_response"}
        result = _normalize_success(model, text)
        _record_success(model)
        return result
    except Exception as exc:
        _record_failure(model, f"vision_request_error:{exc.__class__.__name__}")
        return {"ok": False, "provider": PROVIDER, "model": model, "error": f"vision_request_error:{exc.__class__.__name__}"}


async def analyze_screen_image(image_path: str, user_question: str | None = None) -> dict[str, Any]:
    path, error = _validate_image(image_path)
    if error is not None:
        return error
    assert path is not None
    model = _model_name()
    limited = _check_rate_limit(model)
    if limited is not None:
        return limited
    # Phase 107: rotate, exactly as the sync path above. Two copies of this
    # request existed and only fixing one would leave the async caller stuck on
    # a single key -- the failure mode this change is about.
    keys = gemini_api_keys() or [os.environ.get("GEMINI_API_KEY", "")]
    url = GEMINI_GENERATE_URL.format(model=model)
    try:
        response = None
        retry_after = 60
        async with httpx.AsyncClient(timeout=45) as client:
            for api_key in keys:
                response = await client.post(url, params={"key": api_key}, json=_request_payload(path, user_question))
                if response.status_code != 429:
                    break
                retry_after = retry_after_from_headers(dict(response.headers)) or 60
        if response is None or response.status_code == 429:
            _record_failure(model, "gemini_vision_http_429", rate_limited=True, retry_after_seconds=retry_after)
            state = _prepare_state(model)
            return _blocked_response(model, int(state.get("blocked_until") or (_now() + retry_after)), "gemini_vision_http_429")
        if response.status_code >= 400:
            _record_failure(model, f"gemini_vision_http_{response.status_code}")
            return {
                "ok": False,
                "provider": PROVIDER,
                "model": model,
                "error": f"gemini_vision_http_{response.status_code}",
            }
        text = _extract_text(response.json())
        if not text:
            _record_failure(model, "empty_vision_response")
            return {"ok": False, "provider": PROVIDER, "model": model, "error": "empty_vision_response"}
        result = _normalize_success(model, text)
        _record_success(model)
        return result
    except Exception as exc:
        _record_failure(model, f"vision_request_error:{exc.__class__.__name__}")
        return {"ok": False, "provider": PROVIDER, "model": model, "error": f"vision_request_error:{exc.__class__.__name__}"}
