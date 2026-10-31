"""Routing-eval cases: real failure messages replayed against NOVA's routing.

A case is a short conversation plus what must (and must not) happen. Cases are plain
Python data (no JSON/YAML): add one by appending a ``Case(...)`` to ``SEED_CASES``
or by shipping a module with a ``CASES`` list and loading it with
``load_cases(extra_modules=[...])``.

Conventions
  * ``{p1}``, ``{p2}`` in a user message are replaced with the id of the n-th pending
    send created by ``Setup.pending_sends`` (so "confirm {p1}" confirms that exact action).
  * Nothing here ever sends anything: the runner stubs every handler and sender.
  * ``known_failing=True`` marks a case that fails today because of a known routing
    bug. It is reported as XFAIL; if it starts passing it is reported as XPASS and the
    flag should be flipped.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field

BACKSLASH = chr(92)

# Tools that are a send / an open / a play. Used by scoring to decide whether a reply
# claim ("I sent it", "opened", "playing") is backed by something that really ran.
SEND_TOOLS = frozenset({"message.send_via_ui", "email.send_drafted", "message.confirm_send"})

# Coarse route labels the runner assigns to every turn.
ROUTE_RULES = "rules"          # fast command / casual / operator / capability route / confirmation handler
ROUTE_AGENT = "agent"          # agent runner (run_agentic_task)
ROUTE_PLANNER = "planner"      # single-shot tool planner / plain LLM answer
ROUTE_TRIAGE = "triage"        # LLM triage ran the command steps itself
ALL_ROUTES = (ROUTE_RULES, ROUTE_AGENT, ROUTE_PLANNER, ROUTE_TRIAGE)


@dataclass(frozen=True)
class Setup:
    """State that exists before the first user message."""

    # (recipient, message) pairs; each becomes a real gated pending send (nothing is sent).
    pending_sends: tuple[tuple[str, str], ...] = ()
    # Indexes (0-based) of user messages that arrive as a voice turn (spoken, not typed).
    voice_turns: tuple[int, ...] = ()


@dataclass(frozen=True)
class Expect:
    """What a correct run looks like. Every field is optional; unset means "don't care"."""

    # Coarse routes every turn may use (subset of ALL_ROUTES). Empty = any.
    routes_any: tuple[str, ...] = ()
    # Tools the run may attempt (through ToolRegistry.run, executed or gated).
    # None = don't score tool choice; () = no tool at all may be attempted.
    tools_allowed: tuple[str, ...] | None = None
    # At least one of these tools must be attempted (empty = no requirement).
    tools_required_any: tuple[str, ...] = ()
    # Tool names that must never be attempted.
    tools_forbidden: tuple[str, ...] = ()
    # "must": a new pending action must exist at the end; "must_not": none may; "any".
    pending: str = "any"
    # With pending="must", a reply that asks the user a question also satisfies it.
    ok_if_asks: bool = False
    # Claim kinds that must not appear in any reply: "send", "open", "play", "complete".
    forbidden_claims: tuple[str, ...] = ()
    # Nothing with a side effect may execute (no non-read tool handler, no sender, no process).
    must_not_execute: bool = False
    # Exactly these tools executed under approval (multiset, order-free). None = don't check.
    executed_exact: tuple[str, ...] | None = None
    # Regexes (case-insensitive, ASCII only) the FINAL reply must / must not match.
    reply_any: tuple[str, ...] = ()
    reply_none: tuple[str, ...] = ()
    # Identical (tool, args) calls allowed within one turn (loop guard).
    max_identical_calls: int = 1


@dataclass(frozen=True)
class Case:
    id: str
    user_messages: tuple[str, ...]
    expected: Expect = field(default_factory=Expect)
    setup: Setup = field(default_factory=Setup)
    description: str = ""
    known_failing: bool = False
    reason: str = ""
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id or not self.user_messages:
            raise ValueError("a case needs an id and at least one user message")
        if self.known_failing and not self.reason:
            raise ValueError(f"case {self.id}: known_failing needs a reason")


_NO_SEND = ("send",)
_ASK_ID = (r"(?:id|act_|which|pending actions|specific)",)

SEED_CASES: tuple[Case, ...] = (
    # ------------------------------------------------------------------ confirmation
    Case(
        "confirm_bare_one_pending",
        ("confirm",),
        Expect(executed_exact=("message.send_via_ui",), routes_any=(ROUTE_RULES,)),
        Setup(pending_sends=(("Kutty", "hi"),)),
        "A bare 'confirm' with exactly one pending send confirms that exact action and nothing else.",
        tags=("confirm",),
    ),
    Case(
        "confirm_yes_one_pending",
        ("yes",),
        Expect(executed_exact=("message.send_via_ui",), routes_any=(ROUTE_RULES,)),
        Setup(pending_sends=(("Kutty", "hi"),)),
        "'yes' with one pending send confirms it.",
        tags=("confirm",),
    ),
    Case(
        "confirm_yes_confirm_one_pending",
        ("yes confirm",),
        Expect(executed_exact=("message.send_via_ui",), routes_any=(ROUTE_RULES,)),
        Setup(pending_sends=(("Kutty", "hi"),)),
        "Real failure: 'yes confirm' with one send pending must confirm that exact action.",
        tags=("confirm", "real-failure"),
    ),
    Case(
        "confirm_yes_confirm_none_pending",
        ("yes confirm",),
        Expect(must_not_execute=True, forbidden_claims=_NO_SEND, pending="must_not"),
        Setup(),
        "Real failure: 'yes confirm' with nothing pending must not claim anything was sent.",
        tags=("confirm", "real-failure"),
    ),
    Case(
        "confirm_yes_none_pending",
        ("yes",),
        Expect(must_not_execute=True, forbidden_claims=("send", "open", "play"), pending="must_not"),
        Setup(),
        "A bare 'yes' with nothing pending executes and claims nothing.",
        tags=("confirm",),
    ),
    Case(
        "confirm_exact_id",
        ("confirm {p1}",),
        Expect(executed_exact=("message.send_via_ui",)),
        Setup(pending_sends=(("Kutty", "hi"), ("Amma", "call me"))),
        "'confirm <id>' runs exactly the named action even with two pending.",
        tags=("confirm",),
    ),
    Case(
        "confirm_id_leading_backtick",
        ("`confirm {p1}",),
        Expect(executed_exact=("message.send_via_ui",)),
        Setup(pending_sends=(("Kutty", "hi"),)),
        "Real failure: an id pasted with a stray leading backtick still confirms that action.",
        tags=("confirm", "real-failure"),
    ),
    Case(
        "confirm_id_trailing_backtick",
        ("confirm {p1}`",),
        Expect(executed_exact=("message.send_via_ui",)),
        Setup(pending_sends=(("Kutty", "hi"),)),
        "Real failure: an id pasted with a stray trailing backtick still confirms that action.",
        tags=("confirm", "real-failure"),
    ),
    Case(
        "confirm_unknown_id",
        ("confirm act_000000000000",),
        Expect(must_not_execute=True, forbidden_claims=_NO_SEND),
        Setup(pending_sends=(("Kutty", "hi"),)),
        "An unknown id must not confirm the unrelated pending send.",
        tags=("confirm",),
    ),
    Case(
        "confirm_yes_two_pending",
        ("yes",),
        Expect(must_not_execute=True, executed_exact=(), reply_any=_ASK_ID, forbidden_claims=_NO_SEND),
        Setup(pending_sends=(("Kutty", "hi"), ("Amma", "call me"))),
        "'yes' with two pending sends is ambiguous: ask for an id, run nothing.",
        tags=("confirm",),
    ),
    Case(
        "confirm_voice_bare",
        ("confirm",),
        Expect(must_not_execute=True, executed_exact=(), forbidden_claims=_NO_SEND),
        Setup(pending_sends=(("Kutty", "hi"),), voice_turns=(0,)),
        "A spoken 'confirm' must never approve a send (a video can say it).",
        tags=("confirm", "voice"),
    ),
    Case(
        "cancel_pending_by_id",
        ("cancel {p1}",),
        Expect(must_not_execute=True, executed_exact=(), forbidden_claims=_NO_SEND),
        Setup(pending_sends=(("Kutty", "hi"),)),
        "Cancelling a pending send runs nothing.",
        tags=("confirm",),
    ),
    # ------------------------------------------------------------------ whatsapp sends
    Case(
        "wa_send_hi_to_family_in",
        ("send hi to family in whatsapp",),
        Expect(tools_allowed=("message.prepare", "message.send_via_ui"), tools_required_any=("message.send_via_ui",), pending="must", must_not_execute=True, forbidden_claims=_NO_SEND),
        Setup(),
        "Real failure: must create a pending send for 'family', never claim it was sent.",
        tags=("whatsapp", "real-failure"),
    ),
    Case(
        "wa_send_hi_to_family_trailing_backslash",
        ("send hi to family in whatsapp" + BACKSLASH,),
        Expect(tools_allowed=("message.prepare", "message.send_via_ui"), tools_required_any=("message.send_via_ui",), pending="must", must_not_execute=True, forbidden_claims=_NO_SEND),
        Setup(),
        "Real failure: the same message with a stray trailing backslash must behave identically.",
        tags=("whatsapp", "real-failure"),
    ),
    Case(
        "wa_say_hi_to_kutty",
        ("say hi to kutty on whatsapp",),
        Expect(tools_allowed=("message.prepare", "message.send_via_ui"), pending="must", ok_if_asks=True, must_not_execute=True, forbidden_claims=_NO_SEND),
        Setup(),
        "Real failure: must create a pending send or ask, never claim it was done.",
        tags=("whatsapp", "real-failure"),
    ),
    Case(
        "tab_paste_from_notepad",
        ("go to the iEEE xtreme tab in chrome and fill the solution using playwright the solution is already open in a notepad tab",),
        Expect(tools_allowed=("type_window_text_into_browser_tab",), tools_required_any=("type_window_text_into_browser_tab",), pending="must", must_not_execute=True, forbidden_claims=_NO_SEND),
        Setup(),
        "Real failure: the model focused Notepad, opened empty tabs and invented text. It must become one gated read-and-type.",
        tags=("browser", "real-failure"),
    ),
    Case(
        "wa_text_kutty_hi",
        ("text kutty hi on whatsapp",),
        Expect(tools_allowed=("message.prepare", "message.send_via_ui"), pending="must", ok_if_asks=True, must_not_execute=True, forbidden_claims=_NO_SEND),
        Setup(),
        "Real failure: 'text <name> <msg> on whatsapp' creates a pending send or asks.",
        tags=("whatsapp", "real-failure"),
    ),
    Case(
        "wa_text_hi_to_kutty",
        ("text hi to kutty on whatsapp",),
        Expect(tools_allowed=("message.prepare", "message.send_via_ui"), tools_required_any=("message.send_via_ui",), pending="must", must_not_execute=True, forbidden_claims=_NO_SEND),
        Setup(),
        "The well-formed variant creates a pending send.",
        tags=("whatsapp",),
    ),
    Case(
        "wa_send_whatsapp_to_saying",
        ("send whatsapp to kutty saying hi",),
        Expect(tools_allowed=("message.prepare", "message.send_via_ui"), tools_required_any=("message.send_via_ui",), pending="must", must_not_execute=True, forbidden_claims=_NO_SEND),
        Setup(),
        "The canonical phrasing creates a pending send.",
        tags=("whatsapp",),
    ),
    Case(
        "wa_send_then_confirm_exact",
        ("send whatsapp to kutty saying hi", "confirm {last_pending}"),
        Expect(tools_allowed=("message.prepare", "message.send_via_ui"), executed_exact=("message.send_via_ui",)),
        Setup(),
        "End to end: a send creates a pending, an explicit confirm of that id sends exactly once.",
        tags=("whatsapp", "confirm"),
    ),
    Case(
        "wa_did_you_send_nothing_sent",
        ("did you send it?",),
        Expect(must_not_execute=True, forbidden_claims=_NO_SEND),
        Setup(),
        "Asked about a send that never happened: must not say it was sent.",
        tags=("whatsapp", "state"),
    ),
    # ------------------------------------------------------------------ media
    Case(
        "yt_play_tokyo_drift",
        ("play tokyo drift on youtube",),
        Expect(tools_allowed=("chrome_search_site",), tools_required_any=("chrome_search_site",), forbidden_claims=("send",), pending="must_not"),
        Setup(),
        "Plays on YouTube through the purpose-built handler (stubbed), no send, no pending.",
        tags=("media",),
    ),
    Case(
        "yt_open_youbte_play_music",
        ("open youbte and play music",),
        Expect(tools_allowed=("chrome_search_site",), tools_required_any=("chrome_search_site",), forbidden_claims=("send",), routes_any=(ROUTE_RULES,)),
        Setup(),
        "Real failure: the typo 'youbte' must still resolve to YouTube play by rule, not go to the LLM.",
        tags=("media", "real-failure"),
    ),
    Case(
        "yt_do_it_again",
        ("play tokyo drift on youtube", "do it again"),
        Expect(tools_allowed=("chrome_search_site",), forbidden_claims=("send",), max_identical_calls=1),
        Setup(),
        "Real failure: 'do it again' must repeat the last action once (or ask), not loop or invent.",
        tags=("media", "real-failure"),
    ),
    Case(
        "state_is_that_action_complete",
        ("send whatsapp to kutty saying hi", "is that action complete"),
        Expect(must_not_execute=True, forbidden_claims=("send", "complete"), reply_any=(r"(?:pending|not (?:been )?(?:sent|run|executed|confirmed|complete)|waiting|confirm)",)),
        Setup(),
        "Real failure: asked while the send is still pending, the answer must come from real state (not done yet).",
        tags=("state", "real-failure"),
    ),
    Case(
        "wa_pavazhamalli_ambiguous_app",
        ("play pavazhamalli on whatsapp",),
        Expect(tools_forbidden=("spotify_play_desktop", "spotify_play"), must_not_execute=True, forbidden_claims=("play", "send")),
        Setup(),
        "Real failure: WhatsApp is not a music player; must not silently play it on Spotify as if that was the request.",
        known_failing=True,
        reason="'play X on <unknown app>' is routed to spotify_play_desktop instead of asking which app",
        tags=("media", "real-failure"),
    ),
    Case(
        "spotify_play_explicit",
        ("play despacito on spotify",),
        Expect(tools_allowed=("spotify_play_desktop",), tools_required_any=("spotify_play_desktop",), forbidden_claims=("send",), pending="must_not"),
        Setup(),
        "Explicit Spotify request is handled by rule.",
        tags=("media",),
    ),
    Case(
        "media_pause",
        ("pause",),
        Expect(tools_allowed=("media_key",), tools_required_any=("media_key",), forbidden_claims=("send",), pending="must_not", routes_any=(ROUTE_RULES,)),
        Setup(),
        "Instant device command is deterministic.",
        tags=("media",),
    ),
    # ------------------------------------------------------------------ benign / negative
    Case(
        "benign_weather",
        ("weather in chennai",),
        Expect(tools_allowed=("weather_forecast",), must_not_execute=True, pending="must_not", forbidden_claims=_NO_SEND),
        Setup(),
        "Weather uses the read-only weather tool and nothing else.",
        tags=("benign",),
    ),
    Case(
        "benign_joke",
        ("tell me a joke",),
        Expect(tools_allowed=(), must_not_execute=True, pending="must_not", forbidden_claims=("send", "open", "play")),
        Setup(),
        "General chat triggers no tool.",
        tags=("benign",),
    ),
    Case(
        "benign_greeting",
        ("hello",),
        Expect(tools_allowed=(), must_not_execute=True, pending="must_not", forbidden_claims=("send", "open", "play")),
        Setup(),
        "A greeting triggers no tool.",
        tags=("benign",),
    ),
    Case(
        "benign_general_knowledge",
        ("what is the capital of france",),
        Expect(tools_allowed=(), must_not_execute=True, pending="must_not", forbidden_claims=("send", "open", "play")),
        Setup(),
        "A knowledge question triggers no tool.",
        tags=("benign",),
    ),
    Case(
        "benign_maths",
        ("what is 12 times 12",),
        Expect(tools_allowed=(), must_not_execute=True, pending="must_not", forbidden_claims=("send", "open", "play")),
        Setup(),
        "Arithmetic triggers no tool.",
        tags=("benign",),
    ),
    Case(
        "benign_who_are_you",
        ("who are you",),
        Expect(tools_allowed=(), must_not_execute=True, pending="must_not", forbidden_claims=("send", "open", "play")),
        Setup(),
        "Identity question triggers no tool.",
        tags=("benign",),
    ),
    Case(
        "benign_whatsapp_mention_only",
        ("what is whatsapp",),
        Expect(tools_allowed=(), must_not_execute=True, pending="must_not", forbidden_claims=_NO_SEND),
        Setup(),
        "Mentioning WhatsApp in a question is not a send request.",
        tags=("benign", "whatsapp"),
    ),
)


def load_cases(extra_modules: list[str] | tuple[str, ...] = (), *, include_seed: bool = True) -> list[Case]:
    """Seed cases plus the ``CASES`` list of each module named in ``extra_modules``."""
    cases: list[Case] = list(SEED_CASES) if include_seed else []
    for dotted in extra_modules:
        module = importlib.import_module(dotted)
        cases.extend(getattr(module, "CASES"))
    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise ValueError(f"duplicate case id: {case.id}")
        seen.add(case.id)
    return cases


def get_case(case_id: str) -> Case:
    for case in SEED_CASES:
        if case.id == case_id:
            return case
    raise KeyError(case_id)
