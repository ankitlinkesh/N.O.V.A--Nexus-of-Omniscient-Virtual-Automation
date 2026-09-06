"""Shared parsing/text helpers used by more than one fast-command module.

Phase 71 split ``fast_commands.py`` (previously ~5,800 lines) into
domain-scoped modules (formatters, vault, rules, learned skills, the
``eva ask`` handler) plus this module for the small pieces genuinely needed
on both sides of that split:

- ``_after_prefix`` / ``_parse_between`` / ``_parse_replace_draft`` /
  ``_parse_replace_with_prefix`` are pure string-parsing helpers used by both
  ``maybe_handle_fast_command`` (still in ``fast_commands.py``) and
  ``_handle_eva_ask_command`` (moved to ``fast_command_ask.py``).
- ``_PROACTIVITY_DISABLED_MSG`` is the same off-message shown by the
  proactivity status/report commands that stayed in ``fast_commands.py``
  (``_proactivity_rules`` / ``_proactivity_tick`` / ``_proactivity_notifications``)
  and by the rule-mutation commands that moved to ``fast_command_rules.py``
  (``_proactivity_create_rule`` / ``_proactivity_delete_rule`` /
  ``_proactivity_set_enabled``).

This module intentionally has no imports from any other ``fast_command_*``
module, so it can be imported by all of them without risk of a cycle.
"""
from __future__ import annotations

_PROACTIVITY_DISABLED_MSG = (
    "Proactivity is off. Set EVA_PROACTIVITY_ENABLED=1 to let me act on standing rules (schedules, "
    "file watchers). Rules only ever PROPOSE work — anything they queue still needs the gate, and a "
    "privileged action still waits for your confirmation."
)


def _after_prefix(text: str, prefixes: tuple[str, ...]) -> str | None:
    for prefix in prefixes:
        if text.startswith(prefix):
            value = text[len(prefix):].strip(" :")
            if value:
                return value
    return None


# A window name is a name: "chrome", "untitled - notepad", "vs code". These are
# the marks of a sentence carrying a SECOND thing to do, which a fast command
# whose argument is supposed to be a name must not swallow.
_INSTRUCTION_MARKERS = (" and ", " then ", ", ", "; ")
_MAX_NAME_WORDS = 6


def _looks_like_an_instruction(value: str) -> bool:
    """True when a fast command's argument is really a multi-clause errand.

    A fast command binds a whole phrase to ONE tool call, so a compound
    instruction reaching one is not partly carried out -- the remaining clauses
    are silently dropped and the reply reports the first as the whole job.
    Declining the shortcut hands it to the planner, which can take several steps.
    """
    text = " ".join(str(value or "").lower().split())
    if not text:
        return False
    if any(marker in text for marker in _INSTRUCTION_MARKERS):
        return True
    return len(text.split()) > _MAX_NAME_WORDS


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
