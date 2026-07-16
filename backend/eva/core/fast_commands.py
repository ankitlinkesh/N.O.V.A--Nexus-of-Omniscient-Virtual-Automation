from __future__ import annotations

import json
import re

from ..diagnostics.health import get_eva_health_summary
from ..diagnostics.providers import format_llm_status
from .fast_command_table import dispatch_status_command
from ..llm.router import get_llm_status, set_llm_mode
from ..core.persona import ASSISTANT_NAME, CAPABILITY_SUMMARY, USER_PROFILE_SUMMARY
from ..core.provenance import answer_provenance_status
from ..core.web_context import (
    last_web_results,
    profile_key_from_message,
    profile_urls,
    remember_web_results,
    result_reference_from_message,
    wants_previous_result,
)
from ..tools.registry import ToolRegistry
from ..tools.tavily_search import tavily_status
from ..vision import vision_status


APP_WORDS = {
    "calculator",
    "chrome",
    "cmd",
    "codex",
    "discord",
    "edge",
    "explorer",
    "notepad",
    "paint",
    "powershell",
    "settings",
    "spotify",
    "task manager",
    "terminal",
    "vscode",
    "vs code",
    "visual studio code",
    "whatsapp",
    "word",
    "excel",
    "powerpoint",
}
FOLDER_WORDS = {"desktop", "documents", "downloads", "pictures", "videos", "music", "eva", "eva folder"}
WEB_ALIASES = {
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "spotify web": "https://open.spotify.com",
    "whatsapp web": "https://web.whatsapp.com",
}
ABOUT_ME_COMMANDS = {
    "tell me about myself",
    "about me",
    "what do you know about me",
    "what do u know about me",
    "who am i",
    "who am i to you",
    "what do you remember about me",
    "what do u remember about me",
}
ABOUT_EVA_COMMANDS = {
    "tell me about yourself",
    "who are you",
    "what are you",
    "introduce yourself",
}
EVA_IDENTITY_SUMMARY = (
    f"I'm {ASSISTANT_NAME} — your local agent running on this laptop."
)
LOCAL_MEMORY_SUMMARY = (
    "Yep. Eva has local SQLite memory on this laptop. Right now I store chat messages and tool events locally, "
    "and I use the known local profile for stable things like your name and Eva project preferences. I'm not a "
    "stateless cloud bot here, but I also won't invent personal facts you haven't told me."
)
AGENT_STATUS_SUMMARY = {
    "mode": "Agentic v2",
    "loop": "bounded plan -> act -> observe -> reflect -> stop/continue",
    "safety": {
        "arbitrary_shell": False,
        "camera": False,
        "always_on_screen": False,
        "power_actions_need_confirmation": True,
        "tools_are_whitelisted": True,
    },
    "features": [
        "initial task plan",
        "step-by-step safe tool execution",
        "observation tracking",
        "reflection after tool results",
        "SQLite chat/event memory",
        "user facts via 'remember that ...'",
        "repeat-action stop",
        "budget limits for tools, web searches, and screen captures",
    ],
}


def _json_debug(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def _format_agent_status(*, raw: bool = False) -> str:
    if raw:
        return _json_debug(AGENT_STATUS_SUMMARY)
    safety = AGENT_STATUS_SUMMARY["safety"]
    return "\n".join(
        [
            "Agent status: Agentic v2 is available.",
            "Loop: bounded plan -> act -> observe -> reflect -> continue/stop.",
            "Verification: tool observations and reflections are tracked before Eva reports completion.",
            "Safety: arbitrary shell is blocked, camera is off, always-on screen watching is off, and power actions require confirmation.",
            f"Limits: {len(AGENT_STATUS_SUMMARY['features'])} tracked agent features are enabled. Say `agent status raw` for debug JSON.",
        ]
    )


def _format_tools_status(tools: ToolRegistry, *, raw: bool = False) -> str:
    specs = tools.list_tools()
    if raw:
        return _json_debug({"tool_count": len(specs), "tools": specs})
    categories: dict[str, int] = {}
    risky: dict[str, int] = {}
    confirmation_count = 0
    rollback_count = 0
    for spec in specs:
        categories[str(spec.get("category") or "general")] = categories.get(str(spec.get("category") or "general"), 0) + 1
        risky[str(spec.get("risk") or "low")] = risky.get(str(spec.get("risk") or "low"), 0) + 1
        confirmation_count += 1 if spec.get("requires_confirmation") else 0
        rollback_count += 1 if spec.get("supports_rollback") else 0
    category_text = ", ".join(f"{name}: {count}" for name, count in sorted(categories.items()))
    risk_text = ", ".join(f"{name}: {count}" for name, count in sorted(risky.items()))
    return "\n".join(
        [
            f"Tools status: Eva has {len(specs)} registered tool specs in the local tool registry.",
            f"Categories: {category_text}.",
            f"Risk levels: {risk_text}.",
            f"Permission-aware tools: {confirmation_count} require confirmation/override; {rollback_count} advertise rollback support.",
            "No arbitrary shell tool is registered as a default path. Say `tools status raw` for debug JSON.",
        ]
    )


def _format_permissions_status(*, raw: bool = False) -> str:
    payload = {
        "safe_local_actions": "allow",
        "privacy_screen_file_chat_reads": "ask_override",
        "external_messages_posts_forms": "ask_confirmation",
        "destructive_file_or_system_changes": "ask_override",
        "power_actions": "ask_confirmation",
        "shell_default": "hard_block",
        "override_phrase": "confirm override",
        "override_expires_after_seconds": 120,
        "hard_blocks": ["credential theft", "spyware behavior", "malware-like actions", "illegal harmful requests"],
    }
    if raw:
        return _json_debug(payload)
    return "\n".join(
        [
            "Permissions status: Eva's local permission gate is active.",
            "Allowed: safe local reads and bounded visible UI actions.",
            "Confirmation required: external messages, posts, form submits, and guarded power actions.",
            "Override required: privacy-sensitive reads, destructive file actions, and system-changing actions. Override phrase: `confirm override`.",
            "Hard blocked: credential access, spying, malware-like behavior, illegal harmful requests, and arbitrary shell by default.",
            "Say `permissions status raw` for debug JSON.",
        ]
    )


def _format_code_status(result: object, *, raw: bool = False) -> str:
    if raw:
        return _json_debug(result)
    if not isinstance(result, dict) or not result.get("ok"):
        return f"Code status: unavailable safely ({result.get('error') if isinstance(result, dict) else 'unknown error'})."
    indexed = "ready" if result.get("indexed") else "not built yet"
    return (
        f"Code status: safe code index is {indexed}. "
        f"Indexed files: {result.get('indexed_files', 0)}. "
        f"Secrets indexed: {'yes' if result.get('secrets_indexed') else 'no'}. "
        "Say `code status raw` for debug JSON."
    )


def _format_research_status(result: object, *, raw: bool = False) -> str:
    if raw:
        return _json_debug(result)
    if not isinstance(result, dict) or not result.get("ok"):
        return f"Research status: unavailable safely ({result.get('error') if isinstance(result, dict) else 'unknown error'})."
    return (
        "Research status: local SQLite research knowledge is available. "
        f"Topics: {result.get('topic_count', 0)}. Sources: {result.get('item_count', 0)}. "
        f"Notes: {result.get('note_count', 0)}. Sessions: {result.get('session_count', 0)}. "
        "Say `research status raw` for debug JSON."
    )


def _save_research_memory_note(topic: str, note: str, tags: object | None = None) -> str:
    from ..research_memory.models import ResearchMemoryItem
    from ..research_memory.quality import normalize_tags
    from ..research_memory.sources import extract_tags, looks_private_or_sensitive, redact_research_text
    from ..research_memory.store import add_research_item

    clean_topic = str(topic or "").strip()
    clean_note = str(note or "").strip()
    if not clean_topic or not clean_note:
        return "Give me a research topic and note, like `save research note LangGraph: graph workflows`."
    redacted_note, was_redacted = redact_research_text(clean_note)
    item = add_research_item(
        ResearchMemoryItem(
            id="",
            topic=clean_topic,
            title=clean_topic,
            summary=redacted_note[:1500],
            content_preview=redacted_note,
            source_type="user_note",
            source_url=None,
            source_domain=None,
            tags=normalize_tags(tags) or extract_tags(f"{clean_topic} {clean_note}"),
            confidence="medium",
            private=looks_private_or_sensitive(clean_note),
            redacted=was_redacted,
            provenance="fast_command:research_memory_save",
        )
    )
    suffix = " Sensitive-looking text was redacted before storage." if item.redacted else ""
    return f"Saved research note locally under {item.topic}. Item: {item.id}.{suffix}"


def _format_eva_v2_status() -> str:
    from ..runtime.feature_flags import eva_v2_runtime_status
    from ..runtime.graph import is_langgraph_available

    status = eva_v2_runtime_status()
    flags = status.get("flags") if isinstance(status.get("flags"), dict) else {}
    enabled = "enabled" if status.get("enabled") else "installed but disabled"
    return "\n".join(
        [
            f"Eva v2 runtime status: {enabled}.",
            "EVA_V2_RUNTIME_ENABLED=false, so the current Eva routing and Agentic v2 loop remain active by default."
            if not status.get("enabled")
            else "EVA_V2_RUNTIME_ENABLED=true, so safe demo requests may pass through the v2 skeleton.",
            f"Optional graph: LangGraph {'available' if is_langgraph_available() else 'not installed or disabled'}; flag EVA_V2_LANGGRAPH_ENABLED={str(flags.get('langgraph_enabled', False)).lower()}.",
            "Phase 1 scope: typed state/actions, specialist-agent selection, guardrail hooks, local traces, vector-memory interfaces, and optional automation adapters.",
        ]
    )


def _format_agents_status() -> str:
    from ..runtime.supervisor import supervisor_status

    status = supervisor_status()
    agents = status.get("agents") if isinstance(status.get("agents"), list) else []
    lines = [f"Specialist agents status: {len(agents)} v2 skeleton agents are registered."]
    for item in agents:
        if isinstance(item, dict):
            lines.append(f"- {item.get('name')}: {item.get('delegated_core')}")
    lines.append("They propose/delegate through existing Eva systems; they do not replace the current loop yet.")
    return "\n".join(lines)


def _format_guardrails_status() -> str:
    from ..guardrails.llm_guard_adapter import is_llm_guard_available
    from ..runtime.feature_flags import get_v2_feature_flags

    flags = get_v2_feature_flags()
    available = is_llm_guard_available()
    enabled = bool(flags.llm_guard_enabled and available)
    return "\n".join(
        [
            f"Guardrails status: LLM Guard package is {'available' if available else 'not installed'}; adapter enabled: {enabled}.",
            "Fallback guardrails are active for Phase 1: secret redaction, prompt-injection phrase detection, suspicious tool-call checks, and output-safety checks.",
            "The Cloud Context Firewall and Permission Gate remain the authority for private local context and risky actions.",
        ]
    )


def _format_vector_memory_status() -> str:
    from ..vector_memory.retriever import vector_memory_status

    status = vector_memory_status()
    return "\n".join(
        [
            f"Vector memory status: interfaces installed, primary backend is {status.get('primary')}.",
            f"Chroma enabled: {status.get('chroma', {}).get('enabled') if isinstance(status.get('chroma'), dict) else False}. Qdrant enabled: {status.get('qdrant', {}).get('enabled') if isinstance(status.get('qdrant'), dict) else False}.",
            "Vector memory is disabled by default; Eva keeps using local SQLite memory/research retrieval unless explicitly configured.",
        ]
    )


def _format_traces_status() -> str:
    from ..observability.langfuse_adapter import langfuse_status
    from ..observability.traces import traces_status

    local = traces_status()
    langfuse = langfuse_status()
    return "\n".join(
        [
            f"Traces status: local trace store is {local.get('backend')} at {local.get('path')}.",
            f"Langfuse enabled: {langfuse.get('enabled')} ({langfuse.get('message')}).",
            "Trace payloads are redacted before local write; remote tracing is disabled unless explicitly configured later.",
        ]
    )


def _format_traces_list() -> str:
    from ..observability.traces import list_traces

    traces = list_traces(limit=10)
    if not traces:
        return "No recent traces found. Tracing is off by default; enable EVA_TRACING_ENABLED to record traces."
    lines = ["Recent traces:"]
    for trace in traces:
        request = str(trace.get("request") or "").strip()
        if len(request) > 80:
            request = request[:80] + "…"
        lines.append(f"- {trace.get('trace_id')} ({trace.get('event_count')} events): {request or '(no request captured)'}")
    return "\n".join(lines)


def _format_trace_show(trace_id: str) -> str:
    from ..observability.traces import read_trace

    trace = read_trace(trace_id)
    if not trace.get("found"):
        return f"No trace found for `{trace_id}`."
    lines = [f"Trace {trace_id}:"]
    for event in trace.get("events", []):
        event_type = str(event.get("type") or "unknown")
        payload = event.get("payload")
        preview = json.dumps(payload, ensure_ascii=False, default=str) if payload is not None else ""
        if len(preview) > 120:
            preview = preview[:120] + "…"
        lines.append(f"- {event_type}: {preview}")
    return "\n".join(lines)


def _format_evals_status() -> str:
    from ..evals import benchmark_adapters, run_offline_evals

    report = run_offline_evals()
    lines = [report.summary_text()]
    lines.append("Benchmark availability (all inert/gated unless explicitly opted in via env flags):")
    for adapter in benchmark_adapters():
        status = adapter.availability()
        lines.append(f"- {status.get('name')}: available={status.get('available')} ({status.get('reason')})")
    return "\n".join(lines)


def _format_activation_status() -> str:
    from ..runtime.activation import current_activation_status

    status = current_activation_status()
    mind = status["mind"]
    hands = status["hands_external"]

    def _state(flag: bool) -> str:
        return "ON" if flag else "off"

    lines = [
        f"Activation profile: {status['profile']} (set EVA_PROFILE to change).",
        "Mind capabilities (a profile may enable these):",
        f"- tracing: {_state(mind['tracing'])}",
        f"- vector_memory: {_state(mind['vector_memory'])}",
        f"- native_function_calling: {_state(mind['native_function_calling'])}",
        "Hands & external (manual only — never auto-enabled by a profile):",
        f"- real_input: {_state(hands['real_input'])}",
        f"- browser: {_state(hands['browser'])}",
        f"- mcp: {_state(hands['mcp'])}",
        str(status["note"]),
    ]
    return "\n".join(lines)


def _format_exercise_status() -> str:
    from ..evals import run_offline_exercise

    return run_offline_exercise().summary_text()


def _format_automation_adapters_status() -> str:
    from ..browser_automation.playwright_driver import playwright_status
    from ..desktop_automation.pyautogui_driver import pyautogui_status

    playwright = playwright_status()
    pyautogui = pyautogui_status()
    return "\n".join(
        [
            f"Automation adapters status: Playwright enabled={playwright.get('enabled')} available={playwright.get('available')}.",
            f"PyAutoGUI strict adapter enabled={pyautogui.get('enabled')} available={pyautogui.get('available')}.",
            "Existing Chrome/Desktop skills remain primary. Optional adapters refuse unsafe reads, raw coordinate clicks, and unconfirmed external/destructive actions.",
        ]
    )


def _handle_eva_v2_preview_command(normalized: str, original: str) -> tuple[str, str] | None:
    commands = (
        ("eva v2 dry run ", "dry_run"),
        ("eva v2 plan ", "plan"),
        ("eva v2 route ", "route"),
    )
    for prefix, mode in commands:
        if not normalized.startswith(prefix):
            continue
        request = original[len(prefix) :].strip()
        if not request:
            return "Give me a request after the v2 preview command, like `eva v2 dry run open ChatGPT on Chrome`.", "fast-command"
        if mode == "route":
            from ..runtime.graph import run_eva_v2_route_preview

            state = run_eva_v2_route_preview(request)
        elif mode == "plan":
            from ..runtime.graph import run_eva_v2_plan_preview

            state = run_eva_v2_plan_preview(request)
        else:
            from ..runtime.graph import run_eva_v2_dry_run

            state = run_eva_v2_dry_run(request)
        return state.final_response, "fast-command"
    return None


def _handle_eva_v2_execute_command(normalized: str, original: str) -> tuple[str, str] | None:
    for prefix in ("eva v2 execute ", "eva v2 run "):
        if not normalized.startswith(prefix):
            continue
        request = original[len(prefix) :].strip()
        if not request:
            return "Give me a request after the v2 execution command, like `eva v2 execute resources status`.", "fast-command"
        from ..runtime.graph import run_eva_v2_execute

        state = run_eva_v2_execute(request)
        return state.final_response, "fast-command"
    return None


def _handle_resource_registry_command(normalized: str, original: str) -> tuple[str, str] | None:
    if normalized in {"resources status", "resource registry status"}:
        from ..resources.status import format_resource_registry_status

        return format_resource_registry_status(), "fast-command"

    if normalized == "resources safe":
        from ..resources.status import format_resources_by_status

        return format_resources_by_status("safe"), "fast-command"

    if normalized == "resources experimental":
        from ..resources.status import format_resources_by_status

        return format_resources_by_status("experimental"), "fast-command"

    if normalized == "resources blocked":
        from ..resources.status import format_resources_by_status

        return format_resources_by_status("blocked"), "fast-command"

    if normalized in {"resource categories", "resources categories"}:
        from ..resources.status import format_resource_categories

        return format_resource_categories(), "fast-command"

    if normalized in {"mcp status", "mcp policy status"}:
        from ..resources.status import format_mcp_policy_status

        return format_mcp_policy_status(), "fast-command"

    if normalized in {"open source tools status", "open-source tools status", "open source status"}:
        from ..resources.status import format_open_source_tools_status

        return format_open_source_tools_status(), "fast-command"

    for prefix in ("resource detail ", "tool resource detail "):
        if normalized.startswith(prefix):
            resource_id = original[len(prefix):].strip()
            if not resource_id:
                return "Give me a resource id, like `resource detail github-mcp-server`.", "fast-command"
            from ..resources.status import format_resource_detail

            return format_resource_detail(resource_id), "fast-command"

    return None


def _looks_like_identity_joke(original: str, payload: str) -> bool:
    text = f"{original} {payload}".lower()
    return bool(re.search(r"\b(my name is|i am|i'm|call me)\b", text)) and any(marker in text for marker in ("lmao", "lol", "jk", "joking", "just kidding"))


def _is_about_me_command(text: str) -> bool:
    if any(command in text for command in ABOUT_ME_COMMANDS):
        return True
    return (
        ("what" in text or "tell" in text or "remember" in text)
        and ("know" in text or "remember" in text)
        and ("about me" in text or "abt me" in text or "about myself" in text)
    )


def _is_local_memory_question(text: str) -> bool:
    memory_words = ("memory", "remember", "store", "storage", "sqlite", "local")
    can_words = ("can", "could", "right", "rite", "yes", "u can", "you can")
    return (
        any(word in text for word in memory_words)
        and any(word in text for word in can_words)
        and ("sqlite" in text or "local" in text or "store" in text or "memory" in text)
    )


def _remember_payload(original: str) -> str | None:
    lowered = original.lower().strip()
    for prefix in ("remember that ", "remember this ", "save this ", "store this "):
        if lowered.startswith(prefix):
            return original[len(prefix):].strip(" .")
    return None


def _project_note_payload(original: str) -> str | None:
    lowered = original.lower().strip()
    for prefix in ("remember project note that ", "remember project note ", "save project note that ", "store project note that "):
        if lowered.startswith(prefix):
            return original[len(prefix):].strip(" .")
    return None


def _memory_facts_summary(memory: object | None) -> str:
    if memory is None or not hasattr(memory, "recent_memories"):
        return ""
    try:
        facts = memory.recent_memories(limit=5)
    except Exception:
        return ""
    if not facts:
        return ""
    lines = ["Extra things you've asked me to remember locally:"]
    for fact in facts[:5]:
        value = str(fact.get("value") or "").strip()
        if value:
            lines.append(f"- {value}")
    return "\n".join(lines)


def _user_model_summary(memory: object | None) -> str:
    """Report the durable, learned user model (Phase 43)."""
    if memory is None or not hasattr(memory, "_user_model"):
        return "Durable user model is unavailable in this route."
    try:
        model = memory._user_model()
    except Exception:
        model = None
    if model is None:
        return "Durable user model is off. Set EVA_USER_MODEL_ENABLED=1 (or EVA_PROFILE=daily) to let me learn compounding facts about you."
    try:
        data = model.summary()
        beliefs = data.get("beliefs") or []
    except Exception:
        return "I could not read the durable user model."
    if not beliefs:
        return "I haven't learned any durable facts about you yet. Tell me things like where you live or what you're allergic to, and they'll compound over time."
    lines = ["Here's what I've durably learned about you (most-confident first):"]
    for belief in beliefs[:12]:
        seen = belief.get("evidence_count", 1)
        seen_txt = f", seen {seen}x" if isinstance(seen, int) and seen > 1 else ""
        lines.append(f"- {belief.get('attribute')}: {belief.get('value')} (confidence {belief.get('confidence')}{seen_txt})")
    return "\n".join(lines)


def _consolidate_user_model(memory: object | None, session_id: str | None) -> str:
    """Distil recent raw chat turns into the structured user model."""
    if memory is None or not hasattr(memory, "_user_model"):
        return "Durable user model is unavailable in this route."
    try:
        model = memory._user_model()
    except Exception:
        model = None
    if model is None:
        return "Durable user model is off. Set EVA_USER_MODEL_ENABLED=1 (or EVA_PROFILE=daily) first."
    try:
        result = model.consolidate(memory, session_id=session_id)
    except Exception:
        return "I could not consolidate memory just now."
    return f"Consolidated memory: scanned {result.get('scanned', 0)} of your messages and learned/reinforced {result.get('learned', 0)} durable fact(s)."


def _situation_report() -> str:
    """Report the opt-in, metadata-only situational model (Phase 44). No pixels."""
    try:
        from ..perception.situational_model import capture_situation, perception_enabled, situational_summary
    except Exception:
        return "Situational awareness is unavailable in this build."
    if not perception_enabled():
        return (
            "Situational awareness is off (opt-in). Set EVA_PERCEPTION_ENABLED=1 to let me ground on "
            "which app you're using — from window metadata only, never a screenshot. Pixel reading stays the "
            "gated 'observe screen' action."
        )
    snap = capture_situation()
    if not snap.available:
        return "I couldn't read any window metadata right now (nothing focused, or unsupported host)."
    summary = situational_summary(snap)
    note = " A privacy-sensitive window title was hidden." if snap.privacy_redacted else ""
    return (summary or "No foreground app is observable right now.") + note + " (No screenshot was taken.)"


def _open_durable_queue():
    try:
        from ..tasks import open_default_queue
        return open_default_queue()
    except Exception:
        return None


_QUEUE_DISABLED_MSG = (
    "The durable task queue is off. Set EVA_DURABLE_QUEUE_ENABLED=1 to let me remember tasks across "
    "restarts. (Queued tasks still run through the permission gate — nothing privileged runs unattended.)"
)


def _durable_queue_status() -> str:
    queue = _open_durable_queue()
    if queue is None:
        return _QUEUE_DISABLED_MSG
    s = queue.stats()
    return (
        f"Durable task queue: {s.get('total', 0)} total | "
        f"queued {s.get('queued', 0)}, running {s.get('running', 0)}, succeeded {s.get('succeeded', 0)}, "
        f"failed {s.get('failed', 0)}, cancelled {s.get('cancelled', 0)}."
    )


def _durable_queue_recover() -> str:
    queue = _open_durable_queue()
    if queue is None:
        return _QUEUE_DISABLED_MSG
    r = queue.recover_orphans()
    return (
        f"Recovered {r.get('recovered', 0)} interrupted task(s) back into the queue and abandoned "
        f"{r.get('abandoned', 0)} that had run out of attempts. Recovered tasks re-run through the gate."
    )


def _durable_queue_enqueue(text: str) -> str:
    queue = _open_durable_queue()
    if queue is None:
        return _QUEUE_DISABLED_MSG
    task = queue.enqueue(text, source="user")
    if task is None:
        return "I couldn't queue that — the task text was empty."
    return f"Queued a durable task (id {task.id[:8]}): {task.request}. It survives restarts and runs through the gate."


_PROACTIVITY_DISABLED_MSG = (
    "Proactivity is off. Set EVA_PROACTIVITY_ENABLED=1 to let me act on standing rules (schedules, "
    "file watchers). Rules only ever PROPOSE work — anything they queue still needs the gate, and a "
    "privileged action still waits for your confirmation."
)


def _proactivity_rules() -> str:
    try:
        from ..proactivity import open_default_store, proactivity_enabled
    except Exception:
        return "Proactivity is unavailable in this build."
    if not proactivity_enabled():
        return _PROACTIVITY_DISABLED_MSG
    store = open_default_store()
    if store is None:
        return _PROACTIVITY_DISABLED_MSG
    rules = store.list_rules()
    if not rules:
        return "No proactive rules yet. Rules propose work on a schedule or when a file changes; they never act on their own."
    lines = [f"Proactive rules ({len(rules)}):"]
    for rule in rules[:15]:
        state = "on" if rule.enabled else "off"
        last = rule.last_fired_at or "never"
        lines.append(f"- [{state}] {rule.name} ({rule.kind}) -> '{rule.request}' | last fired: {last}")
    lines.append("Rules only propose; every queued task still runs through the permission gate.")
    return "\n".join(lines)


def _proactivity_tick() -> str:
    try:
        from ..proactivity import open_default_engine, proactivity_enabled
    except Exception:
        return "Proactivity is unavailable in this build."
    if not proactivity_enabled():
        return _PROACTIVITY_DISABLED_MSG
    engine = open_default_engine()
    if engine is None:
        return _PROACTIVITY_DISABLED_MSG
    result = engine.tick()
    proposed = result.get("proposed") or []
    suppressed = result.get("suppressed") or []
    if not proposed:
        extra = f" ({len(suppressed)} suppressed by rate limits)" if suppressed else ""
        return f"Checked {result.get('evaluated', 0)} rule(s); nothing is due right now{extra}."
    lines = [f"Checked {result.get('evaluated', 0)} rule(s) and queued {len(proposed)} proposal(s):"]
    for item in proposed[:10]:
        lines.append(f"- {item.get('rule')}: {item.get('request')}")
    lines.append("These are queued for approval — nothing ran; each still goes through the gate.")
    return "\n".join(lines)


def _proactivity_notifications() -> str:
    try:
        from ..proactivity import open_default_store, proactivity_enabled
    except Exception:
        return "Proactivity is unavailable in this build."
    if not proactivity_enabled():
        return _PROACTIVITY_DISABLED_MSG
    store = open_default_store()
    if store is None:
        return _PROACTIVITY_DISABLED_MSG
    notes = store.list_notifications(limit=10)
    if not notes:
        return "No notifications."
    lines = [f"Notifications ({len(notes)}):"]
    for note in notes:
        mark = "" if note.read else "* "
        lines.append(f"- {mark}{note.message}")
    store.mark_all_read()
    return "\n".join(lines)


def _after_prefix(text: str, prefixes: tuple[str, ...]) -> str | None:
    for prefix in prefixes:
        if text.startswith(prefix):
            value = text[len(prefix):].strip(" :")
            if value:
                return value
    return None


def _parse_between(text: str, prefix: str, separator: str) -> tuple[str, str] | None:
    if not text.startswith(prefix):
        return None
    payload = text[len(prefix):]
    index = payload.find(separator)
    if index <= 0:
        return None
    left = payload[:index].strip()
    right = payload[index + len(separator):].strip()
    if not left or not right:
        return None
    return left, right


def _parse_replace_draft(text: str) -> tuple[str, str, str] | None:
    return _parse_replace_with_prefix(text, "eva file draft replace ")


def _parse_replace_with_prefix(text: str, prefix: str) -> tuple[str, str, str] | None:
    old_marker = " old "
    new_marker = " new "
    if not text.startswith(prefix):
        return None
    payload = text[len(prefix):]
    old_index = payload.find(old_marker)
    if old_index <= 0:
        return None
    new_index = payload.find(new_marker, old_index + len(old_marker))
    if new_index <= old_index:
        return None
    path_text = payload[:old_index].strip()
    old_text = payload[old_index + len(old_marker):new_index].strip()
    new_text = payload[new_index + len(new_marker):].strip()
    if not path_text or not old_text or not new_text:
        return None
    return path_text, old_text, new_text


def _format_web_search_result(result: object) -> str:
    if not isinstance(result, dict):
        return str(result)
    query = result.get("query") or "your search"
    if result.get("ok") and result.get("provider") == "tavily":
        personal_profile = _looks_like_personal_profile_query(str(query))
        lines = [
            "I found possible matches, but I can't assume which one is yours."
            if personal_profile
            else f"I searched Tavily for: {query}."
        ]
        answer = str(result.get("answer") or "").strip()
        if answer and not personal_profile:
            lines.append(answer)
        results = result.get("results") or []
        if isinstance(results, list) and results:
            lines.append("Options:" if personal_profile else "Top results:")
            for item in results[:5]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "Untitled")
                url = str(item.get("url") or "")
                lines.append(f"- {title}: {url}" if url else f"- {title}")
        return "\n".join(lines)
    if result.get("fallback") == "browser":
        reason = result.get("error") or "unavailable"
        return f"Tavily search was {reason}, so I opened a browser search for: {query}."
    return str(result)


