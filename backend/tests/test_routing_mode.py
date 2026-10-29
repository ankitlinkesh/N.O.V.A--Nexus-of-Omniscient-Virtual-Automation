import pytest

from backend.eva.core import routing_mode
from backend.eva.security import tool_gate


@pytest.fixture(autouse=True)
def _clean_pending():
    tool_gate.reset_pending_calls()
    yield
    tool_gate.reset_pending_calls()


def test_default_is_llm_first_and_rules_first_restores_old_order(monkeypatch):
    monkeypatch.delenv("EVA_ROUTING", raising=False)
    assert routing_mode.llm_first_enabled()
    monkeypatch.setenv("EVA_ROUTING", "rules_first")
    assert not routing_mode.llm_first_enabled()
    assert routing_mode.use_rule_layers("open my gmail")


@pytest.mark.parametrize(
    "message",
    [
        "confirm act_0123456789ab",
        "gui: open notepad",
        "box: ls",
        "delegate research to the researcher",
        "eva control center",
        "explain act_0123456789ab",
        "pause the music",
        "can you skip this song please",
        "turn the volume up",
        "set volume to 30",
        "mute",
        "what time is it",
        "play pavazhamalli from spotify",
        "play the interstellar trailer on youtube",
        "open youtube and search lofi",
        "can you play despacito on spotify please",
        "send whatsapp to kutty saying hi",
        "send a whatsapp message to kutty saying hi",
    ],
)
def test_exact_and_authority_commands_stay_deterministic(message, monkeypatch):
    monkeypatch.setenv("EVA_ROUTING", "llm_first")
    assert routing_mode.use_rule_layers(message)


@pytest.mark.parametrize(
    "message",
    [
        "open my gmail",
        "go to github",
        "remind me to call mom tomorrow",
        "shut down the laptop",
        "tell me a joke",
    ],
)
def test_natural_messages_go_to_the_llm(message, monkeypatch):
    monkeypatch.setenv("EVA_ROUTING", "llm_first")
    assert not routing_mode.use_rule_layers(message)


def test_yes_no_only_stay_deterministic_while_an_action_is_pending(monkeypatch):
    monkeypatch.setenv("EVA_ROUTING", "llm_first")
    assert not routing_mode.use_rule_layers("yes")
    tool_gate.register_pending_call("act_0123456789ab", "close_app", {"app_name": "chrome"})
    assert routing_mode.use_rule_layers("yes")
    assert routing_mode.use_rule_layers("no")
