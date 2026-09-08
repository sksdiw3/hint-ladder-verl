from collections import defaultdict
from pathlib import Path

from hintladder.behavior import aggregate, episode_metrics, admissible_from_prompt
from hintladder.io import manifest, read_jsonl, write_json
from hintladder.keys import normalize_gamefile
from hintladder.teacher_prompt import OPEN


def audit_dump(rows, facts):
    groups = defaultdict(list)
    for row in rows:
        if OPEN in row["input"]:
            raise ValueError("private teacher note appeared in clean validation")
        game = normalize_gamefile(row["gamefile"])
        row = {**row, "admissible_commands": admissible_from_prompt(row["input"])}
        # Native dump carries sample index through reward_extra_infos. Some
        # upstream revisions only dump traj_uid; here it is used to group rows,
        # never persisted as a Hint Ladder primary key or filename.
        replica = row.get("validation_sample_index", row.get("traj_uid"))
        if replica is None:
            raise ValueError("validation dump lacks episode identity")
        groups[(game, replica)].append(row)
    episodes = []
    for (game, replica), turns in groups.items():
        turns.sort(key=lambda row: row["turn_step"])
        if len({row["turn_step"] for row in turns}) != len(turns):
            raise ValueError("duplicate turn in validation episode")
        rewards = {float(row["episode_rewards"]) for row in turns}
        if len(rewards) != 1:
            raise ValueError("inconsistent episode reward in dump")
        episodes.append(episode_metrics(turns, facts[game], next(iter(rewards)) > 0))
    return aggregate(episodes)


def run(config, config_path, seed, checkpoint, inputs):
    validation = Path(config["stage.validation_dir"])
    output = Path(config["stage.output_dir"])
    sources = config["stage.privilege_banks"]
    facts = {}
    for path in sources:
        for row in read_jsonl(path):
            game = normalize_gamefile(row["gamefile"])
            if game in facts:
                raise ValueError(f"duplicate privilege game {game}")
            facts[game] = row["hidden_facts"]
    by_step = defaultdict(dict)
    dumps = sorted(validation.glob("*/*.jsonl"))
    if not dumps:
        raise ValueError(f"no native validation dumps in {validation}")
    for path in dumps:
        step = int(path.stem)
        by_step[step][path.parent.name] = audit_dump(read_jsonl(path), facts)
    manifest(output, "eval-behavior", config_path, config, [*inputs, *sources, *dumps])
    for step, values in by_step.items():
        write_json(output / f"step_{step}.json", {"step": step, "seed": seed, "splits": values})
    return output