def _format_screen_result(result: object) -> str:
    if not isinstance(result, dict):
        return str(result)
    if not result.get("ok"):
        summary = str(result.get("summary") or "").strip()
        if result.get("rate_limited") and summary:
            return summary
        return f"I captured the screen once, but vision analysis failed: {result.get('error') or 'unknown error'}."
    summary = str(result.get("summary") or "").strip()
    issue = str(result.get("possible_issue") or "").strip()
    actions = result.get("suggested_actions") or []
    chunks = [summary or "I analyzed the screen, but the image is unclear."]
    if issue:
        chunks.append(f"Possible issue: {issue}")
    if isinstance(actions, list) and actions:
        chunks.append("Try this: " + "; ".join(str(item) for item in actions[:3] if str(item).strip()))
    return " ".join(chunks)


def _format_workspace_result(result: object, *, mode: str = "generic") -> str:
    if not isinstance(result, dict):
        return str(result)
    if not result.get("ok"):
        return f"I refused that workspace request safely: {result.get('error') or 'unknown error'}."

    if mode == "status" or "exclude_dirs" in result:
        return json.dumps(result, indent=2)

    if "sections" in result:
        lines = ["Here is Eva's project shape:"]
        for section in result.get("sections") or []:
            if not isinstance(section, dict):
                continue
            folder = section.get("folder")
            description = section.get("description")
            lines.append(f"- {folder}: {description}")
            notable = section.get("notable_files") or []
            if notable:
                lines.append("  Key files: " + ", ".join(str(item) for item in notable[:5]))
        lines.append("Workspace scan is read-only and skips secrets/runtime folders.")
        return "\n".join(lines)

    if "matches" in result:
        matches = result.get("matches") or []
        if not matches:
            return f"I searched the Eva workspace for '{result.get('query')}', but did not find a safe match."
        lines = [f"I searched the Eva workspace for '{result.get('query')}'. Top matches:"]
        for item in matches[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('path')}:{item.get('line')} - {item.get('snippet')}")
        return "\n".join(lines)

    if "files" in result:
        files = result.get("files") or []
        lines = [f"I found {len(files)} safe workspace files" + (" in " + str(result.get("path")) if result.get("path") else "") + ":"]
        for item in files[:80]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('path')} ({item.get('size')} bytes)")
        if result.get("truncated"):
            lines.append("More files exist, but I stopped at the configured scan limit.")
        return "\n".join(lines)

    if "content" in result:
        content = str(result.get("content") or "")
        snippet = content[:6000]
        suffix = "\n\n[truncated]" if result.get("truncated") else ""
        return f"Read `{result.get('path')}` safely:\n```text\n{snippet}\n```{suffix}"

    if "summary" in result:
        return f"{result.get('summary')}"

    return json.dumps(result, indent=2)


def _format_code_index_status(result: object) -> str:
    if not isinstance(result, dict) or not result.get("ok"):
        error = result.get("error") if isinstance(result, dict) else "unknown error"
        return f"Code index v2 status unavailable safely: {error}."
    if not result.get("indexed"):
        return "Code index v2 status: no local metadata cache has been built yet. Run `code index refresh` to build it."
    return (
        "Code index v2 status: ready. "
        f"Indexed files: {result.get('indexed_files', 0)}. "
        f"Skipped: {result.get('skipped', 0)}. "
        "Cache: local metadata only. Full file contents stored: no. Secrets indexed: no."
    )


def _format_code_index_refresh(result: object) -> str:
    if not isinstance(result, dict) or not result.get("ok"):
        error = result.get("error") if isinstance(result, dict) else "unknown error"
        return f"Code index v2 refresh failed safely: {error}."
    return (
        "Code index v2 refreshed. "
        f"Indexed {result.get('indexed_files', 0)} safe files and skipped {result.get('skipped', 0)} blocked/unsupported files. "
        "The cache stores metadata only, not full file contents."
    )


def _format_code_index_search(result: object) -> str:
    if not isinstance(result, dict) or not result.get("ok"):
        error = result.get("error") if isinstance(result, dict) else "unknown error"
        return f"Code index v2 search refused safely: {error}."
    matches = result.get("matches") or []
    if not matches:
        return f"Code index v2 matches for `{result.get('query')}`: none found in the safe metadata index."
    lines = [f"Code index v2 matches for `{result.get('query')}`:"]
    for item in matches[:8]:
        if isinstance(item, dict):
            lines.append(f"- {item.get('path')}: {item.get('summary')}")
    return "\n".join(lines)


def _format_code_index_symbols(result: object) -> str:
    if not isinstance(result, dict) or not result.get("ok"):
        error = result.get("error") if isinstance(result, dict) else "unknown error"
        return f"Code index v2 symbol search refused safely: {error}."
    matches = result.get("matches") or []
    if not matches:
        return f"Code index v2 symbols for `{result.get('query')}`: none found."
    lines = [f"Code index v2 symbols for `{result.get('query')}`:"]
    for item in matches[:10]:
        if isinstance(item, dict):
            lines.append(f"- {item.get('name')} ({item.get('kind')}) in {item.get('path')}:{item.get('line')}")
    return "\n".join(lines)


def _format_code_index_workspace(result: object) -> str:
    if not isinstance(result, dict) or not result.get("ok"):
        error = result.get("error") if isinstance(result, dict) else "unknown error"
        return f"Workspace summary unavailable safely: {error}."
    lines = ["Workspace summary:"]
    for area in result.get("major_areas") or []:
        lines.append(f"- {area}")
    lines.append(f"Indexed safe files: {result.get('indexed_files', 0)}.")
    lines.append(str(result.get("safety") or "Code index stores metadata only."))
    return "\n".join(lines)


def _format_code_index_file_summary(result: object) -> str:
    if not isinstance(result, dict) or not result.get("ok"):
        error = result.get("error") if isinstance(result, dict) else "unknown error"
        return f"Code file summary refused safely: {error}."
    lines = [
        f"Code file summary for `{result.get('path')}`:",
        str(result.get("summary") or "Summary unavailable."),
        "Summary-only local read; full file contents were not returned.",
    ]
    symbols = result.get("symbols") or []
    if symbols:
        lines.append("Symbols: " + ", ".join(str(symbol) for symbol in symbols[:20]))
    return "\n".join(lines)


def _format_code_result(result: object, *, mode: str = "generic") -> str:
    if not isinstance(result, dict):
        return str(result)
    if not result.get("ok"):
        return f"Code intelligence refused that safely: {result.get('error') or 'unknown error'}."

    if mode == "status":
        return _format_code_status(result)

    if mode == "reindex":
        return f"Code index refreshed. Indexed {result.get('indexed_files', 0)} safe files. Skipped {result.get('skipped', 0)} blocked/unsupported files."

    if mode == "project_map":
        lines = [f"Code project map: {result.get('indexed_files', 0)} indexed files."]
        for module in result.get("modules") or []:
            if isinstance(module, dict):
                lines.append(f"- {module.get('folder')}: {module.get('description')} ({module.get('file_count')} files)")
        return "\n".join(lines)

    if mode == "search":
        matches = result.get("matches") or []
        if not matches:
            return f"I searched the code index for '{result.get('query')}', but found no safe matches."
        lines = [f"Code matches for '{result.get('query')}':"]
        for item in matches[:8]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('path')}: {item.get('summary')}")
        return "\n".join(lines)

    if mode == "find_symbol":
        matches = result.get("matches") or []
        if not matches:
            return f"I couldn't find symbol `{result.get('symbol')}` in the safe code index."
        lines = [f"Symbol matches for `{result.get('symbol')}`:"]
        for item in matches[:10]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('name')} ({item.get('kind')}) in {item.get('path')}:{item.get('line')}")
        return "\n".join(lines)

    if mode == "explain_feature":
        lines = [str(result.get("summary") or "Feature locations found.")]
        related = result.get("related_files") or []
        if related:
            lines.append("Relevant files:")
            lines.extend(f"- {path}" for path in related[:10])
        return "\n".join(lines)

    if mode == "debug_traceback":
        lines = [
            f"Error: {result.get('exception_type') or 'unknown'} - {result.get('exception_message') or 'no message'}",
            str(result.get("likely_cause") or "Likely cause needs inspection."),
        ]
        likely = result.get("likely_files") or []
        if likely:
            lines.append("Files to inspect:")
            lines.extend(f"- {path}" for path in likely[:8])
        tests = result.get("suggested_tests") or []
        if tests:
            lines.append("Tests to run:")
            lines.extend(f"- {test}" for test in tests[:4])
        return "\n".join(lines)

    if mode == "plan_change":
        lines = [f"Patch plan for: {result.get('goal')}"]
        files = result.get("likely_files") or []
        if files:
            lines.append("Likely files:")
            lines.extend(f"- {path}" for path in files[:10])
        steps = result.get("proposed_steps") or []
        if steps:
            lines.append("Steps:")
            lines.extend(f"- {step}" for step in steps[:8])
        tests = result.get("tests_to_run") or []
        if tests:
            lines.append("Tests:")
            lines.extend(f"- {test}" for test in tests[:5])
        risks = result.get("risks") or []
        if risks:
            lines.append("Risks:")
            lines.extend(f"- {risk}" for risk in risks[:5])
        lines.append("This is planning-only. I will not edit files unless you explicitly ask.")
        return "\n".join(lines)

    return json.dumps(result, indent=2)


def _format_research_result(result: object, *, mode: str = "generic") -> str:
    if not isinstance(result, dict):
        return str(result)
    if not result.get("ok"):
        if result.get("fallback") == "browser":
            return f"Tavily is unavailable for research right now, so only limited browser fallback is available for: {result.get('query')}."
        return f"Research request failed safely: {result.get('error') or 'unknown error'}."

    if mode == "status" or "topic_count" in result:
        return _format_research_status(result)

    if mode == "start_topic" or "topic" in result and "message" in result:
        return str(result.get("message") or f"Research topic ready: {result.get('topic')}")

    if mode == "save_note":
        return str(result.get("message") or f"Saved research note for {result.get('topic')}.")

    if mode == "recall":
        matches = result.get("matches") or []
        topic = result.get("topic")
        if not matches:
            return f"I don't have saved research on {topic} yet."
        lines = [f"Here is what I know locally about {topic}:"]
        for item in matches[:5]:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "source":
                lines.append(f"- {item.get('title')}: {item.get('url')} - {item.get('text')}")
            else:
                lines.append(f"- {item.get('text')}")
        return "\n".join(lines)

    if mode == "summary" or "summary" in result:
        return str(result.get("summary") or result)

    if mode == "web":
        lines = [f"Saved fresh research for {result.get('topic')}: {result.get('query')}"]
        answer = str(result.get("answer") or "").strip()
        if answer:
            lines.append(answer)
        saved = result.get("saved_results") or []
        if saved:
            lines.append("Sources saved:")
            for item in saved[:5]:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('title')}: {item.get('url')}")
        return "\n".join(lines)

    return json.dumps(result, indent=2)


def _format_window_result(result: object, *, mode: str = "generic") -> str:
    if not isinstance(result, dict) or not result.get("ok"):
        error = result.get("error") if isinstance(result, dict) else "unknown error"
        return f"I couldn't read that desktop state right now: {error}."
    if mode == "active":
        window = result.get("window") if isinstance(result.get("window"), dict) else {}
        return f"You're on: {window.get('title') or 'unknown window'} ({window.get('process_name') or 'unknown process'})."
    if mode == "list":
        windows = result.get("windows") if isinstance(result.get("windows"), list) else []
        if not windows:
            return "I don't see any visible app windows from this context."
        lines = ["Open windows:"]
        for item in windows[:12]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('title') or 'Untitled'} ({item.get('process_name') or 'unknown'})")
        return "\n".join(lines)
    if mode in {"focus", "minimize", "maximize", "close_safe"}:
        window = result.get("window") if isinstance(result.get("window"), dict) else {}
        title = window.get("title") or result.get("query") or "that window"
        if mode == "focus" and result.get("verified") is False:
            return f"I tried switching to {title}, but Windows did not confirm focus."
        action = {"focus": "focused", "minimize": "minimized", "maximize": "maximized", "close_safe": "closed"}[mode]
        return f"Done, {action} {title}."
    if mode == "observe":
        active = result.get("active_window_title") or "unknown"
        count = len(result.get("open_windows") or []) if isinstance(result.get("open_windows"), list) else 0
        notes = result.get("notes") or []
        suffix = f" Notes: {' '.join(str(item) for item in notes[:2])}" if notes else ""
        return f"Desktop observed. Active window: {active}. Visible windows: {count}.{suffix}"
    if mode == "verify":
        message = str(result.get("message") or "").strip()
        if message:
            return message
        return "Verified." if result.get("verified") else "I couldn't verify that from Windows."
    return json.dumps(result, indent=2)


def _format_browser_result(result: object, *, mode: str = "generic") -> str:
    if not isinstance(result, dict):
        return str(result)
    if not result.get("ok"):
        if result.get("safety_blocked"):
            return str(result.get("summary") or "I refused to read that page automatically because it looks private or sensitive.")
        return str(result.get("summary") or f"Browser action failed safely: {result.get('error') or 'unknown error'}.")
    if mode == "status":
        detected = "yes" if result.get("browser_detected") else "no"
        known = result.get("known_current_url") or "unknown"
        windows = result.get("open_browser_windows") or []
        return f"Browser detected: {detected}. Known page: {known}. Browser windows visible: {len(windows) if isinstance(windows, list) else 0}."
    if mode == "current_page":
        title = result.get("current_title") or result.get("active_window_title") or "unknown page"
        url = result.get("current_url")
        if result.get("verified") is False or result.get("stale"):
            message = str(result.get("message") or "").strip()
            if message:
                return message
            known = result.get("known_current_url") or result.get("url")
            return "I can't verify the current Chrome page right now." + (f" Last known page was {known}." if known else "")
        if url:
            return f"Current browser page: {title}\n{url}"
        return f"I can see the browser title: {title}. I do not have the current tab URL unless you opened it through Eva or send me the URL."
    if mode == "summarize_page":
        title = result.get("current_title") or "Current page"
        summary = result.get("page_summary") or "I could not extract readable page text."
        url = result.get("current_url") or ""
        return f"{title}: {summary}" + (f"\n{url}" if url else "")
    if mode == "extract_links":
        links = result.get("extracted_links") or []
        if not links:
            return "I did not find readable links on that safe public page."
        lines = [f"Found {len(links)} links:"]
        for item in links[:12]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('text') or 'Link'}: {item.get('url')}")
        return "\n".join(lines)
    if mode == "save_page_to_research":
        return str(result.get("message") or f"Saved {result.get('saved_count', 0)} browser page source(s) to research.")
    if mode == "search":
        remember = _format_web_search_result(result)
        return remember if remember != str(result) else f"Opened browser search for {result.get('query')}."
    if mode == "open_url":
        return "Done, opened that in Chrome." if result.get("opened") else "I tried to open that URL, but could not confirm it."
    if mode == "observe":
        return _format_browser_result(result, mode="current_page")
    return json.dumps(result, indent=2)


def _looks_like_personal_profile_query(text: str) -> bool:
    lowered = text.lower()
    return ("ankit l" in lowered or "my profile" in lowered) and "profile" in lowered


def _run_tool(tools: ToolRegistry, name: str, session_context: dict | None = None, **kwargs: object) -> tuple[str, str]:
    try:
        result = tools.run(name, **kwargs)
        if name in {"open_app", "open_folder", "open_url"}:
            target = str(kwargs.get("app") or kwargs.get("app_name") or kwargs.get("folder") or kwargs.get("folder_name") or kwargs.get("url") or "")
            try:
                verification = tools.run("verify_last_action", tool=name, target=target)
            except Exception:
                verification = None
            if isinstance(verification, dict):
                if name == "open_app":
                    return (f"Done, {target} is open." if verification.get("verified") else f"Done, opened {target}, but I couldn't verify the window."), "desktop-tool"
                if name == "open_folder":
                    return (f"Done, {target} is open." if verification.get("verified") else f"Done, opened {target}, but I couldn't verify the folder window."), "desktop-tool"
                if name == "open_url":
                    return ("Done, opened that in Chrome." if verification.get("verified") else "Done, opened the link, but I couldn't verify the browser URL from Windows."), "desktop-tool"
        if name == "web_search":
            remember_web_results(session_context, result)
            return _format_web_search_result(result), "desktop-tool"
        if name == "analyze_screen":
            return _format_screen_result(result), "desktop-tool"
        if name.startswith("window_"):
            return _format_window_result(result, mode=name.removeprefix("window_")), "desktop-tool"
        if name == "desktop_observe":
            return _format_window_result(result, mode="observe"), "desktop-tool"
        if name == "verify_last_action":
            return _format_window_result(result, mode="verify"), "desktop-tool"
        if name.startswith("browser_"):
            mode = name.removeprefix("browser_")
            if name == "browser_search":
                remember_web_results(session_context, result)
                mode = "search"
            return _format_browser_result(result, mode=mode), "browser-tool"
        if name.startswith("chrome_") or name == "browser_open_result_and_verify":
            if isinstance(result, dict):
                message = str(result.get("message") or result.get("summary") or "").strip()
                if message:
                    return message, "browser-tool"
                if name == "chrome_copy_current_url" and not result.get("ok"):
                    return "I can't verify the current Chrome page right now, so I did not copy a stale URL.", "browser-tool"
            return _format_browser_result(result, mode=name), "browser-tool"
        if name.startswith("code_"):
            return _format_code_result(result, mode=name.removeprefix("code_")), "code-tool"
        if name.startswith("workspace_"):
            return _format_workspace_result(result, mode=name.removeprefix("workspace_")), "workspace-tool"
        if name.startswith("research_"):
            return _format_research_result(result, mode=name.removeprefix("research_")), "research-tool"
        return str(result), "desktop-tool"
    except Exception as exc:
        return f"I tried, but Windows reported: {exc}", "desktop-tool"


def _set_llm_mode_reply(mode: str) -> str:
    selected = set_llm_mode(mode)
    labels = {
        "auto": "Auto brain is back on: NVIDIA NIM first, then Gemini and the configured fallbacks.",
        "nvidia_nim": "NVIDIA NIM is now the manual brain. I’ll use NIM first and fall back locally if it blocks.",
        "gemini": "Gemini API is now the manual brain. If all Gemini keys are exhausted, I’ll tell you and fall through safely.",
        "openrouter": "OpenRouter is now the manual cloud brain. I’ll fall back safely if it rejects the request.",
        "groq": "Groq is now the manual cloud brain. I’ll fall back safely if it is missing or rate-limited.",
        "clod": "CLōD is now the manual cloud brain. I’ll fall back safely if quota blocks it.",
        "qwen": "Qwen is now the manual local brain through Ollama.",
        "llama": "Llama is now the manual local brain through Ollama.",
        "local": "Local-only brain is on. I’ll avoid cloud LLMs and use local/safe fallback paths.",
    }
    status = get_llm_status()
    extra = ""
    if selected == "gemini" and status.get("gemini_key_status", {}).get("all_exhausted_or_blocked"):
        extra = " Heads up: all Gemini key slots look locally exhausted or blocked right now."
    return labels[selected] + extra


