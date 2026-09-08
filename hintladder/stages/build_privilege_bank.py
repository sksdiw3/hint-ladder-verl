from pathlib import Path
import random

from hintladder.io import ROOT, manifest, write_json, write_jsonl
from hintladder.keys import data_root, normalize_gamefile, read_game_list
from hintladder.privilege import replay_game


def run(config, config_path, seed, checkpoint, inputs):
    out = ROOT / config["stage.output_dir"]
    out.mkdir(parents=True, exist_ok=True)
    requested = config["stage.splits"]
    all_inputs = list(inputs)
    for split, settings in requested.items():
        if settings.get("source_list"):
            candidates = read_game_list(settings["source_list"])
            all_inputs.append(settings["source_list"])
        else:
            candidates = [normalize_gamefile(str(path)) for path in sorted((data_root() / "json_2.1.1" / split).rglob("game.tw-pddl"))]
            random.Random(seed).shuffle(candidates)
        count = int(settings["count"])
        if len(set(candidates)) != len(candidates) or len(candidates) < count:
            raise ValueError(f"{split}: need {count} distinct game files, found {len(candidates)}")
        records, traces, accepted, rejected = [], [], [], []
        for game in candidates:
            record, trace = replay_game(game, split, seed)
            records.append(record)
            all_inputs.append(str(data_root() / game))
            if record["walkthrough_verified"]:
                accepted.append(game)
                traces.append(trace)
            else:
                rejected.append(game)
            if len(accepted) == count:
                break
            if len(records) % 16 == 0:
                print(f"{split}: verified {len(accepted)}/{count}; rejected {len(rejected)}", flush=True)
        write_jsonl(out / f"alfworld_{split}.jsonl", records)
        write_jsonl(out / f"alfworld_{split}_walkthrough_states.jsonl", traces)
        games_path = ROOT / settings["game_list"]
        games_path.parent.mkdir(parents=True, exist_ok=True)
        games_path.write_text("".join(game + "\n" for game in accepted))
        write_json(out / f"{split}_validation_report.json", {"requested": count, "accepted": len(accepted), "rejected": rejected})
        if len(accepted) != count:
            manifest(out, "build-privilege-bank", config_path, config, all_inputs)
            raise ValueError(f"{split}: only {len(accepted)} winning walkthroughs, requested {count}; see validation report")
    manifest(out, "build-privilege-bank", config_path, config, all_inputs)
