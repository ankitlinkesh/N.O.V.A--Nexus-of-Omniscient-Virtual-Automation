"""Routing/honesty fixes from the live chat log: natural confirms, WhatsApp phrasings, send claims,
"did it send?" answers and "do it again". Nothing here sends, confirms for real, or calls a model."""

from __future__ import annotations

import pytest

from backend.eva.agent.claim_check import NO_SEND_NOTE, replace_send_claims, unbacked_send_claim
from backend.eva.core import last_action
from backend.eva.core.intent_router import _whatsapp_message_parts, classify_capability_intent
from backend.eva.core.request_normalizer import canonicalize_request
from backend.eva.core.routing_mode import must_stay_deterministic
from backend.eva.permissions import confirmation
from backend.eva.permissions.ledger import cancel_pending_action, confirm_pending_action, create_pending_action
from backend.eva.permissions.pending_actions import EvaPendingAction
from backend.eva.security import tool_gate
from backend.eva.security.voice_trust import voice_turn

BS = chr(92)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("EVA_PENDING_ACTION_LEDGER_PATH", str(tmp_path / "pending.jsonl"))
    tool_gate.reset_pending_calls()
    last_action.reset()
    ran = []
    # The ledger confirm is real (a temp file); the execution after it is a recorder, so nothing can run.
    monkeypatch.setattr(confirmation, "_with_execution", lambda action_id, result, session_id=None: ran.append(action_id) or f"EXECUTED {action_id}")
    yield ran
    tool_gate.reset_pending_calls()
    last_action.reset()


def make_pending(*, override=False, held=True, summary="Send WhatsApp message to dad: hi"):
    action = EvaPendingAction.new(
        action_type="message.send.whatsapp", risk_level="medium", risk_category="external_message", summary=summary,
        requires_confirmation=True, requires_override=override, source="tool_gate", executor_available=True,
    )
    create_pending_action(action)
    if held:
        tool_gate.register_pending_call(action.id, "message.send_via_ui", {"recipient": "dad", "message": "hi"})
    return action


# 1. natural confirmation phrases -------------------------------------------------------------

VARIANTS = ["yes confirm", "ok confirm", "okay confirm", "please confirm", "confirm it", "go ahead and send it", "sure send it",
            "Yes, confirm.", "yes confirm please", "confirm", "send it"]


@pytest.mark.parametrize("phrase", VARIANTS)
def test_natural_confirm_confirms_the_one_pending_send(phrase, isolated):
    action = make_pending()
    reply = confirmation.handle_confirmation_command(phrase)
    assert isolated == [action.id] and reply == f"EXECUTED {action.id}"


@pytest.mark.parametrize("phrase", ["yes confirm", "go ahead and send it", "sure send it"])
def test_voice_turn_never_confirms(phrase, isolated):
    make_pending()
    with voice_turn():
        reply = confirmation.handle_confirmation_command(phrase)
    assert isolated == [] and "specific pending action ID" in reply


def test_two_pending_asks_for_the_id(isolated):
    make_pending()
    make_pending()
    reply = confirmation.handle_confirmation_command("yes confirm")
    assert isolated == [] and "specific pending action ID" in reply


def test_override_class_is_never_confirmed_by_a_natural_phrase(isolated):
    make_pending(override=True)
    reply = confirmation.handle_confirmation_command("yes confirm")
    assert isolated == [] and "specific pending action ID" in reply


def test_pending_without_a_held_call_is_not_confirmed(isolated):
    make_pending(held=False)
    confirmation.handle_confirmation_command("ok confirm")
    assert isolated == []


@pytest.mark.parametrize("phrase", ["confirm override act_abc123", "yes confirm override", "confirm the thing tomorrow", "yes sure maybe", "ok", "no"])
def test_not_a_bare_confirm(phrase):
    assert not confirmation.is_bare_confirm(phrase)


def test_yes_confirm_with_nothing_pending_stays_deterministic_and_honest(isolated):
    assert must_stay_deterministic("yes confirm")
    assert "specific pending action ID" in confirmation.handle_confirmation_command("yes confirm")
    assert isolated == []


# 2. stray trailing junk ------------------------------------------------------------------------

def test_trailing_backslash_is_stripped_and_parsed():
    raw = "send hi to family in whatsapp" + BS
    assert canonicalize_request(raw) == "send hi to family in whatsapp"
    assert _whatsapp_message_parts(raw) == ("family", "hi")
    assert must_stay_deterministic(raw)
    assert classify_capability_intent(raw)["suggested_route"] == "whatsapp_message_prepare"


