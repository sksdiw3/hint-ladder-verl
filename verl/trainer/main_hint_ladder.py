"""Hydra entrypoint; launch through hintladder.cli, never a shell wrapper."""
import hydra
from omegaconf import OmegaConf


@hydra.main(config_path="config", config_name="ppo_trainer", version_base=None)
def main(config):
    from hintladder.config import validate_student_config
    from hintladder.io import read_json
    stage = read_json(config.algorithm.hint_ladder.stage_config_path)
    if not config.algorithm.hint_ladder.enable:
        raise ValueError("algorithm.hint_ladder.enable must be true")
    OmegaConf.resolve(config)
    if config.algorithm.hint_ladder.mode == "train":
        validate_student_config(stage, coverage=True)
        from verl.trainer.ppo.hint_ladder_ray_trainer import run_training
        run_training(config, stage)
    else:
        from verl.trainer.ppo.hint_ladder_ray_trainer import run_frozen_probe
        run_frozen_probe(config, stage)


if __name__ == "__main__":
    main()
