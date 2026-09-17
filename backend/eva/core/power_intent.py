"""Is this message asking to power the COMPUTER off, restart it, sleep it or sign out?

Phase 112. Three copies of one substring table decided this
(`operator_commands.POWER_ACTIONS`, `planner._forced_decision`,
`planner._extract_action`), each matching `"turn off"`, `"restart"` and
`"sleep"` anywhere in the text. So:

    "turn off wifi"             -> "This will shutdown your laptop. Confirm?"
    "turn off dark mode"        -> shutdown
    "restart spotify"           -> restart the laptop
    "sleep mode on my screen timer" -> sleep the laptop

It failed safe -- it asked rather than acted -- but a confirmation prompt about
the wrong thing is how someone approves a shutdown they did not ask for.

The rule now: the power verb is the WHOLE request, optionally naming the machine
("shut down", "restart my laptop", "put the computer to sleep", "sign out"),
with politeness around it. A verb aimed at anything else ("turn off wifi",
"restart spotify") is not a power action and goes to the ordinary routes. One
module, so the copies cannot drift apart again.
"""

from __future__ import annotations

import re

_MACHINE = r"(?:(?:the|my|this)\s+)?(?:laptop|computer|pc|system|device|machine|windows)"
_LEAD = r"(?:(?:hey\s+)?(?:nova|eva)[,\s]+)?(?:please\s+|can\s+you\s+|could\s+you\s+|would\s+you\s+)?"
_TAIL = r"(?:\s+(?:now|please|right\s+now|for\s+me))*[.!?]*"

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (action, re.compile(rf"^{_LEAD}{body}{_TAIL}$", re.IGNORECASE))
    for action, body in (
        ("shutdown", rf"(?:shut\s*down|shutdown|power\s+off|turn\s+off|switch\s+off)(?:\s+{_MACHINE})?"),
        ("shutdown", rf"(?:shut|power|turn|switch)\s+{_MACHINE}\s+(?:down|off)"),
        ("restart", rf"(?:restart|reboot)(?:\s+{_MACHINE})?"),
        ("sleep", rf"(?:sleep|go\s+to\s+sleep)(?:\s+{_MACHINE})?"),
        ("sleep", rf"(?:put|send)\s+{_MACHINE}\s+to\s+sleep"),
        ("sleep", rf"sleep\s+mode"),
        ("sign_out", rf"(?:sign\s*out|log\s*out|logout)(?:\s+(?:of\s+)?(?:windows|{_MACHINE}))?"),
    )
)


def power_action_requested(message: str) -> str | None:
    """The power action this whole message asks for, or None."""
    text = " ".join(str(message or "").split())
    for action, pattern in _PATTERNS:
        if pattern.match(text):
            return action
    return None
