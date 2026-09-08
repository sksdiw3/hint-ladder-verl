import json
import pytest
from hintladder.ladder import audit_leak, fullpath, generation_messages, public_input, validate_hint


def test_blind_l2_does_not_receive_privilege(facts):
    record = {"initial_observation": "Your task is to: find a mug", "initial_admissible_commands": ["look"], "hidden_facts": facts}
    with pytest.raises(ValueError):
        generation_messages("L2", record)
    messages = generation_messages("L2", public_input(record))
    assert set(json.loads(messages[-1]["content"])) == {"initial_observation", "initial_admissible_commands"}
    assert "mug 2" not in messages[-1]["content"]


@pytest.mark.parametrize("text", ["mug 2", "countertop", "counter top 1", "cabinet", "The mug is already clean."])
def test_fact_alias_audit(text, facts):
    assert audit_leak(text, facts)


def test_hint_contracts(facts):
    hint = "Explore the room systematically, inspect visible contents, track evidence, and satisfy all requested conditions before completing the household task."
    assert not validate_hint("L1", hint)
    assert not audit_leak(hint, facts)
    assert validate_hint("L1", "too short")
    assert validate_hint("HINTER", "The mug 2 is on countertop 1.", facts)
    assert validate_hint("L3", "Use the room.", facts)
    assert validate_hint("L2", "word " * 101)
    assert fullpath({"walkthrough_verified": True, "walkthrough_actions": ["look", "go to desk 1"]}) == "look -> go to desk 1"
    with pytest.raises(ValueError):
        fullpath({"walkthrough_verified": False, "walkthrough_actions": ["look"]})
