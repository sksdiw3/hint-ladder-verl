"""Explicit external trainer handoff. Reward/GRPO implementation is deferred."""
from pathlib import Path
import shlex
import subprocess

from hintladder.io import ROOT, manifest, read_json, write_json
from hintladder.launch import hf_checkpoint


def run(config, config_path, seed, checkpoint, inputs):
    output = Path(config["stage.output_dir"]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    previous = str(hf_checkpoint(checkpoint or config["stage.hinter_checkpoint"]))
    student = str(hf_checkpoint(config["stage.student_checkpoint"]))
    request_path = output / "training_request.json"
    response_path = output / "training_response.json"
    request = {"round": config["stage.round"], "seed": seed, "hinter_checkpoint": previous,
               "student_checkpoint": student, "privilege_banks": config["stage.privilege_banks"],
               "output_dir": str(output), "response_path": str(response_path)}
    if request_path.exists() and read_json(request_path) != request:
        raise ValueError("Hinter output belongs to a different training request")
    write_json(request_path, request)
    manifest(output, "train-hinter-handoff", config_path, config, [*inputs, *config["stage.privilege_banks"]])
    command = config.get("stage.command")
    if not isinstance(command, list) or not command:
        raise ValueError(f"Hinter reward/GRPO is deferred. Configure stage.command; the concrete request is at {request_path}")
    argv = [str(value).format(request=str(request_path), response=str(response_path), output=str(output)) for value in command]
    (output / "launch_command.txt").write_text(shlex.join(argv) + "\n")
    # A completed handoff may be resumed after the parent exits. Never run
    # external training twice merely because the outer status write was lost.
    if not response_path.exists():
        subprocess.run(argv, cwd=ROOT, check=True)
    response = read_json(response_path)
    updated = str(hf_checkpoint(response["checkpoint"]))
    if updated == previous or int(response["trained_steps"]) <= 0:
        raise ValueError("external Hinter trainer must return a new checkpoint and positive trained_steps")
    write_json(output / "result.json", {"checkpoint": updated, "trained_steps": int(response["trained_steps"]),
                                       "implementation": "external", "reward_implemented_here": False})
    return output
