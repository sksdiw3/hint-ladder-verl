from collections import defaultdict
from pathlib import Path
from statistics import mean

from hintladder.behavior import aggregate
from hintladder.config import output_dir
from hintladder.hint_bank import HintProvider
from hintladder.io import read_jsonl, write_json, write_jsonl
from hintladder.keys import experiment_name, normalize_gamefile, read_game_list
from hintladder.ladder import audit_leak
from hintladder.launch import hf_checkpoint, launch_native
from hintladder.service import model_service


def probe_run(mode, config, config_path, seed, checkpoint, inputs):
    config = dict(config)
    output = output_dir(config, experiment_name(config_path, seed)).resolve()
    games = read_game_list(config["stage.games"])
    if len(games) != len(set(games)):
        raise ValueError("probe game list must be unique")
    model = str(hf_checkpoint(checkpoint)) if checkpoint else config["actor_rollout_ref.model.path"]
    config.update({"actor_rollout_ref.model.path": model, "env.seed": seed,
                   "algorithm.hint_ladder.mode": mode, "stage.output_dir": str(output), "stage.seed": seed})
    source_paths = [*config["stage.privilege_banks"], config["stage.games"]]
    if mode == "e1":
        source_paths += config["stage.reference_banks"]
    for level in config["stage.levels"]:
        HintProvider(config["algorithm.hint_ladder.bank_dir"], level=level).validate_coverage(games)
        if level != "L0":
            source_paths.append(Path(config["algorithm.hint_ladder.bank_dir"]) / f"{level}.jsonl")
    with model_service(config["stage.policy"], model, output):
        launch_native(mode, config, config_path, output, [*inputs, *source_paths])
    return output


def summarize(config, output):
    rows = read_jsonl(output / "rows.jsonl")
    by_level = defaultdict(list)
    for row in rows:
        by_level[row["level"]].append(row)
    summary = {"levels": {}}
    for level, level_rows in by_level.items():
        metrics = aggregate([episode for row in level_rows for episode in row["episodes"]])
        metrics.update({"hint_ladder/fact_leak_rate": mean(bool(row["fact_leaks"]) for row in level_rows),
                        "hint_ladder/lift": mean(row["hint_ladder/lift"] for row in level_rows),
                        "hint_ladder/copy": mean(row["hint_ladder/copy"] for row in level_rows)})
        summary["levels"][level] = metrics
    levels = summary["levels"]
    leak_pass = levels["L1"]["hint_ladder/fact_leak_rate"] == 0 and levels["L2"]["hint_ladder/fact_leak_rate"] == 0 and levels["L3"]["hint_ladder/fact_leak_rate"] >= config.get("stage.min_l3_leak_rate", 0.9)
    separation = max(abs(levels["L2"][key] - levels["L3"][key]) for key in
                     ("hint_ladder/direct_location_hit_rate", "hint_ladder/query_before_pickup_rate"))
    calibrated = leak_pass and separation >= config.get("stage.min_behavior_separation", 0.1)
    summary.update({"hint_ladder/behavior_separation": separation,
                    "calibration_checks_passed": calibrated, "smoke_only": bool(config.get("stage.smoke", False)),
                    "accepted_for_e2": calibrated and not config.get("stage.smoke", False),
                    "copy_is_diagnostic_only": True, "games": len(by_level["L1"])})
    write_json(output / "summary.json", summary)
    return summary


def run(config, config_path, seed, checkpoint, inputs):
    if not {"L1", "L2", "L3"}.issubset(config["stage.levels"]):
        raise ValueError("E1 requires L1, L2 and L3")
    output = probe_run("e1", config, config_path, seed, checkpoint, inputs)
    summarize(config, output)
    return output