@pytest.mark.parametrize("junk", ["`", "/", '"', "'", BS + BS])
def test_other_trailing_junk(junk):
    assert _whatsapp_message_parts("send hi to dad on whatsapp" + junk) == ("dad", "hi")


def test_inner_punctuation_and_paired_quotes_are_kept():
    assert _whatsapp_message_parts("send see you at 5:30, ok to dad on whatsapp") == ("dad", "see you at 5:30, ok")
    assert canonicalize_request('copy "two  words" to my clipboard') == 'copy "two  words" to my clipboard'
    assert canonicalize_request("open the notes' folder") .endswith("notes' folder")


# 3. "say hi to X on whatsapp" -----------------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("say hi to kutty on whatsapp", ("kutty", "hi")),
        ("say good morning to kutty via whatsapp", ("kutty", "good morning")),
        ("tell kutty I am late on whatsapp", ("kutty", "I am late")),
        ("tell kutty that I am late in whatsapp", ("kutty", "I am late")),
        ("message kutty hi on whatsapp", ("kutty", "hi")),
        ("say hi to kutty on whatsapp.", ("kutty", "hi")),
    ],
)
def test_new_whatsapp_phrasings(text, expected):
    assert _whatsapp_message_parts(text) == expected
    assert must_stay_deterministic(text)


@pytest.mark.parametrize("text", ["say hi to kutty", "tell me a joke", "say something on whatsapp", "what is whatsapp"])
def test_unrelated_sentences_are_not_whatsapp_sends(text):
    assert _whatsapp_message_parts(text) is None


# 4. send claims -------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "reply",
    [
        "Hi kutty! I've said hi to you on WhatsApp.",
        "I messaged dad for you.",
        "I have texted her already.",
        "I pinged the group.",
        "I told kutty hello on WhatsApp.",
        "Message sent!",
        "Message 'hi' to family on WhatsApp has been sent successfully.",
        "I've just sent it.",
    ],
)
def test_widened_claims_are_caught(reply):
    assert unbacked_send_claim(reply)


@pytest.mark.parametrize(
    "reply",
    [
        'He wrote "I sent the message yesterday" in his note.',
        "I said that before.",
        "I told you earlier that it is raining.",
        "Do you want me to message dad?",
        "A text message is short.",
        "Texting is fun.",
        NO_SEND_NOTE,
    ],
)
def test_unrelated_sentences_are_not_claims(reply):
    assert not unbacked_send_claim(reply)


def test_claim_sentence_is_replaced_not_appended():
    out = replace_send_claims("Sure thing. I've said hi to you on WhatsApp. Anything else?")
    assert out == f"Sure thing. {NO_SEND_NOTE} Anything else?"
    assert "said hi" not in out and not unbacked_send_claim(out)
    assert replace_send_claims("Message sent! I've texted him.").count("I have not sent anything") == 1


# 5. status questions ----------------------------------------------------------------------------

@pytest.mark.parametrize("q", ["is that action complete", "Is that action complete?", "did it send", "was it sent", "did it go through", "has it been sent", "did you send it"])
def test_status_questions_are_deterministic(q):
    assert last_action.is_status_question(q) and must_stay_deterministic(q)


@pytest.mark.parametrize("q", ["is the sky complete", "did it rain", "send it", "what is the time"])
def test_not_status_questions(q):
    assert not last_action.is_status_question(q)


def test_status_with_no_record():
    reply = last_action.last_action_status()
    assert "Nothing is pending" in reply and "no record" in reply


def test_status_pending_confirmed_cancelled():
    action = make_pending()
    assert "still waiting for your confirmation" in last_action.last_action_status() and "nothing has been sent" in last_action.last_action_status()
    confirm_pending_action(action.id)
    assert "no record of its result" in last_action.last_action_status()
    last_action.note_execution(action.id, True, "Message sent to dad")
    assert "confirmed and ran" in last_action.last_action_status() and "Message sent to dad" in last_action.last_action_status()
    last_action.note_execution(action.id, False, "WhatsApp window not found")
    assert "did not complete: WhatsApp window not found" in last_action.last_action_status()
    other = make_pending()
    cancel_pending_action(other.id)
    assert "cancelled" in last_action.last_action_status()


