from types import SimpleNamespace

import pytest

from hintladder.privilege import hidden_facts_from_initial, render_walkthrough


def fact(name, *arguments):
    return SimpleNamespace(name=name, arguments=[SimpleNamespace(name=value) for value in arguments])


def test_transitive_containment_uses_fact_supported_pickup_source():
    facts = [fact("inreceptacle", "mug 1", "coffeemachine 1"),
             fact("inreceptacle", "mug 1", "countertop 1"), fact("isclean", "mug 1")]
    hidden = hidden_facts_from_initial(facts, ["take mug 1 from coffeemachine 1", "put mug 1 in/on cabinet 2"])
    assert hidden["goal_object_location"] == "coffeemachine 1"
    assert hidden["destination_receptacle"] == "cabinet 2"
    assert hidden["goal_object_initial_states"] == {"hot": False, "clean": True, "cool": False}
    with pytest.raises(ValueError, match="initial facts"):
        hidden_facts_from_initial(facts, ["take mug 1 from drawer 3"])


def test_released_walkthrough_entity_encoding_is_explicit():
    infos = {"mug_bar_1": SimpleNamespace(name="mug 2"), "table_bar_1": SimpleNamespace(name="table 1")}
    assert render_walkthrough(["take mug_bar_1 from table_bar_1", "look"], infos) == ["take mug 2 from table 1", "look"]
    with pytest.raises(ValueError, match="unknown encoded"):
        render_walkthrough(["take apple_bar_8"], infos)
