import pytest
from hintladder.keys import normalize_gamefile, experiment_name


def test_normalize(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFWORLD_DATA", str(tmp_path))
    assert normalize_gamefile(str(tmp_path / "json_2.1.1/train/a/game.tw-pddl")) == normalize_gamefile("json_2.1.1//train/./a/game.tw-pddl")


@pytest.mark.parametrize("value", [None, "", "../escape", "/outside/game.tw-pddl", "a\\b", "a\nb"])
def test_bad_keys(value, tmp_path):
    with pytest.raises((ValueError, TypeError)):
        normalize_gamefile(value, tmp_path)


def test_natural_experiment_name():
    assert experiment_name("configs/arms/e2_L3.yaml", 2) == "e2_L3_seed2"
    with pytest.raises(ValueError):
        experiment_name("x.yaml", -1)
