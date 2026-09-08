from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from itertools import repeat
from multiprocessing import get_context
import random

from hintladder.io import ROOT, manifest, write_json, write_jsonl
from hintladder.keys import data_root, normalize_gamefile, read_game_list
from hintladder.privilege import replay_game


def replay_candidates(candidates, split, seed, workers=1):
    if workers < 1:
        raise ValueError("privilege workers must be positive")
    if workers == 1:
        for game in candidates:
            yield replay_game(game, split, seed)
        return
    # TextWorld's parser is not thread-safe. Keep independent processes and
    # yield in candidate order so parallelism never changes the selected panel.
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as pool:
        for offset in range(0, len(candidates), workers):
            batch = candidates[offset:offset + workers]
            yield from pool.map(replay_game, batch, repeat(split), repeat(seed))


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
        replayed = replay_candidates(candidates, split, seed, int(config.get("stage.workers", 1)))
        for record, trace in replayed:
            game = record["gamefile"]
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
        replayed.close()
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
