import threading

import pytest

from hintladder.io import read_json, read_jsonl, write_jsonl
from hintladder.stages import build_hint_bank, build_privilege_bank


def test_partial_generation_survives_failure_and_preserves_resume_seed(tmp_path, monkeypatch):
    games = [f"task_{i}/game.tw-pddl" for i in range(9)]
    source = tmp_path / "privilege.jsonl"
    write_jsonl(source, [{"gamefile": game, "walkthrough_verified": True} for game in games])
    panel = tmp_path / "games.txt"
    panel.write_text("\n".join(games) + "\n")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("test: recovery\n")
    out = tmp_path / "bank"
    config = {"stage.output_dir": str(out), "stage.privilege_banks": [str(source)],
              "stage.game_lists": [str(panel)], "stage.levels": ["L2"],
              "stage.generator": {"attempts": 3, "concurrency": 2}}
    saved = threading.Event()
    original_write = build_hint_bank.write_bank

    def write(path, rows):
        original_write(path, rows)
        if len(rows) == 8:
            saved.set()

    fail = True
    calls = []

    def generate(record, level, generator, client, seed):
        calls.append((record["gamefile"], seed))
        if fail and record["gamefile"] == games[-1]:
            assert saved.wait(5), "completed rows were not persisted during generation"
            raise RuntimeError("injected request failure")
        return {"gamefile": record["gamefile"], "level": level, "hint": "Observe carefully.",
                "word_count": 2, "validation": {"ok": True, "errors": []}}

    monkeypatch.setattr(build_hint_bank, "write_bank", write)
    monkeypatch.setattr(build_hint_bank, "ModelClient", lambda config: None)
    monkeypatch.setattr(build_hint_bank, "generate_row", generate)
    with pytest.raises(RuntimeError, match="injected"):
        build_hint_bank.run(config, config_path, 7, None, [])
    assert [r["gamefile"] for r in read_jsonl(out / "L2.jsonl")] == games[:8]
    assert read_json(out / "progress.json")["completed"] == 8
    fail = False
    calls.clear()
    build_hint_bank.run(config, config_path, 7, None, [])
    assert calls == [(games[-1], 7 + 8 * 3)]
    assert [r["gamefile"] for r in read_jsonl(out / "L2.jsonl")] == games
    assert read_json(out / "progress.json")["resumed"] == 8


def test_process_replay_preserves_order_and_arguments(monkeypatch):
    # A picklable stand-in exercises the actual spawned-process dispatch without
    # requiring downloaded ALFWorld assets in the CPU test suite.
    monkeypatch.setattr(build_privilege_bank, "replay_game", pow)
    values = [7, 2, 8, 3]
    serial = list(build_privilege_bank.replay_candidates(values, 3, 11, workers=1))
    parallel = list(build_privilege_bank.replay_candidates(values, 3, 11, workers=2))
    assert parallel == serial == [2, 8, 6, 5]
    with pytest.raises(ValueError, match="positive"):
        list(build_privilege_bank.replay_candidates(values, 3, 11, workers=0))
