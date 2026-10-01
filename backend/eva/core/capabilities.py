from __future__ import annotations

from dataclasses import dataclass


RouteType = str


@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    trigger_concepts: tuple[str, ...]
    related_tools: tuple[str, ...]
    example_intents: tuple[str, ...]
    route_type: RouteType


CAPABILITIES: dict[str, Capability] = {
    "self_architecture": Capability(
        name="self_architecture",
        description="Explain Eva's own frontend, backend, agent, tool, provider, memory, and safety architecture.",
        trigger_concepts=("architecture", "built", "systems", "modules", "how eva works", "full architecture"),
        related_tools=("code_project_map", "workspace_project_summary", "code_search"),
        example_intents=("explain your full architecture", "how are you built", "what systems do you have"),
        route_type="skill",
    ),
    "workflow_explanation": Capability(
        name="workflow_explanation",
        description="Explain Eva's real command, operator, agent, browser, research, LLM, code, and voice workflows.",
        trigger_concepts=("workflows", "process commands", "agent workflows", "how do you work"),
        related_tools=("code_project_map", "workspace_project_summary"),
        example_intents=("explain your workflows", "how do you process commands"),
        route_type="skill",
    ),
    "self_diagnostics": Capability(
        name="self_diagnostics",
        description="Summarize which Eva subsystems and providers are working, degraded, or unavailable.",
        trigger_concepts=("diagnose", "health", "broken", "working", "degraded"),
        related_tools=("llm_status", "vision_status", "research_status"),
        example_intents=("what part of you is broken", "system health", "diagnose yourself"),
        route_type="deterministic",
    ),
    "eva_v2_runtime": Capability(
        name="eva_v2_runtime",
        description="Report the optional Eva v2 runtime skeleton, specialist agents, guardrails, traces, vector memory, and automation adapter status.",
        trigger_concepts=("eva v2", "runtime status", "agents status", "guardrails status", "vector memory", "traces status", "automation adapters"),
        related_tools=("eva_v2_status", "agents_status", "guardrails_status", "vector_memory_status", "traces_status"),
        example_intents=("eva v2 status", "agents status", "automation adapters status"),
        route_type="deterministic",
    ),
    "provider_diagnostics": Capability(
        name="provider_diagnostics",
        description="Inspect configured LLM providers, models, local soft caps, blocked providers, and last errors without exposing keys.",
        trigger_concepts=("openrouter", "nvidia nim", "gemini", "groq", "clod", "ollama", "provider", "api status"),
        related_tools=("llm_status",),
        example_intents=("test OpenRouter API", "is NVIDIA NIM working", "check Gemini"),
        route_type="deterministic",
    ),
    "code_intelligence": Capability(
        name="code_intelligence",
        description="Use Eva's safe code index to find symbols, explain features, debug tracebacks, and plan changes.",
        trigger_concepts=("where is", "implemented", "find symbol", "traceback", "plan change", "code"),
        related_tools=("code_search", "code_find_symbol", "code_project_map", "code_explain_feature", "code_debug_traceback", "code_plan_change"),
        example_intents=("where is browser agent implemented", "find symbol run_agentic_task", "plan change improve voice"),
        route_type="skill",
    ),
    "workspace_inspection": Capability(
        name="workspace_inspection",
        description="Read-only workspace listing, search, file reading, and project summaries with secret exclusions.",
        trigger_concepts=("workspace", "project structure", "read file", "inspect files"),
        related_tools=("workspace_list_files", "workspace_search", "workspace_read_file", "workspace_project_summary"),
        example_intents=("project structure", "read file backend/eva/agent/runner.py"),
        route_type="skill",
    ),
    "research_knowledge": Capability(
        name="research_knowledge",
        description="Recall, save, and summarize local SQLite-backed research knowledge.",
        trigger_concepts=("research", "what do we know", "saved sources", "knowledge"),
        related_tools=("research_recall", "research_web", "research_summary", "research_status"),
        example_intents=("what do we know about NVIDIA NIM", "research AI agents"),
        route_type="agentic",
    ),
    "browser_agent": Capability(
        name="browser_agent",
        description="Open web apps in Chrome, run safe site searches, observe browser state, copy URLs, summarize pages, and save public pages to research.",
        trigger_concepts=("browser", "chrome", "web app", "page", "website", "tab", "summarize this page", "current url", "copy current url"),
        related_tools=(
            "chrome_open_web_app",
            "chrome_search_site",
            "chrome_copy_current_url",
            "browser_verify_target",
            "chrome_activate_top_youtube_result",
            "browser_open_result_and_verify",
            "browser_status",
            "browser_current_page",
            "browser_summarize_page",
            "browser_extract_links",
            "browser_save_page_to_research",
            "browser_observe",
        ),
        example_intents=("open ChatGPT on Chrome", "open YouTube and search Interstellar theme", "play it now", "verify results", "copy current URL", "summarize this page"),
        route_type="skill",
    ),
    "desktop_agent": Capability(
        name="desktop_agent",
        description="Observe active/open windows, focus/minimize/maximize safe windows, and verify desktop actions.",
        trigger_concepts=("window", "desktop", "what is open", "active app", "focus", "minimize"),
        related_tools=("window_active", "window_list", "desktop_observe", "window_focus"),
        example_intents=("what window am I on", "what is open", "switch to chrome"),
        route_type="skill",
    ),
    "screen_vision": Capability(
        name="screen_vision",
        description="One-shot explicit screen capture and Gemini Vision screen understanding.",
        trigger_concepts=("screen", "look", "analyze screen", "visible error"),
        related_tools=("analyze_screen", "capture_screen"),
        example_intents=("look at my screen", "what error is visible"),
        route_type="skill",
    ),
    "operator_control": Capability(
        name="operator_control",
        description="Safe laptop controls for apps, folders, URLs, media keys, and guarded power actions.",
        trigger_concepts=("open app", "close app", "volume", "lock laptop", "shutdown", "brightness", "dark mode", "wifi", "bluetooth"),
        related_tools=("open_app", "open_folder", "open_url", "media_control", "guarded_power_action", "system_volume", "display_brightness", "theme_mode", "radio_set", "radio_status"),
        example_intents=("open chrome", "volume up", "set volume to 30", "set brightness to 60", "turn on dark mode", "turn off wifi", "shutdown my laptop"),
        route_type="deterministic",
    ),
    "media_music_control": Capability(
        name="media_music_control",
        description="Open Spotify, search/play requested music, and send safe media controls without API keys or arbitrary shell access.",
        trigger_concepts=("spotify", "play song", "search spotify", "pause spotify", "next song", "previous song"),
        related_tools=("spotify_play_desktop", "spotify_search_desktop", "spotify_pause", "spotify_next", "spotify_previous", "spotify_restart_current", "media_control"),
        example_intents=("play Starboy by The Weeknd on Spotify", "search Spotify for Blinding Lights", "pause Spotify"),
        route_type="skill",
    ),
    "permission_gate": Capability(
        name="permission_gate",
        description="Classify destructive, privacy-sensitive, external, system-changing, and hard-blocked actions before any tool execution.",
        trigger_concepts=("permission", "delete", "override", "destructive", "confirmation"),
        related_tools=("file.delete", "permission_gate"),
        example_intents=("delete my downloads", "permissions status"),
        route_type="deterministic",
    ),
    "message_workflow": Capability(
        name="message_workflow",
        description="Prepare visible message workflows while requiring confirmation before sending anything externally.",
        trigger_concepts=("send message", "whatsapp", "email", "confirmation"),
        related_tools=("message.prepare", "message.confirm_send", "message.send_via_ui"),
        example_intents=("send a WhatsApp message saying hello to raks"),
        route_type="skill",
    ),
    "memory": Capability(
        name="memory",
        description="Local user and project memory through SQLite-backed message/event/fact storage.",
        trigger_concepts=("remember", "what do you know about me", "memory"),
        related_tools=("memory",),
        example_intents=("remember that I like short replies", "what do you know about me"),
        route_type="deterministic",
    ),
    "voice_ui": Capability(
        name="voice_ui",
        description="Browser push-to-talk and speech synthesis controls.",
        trigger_concepts=("voice", "mic", "speak", "talk faster", "tts"),
        related_tools=("voice_ui",),
        example_intents=("why is voice slow", "change Eva voice"),
        route_type="synthesize",
    ),
}


def get_capability(name: str) -> Capability | None:
    return CAPABILITIES.get(name)


def capability_names() -> list[str]:
    return list(CAPABILITIES)
