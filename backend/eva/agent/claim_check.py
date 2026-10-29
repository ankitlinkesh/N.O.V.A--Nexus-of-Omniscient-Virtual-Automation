"""Catch "I finished" when the run never did what the goal asked for.

The critic (``critic.py``) only gates completion when a delegation contract is enforcing, and
with no contract it accepts everything. In practice that let a 4B planner open Calculator,
stop, and report "I finished the task ... (verified)" for a goal that also asked for four
clicks, because the step it DID run was verified.

This is a deterministic, evidence-only check, the same kind of outside check the research
notes recommend over asking another model: it reads the goal and the steps that actually ran
and lists the parts of the goal that have no matching successful step. It is conservative on
purpose, so it only names a part when the goal clearly asked for it AND no step of that kind
succeeded:

  * click / press / type / scroll / fill  -> a successful ``screen.*`` or ``web.*`` input step;
  * each quoted label in a click goal      -> at least that many successful click steps;
  * send an email / message               -> a successful send step (a draft is not a send).

It never blocks or undoes anything. The caller appends the finding to the reply as a plain
"not done" note and marks the task attempted, so the user is told the truth.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

_CLICK = re.compile(r"\b(click|double[- ]click|right[- ]click)\b", re.I)
# "what type of music" is not a request to type.
_TYPE = re.compile(r"\b(type(?!\s+(of|is|are|and|or)\b)|typing|enter the text|write into|fill in|fill out|fill the)\b", re.I)
_PRESS = re.compile(r"\b(press|hit)\s+(the\s+)?(key|enter|escape|esc|tab|ctrl|alt|shift|f\d+|[a-z]\b)", re.I)
_SCROLL = re.compile(r"\bscroll\b", re.I)
_SEND = re.compile(r"\b(send|sent|email|e-mail|mail|message|text|whatsapp)\b", re.I)
_SEND_VERB = re.compile(r"\bsend\b", re.I)
_QUOTED = re.compile(r"[\"“']([^\"”']{1,40})[\"”']")

_CLICK_TOOLS = {"screen.click", "web.click"}
_TYPE_TOOLS = {"screen.type_text", "web.type", "screen.submit_form"}
_PRESS_TOOLS = {"screen.press", "screen.hotkey"}
_SCROLL_TOOLS = {"screen.scroll"}
_SEND_TOOLS = {"message.send_via_ui", "email.send_drafted"}


def _ok_tools(steps: Iterable[Any]) -> list[str]:
    return [str(getattr(step, "tool_name", "") or "") for step in steps if getattr(step, "status", "") == "done" and getattr(step, "tool_name", None)]


def unsupported_parts(goal: str, steps: Iterable[Any]) -> list[str]:
    """The parts of `goal` with no successful matching step (empty when nothing is missing)."""
    goal = str(goal or "")
    ran = _ok_tools(steps)
    missing: list[str] = []

    clicks = sum(1 for tool in ran if tool in _CLICK_TOOLS)
    if _CLICK.search(goal):
        labels = [label.strip() for label in _QUOTED.findall(goal) if label.strip()]
        if clicks == 0:
            missing.append("the click(s) you asked for")
        elif len(labels) > clicks:
            missing.append(f"{len(labels) - clicks} of the {len(labels)} clicks you named")
    if _TYPE.search(goal) and not any(tool in _TYPE_TOOLS for tool in ran):
        missing.append("typing the text")
    if _PRESS.search(goal) and not any(tool in _PRESS_TOOLS for tool in ran):
        missing.append("the key press")
    if _SCROLL.search(goal) and not any(tool in _SCROLL_TOOLS for tool in ran):
        missing.append("the scrolling")
    # A draft or a prepared message is not a send; only an explicit "send" in the goal counts.
    if _SEND_VERB.search(goal) and _SEND.search(goal) and not any(tool in _SEND_TOOLS for tool in ran):
        missing.append("sending it (nothing was sent)")
    return missing


def unsupported_note(goal: str, steps: Iterable[Any]) -> str:
    missing = unsupported_parts(goal, steps)
    if not missing:
        return ""
    return f" (Note: I have no record of {'; '.join(missing)}, so this may be only partly done.)"
