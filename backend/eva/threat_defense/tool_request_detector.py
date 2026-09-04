from __future__ import annotations

import re

from .models import ThreatFinding


_DIRECT_TOOL_MARKERS = ("tool_call", "call tool", "use tool", "run action", "execute action")
_INDIRECT_TOOL_MARKERS = ("after validation", "quietly trigger", "later trigger", "once approved", "after this check")
_EXECUTION_MARKERS = ("powershell", "terminal", "install a package", "package install", "open browser", "desktop action", "mcp", "cloud action", "shell")
_COMMAND_MARKERS = ("&&", "||", "| sh", "; rm", "rm -rf", "`", "$(")
_KNOWN_CAPABILITIES = {
    "context.status",
    "context.sources",
    "context.policy",
    "context.budget",
    "context.assemble_preview",
    "context.grounding_report",
    "context.redaction_policy",
    "context.readiness",
    "threat.status",
    "threat.catalog",
    "threat.policy",
    "threat.scan_preview",
    "threat.injection_examples",
    "threat.exfiltration_examples",
    "threat.context_guard",
    "threat.readiness",
    "llm.validation_status",
    "llm.red_team_status",
}


# A capability claim looks like `browser.execute` -- an invented tool identifier,
# which is a real injection tactic and must keep firing. The old pattern was
# `\b[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\b` with IGNORECASE, which also matched every
# process name, window class and filename: listing your own windows produced TEN
# "unknown capability claim" findings (`chrome.exe`, `explorer.exe`,
# `WindowsTerminal.exe`, `MicrosoftWindows.Client`, `Cua.AgentCursorOverlay`...).
# That is not merely noise -- a finding calls `state.record_injection`, which
# taints the whole task, so a later privileged step was escalated as though a real
# injection had happened. Two narrowings, each of which leaves the threat concept
# intact:
#
#   1. Case-sensitive. The pattern was WRITTEN as a lowercase identifier
#      (`[a-z][a-z0-9_]*`) and then made case-insensitive, which is what let
#      PascalCase window classes through. Capability identifiers in this system
#      are lowercase; `MicrosoftWindows.Client` never was one.
#   2. A dotted token whose suffix is a file extension or a TLD is a filename or a
#      domain, not a claim about what Eva can do.
#
# `browser.execute`, `threat.unlock_shell` and `llm.fake_status` all still fire --
# pinned by tests, and by the red-team verifier that caught an earlier, wronger
# version of this narrowing.
_NON_CAPABILITY_SUFFIXES = frozenset(
    {
        # file extensions
        "exe", "dll", "sys", "msi", "py", "pyc", "js", "ts", "css", "html", "htm",
        "md", "txt", "log", "json", "xml", "yml", "yaml", "toml", "ini", "cfg",
        "csv", "tsv", "pdf", "docx", "xlsx", "pptx", "zip", "tar", "gz",
        "png", "jpg", "jpeg", "gif", "svg", "ico", "mp3", "mp4", "wav",
        "db", "sqlite", "sqlite3", "bak", "tmp", "lock", "env",
        # common TLDs
        "com", "org", "net", "io", "dev", "ai", "co", "uk", "gov", "edu",
    }
)
_CAPABILITY_CLAIM_RE = re.compile(r"\b[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\b")


def _capability_claims(raw: str) -> list[str]:
    """Dotted identifiers that are actually claims about a capability."""
    claims = []
    for claim in sorted(set(_CAPABILITY_CLAIM_RE.findall(raw))):
        if claim.split(".", 1)[1] in _NON_CAPABILITY_SUFFIXES:
            continue
        claims.append(claim)
    return claims


def _mentions_execution_surface(lowered: str) -> bool:
    """Does this text USE an execution-surface word, or merely contain the letters?

    `_EXECUTION_MARKERS` was matched by plain substring, so `WindowsTerminal.exe`
    -- a window title on any machine with a terminal open -- matched "terminal"
    and raised a CRITICAL finding, tainting the task. The catalog calls this
    category "Locked execution-surface *language*"; letters inside a longer
    identifier are not language.

    Single-word markers must therefore match a whole token, where tokens split on
    every non-alphanumeric character. That keeps `shell_exec` and `PowerShell:`
    matching (`_` and `:` are separators) while `WindowsTerminal` does not contain
    the token "terminal". Multi-word markers ("install a package", "open browser")
    keep substring matching, because a phrase cannot collide with an identifier
    the same way. Every red-team case still fires -- pinned, and an earlier,
    wronger narrowing of this file was caught by exactly that verifier.
    """
    tokens = set(re.findall(r"[a-z0-9]+", lowered))
    for marker in _EXECUTION_MARKERS:
        if " " in marker:
            if marker in lowered:
                return True
        elif marker in tokens:
            return True
    return False


def detect_tool_or_capability_requests(text: str, source_type: str) -> tuple[ThreatFinding, ...]:
    raw = str(text or "")
    lowered = raw.lower()
    findings: list[ThreatFinding] = []
    if any(marker in lowered for marker in _DIRECT_TOOL_MARKERS):
        findings.append(_finding("direct_tool_execution", "critical", source_type, "Direct tool/action execution language was detected."))
    if any(marker in lowered for marker in _INDIRECT_TOOL_MARKERS):
        findings.append(_finding("indirect_tool_execution", "critical", source_type, "Indirect or delayed tool execution language was detected."))
    if _mentions_execution_surface(lowered):
        findings.append(_finding("execution_surface_request", "critical", source_type, "Locked execution-surface language was detected."))
    if any(marker in lowered for marker in _COMMAND_MARKERS):
        findings.append(_finding("command_injection", "high", source_type, "Command-injection-looking text was detected."))
    if "repair" in lowered and ("executable" in lowered or "action" in lowered or "unsafe" in lowered):
        findings.append(_finding("unsafe_repair", "high", source_type, "Unsafe repair into executable action was requested."))
    for claim in _capability_claims(raw):
        normalized = claim.lower()
        if normalized in _KNOWN_CAPABILITIES:
            continue
        category = "hallucinated_capability" if "superpower" in normalized or "unlocked" in normalized else "unknown_capability"
        severity = "high" if category == "hallucinated_capability" else "medium"
        findings.append(_finding(category, severity, source_type, "Unknown or hallucinated capability claim was flagged."))
    return tuple(findings)


def _finding(category: str, severity: str, source_type: str, summary: str) -> ThreatFinding:
    return ThreatFinding(category, severity, source_type, summary, "block_execution_or_flag_capability")
