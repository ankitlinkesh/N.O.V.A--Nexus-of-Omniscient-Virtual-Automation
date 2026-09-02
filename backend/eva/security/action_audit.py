"""The auto-allow audit — no tool becomes unguarded by accident (Phase 51).

Two real bugs shipped with the same root cause, found within an hour of each
other by probing rather than by the 79-verifier suite:

  * ``capture_screen`` / ``analyze_screen`` declared no ``action_type``. It
    silently defaulted to ``SAFE_LOCAL_READ``, which is ALLOW-class, so they
    screenshotted the whole screen to disk with no confirmation — while the
    correctly-typed ``screen.observe`` sat gated and unreachable.
  * ``desktop_observe`` was ALLOW-class with a caller-supplied
    ``explicit_screen_intent`` flag that unlocked pixel capture — the model
    authorizing itself.

The lesson is not "we mislabelled two tools". It is that **the safe-looking
default is the dangerous one**: forget a field, get auto-allow, and nothing in
the suite notices. A permission gate whose default is "allow" fails open.

This module closes that hole. ``AUDITED_SAFE_LOCAL_READ`` is the *explicit,
reviewed* list of tools permitted to be auto-allowed. The Phase 51 verifier
fails if any tool is ``SAFE_LOCAL_READ`` without appearing here — so a new tool
that omits ``action_type`` breaks the build instead of quietly becoming
unguarded. Adding a name here is a deliberate act with a reason attached, which
is exactly what was missing.

Being listed here is a claim: *this tool reads only non-sensitive local state,
touches no pixels, mutates nothing, and reaches no network.*
"""

from __future__ import annotations

# --- Status / metadata reads: report internal state, no side effects. --------
_STATUS_TOOLS = frozenset(
    {
        "status",
        "system_status",
        "workspace_status",
        "research_status",
        "code_status",
        "browser_status",
        "spotify_status",
        "spotify_now_playing_status",
        "system_time",
        "verify_last_action",
    }
)

# --- Window metadata: titles + process names, NEVER pixels. ------------------
# desktop_observe belongs here ONLY because its screen-capture path was removed
# in the Phase 50 fix. If a pixel path ever returns, it must leave this set.
_WINDOW_METADATA_TOOLS = frozenset({"desktop_observe", "window_active", "window_list"})

# --- Workspace / code reads. ------------------------------------------------
# REVIEWED DECISION, not an oversight. These read file *contents*, which is
# literally a PRIVACY_FILE_READ. They stay allow-class because:
#   1. they are hard-restricted by the `_safe_path` allowlist to the project and
#      Documents/Desktop/Downloads, and it denies `.env*`, `.git`, `*.sqlite3`
#      and key files, so secrets are unreachable through them;
#   2. inspecting the user's own project is the assistant's core job — gating
#      every "search my code" behind a typed confirmation would make the
#      workspace tools unusable and train the user to approve reflexively, which
#      is worse for safety than the read itself.
# The underlying judgment is an asymmetry between broad and narrow reads:
# an arbitrary-path read (any file, anywhere the OS user can reach) should be
# gated; a narrow, allowlist-bounded read of the user's own project should
# not. Phase 66 found the arbitrary-path tool that used to make this contrast
# concrete, `file.read_text`, had no caller anywhere in the product -- the
# planner and console only ever routed reads through the allowlisted tools
# below -- so Phase 70 deleted it rather than let a stranded duplicate keep
# masquerading as "the gated alternative". The judgment this comment records
# does not depend on that specific tool existing; the workspace tools below
# would stay allow-class for the same two reasons even with nothing broader
# registered at all.
_WORKSPACE_READ_TOOLS = frozenset(
    {
        "workspace_read_file",
        "workspace_search",
        "workspace_list_files",
        "workspace_summarize_file",
        "workspace_project_summary",
        "file.list_dir",
        "code_search",
        "code_find_symbol",
        "code_project_map",
        "code_explain_feature",
        "code_debug_traceback",
        "code_plan_change",
    }
)

# --- Local research knowledge (local SQLite, no network). --------------------
_RESEARCH_LOCAL_TOOLS = frozenset({"research_recall", "research_summary"})

AUDITED_SAFE_LOCAL_READ: frozenset[str] = frozenset(
    _STATUS_TOOLS | _WINDOW_METADATA_TOOLS | _WORKSPACE_READ_TOOLS | _RESEARCH_LOCAL_TOOLS
)

# Tools that reach the network. Typed NETWORK_ACTION for honesty; that is
# allow-class exactly as before, so this is metadata truth, not a gate change.
NETWORK_TOOLS: frozenset[str] = frozenset(
    {
        "research_web",
        "browser_search",
        "browser_open_url",
        "browser_current_page",
        "browser_observe",
        "browser_summarize_page",
        "browser_extract_links",
        "browser_verify_target",
        "browser_recover_target",
        "chatgpt_in_chrome",
    }
)

# Tools that WRITE local state. They were typed SAFE_LOCAL_READ — a write
# labelled a read. DESTRUCTIVE_FILE_ACTION would be dishonest in the other
# direction (appending a research note is not destructive and gating it would
# break the research flow), so they are typed SAFE_LOCAL_UI: allow-class, same
# as before, but no longer claiming to be a read.
LOCAL_WRITE_TOOLS: frozenset[str] = frozenset({"research_save_note", "research_start_topic", "code_reindex"})


def unaudited_safe_local_reads(tools: dict) -> list[str]:
    """Every tool claiming SAFE_LOCAL_READ that nobody has reviewed.

    ``tools`` maps name -> spec. A non-empty result means someone added a tool
    without declaring an ``action_type`` and it silently became auto-allow.
    """
    offenders = []
    for name, spec in (tools or {}).items():
        if getattr(spec, "action_type", None) != "SAFE_LOCAL_READ":
            continue
        if name not in AUDITED_SAFE_LOCAL_READ:
            offenders.append(name)
    return sorted(offenders)


__all__ = [
    "AUDITED_SAFE_LOCAL_READ",
    "NETWORK_TOOLS",
    "LOCAL_WRITE_TOOLS",
    "unaudited_safe_local_reads",
]
