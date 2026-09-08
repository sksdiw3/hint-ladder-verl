"""CPU TextWorld replay. No AgentGym/ETO or model-generated references."""
import json
import random
import re
from pathlib import Path

from .keys import data_root, normalize_gamefile


def hidden_facts_from_initial(facts, actions):
    pickups = [re.fullmatch(r"take (.+?) from (.+)", action) for action in actions]
    pickups = [match for match in pickups if match]
    if not pickups:
        raise ValueError("walkthrough has no goal-object pickup")
    goal = pickups[0].group(1)
    relations = [(fact.name.lower(), tuple(arg.name.strip() for arg in fact.arguments)) for fact in facts]
    locations = {args[1] for name, args in relations
                 if name in ("inreceptacle", "on", "in") and len(args) == 2 and args[0] == goal}
    # TextWorld includes transitive containment, e.g. a mug belongs to both
    # a coffee machine and its countertop. Select the pickup source only if
    # initial facts explicitly support it; never infer a missing location.
    location = pickups[0].group(2)
    if location not in locations:
        raise ValueError(f"initial facts do not support pickup of {goal} from {location}: {locations}")
    destinations = [match.group(1) for action in actions
                    if (match := re.fullmatch(r"(?:put|move) " + re.escape(goal) + r" (?:in/on|in|on|to) (.+)", action))]
    states = {"hot": any(name in ("hot", "ishot") and args == (goal,) for name, args in relations),
              "clean": any(name in ("clean", "isclean") and args == (goal,) for name, args in relations),
              "cool": any(name in ("cool", "iscool", "cold", "iscold") and args == (goal,) for name, args in relations)}
    return {"goal_object": goal, "goal_object_location": location,
            "destination_receptacle": destinations[-1] if destinations else None,
            "goal_object_initial_states": states}


def render_walkthrough(actions, entity_infos):
    """Expand game-native PDDL entity identifiers using the same native demangler.

    ALFWorld's released bank contains both readable and PDDL-encoded commands.
    This is a declared input encoding conversion, never a generated reference.
    """
    names = {key: value.name.strip() for key, value in entity_infos.items() if "_bar_" in key}
    pattern = re.compile(r"(?<!\w)(" + "|".join(re.escape(key) for key in sorted(names, key=len, reverse=True)) + r")(?!\w)") if names else None
    rendered = [pattern.sub(lambda match: names[match.group(0)], action) if pattern else action for action in actions]
    if any("_bar_" in action for action in rendered):
        raise ValueError("walkthrough contains an unknown encoded entity")
    return rendered


def replay_game(gamefile, split, seed=0):
    import textworld
    from agent_system.environments.env_package.alfworld.alfworld.agents.environment.alfred_tw_env import AlfredDemangler, AlfredInfos

    game = normalize_gamefile(gamefile)
    path = data_root() / game
    game_data = json.loads(path.read_text())
    actions = game_data["walkthrough"]
    if not isinstance(actions, list) or not actions or any(not isinstance(a, str) for a in actions):
        raise ValueError(f"game's embedded walkthrough must be a nonempty command list: {game}")
    random.seed(seed)
    env = textworld.start(str(path), request_infos=textworld.EnvInfos(facts=True, won=True, admissible_commands=True),
                          wrappers=[AlfredDemangler(shuffle=False), AlfredInfos])
    try:
        env.seed(seed)
        initial = env.reset()
        actions = render_walkthrough(actions, env._entity_infos)
        marker = "Your task is to: "
        if marker not in initial.feedback:
            raise ValueError(f"missing public goal: {game}")
        record = {"gamefile": game, "split": split, "task_type": path.parent.parent.name.split("-", 1)[0],
                  "goal_text": initial.feedback.split(marker, 1)[1].strip(),
                  "initial_observation": initial.feedback,
                  "initial_admissible_commands": list(initial.admissible_commands),
                  "walkthrough_actions": list(actions), "walkthrough_verified": False,
                  "hidden_facts": hidden_facts_from_initial(initial.facts, actions)}
        state, turns = initial, []
        for step, action in enumerate(actions):
            row = {"step": step, "observation": state.feedback,
                   "admissible_commands": list(state.admissible_commands), "action": action}
            state, reward, done = env.step(action)
            row.update(next_observation=state.feedback, won=bool(state.won), done=bool(done))
            turns.append(row)
            if done:
                break
        record["walkthrough_verified"] = bool(state.won) and len(turns) == len(actions)
        return record, {"gamefile": game, "split": split, "seed": seed, "turns": turns,
                        "walkthrough_verified": record["walkthrough_verified"]}
    finally:
        env.close()
