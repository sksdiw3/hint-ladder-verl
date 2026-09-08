from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml

from hintladder.io import read_json, write_json, write_jsonl
from hintladder.stages import alternate
from hintladder.stages.build_hint_bank import generate_row


def hf_fixture(path):
    path.mkdir(parents=True)
    write_json(path / "config.json", {"cpu_interface_fixture": True})
    (path / "model.safetensors").write_bytes(b"not model weights; CPU orchestration test")
    return str(path)


@pytest.mark.parametrize("accepted", [True, False])
def test_alternation_acceptance_rollback_and_idempotent_resume(tmp_path, monkeypatch, accepted):
    student = hf_fixture(tmp_path / "student_base")
    hinter = hf_fixture(tmp_path / "hinter_base")
    updated_hinter = hf_fixture(tmp_path / "hinter_updated")
    evidence = tmp_path / "e2.json"
    write_json(evidence, {"phenomenon_observed": True})
    files = {}
    for name, value in {"student": {}, "hint": {"stage.generator": {"api_key_file": "must-not-propagate", "max_tokens": 100}},
                        "hinter": {"stage.command": ["external-trainer"]}}.items():
        path = tmp_path / f"{name}.yaml"
        path.write_text(yaml.safe_dump(value))
        files[f"stage.{name}_config"] = str(path)
    config = {**files, "stage.output_dir": str(tmp_path / "run"), "stage.e2_evidence": str(evidence),
              "stage.student_checkpoint": student, "stage.hinter_checkpoint": hinter,
              "stage.rounds": 1, "stage.student_steps": 2,
              "stage.hinter_policy": {"base_url": "http://127.0.0.1:18086/v1", "model": "local-hinter"}}
    config_path = tmp_path / "alternate.yaml"
    config_path.write_text(yaml.safe_dump(config))
    calls = []

    @contextmanager
    def service(*args):
        yield None

    def launch(stage, path, **kwargs):
        cfg = yaml.safe_load(Path(path).read_text())
        calls.append(stage)
        out = Path(cfg["stage.output_dir"])
        if stage == "build-hint-bank":
            assert "api_key_file" not in cfg["stage.generator"]
            assert cfg["stage.levels"] == ["HINTER"]
        elif stage == "train-hinter":
            write_json(out / "result.json", {"checkpoint": updated_hinter})
        else:
            baseline = out.name == "baseline"
            write_jsonl(out / "metrics.jsonl", [{"step": 0 if baseline else 2,
                "val/valid_seen/success_rate": .5 if baseline else .75,
                "val/valid_unseen/success_rate": .5 if baseline or accepted else .25}])
            if not baseline:
                checkpoint = out / "global_step_2"
                hf_fixture(checkpoint / "actor" / "huggingface")
                (checkpoint / "data.pt").write_bytes(b"CPU fixture")
                (out / "latest_checkpointed_iteration.txt").write_text("2\n")

    monkeypatch.setattr(alternate, "model_service", service)
    monkeypatch.setattr(alternate, "launch_stage", launch)
    alternate.run(config, config_path, 0, None, [])
    result = read_json(tmp_path / "run" / "result.json")
    status = read_json(tmp_path / "run" / "rounds" / "round_0" / "status.json")
    assert status["rolled_back"] is not accepted
    assert result["student_step"] == (2 if accepted else 0)
    assert result["hinter_checkpoint"] == (updated_hinter if accepted else hinter)
    assert ("train-hinter" in calls) is accepted
    original_calls = list(calls)
    alternate.run(config, config_path, 0, None, [])
    assert calls == original_calls


def test_hint_transport_retry_does_not_hide_failed_generation(monkeypatch):
    from urllib.error import HTTPError
    from hintladder.stages import build_hint_bank
    monkeypatch.setattr(build_hint_bank.time, "sleep", lambda seconds: None)
    record = {"gamefile": "a/game.tw-pddl", "initial_observation": "public", "initial_admissible_commands": ["look"]}
    config = {"model": "glm-5.3-flash", "attempts": 2, "temperature": .7, "max_tokens": 4096, "prompt_version": "v1"}

    class Client:
        def chat(self, *args, **kwargs):
            raise HTTPError("http://localhost/v1", 503, "unavailable", {}, None)

    row = generate_row(record, "L1", config, Client(), 0)
    assert not row["validation"]["ok"]
    assert row["hint"] == ""
    assert "503" in row["validation"]["errors"][0]


