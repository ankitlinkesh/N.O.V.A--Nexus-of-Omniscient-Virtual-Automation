"""Instant clipboard commands (Phase 128): "copy hello to my clipboard", "what's on my clipboard".

Only clearly anchored phrasings (the Phase 125/127 rules):

- WRITE needs the word "clipboard" in a fixed slot. "copy hello to my clipboard",
  "copy this to my clipboard: hello", "put hello on my clipboard", "set my clipboard
  to hello". Everything after "clipboard" must be empty or a bare "please" -- a
  second request ("... and open chrome") declines so the agent loop does both
  halves. "copy the file to Documents" has no "clipboard" and never matches.
- A payload that is a pronoun ("copy it/this/that to my clipboard") or a file
  reference ("copy notes.txt to my clipboard") is NOT text the user typed -- the
  user means the thing, not the word -- so those decline to the planner, which can
  read the file and copy its text under the normal gates.
- READ matches the WHOLE normalized message ("what's on my clipboard"). It still
  goes through ``tools.run``, so ``clipboard.read`` comes back as an approval
  prompt (confirm-class); nothing in this module can approve it.

The write payload keeps the user's exact case and spacing; only matching is
case-insensitive.
"""

from __future__ import annotations

import re
from typing import Any

from .fast_command_instant import _run, normalize_question

_LEAD = re.compile(r"^(?:hey\s+)?(?:nova|eva)[,\s]+(?:can you |could you |please )?|^(?:can you |could you |please |pls )", re.I)
_CLIP = r"(?:my |the |your )?(?:system )?clipboard"
_TRAIL = r"[\s.!]*(?:please|pls)?[\s.!]*"

# payload is captured lazily so the FIRST "to ... clipboard" wins.
_WRITE_PATTERNS = tuple(
    re.compile(rx, re.I | re.S)
    for rx in (
        rf"copy (?P<text>.+?) (?:to|onto|into|in) {_CLIP}{_TRAIL}",
        rf"(?:put|place|save|store) (?P<text>.+?) (?:on|onto|to|in|into) {_CLIP}{_TRAIL}",
        rf"copy this (?:to|onto|into) {_CLIP}\s*[:,-]\s*(?P<text>.+?){_TRAIL}",
        rf"copy (?:to|onto|into) {_CLIP}\s*[:,-]\s*(?P<text>.+?){_TRAIL}",
        rf"(?:set|change|make) {_CLIP} (?:to|as) (?P<text>.+?){_TRAIL}",
    )
)

_READ_PATTERNS = tuple(
    re.compile(rx)
    for rx in (
        r"what(?:'s| is) (?:currently |now )?(?:on|in) (?:my |the )?clipboard(?: right now| now| currently)?",
        r"what(?:'s| is) (?:my |the )?clipboard(?: contents?| text)?",
        r"what do i have (?:on|in) (?:my |the )?clipboard",
        r"(?:read|show|check|get|tell me) (?:me )?(?:what(?:'s| is) (?:on|in) )?(?:my |the )?clipboard(?: contents?| text)?",
    )
)

_PRONOUN_PAYLOADS = frozenset({"it", "this", "that", "these", "those", "this text", "that text", "the text", "the selection", "the selected text", "selection", "the file", "this file", "that file"})
# "notes.txt", "C:/x/report.pdf": a single file-looking token is a reference to a file.
_FILE_REF = re.compile(r"^\S+\.(?:txt|md|csv|json|log|py|js|ts|html?|xml|ya?ml|ini|pdf|docx?|xlsx?|pptx?|png|jpe?g|gif|zip|exe)$", re.I)


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'`":
        return text[1:-1]
    return text


def match_clipboard_command(message: str) -> tuple[str, dict[str, str]] | None:
    """Pure: ("write", {"text": ...}) | ("read", {}) | None. Whole-message only."""
    original = str(message or "").strip()
    if not original or "clipboard" not in original.lower():
        return None
    try:
        from ..agent.policies import split_trailing_request

        _head, tail = split_trailing_request(original)
        if tail:
            return None
    except Exception:
        pass

    norm = _LEAD.sub("", normalize_question(original))
    for rx in _READ_PATTERNS:
        if rx.fullmatch(norm):
            return "read", {}

    stripped = _LEAD.sub("", original).strip()
    for rx in _WRITE_PATTERNS:
        m = rx.fullmatch(stripped)
        if not m:
            continue
        text = _unquote(m.group("text"))
        lowered = text.lower().strip()
        if not text.strip() or lowered in _PRONOUN_PAYLOADS or _FILE_REF.match(text):
            return None
        if re.search(r"\bclipboard\b", lowered):
            return None  # "copy a to my clipboard and b to my clipboard" etc.
        return "write", {"text": text}
    return None


def maybe_handle_clipboard_command(message: str, tools: Any, session_context: dict | None = None) -> tuple[str, str] | None:
    matched = match_clipboard_command(message)
    if matched is None:
        return None
    kind, groups = matched
    if kind == "write":
        result, early = _run(tools, "clipboard.write", text=groups["text"])
    else:
        result, early = _run(tools, "clipboard.read")
        if early is None and isinstance(result, dict) and result.get("ok") and isinstance(result.get("text"), str):
            # Only reachable when the registry let it through (an approved replay);
            # the reply is the masked text the tool produced, never raw.
            body = result["text"]
            reply = body if body else str(result.get("message") or "Your clipboard is empty.")
            if body:
                reply = f"On your clipboard:\n{body}" + (f"\n({result['message']})" if result.get("message") else "")
            return reply, "desktop-tool"
    if early:
        return early, "desktop-tool"
    if isinstance(result, dict) and isinstance(result.get("message"), str) and result["message"].strip():
        return result["message"], "desktop-tool"
    return "I couldn't confirm the clipboard change: the tool answered without a result.", "desktop-tool"
