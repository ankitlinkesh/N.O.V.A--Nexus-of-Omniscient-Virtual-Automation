"""LLM triage: split a request into ordered steps and label each one.

Replaces guessing a request's category with phrase-matching rules. One short,
cache-friendly LLM call reads the request and returns steps, each labelled:

  command  a single exact device/app action (volume, media keys, open an app or
           site, play X on Spotify/YouTube, ...). Run by the fast-command rules.
  tool     one action needing a tool or lookup plus a little judgement.
  work     multi-step or on-screen work. Goes to the agent task runner.
  chat     just answer in words.

The label only chooses WHICH executor handles a step. It grants nothing: every
tool call still goes through the registry and the tool gate, so a wrong label can
make NOVA slower or less capable, never less safe. Any failure (endpoint down,
bad JSON, nothing usable) returns None and the caller falls back to the normal
routing, so triage can only add a better route, not remove the old one.

Measured on a local Qwen3-VL-4B over 36 realistic requests: ~0.5 s median, correct
kind for nearly all of them, with the model tending to over-split one action into
several same-kind steps. `merge_steps` collapses those, because running one action
twice is the failure to avoid.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import httpx

KINDS = ("command", "tool", "work", "chat")
MAX_STEPS = 4
TRIAGE_TIMEOUT_SECONDS = 15.0

SYSTEM_PROMPT = (
    "You are the dispatcher for a Windows desktop assistant. Split the user's request into ordered steps "
    "and label each step with ONE kind:\n"
    "- command: a single exact device/app action with a fixed meaning: volume up/down/set, mute, pause/play/next/"
    "previous media, current time or date, lock the PC, brightness, dark/light mode, open a named app, open a named "
    "website, play a named song/video on spotify or youtube.\n"
    "- tool: one action that needs a tool or lookup plus a little judgement: web search or weather or news, "
    "read/list/create a file, check disk space/battery/system status, describe what is on the screen, send a "
    "message to a named contact.\n"
    "- work: anything multi-step, ambiguous, or done by operating an app on screen: writing and sending an email, "
    "filling a form, booking, buying, researching and compiling, using an app that has no command, and ANY "
    "click, typing, key press, scrolling or calculation inside an app, even right after open-an-app. "
    "Opening an app and then doing something in it is ONE work step, never a command plus another step.\n"
    "- chat: just answer in words: greetings, jokes, math, general knowledge, opinions.\n"
    "Use exactly ONE step for a request that is one action or one task, however many details it has. Only split "
    "when the user clearly asks for several DIFFERENT things, joined by words like \"and\", \"then\" or commas, and "
    "never emit two steps of the same kind for one thing. Each step's text is the self-contained instruction for "
    "that step."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"kind": {"type": "string", "enum": list(KINDS)}, "text": {"type": "string"}},
                "required": ["kind", "text"],
            },
        }
    },
    "required": ["steps"],
}


@dataclass(frozen=True)
class TriageStep:
    kind: str
    text: str


def triage_enabled() -> bool:
    if os.environ.get("EVA_TRIAGE", "on").strip().lower() in {"0", "off", "false", "no"}:
        return False
    return bool(_endpoint())


def _endpoint() -> str:
    return (os.environ.get("EVA_TRIAGE_URL") or os.environ.get("CLOD_BASE_URL") or "").strip().rstrip("/")


def parse_steps(raw: object) -> list[TriageStep]:
    """Validate the model's JSON into steps. Anything malformed is dropped."""
    steps = raw.get("steps") if isinstance(raw, dict) else None
    if not isinstance(steps, list):
        return []
    parsed: list[TriageStep] = []
    for item in steps:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().lower()
        text = " ".join(str(item.get("text") or "").split())
        if kind in KINDS and text:
            parsed.append(TriageStep(kind, text))
    return parsed


def merge_steps(steps: list[TriageStep]) -> list[TriageStep]:
    """Collapse the model's over-splitting and cap the plan.

    Consecutive steps of the same kind are one thing for tool/work/chat (joined into
    one instruction). Commands are kept apart ("pause the music" and "set the volume
    to 20" are two actions) but an identical repeat is dropped.
    """
    merged: list[TriageStep] = []
    for step in steps:
        if merged and merged[-1].kind == step.kind:
            if step.kind == "command":
                if merged[-1].text.lower() != step.text.lower():
                    merged.append(step)
            else:
                merged[-1] = TriageStep(step.kind, f"{merged[-1].text} then {step.text}")
            continue
        merged.append(step)
    return merged[:MAX_STEPS]


async def triage_request(message: str) -> list[TriageStep] | None:
    """The labelled steps for `message`, or None to use the normal routing."""
    if not triage_enabled() or not str(message or "").strip():
        return None
    model = (os.environ.get("EVA_TRIAGE_MODEL") or os.environ.get("CLOD_MODEL") or "").strip()
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": 300,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": str(message)[:1500]}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "plan", "schema": SCHEMA, "strict": True}},
    }
    headers = {"Authorization": f"Bearer {os.environ.get('CLOD_API_KEY', '')}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(TRIAGE_TIMEOUT_SECONDS, connect=2.0)) as client:
            response = await client.post(f"{_endpoint()}/chat/completions", json=body, headers=headers)
        if response.status_code >= 400:
            return None
        content = response.json()["choices"][0]["message"]["content"]
        steps = merge_steps(parse_steps(json.loads(content)))
    except Exception:
        return None
    return steps or None
