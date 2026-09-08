from collections import Counter

from hintladder.hstar import LEVELS, classify, random_level_map
from hintladder.io import read_jsonl, write_json, write_jsonl
from hintladder.stages.e1_audit import probe_run


def build_curriculum(rows, checkpoint, k, seed, output):
    games = {}
    for row in rows:
        game, level = row["gamefile"], row["level"]
        if level in games.setdefault(game, {}):
            raise ValueError("duplicate game/level probe row")
        if len(row["episodes"]) != k:
            raise ValueError("probe denominator does not equal k")
        games[game][level] = sum(bool(e["success"]) for e in row["episodes"]) / k
    manifest_rows, mapping = [], {}
    for game, rates in games.items():
        result = classify(rates)
        manifest_rows.append({"gamefile": game, "checkpoint": str(checkpoint), "k": k,
                              "pass_at_k": rates, **result})
        if result["h_star"] not in (None, "L0"):
            mapping[game] = result["h_star"]
    write_jsonl(output / "hstar_manifest.jsonl", manifest_rows)
    write_json(output / "level_map.json", mapping)
    # Matched training pool for random dose control; mastered and unreachable
    # games are excluded from both arms, never replaced by unobserved levels.
    write_json(output / "random_level_map.json", random_level_map(mapping, seed))
    (output / "train_games.txt").write_text("".join(game + "\n" for game in sorted(mapping)))
    write_json(output / "summary.json", {"hint_ladder/bands": dict(Counter(row["band"] for row in manifest_rows)),
               "hint_ladder/train_games": len(mapping), "hint_ladder/probe_games": len(games),
               "pass_at_k_definition": "empirical success fraction over k trials; not the at-least-one estimator"})


def run(config, config_path, seed, checkpoint, inputs):
    if set(config["stage.levels"]) != set(LEVELS):
        raise ValueError("h-star probe requires exactly L0/L1/L2/L3")
    output = probe_run("probe", config, config_path, seed, checkpoint, inputs)
    build_curriculum(read_jsonl(output / "rows.jsonl"), checkpoint or config["actor_rollout_ref.model.path"],
                     int(config["stage.k"]), seed, output)
    return output