def test_offline_bank_resume_reuses_only_unchanged_inputs(tmp_path, monkeypatch):
    from hintladder.stages import build_hint_bank
    privilege = tmp_path / "privilege.jsonl"
    write_jsonl(privilege, [{"gamefile": "a/game.tw-pddl", "walkthrough_verified": True,
                           "initial_observation": "public", "initial_admissible_commands": ["look"]}])
    games = tmp_path / "games.txt"
    games.write_text("a/game.tw-pddl\n")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("fixture: true\n")
    config = {"stage.seed": 0, "stage.output_dir": str(tmp_path / "bank"), "stage.privilege_banks": [str(privilege)],
              "stage.game_lists": [str(games)], "stage.levels": ["L2"],
              "stage.generator": {"model": "CPU_fixture", "attempts": 1, "concurrency": 1,
                                  "max_tokens": 100, "temperature": 0, "prompt_version": "fixture"}}
    calls = []

    class Client:
        def __init__(self, config):
            pass

        def chat(self, *args, **kwargs):
            calls.append(1)
            return "Search systematically and use observations to check the task conditions."

    monkeypatch.setattr(build_hint_bank, "ModelClient", Client)
    build_hint_bank.run(config, config_path, 0, None, [])
    build_hint_bank.run(config, config_path, 0, None, [])
    assert len(calls) == 1
    privilege.write_text(privilege.read_text() + "\n")
    with pytest.raises(ValueError, match="manifest input changed"):
        build_hint_bank.run(config, config_path, 0, None, [])


def test_random_curriculum_uses_hstar_panel_instead_of_reprobing(tmp_path, monkeypatch):
    from hintladder import experiments
    initial = hf_fixture(tmp_path / "initial")
    matched = tmp_path / "hstar_seed0"
    write_json(matched / "manifest.json", {"config": {"stage.initial_checkpoint": initial}})
    panel = matched / "round_0" / "probe"
    write_json(panel / "summary.json", {"hint_ladder/train_games": 1})
    write_json(panel / "random_level_map.json", {"a/game.tw-pddl": "L2"})
    (panel / "train_games.txt").write_text("a/game.tw-pddl\n")
    probe_cfg = tmp_path / "probe.yaml"
    probe_cfg.write_text("{}\n")
    cfg = {"stage.output_dir": str(tmp_path / "random"), "stage.probe_config": str(probe_cfg),
           "stage.matched_hstar_run": str(tmp_path / "hstar_seed{seed}"),
           "stage.map_name": "random_level_map.json", "stage.curriculum_rounds": 1,
           "stage.refresh_every": 1, "actor_rollout_ref.model.path": initial}
    cfg_path = tmp_path / "random.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))
    calls = []

    def launch(stage, path, **kwargs):
        assert stage == "train-student"
        arm = yaml.safe_load(Path(path).read_text())
        assert arm["stage.train_games"] == str(panel / "train_games.txt")
        assert arm["algorithm.hint_ladder.level_map_path"] == str(panel / "random_level_map.json")
        assert arm["algorithm.hint_ladder.reset_dataloader"] is True
        calls.append(stage)
        out = Path(arm["stage.output_dir"])
        (out / "global_step_1" / "actor").mkdir(parents=True)
        (out / "global_step_1" / "data.pt").write_bytes(b"CPU fixture")
        (out / "latest_checkpointed_iteration.txt").write_text("1\n")

    monkeypatch.setattr(experiments, "launch_stage", launch)
    experiments.curriculum(cfg, cfg_path, 0, None, [])
    assert calls == ["train-student"]
    experiments.curriculum(cfg, cfg_path, 0, None, [])
    assert calls == ["train-student"]
