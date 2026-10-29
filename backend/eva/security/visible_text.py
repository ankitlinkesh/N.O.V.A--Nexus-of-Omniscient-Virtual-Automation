"""Make invisible and look-alike characters visible before a person approves text.

An approval prompt shows text the user is asked to trust. Text can lie to the eye: a zero-width
character splits a word a filter would catch, a right-to-left override reorders what is read,
a no-break or ideographic space hides in a gap, and a Cyrillic "а" is a Latin "a" to a human. None
of these change what is typed or sent, so the only defence is to show them for what they are.

``reveal`` replaces every character that does not render as itself with a visible ``⟦U+XXXX⟧``
marker, and ``note`` gives the one-line warning to put next to it. Ordinary printable text (every
script, emoji, accents) passes through unchanged. Newline and tab are kept as they are.
"""

from __future__ import annotations

import unicodedata

_KEEP = {"\n", "\t"}
# Letters from these scripts inside otherwise-Latin text are the classic look-alike attack.
_LOOKALIKE_SCRIPTS = ("CYRILLIC", "GREEK")


def _hidden(ch: str) -> bool:
    if ch in _KEEP or ch == " ":
        return False
    category = unicodedata.category(ch)
    if category in {"Cf", "Cc", "Co", "Cs", "Cn", "Zl", "Zp"}:
        return True
    return category == "Zs"  # every space-like character except the plain space


def _lookalike(text: str) -> bool:
    has_latin = any("LATIN" in unicodedata.name(ch, "") for ch in text if ch.isalpha())
    has_other = any(any(script in unicodedata.name(ch, "") for script in _LOOKALIKE_SCRIPTS) for ch in text if ch.isalpha())
    return has_latin and has_other


def reveal(text: str) -> tuple[str, int]:
    """(text with hidden characters shown as ⟦U+XXXX⟧, how many were replaced)."""
    shown: list[str] = []
    count = 0
    for ch in str(text):
        if _hidden(ch):
            shown.append(f"⟦U+{ord(ch):04X}⟧")
            count += 1
        else:
            shown.append(ch)
    return "".join(shown), count


def note(text: str) -> str:
    """A one-line warning for `text`, or "" when nothing about it can mislead the eye."""
    _, hidden = reveal(text)
    parts = []
    if hidden:
        parts.append(f"{hidden} invisible or unusual character(s), shown as ⟦U+…⟧")
    if _lookalike(str(text)):
        parts.append("letters from more than one alphabet (Latin mixed with Cyrillic or Greek), which can imitate each other")
    if not parts:
        return ""
    return "WARNING: this text contains " + " and ".join(parts) + ". Check it carefully before approving."
