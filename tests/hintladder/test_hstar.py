import pytest
from hintladder.hstar import classify
from hintladder.stages.e3_probe import build_curriculum
from hintladder.io import read_json


@pytest.mark.parametrize("rates,level,band", [([.5,1,1,1],"L0","mastered"),([.125,.5,1,1],"L1","frontier"),
    ([0,0,.5,1],"L2","scaffolded"),([0,0,0,.5],"L3","oracle_only"),([0,0,0,.25],None,"unreachable"),
    ([0,.75,.1,.1],"L1","scaffolded")])
def test_boundaries(rates,level,band):
    result = classify(dict(zip(("L0","L1","L2","L3"),rates)))
    assert (result["h_star"],result["band"]) == (level,band)


def test_maps_share_eligible_game_pool(tmp_path):
    rows = [{"gamefile": game,"level": level,"episodes":[{"success": (game=="mastered" or level in ("L2","L3"))}]*8}
            for game in ("mastered","frontier") for level in ("L0","L1","L2","L3")]
    build_curriculum(rows,"checkpoint",8,0,tmp_path)
    assert read_json(tmp_path/'level_map.json') == {"frontier":"L2"}
    assert set(read_json(tmp_path/'random_level_map.json')) == {"frontier"}
