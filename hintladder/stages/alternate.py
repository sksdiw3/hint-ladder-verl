"""Sequential offline-bank → native Student → acceptance → external Hinter rounds."""
from pathlib import Path
import math
import yaml

from hintladder.config import load_config, output_dir
from hintladder.io import manifest, read_json, read_jsonl, write_json
from hintladder.keys import experiment_name
from hintladder.launch import hf_checkpoint, launch_stage, latest_checkpoint
from hintladder.service import model_service


def write_config(path, config):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
    return path


def evaluation(directory):
    rows = read_jsonl(Path(directory) / "metrics.jsonl")
    rows = [row for row in rows if "val/valid_seen/success_rate" in row and "val/valid_unseen/success_rate" in row]
    if not rows:
        raise ValueError("native validation has not reported both split success rates")
    last = rows[-1]
    result = {split: float(last[f"val/{split}/success_rate"]) for split in ("valid_seen", "valid_unseen")}
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in result.values()):
        raise ValueError("invalid validation success rates")
    return result


def accept_candidate(previous, candidate, tolerance=0.0):
    if set(previous) != set(candidate) or not previous or tolerance < 0:
        raise ValueError("acceptance requires the identical nonempty validation panel")
    return all(candidate[key] >= previous[key] - tolerance for key in previous)


def run(config, config_path, seed, checkpoint, inputs):
    output = output_dir(config, experiment_name(config_path, seed)).resolve()
    evidence = read_json(config["stage.e2_evidence"])
    if evidence.get("phenomenon_observed") is not True:
        raise ValueError("E4 requires E2 evidence with phenomenon_observed=true")
    student_cfg, student_inputs = load_config(config["stage.student_config"])
    bank_cfg, bank_inputs = load_config(config["stage.hint_config"])
    hinter_cfg, hinter_inputs = load_config(config["stage.hinter_config"])
    # Fail before allocating GPUs if the deliberately deferred trainer was not
    # supplied, while still producing a concrete reviewable configuration.
    manifest(output, "alternate", config_path, config, [*inputs, *student_inputs, *bank_inputs, *hinter_inputs,
             config["stage.student_config"], config["stage.hint_config"], config["stage.hinter_config"], config["stage.e2_evidence"]])
    if not hinter_cfg.get("stage.command"):
        raise ValueError("E4 external Hinter command is missing; reward/GRPO implementation is deferred")
    current_student = str(hf_checkpoint(checkpoint or config["stage.student_checkpoint"]))
    current_hinter = str(hf_checkpoint(config["stage.hinter_checkpoint"]))
    current_step = 0
    baseline = output / "baseline"
    if not (baseline / "metrics.jsonl").exists():
        base = {**student_cfg, "stage.output_dir": str(baseline), "algorithm.hint_ladder.level": "L0",
                "algorithm.hint_ladder.level_map_path": None, "actor_rollout_ref.actor.pg_loss_coef": 0.0,
                "actor_rollout_ref.actor.use_sdl_loss": False, "trainer.val_only": True}
        launch_stage("train-student", write_config(output / "baseline.yaml", base), seed=seed, checkpoint=current_student)
    accepted_metrics = evaluation(baseline)
    rounds = int(config["stage.rounds"])
    steps = int(config["stage.student_steps"])
    if rounds <= 0 or steps <= 0:
        raise ValueError("rounds and Student steps must be positive")
    for number in range(rounds):
        directory = output / "rounds" / f"round_{number}"
        status_path = directory / "status.json"
        status = read_json(status_path) if status_path.exists() else {"round": number, "phase": "pending"}
        if status["phase"] == "complete":
            current_student, current_hinter = status["student_checkpoint"], status["hinter_checkpoint"]
            current_step, accepted_metrics = status["student_step"], status["validation"]
            continue
        manifest(directory, "alternate-round", config_path, config, [config["stage.e2_evidence"]])
        bank_dir = directory / "hint_bank" / f"hinter_round{number}"
        if status["phase"] == "pending":
            bank = {**bank_cfg, "stage.output_dir": str(bank_dir), "stage.levels": ["HINTER"]}
            # A trained local Hinter has its own endpoint and authentication.
            # Never inherit the bootstrap GLM credential or provider options.
            generator = {key: value for key, value in bank["stage.generator"].items()
                         if key not in ("api_key_file", "thinking", "reasoning_effort", "base_url", "model")}
            bank["stage.generator"] = {**generator, **config["stage.hinter_policy"]}
            with model_service(config["stage.hinter_policy"], current_hinter, directory):
                launch_stage("build-hint-bank", write_config(directory / "hint_bank.yaml", bank), seed=seed, checkpoint=current_hinter)
            status["phase"] = "bank_ready"
            write_json(status_path, status)
        train_dir = directory / "student"
        if status["phase"] == "bank_ready":
            student = {**student_cfg, "stage.output_dir": str(train_dir), "stage.round": number,
                       "algorithm.hint_ladder.level": "HINTER", "algorithm.hint_ladder.level_map_path": None,
                       "algorithm.hint_ladder.bank_dir": str(bank_dir), "trainer.total_training_steps": current_step + steps,
                       "algorithm.hint_ladder.active_token_budget": None}
            resume = current_student
            if (train_dir / "latest_checkpointed_iteration.txt").exists():
                resume = str(latest_checkpoint(train_dir)[0])
            launch_stage("train-student", write_config(directory / "student.yaml", student), seed=seed, checkpoint=resume)
            candidate, candidate_step = latest_checkpoint(train_dir)
            if candidate_step != current_step + steps:
                raise ValueError("Student did not finish the requested alternation steps")
            candidate_metrics = evaluation(train_dir)
            accepted = accept_candidate(accepted_metrics, candidate_metrics, float(config.get("stage.acceptance_tolerance", 0.0)))
            status.update(phase="student_evaluated", accepted=accepted, candidate_checkpoint=str(candidate),
                          candidate_step=candidate_step, candidate_validation=candidate_metrics)
            write_json(status_path, status)
        if not status["accepted"]:
            status.update(phase="complete", rolled_back=True, student_checkpoint=current_student,
                          hinter_checkpoint=current_hinter, student_step=current_step, validation=accepted_metrics)
            write_json(status_path, status)
            # Preserve the accepted pair. No update of Hinter on a rejected Student.
            continue
        hinter_output = directory / "hinter"
        if status["phase"] == "student_evaluated":
            hinter = {**hinter_cfg, "stage.output_dir": str(hinter_output), "stage.round": number,
                      "stage.student_checkpoint": str(hf_checkpoint(status["candidate_checkpoint"]))}
            launch_stage("train-hinter", write_config(directory / "hinter.yaml", hinter), seed=seed, checkpoint=current_hinter)
            current_hinter = read_json(hinter_output / "result.json")["checkpoint"]
            current_student, current_step = status["candidate_checkpoint"], status["candidate_step"]
            accepted_metrics = status["candidate_validation"]
            status.update(phase="complete", rolled_back=False, student_checkpoint=current_student,
                          hinter_checkpoint=current_hinter, student_step=current_step, validation=accepted_metrics)
            write_json(status_path, status)
    write_json(output / "result.json", {"rounds": rounds, "student_checkpoint": current_student,
               "hinter_checkpoint": current_hinter, "student_step": current_step, "validation": accepted_metrics})
    return output
