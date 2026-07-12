from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CAPS = tuple(f"news.{name}" for name in ("status", "policy", "dashboard", "topics", "sources", "freshness", "safety_report", "readiness"))
COMMANDS = tuple(f"eva news {name.replace('_', ' ')}" for name in ("status", "policy", "dashboard", "topics", "sources", "freshness", "safety_report", "readiness"))
ASK = {
    "show news dashboard": "news_dashboard",
    "show web intelligence status": "news_status",
    "what is Eva's news policy": "news_policy",
    "can Eva monitor news": "news_policy",
    "can Eva crawl the web": "news_policy",
    "show news source reliability": "news_sources",
    "show news freshness": "news_freshness",
    "show news readiness": "news_readiness",
}
BOUNDARIES = (
    "dashboard is local/mock or safe-read-only only", "no unrestricted crawler",
    "no login/session/cookie/profile access", "no browser control",
    "no background monitoring unless a future explicit scheduler gate exists",
    "no live llm call was made", "no tool execution",
    "phase 12l remains a gated write path",
)


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def safe(text: str) -> None:
    low = text.lower()
    for phrase in BOUNDARIES:
        check(phrase in low, f"missing boundary: {phrase}")
    for token in ("traceback", "{'", "c:\\users\\", ".env.local", "token=", "password="):
        check(token not in low, f"unsafe output: {token}")


