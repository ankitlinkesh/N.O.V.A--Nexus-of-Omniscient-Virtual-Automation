"""Who decides what a message means: the regex rule layers, or the LLM planner.

Historically a message passed through four layers of phrase-matching rules
(fast commands, casual replies, operator commands, the capability classifier)
and reached the LLM planner only when every one of them missed. Rules match exact
wording, so natural requests fell through them or, worse, were claimed by the
wrong one ("open my gmail" -> a folder named gmail).

`EVA_ROUTING=llm_first` (the default) sends natural messages straight to the
planner, which sees the whole tool registry and the conversation. The rules stay
only where being deterministic is the point:

  * approvals and confirmations (`confirm ...`, yes/no while an action is pending),
  * console-only commands whose authority comes from the exact prefix (`gui:`,
    `box:`, `delegate`, `role`, `explain`, `eva ...` status commands),
  * "play X on youtube/spotify", which have purpose-built handlers,
  * a short list of instant device commands (media keys, volume, mute, time),
    which are faster and cheaper than an LLM call and have exactly one meaning.

Safety does not live here. Every tool call still goes through the registry and
tool gate, whichever layer chose it. `EVA_ROUTING=rules_first` restores the old
order unchanged.
"""

from __future__ import annotations

import os
import re

from .request_normalizer import canonicalize_request

_DETERMINISTIC_PREFIXES = (
    "eva ", "nova ", "confirm", "approve", "deny", "reject", "cancel ",
    "gui:", "box:", "sandbox:", "delegate ", "role ", "roles", "explain ",
    "set volume", "volume ", "mute", "unmute",
)
_INSTANT = re.compile(
    r"^(?:pause|play|next track|previous track|volume up|volume down|mute|unmute|lock|lock laptop|lock pc|lock screen"
    r"|what(?:'s| is) the time|what time is it|what(?:'s| is) (?:today'?s |the )?date)$"
)
# "play X on youtube/spotify" has purpose-built handlers (open the site or app, search,
# activate the right result, verify). Measured live: given the same request the 4B
# planner chose a generic Google search and then verified the wrong window, so these
# stay on the rules.
_SITE_PLAYBACK = re.compile(
    r"^(?:(?:play|watch)\s+.+\s+(?:on|from|in|via)\s+(?:youtube|spotify)"
    r"|open\s+(?:youtube|spotify)\s+and\s+(?:play|search)\s+.+"
    r"|search\s+(?:youtube|spotify)\s+for\s+.+|youtube\s+search\s+.+)$"
)
# "send whatsapp to X saying Y" creates a gated send for exactly that recipient and
# text, so the wording is parsed by rule rather than guessed by the planner.
_SEND_WHATSAPP = re.compile(
    r"^send\s+(?:a\s+)?whatsapp(?:\s+message)?\s+to\s+.+?\s+saying\s+.+$"
    r"|^send\s+(?:a\s+)?whatsapp\s+message\s+saying\s+.+?\s+to\s+.+$"
    r"|^send\s+.+?\s+to\s+.+?\s+on\s+whatsapp$"
)
_CONFIRM_WORDS = {"yes", "y", "yep", "yeah", "no", "n", "nope", "cancel", "stop", "do it", "go ahead"}


def llm_first_enabled() -> bool:
    return os.environ.get("EVA_ROUTING", "llm_first").strip().lower() != "rules_first"


def must_stay_deterministic(message: str) -> bool:
    """True when the rule layers, not the LLM, must handle this message."""
    from ..security import tool_gate

    canonical = " ".join(canonicalize_request(message).lower().split()).rstrip(" .!?")
    if not canonical:
        return True
    from ..tools.email_tools import is_send_draft_request
    from ..tools.info_tools import parse_weather_request

    from .intent_router import _whatsapp_message_parts

    # Any phrasing the WhatsApp parser understands ("text hi to kutty on whatsapp") goes to the gated send, not the agent.
    if _whatsapp_message_parts(canonical) is not None:
        return True
    if is_send_draft_request(canonical) or parse_weather_request(canonical) is not None:
        return True
    if canonical.startswith(_DETERMINISTIC_PREFIXES) or _INSTANT.match(canonical) or _SITE_PLAYBACK.match(canonical) or _SEND_WHATSAPP.match(canonical):
        return True
    from ..permissions.confirmation import BARE_CONFIRM_PHRASES

    return tool_gate.has_pending_calls() and (canonical in _CONFIRM_WORDS or canonical in BARE_CONFIRM_PHRASES)


def use_rule_layers(message: str) -> bool:
    return (not llm_first_enabled()) or must_stay_deterministic(message)
