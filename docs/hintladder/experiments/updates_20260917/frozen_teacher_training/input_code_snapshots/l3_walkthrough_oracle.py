"""Align a game's embedded walkthrough with an actual Student action prefix.

No planner-generated or LLM-generated answers: candidates are suffixes of the
embedded reference. Inapplicable reference steps may be omitted (e.g. a pickup
already completed), but every retained action must be legal and the candidate
must end in native won=True. Unrecoverable states have no Oracle supervision.
"""
from functools import lru_cache
from copy import copy
from collections import defaultdict
import hashlib
import json
import time

from .keys import data_root, normalize_gamefile
from .privilege import render_walkthrough


@lru_cache(maxsize=32)
def _game(game):
    import textworld
    from agent_system.environments.env_package.alfworld.alfworld.agents.environment.alfred_tw_env import AlfredDemangler, AlfredInfos
    path = data_root() / game
    raw = path.read_bytes()
    data = json.loads(raw)
    env = textworld.start(str(path), request_infos=textworld.EnvInfos(won=True, admissible_commands=True),
                          wrappers=[AlfredDemangler(shuffle=False), AlfredInfos])
    env.seed(0)
    env.reset()
    walkthrough = render_walkthrough(data['walkthrough'], env._entity_infos)
    initial = _copy_state(env.unwrapped._pddl_state)
    return env, walkthrough, hashlib.sha256(raw).hexdigest(), initial, env.state.feedback


def _copy_state(state):
    # PddlState.copy() inherits State.copy(), which loses the native PDDL
    # handle. Copy only its mutable Python fact indices, sharing static logic.
    result = copy(state)
    result._facts = defaultdict(set, {k: v.copy() for k, v in state._facts.items()})
    result._vars_by_name = state._vars_by_name.copy()
    result._vars_by_type = defaultdict(set, {k: v.copy() for k, v in state._vars_by_type.items()})
    result._var_counts = state._var_counts.copy()
    return result


def _reset_compiled(env, initial, feedback):
    """Reset the same native SAS state without rerunning PDDL translation."""
    from textworld.core import GameState
    core = env.unwrapped
    initial.downward_lib.load_sas(initial.sas.encode('utf-8'))
    initial.downward_lib.load_sas_replan(initial.sas_replan.encode('utf-8'))
    core._pddl_state = _copy_state(initial)
    core.prev_state, core._last_action, core._moves = None, None, 0
    core.state = GameState(feedback=feedback, raw=feedback)
    core._gather_infos()
    return core.state


def _available(core):
    """Native operators with cached, game-specific command rendering."""
    state = core._pddl_state
    actions = list(state.all_applicable_actions())
    cache = core.__dict__.setdefault('_oracle_command_cache', {})
    names = {key: info.name for key, info in core._entity_infos.items()}
    commands = []
    for action in actions:
        key = (action.id, action.name)
        if key not in cache:
            context = dict(state=state, facts=list(state.facts),
                variables={p.name:core._entity_infos[v.name] for p,v in action.mapping.items()},
                mapping=action.mapping, entity_infos=core._entity_infos)
            action.command_template = core._logic.grammar.derive(action.command_template, context)
            cache[key] = action.format_command(names)
        commands.append(cache[key])
    core.state['_valid_actions'], core.state['_valid_commands'] = actions, commands
    core.state['admissible_commands'] = sorted(set(commands))
    return dict(zip(commands, actions))


def _apply_native(core, command):
    available = _available(core)
    if command not in available:
        return False
    core._pddl_state.apply(available[command])
    core._moves += 1
    return True


def align_walkthrough(gamefile, actions, expected_observation):
    """CPU process-pool entrypoint; each process owns its cached environments."""
    started = time.monotonic()
    game = normalize_gamefile(gamefile)
    env, walkthrough, game_hash, initial, initial_feedback = _game(game)
    def restore():
        state = _reset_compiled(env, initial, initial_feedback)
        core = env.unwrapped
        for action in actions[:-1]:
            _apply_native(core, action)
            if core._pddl_state.check_goal():
                raise ValueError('Oracle prefix already terminal')
        if actions:
            _available(core)
            state, _, done = env.step(actions[-1])
            if done:
                raise ValueError('Oracle prefix already terminal')
        return state
    state = restore()
    # The initial public observation is stripped by the native manager before
    # being inserted into the prompt. Compare through the same normalization.
    actual = state.feedback.strip()
    expected = expected_observation.strip()
    if expected not in actual and actual not in expected:
        raise ValueError('Oracle replay observation does not match Student state')
    admissible = list(state.admissible_commands)
    candidates = []
    for start in range(len(walkthrough) - 1, -1, -1):
        if walkthrough[start] not in admissible:
            continue
        state = restore()
        continuation = []
        skipped = []
        for index in range(start, len(walkthrough)):
            action = walkthrough[index]
            if not _apply_native(env.unwrapped, action):
                skipped.append(index)
                continue
            continuation.append(action)
            if env.unwrapped._pddl_state.check_goal():
                break
        if env.unwrapped._pddl_state.check_goal() and continuation:
            candidates.append((len(continuation), start, continuation, skipped))
            if len(continuation) == 1:
                break
    result = dict(gamefile=game, game_sha256=game_hash, reference_walkthrough=walkthrough,
                  admissible_actions=admissible, elapsed_seconds=time.monotonic() - started)
    if not candidates:
        return dict(result, status='unavailable', reason='no_winning_reference_suffix')
    _, index, continuation, skipped = min(candidates, key=lambda row: (row[0], row[1]))
    return dict(result, status='verified', next_reference_action=continuation[0],
                reference_index=index, verified_continuation=continuation,
                skipped_reference_indices=skipped, suffix_won=True)
