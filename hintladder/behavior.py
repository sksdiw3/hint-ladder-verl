"""Behavior endpoints over executed episodes, with explicit denominators."""
import re
from statistics import mean

from .ladder import entity_aliases


def action_text(response):
    match = re.fullmatch(r"\s*<action>\s*([^<>]+?)\s*</action>\s*", response, re.S)
    return match.group(1).strip().lower() if match else None


def admissible_from_prompt(prompt):
    matches = re.findall(r"Your admissible actions of the current situation are: \[(.*?)\]\.\s*", prompt, re.S)
    if len(matches) != 1:
        raise ValueError("expected exactly one current admissible-action menu")
    actions = re.findall(r"'([^']+)'", matches[0])
    if not actions:
        raise ValueError("empty admissible-action menu")
    return actions


def episode_metrics(steps, hidden_facts, won):
    if not steps:
        raise ValueError("cannot audit an empty rollout")
    if any("<think>" in row.get("output", "") or "</think>" in row.get("output", "") for row in steps):
        raise ValueError("thinking appeared in generated response")
    actions = [row["executed_action"].strip().lower() for row in steps]
    first_navigation = next((a[6:] for a in actions if a.startswith("go to ")), None)
    pickup = next((i for i, a in enumerate(actions) if a.startswith("take ")), None)
    inspected = False
    for row, action in zip(steps[:pickup] if pickup is not None else steps,
                           actions[:pickup] if pickup is not None else actions):
        if action.startswith(("look", "open ", "examine ")):
            inspected = True
    # Upstream is_action_valid checks tag syntax, not action-pool membership.
    # Offline behavior additionally checks the exact current admissible menu.
    invalid = sum(not bool(row["is_action_valid"]) or action_text(row["output"]) not in row["admissible_commands"]
                  for row in steps)
    return {"direct_location_hit": first_navigation in entity_aliases(hidden_facts["goal_object_location"]) if first_navigation else False,
            "query_before_pickup": inspected, "steps_to_pickup": pickup + 1 if pickup is not None else None,
            "invalid_actions": invalid, "actions": len(steps), "success": bool(won)}


def aggregate(episodes):
    if not episodes:
        raise ValueError("no valid episodes to aggregate")
    pickup = [row["steps_to_pickup"] for row in episodes if row["steps_to_pickup"] is not None]
    total_actions = sum(row["actions"] for row in episodes)
    return {"hint_ladder/episodes": len(episodes), "hint_ladder/actions": total_actions,
            "hint_ladder/direct_location_hit_rate": mean(row["direct_location_hit"] for row in episodes),
            "hint_ladder/query_before_pickup_rate": mean(row["query_before_pickup"] for row in episodes),
            "hint_ladder/invalid_action_rate": sum(row["invalid_actions"] for row in episodes) / total_actions,
            "hint_ladder/steps_to_pickup_mean": mean(pickup) if pickup else None,
            "hint_ladder/pickup_episodes": len(pickup),
            "hint_ladder/success_rate": mean(row["success"] for row in episodes)}
