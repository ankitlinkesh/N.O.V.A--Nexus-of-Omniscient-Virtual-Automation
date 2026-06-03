from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Intentional fake secret-pattern fixture for redaction tests. Not a real secret.


def emit(case: str, passed: bool, **payload: Any) -> int:
    print(json.dumps({"case": case, "pass": passed, **payload}, indent=2, ensure_ascii=False))
    return 0 if passed else 1


def _has_raw_repr(text: str) -> bool:
    return "ResearchMemoryItem(" in text or "ResearchSearchResult(" in text or "sqlite3.Row" in text or "Traceback" in text or "{'" in text


def _clean_human_output(text: str) -> bool:
    return bool(text and not _has_raw_repr(text) and "C:\\" not in text and "/tmp/" not in text)


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="eva_research_memory_v2_"))
    os.environ["EVA_RESEARCH_MEMORY_DB_PATH"] = str(temp_root / "research_memory.sqlite3")
    os.environ.setdefault("EVA_PENDING_ACTION_LEDGER_PATH", str(temp_root / "pending_actions.jsonl"))

    from backend.eva.agents.supervisor_agent import select_agent_for_intent
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.research_memory.models import ResearchMemoryItem
    from backend.eva.research_memory.sources import extract_domain, looks_private_or_sensitive, redact_research_text
    from backend.eva.research_memory.status import format_research_memory_status, format_research_search, format_research_topic_summary
    from backend.eva.research_memory.store import (
        add_research_item,
        init_research_memory_store,
        list_recent_research,
        research_memory_status,
        search_research_items,
    )
    from backend.eva.runtime.graph import run_eva_v2_execute
    from backend.eva.tools.registry import ToolRegistry

    failures = 0

    failures += emit("research_memory_package_imports", True)

    db_path = init_research_memory_store()
    failures += emit("store_initializes_isolated_db", db_path == temp_root / "research_memory.sqlite3" and db_path.exists(), path=str(db_path))

    empty_status = format_research_memory_status()
    empty_recent = maybe_handle_fast_command("recent research", ToolRegistry(), {})
    empty_topics = maybe_handle_fast_command("research topics", ToolRegistry(), {})
    empty_search = format_research_search("nothing saved yet")
    empty_topic = format_research_topic_summary("missing topic")
    failures += emit(
        "empty_states_are_friendly",
        "no local research notes saved yet" in (empty_recent or [""])[0].lower()
        and "no local research memory topics saved yet" in (empty_topics or [""])[0].lower()
        and "no local saved results" in empty_search.lower()
        and "topic not found" in empty_topic.lower()
        and _clean_human_output(empty_status + empty_search + empty_topic),
        status=empty_status,
        recent=empty_recent,
        topics=empty_topics,
        search=empty_search,
        topic=empty_topic,
    )

    item = add_research_item(
        ResearchMemoryItem(
            id="",
            topic="LangGraph",
            title="LangGraph note",
            summary="LangGraph is useful for stateful agent graphs.",
            content_preview="LangGraph helps build stateful agent workflows with graph nodes.",
            source_type="user_note",
            tags=["langgraph", "agents"],
            confidence="high",
            provenance="verifier",
        )
    )
    failures += emit("add_research_item_stores_item", bool(item.id and item.topic == "LangGraph"), item=item.as_dict())

    recent = list_recent_research(limit=5)
    failures += emit("list_recent_research_returns_item", any(entry.id == item.id for entry in recent), count=len(recent))

    results = search_research_items("LangGraph stateful agents", limit=5)
    failures += emit("search_research_items_finds_matches", bool(results and results[0].id == item.id), results=[r.as_dict() for r in results])

    topic_summary = format_research_topic_summary("LangGraph")
    failures += emit("summarize_topic_human_readable", "LangGraph" in topic_summary and not _has_raw_repr(topic_summary), summary=topic_summary)

    redacted, was_redacted = redact_research_text("OPENAI_API_KEY=sk-test12345678901234567890 bearer abc.def.ghi password: hunter2")
    failures += emit(
        "redactor_removes_secrets",
        was_redacted and "sk-test" not in redacted and "hunter2" not in redacted,
        redacted=redacted,
    )

    secret_item = add_research_item(
        ResearchMemoryItem(
            id="",
            topic="Secrets",
            title="secret-heavy",
            summary="-----BEGIN PRIVATE KEY----- abc -----END PRIVATE KEY-----",
            content_preview="API_TOKEN=abc123456789012345678901234567890 localStorage token",
            source_type="user_note",
            provenance="verifier",
        )
    )
    failures += emit(
        "secret_heavy_note_redacted",
        secret_item.redacted and "API_TOKEN" not in secret_item.content_preview and "PRIVATE KEY" not in secret_item.summary,
        item=secret_item.as_dict(),
    )

    failures += emit("source_domain_extraction", extract_domain("https://github.com/langchain-ai/langgraph") == "github.com")

    status_text = format_research_memory_status()
    failures += emit("research_memory_status_output_human_readable", "Research Memory v2 status" in status_text and _clean_human_output(status_text), status=status_text)

    search_text = format_research_search("LangGraph")
    failures += emit(
        "search_output_includes_provenance_fields",
        "LangGraph" in search_text
        and "Topic:" in search_text
        and "Type:" in search_text
        and "Created:" in search_text
        and _clean_human_output(search_text),
        text=search_text,
    )
    failures += emit("search_output_no_raw_dict_repr", "LangGraph" in search_text and not _has_raw_repr(search_text), text=search_text)
    failures += emit("search_output_no_dataclass_repr", "ResearchSearchResult(" not in search_text and "ResearchMemoryItem(" not in search_text)

    registry = ToolRegistry()
    session: dict[str, Any] = {}
    save_reply = maybe_handle_fast_command("save research note LangGraph: LangGraph helps build stateful agent workflows with graph nodes.", registry, session)
    failures += emit("save_research_note_command_writes_local", bool(save_reply and "Saved research note locally" in save_reply[0]), reply=save_reply)

    redacted_reply = maybe_handle_fast_command(
        "save research note Security: OPENAI_API_KEY=sk-test12345678901234567890 bearer abc.def.ghi password: hunter2",
        registry,
        session,
    )
    redacted_search = format_research_search("Security sensitive")
    failures += emit(
        "save_command_redacts_token_like_text",
        bool(redacted_reply and "Saved research note locally" in redacted_reply[0])
        and "sk-test" not in redacted_search
        and "hunter2" not in redacted_search
        and "Redacted:" in redacted_search
        and _clean_human_output(redacted_search),
        reply=redacted_reply,
        search=redacted_search,
    )

    private_agent = select_agent_for_intent("read my Gmail research emails")
    private_state = run_eva_v2_execute("read my Gmail research emails")
    failures += emit(
        "private_logged_in_research_refused",
        private_agent.name == "safety" and "refused" in private_state.final_response.lower() and "No real action was executed" in private_state.final_response,
        agent=private_agent.name,
        response=private_state.final_response,
    )

    v2_status = run_eva_v2_execute("research memory status")
    failures += emit("v2_execute_research_memory_status", "Research Memory v2 status" in v2_status.final_response, response=v2_status.final_response)

    v2_search = run_eva_v2_execute("search research memory LangGraph")
    failures += emit("v2_execute_search_research_memory", "LangGraph" in v2_search.final_response and "Research memory" in v2_search.final_response, response=v2_search.final_response)

    v2_save = run_eva_v2_execute("save research note LangGraph: sample note stores locally")
    failures += emit("v2_execute_save_research_note", "Saved research note locally" in v2_save.final_response, response=v2_save.final_response)

    v2_plan = maybe_handle_fast_command("eva v2 plan search research memory LangGraph", registry, session)
    failures += emit(
        "v2_plan_mentions_research_memory_local_source",
        bool(v2_plan and "Research Memory v2" in v2_plan[0] and "local" in v2_plan[0].lower()),
        response=v2_plan,
    )

    public = run_eva_v2_execute("search latest AI news")
    failures += emit(
        "v2_public_search_safe_or_unavailable",
        ("Research search unavailable" in public.final_response or "Research public search" in public.final_response) and "No real action was executed" not in public.final_response,
        response=public.final_response,
    )

    failures += emit("tavily_missing_does_not_crash", "Trace:" in public.final_response and "Traceback" not in public.final_response, response=public.final_response)

    for command, case in (
        ("inspect my repo with github mcp", "no_mcp_execution"),
        ("use playwright to open gmail", "no_playwright_execution"),
        ("pyautogui click 10 10", "no_pyautogui_execution"),
        ("run powershell dir", "no_shell_subprocess"),
        ("install requests", "no_package_install"),
        ("read .env.local", "no_env_local_read"),
        ("scrape my logged-in dashboard", "private_dashboard_refused"),
        ("use cookies to access private page", "cookies_private_page_refused"),
        ("bypass login/paywall for research", "bypass_login_paywall_refused"),
    ):
        state = run_eva_v2_execute(command)
        failures += emit(case, "No real action was executed" in state.final_response and "refused" in state.final_response.lower(), response=state.final_response)

    status = research_memory_status()
    failures += emit("status_model_counts", status.item_count >= 3 and status.topic_count >= 2, status=status.as_dict())

    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in [
            ROOT / "backend" / "eva" / "research_memory" / "store.py",
            ROOT / "backend" / "eva" / "research_memory" / "search.py",
            ROOT / "backend" / "eva" / "research_memory" / "sources.py",
            ROOT / "backend" / "eva" / "runtime" / "read_only_delegates.py",
        ]
    )
    failures += emit("no_arbitrary_shell_or_package_install_code", "subprocess" not in source_text and "pip install" not in source_text)

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