def main() -> int:
    from backend.eva.news_dashboard.deduplication import duplicate_group_id
    from backend.eva.news_dashboard.freshness import freshness_label
    from backend.eva.news_dashboard.mock_feeds import build_mock_dashboard
    from backend.eva.news_dashboard.news_policy import news_policy_text
    from backend.eva.news_dashboard.source_policy import source_policy_text
    from backend.eva.news_dashboard.status import get_news_dashboard_status
    from backend.eva.news_dashboard.url_integration import evaluate_news_url
    from backend.eva.news_dashboard.formatter import (
        format_news_dashboard, format_news_freshness, format_news_policy,
        format_news_readiness, format_news_safety_report, format_news_sources,
        format_news_status, format_news_topics,
    )
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.core.natural_router import route_natural_request
    from backend.eva.tools.registry import ToolRegistry
    from backend.eva.control_center.collector import collect_control_center_status
    from backend.eva.control_center.formatter import format_control_center_status
    from backend.eva.capabilities.registry import get_capability
    from backend.eva.capabilities.resource_mapping import resolve_capability
    from backend.eva.capabilities.tool_schemas import capability_to_tool_schema
    from backend.eva.planner.capability_selector import select_capabilities_for_goal
    from backend.eva.planner.decomposer import create_task_plan
    from backend.eva.agents.team_review import format_team_review
    from scripts import verify_eva_all

    check(len(news_policy_text().splitlines()) > 2 and len(source_policy_text().splitlines()) > 2, "policy unreadable")
    check(get_news_dashboard_status().backend_mode == "mock_fixture", "unsafe backend")
    dashboard = build_mock_dashboard("climate technology")
    for field in (
        "dashboard_id", "topic", "query_summary", "backend_mode", "source_cards",
        "event_cards", "freshness_labels", "source_reliability_notes",
        "duplicate_grouping_notes", "uncertainty_notes", "safety_notes",
        "blocked_source_notes", "citation_source_metadata", "final_status",
        "no_unrestricted_crawling_statement", "no_login_session_cookie_profile_statement",
        "no_browser_control_statement", "no_live_llm_call_statement",
        "no_tool_execution_statement", "no_new_write_path_statement",
    ):
        check(hasattr(dashboard, field), f"dashboard field missing: {field}")
    check(dashboard.source_cards and dashboard.event_cards, "mock cards missing")
    source = dashboard.source_cards[0]
    event = dashboard.event_cards[0]
    for field in ("source_id", "source_title", "source_type", "public_url", "freshness_label", "reliability_note", "summary", "citation_metadata", "safety_status", "exclusion_reason"):
        check(hasattr(source, field), f"source field missing: {field}")
    for field in ("event_id", "event_title", "event_summary", "related_sources", "freshness_label", "confidence_uncertainty_label", "duplicate_group_id", "what_changed_why_it_matters", "safety_notes"):
        check(hasattr(event, field), f"event field missing: {field}")
    check(duplicate_group_id("Major Climate Update") == duplicate_group_id("major climate update!"), "dedupe unstable")
    check(freshness_label(2) == "fresh" and freshness_label(200) == "stale", "freshness unstable")
    for url in ("http://localhost/private", "http://127.0.0.1", "file:///secret", "https://user:pass@example.com"):
        check(not evaluate_news_url(url).allowed, f"unsafe URL allowed: {url}")

    outputs = (format_news_status(), format_news_policy(), format_news_dashboard(), format_news_topics(), format_news_sources(), format_news_freshness(), format_news_safety_report(), format_news_readiness())
    for output in outputs:
        safe(output)
    for command in COMMANDS:
        result = maybe_handle_fast_command(command, ToolRegistry())
        check(result is not None, f"command missing: {command}")
        safe(result[0])
    for prompt, intent in ASK.items():
        route = route_natural_request(prompt)
        check(route.intent == intent and not route.real_execution_requested, f"bad route: {prompt}")
        result = maybe_handle_fast_command(f"eva ask {prompt}", ToolRegistry())
        check(result is not None, f"ask missing: {prompt}")
        safe(result[0])

    control = collect_control_center_status()
    check(hasattr(control, "news_dashboard_summary"), "Control Center summary missing")
    check("News / Web Intelligence Dashboard" in format_control_center_status(control), "Control Center panel missing")
    from backend.eva.ai_os.system_map import system_map_text
    from backend.eva.ai_os.capability_matrix import capability_matrix_text
    ai = system_map_text() + capability_matrix_text()
    check("News / Web Intelligence Dashboard" in ai and "browser control" in ai.lower(), "AI OS state missing")
    for cap_id in CAPS:
        check(get_capability(cap_id) is not None, f"cap missing: {cap_id}")
        check(resolve_capability(cap_id).execution_path == "fast_command", f"resource missing: {cap_id}")
        check(capability_to_tool_schema(cap_id).get("execution_status") == "dashboard_only", f"schema missing: {cap_id}")
    check("news.dashboard" in select_capabilities_for_goal("show news dashboard"), "planner selector missing")
    check(any(s.capability_id == "news.dashboard" for s in create_task_plan("show news dashboard").steps), "planner step missing")
    review = format_team_review("review Phase 27 News Web Intelligence Dashboard")
    for phrase in ("dashboard/report/status only", "no unrestricted crawling happens", "no browser control happens", "Phase 28 Coding Specialist / CodingAgent is next"):
        check(phrase.lower() in review.lower(), f"team review missing: {phrase}")
    for doc in ("EVA_CURRENT_STATE.md", "EVA_CAPABILITIES.md", "EVA_AGENT_FRAMEWORK.md", "EVA_THREAT_MODEL.md", "EVA_VERIFICATION.md"):
        text = (ROOT / "docs" / doc).read_text(encoding="utf-8")
        check("Phase 27 News / Web Intelligence Dashboard is complete after this pass" in text, f"doc missing: {doc}")
    check("verify_eva_news_web_intelligence_dashboard.py" in verify_eva_all.FULL_VERIFIERS, "full profile missing")
    check("verify_eva_news_web_intelligence_dashboard.py" in verify_eva_all.QUICK_VERIFIERS, "quick profile missing")
    source_text = "\n".join(p.read_text(encoding="utf-8").lower() for p in (ROOT / "backend/eva/news_dashboard").glob("*.py"))
    for token in ("requests.", "httpx.", "urllib.request", "playwright", "selenium", "subprocess", "pyautogui", "os.system", "open("):
        check(token not in source_text, f"forbidden runtime surface: {token}")
    print("PASS: Phase 27 News/Web Intelligence Dashboard is deterministic, local/mock, and crawler-locked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
