from __future__ import annotations

from collections import Counter
from pathlib import Path
import sqlite3
from typing import Any

from ..privacy.redaction import redact_secrets
from ..observability.traces import log_tool_call
from .state import EvaRuntimeState
from ..core.data_paths import data_path


ROOT = Path(__file__).resolve().parents[3]
MEMORY_DB = ROOT / "data" / "eva.sqlite3"

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".next",
    "dist",
    "build",
    "data",
    "bin",
    "models",
}
SKIP_PATHS = {"frontend/assets", "backend/eva/data", "backend/data/checkpoints"}
SAFE_EXTENSIONS = {".py", ".js", ".ts", ".html", ".css", ".md", ".toml", ".yaml", ".yml", ".json"}
MAJOR_AREAS = (
    "backend/eva/runtime",
    "backend/eva/agents",
    "backend/eva/resources",
    "backend/eva/guardrails",
    "backend/eva/observability",
    "backend/eva/vector_memory",
    "backend/eva/browser_automation",
    "backend/eva/desktop_automation",
    "scripts",
    "docs",
)


def execute_code_readonly_delegate(state: EvaRuntimeState) -> tuple[bool, str]:
    action_type = _primary_action_type(state)
    if action_type == "code.status":
        result = _code_status_summary()
        _trace_code_index(state, "code_index.status", {}, result)
        return True, result
    if action_type in {"code.inspect_structure", "code.summarize_workspace", "code.read_allowed_source_summary"}:
        result = _workspace_structure_summary()
        _trace_code_index(state, "code_index.workspace_summary", {}, result)
        return True, result
    if action_type == "code.summarize_file":
        target = _path_from_intent(state)
        result = _file_summary(target)
        _trace_code_index(state, "code_index.summarize_file", {"path": target}, result)
        return True, result
    if action_type == "code.search_files":
        query = _query_from_intent(state)
        result = _code_search_summary(query)
        _trace_code_index(state, "code_index.search_code", {"query": query}, result)
        return True, result
    if action_type == "code.find_symbols":
        query = _query_from_intent(state)
        result = _symbol_summary(query)
        _trace_code_index(state, "code_index.search_symbols", {"query": query}, result)
        return True, result
    return False, "Code read-only delegate unavailable: this action type is not allowlisted."


def execute_research_readonly_delegate(state: EvaRuntimeState) -> tuple[bool, str]:
    action_type = _primary_action_type(state)
    query = _query_from_intent(state)
    intent_text = str(state.normalized_intent or state.user_request or "").lower()
    if action_type == "research.status":
        if "research memory retrieval status" in intent_text:
            result = _research_memory_retrieval_status_summary()
            _trace_research_memory(state, "research_memory_retrieval_status", {"query": ""}, result)
            return True, result
        result = _research_memory_status_summary()
        _trace_research_memory(state, "research_memory_status", {"query": ""}, result)
        return True, result
    if action_type == "research.memory_search":
        if _is_research_memory_full_dump_request(intent_text):
            result = (
                "Research Memory full dump refused. Use `research memory search <query>`, "
                "`research memory export`, or `research memory topics` instead."
            )
            _trace_research_memory(state, "research_memory_full_dump_refused", {"query": ""}, result)
            return True, result
        result = _research_memory_search_summary(query)
        _trace_research_memory(state, "research_memory_search", {"query": query}, result)
        return True, result
    if action_type == "research.memory_topic_summary":
        result = _research_memory_topic_summary(query)
        _trace_research_memory(state, "research_topic_summary", {"topic": query}, result)
        return True, result
    if action_type == "research.memory_save":
        result = _research_memory_save_summary(state)
        _trace_research_memory(state, "research_memory_save", {"topic": _research_note_parts(state)[0]}, result)
        return True, result
    if action_type in {"research.public_search", "research.public_summary", "research.safe_lookup"}:
        return True, _research_lookup_summary(query)
    return False, "Research read-only delegate unavailable: this action type is not allowlisted."


