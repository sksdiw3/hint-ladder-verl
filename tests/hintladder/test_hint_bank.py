import pytest
from hintladder.hint_bank import HintProvider, write_bank
from hintladder.io import write_json


def test_absent_and_invalid(provider):
    with pytest.raises(KeyError):
        provider.get("missing/game.tw-pddl")
    key = next(iter(provider.rows))
    provider.rows[key]["validation"]["ok"] = False
    with pytest.raises(ValueError):
        provider.get(key[0])


def test_l0_never_reads_a_bank():
    provider = HintProvider("does-not-exist", level="L0")
    assert provider.get("a/game.tw-pddl") == ""


def test_selector_and_duplicate_errors(tmp_path):
    with pytest.raises(ValueError):
        HintProvider(tmp_path, level="L2", level_map_path="map.json")
    path = tmp_path / "map.json"
    path.write_text('{"a":"L0","a":"L1"}')
    with pytest.raises(ValueError):
        HintProvider(tmp_path, level_map_path=path)
    write_json(path, {"a/game.tw-pddl": "L0"})
    with pytest.raises(ValueError, match="exclude"):
        HintProvider(tmp_path, level_map_path=path).validate_coverage(["a/game.tw-pddl"], training=True)
