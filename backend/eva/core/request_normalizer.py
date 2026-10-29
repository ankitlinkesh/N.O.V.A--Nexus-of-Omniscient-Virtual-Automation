"""Loose spoken phrasing -> the canonical form the fast-command rules already know.

The deterministic layers match whole phrases ("pause", "volume up", "open
calculator"). Real requests are rarely that tidy: "can you pause the music
please", "turn the volume up", "open the calculator for me". Each of those used to
miss every rule and cost a full LLM planner call (a ~7k-token prompt) for
something with one obvious answer.

This is a pure text rewrite and nothing else. It decides no action, grants no
permission and touches no tool: whatever it produces is routed by the same rules
and runs through the same registry gate as if the user had typed the canonical
phrase. A rewrite that does not match any rule changes nothing, because the
caller falls through exactly as before.
"""

from __future__ import annotations

import re

_LEADING = (
    re.compile(r"^(?:hey|hi|yo|ok|okay)[,\s]+(?:eva|nova)[,:]?\s+", re.IGNORECASE),
    # Bare "eva"/"nova" starts real commands ("eva control center"), so a vocative
    # needs its comma or colon.
    re.compile(r"^(?:eva|nova)[,:]\s+", re.IGNORECASE),
    re.compile(r"^(?:please|pls|kindly)[,\s]+", re.IGNORECASE),
    re.compile(r"^(?:can|could|would|will)\s+you\s+(?:please\s+)?(?:go ahead and\s+)?", re.IGNORECASE),
    re.compile(r"^go ahead and\s+", re.IGNORECASE),
)
_TRAILING = re.compile(r"[\s,]+(?:for me|please|pls|now|right now|real quick|quickly)$", re.IGNORECASE)
_THE_AFTER_VERB = re.compile(r"^(open|launch|start|close|quit)\s+the\s+", re.IGNORECASE)

# (whole-utterance pattern, canonical replacement). First match wins.
_SYNONYMS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(f"^(?:{pattern})$", re.IGNORECASE), replacement)
    for pattern, replacement in (
        (r"(?:pause|stop|halt)\s+(?:the\s+|this\s+)?(?:music|song|track|playback|audio|spotify|it)", "pause"),
        (r"(?:resume|continue|unpause)\s+(?:the\s+|this\s+)?(?:music|song|track|playback|audio|spotify|it)", "play"),
        (r"skip(?:\s+(?:this|the))?(?:\s+(?:song|track))?|(?:play\s+)?(?:the\s+)?next\s+(?:song|track)", "next track"),
        (r"(?:play\s+)?(?:the\s+)?(?:previous|last)\s+(?:song|track)", "previous track"),
        (
            r"turn\s+(?:the\s+)?(?:volume|sound)\s+up|turn\s+it\s+up|raise\s+the\s+volume|make\s+it\s+louder|(?:volume|sound)\s+up",
            "volume up",
        ),
        (
            r"turn\s+(?:the\s+)?(?:volume|sound)\s+down|turn\s+it\s+down|lower\s+the\s+volume|make\s+it\s+quieter|(?:volume|sound)\s+down",
            "volume down",
        ),
        (r"make\s+it\s+(?:brighter|lighter)", "make the screen brighter"),
        (r"make\s+it\s+(?:dimmer|darker)", "make the screen dimmer"),
    )
)
_PUT_ON = re.compile(r"^(?:put on|throw on|blast)\s+(?:some\s+)?(?P<what>.+)$", re.IGNORECASE)


def canonicalize_request(message: str) -> str:
    """Return the message in canonical form, or the message unchanged."""
    original = str(message or "")
    text = " ".join(original.split())
    if not text:
        return original
    # `eva ask ...` hands its tail to the question router verbatim: dropping a trailing "now" turned
    # "eva ask can Eva browse now" into a different question.
    if text.lower().startswith("eva ask "):
        return original

    stripped_lead = False
    for pattern in _LEADING:
        new = pattern.sub("", text, count=1)
        if new != text and new:
            text, stripped_lead = new, True
    # Only drop the trailing "?" of a request that began politely ("can you ...?").
    if stripped_lead:
        text = text.rstrip(" ?!.")
    while True:
        new = _TRAILING.sub("", text)
        if new == text or not new:
            break
        text = new
    text = _THE_AFTER_VERB.sub(lambda m: f"{m.group(1)} ", text, count=1)

    probe = text.rstrip(" .!?")
    for pattern, replacement in _SYNONYMS:
        if pattern.match(probe):
            return replacement
    put_on = _PUT_ON.match(probe)
    if put_on:
        return f"play {put_on.group('what')}"
    # Nothing was rewritten: hand back the caller's exact text. Collapsing its
    # whitespace here would corrupt payloads such as `copy 'two  words' to my clipboard`.
    return text if text != " ".join(original.split()) else original