def execute_memory_readonly_delegate(state: EvaRuntimeState) -> tuple[bool, str]:
    action_type = _primary_action_type(state)
    if action_type == "memory.status":
        return True, _memory_status_summary()
    if action_type in {"memory.recall", "memory.search", "memory.read_user_approved_facts"}:
        return True, _memory_recall_summary(_query_from_intent(state))
    return False, "Memory read-only delegate unavailable: this action type is not allowlisted."


def _primary_action_type(state: EvaRuntimeState) -> str:
    for action in state.proposed_actions:
        if isinstance(action, dict) and action.get("action_type"):
            return str(action["action_type"])
    return ""


def _query_from_intent(state: EvaRuntimeState) -> str:
    text = " ".join(str(state.normalized_intent or state.user_request or "").strip().split())
    lowered = text.lower()
    prefixes = (
        "search latest ",
        "search research memory ",
        "research memory search ",
        "research memory retrieve ",
        "summarize research topic ",
        "summarise research topic ",
        "research topic ",
        "research ",
        "recall what you remember about ",
        "recall ",
        "find symbol ",
        "where is symbol ",
        "symbol search ",
        "code symbols ",
        "code search ",
        "search code for ",
        "search files for ",
        "search project for ",
        "search workspace for ",
        "search ",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return text[len(prefix) :].strip(" .?!")
    return text.strip(" .?!")


def _path_from_intent(state: EvaRuntimeState) -> str:
    text = " ".join(str(state.normalized_intent or state.user_request or "").strip().split())
    lowered = text.lower()
    prefixes = (
        "summarize file ",
        "summarise file ",
        "code file summary ",
        "file summary ",
        "summarize ",
        "summarise ",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return text[len(prefix) :].strip(" .?!")
    return text.strip(" .?!")


def _code_status_summary() -> str:
    try:
        from ..code_index.status import code_index_status

        status = code_index_status()
    except Exception as exc:
        return f"Code status: unavailable safely ({str(exc)[:160]})."
    if not isinstance(status, dict) or not status.get("ok"):
        return f"Code status: unavailable safely ({status.get('error') if isinstance(status, dict) else 'unknown error'})."
    return (
        "Code status: Code index v2 safe metadata index is "
        f"{'ready' if status.get('indexed') else 'not built yet'}. "
        f"Indexed files: {status.get('indexed_files', 0)}. "
        f"Secrets indexed: {'yes' if status.get('secrets_indexed') else 'no'}. "
        "Full file contents stored: no."
    )


def _workspace_structure_summary() -> str:
    try:
        from ..code_index.status import workspace_summary

        result = workspace_summary()
    except Exception:
        result = {}
    if not isinstance(result, dict) or not result.get("ok"):
        counts: Counter[str] = Counter()
        total_seen = 0
        for path in _iter_safe_files(ROOT, limit=2500):
            total_seen += 1
            counts[path.suffix.lower() or "[no extension]"] += 1
        lines = ["Workspace structure summary:"]
        for area in MAJOR_AREAS:
            lines.append(f"- {area}: {'present' if (ROOT / area).exists() else 'missing'}")
        lines.extend(["", "Safe source file counts:"])
        lines.append(f"- Python files: {counts.get('.py', 0)}")
        lines.append(f"- JavaScript files: {counts.get('.js', 0)}")
        lines.append(f"- HTML/CSS files: {counts.get('.html', 0) + counts.get('.css', 0)}")
        lines.append(f"- Markdown docs: {counts.get('.md', 0)}")
        lines.append(f"- YAML configs: {counts.get('.yaml', 0) + counts.get('.yml', 0)}")
        lines.append(f"- Safe files sampled: {total_seen}")
    else:
        counts = Counter(result.get("extension_counts") or {})
        lines = ["Workspace structure summary:"]
        lines.extend(f"- {area}" for area in result.get("major_areas") or [])
        lines.extend(["", "Safe source file counts:"])
        lines.append(f"- Python files: {counts.get('.py', 0)}")
        lines.append(f"- JavaScript/TypeScript files: {counts.get('.js', 0) + counts.get('.ts', 0)}")
        lines.append(f"- HTML/CSS files: {counts.get('.html', 0) + counts.get('.css', 0)}")
        lines.append(f"- Markdown docs: {counts.get('.md', 0)}")
        lines.append(f"- YAML configs: {counts.get('.yaml', 0) + counts.get('.yml', 0)}")
        lines.append(f"- Safe files indexed: {result.get('indexed_files', 0)}")
        lines.append(f"- Cache scope: {result.get('cache_scope')}")
    lines.extend(
        [
            "",
            "Skipped sensitive/runtime folders:",
            "- .git",
            "- .venv",
            "- node_modules",
            "- .env*",
            "- data",
            "- bin",
            "- models",
            "- frontend/assets",
        ]
    )
    return "\n".join(lines)


def _iter_safe_files(root: Path, *, limit: int) -> list[Path]:
    files: list[Path] = []
    stack = [root]
    while stack and len(files) < limit:
        current = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda item: item.name.lower())
        except OSError:
            continue
        for child in children:
            if len(files) >= limit:
                break
            rel = _rel(child)
            if child.is_dir():
                if child.name in SKIP_DIRS or rel in SKIP_PATHS or any(rel.startswith(path + "/") for path in SKIP_PATHS):
                    continue
                stack.append(child)
                continue
            if not child.is_file() or _skip_file(child, rel):
                continue
            files.append(child)
    return files


def _skip_file(path: Path, rel: str) -> bool:
    name = path.name.lower()
    if name.startswith(".env") or any(marker in name for marker in ("secret", "token", "credential")):
        return True
    if path.suffix.lower() not in SAFE_EXTENSIONS:
        return True
    return any(rel.startswith(skip + "/") for skip in SKIP_PATHS)


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _code_search_summary(query: str) -> str:
    if not query:
        return "Code search: no query provided."
    try:
        from ..code_index.search import search_code

        result = search_code(query, limit=8)
    except Exception as exc:
        return f"Code search unavailable safely for {query}: {str(exc)[:160]}."
    matches = result.get("matches") if isinstance(result, dict) else []
    if not matches:
        return f"Code search: no safe indexed matches for {query}."
    lines = [f"Code index v2 matches for {query}:"]
    for item in matches[:8]:
        if isinstance(item, dict) and item.get("path"):
            suffix = f" - {item.get('summary')}" if item.get("summary") else ""
            lines.append(f"- {item.get('path')}{suffix}")
    return "\n".join(lines)


def _symbol_summary(query: str) -> str:
    symbol = query.strip()
    if not symbol:
        return "Symbol search: no symbol provided."
    try:
        from ..code_index.search import search_symbols

        result = search_symbols(symbol, limit=8)
    except Exception as exc:
        return f"Symbol search unavailable safely for {symbol}: {str(exc)[:160]}."
    matches = result.get("matches") if isinstance(result, dict) else []
    if not matches:
        return f"Symbol search: no safe indexed symbol matches for {symbol}."
    lines = [f"Code index v2 symbols for {symbol}:"]
    for item in matches[:8]:
        if isinstance(item, dict):
            lines.append(f"- {item.get('path')}:{item.get('line')} {item.get('kind')}")
    return "\n".join(lines)


def _file_summary(path: str) -> str:
    if not path:
        return "Code file summary: no path provided."
    try:
        from ..code_index.search import summarize_file

        result = summarize_file(path)
    except Exception as exc:
        return f"Code file summary unavailable safely for {path}: {str(exc)[:160]}."
    if not isinstance(result, dict) or not result.get("ok"):
        return f"Code file summary refused safely for {path}: {result.get('error') if isinstance(result, dict) else 'unknown error'}."
    lines = [
        f"Code file summary for {result.get('path')}:",
        str(result.get("summary") or "Summary unavailable."),
        "This is summary-only; no full file contents were returned.",
    ]
    symbols = result.get("symbols") or []
    if symbols:
        lines.append("Symbols: " + ", ".join(str(symbol) for symbol in symbols[:20]))
    return "\n".join(lines)


def _trace_code_index(state: EvaRuntimeState, tool_name: str, args: dict[str, object], result: str) -> None:
    trace_id = str(getattr(state, "trace_id", "") or "")
    if not trace_id:
        return
    try:
        log_tool_call(trace_id, tool_name, args, result[:500])
    except Exception:
        return


def _research_status_summary() -> str:
    try:
        from ..research.skills import research_status

        status = research_status()
    except Exception as exc:
        return f"Research status: unavailable safely ({str(exc)[:160]})."
    if not isinstance(status, dict) or not status.get("ok"):
        return f"Research status: unavailable safely ({status.get('error') if isinstance(status, dict) else 'unknown error'})."
    return (
        "Research status: local SQLite research knowledge is available. "
        f"Topics: {status.get('topic_count', 0)}. Sources: {status.get('item_count', 0)}. "
        f"Notes: {status.get('note_count', 0)}. Sessions: {status.get('session_count', 0)}. "
        f"Retrieval mode: {status.get('retrieval_mode', 'keyword')}."
    )


def _research_memory_status_summary() -> str:
    try:
        from ..research_memory.status import format_research_memory_status

        return format_research_memory_status()
    except Exception as exc:
        return f"Research Memory v2 status: unavailable safely ({str(exc)[:160]})."


def _research_memory_retrieval_status_summary() -> str:
    try:
        from ..research_memory.retrieval import retrieval_status

        return retrieval_status()
    except Exception as exc:
        return f"Research Memory retrieval status: unavailable safely ({str(exc)[:160]})."


def _research_memory_search_summary(query: str) -> str:
    clean_query = query or "research"
    if _looks_private_research(clean_query):
        return "Research Memory v2 refused: private/logged-in research requests are not stored or searched automatically."
    try:
        from ..research_memory.retrieval import format_retrieval_results, retrieve_research

        return format_retrieval_results(retrieve_research(clean_query))
    except Exception as exc:
        return f"Research Memory v2 search unavailable safely for {clean_query}: {str(exc)[:160]}."


def _research_memory_topic_summary(topic: str) -> str:
    clean_topic = topic or "research"
    if _looks_private_research(clean_topic):
        return "Research Memory v2 refused: private/logged-in research topics are not summarized automatically."
    try:
        from ..research_memory.status import format_research_topic_summary

        return format_research_topic_summary(clean_topic)
    except Exception as exc:
        return f"Research Memory v2 topic summary unavailable safely for {clean_topic}: {str(exc)[:160]}."


def _research_note_parts(state: EvaRuntimeState) -> tuple[str, str]:
    text = str(state.normalized_intent or state.user_request or "").strip()
    lowered = text.lower()
    for prefix in ("save research note ", "remember research "):
        if lowered.startswith(prefix):
            payload = text[len(prefix) :].strip()
            if ":" in payload:
                topic, note = payload.split(":", 1)
                return topic.strip(), note.strip()
    return "general", text


def _research_memory_save_summary(state: EvaRuntimeState) -> str:
    topic, note = _research_note_parts(state)
    if not topic or not note:
        return "Research Memory v2 save needs `save research note <topic>: <note>`."
    try:
        from ..research_memory.models import ResearchMemoryItem
        from ..research_memory.sources import extract_tags, looks_private_or_sensitive, redact_research_text
        from ..research_memory.store import add_research_item

        redacted_note, was_redacted = redact_research_text(note)
        item = add_research_item(
            ResearchMemoryItem(
                id="",
                topic=topic,
                title=topic,
                summary=redacted_note[:1500],
                content_preview=redacted_note,
                source_type="user_note",
                tags=extract_tags(f"{topic} {note}"),
                confidence="medium",
                private=looks_private_or_sensitive(note),
                redacted=was_redacted,
                provenance="v2_read_only_delegate:research_memory_save",
            )
        )
    except Exception as exc:
        return f"Research Memory v2 save unavailable safely for {topic}: {str(exc)[:160]}."
    suffix = " Sensitive-looking text was redacted before storage." if item.redacted else ""
    return f"Saved research note locally under {item.topic}. Item: {item.id}.{suffix}"


def _research_lookup_summary(query: str) -> str:
    clean_query = query or "requested topic"
    if _looks_private_research(clean_query):
        return "Research private read refused: logged-in/private pages are outside Phase 4 read-only delegation."
    try:
        from ..tools.tavily_search import tavily_status

        status = tavily_status()
    except Exception as exc:
        return f"Research search unavailable: status check failed safely ({str(exc)[:160]})."
    if not status.get("tavily_configured"):
        return (
            f"Research search unavailable: Tavily is not configured for {clean_query}. "
            "No live web search was run; local saved research can still be recalled."
        )
    try:
        from ..research.collector import collect_web_sources

        result = collect_web_sources(clean_query, max_results=5)
    except Exception as exc:
        return f"Research search unavailable: existing research helper failed safely ({str(exc)[:160]})."
    if not isinstance(result, dict) or not result.get("ok"):
        return f"Research search unavailable: {result.get('error') if isinstance(result, dict) else 'unknown error'} for {clean_query}."
    lines = [f"Research public search: {clean_query}"]
    answer = str(result.get("answer") or "").strip()
    if answer:
        lines.append(_redact(answer[:600]))
    results = result.get("results") if isinstance(result.get("results"), list) else []
    if results:
        lines.append("Top public results:")
    for item in results[:5]:
        if isinstance(item, dict):
            title = _redact(str(item.get("title") or "Untitled")[:160])
            url = _redact(str(item.get("url") or "")[:300])
            lines.append(f"- {title}: {url}" if url else f"- {title}")
    return "\n".join(lines)


def _looks_private_research(query: str) -> bool:
    text = query.lower()
    return any(marker in text for marker in ("logged in", "private page", "gmail", "email", "chat", "bypass", "paywall", "hidden credential", "cookies", "localstorage", "sessionstorage", "scrape"))


def _is_research_memory_full_dump_request(text: str) -> bool:
    lowered = str(text or "").lower()
    return "research memory" in lowered and any(marker in lowered for marker in ("dump all", "show all", "print all", "full dump"))


def _trace_research_memory(state: EvaRuntimeState, event: str, args: dict[str, object], result: str) -> None:
    trace_id = str(getattr(state, "trace_id", "") or "")
    if not trace_id:
        return
    safe_args = {key: str(value)[:180] for key, value in args.items()}
    safe_args["result_length"] = len(str(result or ""))
    try:
        log_tool_call(trace_id, event, safe_args, str(result or "")[:500])
    except Exception:
        return


def _memory_status_summary() -> str:
    if not data_path(MEMORY_DB).exists():
        return "Memory status: local SQLite memory store unavailable; no raw database was dumped."
    try:
        with _connect_memory() as conn:
            message_count = _count_table(conn, "messages")
            event_count = _count_table(conn, "events")
            memory_count = _count_table(conn, "memories")
            task_count = _count_table(conn, "agent_tasks")
    except sqlite3.Error as exc:
        return f"Memory status: unavailable safely ({str(exc)[:160]})."
    return (
        "Memory status: local SQLite memory is available. "
        f"Messages: {message_count}. Events: {event_count}. Approved facts: {memory_count}. Agent tasks: {task_count}. "
        "Output is summary-only; no detailed database entries were dumped."
    )


def _memory_recall_summary(query: str) -> str:
    clean_query = query or "Eva"
    if not data_path(MEMORY_DB).exists():
        return "Memory store unavailable: local SQLite memory database was not found."
    try:
        with _connect_memory() as conn:
            rows = conn.execute(
                """
                SELECT namespace, key, value, source, created_at
                FROM memories
                WHERE key LIKE ? OR value LIKE ? OR namespace LIKE ?
                ORDER BY updated_at DESC
                LIMIT 5
                """,
                (f"%{clean_query}%", f"%{clean_query}%", f"%{clean_query}%"),
            ).fetchall()
    except sqlite3.Error as exc:
        return f"Memory store unavailable: safe recall failed ({str(exc)[:160]})."
    if not rows:
        return f"Memory recall: no approved local facts matched {clean_query}."
    lines = [f"Memory recall: approved local facts matching {clean_query}:"]
    for namespace, key, value, source, created_at in rows:
        summary = _redact(str(value or "")[:220])
        lines.append(f"- {namespace}/{key}: {summary} (source: {source}, saved: {created_at})")
    return "\n".join(lines)


def _connect_memory() -> sqlite3.Connection:
    uri = data_path(MEMORY_DB).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _count_table(conn: sqlite3.Connection, table: str) -> int:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.Error:
        return 0


def _redact(text: str) -> str:
    redacted, _events = redact_secrets(text)
    return redacted
