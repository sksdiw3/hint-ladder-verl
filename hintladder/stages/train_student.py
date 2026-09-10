from pathlib import Path
import pandas as pd

from hintladder.config import output_dir, validate_student_config
from hintladder.hint_bank import HintProvider
from hintladder.io import manifest, read_json
from hintladder.keys import data_root, experiment_name, read_game_list
from hintladder.launch import launch_native, checkpoint_path, hf_checkpoint


def prepare_data(directory, train_games, validation_games, config_path, config, inputs):
    """Native RLHFDataset rows, with per-row strict env resets instead of a new sampler."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sources = {"train": train_games, "validation": validation_games}
    for split, games in sources.items():
        path = directory / f"{split}.parquet"
        rows = [{"data_source": "text", "prompt": [{"role": "user", "content": ""}], "ability": "agent",
                 "reward_model": {"style": "rule", "ground_truth": ""}, "extra_info": {"split": split, "index": i},
                 "env_kwargs": {"gamefile": str(data_root() / game), "strict_gamefile": True}}
                for i, game in enumerate(games)]
        if split == 'train' and config.get('stage.pad_train_to_batch', False):
            import copy
            pad = (-len(rows)) % int(config['data.train_batch_size'])
            for i in range(pad):
                row = copy.deepcopy(rows[i])
                row['extra_info']['alignment_repeat'] = True
                rows.append(row)
        frame = pd.DataFrame(rows)
        if path.exists():
            # Exact natural-key equality; no digest-keyed dataset cache.
            old = pd.read_parquet(path)
            old_games = [row["gamefile"] for row in old.env_kwargs]
            if old_games != [row["env_kwargs"]["gamefile"] for row in rows]:
                raise ValueError(f"processed data exists for a different game list: {path}")
        else:
            frame.to_parquet(path, index=False)
    manifest(directory, "prepare-student-data", config_path, config, inputs)
    return str(directory / "train.parquet"), str(directory / "validation.parquet")


def run(config, config_path, seed, checkpoint, inputs):
    if config.get("stage.sweep", False):
        from hintladder.experiments import e2_sweep
        return e2_sweep(config, config_path, seed, checkpoint, inputs)
    if config.get("stage.curriculum_rounds", 0):
        from hintladder.experiments import curriculum
        return curriculum(config, config_path, seed, checkpoint, inputs)
    config = dict(config)
    name = experiment_name(config_path, seed)
    output = output_dir(config, name).resolve()
    train_games = read_game_list(config["stage.train_games"])
    validation = {split: read_game_list(path) for split, path in config["stage.validation_games"].items()}
    if set(validation) != {"valid_seen", "valid_unseen"}:
        raise ValueError("validation requires fixed seen and unseen lists")
    if any(len(games) != len(set(games)) for games in validation.values()):
        raise ValueError("validation game lists must not repeat games")
    for game in set(train_games + sum(validation.values(), [])):
        if not (data_root() / game).is_file():
            raise FileNotFoundError(data_root() / game)
    config.update({"env.seed": seed, "data.seed": seed, "actor_rollout_ref.rollout.seed": seed,
                   "trainer.experiment_name": name, "trainer.default_local_dir": str(output),
                   "trainer.rollout_data_dir": str(output / "rollouts"), "trainer.validation_data_dir": str(output / "validation"),
                   "data.val_batch_size": len(validation["valid_seen"]), "algorithm.hint_ladder.mode": "train"})
    if config["algorithm.hint_ladder.level"] == "L0":
        config["actor_rollout_ref.actor.use_sdl_loss"] = False
        config["trainer.val_only"] = config["actor_rollout_ref.actor.pg_loss_coef"] == 0
    config.setdefault("trainer.val_only", False)
    budget_reference = config.get("stage.budget_reference")
    if budget_reference:
        state = read_json(Path(budget_reference) / "hint_ladder_budget.json")
        if state["used"] <= 0:
            raise ValueError("reference run has no active SDL tokens")
        config["algorithm.hint_ladder.active_token_budget"] = state["used"]
        inputs = [*inputs, Path(budget_reference) / "hint_ladder_budget.json"]
    config["trainer.resume_mode"] = "disable"
    config["trainer.resume_from_path"] = None
    if checkpoint:
        path = checkpoint_path(checkpoint)
        if path.name.startswith("global_step_"):
            for filename in ("data.pt", "hint_ladder_budget.json"):
                if not (path / filename).is_file():
                    raise FileNotFoundError(path / filename)
            config["trainer.resume_mode"], config["trainer.resume_from_path"] = "resume_path", str(path)
        else:
            config["actor_rollout_ref.model.path"] = str(hf_checkpoint(path))
    if (output / "metrics.jsonl").exists() and (output / "metrics.jsonl").stat().st_size and checkpoint is None:
        raise ValueError("run already has metrics; supply its native checkpoint or use a new output directory")
    validate_student_config(config, coverage=True)
    online = config.get('algorithm.hint_ladder.online.enable', False)
    provider = None if online else HintProvider(config["algorithm.hint_ladder.bank_dir"], level=config["algorithm.hint_ladder.level"],
                            level_map_path=config["algorithm.hint_ladder.level_map_path"])
    levels = set() if online else {provider.level_for(game) for game in train_games} - {"L0"}
    inputs = [*inputs, config["stage.train_games"], *config["stage.validation_games"].values(),
              *[Path(config["algorithm.hint_ladder.bank_dir"]) / f"{level}.jsonl" for level in sorted(levels)]]
    if config["algorithm.hint_ladder.level_map_path"]:
        inputs.append(config["algorithm.hint_ladder.level_map_path"])
    if online:
        inputs.append(config['algorithm.hint_ladder.online.prompt_path'])
    # Arm/seed directories prevent refreshed list collisions. Subsequent launch
    # of the same run verifies and reuses the parquet rows.
    processed = Path(config.get("stage.processed_dir", "data/processed/hintladder")) / name
    if config.get("stage.round") is not None:
        processed /= f"round_{config['stage.round']}"
    config["data.train_files"], config["data.val_files"] = prepare_data(processed, train_games, validation["valid_seen"], config_path, config, inputs)
    return launch_native("train-student", config, config_path, output, inputs)