def test_fast_command_answers_status_from_the_ledger():
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.tools.registry import ToolRegistry

    reply, source = maybe_handle_fast_command("did it send", ToolRegistry())
    assert source == "fast-command" and "Nothing is pending" in reply


def test_execution_is_recorded_for_the_status_answer():
    action = make_pending()
    confirmation._record_execution(action.id, {"ok": True, "text": "sent to dad"})
    confirm_pending_action(action.id)
    assert "sent to dad" in last_action.last_action_status()


# 6. "do it again" -------------------------------------------------------------------------------

@pytest.mark.parametrize("q", ["do it again", "again", "repeat that", "Same again", "do that again", "once more"])
def test_repeat_phrases(q):
    assert last_action.is_repeat_request(q) and must_stay_deterministic(q)


def test_repeat_phrases_do_not_overlap_confirms():
    assert not last_action.is_repeat_request("do it") and not confirmation.is_bare_confirm("do it again")


def test_nothing_to_repeat_is_said_honestly():
    assert last_action.last_request() == ""
    assert last_action.repeat_target() == (None, last_action.NO_PREVIOUS_REQUEST)


def test_a_spoken_again_never_repeats(isolated):
    last_action.remember_request("send hi to kutty on whatsapp")
    with voice_turn():
        assert last_action.repeat_target() == (None, last_action.VOICE_REPEAT_REFUSED)
    assert last_action.repeat_target() == ("send hi to kutty on whatsapp", "")


def test_each_chat_has_its_own_last_request():
    last_action.remember_request("open spotify", "a")
    last_action.remember_request("send hi to kutty on whatsapp", "b")
    assert last_action.last_request("a") == "open spotify" and last_action.last_request("b").startswith("send hi")
    assert last_action.last_request("c") == ""


def test_a_turn_handled_by_the_model_is_not_replaced_by_an_older_request():
    last_action.remember_request("send hi to kutty on whatsapp", "s")
    last_action.forget_request("s")  # the next turn went to the model
    assert last_action.repeat_target("s")[0] is None


def test_an_old_request_is_not_repeated(monkeypatch):
    last_action.remember_request("send hi to kutty on whatsapp", "s")
    later = __import__("time").time() + last_action.REPEAT_WINDOW_SECONDS + 1
    monkeypatch.setattr(last_action.time, "time", lambda: later)
    assert last_action.last_request("s") == ""


def test_control_messages_are_not_remembered():
    last_action.remember_request("send hi to kutty on whatsapp")
    for text in ("yes confirm", "confirm act_0123456789ab", "did it send", "do it again", "cancel act_0123456789ab", "pending actions"):
        last_action.remember_request(text)
    assert last_action.last_request() == "send hi to kutty on whatsapp"


def test_repeat_of_a_send_makes_a_new_pending_action_and_sends_nothing(monkeypatch, isolated):
    from backend.eva.api import routes

    sent = []
    monkeypatch.setattr("backend.eva.media.whatsapp_desktop.send_whatsapp_desktop", lambda *a, **k: sent.append((a, k)) or {"ok": True})
    ids = []
    for _ in range(2):  # the original request, then the "do it again" re-run of the remembered text
        message = "send hi to kutty on whatsapp" if not ids else last_action.last_request()
        classification = classify_capability_intent(message)
        reply, _source = routes._handle_capability_route(message, classification, {}, None, "s1")
        assert "I did not send anything yet" in reply
        ids.append(reply.split("ID: ")[1].split()[0])
        last_action.remember_request(message)
    assert ids[0] != ids[1] and sent == [] and isolated == []
    assert tool_gate.get_pending_call(ids[1]) is not None


@pytest.mark.parametrize("phrase", ["yes please", "go ahead", "sure", "ok please", "yeah please", "yes", "do it", "ok do it",
                                    "yes do it", "sure, do it", "approve", "approve it", "okay"])
def test_ambiguous_agreement_never_confirms_a_send(phrase, isolated):
    # "yes please" answers whatever was asked last, which may not be the pending send.
    make_pending()
    reply = confirmation.handle_confirmation_command(phrase)
    assert isolated == [] and "say `confirm`" in reply


def test_agreement_with_nothing_pending_is_left_to_the_chat(isolated):
    assert confirmation.handle_confirmation_command("yes") == ""


@pytest.mark.parametrize("phrase", ["sure, do it", "ok do it", "yes do it", "yeah go ahead"])
def test_agreement_with_a_pending_send_stays_with_the_rules(phrase, isolated):
    make_pending()
    assert must_stay_deterministic(phrase)