def _handle_eva_ask_command(
    normalized: str,
    original: str,
    tools: ToolRegistry,
    session_context: dict | None,
    memory: object | None,
    session_id: str | None,
) -> tuple[str, str] | None:
    request = _after_prefix(original, ("eva ask ",))
    if not request:
        return None
    from ..authority.formatter import format_authority_decision
    from ..core.natural_router import NaturalRouteResult, route_natural_request

    route = route_natural_request(request)
    decision = _authority_decision_from_natural_route(route)
    if route.intent == "project_inspect":
        from ..skills.project_inspection import format_project_inspection

        return _format_eva_ask_response(route, decision, format_project_inspection()), "fast-command"
    if route.intent == "project_recent_changes":
        from ..skills.project_inspection import format_recent_project_changes

        return _format_eva_ask_response(route, decision, format_recent_project_changes()), "fast-command"
    if route.intent == "project_next_step":
        from ..skills.project_inspection import format_project_next_step

        return _format_eva_ask_response(route, decision, format_project_next_step()), "fast-command"
    if route.intent == "project_proof":
        from ..skills.reality_check import format_project_proof

        return _format_eva_ask_response(route, decision, format_project_proof()), "fast-command"
    if route.intent == "done_check":
        from ..skills.reality_check import format_done_check

        return _format_eva_ask_response(route, decision, format_done_check()), "fast-command"
    if route.intent == "project_broken_status":
        from ..skills.reality_check import format_broken_status

        return _format_eva_ask_response(route, decision, format_broken_status()), "fast-command"
    if route.intent in {"control_center_status", "locked_features", "enabled_features", "next_safe_step"}:
        if route.intent == "locked_features":
            from ..ai_os.formatter import format_ai_os_locked_features

            return _format_ai_os_ask_response(route, format_ai_os_locked_features()), "fast-command"
        if route.intent == "next_safe_step":
            from ..ai_os.formatter import format_ai_os_next_safe_step

            return _format_ai_os_ask_response(route, format_ai_os_next_safe_step()), "fast-command"
        from ..control_center.status import (
            format_control_center_summary_text,
            format_enabled_features_text,
            format_locked_features_text,
            format_next_safe_step_text,
        )

        body_map = {
            "control_center_status": format_control_center_summary_text,
            "locked_features": format_locked_features_text,
            "enabled_features": format_enabled_features_text,
            "next_safe_step": format_next_safe_step_text,
        }
        return _format_eva_ask_response(route, decision, body_map[route.intent]()), "fast-command"
    if route.intent in {"work_sessions_status", "audit_timeline", "latest_work_session"}:
        from ..work_sessions.status import format_audit_timeline, format_latest_work_session
        from ..work_sessions.formatter import format_work_sessions_status

        body_map = {
            "work_sessions_status": format_work_sessions_status,
            "audit_timeline": format_audit_timeline,
            "latest_work_session": format_latest_work_session,
        }
        return _format_eva_ask_response(route, decision, body_map[route.intent]()), "fast-command"
    if route.intent == "golden_workflow_status":
        from ..golden_workflows.status import format_golden_workflows_text

        return _format_eva_ask_response(route, decision, format_golden_workflows_text()), "fast-command"
    if route.intent in {"golden_workflow_test_plan", "golden_workflow_proof"}:
        from ..golden_workflows.status import format_golden_workflow_proof, format_golden_workflow_test_plan

        body = format_golden_workflow_proof() if route.intent == "golden_workflow_proof" else format_golden_workflow_test_plan()
        return _format_eva_ask_response(route, decision, body), "fast-command"
    if route.intent in {"workflow_continue", "workflow_next_step"}:
        from ..skills.workflow_state import classify_next_fileagent_step, format_workflow_next_step

        body = format_workflow_next_step(classify_next_fileagent_step(request))
        return _format_eva_ask_response(route, decision, body), "fast-command"
    if route.intent in {"phase12_verify_status", "phase12_status"}:
        from ..core.ux_messages import format_phase12_status, format_quick_status_summary

        body = format_quick_status_summary() if route.intent == "phase12_verify_status" else format_phase12_status()
        return _format_eva_ask_response(route, decision, body), "fast-command"
    if route.intent in {"phase12_ready", "phase12_summary", "phase12_limits", "phase12_proof"}:
        from ..core.phase12_ready import format_phase12_limits, format_phase12_proof, format_phase12_ready, format_phase12_summary

        body_map = {
            "phase12_ready": format_phase12_ready,
            "phase12_summary": format_phase12_summary,
            "phase12_limits": format_phase12_limits,
            "phase12_proof": format_phase12_proof,
        }
        return _format_eva_ask_response(route, decision, body_map[route.intent]()), "fast-command"
    if route.intent in {"llm_status", "llm_providers", "llm_routing_policy", "llm_fallback_policy", "llm_limits", "llm_structured_output", "llm_readiness"}:
        from ..llm.formatter import format_llm_fallback_policy, format_llm_limits, format_llm_providers, format_llm_readiness, format_llm_routing_policy, format_llm_status, format_llm_structured_output

        body_map = {"llm_status": format_llm_status, "llm_providers": format_llm_providers, "llm_routing_policy": format_llm_routing_policy, "llm_fallback_policy": format_llm_fallback_policy, "llm_limits": format_llm_limits, "llm_structured_output": format_llm_structured_output, "llm_readiness": format_llm_readiness}
        return _format_eva_ask_response(route, decision, body_map[route.intent]()), "fast-command"
    if route.intent in {"llm_validation_status", "llm_validation_policy", "llm_validation_invalid_examples", "llm_validation_readiness"}:
        from ..llm.formatter import format_llm_validate_invalid_examples, format_llm_validation_policy, format_llm_validation_readiness, format_llm_validation_status

        body_map = {
            "llm_validation_status": format_llm_validation_status,
            "llm_validation_policy": format_llm_validation_policy,
            "llm_validation_invalid_examples": format_llm_validate_invalid_examples,
            "llm_validation_readiness": format_llm_validation_readiness,
        }
        return _format_llm_validation_ask_response(route, body_map[route.intent]()), "fast-command"
    if route.intent in {"llm_red_team_status", "llm_red_team_run", "llm_failure_tests", "llm_safety_failure_report", "llm_red_team_readiness"}:
        from ..llm.formatter import format_llm_failure_tests, format_llm_red_team_readiness, format_llm_red_team_run, format_llm_red_team_status, format_llm_safety_failure_report
        body_map = {"llm_red_team_status": format_llm_red_team_status, "llm_red_team_run": format_llm_red_team_run, "llm_failure_tests": format_llm_failure_tests, "llm_safety_failure_report": format_llm_safety_failure_report, "llm_red_team_readiness": format_llm_red_team_readiness}
        return _format_llm_validation_ask_response(route, body_map[route.intent]()), "fast-command"
    if route.intent in {"context_status", "context_policy", "context_budget", "context_assemble_preview", "context_grounding_report", "context_redaction_policy", "context_readiness"}:
        from ..context_engine.formatter import format_context_assemble_preview, format_context_budget, format_context_grounding_report, format_context_policy, format_context_readiness, format_context_redaction_policy, format_context_status
        body_map = {
            "context_status": format_context_status,
            "context_policy": format_context_policy,
            "context_budget": format_context_budget,
            "context_assemble_preview": format_context_assemble_preview,
            "context_grounding_report": format_context_grounding_report,
            "context_redaction_policy": format_context_redaction_policy,
            "context_readiness": format_context_readiness,
        }
        return _format_context_ask_response(route, body_map[route.intent]()), "fast-command"
    if route.intent in {"threat_status", "threat_policy", "threat_scan_preview", "threat_exfiltration_examples", "threat_context_guard", "threat_readiness"}:
        from ..threat_defense.formatter import format_threat_context_guard, format_threat_exfiltration_examples, format_threat_policy, format_threat_readiness, format_threat_scan_preview, format_threat_status
        body_map = {
            "threat_status": format_threat_status,
            "threat_policy": format_threat_policy,
            "threat_scan_preview": format_threat_scan_preview,
            "threat_exfiltration_examples": format_threat_exfiltration_examples,
            "threat_context_guard": format_threat_context_guard,
            "threat_readiness": format_threat_readiness,
        }
        return _format_threat_ask_response(route, body_map[route.intent]()), "fast-command"
    if route.intent in {"agent_loop_status", "agent_loop_policy", "agent_loop_run_preview", "agent_loop_safety_report", "agent_loop_stop_reasons", "agent_loop_action_previews", "agent_loop_readiness"}:
        from ..agent_loop.formatter import format_agent_loop_action_previews, format_agent_loop_policy, format_agent_loop_readiness, format_agent_loop_run_preview, format_agent_loop_safety_report, format_agent_loop_status, format_agent_loop_stop_reasons
        body_map = {
            "agent_loop_status": format_agent_loop_status,
            "agent_loop_policy": format_agent_loop_policy,
            "agent_loop_run_preview": format_agent_loop_run_preview,
            "agent_loop_safety_report": format_agent_loop_safety_report,
            "agent_loop_stop_reasons": format_agent_loop_stop_reasons,
            "agent_loop_action_previews": format_agent_loop_action_previews,
            "agent_loop_readiness": format_agent_loop_readiness,
        }
        return _format_agent_loop_ask_response(route, body_map[route.intent]()), "fast-command"
    if route.intent in {"workflow_planner_status", "workflow_planner_policy", "workflow_planner_preview", "workflow_planner_dependencies", "workflow_planner_approvals", "workflow_planner_rollback", "workflow_planner_readiness"}:
        from ..workflow_planner.formatter import format_workflow_planner_approvals, format_workflow_planner_dependencies, format_workflow_planner_policy, format_workflow_planner_preview, format_workflow_planner_readiness, format_workflow_planner_rollback, format_workflow_planner_status
        body_map = {
            "workflow_planner_status": format_workflow_planner_status,
            "workflow_planner_policy": format_workflow_planner_policy,
            "workflow_planner_preview": format_workflow_planner_preview,
            "workflow_planner_dependencies": format_workflow_planner_dependencies,
            "workflow_planner_approvals": format_workflow_planner_approvals,
            "workflow_planner_rollback": format_workflow_planner_rollback,
            "workflow_planner_readiness": format_workflow_planner_readiness,
        }
        return _format_workflow_planner_ask_response(route, body_map[route.intent]()), "fast-command"
    if route.intent in {"execution_gates_status", "execution_gates_policy", "execution_gates_blocked_actions", "execution_gates_approvals", "execution_gates_confirmations", "execution_gates_readiness"}:
        from ..execution_gates.formatter import (
            format_execution_gate_approvals,
            format_execution_gate_blocked_actions,
            format_execution_gate_confirmations,
            format_execution_gate_policy,
            format_execution_gate_readiness,
            format_execution_gate_status,
        )

        body_map = {
            "execution_gates_status": format_execution_gate_status,
            "execution_gates_policy": format_execution_gate_policy,
            "execution_gates_blocked_actions": format_execution_gate_blocked_actions,
            "execution_gates_approvals": format_execution_gate_approvals,
            "execution_gates_confirmations": format_execution_gate_confirmations,
            "execution_gates_readiness": format_execution_gate_readiness,
        }
        return _format_execution_gates_ask_response(route, body_map[route.intent]()), "fast-command"
    if route.intent in {"ai_os_status", "ai_os_dashboard", "ai_os_system_map", "ai_os_capability_matrix", "ai_os_locked_features", "ai_os_next_safe_step", "ai_os_safety_boundaries", "ai_os_readiness"}:
        from ..ai_os.formatter import (
            format_ai_os_capability_matrix,
            format_ai_os_dashboard,
            format_ai_os_locked_features,
            format_ai_os_next_safe_step,
            format_ai_os_readiness,
            format_ai_os_safety_boundaries,
            format_ai_os_status,
            format_ai_os_system_map,
        )

        body_map = {
            "ai_os_status": format_ai_os_status,
            "ai_os_dashboard": format_ai_os_dashboard,
            "ai_os_system_map": format_ai_os_system_map,
            "ai_os_capability_matrix": format_ai_os_capability_matrix,
            "ai_os_locked_features": format_ai_os_locked_features,
            "ai_os_next_safe_step": format_ai_os_next_safe_step,
            "ai_os_safety_boundaries": format_ai_os_safety_boundaries,
            "ai_os_readiness": format_ai_os_readiness,
        }
        return _format_ai_os_ask_response(route, body_map[route.intent]()), "fast-command"
    if route.intent in {"voice_status", "voice_policy", "voice_providers", "voice_listen_state", "voice_transcript_safety", "voice_confirmations", "voice_readiness"}:
        from ..voice_assistant.formatter import (
            format_voice_confirmations,
            format_voice_listen_state,
            format_voice_policy,
            format_voice_providers,
            format_voice_readiness,
            format_voice_status,
            format_voice_transcript_safety,
        )

        body_map = {
            "voice_status": format_voice_status,
            "voice_policy": format_voice_policy,
            "voice_providers": format_voice_providers,
            "voice_listen_state": format_voice_listen_state,
            "voice_transcript_safety": format_voice_transcript_safety,
            "voice_confirmations": format_voice_confirmations,
            "voice_readiness": format_voice_readiness,
        }
        return _format_voice_ask_response(route, body_map[route.intent]()), "fast-command"
    if route.intent in {"memory_v3_status", "memory_v3_policy", "memory_v3_privacy", "memory_v3_freshness", "memory_v3_conflicts", "memory_v3_retrieval_preview", "memory_v3_readiness"}:
        from ..memory_v3.formatter import (
            format_memory_v3_conflicts,
            format_memory_v3_freshness,
            format_memory_v3_policy,
            format_memory_v3_privacy,
            format_memory_v3_readiness,
            format_memory_v3_retrieval_preview,
            format_memory_v3_status,
        )

        body_map = {
            "memory_v3_status": format_memory_v3_status,
            "memory_v3_policy": format_memory_v3_policy,
            "memory_v3_privacy": format_memory_v3_privacy,
            "memory_v3_freshness": format_memory_v3_freshness,
            "memory_v3_conflicts": format_memory_v3_conflicts,
            "memory_v3_retrieval_preview": format_memory_v3_retrieval_preview,
            "memory_v3_readiness": format_memory_v3_readiness,
        }
        return _format_memory_v3_ask_response(route, body_map[route.intent]()), "fast-command"
    if route.intent in {
        "browser_read_status",
        "browser_read_policy",
        "browser_read_boundaries",
        "browser_read_observe",
        "browser_read_session_boundary",
        "browser_read_blocked_urls",
        "browser_read_readiness",
    }:
        from ..browser_readonly.formatter import (
            format_browser_read_blocked_urls,
            format_browser_read_observe,
            format_browser_read_policy,
            format_browser_read_readiness,
            format_browser_read_status,
        )

        body_map = {
            "browser_read_status": format_browser_read_status,
            "browser_read_policy": format_browser_read_policy,
            "browser_read_boundaries": format_browser_read_policy,
            "browser_read_observe": format_browser_read_observe,
            "browser_read_session_boundary": format_browser_read_policy,
            "browser_read_blocked_urls": format_browser_read_blocked_urls,
            "browser_read_readiness": format_browser_read_readiness,
        }
        return _format_browser_read_ask_response(route, body_map[route.intent]()), "fast-command"
    if route.intent in {
        "news_status", "news_policy", "news_dashboard", "news_sources", "news_freshness", "news_readiness",
    }:
        from ..news_dashboard.formatter import format_news_dashboard, format_news_freshness, format_news_policy, format_news_readiness, format_news_sources, format_news_status
        body = {"news_status":format_news_status,"news_policy":format_news_policy,"news_dashboard":format_news_dashboard,"news_sources":format_news_sources,"news_freshness":format_news_freshness,"news_readiness":format_news_readiness}[route.intent]()
        return "Eva ask\n\n" + body, "fast-command"
    if route.intent in {
        "coding_status",
        "coding_policy",
        "coding_patch_plan",
        "coding_review_checklist",
        "coding_test_plan",
        "coding_risk_review",
        "coding_handoff",
        "coding_readiness",
    }:
        from ..coding_agent.formatter import (
            format_coding_handoff,
            format_coding_patch_plan,
            format_coding_policy,
            format_coding_readiness,
            format_coding_review_checklist,
            format_coding_risk_review,
            format_coding_status,
            format_coding_test_plan,
        )

        body_map = {
            "coding_status": format_coding_status,
            "coding_policy": format_coding_policy,
            "coding_patch_plan": format_coding_patch_plan,
            "coding_review_checklist": format_coding_review_checklist,
            "coding_test_plan": format_coding_test_plan,
            "coding_risk_review": format_coding_risk_review,
            "coding_handoff": format_coding_handoff,
            "coding_readiness": format_coding_readiness,
        }
        return "Eva ask\n\n" + body_map[route.intent](), "fast-command"
    if route.intent in {
        "rc_status",
        "rc_manifest",
        "rc_commit_plan",
        "rc_hardening_report",
        "rc_checklist",
        "rc_readiness",
        "rc_verification",
    }:
        from ..release_candidate.formatter import (
            format_rc_checklist,
            format_rc_commit_plan,
            format_rc_hardening_report,
            format_rc_manifest,
            format_rc_readiness,
            format_rc_status,
            format_rc_verification,
        )

        body_map = {
            "rc_status": format_rc_status,
            "rc_manifest": format_rc_manifest,
            "rc_commit_plan": format_rc_commit_plan,
            "rc_hardening_report": format_rc_hardening_report,
            "rc_checklist": format_rc_checklist,
            "rc_readiness": format_rc_readiness,
            "rc_verification": format_rc_verification,
        }
        return "Eva ask\n\n" + body_map[route.intent](), "fast-command"
    if route.intent in {
        "release_status",
        "release_demo",
        "release_commands",
        "release_capability_map",
        "release_safety_proof",
        "release_readiness",
        "release_limitations",
        "release_demo_smoke",
        "release_post_push_sync",
    }:
        from ..release_demo.formatter import (
            format_release_capability_map,
            format_release_commands,
            format_release_demo,
            format_release_demo_smoke,
            format_release_limitations,
            format_release_post_push_sync,
            format_release_readiness,
            format_release_safety_proof,
            format_release_status,
        )

        body_map = {
            "release_status": format_release_status,
            "release_demo": format_release_demo,
            "release_commands": format_release_commands,
            "release_capability_map": format_release_capability_map,
            "release_safety_proof": format_release_safety_proof,
            "release_readiness": format_release_readiness,
            "release_limitations": format_release_limitations,
            "release_demo_smoke": format_release_demo_smoke,
            "release_post_push_sync": format_release_post_push_sync,
        }
        return "Eva ask\n\n" + body_map[route.intent](), "fast-command"
    if route.intent in {
        "desktop_control_status",
        "desktop_control_policy",
        "desktop_control_dry_run",
        "desktop_control_approvals",
        "desktop_control_blocked_actions",
        "desktop_control_readiness",
    }:
        from ..desktop_control_gate.formatter import (
            format_desktop_control_approvals,
            format_desktop_control_blocked_actions,
            format_desktop_control_dry_run,
            format_desktop_control_policy,
            format_desktop_control_readiness,
            format_desktop_control_status,
        )

        body_map = {
            "desktop_control_status": format_desktop_control_status,
            "desktop_control_policy": format_desktop_control_policy,
            "desktop_control_dry_run": format_desktop_control_dry_run,
            "desktop_control_approvals": format_desktop_control_approvals,
            "desktop_control_blocked_actions": format_desktop_control_blocked_actions,
            "desktop_control_readiness": format_desktop_control_readiness,
        }
        return "Eva ask\n\n" + body_map[route.intent](), "fast-command"
    if route.intent in {
        "desktop_observe_status",
        "desktop_observe_policy",
        "desktop_observe_boundaries",
        "desktop_observe_sensitive_screens",
        "desktop_observe_mock",
        "desktop_observe_readiness",
    }:
        from ..desktop_observation.formatter import (
            format_desktop_observe_mock,
            format_desktop_observe_policy,
            format_desktop_observe_readiness,
            format_desktop_observe_sensitive_screens,
            format_desktop_observe_status,
        )

        body_map = {
            "desktop_observe_status": format_desktop_observe_status,
            "desktop_observe_policy": format_desktop_observe_policy,
            "desktop_observe_boundaries": format_desktop_observe_policy,
            "desktop_observe_sensitive_screens": format_desktop_observe_sensitive_screens,
            "desktop_observe_mock": format_desktop_observe_mock,
            "desktop_observe_readiness": format_desktop_observe_readiness,
        }
        return _format_desktop_observe_ask_response(route, body_map[route.intent]()), "fast-command"
    if route.intent in {"desktop_status", "desktop_policy", "desktop_blocked_actions", "desktop_action_safety", "desktop_app_risk", "desktop_readiness", "desktop_session_status", "desktop_session_preview", "desktop_session_plan", "desktop_window_status_preview", "desktop_active_context_preview", "desktop_observation_readiness", "desktop_screen_policy", "desktop_screen_observation_policy", "desktop_sensitive_screens", "desktop_screen_redaction_policy", "desktop_screen_capture_gate", "desktop_screen_readiness", "desktop_action_dry_run", "desktop_action_plan_preview", "desktop_action_risk", "desktop_action_approvals", "desktop_dry_run_policy", "desktop_action_readiness", "desktop_risk_score", "desktop_risk_factors", "desktop_approval_required", "desktop_safety_matrix", "desktop_high_risk_actions", "desktop_risk_readiness", "desktop_approval_policy", "desktop_approval_levels", "desktop_approval_preview", "desktop_confirmation_phrase", "desktop_forbidden_actions", "desktop_approval_audit_status", "desktop_approval_readiness", "desktop_phase14_status", "desktop_phase14_summary", "desktop_phase14_limits", "desktop_phase14_ready", "desktop_phase14_final_proof", "desktop_readiness_proof", "desktop_locked_status", "desktop_readiness_gaps"}:
        from ..desktop_agent.formatter import (
            format_desktop_active_context_preview,
            format_desktop_approval_audit_status,
            format_desktop_approval_levels,
            format_desktop_approval_model_preview,
            format_desktop_approval_model_readiness,
            format_desktop_approval_policy,
            format_desktop_approval_required,
            format_desktop_action_approvals,
            format_desktop_action_dry_run,
            format_desktop_action_plan,
            format_desktop_action_readiness,
            format_desktop_action_risk,
            format_desktop_action_safety,
            format_desktop_app_risk,
            format_desktop_blocked_actions,
            format_desktop_dry_run_policy,
            format_desktop_observation_readiness,
            format_desktop_policy,
            format_desktop_readiness,
            format_desktop_screen_capture_gate,
            format_desktop_screen_observation_policy,
            format_desktop_screen_policy,
            format_desktop_screen_readiness,
            format_desktop_screen_redaction_policy,
            format_desktop_session_plan,
            format_desktop_session_preview,
            format_desktop_session_status,
            format_desktop_sensitive_screens,
            format_desktop_status,
            format_desktop_window_status_preview,
            format_desktop_high_risk_actions,
            format_desktop_risk_factors,
            format_desktop_risk_readiness,
            format_desktop_risk_score,
            format_desktop_safety_matrix,
            format_desktop_confirmation_phrase,
            format_desktop_forbidden_actions,
            format_desktop_locked_status,
            format_desktop_phase14_final_proof,
            format_desktop_phase14_limits,
            format_desktop_phase14_ready,
            format_desktop_phase14_status,
            format_desktop_phase14_summary,
            format_desktop_readiness_gaps,
            format_desktop_readiness_proof,
        )

        if route.intent == "desktop_phase14_status":
            body = format_desktop_phase14_status()
        elif route.intent == "desktop_phase14_summary":
            body = format_desktop_phase14_summary()
        elif route.intent == "desktop_phase14_limits":
            body = format_desktop_phase14_limits()
        elif route.intent == "desktop_phase14_ready":
            body = format_desktop_phase14_ready()
        elif route.intent == "desktop_phase14_final_proof":
            body = format_desktop_phase14_final_proof()
        elif route.intent == "desktop_readiness_proof":
            body = format_desktop_readiness_proof()
        elif route.intent == "desktop_locked_status":
            body = format_desktop_locked_status()
        elif route.intent == "desktop_readiness_gaps":
            body = format_desktop_readiness_gaps()
        elif route.intent == "desktop_policy":
            body = format_desktop_policy()
        elif route.intent == "desktop_blocked_actions":
            body = format_desktop_blocked_actions()
        elif route.intent == "desktop_action_safety":
            body = format_desktop_action_safety(str(route.suggested_command or "").removeprefix("eva desktop action safety ").strip() or "unknown")
        elif route.intent == "desktop_action_dry_run":
            body = format_desktop_action_dry_run(request)
        elif route.intent == "desktop_action_plan_preview":
            body = format_desktop_action_plan(request)
        elif route.intent == "desktop_action_risk":
            body = format_desktop_action_risk(str(route.suggested_command or "").removeprefix("eva desktop action risk ").strip() or "unknown")
        elif route.intent == "desktop_action_approvals":
            body = format_desktop_action_approvals()
        elif route.intent == "desktop_dry_run_policy":
            body = format_desktop_dry_run_policy()
        elif route.intent == "desktop_action_readiness":
            body = format_desktop_action_readiness()
        elif route.intent == "desktop_risk_score":
            body = format_desktop_risk_score(request)
        elif route.intent == "desktop_risk_factors":
            body = format_desktop_risk_factors(request)
        elif route.intent == "desktop_approval_required":
            body = format_desktop_approval_required(request)
        elif route.intent == "desktop_approval_policy":
            body = format_desktop_approval_policy()
        elif route.intent == "desktop_approval_levels":
            body = format_desktop_approval_levels()
        elif route.intent == "desktop_approval_preview":
            body = format_desktop_approval_model_preview(request)
        elif route.intent == "desktop_confirmation_phrase":
            body = format_desktop_confirmation_phrase(request)
        elif route.intent == "desktop_forbidden_actions":
            body = format_desktop_forbidden_actions()
        elif route.intent == "desktop_approval_audit_status":
            body = format_desktop_approval_audit_status()
        elif route.intent == "desktop_approval_readiness":
            body = format_desktop_approval_model_readiness()
        elif route.intent == "desktop_safety_matrix":
            body = format_desktop_safety_matrix()
        elif route.intent == "desktop_high_risk_actions":
            body = format_desktop_high_risk_actions()
        elif route.intent == "desktop_risk_readiness":
            body = format_desktop_risk_readiness()
        elif route.intent == "desktop_app_risk":
            body = format_desktop_app_risk(str(route.suggested_command or "").removeprefix("eva desktop app risk ").strip() or "unknown")
        elif route.intent == "desktop_readiness":
            body = format_desktop_readiness()
        elif route.intent == "desktop_session_status":
            body = format_desktop_session_status()
        elif route.intent == "desktop_session_preview":
            body = format_desktop_session_preview("Natural desktop session request")
        elif route.intent == "desktop_session_plan":
            body = format_desktop_session_plan()
        elif route.intent == "desktop_window_status_preview":
            body = format_desktop_window_status_preview()
        elif route.intent == "desktop_active_context_preview":
            body = format_desktop_active_context_preview()
        elif route.intent == "desktop_observation_readiness":
            body = format_desktop_observation_readiness()
        elif route.intent == "desktop_screen_policy":
            body = format_desktop_screen_policy()
        elif route.intent == "desktop_screen_observation_policy":
            body = format_desktop_screen_observation_policy()
        elif route.intent == "desktop_sensitive_screens":
            body = format_desktop_sensitive_screens()
        elif route.intent == "desktop_screen_redaction_policy":
            body = format_desktop_screen_redaction_policy()
        elif route.intent == "desktop_screen_capture_gate":
            body = format_desktop_screen_capture_gate()
        elif route.intent == "desktop_screen_readiness":
            body = format_desktop_screen_readiness()
        else:
            body = format_desktop_status()
        return _format_eva_ask_response(route, decision, body), "fast-command"
    if route.intent in {"browser_status", "browser_policy", "browser_action_safety", "browser_session_status", "browser_session_preview", "browser_session_plan", "browser_session_readiness", "browser_page_summary_policy", "browser_page_summary_preview", "browser_dom_summary_policy", "browser_observation_readiness", "browser_action_dry_run", "browser_action_plan_preview", "browser_action_risk", "browser_action_approvals", "browser_dry_run_policy", "browser_domain_check", "browser_site_risk", "browser_sensitive_sites", "browser_domain_rules", "browser_domain_approvals", "browser_readonly_readiness", "browser_readiness_proof", "browser_safety_proof", "browser_readiness_gaps", "browser_locked_status", "browser_phase13_proof", "browser_phase13_status", "browser_phase13_summary", "browser_phase13_limits", "browser_phase13_ready", "browser_phase13_final_proof"}:
        from ..browser_agent.formatter import (
            format_browser_action_safety,
            format_browser_action_approvals,
            format_browser_action_dry_run,
            format_browser_action_plan,
            format_browser_action_risk,
            format_browser_locked_status,
            format_browser_domain_approvals,
            format_browser_domain_check,
            format_browser_domain_rules,
            format_browser_dom_summary_policy,
            format_browser_dry_run_policy,
            format_browser_observation_readiness,
            format_browser_page_summary_policy,
            format_browser_page_summary_preview,
            format_browser_phase13_final_proof,
            format_browser_phase13_limits,
            format_browser_phase13_proof,
            format_browser_phase13_ready,
            format_browser_phase13_status,
            format_browser_phase13_summary,
            format_browser_policy,
            format_browser_readiness,
            format_browser_readiness_gaps,
            format_browser_readiness_proof,
            format_browser_read_only_readiness,
            format_browser_safety_proof,
            format_browser_session_plan,
            format_browser_session_preview,
            format_browser_session_status,
            format_browser_sensitive_sites,
            format_browser_site_risk,
            format_browser_status,
        )

        if route.intent == "browser_policy":
            body = format_browser_policy()
        elif route.intent == "browser_action_safety":
            action = str(route.suggested_command or "").removeprefix("eva browser action safety ").strip() or request
            body = format_browser_action_safety(action)
        elif route.intent == "browser_session_status":
            body = format_browser_session_status()
        elif route.intent == "browser_session_preview":
            body = format_browser_session_preview("Natural browser session request")
        elif route.intent == "browser_session_plan":
            body = format_browser_session_plan()
        elif route.intent == "browser_session_readiness":
            body = format_browser_readiness()
        elif route.intent == "browser_page_summary_policy":
            body = format_browser_page_summary_policy()
        elif route.intent == "browser_page_summary_preview":
            body = format_browser_page_summary_preview()
        elif route.intent == "browser_dom_summary_policy":
            body = format_browser_dom_summary_policy()
        elif route.intent == "browser_observation_readiness":
            body = format_browser_observation_readiness()
        elif route.intent == "browser_action_dry_run":
            body = format_browser_action_dry_run(request)
        elif route.intent == "browser_action_plan_preview":
            body = format_browser_action_plan(request)
        elif route.intent == "browser_action_risk":
            action = str(route.suggested_command or "").removeprefix("eva browser action risk ").strip() or request
            body = format_browser_action_risk(action)
        elif route.intent == "browser_action_approvals":
            body = format_browser_action_approvals()
        elif route.intent == "browser_dry_run_policy":
            body = format_browser_dry_run_policy()
        elif route.intent == "browser_domain_check":
            domain = str(route.suggested_command or "").removeprefix("eva browser domain check ").strip() or request
            body = format_browser_domain_check(domain)
        elif route.intent == "browser_site_risk":
            domain = str(route.suggested_command or "").removeprefix("eva browser site risk ").strip() or request
            body = format_browser_site_risk(domain)
        elif route.intent == "browser_sensitive_sites":
            body = format_browser_sensitive_sites()
        elif route.intent == "browser_domain_rules":
            body = format_browser_domain_rules()
        elif route.intent == "browser_domain_approvals":
            body = format_browser_domain_approvals()
        elif route.intent == "browser_readonly_readiness":
            body = format_browser_read_only_readiness()
        elif route.intent == "browser_readiness_proof":
            body = format_browser_readiness_proof()
        elif route.intent == "browser_safety_proof":
            body = format_browser_safety_proof()
        elif route.intent == "browser_readiness_gaps":
            body = format_browser_readiness_gaps()
        elif route.intent == "browser_locked_status":
            body = format_browser_locked_status()
        elif route.intent == "browser_phase13_proof":
            body = format_browser_phase13_proof()
        elif route.intent == "browser_phase13_status":
            body = format_browser_phase13_status()
        elif route.intent == "browser_phase13_summary":
            body = format_browser_phase13_summary()
        elif route.intent == "browser_phase13_limits":
            body = format_browser_phase13_limits()
        elif route.intent == "browser_phase13_ready":
            body = format_browser_phase13_ready()
        elif route.intent == "browser_phase13_final_proof":
            body = format_browser_phase13_final_proof()
        else:
            body = format_browser_status()
        return _format_eva_ask_response(route, decision, body), "fast-command"
    if route.intent == "verification_before_completion":
        from ..core.ux_messages import format_phase12_status
        from ..skills.workflow_state import format_workflow_state_summary, summarize_fileagent_workflow_state

        body = "\n\n".join(
            [
                "Evidence check",
                "I can summarize the current local verification and workflow evidence, but I should not claim completion without fresh verifier output.",
                format_phase12_status(),
                format_workflow_state_summary(summarize_fileagent_workflow_state()),
                "Remaining limitations: broad file edits, source edits, browser/desktop control, shell execution, MCP, cloud calls, and normal-chat v2 routing remain locked.",
            ]
        )
        return _format_eva_ask_response(route, decision, body), "fast-command"
    if route.intent == "golden_project_note_create":
        if _should_show_skill_workflow_plan(request):
            from ..skills.workflows import format_fileagent_project_note_workflow

            body = format_fileagent_project_note_workflow(request)
            return _format_eva_ask_response(route, decision, body), "fast-command"
        from ..golden_workflows.formatter import format_golden_workflow_result
        from ..golden_workflows.runner import start_safe_project_note_workflow

        body = format_golden_workflow_result(start_safe_project_note_workflow(request))
        return _format_eva_ask_response(route, decision, body), "fast-command"
    if route.intent == "golden_workflow_continue":
        from ..golden_workflows.formatter import format_golden_workflow_result
        from ..golden_workflows.runner import continue_safe_project_note_workflow

        body = format_golden_workflow_result(continue_safe_project_note_workflow(request))
        return _format_eva_ask_response(route, decision, body), "fast-command"
    if route.intent == "capability_status" and route.suggested_command == "eva capabilities safe":
        from ..capabilities.registry import format_capability_summary
        from ..authority.status import format_authority_status

        body = "\n\n".join(
            [
                "Eva safe actions right now",
                format_authority_status(),
                format_capability_summary(safe_only=True),
            ]
        )
        return _format_eva_ask_response(route, decision, body), "fast-command"
    if route.intent in {"approval_sandbox_apply", "approval_sandbox_verify", "approval_sandbox_rollback"} and not route.suggested_command:
        resolved = _resolve_single_approved_file_approval(route.intent)
        if not resolved:
            body = (
                "I found no single approved sandbox-eligible FileAgent approval to use.\n"
                "Run `eva file approvals pending` or specify an approval id like `fap_...`."
            )
            return _format_eva_ask_response(route, decision, body), "fast-command"
        route = NaturalRouteResult(**{**route.as_dict(), "suggested_command": resolved, "routed_to": resolved})
    if route.intent == "real_create_request" and not route.suggested_command:
        body = _format_real_create_next_step()
        return _format_eva_ask_response(route, decision, body), "fast-command"
    if route.intent == "real_create_request":
        from ..skills.workflow_state import classify_next_fileagent_step, format_workflow_next_step

        body = format_workflow_next_step(classify_next_fileagent_step(request))
        return _format_eva_ask_response(route, decision, body), "fast-command"
    if route.intent == "real_apply_policy":
        from ..file_agent.real_apply import format_real_apply_policy

        return _format_eva_ask_response(route, decision, format_real_apply_policy()), "fast-command"
    if route.intent == "real_create_verify_latest":
        from ..skills.workflow_state import classify_next_fileagent_step, format_workflow_next_step

        body = format_workflow_next_step(classify_next_fileagent_step("verify latest real create"))
        return _format_eva_ask_response(route, decision, body), "fast-command"
    if route.intent == "real_create_rollback_latest":
        from ..skills.workflow_state import classify_next_fileagent_step, format_workflow_next_step

        body = format_workflow_next_step(classify_next_fileagent_step("rollback latest real create"))
        return _format_eva_ask_response(route, decision, body), "fast-command"
    if route.intent == "real_create_rollback_request" and not route.suggested_command:
        body = "Specify the approval id and exact phrase: `eva ask confirm rollback real create <approval_id>`."
        return _format_eva_ask_response(route, decision, body), "fast-command"
    if route.refusal_reason:
        return _format_eva_ask_response(route, decision, route.refusal_reason), "fast-command"
    if route.suggested_command:
        delegated = maybe_handle_fast_command(route.suggested_command, tools, session_context=session_context, memory=memory, session_id=session_id)
        body = delegated[0] if delegated else f"Suggested safe command: `{route.suggested_command}`"
        return _format_eva_ask_response(route, decision, body), "fast-command"
    body = "I understood the request, but I need a more specific safe command before doing anything."
    return _format_eva_ask_response(route, decision, body), "fast-command"


