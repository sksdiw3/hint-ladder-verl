import pytest
from hintladder.behavior import episode_metrics, aggregate


def steps(commands):
    return [{"executed_action": command, "is_action_valid": command != "nonsense", "output": f"<action>{command}</action>",
             "admissible_commands": [c for c in commands if c != "nonsense"]} for command in commands]


def test_three_episodes(facts):
    first = episode_metrics(steps(["go to countertop 1", "take mug 2 from countertop 1"]), facts, True)
    second = episode_metrics(steps(["go to drawer 1", "open drawer 1", "nonsense", "take mug 2 from drawer 1"]), facts, False)
    third = episode_metrics(steps(["look", "go to cabinet 1"]), facts, False)
    result = aggregate([first, second, third])
    assert result["hint_ladder/direct_location_hit_rate"] == pytest.approx(1/3)
    assert result["hint_ladder/query_before_pickup_rate"] == pytest.approx(2/3)
    assert result["hint_ladder/invalid_action_rate"] == 1/8
    assert result["hint_ladder/steps_to_pickup_mean"] == 3
    assert result["hint_ladder/success_rate"] == pytest.approx(1/3)


def test_thinking_fails(facts):
    row = steps(["look"])
    row[0]["output"] = "<think>reason</think><action>look</action>"
    with pytest.raises(ValueError):
        episode_metrics(row, facts, False)
