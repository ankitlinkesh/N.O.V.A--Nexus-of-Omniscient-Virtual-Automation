"""Trusted-voice mode: your own spoken request may run reversible actions without a prompt.

By default every spoken request is treated exactly like typed text. This is the owner's explicit
opt-in (``EVA_VOICE_TRUST=1``) to relax that for ONE channel: a request that arrives through the
voice endpoints, i.e. words that came out of your own microphone, not from a web page, a file, a tool
result or any other content. For such a turn only, the confirm- or override-class actions below run
without asking. Nothing else changes.

What stays gated, voice or not (the owner's two exceptions, plus the cases that cannot be told apart):

  * SENDING: any external message or email (``message.*``, ``email.send_drafted``), form submission
    (``screen.submit_form``) and MCP tools (a server can send anything);
  * UNDOABLE actions: file writes, copies, moves and deletes, closing apps (unsaved work), power
    actions, shell commands, sandbox file transfers, turning Wi-Fi off (it cuts NOVA's own access);
  * anything the Phase 55 risk layer escalated (a sensitive path or target), because this only ever
    runs after that and never lowers an escalated call.

Because a key press or a click can SEND from inside an app (Enter in a chat box, a Send button), the
screen tools are refused here when they would plausibly send: Enter/Ctrl+Enter and newlines while a
messaging or mail app is in front, and clicks on Send/Post/Submit/Pay/Buy/Delete/Confirm-style labels.

Three guards keep "your voice" from becoming "anyone's voice":

  * the scope is opened only by the voice endpoint and, for an agent task, re-opened per step only
    when the task is untainted and the goal is the user's own (the same conditions as the typing and
    click grants), so injected content that tainted the task loses it;
  * an allowlist, not a denylist: a tool this file does not name is never lowered;
  * it is off unless the operator turns it on, and ``verify`` suites run with it off.

Known limit, stated plainly: speech from a speaker (a video that says the wake phrase) is also
"your microphone". That is why the two exceptions above exist: nothing that sends or cannot be
undone ever runs on a heard command alone.
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

_voice_turn: ContextVar[bool] = ContextVar("eva_voice_turn", default=False)

# Allowlist of tools a trusted voice turn may lower to "allow". All reversible: input into the app
# in front, reading the screen or clipboard for the user.
ELIGIBLE_TOOLS = frozenset({
    "screen.type_text", "screen.press", "screen.hotkey", "screen.click", "screen.scroll", "screen.observe",
    "capture_screen", "analyze_screen", "clipboard.read", "radio_set",
})

_MESSAGING_WINDOW = re.compile(
    r"whatsapp|gmail|compose|new message|inbox|outlook|mail|telegram|discord|slack|signal|teams|messenger|messages|instagram|"
    r"linkedin|twitter|x\.com|facebook|reddit|tweet|chat",
    re.I,
)
_SEND_KEYS = {"enter", "return"}
_SEND_LABEL = re.compile(r"\b(send|post|submit|publish|tweet|reply|share|pay|buy|purchase|order|checkout|confirm|delete|remove|erase|transfer|sign ?out|log ?out|install|uninstall)\b", re.I)


def voice_trust_enabled() -> bool:
    return os.environ.get("EVA_VOICE_TRUST", "").strip().lower() in {"1", "true", "yes", "on"}


@contextmanager
def voice_turn() -> Iterator[None]:
    """Mark everything run inside as the owner's own spoken request."""
    token = _voice_turn.set(True)
    try:
        yield
    finally:
        _voice_turn.reset(token)


def in_voice_turn() -> bool:
    return _voice_turn.get()


def _foreground_text() -> str:
    try:
        from ..desktop.windows import get_active_window

        active = get_active_window()
        return f"{getattr(active, 'title', '')} {getattr(active, 'process_name', '')}"
    except Exception:
        return ""


def _keys(args: dict[str, Any]) -> list[str]:
    raw = args.get("keys") if args.get("keys") is not None else args.get("key")
    if isinstance(raw, str):
        raw = re.split(r"[+\s,]+", raw)
    return [str(k).strip().lower() for k in (raw or []) if str(k).strip()]


def allow_reason(name: str, spec: Any, args: dict[str, Any], *, foreground: str | None = None) -> str:
    """Why a trusted voice turn may skip the prompt for this call, or "" when it may not."""
    if not voice_trust_enabled() or not in_voice_turn() or name not in ELIGIBLE_TOOLS:
        return ""
    args = args or {}
    front = _foreground_text() if foreground is None else foreground
    in_messaging_app = bool(_MESSAGING_WINDOW.search(front))

    if name == "radio_set" and str(args.get("kind", "")).lower() == "wifi" and str(args.get("state", "")).lower() == "off":
        return ""  # cuts NOVA's own connection; keep the explicit prompt
    if name in {"screen.press", "screen.hotkey"} and in_messaging_app and _SEND_KEYS & set(_keys(args)):
        return ""  # Enter in a chat or mail window sends
    if name == "screen.type_text" and in_messaging_app and re.search(r"[\r\n]", str(args.get("text") or "")):
        return ""  # a newline is an Enter
    if name == "screen.click":
        label = str(args.get("label") or (args.get("target") or {}).get("label") or "")
        if _SEND_LABEL.search(label):
            return ""
    if name == "analyze_screen":
        try:
            from ..vision.screen_vision import local_vision_enabled

            if not local_vision_enabled():
                return ""  # a cloud vision model would receive the screenshot
        except Exception:
            return ""
    return "voice_trust"
