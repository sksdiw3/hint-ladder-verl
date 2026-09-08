"""Sequential processes with explicit argv and auditable configurations."""
from pathlib import Path
import shlex
import subprocess
import sys

from .config import hydra_overrides
from .io import ROOT, manifest, write_json


def launch_native(stage, config, config_path, output, inputs):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    resolved = output / "resolved_config.json"
    config = dict(config)
    config["algorithm.hint_ladder.stage_config_path"] = str(resolved)
    write_json(resolved, config)
    manifest(output, stage, config_path, config, inputs)
    argv = [sys.executable, "-m", "verl.trainer.main_hint_ladder", *hydra_overrides(config)]
    (output / "launch_command.txt").write_text(shlex.join(argv) + "\n")
    subprocess.run(argv, cwd=ROOT, check=True)
    return output


def launch_stage(stage, path, *, seed, checkpoint=None):
    argv = [sys.executable, "-m", "hintladder.cli", stage, "--config", str(path), "--seed", str(seed)]
    if checkpoint is not None:
        argv += ["--checkpoint", str(checkpoint)]
    subprocess.run(argv, cwd=ROOT, check=True)


def checkpoint_path(value):
    path = Path(value).resolve()
    if not path.is_dir():
        raise FileNotFoundError(path)
    return path


def hf_checkpoint(value):
    path = checkpoint_path(value)
    if path.name.startswith("global_step_"):
        path = path / "actor" / "huggingface"
    if not (path / "config.json").is_file():
        raise ValueError(f"checkpoint has no Hugging Face config: {path}")
    if not (list(path.glob("*.safetensors")) or list(path.glob("pytorch_model*.bin"))):
        raise ValueError(f"checkpoint has no model weights: {path}")
    return path


def latest_checkpoint(directory):
    directory = Path(directory)
    step = int((directory / "latest_checkpointed_iteration.txt").read_text().strip())
    path = checkpoint_path(directory / f"global_step_{step}")
    if not (path / "actor").is_dir() or not (path / "data.pt").is_file():
        raise ValueError(f"incomplete native checkpoint: {path}")
    return path, step
