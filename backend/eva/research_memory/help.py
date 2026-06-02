from __future__ import annotations


def format_research_memory_help() -> str:
    return "\n".join(
        [
            "Research Memory help",
            "",
            "What it is:",
            "Research Memory is Eva's local saved-research note system. It stores sanitized notes, topics, tags, source metadata, and quality signals in a local runtime SQLite store.",
            "",
            "Main commands:",
            "- research memory status",
            "- research memory recent",
            "- research memory topics",
            "- research memory search <query>",
            "- research memory retrieve <query>",
            "- research memory commands",
            "- research memory examples",
            "- research memory safety",
            "",
            "Safety note:",
            "Research Memory uses local research data and local control, with API-backed LLM reasoning elsewhere in Eva when configured. It does not scrape private pages or send saved notes to cloud embedding/summarization services.",
            "",
            "See docs/EVA_RESEARCH_MEMORY.md for the full command reference.",
        ]
    )


def format_research_memory_command_reference() -> str:
    return "\n".join(
        [
            "Research Memory command reference",
            "",
            "Core:",
            "- research memory status",
            "- research memory recent",
            "- research memory topics",
            "- research memory stats",
            "",
            "Save/import:",
            "- research memory save topic <topic> note <text>",
            "- research memory save topic <topic> tags <tag1,tag2> note <text>",
            "- research memory import note topic <topic> title <title> text <text>",
            "- research memory import note topic <topic> title <title> tags <tag1,tag2> text <text>",
            "",
            "Search/retrieve:",
            "- research memory search <query>",
            "- research memory search <query> topic <topic>",
            "- research memory search <query> tag <tag>",
            "- research memory search <query> source <source_type>",
            "- research memory retrieve <query>",
            "- research memory retrieve <query> topic <topic>",
            "- research memory retrieve <query> tag <tag>",
            "- research memory retrieve <query> source <source_type>",
            "- research memory retrieval status",
            "- research memory retrieval plan <query>",
            "",
            "Topics/tags/quality:",
            "- research memory topic <topic>",
            "- research memory tags",
            "- research memory duplicates",
            "- research memory merge duplicates preview",
            "- research memory quality",
            "",
            "Import/export/cleanup:",
            "- research memory export",
            "- research memory export topic <topic>",
            "- research memory delete item <item_id>",
            "- research memory clear topic <topic> confirm",
            "",
            "Vector prep:",
            "- research memory vector status",
            "- research memory vector index preview",
            "- research memory vector search <query>",
            "- research memory semantic search <query>",
            "",
            "Explicit v2 usage:",
            "- eva v2 plan use my saved research about Eva memory",
            "- eva v2 dry run summarize what I saved about Eva",
            "- eva v2 execute research memory retrieve Eva",
        ]
    )


def format_research_memory_examples() -> str:
    return "\n".join(
        [
            "Research Memory examples",
            "",
            "Save a note:",
            "- research memory save topic Eva note Research Memory keeps saved research local.",
            "- research memory save topic Eva tags memory,safety note Vector search is disabled by default.",
            "",
            "Import a local note:",
            "- research memory import note topic Eva title Memory safety text Research Memory refuses private scraping.",
            "- research memory import note topic Eva title Retrieval tags memory,retrieval text Lexical retrieval is the default.",
            "",
            "Search and retrieve:",
            "- research memory search Eva",
            "- research memory search Eva tag memory",
            "- research memory retrieve Eva",
            "- research memory retrieval plan Eva",
            "",
            "Review and cleanup:",
            "- research memory topics",
            "- research memory tags",
            "- research memory quality",
            "- research memory duplicates",
            "- research memory clear topic Test confirm",
            "",
            "Explicit v2 planning:",
            "- eva v2 plan use my saved research about Eva memory",
            "- eva v2 dry run summarize what I saved about Eva",
            "- eva v2 execute research memory retrieve Eva",
        ]
    )


def format_research_memory_safety() -> str:
    return "\n".join(
        [
            "Research Memory safety",
            "",
            "Data model:",
            "- Stores local sanitized notes, topics, tags, source metadata, and quality signals.",
            "- Uses lexical retrieval by default.",
            "- Vector search is prepared but disabled by default.",
            "- Exports stay under local runtime export storage and normal output shows the filename only.",
            "",
            "Not enabled:",
            "- No cloud embeddings.",
            "- No cloud summarization.",
            "- No Chroma/Qdrant backend is active yet.",
            "- No MCP, Playwright, or PyAutoGUI execution is involved in Research Memory commands.",
            "",
            "Refusals:",
            "- Does not scrape private, logged-in, Gmail, chat, or paywall pages.",
            "- Does not read cookies, tokens, localStorage, sessionStorage, or passwords.",
            "- Does not read .env.local.",
            "- Does not expose full memory dumps through v2.",
            "- Does not support clear-all.",
            "",
            "Cleanup rules:",
            "- Delete is item-scoped: research memory delete item <item_id>.",
            "- Clear topic requires confirm: research memory clear topic <topic> confirm.",
            "",
            "Scope wording:",
            "Research Memory uses local research data and local control, with API-backed LLM reasoning elsewhere in Eva when configured.",
        ]
    )


def format_research_memory_phase_summary() -> str:
    return "\n".join(
        [
            "Research Memory Phase 7.x summary",
            "",
            "Implemented:",
            "- Research Memory v2 local note store with sanitized save/search/status outputs.",
            "- Phase 7.1 import, export, scoped delete, confirmed topic clear, and stats.",
            "- Phase 7.2 tags, quality warnings, exact/near duplicate preview, and filtered search.",
            "- Phase 7.3 optional local vector interface with hashing fallback for tests, disabled by default.",
            "- Phase 7.4 lexical-first hybrid retrieval with topic/tag/source filters and quality-aware ranking.",
            "- Phase 7.5 v2 explicit context injection for saved-research prompts.",
            "- Phase 7.6 command help and repo documentation.",
            "",
            "Still limited:",
            "- Vector search is not the default retrieval path.",
            "- Chroma/Qdrant are not active.",
            "- Cloud embedding and cloud summarization paths are not enabled.",
            "- Normal Eva chat is not routed through v2 by this phase.",
            "- Private or logged-in scraping remains refused.",
        ]
    )


__all__ = [
    "format_research_memory_command_reference",
    "format_research_memory_examples",
    "format_research_memory_help",
    "format_research_memory_phase_summary",
    "format_research_memory_safety",
]
