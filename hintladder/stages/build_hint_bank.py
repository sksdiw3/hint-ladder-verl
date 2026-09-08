from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time
from urllib.error import HTTPError, URLError

from hintladder.api import ModelClient
from hintladder.hint_bank import write_bank
from hintladder.io import ROOT, manifest, read_json, read_jsonl, write_json, verify_manifest_inputs
from hintladder.keys import Level, read_game_list
from hintladder.ladder import fullpath, generation_messages, public_input, validate_hint


def generate_row(record, level, generator, client, seed):
    if level == "FULLPATH":
        hint, errors = fullpath(record), []
    else:
        payload = public_input(record)
        if level in ("L3", "HINTER"):
            payload.update(goal_text=record["goal_text"], hidden_facts=record["hidden_facts"],
                           walkthrough=record["walkthrough_actions"])
        messages = generation_messages(level, payload)
        hint, errors = "", ["generation has not completed"]
        for attempt in range(int(generator["attempts"])):
            try:
                hint = client.chat(messages, seed=seed + attempt, temperature=generator["temperature"], max_tokens=generator["max_tokens"])
            except (HTTPError, URLError, TimeoutError) as exc:
                if isinstance(exc, HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                    raise
                # Keep only the error type/status, never response bodies or auth.
                errors = [f"generator transport failure: {type(exc).__name__} {getattr(exc, 'code', '')}".strip()]
                if attempt + 1 < int(generator["attempts"]):
                    time.sleep(2 ** attempt)
                continue
            errors = validate_hint(level, hint, record["hidden_facts"] if level in ("L3", "HINTER") else None)
            if not errors:
                break
    return {"gamefile": record["gamefile"], "level": level, "hint": hint,
            "word_count": len(hint.split()),
            "generator": {"model": "embedded_walkthrough" if level == "FULLPATH" else generator["model"],
                          "temperature": 0 if level == "FULLPATH" else generator["temperature"],
                          "prompt_version": generator["prompt_version"]},
            "validation": {"ok": not errors, "errors": errors}}


def run(config, config_path, seed, checkpoint, inputs):
    out = ROOT / config["stage.output_dir"]
    sources = config["stage.privilege_banks"]
    records = {}
    for source in sources:
        for row in read_jsonl(source):
            if row["gamefile"] in records:
                raise ValueError(f"duplicate privilege game: {row['gamefile']}")
            records[row["gamefile"]] = row
    game_lists = config["stage.game_lists"]
    games = [game for path in game_lists for game in read_game_list(path)]
    if len(set(games)) != len(games):
        raise ValueError("duplicate games across hint-generation splits")
    selected = [records[game] for game in games]
    if any(row["walkthrough_verified"] is not True for row in selected):
        raise ValueError("requested hint game has an unverified walkthrough")
    levels = [Level(level).value for level in config["stage.levels"]]
    if "L0" in levels:
        raise ValueError("L0 has no bank file and must not call a generator")
    generator = dict(config["stage.generator"])
    if generator["attempts"] < 1:
        raise ValueError("generation attempts must be positive")
    client = ModelClient(generator)
    if checkpoint is not None:
        client.verify_model(checkpoint)
    out.mkdir(parents=True, exist_ok=True)
    previous = out / "manifest.json"
    if previous.exists():
        previous = read_json(previous)
        if previous["config"] != config:
            raise ValueError("hint output belongs to another configuration; use a new bank directory")
        verify_manifest_inputs(previous)
    manifest(out, "build-hint-bank", config_path, config, [*inputs, *sources, *game_lists])
    failures = []
    for level in levels:
        existing_path = out / f"{level}.jsonl"
        existing = {}
        if existing_path.exists():
            for row in read_jsonl(existing_path):
                if row["gamefile"] in existing or row["level"] != level:
                    raise ValueError("invalid existing hint bank natural keys")
                if row["validation"]["ok"]:
                    existing[row["gamefile"]] = row
        with ThreadPoolExecutor(max_workers=int(generator["concurrency"])) as pool:
            rows = list(pool.map(lambda pair: existing[pair[1]["gamefile"]] if pair[1]["gamefile"] in existing else
                                 generate_row(pair[1], level, generator, client, seed + pair[0] * generator["attempts"]), enumerate(selected)))
        write_bank(out / f"{level}.jsonl", rows)
        print(f"{level}: generated {len(rows)} hints; {sum(not row['validation']['ok'] for row in rows)} failures", flush=True)
        failures.extend({"gamefile": row["gamefile"], "level": level, "errors": row["validation"]["errors"]}
                        for row in rows if not row["validation"]["ok"])
    write_json(out / "validation_report.json", {"games": len(games), "levels": levels, "failures": failures})
    if failures:
        raise ValueError(f"{len(failures)} hints failed validation; see {out / 'validation_report.json'}")
