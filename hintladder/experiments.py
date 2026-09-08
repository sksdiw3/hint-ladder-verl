"""E2 equal-budget sweep and E3 checkpoint-based curriculum refresh."""
from pathlib import Path

from .config import load_config, output_dir
from .io import manifest, read_json, write_json
from .keys import experiment_name
from .launch import launch_stage, latest_checkpoint, hf_checkpoint
from .stages.alternate import write_config


def e2_sweep(config, config_path, seed, checkpoint, inputs):
    output = output_dir(config, experiment_name(config_path, seed))
    if read_json(config["stage.e1_summary"]).get("accepted_for_e2") is not True:
        raise ValueError("E2 sweep requires an accepted E1 audit")
    manifest(output, "e2-sweep", config_path, config, [*inputs, config["stage.e1_summary"]])
    seeds = config.get("stage.seeds", [0, 1, 2])
    if seeds != [0, 1, 2]:
        raise ValueError("the main E2 sweep uses seeds 0, 1, 2")
    budget = None
    completed = []
    pairs = [("L3", 0)] + [(level, s) for level in ("L0", "L1", "L2", "L3", "FULLPATH") for s in seeds if (level, s) != ("L3", 0)]
    for level, run_seed in pairs:
        arm, _ = load_config(Path(config["stage.arm_dir"]) / f"e2_{level}.yaml")
        directory = output / f"e2_{level}_seed{run_seed}"
        arm["stage.output_dir"] = str(directory.resolve())
        arm["algorithm.hint_ladder.active_token_budget"] = budget if level != "L0" else None
        if budget is not None and level != "L0":
            arm["trainer.total_training_steps"] = config.get("stage.max_budget_steps", 1000)
        marker = directory / "complete.json"
        if not marker.exists():
            resume = checkpoint
            if (directory / "latest_checkpointed_iteration.txt").exists():
                resume = str(latest_checkpoint(directory)[0])
            launch_stage("train-student", write_config(output / f"e2_{level}_seed{run_seed}.yaml", arm), seed=run_seed, checkpoint=resume)
            if level != "L0" and budget is not None and not (directory / "budget_exhausted.json").exists():
                raise ValueError("E2 arm reached its step cap before matching the reference active-token budget")
            write_json(marker, {"level": level, "seed": run_seed})
        if (level, run_seed) == ("L3", 0):
            reference, step = latest_checkpoint(directory)
            if step != 250:
                raise ValueError("reference L3 seed0 must finish 250 steps")
            budget = read_json(reference / "hint_ladder_budget.json")["used"]
            if budget <= 0:
                raise ValueError("reference L3 run has no active SDL tokens")
            write_json(output / "budget.json", {"reference": str(reference), "active_tokens": budget})
        completed.append({"level": level, "seed": run_seed, "run": str(directory)})
    write_json(output / "sweep.json", {"active_token_budget": budget, "runs": completed})
    return output


def curriculum(config, config_path, seed, checkpoint, inputs):
    config = dict(config)
    output = output_dir(config, experiment_name(config_path, seed))
    current = str(hf_checkpoint(checkpoint)) if checkpoint else config["actor_rollout_ref.model.path"]
    if not Path(current).is_dir():
        raise ValueError("curriculum requires a local frozen HF checkpoint")
    config["stage.initial_checkpoint"] = str(Path(current).resolve())
    probe, probe_inputs = load_config(config["stage.probe_config"])
    matched_run = config.get("stage.matched_hstar_run")
    if matched_run:
        if config["stage.map_name"] != "random_level_map.json":
            raise ValueError("matched h-star panels are only used by the random control")
        matched_run = Path(matched_run.format(seed=seed))
        paired = read_json(matched_run / "manifest.json")
        if paired["config"]["stage.initial_checkpoint"] != config["stage.initial_checkpoint"]:
            raise ValueError("paired curriculum arms must start from the same checkpoint")
        inputs = [*inputs, matched_run / "manifest.json"]
    manifest(output, "e3-curriculum", config_path, config, [*inputs, *probe_inputs, config["stage.probe_config"]])
    step = 0
    for number in range(int(config["stage.curriculum_rounds"])):
        directory = output / f"round_{number}"
        marker = directory / "status.json"
        if marker.exists() and read_json(marker)["phase"] == "complete":
            result = read_json(marker)
            current, step = result["checkpoint"], result["step"]
            continue
        probe_output = matched_run / f"round_{number}" / "probe" if matched_run else directory / "probe"
        if matched_run and not (probe_output / "summary.json").exists():
            raise FileNotFoundError(f"run the paired h-star arm first: {probe_output / 'summary.json'}")
        if not matched_run and not (probe_output / "summary.json").exists():
            launch_stage("e3-probe", write_config(directory / "probe.yaml", {**probe, "stage.output_dir": str(probe_output.resolve())}),
                         seed=seed, checkpoint=str(hf_checkpoint(current)))
        if read_json(probe_output / "summary.json")["hint_ladder/train_games"] == 0:
            write_json(directory / "status.json", {"phase": "no_trainable_games", "round": number, "checkpoint": current, "step": step})
            return output
        arm = dict(config)
        arm.pop("stage.curriculum_rounds")
        arm.update({"stage.output_dir": str((directory / "student").resolve()), "stage.round": number,
                    "stage.train_games": str((probe_output / "train_games.txt").resolve()),
                    "algorithm.hint_ladder.level_map_path": str((probe_output / config["stage.map_name"]).resolve()),
                    "algorithm.hint_ladder.reset_dataloader": True,
                    "trainer.total_training_steps": step + int(config.get("stage.refresh_every", 100))})
        resume = current
        if (directory / "student" / "latest_checkpointed_iteration.txt").exists():
            resume = str(latest_checkpoint(directory / "student")[0])
        launch_stage("train-student", write_config(directory / "student.yaml", arm), seed=seed, checkpoint=resume)
        path, step = latest_checkpoint(directory / "student")
        current = str(path)
        write_json(marker, {"round": number, "phase": "complete", "checkpoint": current, "step": step})
    return output