def _authority_decision_from_natural_route(route: object) -> object:
    from ..authority.decision import (
        allow_approval_decision,
        allow_draft_decision,
        allow_preview_decision,
        allow_readonly_decision,
        allow_sandbox_decision,
        block_real_execution_decision,
        refuse_authority_decision,
    )

    category = str(getattr(route, "authority_category", "unknown"))
    intent = str(getattr(route, "intent", "unknown"))
    suggested = getattr(route, "suggested_command", None)
    capability = _capability_for_natural_intent(intent)
    reason = f"Natural router interpreted this as `{intent}`."
    if getattr(route, "refusal_reason", None):
        if category in {"destructive", "external_send", "terminal", "browser_action", "desktop_control", "system_change", "local_write"}:
            return refuse_authority_decision(action_type=intent, action_category=category, capability_id=capability, reason=reason, blocked_reason=str(getattr(route, "refusal_reason")))
        return block_real_execution_decision(action_type=intent, action_category=category, capability_id=capability, reason=reason, blocked_reason=str(getattr(route, "refusal_reason")))
    if category == "read":
        return allow_readonly_decision(action_type=intent, action_category="read", capability_id=capability, agent_name=_agent_for_capability(capability), reason=reason)
    if category == "draft":
        return allow_draft_decision(action_type=intent, action_category="draft", capability_id=capability, agent_name="FileAgent", reason=reason)
    if category == "golden_workflow":
        return allow_sandbox_decision(action_type=intent, action_category="golden_workflow", capability_id=capability, agent_name="FileAgent", reason=reason, requires_approval=True, public_mode_allowed=False)
    if category == "approve":
        return allow_approval_decision(action_type=intent, action_category="approve", capability_id=capability, agent_name="FileAgent", reason=reason, public_mode_allowed=False)
    if category in {"sandbox_apply", "verify", "rollback"}:
        return allow_sandbox_decision(action_type=intent, action_category=category, capability_id=capability, agent_name="FileAgent", reason=reason, requires_approval=True, public_mode_allowed=False)
    if category == "real_create_safe_text":
        return block_real_execution_decision(action_type=intent, action_category="local_write", capability_id=capability, agent_name="FileAgent", reason=reason, blocked_reason="Exact approval confirmation is required before narrow real create-new-text-file.", public_mode_allowed=False, risk_level="high")
    if category == "rollback_real_create":
        return block_real_execution_decision(action_type=intent, action_category="local_write", capability_id=capability, agent_name="FileAgent", reason=reason, blocked_reason="Exact rollback confirmation is required before removing an Eva-created file.", public_mode_allowed=False, risk_level="medium")
    if suggested:
        return allow_preview_decision(action_type=intent, action_category="plan", capability_id=capability, reason=reason)
    return refuse_authority_decision(action_type=intent, action_category="unknown", capability_id=capability, reason=reason, blocked_reason="No safe route was selected.")


def _capability_for_natural_intent(intent: str) -> str | None:
    mapping = {
        "project_inspect": "eva.project_inspect",
        "project_recent_changes": "eva.project_recent_changes",
        "project_next_step": "eva.project_next_step",
        "project_proof": "eva.project_proof",
        "done_check": "eva.done_check",
        "project_broken_status": "eva.project_reality_check",
        "control_center_status": "eva.control_center_status",
        "work_sessions_status": "eva.work_sessions_status",
        "audit_timeline": "eva.audit_timeline",
        "latest_work_session": "eva.latest_work_session",
        "locked_features": "eva.locked_features",
        "enabled_features": "eva.enabled_features",
        "next_safe_step": "eva.next_safe_step",
        "file_inspect": "file.preview_text",
        "file_understand": "file.understand_text",
        "file_draft": "file.draft_readme_section",
        "file_apply_readiness": "file.apply_readiness",
        "approval_status": "file.approval_status",
        "approval_pending": "file.approval_list_pending",
        "approval_request": "file.approval_request_create",
        "approval_sandbox_apply": "file.sandbox_apply_approved",
        "approval_sandbox_verify": "file.sandbox_verify_apply",
        "approval_sandbox_rollback": "file.sandbox_rollback_apply",
        "capability_status": "eva.ask",
        "agent_status": "eva.ask",
        "planner_status": "eva.ask",
        "research_memory_status": "research_memory.status",
        "safety_status": "eva.authority_status",
        "control_center_dashboard": "eva.control_center_status",
        "golden_workflow_status": "eva.golden_workflows_status",
        "golden_workflow_test_plan": "eva.golden_workflow_test_plan",
        "golden_workflow_proof": "eva.golden_workflow_proof",
        "golden_project_note_create": "eva.golden_workflow_project_note",
        "golden_workflow_continue": "eva.golden_workflow_continue",
        "workflow_continue": "eva.workflow_next_step",
        "workflow_next_step": "eva.workflow_next_step",
        "phase12_verify_status": "eva.smoke_status",
        "phase12_status": "eva.phase12_status",
        "phase12_ready": "eva.phase12_ready",
        "phase12_summary": "eva.phase12_summary",
        "phase12_limits": "eva.phase12_limits",
        "phase12_proof": "eva.phase12_proof",
        "browser_read_status": "browser_read.status",
        "browser_read_policy": "browser_read.policy",
        "browser_read_boundaries": "browser_read.policy",
        "browser_read_observe": "browser_read.observe",
        "browser_read_session_boundary": "browser_read.policy",
        "browser_read_blocked_urls": "browser_read.blocked_urls",
        "browser_read_readiness": "browser_read.readiness",
        "desktop_observe_status": "desktop_observe.status",
        "desktop_observe_policy": "desktop_observe.policy",
        "desktop_observe_boundaries": "desktop_observe.policy",
        "desktop_observe_sensitive_screens": "desktop_observe.sensitive_screens",
        "desktop_observe_mock": "desktop_observe.mock",
        "desktop_observe_readiness": "desktop_observe.readiness",
        "desktop_control_status": "desktop_control.status",
        "desktop_control_policy": "desktop_control.policy",
        "desktop_control_dry_run": "desktop_control.dry_run",
        "desktop_control_approvals": "desktop_control.approvals",
        "desktop_control_blocked_actions": "desktop_control.blocked_actions",
        "desktop_control_readiness": "desktop_control.readiness",
        "news_status": "news.status", "news_policy": "news.policy", "news_dashboard": "news.dashboard",
        "news_sources": "news.sources", "news_freshness": "news.freshness", "news_readiness": "news.readiness",
        "coding_status": "coding.status",
        "coding_policy": "coding.policy",
        "coding_patch_plan": "coding.patch_plan",
        "coding_review_checklist": "coding.review_checklist",
        "coding_test_plan": "coding.test_plan",
        "coding_risk_review": "coding.risk_review",
        "coding_handoff": "coding.handoff",
        "coding_readiness": "coding.readiness",
        "rc_status": "rc.status",
        "rc_manifest": "rc.manifest",
        "rc_commit_plan": "rc.commit_plan",
        "rc_hardening_report": "rc.hardening_report",
        "rc_checklist": "rc.checklist",
        "rc_readiness": "rc.readiness",
        "rc_verification": "rc.verification",
        "release_status": "release.status",
        "release_demo": "release.demo",
        "release_commands": "release.commands",
        "release_capability_map": "release.capability_map",
        "release_safety_proof": "release.safety_proof",
        "release_readiness": "release.readiness",
        "release_limitations": "release.limitations",
        "release_demo_smoke": "release.demo_smoke",
        "release_post_push_sync": "release.post_push_sync",
        "verification_before_completion": "eva.workflow_plan",
        "real_apply_policy": "file.real_apply_policy",
        "real_create_request": "file.real_create_new_text_file",
        "real_create_confirm": "file.real_create_new_text_file",
        "real_create_verify": "file.real_verify_new_text_file",
        "real_create_verify_latest": "eva.file_latest_status",
        "real_create_rollback_request": "file.real_rollback_new_text_file",
        "real_create_rollback_latest": "eva.file_latest_status",
        "real_create_rollback_confirm": "file.real_rollback_new_text_file",
    }
    return mapping.get(intent)


def _agent_for_capability(capability_id: str | None) -> str | None:
    if not capability_id:
        return None
    if capability_id.startswith("file."):
        return "FileAgent"
    if capability_id.startswith("research_memory."):
        return "ResearchAgent"
    return "PlannerAgent"


def _format_eva_ask_response(route: object, decision: object, body: str) -> str:
    from ..authority.formatter import format_authority_decision
    from ..core.ux_messages import format_safe_next_step, format_understood_request
    from ..skills.selector import select_skills_for_request, select_workflow_for_request
    from ..specialists.selector import select_specialists_for_request

    intent = str(getattr(route, "intent", "unknown"))
    mode = str(getattr(decision, "mode", "preview"))
    allowed = bool(getattr(decision, "allowed", False))
    sandbox_only = bool(getattr(decision, "sandbox_only", False))
    request_text = str(getattr(route, "original_text", ""))
    specialists = select_specialists_for_request(request_text)
    skills = select_skills_for_request(request_text)
    workflow = select_workflow_for_request(request_text)
    if not allowed:
        next_step = "Use a safe read-only status, preview, or exact confirmation command. Nothing was executed."
    elif sandbox_only:
        next_step = "Review the sandbox or approval output before any exact confirmation step."
    elif mode in {"read_only", "preview_only", "draft_only", "approval_only"}:
        next_step = "Review the result below. No real file, browser, desktop, shell, or external action was executed."
    else:
        next_step = "Review the result below before taking any manual action."
    work_session_id = ""
    try:
        from ..work_sessions.timeline import finalize_work_session, record_eva_ask_work_session

        work_session_id = record_eva_ask_work_session(
            request_text=request_text,
            route=route,
            decision=decision,
            specialists=specialists,
            skills=skills,
            workflow=workflow,
            next_safe_step=next_step,
        )
        finalize_work_session(work_session_id, body)
    except Exception:
        work_session_id = "unavailable"
    return "\n".join(
        [
            "Eva ask",
            "",
            format_understood_request(intent, f"Intent `{intent}` routed to `{getattr(route, 'routed_to', 'authority_preview')}`."),
            "",
            f"Work session: {work_session_id}",
            f"Request: {getattr(route, 'original_text', '')}",
            f"Interpreted intent: {getattr(route, 'intent', 'unknown')}",
            f"Confidence: {float(getattr(route, 'confidence', 0.0)):.2f}",
            "",
            format_authority_decision(decision),
            "",
            "Specialist route:",
            ", ".join(item.id for item in specialists[:4]) if specialists else "none",
            "Skill route:",
            ", ".join(item.id for item in skills[:4]) if skills else "none",
            "Workflow route:",
            workflow.id if workflow else "none",
            "",
            format_safe_next_step(next_step),
            "",
            "Result:",
            body,
        ]
    )


def _format_llm_validation_ask_response(route: object, body: str) -> str:
    """Render local validation status without creating a work-session record."""
    return "\n".join(
        [
            "Eva ask",
            "",
            "Request: structured-output validation status.",
            f"Interpreted intent: {getattr(route, 'intent', 'unknown')}",
            "Mode: read-only local validation status.",
            "No work session was recorded and no action was executed.",
            "",
            "Result:",
            body,
        ]
    )


def _format_context_ask_response(route: object, body: str) -> str:
    """Render local context assembly status without creating a work-session record."""
    return "\n".join(
        [
            "Eva ask",
            "",
            "Request: context assembly status/policy/preview.",
            f"Interpreted intent: {getattr(route, 'intent', 'unknown')}",
            "Mode: read-only local/mock context preview.",
            "No work session was recorded and no action was executed.",
            "No live LLM call was made.",
            "Assembled context cannot execute tools.",
            "",
            "Result:",
            body,
        ]
    )


def _format_threat_ask_response(route: object, body: str) -> str:
    """Render local threat-defense status without creating a work-session record."""
    return "\n".join(
        [
            "Eva ask",
            "",
            "Request: LLM threat defense status/policy/preview.",
            f"Interpreted intent: {getattr(route, 'intent', 'unknown')}",
            "Mode: read-only local/mock threat-defense preview.",
            "No work session was recorded and no action was executed.",
            "No live LLM call was made.",
            "Untrusted context cannot override trusted policy/instruction hierarchy.",
            "Secrets/config/session data are blocked.",
            "Defended context cannot execute tools.",
            "",
            "Result:",
            body,
        ]
    )


def _format_agent_loop_ask_response(route: object, body: str) -> str:
    """Render local agent-loop status without creating a work-session record."""
    return "\n".join(
        [
            "Eva ask",
            "",
            "Request: Agent Loop v1 status/policy/preview.",
            f"Interpreted intent: {getattr(route, 'intent', 'unknown')}",
            "Mode: read-only local/mock agent loop preview.",
            "No work session was recorded and no action was executed.",
            "No live LLM call was made.",
            "Agent loop is local/mock preview only.",
            "Actions are preview-only.",
            "Tools are not executed.",
            "Secrets/config/session data are blocked.",
            "Browser/desktop/shell/cloud/MCP execution remains locked.",
            "",
            "Result:",
            body,
        ]
    )


def _format_workflow_planner_ask_response(route: object, body: str) -> str:
    """Render local workflow-planner status without creating a work-session record."""
    return "\n".join(
        [
            "Eva ask",
            "",
            "Request: Agentic Workflow Planner status/policy/preview.",
            f"Interpreted intent: {getattr(route, 'intent', 'unknown')}",
            "Mode: read-only local/mock workflow planner preview.",
            "No work session was recorded and no action was executed.",
            "No live LLM call was made.",
            "Workflow planner is local/mock preview only.",
            "Workflow steps are preview-only.",
            "Tools are not executed.",
            "Secrets/config/session data are blocked.",
            "Arbitrary file reads/writes are blocked.",
            "Browser/desktop/shell/cloud/MCP execution remains locked.",
            "Phase 12L remains a gated write path.",
            "",
            "Result:",
            body,
        ]
    )


def _format_execution_gates_ask_response(route: object, body: str) -> str:
    """Render local execution-gate status without creating a work-session record."""
    return "\n".join(
        [
            "Eva ask",
            "",
            "Request: Controlled Execution Gates status/policy/evaluation.",
            f"Interpreted intent: {getattr(route, 'intent', 'unknown')}",
            "Mode: read-only local/mock execution-gate policy preview.",
            "No work session was recorded and no action was executed.",
            "No live LLM call was made.",
            "Execution gates are local/mock policy preview only.",
            "Tools are not executed.",
            "Approval alone does not execute.",
            "Confirmation alone does not execute unless an existing implemented gate accepts it.",
            "Browser/desktop/shell/cloud/MCP/package execution remains locked.",
            "Secrets/config/session data are blocked.",
            "Phase 12L narrow real-create remains a gated write path.",
            "",
            "Result:",
            body,
        ]
    )


def _format_ai_os_ask_response(route: object, body: str) -> str:
    """Render local AI OS status without activating any runtime surface."""
    return "\n".join(
        [
            "Eva ask",
            "",
            "Request: AI OS dashboard/status/report.",
            f"Interpreted intent: {getattr(route, 'intent', 'unknown')}",
            "No live LLM call was made.",
            "AI OS dashboard is local/status only.",
            "Preview-only features do not execute.",
            "Tools are not executed.",
            "Browser/desktop/shell/cloud/MCP execution remains locked.",
            "Secrets/config/session data are blocked.",
            "Phase 12L remains a gated write path.",
            "",
            "Result:",
            body,
        ]
    )


def _format_voice_ask_response(route: object, body: str) -> str:
    """Render local Voice Assistant status without touching audio devices."""
    return "\n".join(
        [
            "Eva ask",
            "",
            "Request: Voice Assistant Foundation status/policy/preview.",
            f"Interpreted intent: {getattr(route, 'intent', 'unknown')}",
            "Voice Assistant is local/mock preview only.",
            "No microphone access happened.",
            "No audio playback happened.",
            "No live ASR/TTS happened.",
            "No live LLM call was made.",
            "Voice commands cannot execute tools.",
            "Secrets/config/session data are blocked.",
            "Browser/desktop/shell/cloud/MCP execution remains locked.",
            "Phase 12L remains a gated write path.",
            "",
            "Result:",
            body,
        ]
    )


def _format_memory_v3_ask_response(route: object, body: str) -> str:
    """Render local Memory v3 status without exposing raw memory storage."""
    return "\n".join(
        [
            "Eva ask",
            "",
            "Request: Memory v3 status/policy/retrieval preview.",
            f"Interpreted intent: {getattr(route, 'intent', 'unknown')}",
            "Mode: read-only local memory policy preview.",
            "No work session was recorded and no memory record was written.",
            "Memory v3 is local only.",
            "No live LLM call was made.",
            "No cloud memory is used.",
            "Secrets/config/session data are blocked.",
            "Memory cannot override system/developer/safety policy.",
            "Memory cannot execute tools.",
            "Memory context injection is preview/policy only.",
            "",
            "Result:",
            body,
        ]
    )


def _format_browser_read_ask_response(route: object, body: str) -> str:
    """Render Phase 24 observation/report output without recording a work session."""
    return "\n".join(
        [
            "Eva ask",
            "",
            "Request: Real Browser Read-Only Mode observation/status/policy.",
            f"Interpreted intent: {getattr(route, 'intent', 'unknown')}",
            "Browser mode is read-only.",
            "No clicking.",
            "No typing.",
            "No form submission.",
            "No downloads or uploads.",
            "No cookies, sessions, or browser profiles.",
            "No logged-in browser access.",
            "No browser control.",
            "No tool execution.",
            "No work session was recorded and no browser action was executed.",
            "Phase 12L remains a gated write path.",
            "",
            "Result:",
            body,
        ]
    )


def _format_desktop_observe_ask_response(route: object, body: str) -> str:
    """Render Phase 25 observation/report output without recording a work session."""
    return "\n".join(
        [
            "Eva ask",
            "",
            "Request: Real Desktop Observation Mode observation/status/policy.",
            f"Interpreted intent: {getattr(route, 'intent', 'unknown')}",
            "Desktop mode is observation-only.",
            "No clicking.",
            "No typing.",
            "No hotkeys.",
            "No app or window control.",
            "No continuous monitoring.",
            "No saved screenshots.",
            "No cookies, sessions, or browser profiles.",
            "No tool execution.",
            "No work session was recorded and no desktop action was executed.",
            "Phase 12L remains a gated write path.",
            "",
            "Result:",
            body,
        ]
    )


def _resolve_single_approved_file_approval(intent: str) -> str | None:
    from ..file_agent.approval_ledger import list_file_approval_requests

    approvals = list_file_approval_requests(status="approved_for_future_apply", limit=20)
    if len(approvals) != 1:
        return None
    approval_id = approvals[0].approval_id
    if intent == "approval_sandbox_verify":
        return f"eva file approval sandbox verify {approval_id}"
    if intent == "approval_sandbox_rollback":
        return f"eva file approval sandbox rollback {approval_id}"
    return f"eva file approval sandbox apply {approval_id}"


def _format_real_create_next_step() -> str:
    from ..file_agent.approval_ledger import list_file_approval_requests
    from ..file_agent.real_apply import evaluate_real_apply_eligibility, format_real_apply_eligibility

    eligible = []
    for approval in list_file_approval_requests(status="approved_for_future_apply", limit=50):
        item = evaluate_real_apply_eligibility(approval.approval_id)
        if item.allowed:
            eligible.append(item)
    if len(eligible) == 1:
        return "\n".join(
            [
                format_real_apply_eligibility(eligible[0]),
                "",
                f"To create it, run: `eva ask confirm real create {eligible[0].approval_id}`.",
            ]
        )
    if not eligible:
        return "No eligible narrow real-create approval was found. Use `eva file real apply eligibility <approval_id>` to inspect a specific approval. Exact creation requires `confirm real create <approval_id>`."
    lines = ["Multiple eligible real-create approvals exist. Specify one approval id:"]
    lines.extend(f"- {item.approval_id}: {item.display_path}" for item in eligible[:10])
    return "\n".join(lines)


def _should_show_skill_workflow_plan(request_text: str) -> bool:
    text = " ".join(str(request_text or "").lower().split())
    return any(term in text for term in ("docs note", "phase note", "latest fileagent phase", "latest phase"))


def maybe_handle_fast_command(
    message: str,
    tools: ToolRegistry,
    session_context: dict | None = None,
    memory: object | None = None,
    session_id: str | None = None,
) -> tuple[str, str] | None:
    normalized = " ".join(message.lower().strip().split())
    original = message.strip()
    if not normalized:
        return None

    ask = _handle_eva_ask_command(normalized, original, tools, session_context, memory, session_id)
    if ask:
        return ask

    if normalized in {
        "eva browser read status",
        "eva browser read policy",
        "eva browser read url policy",
        "eva browser read mock observe",
        "eva browser read safety report",
        "eva browser read blocked urls",
        "eva browser read readiness",
    }:
        from ..browser_readonly.formatter import (
            format_browser_read_blocked_urls,
            format_browser_read_mock_observe,
            format_browser_read_policy,
            format_browser_read_readiness,
            format_browser_read_safety_report,
            format_browser_read_status,
            format_browser_read_url_policy,
        )

        browser_read_commands = {
            "eva browser read status": format_browser_read_status,
            "eva browser read policy": format_browser_read_policy,
            "eva browser read url policy": format_browser_read_url_policy,
            "eva browser read mock observe": format_browser_read_mock_observe,
            "eva browser read safety report": format_browser_read_safety_report,
            "eva browser read blocked urls": format_browser_read_blocked_urls,
            "eva browser read readiness": format_browser_read_readiness,
        }
        return browser_read_commands[normalized](), "fast-command"

    if normalized == "eva browser read observe" or normalized.startswith("eva browser read observe "):
        from ..browser_readonly.formatter import format_browser_read_observe

        target = original[len("eva browser read observe") :].strip()
        return format_browser_read_observe(target or None), "fast-command"

    status_reply = dispatch_status_command(normalized)
    if status_reply is not None:
        return status_reply, "fast-command"

    if normalized in {"eva control center", "eva control center status", "eva dashboard status", "eva control status"}:
        from ..control_center.status import format_control_center_text

        return format_control_center_text(), "fast-command"

    if normalized in {"eva control center summary", "eva dashboard summary"}:
        from ..control_center.status import format_control_center_summary_text

        return format_control_center_summary_text(), "fast-command"

    if normalized in {"eva sessions status", "eva work status"}:
        from ..work_sessions.formatter import format_work_sessions_status

        return format_work_sessions_status(), "fast-command"

    if normalized == "eva sessions recent":
        from ..work_sessions.formatter import summarize_recent_work_sessions

        return summarize_recent_work_sessions(), "fast-command"

    if normalized == "eva session latest":
        from ..work_sessions.status import format_latest_work_session

        return format_latest_work_session(), "fast-command"

    if normalized == "eva audit timeline":
        from ..work_sessions.status import format_audit_timeline

        return format_audit_timeline(), "fast-command"

    if normalized.startswith("eva session timeline "):
        from ..work_sessions.status import format_work_session_timeline_by_id

        session_ref = original[len("eva session timeline ") :].strip()
        return format_work_session_timeline_by_id(session_ref), "fast-command"

    if normalized.startswith("eva session "):
        from ..work_sessions.status import format_work_session_detail

        session_ref = original[len("eva session ") :].strip()
        return format_work_session_detail(session_ref), "fast-command"

    if normalized == "eva locked features":
        from ..control_center.status import format_locked_features_text

        return format_locked_features_text(), "fast-command"

    if normalized == "eva enabled features":
        from ..control_center.status import format_enabled_features_text

        return format_enabled_features_text(), "fast-command"

    if normalized == "eva next safe step":
        from ..control_center.status import format_next_safe_step_text

        return format_next_safe_step_text(), "fast-command"

    if normalized == "eva project inspect":
        from ..skills.project_inspection import format_project_inspection

        return format_project_inspection(), "fast-command"

    if normalized == "eva project reality check":
        from ..skills.reality_check import format_reality_check

        return format_reality_check(), "fast-command"

    if normalized == "eva project recent changes":
        from ..skills.project_inspection import format_recent_project_changes

        return format_recent_project_changes(), "fast-command"

    if normalized == "eva project next step":
        from ..skills.project_inspection import format_project_next_step

        return format_project_next_step(), "fast-command"

    if normalized == "eva project proof":
        from ..skills.reality_check import format_project_proof

        return format_project_proof(), "fast-command"

    if normalized == "eva done check":
        from ..skills.reality_check import format_done_check

        return format_done_check(), "fast-command"

    if normalized == "eva phase status":
        from ..skills.project_inspection import format_project_inspection

        return format_project_inspection(), "fast-command"

    if normalized in {"eva specialists status", "eva specialists", "eva specialists list"}:
        from ..specialists.formatter import format_specialist_list
        from ..specialists.status import format_specialist_status

        body = format_specialist_status() if normalized == "eva specialists status" else format_specialist_list()
        return body, "fast-command"

    specialist_id = _after_prefix(original, ("eva specialist ",))
    if specialist_id:
        from ..specialists.formatter import format_specialist_detail

        return format_specialist_detail(specialist_id.strip()), "fast-command"

    if normalized in {"eva skills status", "eva skills", "eva skills list"}:
        from ..skills.formatter import format_skill_list
        from ..skills.status import format_skill_status

        body = format_skill_status() if normalized == "eva skills status" else format_skill_list()
        return body, "fast-command"

    skill_id = _after_prefix(original, ("eva skill ",))
    if skill_id:
        from ..skills.formatter import format_skill_detail

        return format_skill_detail(skill_id.strip()), "fast-command"

    if normalized in {"eva workflows status", "eva workflows", "eva workflows list"}:
        from ..skills.formatter import format_workflow_list
        from ..skills.status import format_workflow_status

        body = format_workflow_status() if normalized == "eva workflows status" else format_workflow_list()
        return body, "fast-command"

    if normalized in {"eva workflow state", "eva file latest status"}:
        from ..skills.workflow_state import format_workflow_state_summary, summarize_fileagent_workflow_state

        return format_workflow_state_summary(summarize_fileagent_workflow_state()), "fast-command"

    if normalized == "eva workflow next":
        from ..skills.workflow_state import classify_next_fileagent_step, format_workflow_next_step

        return format_workflow_next_step(classify_next_fileagent_step("what should I do next")), "fast-command"

    if normalized == "eva workflow latest approval":
        from ..skills.workflow_state import find_latest_approved_approval, find_latest_pending_approval, format_latest_workflow_context

        return "\n\n".join([format_latest_workflow_context(find_latest_pending_approval()), format_latest_workflow_context(find_latest_approved_approval())]), "fast-command"

    if normalized == "eva workflow latest sandbox":
        from ..skills.workflow_state import find_latest_sandbox_apply, format_latest_workflow_context

        return format_latest_workflow_context(find_latest_sandbox_apply()), "fast-command"

    if normalized in {"eva workflow latest real create", "eva file latest real create"}:
        from ..skills.workflow_state import find_latest_real_create, format_latest_workflow_context

        return format_latest_workflow_context(find_latest_real_create()), "fast-command"

    if normalized in {"eva workflow latest rollback", "eva file latest rollback"}:
        from ..skills.workflow_state import find_latest_rollback_available, format_latest_workflow_context

        return format_latest_workflow_context(find_latest_rollback_available()), "fast-command"

    if normalized in {"eva golden workflows", "eva golden workflow status", "eva golden workflow help", "eva workflow golden status"}:
        from ..golden_workflows.status import format_golden_workflows_text

        return format_golden_workflows_text(), "fast-command"

    if normalized == "eva workflow golden test plan":
        from ..golden_workflows.status import format_golden_workflow_test_plan

        return format_golden_workflow_test_plan(), "fast-command"

    if normalized == "eva workflow golden latest":
        from ..golden_workflows.status import format_golden_workflow_latest

        return format_golden_workflow_latest(), "fast-command"

    if normalized == "eva workflow golden proof":
        from ..golden_workflows.status import format_golden_workflow_proof

        return format_golden_workflow_proof(), "fast-command"

    if normalized == "eva os status":
        from ..ai_os.formatter import format_ai_os_status
        return format_ai_os_status(), "fast-command"
    if normalized == "eva os dashboard":
        from ..ai_os.formatter import format_ai_os_dashboard
        return format_ai_os_dashboard(), "fast-command"
    if normalized == "eva os system map":
        from ..ai_os.formatter import format_ai_os_system_map
        return format_ai_os_system_map(), "fast-command"
    if normalized == "eva os capability matrix":
        from ..ai_os.formatter import format_ai_os_capability_matrix
        return format_ai_os_capability_matrix(), "fast-command"
    if normalized == "eva os feature states":
        from ..ai_os.formatter import format_ai_os_feature_states
        return format_ai_os_feature_states(), "fast-command"
    if normalized == "eva os safety boundaries":
        from ..ai_os.formatter import format_ai_os_safety_boundaries
        return format_ai_os_safety_boundaries(), "fast-command"
    if normalized == "eva os locked features":
        from ..ai_os.formatter import format_ai_os_locked_features
        return format_ai_os_locked_features(), "fast-command"
    if normalized == "eva os next safe step":
        from ..ai_os.formatter import format_ai_os_next_safe_step
        return format_ai_os_next_safe_step(), "fast-command"
    if normalized == "eva os readiness":
        from ..ai_os.formatter import format_ai_os_readiness
        return format_ai_os_readiness(), "fast-command"

    if normalized == "eva voice status":
        from ..voice_assistant.formatter import format_voice_status
        return format_voice_status(), "fast-command"
    if normalized == "eva voice policy":
        from ..voice_assistant.formatter import format_voice_policy
        return format_voice_policy(), "fast-command"
    if normalized == "eva voice providers":
        from ..voice_assistant.formatter import format_voice_providers
        return format_voice_providers(), "fast-command"
    if normalized == "eva voice listen state":
        from ..voice_assistant.formatter import format_voice_listen_state
        return format_voice_listen_state(), "fast-command"
    if normalized == "eva voice transcript safety":
        from ..voice_assistant.formatter import format_voice_transcript_safety
        return format_voice_transcript_safety(), "fast-command"
    if normalized == "eva voice route preview":
        from ..voice_assistant.formatter import format_voice_route_preview
        return format_voice_route_preview(), "fast-command"
    if normalized == "eva voice confirmations":
        from ..voice_assistant.formatter import format_voice_confirmations
        return format_voice_confirmations(), "fast-command"
    if normalized == "eva voice readiness":
        from ..voice_assistant.formatter import format_voice_readiness
        return format_voice_readiness(), "fast-command"

    if normalized == "eva memory v3 status":
        from ..memory_v3.formatter import format_memory_v3_status
        return format_memory_v3_status(), "fast-command"
    if normalized == "eva memory v3 policy":
        from ..memory_v3.formatter import format_memory_v3_policy
        return format_memory_v3_policy(), "fast-command"
    if normalized == "eva memory v3 sources":
        from ..memory_v3.formatter import format_memory_v3_sources
        return format_memory_v3_sources(), "fast-command"
    if normalized == "eva memory v3 privacy":
        from ..memory_v3.formatter import format_memory_v3_privacy
        return format_memory_v3_privacy(), "fast-command"
    if normalized == "eva memory v3 freshness":
        from ..memory_v3.formatter import format_memory_v3_freshness
        return format_memory_v3_freshness(), "fast-command"
    if normalized == "eva memory v3 conflicts":
        from ..memory_v3.formatter import format_memory_v3_conflicts
        return format_memory_v3_conflicts(), "fast-command"
    if normalized == "eva memory v3 retrieval preview":
        from ..memory_v3.formatter import format_memory_v3_retrieval_preview
        return format_memory_v3_retrieval_preview(), "fast-command"
    if normalized == "eva memory v3 readiness":
        from ..memory_v3.formatter import format_memory_v3_readiness
        return format_memory_v3_readiness(), "fast-command"

    if normalized == "eva execution gates status":
        from ..execution_gates.formatter import format_execution_gate_status
        return format_execution_gate_status(), "fast-command"
    if normalized == "eva execution gates policy":
        from ..execution_gates.formatter import format_execution_gate_policy
        return format_execution_gate_policy(), "fast-command"
    if normalized == "eva execution gates evaluate":
        from ..execution_gates.formatter import format_execution_gate_evaluation
        return format_execution_gate_evaluation(), "fast-command"
    if normalized == "eva execution gates approvals":
        from ..execution_gates.formatter import format_execution_gate_approvals
        return format_execution_gate_approvals(), "fast-command"
    if normalized == "eva execution gates confirmations":
        from ..execution_gates.formatter import format_execution_gate_confirmations
        return format_execution_gate_confirmations(), "fast-command"
    if normalized == "eva execution gates rollback":
        from ..execution_gates.formatter import format_execution_gate_rollback
        return format_execution_gate_rollback(), "fast-command"
    if normalized == "eva execution gates blocked actions":
        from ..execution_gates.formatter import format_execution_gate_blocked_actions
        return format_execution_gate_blocked_actions(), "fast-command"
    if normalized == "eva execution gates readiness":
        from ..execution_gates.formatter import format_execution_gate_readiness
        return format_execution_gate_readiness(), "fast-command"

    if normalized == "eva workflow planner status":
        from ..workflow_planner.formatter import format_workflow_planner_status
        return format_workflow_planner_status(), "fast-command"
    if normalized == "eva workflow planner catalog":
        from ..workflow_planner.formatter import format_workflow_planner_catalog
        return format_workflow_planner_catalog(), "fast-command"
    if normalized == "eva workflow planner policy":
        from ..workflow_planner.formatter import format_workflow_planner_policy
        return format_workflow_planner_policy(), "fast-command"
    if normalized == "eva workflow planner preview":
        from ..workflow_planner.formatter import format_workflow_planner_preview
        return format_workflow_planner_preview(), "fast-command"
    if normalized == "eva workflow planner dependencies":
        from ..workflow_planner.formatter import format_workflow_planner_dependencies
        return format_workflow_planner_dependencies(), "fast-command"
    if normalized == "eva workflow planner approvals":
        from ..workflow_planner.formatter import format_workflow_planner_approvals
        return format_workflow_planner_approvals(), "fast-command"
    if normalized == "eva workflow planner rollback":
        from ..workflow_planner.formatter import format_workflow_planner_rollback
        return format_workflow_planner_rollback(), "fast-command"
    if normalized == "eva workflow planner readiness":
        from ..workflow_planner.formatter import format_workflow_planner_readiness
        return format_workflow_planner_readiness(), "fast-command"

    workflow_id = _after_prefix(original, ("eva workflow ",))
    if workflow_id:
        from ..skills.formatter import format_workflow_detail

        return format_workflow_detail(workflow_id.strip()), "fast-command"

    if normalized in {"eva golden workflows", "eva golden workflow status", "eva golden workflow help", "eva workflow golden status"}:
        from ..golden_workflows.status import format_golden_workflows_text

        return format_golden_workflows_text(), "fast-command"

    if normalized == "eva workflow golden test plan":
        from ..golden_workflows.status import format_golden_workflow_test_plan

        return format_golden_workflow_test_plan(), "fast-command"

    if normalized == "eva workflow golden latest":
        from ..golden_workflows.status import format_golden_workflow_latest

        return format_golden_workflow_latest(), "fast-command"

    if normalized == "eva workflow golden proof":
        from ..golden_workflows.status import format_golden_workflow_proof

        return format_golden_workflow_proof(), "fast-command"

    if normalized == "eva golden workflow demo":
        from ..golden_workflows.formatter import format_golden_workflow_result
        from ..golden_workflows.runner import start_safe_project_note_workflow

        return format_golden_workflow_result(start_safe_project_note_workflow("demo safe project note")), "fast-command"

    golden_project_note = _after_prefix(original, ("eva golden workflow start project note ",))
    if normalized == "eva golden workflow start project note" or golden_project_note:
        from ..golden_workflows.formatter import format_golden_workflow_result
        from ..golden_workflows.runner import start_safe_project_note_workflow

        return format_golden_workflow_result(start_safe_project_note_workflow(golden_project_note or "create a project note about Eva")), "fast-command"

    golden_continue = _after_prefix(original, ("eva golden workflow continue ",))
    if normalized == "eva golden workflow continue" or golden_continue:
        from ..golden_workflows.formatter import format_golden_workflow_result
        from ..golden_workflows.runner import continue_safe_project_note_workflow

        return format_golden_workflow_result(continue_safe_project_note_workflow(golden_continue or "continue golden workflow")), "fast-command"

    if normalized in {"eva dashboard url", "eva control center url", "eva control url"}:
        from ..control_center.status import format_control_center_url

        return format_control_center_url(), "fast-command"

    if normalized == "eva authority status":
        from ..authority.status import format_authority_status

        return format_authority_status(), "fast-command"

    if normalized in {"eva smoke status", "eva verification status"}:
        from ..core.ux_messages import format_quick_status_summary

        return format_quick_status_summary(), "fast-command"

    if normalized == "eva verify quick command":
        from ..core.ux_messages import format_verify_quick_command

        return format_verify_quick_command(), "fast-command"

    if normalized == "eva verify full command":
        from ..core.ux_messages import format_verify_full_command

        return format_verify_full_command(), "fast-command"

    if normalized == "eva phase 12 status":
        from ..core.ux_messages import format_phase12_status

        return format_phase12_status(), "fast-command"

    if normalized in {"eva phase 12 ready", "eva phase12 ready"}:
        from ..core.phase12_ready import format_phase12_ready

        return format_phase12_ready(), "fast-command"

    if normalized in {"eva phase 12 summary", "eva phase12 summary"}:
        from ..core.phase12_ready import format_phase12_summary

        return format_phase12_summary(), "fast-command"

    if normalized in {"eva phase 12 limits", "eva phase12 limits"}:
        from ..core.phase12_ready import format_phase12_limits

        return format_phase12_limits(), "fast-command"

    if normalized in {"eva phase 12 proof", "eva phase12 proof"}:
        from ..core.phase12_ready import format_phase12_proof

        return format_phase12_proof(), "fast-command"

    if normalized == "eva desktop status":
        from ..desktop_agent.formatter import format_desktop_status

        return format_desktop_status(), "fast-command"

    if normalized == "eva llm status":
        from ..llm.formatter import format_llm_status as format_eva_llm_router_status
        return format_eva_llm_router_status(), "fast-command"
    if normalized == "eva llm providers":
        from ..llm.formatter import format_llm_providers
        return format_llm_providers(), "fast-command"
    if normalized == "eva llm routing policy":
        from ..llm.formatter import format_llm_routing_policy
        return format_llm_routing_policy(), "fast-command"
    if normalized == "eva llm fallback policy":
        from ..llm.formatter import format_llm_fallback_policy
        return format_llm_fallback_policy(), "fast-command"
    if normalized == "eva llm limits":
        from ..llm.formatter import format_llm_limits
        return format_llm_limits(), "fast-command"
    if normalized == "eva llm structured output":
        from ..llm.formatter import format_llm_structured_output
        return format_llm_structured_output(), "fast-command"
    if normalized == "eva llm validation status":
        from ..llm.formatter import format_llm_validation_status
        return format_llm_validation_status(), "fast-command"
    if normalized == "eva llm schema registry":
        from ..llm.formatter import format_llm_schema_registry
        return format_llm_schema_registry(), "fast-command"
    if normalized == "eva llm validation policy":
        from ..llm.formatter import format_llm_validation_policy
        return format_llm_validation_policy(), "fast-command"
    if normalized == "eva llm repair policy":
        from ..llm.formatter import format_llm_repair_policy
        return format_llm_repair_policy(), "fast-command"
    if normalized == "eva llm validate mock":
        from ..llm.formatter import format_llm_validate_mock
        return format_llm_validate_mock(), "fast-command"
    if normalized == "eva llm validate invalid examples":
        from ..llm.formatter import format_llm_validate_invalid_examples
        return format_llm_validate_invalid_examples(), "fast-command"
    if normalized == "eva llm validation readiness":
        from ..llm.formatter import format_llm_validation_readiness
        return format_llm_validation_readiness(), "fast-command"
    if normalized == "eva llm red team status":
        from ..llm.formatter import format_llm_red_team_status
        return format_llm_red_team_status(), "fast-command"
    if normalized == "eva llm red team cases":
        from ..llm.formatter import format_llm_red_team_cases
        return format_llm_red_team_cases(), "fast-command"
    if normalized == "eva llm red team run":
        from ..llm.formatter import format_llm_red_team_run
        return format_llm_red_team_run(), "fast-command"
    if normalized == "eva llm failure tests":
        from ..llm.formatter import format_llm_failure_tests
        return format_llm_failure_tests(), "fast-command"
    if normalized == "eva llm safety failure report":
        from ..llm.formatter import format_llm_safety_failure_report
        return format_llm_safety_failure_report(), "fast-command"
    if normalized == "eva llm red team readiness":
        from ..llm.formatter import format_llm_red_team_readiness
        return format_llm_red_team_readiness(), "fast-command"
    llm_route_preview = _after_prefix(original, ("eva llm route preview ",))
    if llm_route_preview:
        from ..llm.formatter import format_llm_route_preview
        return format_llm_route_preview(llm_route_preview), "fast-command"
    if normalized == "eva llm readiness":
        from ..llm.formatter import format_llm_readiness
        return format_llm_readiness(), "fast-command"
    if normalized == "eva llm fallback chain":
        from ..llm.formatter import format_llm_fallback_chain
        return format_llm_fallback_chain(), "fast-command"
    llm_fallback_simulation = _after_prefix(original, ("eva llm fallback simulate ",))
    if llm_fallback_simulation:
        from ..llm.formatter import format_llm_fallback_simulation
        return format_llm_fallback_simulation(llm_fallback_simulation), "fast-command"
    if normalized == "eva llm degraded mode":
        from ..llm.formatter import format_llm_degraded_mode
        return format_llm_degraded_mode(), "fast-command"
    if normalized == "eva llm session limits":
        from ..llm.formatter import format_llm_session_limits
        return format_llm_session_limits(), "fast-command"
    if normalized == "eva llm rate limits":
        from ..llm.formatter import format_llm_rate_limits
        return format_llm_rate_limits(), "fast-command"
    if normalized == "eva llm routing audit preview":
        from ..llm.formatter import format_llm_routing_audit_preview
        return format_llm_routing_audit_preview(), "fast-command"
    if normalized == "eva llm failure modes":
        from ..llm.formatter import format_llm_failure_modes
        return format_llm_failure_modes(), "fast-command"
    if normalized == "eva llm runaway protection":
        from ..llm.formatter import format_llm_runaway_protection
        return format_llm_runaway_protection(), "fast-command"

    if normalized == "eva context status":
        from ..context_engine.formatter import format_context_status
        return format_context_status(), "fast-command"
    if normalized == "eva context sources":
        from ..context_engine.formatter import format_context_sources
        return format_context_sources(), "fast-command"
    if normalized == "eva context policy":
        from ..context_engine.formatter import format_context_policy
        return format_context_policy(), "fast-command"
    if normalized == "eva context budget":
        from ..context_engine.formatter import format_context_budget
        return format_context_budget(), "fast-command"
    if normalized == "eva context assemble preview":
        from ..context_engine.formatter import format_context_assemble_preview
        return format_context_assemble_preview(original), "fast-command"
    if normalized == "eva context grounding report":
        from ..context_engine.formatter import format_context_grounding_report
        return format_context_grounding_report(original), "fast-command"
    if normalized == "eva context redaction policy":
        from ..context_engine.formatter import format_context_redaction_policy
        return format_context_redaction_policy(), "fast-command"
    if normalized == "eva context readiness":
        from ..context_engine.formatter import format_context_readiness
        return format_context_readiness(), "fast-command"
    if normalized == "eva threat status":
        from ..threat_defense.formatter import format_threat_status
        return format_threat_status(), "fast-command"
    if normalized == "eva threat catalog":
        from ..threat_defense.formatter import format_threat_catalog
        return format_threat_catalog(), "fast-command"
    if normalized == "eva threat policy":
        from ..threat_defense.formatter import format_threat_policy
        return format_threat_policy(), "fast-command"
    if normalized == "eva threat scan preview":
        from ..threat_defense.formatter import format_threat_scan_preview
        return format_threat_scan_preview(), "fast-command"
    if normalized == "eva threat injection examples":
        from ..threat_defense.formatter import format_threat_injection_examples
        return format_threat_injection_examples(), "fast-command"
    if normalized == "eva threat exfiltration examples":
        from ..threat_defense.formatter import format_threat_exfiltration_examples
        return format_threat_exfiltration_examples(), "fast-command"
    if normalized == "eva threat context guard":
        from ..threat_defense.formatter import format_threat_context_guard
        return format_threat_context_guard(), "fast-command"
    if normalized == "eva threat readiness":
        from ..threat_defense.formatter import format_threat_readiness
        return format_threat_readiness(), "fast-command"
    if normalized == "eva agent loop status":
        from ..agent_loop.formatter import format_agent_loop_status
        return format_agent_loop_status(), "fast-command"
    if normalized == "eva agent loop policy":
        from ..agent_loop.formatter import format_agent_loop_policy
        return format_agent_loop_policy(), "fast-command"
    if normalized == "eva agent loop run preview":
        from ..agent_loop.formatter import format_agent_loop_run_preview
        return format_agent_loop_run_preview(), "fast-command"
    if normalized == "eva agent loop steps":
        from ..agent_loop.formatter import format_agent_loop_steps
        return format_agent_loop_steps(), "fast-command"
    if normalized == "eva agent loop action previews":
        from ..agent_loop.formatter import format_agent_loop_action_previews
        return format_agent_loop_action_previews(), "fast-command"
    if normalized == "eva agent loop safety report":
        from ..agent_loop.formatter import format_agent_loop_safety_report
        return format_agent_loop_safety_report(), "fast-command"
    if normalized == "eva agent loop stop reasons":
        from ..agent_loop.formatter import format_agent_loop_stop_reasons
        return format_agent_loop_stop_reasons(), "fast-command"
    if normalized == "eva agent loop readiness":
        from ..agent_loop.formatter import format_agent_loop_readiness
        return format_agent_loop_readiness(), "fast-command"
    if normalized == "eva os status":
        from ..ai_os.formatter import format_ai_os_status
        return format_ai_os_status(), "fast-command"
    if normalized == "eva os dashboard":
        from ..ai_os.formatter import format_ai_os_dashboard
        return format_ai_os_dashboard(), "fast-command"
    if normalized == "eva os system map":
        from ..ai_os.formatter import format_ai_os_system_map
        return format_ai_os_system_map(), "fast-command"
    if normalized == "eva os capability matrix":
        from ..ai_os.formatter import format_ai_os_capability_matrix
        return format_ai_os_capability_matrix(), "fast-command"
    if normalized == "eva os feature states":
        from ..ai_os.formatter import format_ai_os_feature_states
        return format_ai_os_feature_states(), "fast-command"
    if normalized == "eva os safety boundaries":
        from ..ai_os.formatter import format_ai_os_safety_boundaries
        return format_ai_os_safety_boundaries(), "fast-command"
    if normalized == "eva os locked features":
        from ..ai_os.formatter import format_ai_os_locked_features
        return format_ai_os_locked_features(), "fast-command"
    if normalized == "eva os next safe step":
        from ..ai_os.formatter import format_ai_os_next_safe_step
        return format_ai_os_next_safe_step(), "fast-command"
    if normalized == "eva os readiness":
        from ..ai_os.formatter import format_ai_os_readiness
        return format_ai_os_readiness(), "fast-command"
    if normalized == "eva voice status":
        from ..voice_assistant.formatter import format_voice_status
        return format_voice_status(), "fast-command"
    if normalized == "eva voice policy":
        from ..voice_assistant.formatter import format_voice_policy
        return format_voice_policy(), "fast-command"
    if normalized == "eva voice providers":
        from ..voice_assistant.formatter import format_voice_providers
        return format_voice_providers(), "fast-command"
    if normalized == "eva voice listen state":
        from ..voice_assistant.formatter import format_voice_listen_state
        return format_voice_listen_state(), "fast-command"
    if normalized == "eva voice transcript safety":
        from ..voice_assistant.formatter import format_voice_transcript_safety
        return format_voice_transcript_safety(), "fast-command"
    if normalized == "eva voice route preview":
        from ..voice_assistant.formatter import format_voice_route_preview
        return format_voice_route_preview(), "fast-command"
    if normalized == "eva voice confirmations":
        from ..voice_assistant.formatter import format_voice_confirmations
        return format_voice_confirmations(), "fast-command"
    if normalized == "eva voice readiness":
        from ..voice_assistant.formatter import format_voice_readiness
        return format_voice_readiness(), "fast-command"
    if normalized == "eva memory v3 status":
        from ..memory_v3.formatter import format_memory_v3_status
        return format_memory_v3_status(), "fast-command"
    if normalized == "eva memory v3 policy":
        from ..memory_v3.formatter import format_memory_v3_policy
        return format_memory_v3_policy(), "fast-command"
    if normalized == "eva memory v3 sources":
        from ..memory_v3.formatter import format_memory_v3_sources
        return format_memory_v3_sources(), "fast-command"
    if normalized == "eva memory v3 privacy":
        from ..memory_v3.formatter import format_memory_v3_privacy
        return format_memory_v3_privacy(), "fast-command"
    if normalized == "eva memory v3 freshness":
        from ..memory_v3.formatter import format_memory_v3_freshness
        return format_memory_v3_freshness(), "fast-command"
    if normalized == "eva memory v3 conflicts":
        from ..memory_v3.formatter import format_memory_v3_conflicts
        return format_memory_v3_conflicts(), "fast-command"
    if normalized == "eva memory v3 retrieval preview":
        from ..memory_v3.formatter import format_memory_v3_retrieval_preview
        return format_memory_v3_retrieval_preview(), "fast-command"
    if normalized == "eva memory v3 readiness":
        from ..memory_v3.formatter import format_memory_v3_readiness
        return format_memory_v3_readiness(), "fast-command"
    if normalized == "eva execution gates status":
        from ..execution_gates.formatter import format_execution_gate_status
        return format_execution_gate_status(), "fast-command"
    if normalized == "eva execution gates policy":
        from ..execution_gates.formatter import format_execution_gate_policy
        return format_execution_gate_policy(), "fast-command"
    if normalized == "eva execution gates evaluate":
        from ..execution_gates.formatter import format_execution_gate_evaluation
        return format_execution_gate_evaluation(), "fast-command"
    if normalized == "eva execution gates approvals":
        from ..execution_gates.formatter import format_execution_gate_approvals
        return format_execution_gate_approvals(), "fast-command"
    if normalized == "eva execution gates confirmations":
        from ..execution_gates.formatter import format_execution_gate_confirmations
        return format_execution_gate_confirmations(), "fast-command"
    if normalized == "eva execution gates rollback":
        from ..execution_gates.formatter import format_execution_gate_rollback
        return format_execution_gate_rollback(), "fast-command"
    if normalized == "eva execution gates blocked actions":
        from ..execution_gates.formatter import format_execution_gate_blocked_actions
        return format_execution_gate_blocked_actions(), "fast-command"
    if normalized == "eva execution gates readiness":
        from ..execution_gates.formatter import format_execution_gate_readiness
        return format_execution_gate_readiness(), "fast-command"
    if normalized == "eva workflow planner status":
        from ..workflow_planner.formatter import format_workflow_planner_status
        return format_workflow_planner_status(), "fast-command"
    if normalized == "eva workflow planner catalog":
        from ..workflow_planner.formatter import format_workflow_planner_catalog
        return format_workflow_planner_catalog(), "fast-command"
    if normalized == "eva workflow planner policy":
        from ..workflow_planner.formatter import format_workflow_planner_policy
        return format_workflow_planner_policy(), "fast-command"
    if normalized == "eva workflow planner preview":
        from ..workflow_planner.formatter import format_workflow_planner_preview
        return format_workflow_planner_preview(), "fast-command"
    if normalized == "eva workflow planner dependencies":
        from ..workflow_planner.formatter import format_workflow_planner_dependencies
        return format_workflow_planner_dependencies(), "fast-command"
    if normalized == "eva workflow planner approvals":
        from ..workflow_planner.formatter import format_workflow_planner_approvals
        return format_workflow_planner_approvals(), "fast-command"
    if normalized == "eva workflow planner rollback":
        from ..workflow_planner.formatter import format_workflow_planner_rollback
        return format_workflow_planner_rollback(), "fast-command"
    if normalized == "eva workflow planner readiness":
        from ..workflow_planner.formatter import format_workflow_planner_readiness
        return format_workflow_planner_readiness(), "fast-command"

    if normalized == "eva desktop phase 14 status":
        from ..desktop_agent.formatter import format_desktop_phase14_status

        return format_desktop_phase14_status(), "fast-command"

    if normalized == "eva desktop phase 14 summary":
        from ..desktop_agent.formatter import format_desktop_phase14_summary

        return format_desktop_phase14_summary(), "fast-command"

    if normalized == "eva desktop phase 14 limits":
        from ..desktop_agent.formatter import format_desktop_phase14_limits

        return format_desktop_phase14_limits(), "fast-command"

    if normalized == "eva desktop phase 14 ready":
        from ..desktop_agent.formatter import format_desktop_phase14_ready

        return format_desktop_phase14_ready(), "fast-command"

    if normalized == "eva desktop phase 14 final proof":
        from ..desktop_agent.formatter import format_desktop_phase14_final_proof

        return format_desktop_phase14_final_proof(), "fast-command"

    if normalized == "eva desktop readiness proof":
        from ..desktop_agent.formatter import format_desktop_readiness_proof

        return format_desktop_readiness_proof(), "fast-command"

    if normalized == "eva desktop locked status":
        from ..desktop_agent.formatter import format_desktop_locked_status

        return format_desktop_locked_status(), "fast-command"

    if normalized == "eva desktop readiness gaps":
        from ..desktop_agent.formatter import format_desktop_readiness_gaps

        return format_desktop_readiness_gaps(), "fast-command"

    if normalized == "eva desktop policy":
        from ..desktop_agent.formatter import format_desktop_policy

        return format_desktop_policy(), "fast-command"

    if normalized == "eva desktop blocked actions":
        from ..desktop_agent.formatter import format_desktop_blocked_actions

        return format_desktop_blocked_actions(), "fast-command"

    desktop_action_safety = _after_prefix(original, ("eva desktop action safety ",))
    if desktop_action_safety:
        from ..desktop_agent.formatter import format_desktop_action_safety

        return format_desktop_action_safety(desktop_action_safety), "fast-command"

    desktop_action_dry_run = _after_prefix(original, ("eva desktop action dry run ",))
    if desktop_action_dry_run:
        from ..desktop_agent.formatter import format_desktop_action_dry_run

        return format_desktop_action_dry_run(desktop_action_dry_run), "fast-command"

    desktop_action_plan = _after_prefix(original, ("eva desktop action plan ",))
    if desktop_action_plan:
        from ..desktop_agent.formatter import format_desktop_action_plan

        return format_desktop_action_plan(desktop_action_plan), "fast-command"

    desktop_action_risk = _after_prefix(original, ("eva desktop action risk ",))
    if desktop_action_risk:
        from ..desktop_agent.formatter import format_desktop_action_risk

        return format_desktop_action_risk(desktop_action_risk), "fast-command"

    if normalized == "eva desktop action approvals":
        from ..desktop_agent.formatter import format_desktop_action_approvals

        return format_desktop_action_approvals(), "fast-command"

    if normalized == "eva desktop dry run policy":
        from ..desktop_agent.formatter import format_desktop_dry_run_policy

        return format_desktop_dry_run_policy(), "fast-command"

    if normalized == "eva desktop action readiness":
        from ..desktop_agent.formatter import format_desktop_action_readiness

        return format_desktop_action_readiness(), "fast-command"

    desktop_risk_score = _after_prefix(original, ("eva desktop risk score ",))
    if desktop_risk_score:
        from ..desktop_agent.formatter import format_desktop_risk_score

        return format_desktop_risk_score(desktop_risk_score), "fast-command"

    desktop_risk_factors = _after_prefix(original, ("eva desktop risk factors ",))
    if desktop_risk_factors:
        from ..desktop_agent.formatter import format_desktop_risk_factors

        return format_desktop_risk_factors(desktop_risk_factors), "fast-command"

    desktop_approval_required = _after_prefix(original, ("eva desktop approval required ",))
    if desktop_approval_required:
        from ..desktop_agent.formatter import format_desktop_approval_required

        return format_desktop_approval_required(desktop_approval_required), "fast-command"

    if normalized == "eva desktop approval policy":
        from ..desktop_agent.formatter import format_desktop_approval_policy

        return format_desktop_approval_policy(), "fast-command"

    if normalized == "eva desktop approval levels":
        from ..desktop_agent.formatter import format_desktop_approval_levels

        return format_desktop_approval_levels(), "fast-command"

    desktop_approval_preview = _after_prefix(original, ("eva desktop approval preview ",))
    if desktop_approval_preview:
        from ..desktop_agent.formatter import format_desktop_approval_model_preview

        return format_desktop_approval_model_preview(desktop_approval_preview), "fast-command"

    desktop_confirmation_phrase = _after_prefix(original, ("eva desktop confirmation phrase ",))
    if desktop_confirmation_phrase:
        from ..desktop_agent.formatter import format_desktop_confirmation_phrase

        return format_desktop_confirmation_phrase(desktop_confirmation_phrase), "fast-command"

    if normalized == "eva desktop forbidden actions":
        from ..desktop_agent.formatter import format_desktop_forbidden_actions

        return format_desktop_forbidden_actions(), "fast-command"

    if normalized == "eva desktop approval audit status":
        from ..desktop_agent.formatter import format_desktop_approval_audit_status

        return format_desktop_approval_audit_status(), "fast-command"

    if normalized == "eva desktop approval readiness":
        from ..desktop_agent.formatter import format_desktop_approval_model_readiness

        return format_desktop_approval_model_readiness(), "fast-command"

    if normalized == "eva desktop safety matrix":
        from ..desktop_agent.formatter import format_desktop_safety_matrix

        return format_desktop_safety_matrix(), "fast-command"

    if normalized == "eva desktop high risk actions":
        from ..desktop_agent.formatter import format_desktop_high_risk_actions

        return format_desktop_high_risk_actions(), "fast-command"

    if normalized == "eva desktop risk readiness":
        from ..desktop_agent.formatter import format_desktop_risk_readiness

        return format_desktop_risk_readiness(), "fast-command"

    desktop_app_risk = _after_prefix(original, ("eva desktop app risk ",))
    if desktop_app_risk:
        from ..desktop_agent.formatter import format_desktop_app_risk

        return format_desktop_app_risk(desktop_app_risk), "fast-command"

    if normalized == "eva desktop readiness":
        from ..desktop_agent.formatter import format_desktop_readiness

        return format_desktop_readiness(), "fast-command"

    if normalized == "eva desktop session status":
        from ..desktop_agent.formatter import format_desktop_session_status

        return format_desktop_session_status(), "fast-command"

    if normalized == "eva desktop sessions":
        from ..desktop_agent.formatter import format_desktop_sessions

        return format_desktop_sessions(), "fast-command"

    if normalized == "eva desktop session preview":
        from ..desktop_agent.formatter import format_desktop_session_preview

        return format_desktop_session_preview(), "fast-command"

    if normalized == "eva desktop session latest":
        from ..desktop_agent.formatter import format_desktop_session_latest

        return format_desktop_session_latest(), "fast-command"

    if normalized == "eva desktop session plan":
        from ..desktop_agent.formatter import format_desktop_session_plan

        return format_desktop_session_plan(), "fast-command"

    if normalized == "eva desktop app status preview":
        from ..desktop_agent.formatter import format_desktop_app_status_preview

        return format_desktop_app_status_preview(), "fast-command"

    if normalized == "eva desktop window status preview":
        from ..desktop_agent.formatter import format_desktop_window_status_preview

        return format_desktop_window_status_preview(), "fast-command"

    if normalized == "eva desktop active context preview":
        from ..desktop_agent.formatter import format_desktop_active_context_preview

        return format_desktop_active_context_preview(), "fast-command"

    if normalized == "eva desktop observation readiness":
        from ..desktop_agent.formatter import format_desktop_observation_readiness

        return format_desktop_observation_readiness(), "fast-command"

    if normalized == "eva desktop screen policy":
        from ..desktop_agent.formatter import format_desktop_screen_policy

        return format_desktop_screen_policy(), "fast-command"

    if normalized == "eva desktop screen observation policy":
        from ..desktop_agent.formatter import format_desktop_screen_observation_policy

        return format_desktop_screen_observation_policy(), "fast-command"

    if normalized == "eva desktop sensitive screens":
        from ..desktop_agent.formatter import format_desktop_sensitive_screens

        return format_desktop_sensitive_screens(), "fast-command"

    if normalized == "eva desktop screen redaction policy":
        from ..desktop_agent.formatter import format_desktop_screen_redaction_policy

        return format_desktop_screen_redaction_policy(), "fast-command"

    if normalized == "eva desktop screen capture gate":
        from ..desktop_agent.formatter import format_desktop_screen_capture_gate

        return format_desktop_screen_capture_gate(), "fast-command"

    if normalized == "eva desktop screen readiness":
        from ..desktop_agent.formatter import format_desktop_screen_readiness

        return format_desktop_screen_readiness(), "fast-command"

    if normalized == "eva desktop observation policy":
        from ..desktop_agent.formatter import format_desktop_observation_policy

        return format_desktop_observation_policy(), "fast-command"

    if normalized == "eva browser status":
        from ..browser_agent.formatter import format_browser_status

        return format_browser_status(), "fast-command"

    if normalized == "eva browser policy":
        from ..browser_agent.formatter import format_browser_policy

        return format_browser_policy(), "fast-command"

    if normalized == "eva browser blocked actions":
        from ..browser_agent.formatter import format_browser_blocked_actions

        return format_browser_blocked_actions(), "fast-command"

    if normalized == "eva browser domain policy":
        from ..browser_agent.formatter import format_browser_domain_policy

        return format_browser_domain_policy(), "fast-command"

    if normalized == "eva browser readiness":
        from ..browser_agent.formatter import format_browser_readiness

        return format_browser_readiness(), "fast-command"

    if normalized == "eva browser session status":
        from ..browser_agent.formatter import format_browser_session_status

        return format_browser_session_status(), "fast-command"

    if normalized == "eva browser sessions":
        from ..browser_agent.formatter import format_browser_sessions

        return format_browser_sessions(), "fast-command"

    if normalized == "eva browser session preview":
        from ..browser_agent.formatter import format_browser_session_preview

        return format_browser_session_preview(), "fast-command"

    if normalized == "eva browser session latest":
        from ..browser_agent.formatter import format_browser_session_latest

        return format_browser_session_latest(), "fast-command"

    if normalized == "eva browser session plan":
        from ..browser_agent.formatter import format_browser_session_plan

        return format_browser_session_plan(), "fast-command"

    if normalized == "eva browser page summary policy":
        from ..browser_agent.formatter import format_browser_page_summary_policy

        return format_browser_page_summary_policy(), "fast-command"

    if normalized == "eva browser page summary preview":
        from ..browser_agent.formatter import format_browser_page_summary_preview

        return format_browser_page_summary_preview(), "fast-command"

    if normalized == "eva browser dom summary policy":
        from ..browser_agent.formatter import format_browser_dom_summary_policy

        return format_browser_dom_summary_policy(), "fast-command"

    if normalized == "eva browser text extraction policy":
        from ..browser_agent.formatter import format_browser_text_extraction_policy

        return format_browser_text_extraction_policy(), "fast-command"

    if normalized == "eva browser observation readiness":
        from ..browser_agent.formatter import format_browser_observation_readiness

        return format_browser_observation_readiness(), "fast-command"

    if normalized == "eva browser redaction policy":
        from ..browser_agent.formatter import format_browser_redaction_policy

        return format_browser_redaction_policy(), "fast-command"

    browser_domain_check = _after_prefix(original, ("eva browser domain check ",))
    if browser_domain_check:
        from ..browser_agent.formatter import format_browser_domain_check

        return format_browser_domain_check(browser_domain_check), "fast-command"

    browser_site_risk = _after_prefix(original, ("eva browser site risk ",))
    if browser_site_risk:
        from ..browser_agent.formatter import format_browser_site_risk

        return format_browser_site_risk(browser_site_risk), "fast-command"

    if normalized == "eva browser domain rules":
        from ..browser_agent.formatter import format_browser_domain_rules

        return format_browser_domain_rules(), "fast-command"

    if normalized == "eva browser sensitive sites":
        from ..browser_agent.formatter import format_browser_sensitive_sites

        return format_browser_sensitive_sites(), "fast-command"

    if normalized == "eva browser domain approvals":
        from ..browser_agent.formatter import format_browser_domain_approvals

        return format_browser_domain_approvals(), "fast-command"

    if normalized == "eva browser domain readiness":
        from ..browser_agent.formatter import format_browser_domain_readiness

        return format_browser_domain_readiness(), "fast-command"

    if normalized == "eva browser read only readiness":
        from ..browser_agent.formatter import format_browser_read_only_readiness

        return format_browser_read_only_readiness(), "fast-command"

    if normalized == "eva browser readiness proof":
        from ..browser_agent.formatter import format_browser_readiness_proof

        return format_browser_readiness_proof(), "fast-command"

    if normalized == "eva browser safety proof":
        from ..browser_agent.formatter import format_browser_safety_proof

        return format_browser_safety_proof(), "fast-command"

    if normalized == "eva browser readiness gaps":
        from ..browser_agent.formatter import format_browser_readiness_gaps

        return format_browser_readiness_gaps(), "fast-command"

    if normalized == "eva browser locked status":
        from ..browser_agent.formatter import format_browser_locked_status

        return format_browser_locked_status(), "fast-command"

    if normalized == "eva browser phase 13 proof":
        from ..browser_agent.formatter import format_browser_phase13_proof

        return format_browser_phase13_proof(), "fast-command"

    if normalized == "eva browser phase 13 status":
        from ..browser_agent.formatter import format_browser_phase13_status

        return format_browser_phase13_status(), "fast-command"

    if normalized == "eva browser phase 13 summary":
        from ..browser_agent.formatter import format_browser_phase13_summary

        return format_browser_phase13_summary(), "fast-command"

    if normalized == "eva browser phase 13 limits":
        from ..browser_agent.formatter import format_browser_phase13_limits

        return format_browser_phase13_limits(), "fast-command"

    if normalized == "eva browser phase 13 ready":
        from ..browser_agent.formatter import format_browser_phase13_ready

        return format_browser_phase13_ready(), "fast-command"

    if normalized == "eva browser phase 13 final proof":
        from ..browser_agent.formatter import format_browser_phase13_final_proof

        return format_browser_phase13_final_proof(), "fast-command"

    browser_dry_run = _after_prefix(original, ("eva browser action dry run ",))
    if browser_dry_run:
        from ..browser_agent.formatter import format_browser_action_dry_run

        return format_browser_action_dry_run(browser_dry_run), "fast-command"

    browser_action_plan = _after_prefix(original, ("eva browser action plan ",))
    if browser_action_plan:
        from ..browser_agent.formatter import format_browser_action_plan

        return format_browser_action_plan(browser_action_plan), "fast-command"

    browser_action_risk = _after_prefix(original, ("eva browser action risk ",))
    if browser_action_risk:
        from ..browser_agent.formatter import format_browser_action_risk

        return format_browser_action_risk(browser_action_risk), "fast-command"

    if normalized == "eva browser action approvals":
        from ..browser_agent.formatter import format_browser_action_approvals

        return format_browser_action_approvals(), "fast-command"

    if normalized == "eva browser dry run policy":
        from ..browser_agent.formatter import format_browser_dry_run_policy

        return format_browser_dry_run_policy(), "fast-command"

    if normalized == "eva browser action readiness":
        from ..browser_agent.formatter import format_browser_action_readiness

        return format_browser_action_readiness(), "fast-command"

    browser_action = _after_prefix(original, ("eva browser action safety ",))
    if browser_action:
        from ..browser_agent.formatter import format_browser_action_safety

        return format_browser_action_safety(browser_action), "fast-command"

    if normalized == "eva ux status":
        from ..core.ux_messages import format_ux_status

        return format_ux_status(), "fast-command"

    natural_route_goal = _after_prefix(original, ("eva natural route ", "eva authority decision "))
    if natural_route_goal:
        from ..authority.formatter import format_authority_decision
        from ..core.natural_router import route_natural_request

        route = route_natural_request(natural_route_goal.strip())
        decision = _authority_decision_from_natural_route(route)
        return "\n\n".join(
            [
                "Natural route preview",
                f"Intent: {route.intent}",
                f"Suggested command: {route.suggested_command or 'none'}",
                format_authority_decision(decision),
            ]
        ), "fast-command"

    if normalized in {"eva verify all", "eva all verifiers"}:
        return "Use `scripts/verify_eva_all.py` from the terminal to run the local verifier sweep. Eva did not start the sweep from chat.", "fast-command"

    execute = _handle_eva_v2_execute_command(normalized, original)
    if execute:
        return execute

    preview = _handle_eva_v2_preview_command(normalized, original)
    if preview:
        return preview

    if normalized in {"eva release status", "eva public status", "eva community status"}:
        from ..release.status import format_release_status

        return format_release_status(), "fast-command"

    if normalized == "eva planner status":
        from ..planner.status import format_planner_status

        return format_planner_status(), "fast-command"

    if normalized in {"eva plan templates", "eva planner templates"}:
        from ..planner.templates import format_plan_templates

        return format_plan_templates(), "fast-command"

    planner_validate_goal = _after_prefix(original, ("eva plan validate ", "eva planner validate "))
    if planner_validate_goal:
        from ..planner.decomposer import create_task_plan
        from ..planner.validation import format_plan_validation

        plan = create_task_plan(planner_validate_goal.strip())
        return format_plan_validation(plan), "fast-command"

    planner_review_goal = _after_prefix(original, ("eva plan review ", "eva planner review "))
    if planner_review_goal:
        from ..planner.critique import format_plan_review
        from ..planner.decomposer import create_task_plan

        plan = create_task_plan(planner_review_goal.strip())
        return format_plan_review(plan), "fast-command"

    planner_goal = _after_prefix(original, ("eva plan ", "eva planner plan ", "eva planner explain "))
    if planner_goal:
        from ..planner.decomposer import create_task_plan
        from ..planner.formatter import format_task_plan

        plan = create_task_plan(planner_goal.strip())
        return format_task_plan(plan), "fast-command"

    if normalized in {"eva agent framework status", "eva agents framework status"}:
        from ..agents.status import format_agent_framework_status

        return format_agent_framework_status(), "fast-command"

    if normalized in {"eva agents", "eva agents status", "eva agent list"}:
        from ..agents.registry import format_agents_status

        return format_agents_status(), "fast-command"

    if normalized == "eva agents matrix":
        from ..agents.registry import format_agent_capability_matrix

        return format_agent_capability_matrix(), "fast-command"

    agent_dry_run_goal = _after_prefix(original, ("eva agents dry run plan ",))
    if agent_dry_run_goal:
        from ..agents.delegation import format_agent_dry_run_for_goal

        return format_agent_dry_run_for_goal(agent_dry_run_goal.strip()), "fast-command"

    agent_review_goal = _after_prefix(original, ("eva agents review plan ", "eva agent team review "))
    if agent_review_goal:
        from ..agents.team_review import format_agent_team_review, review_plan_with_agent_team
        from ..planner.decomposer import create_task_plan

        plan = create_task_plan(agent_review_goal.strip())
        return format_agent_team_review(review_plan_with_agent_team(plan)), "fast-command"

    agent_coverage_goal = _after_prefix(original, ("eva agents coverage ",))
    if agent_coverage_goal:
        from ..agents.delegation import dry_run_plan_with_agents
        from ..agents.quality import evaluate_plan_agent_coverage, format_agent_coverage_report
        from ..planner.decomposer import create_task_plan

        plan = create_task_plan(agent_coverage_goal.strip())
        dry_run = dry_run_plan_with_agents(plan, include_quality=False)
        return format_agent_coverage_report(evaluate_plan_agent_coverage(plan, dry_run.responses)), "fast-command"

    agent_validate_goal = _after_prefix(original, ("eva agents validate plan ",))
    if agent_validate_goal:
        from ..agents.delegation import format_agent_dry_run_for_goal

        return format_agent_dry_run_for_goal(agent_validate_goal.strip()), "fast-command"

    agent_capabilities_name = _after_prefix(original, ("eva agent capabilities ",))
    if agent_capabilities_name:
        from ..agents.registry import format_agent_capabilities

        return format_agent_capabilities(agent_capabilities_name.strip()), "fast-command"

    agent_explain_name = _after_prefix(original, ("eva agent explain ",))
    if agent_explain_name:
        from ..agents.registry import get_agent

        agent = get_agent(agent_explain_name.strip())
        if not agent:
            return f"Agent explain\n\nAgent `{agent_explain_name.strip()}` was not found.\nUse `eva agent list` to view registered agents.", "fast-command"
        return agent.explain(), "fast-command"

    agent_detail_name = _after_prefix(original, ("eva agent ",))
    if agent_detail_name:
        from ..agents.registry import format_agent_detail

        return format_agent_detail(agent_detail_name.strip()), "fast-command"

    if normalized == "eva file status":
        from ..file_agent.status import format_file_agent_status

        return format_file_agent_status(), "fast-command"

    if normalized == "eva file approval status":
        from ..file_agent.approval_ledger import format_file_approval_ledger_status

        return format_file_approval_ledger_status(), "fast-command"

    if normalized == "eva file apply executor status":
        from ..file_agent.apply_executor import format_apply_executor_status

        return format_apply_executor_status(), "fast-command"

    if normalized == "eva file real apply status":
        from ..file_agent.real_apply_executor import format_real_apply_status

        return format_real_apply_status(), "fast-command"

    if normalized == "eva file real apply policy":
        from ..file_agent.real_apply import format_real_apply_policy

        return format_real_apply_policy(), "fast-command"

    real_eligibility_id = _after_prefix(original, ("eva file real apply eligibility ",))
    if real_eligibility_id:
        from ..file_agent.real_apply import evaluate_real_apply_eligibility, format_real_apply_eligibility

        return format_real_apply_eligibility(evaluate_real_apply_eligibility(real_eligibility_id.strip())), "fast-command"

    real_verify_id = _after_prefix(original, ("eva file approval real verify ", "eva file real create verify "))
    if real_verify_id:
        from ..file_agent.real_apply import format_real_apply_verification, verify_real_text_file_apply

        return format_real_apply_verification(verify_real_text_file_apply(real_verify_id.strip())), "fast-command"

    real_rollback_payload = _after_prefix(original, ("eva file approval real rollback ", "eva file real create rollback "))
    if real_rollback_payload:
        from ..file_agent.real_apply import format_real_apply_rollback, rollback_real_text_file_apply

        marker = " confirm rollback real create "
        if marker not in real_rollback_payload:
            approval_id = real_rollback_payload.strip()
            return f"Usage: eva file approval real rollback <approval_id> confirm rollback real create <approval_id>\nExact phrase required: confirm rollback real create {approval_id}", "fast-command"
        approval_id, phrase_id = real_rollback_payload.split(marker, 1)
        phrase = f"confirm rollback real create {phrase_id.strip()}"
        return format_real_apply_rollback(rollback_real_text_file_apply(approval_id.strip(), phrase)), "fast-command"

    real_create_payload = _after_prefix(original, ("eva file approval real create ",))
    if real_create_payload:
        from ..file_agent.real_apply import build_real_apply_request_from_approval, create_real_text_file_from_approval, format_real_apply_result
        from ..file_agent.real_apply_executor import format_real_create_request

        marker = " confirm real create "
        if marker not in real_create_payload:
            approval_id = real_create_payload.strip()
            request = build_real_apply_request_from_approval(approval_id, confirmation_phrase="")
            return format_real_create_request(request), "fast-command"
        approval_id, phrase_id = real_create_payload.split(marker, 1)
        phrase = f"confirm real create {phrase_id.strip()}"
        request = build_real_apply_request_from_approval(approval_id.strip(), confirmation_phrase=phrase)
        if not request.allowed:
            return format_real_create_request(request), "fast-command"
        return format_real_apply_result(create_real_text_file_from_approval(approval_id.strip(), phrase)), "fast-command"

    if normalized == "eva file apply sandbox policy":
        from ..file_agent.apply_executor import format_apply_executor_status

        return "\n".join(
            [
                "FileAgent sandbox apply policy",
                "",
                "Only approved FileAgent metadata can be applied inside the sandbox harness.",
                "Sandbox backups, verification, and rollback stay under ignored runtime storage.",
                "Real project/user files are not created, modified, backed up, restored, or applied.",
                "",
                format_apply_executor_status(),
            ]
        ), "fast-command"

    approval_create = _parse_between(original, "eva file approval request create ", " text ")
    if approval_create:
        from ..file_agent.approval_ledger import create_file_approval_request, format_file_approval_request
        from ..file_agent.draft_preview import create_file_draft_preview

        path_text, content = approval_create
        return format_file_approval_request(create_file_approval_request(create_file_draft_preview(path_text.strip(), content))), "fast-command"

    approval_append = _parse_between(original, "eva file approval request append ", " text ")
    if approval_append:
        from ..file_agent.approval_ledger import create_file_approval_request, format_file_approval_request
        from ..file_agent.draft_preview import create_append_preview

        path_text, content = approval_append
        return format_file_approval_request(create_file_approval_request(create_append_preview(path_text.strip(), content))), "fast-command"

    approval_replace = _parse_replace_with_prefix(original, "eva file approval request replace ")
    if approval_replace:
        from ..file_agent.approval_ledger import create_file_approval_request, format_file_approval_request
        from ..file_agent.draft_preview import create_text_replacement_preview

        path_text, old_text, new_text = approval_replace
        return format_file_approval_request(create_file_approval_request(create_text_replacement_preview(path_text.strip(), old_text, new_text))), "fast-command"

    if normalized == "eva file approvals pending":
        from ..file_agent.approval_ledger import format_file_approval_list, list_file_approval_requests

        return format_file_approval_list(list_file_approval_requests(status="pending")), "fast-command"

    if normalized == "eva file approvals expire":
        from ..file_agent.approval_ledger import expire_old_file_approvals, format_file_approval_ledger_status

        count = expire_old_file_approvals()
        return f"Expired {count} old FileAgent approval request(s).\n\n{format_file_approval_ledger_status()}", "fast-command"

    approval_events_id = _after_prefix(original, ("eva file approval events ",))
    if approval_events_id:
        from ..file_agent.approval_ledger import format_file_approval_events

        return format_file_approval_events(approval_events_id.strip()), "fast-command"

    sandbox_apply_id = _after_prefix(original, ("eva file approval sandbox apply ",))
    if sandbox_apply_id:
        from ..file_agent.apply_executor import apply_draft_to_sandbox, build_apply_request_from_approval, format_apply_result, verify_sandbox_apply

        request = build_apply_request_from_approval(sandbox_apply_id.strip())
        result = apply_draft_to_sandbox(request)
        verification = verify_sandbox_apply(request, result) if result.ok else None
        text = format_apply_result(result)
        if verification is not None:
            from ..file_agent.apply_executor import format_verification_result

            text = f"{text}\n\n{format_verification_result(verification)}"
        return text, "fast-command"

    sandbox_verify_id = _after_prefix(original, ("eva file approval sandbox verify ",))
    if sandbox_verify_id:
        from ..file_agent.apply_executor import build_apply_request_from_approval, format_verification_result, verify_sandbox_apply

        request = build_apply_request_from_approval(sandbox_verify_id.strip())
        return format_verification_result(verify_sandbox_apply(request)), "fast-command"

    sandbox_rollback_id = _after_prefix(original, ("eva file approval sandbox rollback ",))
    if sandbox_rollback_id:
        from ..file_agent.apply_executor import apply_draft_to_sandbox, build_apply_request_from_approval, format_rollback_result, rollback_sandbox_apply

        request = build_apply_request_from_approval(sandbox_rollback_id.strip())
        result = apply_draft_to_sandbox(request)
        return format_rollback_result(rollback_sandbox_apply(result)), "fast-command"

    approval_approve_payload = _after_prefix(original, ("eva file approval approve ",))
    if approval_approve_payload:
        from ..file_agent.approval_ledger import approve_file_approval_request, format_file_approval_request

        marker = " confirm "
        if marker not in approval_approve_payload:
            return "Usage: eva file approval approve <approval_id> confirm <exact confirmation phrase>\nNo file was created, modified, backed up, restored, or applied.", "fast-command"
        approval_id, phrase = approval_approve_payload.split(marker, 1)
        return format_file_approval_request(approve_file_approval_request(approval_id.strip(), phrase.strip())), "fast-command"

    approval_deny_id = _after_prefix(original, ("eva file approval deny ",))
    if approval_deny_id:
        from ..file_agent.approval_ledger import deny_file_approval_request, format_file_approval_request

        return format_file_approval_request(deny_file_approval_request(approval_deny_id.strip())), "fast-command"

    approval_cancel_id = _after_prefix(original, ("eva file approval cancel ",))
    if approval_cancel_id:
        from ..file_agent.approval_ledger import cancel_file_approval_request, format_file_approval_request

        return format_file_approval_request(cancel_file_approval_request(approval_cancel_id.strip())), "fast-command"

    approval_view_id = _after_prefix(original, ("eva file approval ",))
    if approval_view_id and not approval_view_id.lower().startswith(("request ", "approve ", "deny ", "cancel ", "events ", "sandbox ", "status")):
        from ..file_agent.approval_ledger import format_file_approval_request, get_file_approval_request

        return format_file_approval_request(get_file_approval_request(approval_view_id.strip())), "fast-command"

    if normalized == "eva file apply policy":
        from ..file_agent.write_safety import format_write_policy

        return format_write_policy(), "fast-command"

    apply_create = _parse_between(original, "eva file apply readiness create ", " text ")
    if apply_create:
        from ..file_agent.draft_preview import create_file_draft_preview
        from ..file_agent.write_safety import format_apply_readiness_report

        path_text, content = apply_create
        return format_apply_readiness_report(create_file_draft_preview(path_text.strip(), content)), "fast-command"

    apply_append = _parse_between(original, "eva file apply readiness append ", " text ")
    if apply_append:
        from ..file_agent.draft_preview import create_append_preview
        from ..file_agent.write_safety import format_apply_readiness_report

        path_text, content = apply_append
        return format_apply_readiness_report(create_append_preview(path_text.strip(), content)), "fast-command"

    apply_replace = _parse_replace_with_prefix(original, "eva file apply readiness replace ")
    if apply_replace:
        from ..file_agent.draft_preview import create_text_replacement_preview
        from ..file_agent.write_safety import format_apply_readiness_report

        path_text, old_text, new_text = apply_replace
        return format_apply_readiness_report(create_text_replacement_preview(path_text.strip(), old_text, new_text)), "fast-command"

    write_safety_path = _after_prefix(original, ("eva file write safety ",))
    if write_safety_path:
        from ..file_agent.write_safety import format_write_policy

        return format_write_policy(write_safety_path.strip()), "fast-command"

    rollback_path = _after_prefix(original, ("eva file rollback plan ",))
    if rollback_path:
        from ..file_agent.draft_preview import create_append_preview
        from ..file_agent.write_safety import build_rollback_plan, format_rollback_plan

        return format_rollback_plan(build_rollback_plan(create_append_preview(rollback_path.strip(), "future change placeholder"))), "fast-command"

    draft_create = _parse_between(original, "eva file draft create ", " text ")
    if draft_create:
        from ..file_agent.draft_preview import create_file_draft_preview, format_draft_preview

        path_text, content = draft_create
        return format_draft_preview(create_file_draft_preview(path_text.strip(), content)), "fast-command"

    draft_append = _parse_between(original, "eva file draft append ", " text ")
    if draft_append:
        from ..file_agent.draft_preview import create_append_preview, format_draft_preview

        path_text, content = draft_append
        return format_draft_preview(create_append_preview(path_text.strip(), content)), "fast-command"

    draft_replace = _parse_replace_draft(original)
    if draft_replace:
        from ..file_agent.draft_preview import create_text_replacement_preview, format_draft_preview

        path_text, old_text, new_text = draft_replace
        return format_draft_preview(create_text_replacement_preview(path_text.strip(), old_text, new_text)), "fast-command"

    draft_diff = _parse_between(original, "eva file draft diff ", " text ")
    if draft_diff:
        from ..file_agent.draft_preview import create_unified_diff_preview, format_draft_preview

        path_text, proposed = draft_diff
        return format_draft_preview(create_unified_diff_preview(path_text.strip(), proposed)), "fast-command"

    readme_topic = _after_prefix(original, ("eva draft readme section ",))
    if readme_topic:
        from ..file_agent.draft_generators import draft_readme_section

        return draft_readme_section(readme_topic.strip()), "fast-command"

    if normalized == "eva draft project summary":
        from ..file_agent.draft_generators import draft_project_summary
        from ..file_agent.project_inventory import build_project_inventory

        return draft_project_summary(build_project_inventory(".")), "fast-command"

    report_title = _after_prefix(original, ("eva draft report outline ",))
    if report_title:
        from ..file_agent.draft_generators import draft_report_outline

        return draft_report_outline(report_title.strip()), "fast-command"

    if normalized == "eva draft project todo":
        from ..file_agent.draft_generators import draft_todo_list_from_project_inventory
        from ..file_agent.project_inventory import build_project_inventory

        return draft_todo_list_from_project_inventory(build_project_inventory(".")), "fast-command"

    file_understand_path = _after_prefix(original, ("eva file understand ", "eva file summarize ", "eva file summarise "))
    if file_understand_path:
        from ..file_agent.formatter import format_file_understanding
        from ..file_agent.inspector import understand_file

        return format_file_understanding(understand_file(file_understand_path.strip())), "fast-command"

    project_inventory_path = _after_prefix(original, ("eva project inventory ",))
    if normalized == "eva project inventory" or project_inventory_path:
        from ..file_agent.formatter import format_project_inventory_report
        from ..file_agent.project_inventory import build_project_inventory

        return format_project_inventory_report(build_project_inventory(project_inventory_path.strip() if project_inventory_path else ".")), "fast-command"

    project_explain_path = _after_prefix(original, ("eva project explain ",))
    if normalized == "eva project explain" or project_explain_path:
        from ..file_agent.formatter import format_project_explanation
        from ..file_agent.project_inventory import build_project_inventory

        return format_project_explanation(build_project_inventory(project_explain_path.strip() if project_explain_path else ".")), "fast-command"

    project_missing_path = _after_prefix(original, ("eva project missing ",))
    if normalized == "eva project missing" or project_missing_path:
        from ..file_agent.formatter import format_project_missing
        from ..file_agent.project_inventory import build_project_inventory

        return format_project_missing(build_project_inventory(project_missing_path.strip() if project_missing_path else ".")), "fast-command"

    project_key_files_path = _after_prefix(original, ("eva project key files ",))
    if normalized == "eva project key files" or project_key_files_path:
        from ..file_agent.formatter import format_project_key_files
        from ..file_agent.project_inventory import build_project_inventory

        return format_project_key_files(build_project_inventory(project_key_files_path.strip() if project_key_files_path else ".")), "fast-command"

    project_dependencies_path = _after_prefix(original, ("eva project dependencies ",))
    if normalized == "eva project dependencies" or project_dependencies_path:
        from ..file_agent.formatter import format_project_dependencies
        from ..file_agent.project_inventory import build_project_inventory

        return format_project_dependencies(build_project_inventory(project_dependencies_path.strip() if project_dependencies_path else ".")), "fast-command"

    file_inspect_path = _after_prefix(original, ("eva file inspect ", "eva file explain "))
    if file_inspect_path:
        from ..file_agent.formatter import format_path_inspection
        from ..file_agent.inspector import inspect_path

        return format_path_inspection(inspect_path(file_inspect_path.strip())), "fast-command"

    folder_inspect_path = _after_prefix(original, ("eva folder inspect ",))
    if folder_inspect_path:
        from ..file_agent.formatter import format_folder_inspection
        from ..file_agent.inspector import inspect_folder

        return format_folder_inspection(inspect_folder(folder_inspect_path.strip())), "fast-command"

    file_search_query = _after_prefix(original, ("eva file search ",))
    if file_search_query:
        from ..file_agent.formatter import format_file_search_results
        from ..file_agent.search import search_files_by_name

        return format_file_search_results(search_files_by_name(file_search_query.strip())), "fast-command"

    file_preview_path = _after_prefix(original, ("eva file preview ",))
    if file_preview_path:
        from ..file_agent.formatter import format_text_preview
        from ..file_agent.inspector import preview_text_file

        return format_text_preview(preview_text_file(file_preview_path.strip())), "fast-command"

    project_structure_path = _after_prefix(original, ("eva project structure ",))
    if normalized == "eva project structure" or project_structure_path:
        from ..file_agent.formatter import format_project_structure
        from ..file_agent.inspector import explain_project_structure

        return format_project_structure(explain_project_structure(project_structure_path.strip() if project_structure_path else ".")), "fast-command"

    if normalized == "eva public checklist":
        from ..release.status import format_public_release_checklist

        return format_public_release_checklist(), "fast-command"

    if normalized in {"eva public hardening status", "eva public release audit"}:
        from ..release.hardening import format_public_release_hardening_status

        return format_public_release_hardening_status(), "fast-command"

    if normalized == "eva public ready check":
        from ..release.hardening import format_public_ready_check

        return format_public_ready_check(), "fast-command"

    if normalized == "eva capabilities":
        from ..capabilities.registry import format_capability_summary

        return format_capability_summary(), "fast-command"

    if normalized == "eva capabilities safe":
        from ..capabilities.registry import format_capability_summary

        return format_capability_summary(safe_only=True), "fast-command"

    if normalized == "eva capabilities experimental":
        from ..capabilities.registry import format_capability_summary

        return format_capability_summary(experimental_only=True), "fast-command"

    if normalized in {"eva capabilities matrix", "eva capability permissions"}:
        from ..capabilities.permissions import format_capability_permission_matrix

        return format_capability_permission_matrix(), "fast-command"

    if normalized == "eva capability providers":
        from ..capabilities.registry import format_capability_providers

        return format_capability_providers(), "fast-command"

    capability_permission_id = _after_prefix(original, ("eva capability permission ",))
    if capability_permission_id:
        from ..capabilities.permissions import format_capability_permission_detail

        return format_capability_permission_detail(capability_permission_id.strip()), "fast-command"

    capability_schema_id = _after_prefix(original, ("eva capability schema ", "eva tool schema preview "))
    if capability_schema_id:
        from ..capabilities.tool_schemas import format_tool_schema_preview

        return format_tool_schema_preview(capability_schema_id.strip()), "fast-command"

    if normalized == "eva tool schemas":
        from ..capabilities.tool_schemas import format_tool_schema_catalog

        return format_tool_schema_catalog(), "fast-command"

    if normalized == "eva threat model status":
        from ..capabilities.permissions import format_threat_model_status

        return format_threat_model_status(), "fast-command"

    if normalized == "eva capability resource matrix":
        from ..capabilities.resource_mapping import format_capability_resource_matrix

        return format_capability_resource_matrix(), "fast-command"

    if normalized == "eva capabilities available":
        from ..capabilities.resource_mapping import format_capability_resource_matrix

        return format_capability_resource_matrix("available"), "fast-command"

    if normalized in {"eva capabilities preview only", "eva capabilities preview-only"}:
        from ..capabilities.resource_mapping import format_capability_resource_matrix

        return format_capability_resource_matrix("preview_only"), "fast-command"

    if normalized == "eva capabilities blocked":
        from ..capabilities.resource_mapping import format_capability_resource_matrix

        return format_capability_resource_matrix("blocked"), "fast-command"

    plan_goal = _after_prefix(original, ("eva capability plan resources ",))
    if plan_goal:
        from ..capabilities.resource_mapping import format_capability_plan_resources

        return format_capability_plan_resources(plan_goal.strip()), "fast-command"

    resolve_capability_id = _after_prefix(original, ("eva capability resolve ",))
    if resolve_capability_id:
        from ..capabilities.resource_mapping import format_capability_resolution

        return format_capability_resolution(resolve_capability_id.strip()), "fast-command"

    capability_resources_id = _after_prefix(original, ("eva capability resources ",))
    if capability_resources_id:
        from ..capabilities.resource_mapping import format_capability_resources

        return format_capability_resources(capability_resources_id.strip()), "fast-command"

    resource_capabilities_id = _after_prefix(original, ("eva resource capabilities ",))
    if resource_capabilities_id:
        from ..capabilities.resource_mapping import format_resource_capabilities

        return format_resource_capabilities(resource_capabilities_id.strip()), "fast-command"

    capability_id = _after_prefix(original, ("eva capability ",))
    if capability_id:
        from ..capabilities.registry import format_capability_detail

        return format_capability_detail(None, capability_id.strip()), "fast-command"

    if normalized == "eva demo scenarios":
        from ..demo.runner import format_demo_scenarios

        return format_demo_scenarios(), "fast-command"

    demo_run = _after_prefix(original, ("eva demo run ",))
    if demo_run:
        from ..demo.runner import format_demo_run

        return format_demo_run(demo_run), "fast-command"

    safety_request = _after_prefix(original, ("eva safety test ",))
    if safety_request:
        from ..demo.safety_simulator import simulate_public_safety

        return simulate_public_safety(safety_request).as_text(), "fast-command"

    if normalized in {"eva doctor", "eva doctor public"}:
        from ..release.doctor import format_public_doctor

        return format_public_doctor(), "fast-command"

    resource_command = _handle_resource_registry_command(normalized, original)
    if resource_command:
        return resource_command

    from ..permissions.confirmation import handle_confirmation_command, handle_pending_action_status_command

    pending_status = handle_pending_action_status_command(original)
    if pending_status:
        return pending_status, "fast-command"

    pending_confirmation = handle_confirmation_command(original)
    if pending_confirmation:
        return pending_confirmation, "fast-command"

    if normalized in {"where did you get that answer from", "where did you get that from", "what was your source", "source for that", "did you search that"}:
        return answer_provenance_status(session_context), "fast-command"

    if re.match(r"^agent mode:\s*say hello\b", original, flags=re.IGNORECASE) and "one sentence" in normalized:
        return "Hello, Ankit.", "fast-command"

    if normalized in {"eva v2 status", "eva runtime status", "eva v2 runtime status"}:
        return _format_eva_v2_status(), "fast-command"

    if normalized in {"agents status", "agent registry status", "specialist agents status"}:
        return _format_agents_status(), "fast-command"

    if normalized in {"guardrails status", "guardrail status", "safety guardrails status"}:
        return _format_guardrails_status(), "fast-command"

    if normalized in {"vector memory status", "vectors status", "embedding memory status"}:
        return _format_vector_memory_status(), "fast-command"

    if normalized in {"traces status", "trace status", "last trace status"}:
        return _format_traces_status(), "fast-command"

    if normalized in {"traces list", "list traces", "recent traces"}:
        return _format_traces_list(), "fast-command"

    if normalized in {"evals status", "eval status", "run evals", "evals run"}:
        return _format_evals_status(), "fast-command"

    if normalized in {"activation status", "profile status", "capability activation status"}:
        return _format_activation_status(), "fast-command"

    if normalized in {"exercise run", "run exercise", "friction report", "exercise status"}:
        return _format_exercise_status(), "fast-command"

    trace_show_match = re.match(r"^(?:traces show|show trace)\s+(.+)$", original, flags=re.IGNORECASE)
    if trace_show_match:
        return _format_trace_show(trace_show_match.group(1).strip()), "fast-command"

    if normalized in {"automation adapters status", "automation adapter status", "browser automation status", "desktop automation status"}:
        return _format_automation_adapters_status(), "fast-command"

    if normalized in {"agent status raw", "agentic status raw", "agent mode status raw"}:
        return _format_agent_status(raw=True), "fast-command"

    if normalized in {"agent status", "agentic status", "agent mode status", "agent capabilities"}:
        return _format_agent_status(), "fast-command"

    if normalized in {"tools status raw", "tool status raw", "tool registry raw"}:
        return _format_tools_status(tools, raw=True), "fast-command"

    if normalized in {"tools status", "tool status", "tool registry status", "what tools do you have", "what tools are available"}:
        return _format_tools_status(tools), "fast-command"

    if normalized in {"permissions status raw", "permission status raw", "safety permissions raw"}:
        return _format_permissions_status(raw=True), "fast-command"

    if normalized in {"permissions status", "permission status", "safety permissions", "what are your permissions status", "what is your permissions status"}:
        return _format_permissions_status(), "fast-command"

    if normalized in {"code status raw", "code intelligence status raw"}:
        try:
            return _format_code_status(tools.run("code_status"), raw=True), "code-tool"
        except Exception as exc:
            return _json_debug({"ok": False, "error": str(exc)}), "code-tool"

    if normalized in {"research status raw"}:
        try:
            return _format_research_status(tools.run("research_status"), raw=True), "research-tool"
        except Exception as exc:
            return _json_debug({"ok": False, "error": str(exc)}), "research-tool"

    if normalized == "research memory help":
        from ..research_memory.help import format_research_memory_help

        return format_research_memory_help(), "fast-command"

    if normalized == "research memory commands":
        from ..research_memory.help import format_research_memory_command_reference

        return format_research_memory_command_reference(), "fast-command"

    if normalized == "research memory examples":
        from ..research_memory.help import format_research_memory_examples

        return format_research_memory_examples(), "fast-command"

    if normalized == "research memory safety":
        from ..research_memory.help import format_research_memory_safety

        return format_research_memory_safety(), "fast-command"

    if normalized == "research memory phase summary":
        from ..research_memory.help import format_research_memory_phase_summary

        return format_research_memory_phase_summary(), "fast-command"

    if normalized == "research memory import demo":
        from ..research_memory.demo_pack import format_demo_import_result, import_demo_research_pack

        return format_demo_import_result(import_demo_research_pack()), "fast-command"

    if normalized in {"research memory status", "research memory v2 status"}:
        from ..research_memory.status import format_research_memory_status

        return format_research_memory_status(), "fast-command"

    if normalized == "research memory stats":
        from ..research_memory.io import format_research_memory_stats

        return format_research_memory_stats(), "fast-command"

    if normalized == "research memory vector status":
        from ..research_memory.vector_index import format_vector_status

        return format_vector_status(), "fast-command"

    if normalized == "research memory vector index preview":
        from ..research_memory.vector_index import format_vector_index_preview

        return format_vector_index_preview(), "fast-command"

    if normalized == "research memory retrieval status":
        from ..research_memory.retrieval import retrieval_status

        return retrieval_status(), "fast-command"

    if normalized == "research memory ranking status":
        from ..research_memory.ranking import format_ranking_status

        return format_ranking_status(), "fast-command"

    if normalized == "research memory recall stats":
        from ..research_memory.ranking import format_recall_stats

        return format_recall_stats(), "fast-command"

    if normalized == "research memory promote candidates":
        from ..research_memory.ranking import format_promotion_candidates

        return format_promotion_candidates(), "fast-command"

    if normalized == "research memory review memory":
        from ..research_memory.ranking import format_memory_review

        return format_memory_review(), "fast-command"

    retrieval_plan = _after_prefix(original, ("research memory retrieval plan ",))
    if retrieval_plan:
        from ..research_memory.retrieval import explain_retrieval_plan

        return explain_retrieval_plan(retrieval_plan), "fast-command"

    retrieval_match = re.match(
        r"^\s*research memory retrieve\s+(.+?)(?:\s+(topic|tag|source)\s+(.+))?\s*$",
        original,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if retrieval_match:
        from ..research_memory.retrieval import format_retrieval_results, retrieve_research

        query = retrieval_match.group(1).strip()
        filter_kind = (retrieval_match.group(2) or "").strip().lower()
        filter_value = (retrieval_match.group(3) or "").strip()
        kwargs: dict[str, str] = {}
        if filter_kind == "topic":
            kwargs["topic"] = filter_value
        elif filter_kind == "tag":
            kwargs["tag"] = filter_value
        elif filter_kind == "source":
            kwargs["source_type"] = filter_value
        return format_retrieval_results(retrieve_research(query, **kwargs)), "fast-command"

    vector_search_match = re.match(
        r"^\s*research memory (?:vector|semantic) search\s+(.+?)(?:\s+(topic|tag)\s+(.+))?\s*$",
        original,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if vector_search_match:
        from ..research_memory.vector_index import format_vector_search

        query = vector_search_match.group(1).strip()
        filter_kind = (vector_search_match.group(2) or "").strip().lower()
        filter_value = (vector_search_match.group(3) or "").strip()
        kwargs: dict[str, str] = {}
        if filter_kind == "topic":
            kwargs["topic"] = filter_value
        elif filter_kind == "tag":
            kwargs["tag"] = filter_value
        return format_vector_search(query, **kwargs), "fast-command"

    if normalized == "research memory tags":
        from ..research_memory.quality import format_research_tags

        return format_research_tags(), "fast-command"

    if normalized in {"research memory duplicates", "research memory merge duplicates preview"}:
        from ..research_memory.quality import format_duplicates_preview

        return format_duplicates_preview(), "fast-command"

    if normalized == "research memory quality":
        from ..research_memory.quality import format_quality_report

        return format_quality_report(), "fast-command"

    if normalized == "research memory export":
        from ..research_memory.io import export_research_memory, format_export_result

        return format_export_result(export_research_memory()), "fast-command"

    export_topic = _after_prefix(original, ("research memory export topic ",))
    if export_topic:
        from ..research_memory.io import export_research_memory, format_export_result

        return format_export_result(export_research_memory(topic=export_topic)), "fast-command"

    import_note_match = re.match(
        r"^\s*research memory import note\s+topic\s+(.+?)\s+title\s+(.+?)\s+tags\s+(.+?)\s+text\s+(.+)$",
        original,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if import_note_match:
        from ..research_memory.io import format_import_result, import_research_note

        return (
            format_import_result(
                import_research_note(
                    import_note_match.group(1).strip(),
                    import_note_match.group(2).strip(),
                    import_note_match.group(4).strip(),
                    tags=import_note_match.group(3).strip(),
                )
            ),
            "fast-command",
        )

    import_note_match = re.match(
        r"^\s*research memory import note\s+topic\s+(.+?)\s+title\s+(.+?)\s+text\s+(.+)$",
        original,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if import_note_match:
        from ..research_memory.io import format_import_result, import_research_note

        return (
            format_import_result(
                import_research_note(
                    import_note_match.group(1).strip(),
                    import_note_match.group(2).strip(),
                    import_note_match.group(3).strip(),
                )
            ),
            "fast-command",
        )

    delete_item_id = _after_prefix(original, ("research memory delete item ",))
    if delete_item_id:
        from ..research_memory.io import delete_research_memory_item

        _ok, message = delete_research_memory_item(delete_item_id)
        return message, "fast-command"

    if normalized.startswith("research memory clear all"):
        return "Research memory clear all is not supported in this phase. No research memory was cleared.", "fast-command"

    clear_topic_match = re.match(r"^\s*research memory clear topic\s+(.+?)(?:\s+(confirm))?\s*$", original, flags=re.IGNORECASE | re.DOTALL)
    if clear_topic_match:
        from ..research_memory.io import clear_research_memory_topic

        return clear_research_memory_topic(clear_topic_match.group(1).strip(), confirmed=bool(clear_topic_match.group(2))), "fast-command"

    if normalized in {"recent research", "recent research memory", "research memory recent"}:
        from ..research_memory.status import format_recent_research

        return format_recent_research(limit=10), "fast-command"

    if normalized in {"research topics", "research memory topics"}:
        from ..research_memory.status import format_research_topics

        return format_research_topics(limit=50), "fast-command"

    filtered_search_match = re.match(
        r"^\s*(?:research memory search|search research memory)\s+(.+?)\s+(topic|tag|source)\s+(.+)$",
        original,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if filtered_search_match:
        from ..research_memory.status import format_research_search

        query = filtered_search_match.group(1).strip()
        filter_type = filtered_search_match.group(2).strip().lower()
        filter_value = filtered_search_match.group(3).strip()
        kwargs = {
            "topic": filter_value if filter_type == "topic" else None,
            "tag": filter_value if filter_type == "tag" else None,
            "source_type": filter_value if filter_type == "source" else None,
        }
        return format_research_search(query, **kwargs), "fast-command"

    research_memory_query = _after_prefix(original, ("research memory search ", "search research memory "))
    if research_memory_query:
        from ..research_memory.status import format_research_search

        return format_research_search(research_memory_query), "fast-command"

    research_topic = _after_prefix(original, ("research memory topic ", "research topic ", "summarize research topic ", "summarise research topic "))
    if research_topic:
        from ..research_memory.status import format_research_topic_summary

        return format_research_topic_summary(research_topic), "fast-command"

    save_research_memory_match = re.match(
        r"^\s*(?:save research note|remember research)\s+([^:]+):\s*(.+)$",
        original,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if save_research_memory_match:
        return _save_research_memory_note(save_research_memory_match.group(1), save_research_memory_match.group(2)), "fast-command"

    tagged_save_research_match = re.match(
        r"^\s*research memory save\s+topic\s+(.+?)\s+tags\s+(.+?)\s+note\s+(.+)$",
        original,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if tagged_save_research_match:
        return (
            _save_research_memory_note(
                tagged_save_research_match.group(1),
                tagged_save_research_match.group(3),
                tags=tagged_save_research_match.group(2),
            ),
            "fast-command",
        )

    save_research_memory_match = re.match(
        r"^\s*research memory save\s+topic\s+(.+?)\s+note\s+(.+)$",
        original,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if save_research_memory_match:
        return _save_research_memory_note(save_research_memory_match.group(1), save_research_memory_match.group(2)), "fast-command"

    if normalized in {"copy current url", "copy current link", "copy this url", "copy this page url"}:
        return _run_tool(tools, "chrome_copy_current_url", session_context)

    save_page_match = re.match(
        r"^\s*(?:save this page to research topic|save current page to research topic|save this page to|save current page to|research this page as)\s+(.+)$",
        original,
        flags=re.IGNORECASE,
    )
    if save_page_match:
        return _run_tool(tools, "browser_save_page_to_research", session_context, topic=save_page_match.group(1).strip())

    if normalized in {"browser status", "chrome status", "browser agent status"}:
        return _run_tool(tools, "browser_status", session_context)

    if normalized in {"what page am i on", "what website is open", "current browser page", "current page", "what browser page is open"}:
        return _run_tool(tools, "browser_current_page", session_context)

    if normalized in {"summarize this page", "summarise this page", "summarize current page", "summarise current page", "read this page"}:
        return _run_tool(tools, "browser_summarize_page", session_context)

    if normalized in {"extract links from this page", "extract links", "links on this page", "show links on this page"}:
        return _run_tool(tools, "browser_extract_links", session_context)

    if normalized in {"save this page", "save current page"}:
        return "Which research topic should I save this page under?", "fast-command"

    if normalized in {"open new tab", "new tab"}:
        return _run_tool(tools, "browser_open_url", session_context, url="https://www.google.com")

    browser_search = _after_prefix(original, ("browser search for ", "search browser for ", "chrome search for "))
    if browser_search:
        return _run_tool(tools, "browser_search", session_context, query=browser_search)

    project_note = _project_note_payload(original)
    if project_note:
        if memory is not None and hasattr(memory, "remember_fact"):
            try:
                memory.remember_fact("project_note", project_note, namespace="project", source="user")
                if session_id and hasattr(memory, "log_event"):
                    memory.log_event(session_id, "project_memory_saved", {"key": "project_note", "value": project_note})
            except Exception:
                return "I tried to save that project note locally, but SQLite rejected it.", "fast-command"
            return f"Saved as a local Eva project note: {project_note}", "fast-command"
        return "I can save project notes once the local SQLite memory store is available in this route.", "fast-command"

    remembered = _remember_payload(original)
    if remembered:
        if _looks_like_identity_joke(original, remembered):
            return "Got it, joke noted. I’m not changing your name from Ankit.", "fast-command"
        if memory is not None and hasattr(memory, "remember_fact"):
            try:
                memory.remember_fact("user_note", remembered, source="user")
                if session_id and hasattr(memory, "log_event"):
                    memory.log_event(session_id, "memory_fact_saved", {"key": "user_note", "value": remembered})
            except Exception:
                return "I tried to save that locally, but SQLite rejected it. I did not send it anywhere.", "fast-command"
            return f"Got it. I saved that locally: {remembered}", "fast-command"
        return "I can remember that once the local SQLite memory store is available in this route.", "fast-command"

    if _is_about_me_command(normalized):
        facts = _memory_facts_summary(memory)
        return (USER_PROFILE_SUMMARY + (f"\n{facts}" if facts else "")), "fast-command"

    if _is_local_memory_question(normalized):
        return LOCAL_MEMORY_SUMMARY, "fast-command"

    if normalized in {"user model", "what have you learned about me", "durable memory", "learned memory", "show user model"}:
        return _user_model_summary(memory), "fast-command"

    if normalized in {"consolidate memory", "consolidate user model", "learn from history"}:
        return _consolidate_user_model(memory, session_id), "fast-command"

    if normalized in {"situation", "perception status", "what am i working on", "what am i doing", "situational context"}:
        return _situation_report(), "fast-command"

    if normalized in {"queue status", "task queue status", "durable queue status"}:
        return _durable_queue_status(), "fast-command"

    if normalized in {"queue recover", "recover tasks", "resume tasks"}:
        return _durable_queue_recover(), "fast-command"

    enqueue_text = _after_prefix(original, ("enqueue task ", "queue task ", "add task ", "enqueue "))
    if enqueue_text:
        return _durable_queue_enqueue(enqueue_text), "fast-command"

    if normalized in {"proactivity status", "rules", "rules list", "list rules", "proactive rules"}:
        return _proactivity_rules(), "fast-command"

    if normalized in {"check triggers", "proactivity tick", "run rules", "check rules"}:
        return _proactivity_tick(), "fast-command"

    if normalized in {"notifications", "my notifications", "what did i miss"}:
        return _proactivity_notifications(), "fast-command"

    if normalized in {"skills status", "skill status", "agent skills"}:
        from ..agent.skills import skill_status

        return json.dumps(skill_status(), indent=2), "fast-command"

    if normalized in {"task status", "last task status"}:
        task = (session_context or {}).get("last_agent_task") if isinstance(session_context, dict) else None
        if task:
            return json.dumps(task, indent=2), "fast-command"
        return "No agent task is active yet.", "fast-command"

    if normalized in {"cancel task", "cancel agent task"}:
        if isinstance(session_context, dict):
            session_context["active_task_status"] = "cancelled"
        return "Cancelled the current tracked task state. Any already-finished desktop action was not undone.", "fast-command"

    if normalized in {"resume task", "resume agent task"}:
        return "There is no paused task runner to resume yet. Say the goal again and I’ll start a fresh bounded task.", "fast-command"

    if any(command in normalized for command in ABOUT_EVA_COMMANDS):
        return EVA_IDENTITY_SUMMARY, "fast-command"

    if normalized in {"status", "system status", "laptop status", "pc status", "computer status"}:
        status = tools.run("system_status")
        return (
            f"Laptop is reachable. OS: {status['os_name']}. Shell: {status['shell']}.",
            "fast-command",
        )

    if normalized in {"what can you do", "help", "commands", "capabilities"}:
        return CAPABILITY_SUMMARY, "fast-command"

    if normalized in {"llm status raw", "model status raw", "cloud status raw"}:
        return format_llm_status(raw=True), "fast-command"

    if normalized in {"llm status", "model status", "cloud status"}:
        return format_llm_status(), "fast-command"

    if normalized in {
        "what part of you is broken",
        "what is broken in you",
        "what is working in you",
        "diagnose yourself",
        "system health",
        "health check",
        "full diagnostics",
        "diagnose your brain",
    }:
        return get_eva_health_summary()["text"], "fast-command"

    if normalized in {"use auto brain", "use automatic brain", "use default brain", "switch to auto", "switch to auto brain"}:
        return _set_llm_mode_reply("auto"), "fast-command"

    if normalized in {"use nvidia nim", "use nim", "use nvidia", "switch to nvidia nim", "switch to nim", "use nvidia nim brain"}:
        return _set_llm_mode_reply("nvidia_nim"), "fast-command"

    if normalized in {"use gemini", "use gemini api", "switch to gemini", "switch to gemini api", "use gemini brain"}:
        return _set_llm_mode_reply("gemini"), "fast-command"

    if normalized in {"use openrouter", "use open router", "switch to openrouter", "switch to open router", "use openrouter brain"}:
        return _set_llm_mode_reply("openrouter"), "fast-command"

    if normalized in {"use groq", "switch to groq", "use groq brain"}:
        return _set_llm_mode_reply("groq"), "fast-command"

    if normalized in {"use clod", "use clōd", "switch to clod", "switch to clōd", "use clod brain", "use clōd brain"}:
        return _set_llm_mode_reply("clod"), "fast-command"

    if normalized in {"use qwen", "switch to qwen", "use qwen brain", "use qwen for fallback"}:
        return _set_llm_mode_reply("qwen"), "fast-command"

    if normalized in {"use llama", "switch to llama", "use llama brain", "use llama for fallback"}:
        return _set_llm_mode_reply("llama"), "fast-command"

    if normalized in {"use local brain", "use local only", "switch to local brain", "switch to local only", "local only"}:
        return _set_llm_mode_reply("local"), "fast-command"

    if normalized in {"web status", "search status", "tavily status"}:
        status = tavily_status()
        return json.dumps(status, indent=2), "fast-command"

    if normalized == "code index status":
        from ..code_index.status import code_index_status

        return _format_code_index_status(code_index_status()), "fast-command"

    if normalized in {"code index refresh", "refresh code index"}:
        from ..code_index.status import refresh_code_index

        return _format_code_index_refresh(refresh_code_index()), "fast-command"

    code_index_query = _after_prefix(original, ("code search ", "search code for "))
    if code_index_query:
        from ..code_index.search import search_code

        return _format_code_index_search(search_code(code_index_query, limit=8)), "fast-command"

    symbol_index_query = _after_prefix(original, ("symbol search ", "code symbols "))
    if symbol_index_query:
        from ..code_index.search import search_symbols

        return _format_code_index_symbols(search_symbols(symbol_index_query, limit=8)), "fast-command"

    if normalized == "workspace summary":
        from ..code_index.status import workspace_summary

        return _format_code_index_workspace(workspace_summary()), "fast-command"

    file_summary_path = _after_prefix(original, ("code file summary ", "summarize file ", "summarise file "))
    if file_summary_path:
        from ..code_index.search import summarize_file

        return _format_code_index_file_summary(summarize_file(file_summary_path)), "fast-command"

    if normalized in {"code status", "code intelligence status"}:
        return _run_tool(tools, "code_status", session_context)

    if normalized in {"reindex code", "index code"}:
        return _run_tool(tools, "code_reindex", session_context)

    if normalized in {"project map", "code project map", "map project", "code map"}:
        return _run_tool(tools, "code_project_map", session_context)

    symbol_query = _after_prefix(original, ("find symbol ", "where is symbol ", "search symbol "))
    if symbol_query:
        return _run_tool(tools, "code_find_symbol", session_context, symbol=symbol_query)

    explain_feature = _after_prefix(original, ("explain feature ", "where is feature ", "where is ", "where are "))
    if explain_feature and any(word in normalized for word in ("implemented", "provider", "agent", "feature", "runner", "router", "browser", "nim", "research", "code")):
        feature = re.sub(r"\s+implemented\??$", "", explain_feature, flags=re.IGNORECASE).strip(" ?")
        return _run_tool(tools, "code_explain_feature", session_context, feature=feature)

    debug_payload = _after_prefix(original, ("debug this:", "debug this ", "what does this error mean:", "what does this error mean "))
    if debug_payload:
        return _run_tool(tools, "code_debug_traceback", session_context, traceback=debug_payload)

    plan_goal = _after_prefix(original, ("plan change ", "make a patch plan ", "patch plan ", "plan code change "))
    if plan_goal:
        return _run_tool(tools, "code_plan_change", session_context, goal=plan_goal)

    save_code_insight = re.match(r"^\s*save code insight\s+([^:]+):\s*(.+)$", original, flags=re.IGNORECASE | re.DOTALL)
    if save_code_insight:
        return _run_tool(
            tools,
            "research_save_note",
            session_context,
            topic=save_code_insight.group(1).strip(),
            note="code_insight: " + save_code_insight.group(2).strip(),
            tags="code,project",
        )

    if normalized == "research status":
        return _run_tool(tools, "research_status", session_context)

    topic_to_start = _after_prefix(original, ("start research topic ", "create research topic ", "new research topic "))
    if topic_to_start:
        return _run_tool(tools, "research_start_topic", session_context, topic=topic_to_start)

    research_match = re.match(r"^\s*research\s+([^:]+):\s*(.+)$", original, flags=re.IGNORECASE | re.DOTALL)
    if research_match:
        return _run_tool(
            tools,
            "research_web",
            session_context,
            topic=research_match.group(1).strip(),
            query=research_match.group(2).strip(),
            max_results=5,
        )

    recall_topic = _after_prefix(original, ("what do we know about ", "what do u know about "))
    if recall_topic:
        return _run_tool(tools, "research_recall", session_context, topic=recall_topic, query=recall_topic, limit=6)

    summary_topic = _after_prefix(original, ("summarize research topic ", "summarise research topic "))
    if summary_topic:
        return _run_tool(tools, "research_summary", session_context, topic=summary_topic)

    forget_topic = _after_prefix(original, ("forget research topic ", "delete research topic "))
    if forget_topic:
        return f"Deleting a research topic is destructive. Say 'confirm forget research topic {forget_topic}' if you really want that.", "fast-command"

    if normalized in {"vision status", "screen vision status", "screen analysis status"}:
        status = vision_status()
        return json.dumps(status, indent=2), "fast-command"

    if normalized in {"what window am i on", "what window am i using", "active window", "current window"}:
        return _run_tool(tools, "window_active", session_context)

    if normalized in {"what is open", "what's open", "list windows", "list open windows", "open windows"}:
        return _run_tool(tools, "window_list", session_context, limit=40)

    focus_target = _after_prefix(normalized, ("switch to ", "focus ", "go to window ", "bring up "))
    if focus_target:
        return _run_tool(tools, "window_focus", session_context, query=focus_target)

    minimize_target = _after_prefix(normalized, ("minimize ", "minimise "))
    if minimize_target:
        return _run_tool(tools, "window_minimize", session_context, query=minimize_target)

    maximize_target = _after_prefix(normalized, ("maximize ", "maximise "))
    if maximize_target:
        return _run_tool(tools, "window_maximize", session_context, query=maximize_target)

    open_check = re.match(r"^(?:is|verify|check)\s+(.+?)\s+open\??$", normalized)
    if open_check:
        return _run_tool(tools, "verify_last_action", session_context, tool="open_app", target=open_check.group(1).strip())

    if normalized in {"workspace status", "project status", "workspace config"}:
        return _run_tool(tools, "workspace_status", session_context)

    if normalized in {"project structure", "inspect project structure", "inspect eva project", "eva project structure"}:
        return _run_tool(tools, "workspace_project_summary", session_context)

    if normalized in {"what files changed recently", "recent files", "recently changed files", "what changed recently"}:
        try:
            result = tools.run("workspace_list_files", path="", limit=200)
        except Exception as exc:
            return f"I tried to scan the workspace, but it failed safely: {exc}", "workspace-tool"
        if not isinstance(result, dict) or not result.get("ok"):
            return _format_workspace_result(result, mode="list_files"), "workspace-tool"
        files = result.get("files") if isinstance(result.get("files"), list) else []
        recent = sorted([item for item in files if isinstance(item, dict)], key=lambda item: str(item.get("modified_at") or ""), reverse=True)[:12]
        lines = ["Most recently changed safe workspace files:"]
        lines.extend(f"- {item.get('path')} ({item.get('modified_at')})" for item in recent)
        return "\n".join(lines), "workspace-tool"

    if normalized in {"summarize project", "summarise project", "project summary", "summarize eva project", "explain project architecture", "explain the architecture"}:
        return _run_tool(tools, "workspace_project_summary", session_context)

    read_path = _after_prefix(original, ("read file ", "show file ", "inspect file "))
    if read_path:
        return _run_tool(tools, "workspace_read_file", session_context, path=read_path)

    find_query = _after_prefix(original, ("find file ", "find in project ", "search project for ", "search workspace for "))
    if find_query:
        return _run_tool(tools, "workspace_search", session_context, query=find_query, limit=10)

    if normalized.startswith("where is ") or normalized.startswith("where are "):
        query = re.sub(r"^where (?:is|are)\s+", "", original, flags=re.IGNORECASE).strip(" ?")
        if query:
            return _run_tool(tools, "workspace_search", session_context, query=query, limit=10)

    if normalized in {
        "use mistral for fallback",
        "use mistral as fallback",
        "set mistral as fallback",
        "use mistral local fallback",
    }:
        return "Got it. Mistral is the deep local Ollama fallback target; I’ll keep cloud failures falling through to local Ollama instead of looping on a blocked cloud key.", "fast-command"

    if normalized in {
        "show screen",
        "show my screen",
        "look at screen",
        "look at my screen",
        "check screen",
        "check my screen",
        "analyze screen",
        "analyze my screen",
        "what is on my screen",
        "what's on my screen",
        "tell me what is open",
        "tell me what's open",
    }:
        return _run_tool(tools, "analyze_screen", session_context, question=original)

    if normalized in {"capture screen", "take screenshot", "take a screenshot", "screen shot", "screenshot"}:
        return _run_tool(tools, "capture_screen", session_context)

    profile_key = profile_key_from_message(original)
    if profile_key and normalized.startswith(("open ", "show ", "launch ")) and "my " in f"{normalized} ":
        url = profile_urls().get(profile_key, "")
        if url:
            return _run_tool(tools, "open_url", session_context, url=url)
        label = "profile" if profile_key == "profile" else profile_key
        return f"I don't have your {label} URL saved yet. Send me the link once and I'll use it next time.", "fast-command"

    if wants_previous_result(original):
        results = last_web_results(session_context)
        selected, matches, reason = result_reference_from_message(original, results)
        if selected:
            return _run_tool(tools, "open_url", session_context, url=str(selected.get("url") or ""))
        if reason == "ambiguous" and matches:
            labels = [str(item.get("title") or item.get("url") or "Untitled")[:60] for item in matches[:4]]
            return f"Which one do you want me to open: {', '.join(labels)}?", "fast-command"
        if reason == "no_results":
            if profile_key:
                return "I don't have your profile URL saved yet. Send me the link once and I'll use it next time.", "fast-command"
            return "I don't have previous search results to open yet. Search first, then say which result to open.", "fast-command"
        return "I found possible matches, but I can't assume which one you mean. Say the result number or name.", "fast-command"

    if profile_key and normalized.startswith(("open ", "show ", "launch ")):
        label = "profile" if profile_key == "profile" else profile_key
        return f"I don't have your {label} URL saved yet. Send me the link once and I'll use it next time.", "fast-command"

    app = _after_prefix(normalized, ("open app ", "launch app ", "start app ", "open ", "launch ", "start "))
    if app:
        if app in FOLDER_WORDS:
            return _run_tool(tools, "open_folder", session_context, folder_name=app)
        if app in WEB_ALIASES:
            return _run_tool(tools, "open_url", session_context, url=WEB_ALIASES[app])
        if app in APP_WORDS:
            return _run_tool(tools, "open_app", session_context, app_name=app)

    close_target = _after_prefix(normalized, ("close ", "quit ", "kill app ", "exit app "))
    if close_target:
        return _run_tool(tools, "close_app", session_context, app_name=close_target)

    folder = _after_prefix(normalized, ("open folder ", "show folder ", "open my ", "show my "))
    if folder or normalized in {f"open {name}" for name in FOLDER_WORDS}:
        folder_name = folder or normalized.removeprefix("open ")
        return _run_tool(tools, "open_folder", session_context, folder_name=folder_name)

    url = _after_prefix(original, ("open url ", "open website ", "go to ", "visit "))
    if url:
        return _run_tool(tools, "open_url", session_context, url=url)

    if re.match(r"^(open|visit)\s+([a-z0-9-]+\.)+[a-z]{2,}(/.*)?$", normalized):
        target = original.split(maxsplit=1)[1]
        return _run_tool(tools, "open_url", session_context, url=target)

    search = _after_prefix(original, ("search for ", "google ", "look up ", "search web for ", "web search "))
    if search:
        return _run_tool(tools, "web_search", session_context, query=search)

    media_actions = {
        "mute": "mute",
        "unmute": "mute",
        "volume up": "volume_up",
        "increase volume": "volume_up",
        "louder": "louder",
        "volume down": "volume_down",
        "decrease volume": "volume_down",
        "quieter": "quieter",
        "play": "play_pause",
        "pause": "play_pause",
        "play pause": "play_pause",
        "next song": "next",
        "next track": "next",
        "previous song": "previous",
        "previous track": "previous",
    }
    if normalized in media_actions:
        return _run_tool(tools, "media_key", session_context, action=media_actions[normalized])

    if normalized in {"lock", "lock laptop", "lock pc", "lock screen"}:
        return _run_tool(tools, "system_power", session_context, action="lock")

    confirm_actions = {
        "confirm sleep": "sleep",
        "confirm sleep laptop": "sleep",
        "confirm shutdown": "shutdown",
        "confirm shutdown laptop": "shutdown",
        "confirm turn off laptop": "shutdown",
        "confirm restart": "restart",
        "confirm restart laptop": "restart",
        "confirm sign out": "sign_out",
        "confirm log out": "log_out",
    }
    if normalized in confirm_actions:
        return _run_tool(tools, "system_power", session_context, action=confirm_actions[normalized], confirmed=True)

    return None

