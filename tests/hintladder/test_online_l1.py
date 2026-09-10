import json
from types import SimpleNamespace

import numpy as np
import pytest

from agent_system.environments.prompts.alfworld import ALFWORLD_TEMPLATE_REASONING
from agent_system.environments.env_package.alfworld.projection import alfworld_projection
from hintladder.online_l1 import OnlineL1Provider, public_state
from hintladder.teacher_prompt import insert_note, remove_note


def prompt():
    return ALFWORLD_TEMPLATE_REASONING.format(task_description='look at statue under the desklamp.',
        step_count=1, history_length=1, action_history="[Observation 1: 'An old observation', Action 1: 'go to sidetable 1']",
        current_step=2, current_observation='You see statue 2 and desklamp 1.',
        admissible_actions="'take statue 2 from sidetable 1'")


def test_public_state_does_not_include_old_observation_or_admissibles():
    assert public_state(prompt()) == dict(task='look at statue under the desklamp.',
        current_observation='You see statue 2 and desklamp 1.', action_history=['go to sidetable 1'])
    with pytest.raises(ValueError, match='private note'):
        public_state(insert_note(prompt(), 'SECRET'))


def test_matched_hint_insertion_roundtrip():
    text = '<|im_start|>user\n' + prompt() + '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
    assert remove_note(insert_note(text, 'Use the visible resources.')) == text


def test_matched_action_projection():
    responses = ['<reasoning>ok</reasoning><action>go to desk 1</action>',
        '<action>go to desk 1', '<action>look</action><action>inventory</action>',
        '<reasoning>ok</reasoning><action>take statue 1</action>']
    commands, valid = alfworld_projection(responses, [['go to desk 1']] * 4,
        require_think_tags=False, matched_reasoning=True)
    assert commands == ['go to desk 1', 'invalid_action', 'invalid_action', 'take statue 1']
    assert valid == [1, 0, 0, 0]


def make_provider(tmp_path, **overrides):
    p = tmp_path / 'prompt.txt'; p.write_text('Give a public-only hint.')
    config = dict(model='glm-5.3-flash', prompt_path=str(p), base_url='http://unused', concurrency=8, retries=2)
    config.update(overrides)
    return OnlineL1Provider(config, tmp_path)


def ok_response(text='Consider the resources already here.'):
    return dict(model='glm-5.3-flash', choices=[dict(finish_reason='stop', message=dict(content=text))])


def other_prompt():
    return prompt().replace('You see statue 2 and desklamp 1.', 'You see nothing here.')


def test_online_dedup_scope_cache_and_fresh_update(tmp_path, monkeypatch):
    provider = make_provider(tmp_path)
    calls = []
    def request(self, route, payload):
        calls.append(payload)
        assert set(json.loads(payload['messages'][1]['content'])) == {'task', 'current_observation', 'action_history'}
        assert payload['reasoning_effort'] == 'low' and 'thinking' not in payload
        return ok_response()
    monkeypatch.setattr('hintladder.online_l1.ModelClient.request', request)
    provider.begin_step(1)
    provider.prepare_prompts([prompt(), prompt()])
    provider.prepare_prompts([prompt()])
    assert len(calls) == 1
    provider.begin_step(2)
    provider.prepare_prompts([prompt()])
    assert len(calls) == 2 and calls[0]['seed'] != calls[1]['seed']
    assert provider.records[prompt()]['oracle_supplied'] is False
    assert provider.level_for_prompt('json_2.1.1/train/a/game.tw-pddl', prompt()) == 'L1'


def test_prefetch_then_prepare_has_no_misses(tmp_path, monkeypatch):
    provider = make_provider(tmp_path)
    calls = []
    monkeypatch.setattr('hintladder.online_l1.ModelClient.request', lambda self, route, payload: calls.append(payload) or ok_response())
    provider.begin_step(3)
    provider.prefetch([prompt(), prompt(), other_prompt()])
    provider.prepare_prompts([prompt(), other_prompt(), prompt()])
    assert len(calls) == 2
    assert provider.metrics['hint_ladder/hint_requests'] == 2
    assert provider.metrics['hint_ladder/hint_prefetch_submitted'] == 2
    assert provider.metrics['hint_ladder/hint_prefetch_misses'] == 0
    assert provider.metrics['hint_ladder/hint_failed_rows'] == 0
    assert provider.records[prompt()]['hint'] == 'Consider the resources already here.'


def test_prefetch_requires_begin_step(tmp_path):
    provider = make_provider(tmp_path)
    with pytest.raises(ValueError, match='begin_step'):
        provider.prefetch([prompt()])


def test_thinking_can_be_disabled_explicitly(tmp_path, monkeypatch):
    provider = make_provider(tmp_path, thinking=False)
    seen = {}
    monkeypatch.setattr('hintladder.online_l1.ModelClient.request', lambda self, route, payload: seen.update(payload) or ok_response())
    provider.begin_step(1)
    provider.prepare_prompts([prompt()])
    assert seen['thinking'] == {'type': 'disabled'}


def test_failed_state_within_budget_becomes_l0_row(tmp_path, monkeypatch):
    provider = make_provider(tmp_path, failure_budget_ratio=0.5, failure_budget_max=10)
    monkeypatch.setattr('hintladder.online_l1.time.sleep', lambda seconds: None)
    def request(self, route, payload):
        if 'nothing here' in payload['messages'][1]['content']:
            return dict(model='glm-5.3-flash', choices=[dict(finish_reason='length', message=dict(content='partial'))])
        return ok_response()
    monkeypatch.setattr('hintladder.online_l1.ModelClient.request', request)
    provider.begin_step(1)
    provider.prepare_prompts([prompt(), other_prompt(), other_prompt()])
    game = 'json_2.1.1/train/a/game.tw-pddl'
    assert provider.get_for_prompt(game, other_prompt()) == ''
    assert provider.level_for_prompt(game, other_prompt()) == 'L0_FAILED'
    assert provider.metrics['hint_ladder/hint_failed_states'] == 1
    assert provider.metrics['hint_ladder/hint_failed_rows'] == 2
    assert provider.metrics['hint_ladder/hint_retries'] >= 1
    assert list((tmp_path / 'online_hints' / 'step_000001').glob('*.errors.json'))


def test_failures_over_budget_stop_training(tmp_path, monkeypatch):
    provider = make_provider(tmp_path, failure_budget_max=0)
    monkeypatch.setattr('hintladder.online_l1.time.sleep', lambda seconds: None)
    monkeypatch.setattr('hintladder.online_l1.ModelClient.request', lambda *a: dict(model='glm-5.3-flash', choices=[dict(finish_reason='length', message=dict(content='partial'))]))
    provider.begin_step(1)
    with pytest.raises(RuntimeError, match='no hint after 2 attempts'):
        provider.prepare_prompts([prompt()])


def test_non_retryable_http_error_propagates(tmp_path, monkeypatch):
    from urllib.error import HTTPError
    provider = make_provider(tmp_path)
    def request(self, route, payload):
        raise HTTPError('http://unused', 401, 'unauthorized', hdrs=None, fp=None)
    monkeypatch.setattr('hintladder.online_l1.ModelClient.request', request)
    provider.begin_step(1)
    with pytest.raises(HTTPError):
        provider.prepare_prompts([prompt()])


def test_proxy_prefetches_before_delegating():
    import torch
    events = []
    class Tok:
        def decode(self, ids, **kwargs):
            return ''.join(chr(i) for i in ids)
    class Provider:
        def prefetch(self, texts):
            events.append(('prefetch', tuple(texts)))
    class Group:
        world_size = 8
        def generate_sequences(self, prompts):
            events.append(('generate',)); return 'out'
        def begin_rollout_generation(self):
            return {'enabled': True}
    from verl.trainer.ppo.hint_ladder_ray_trainer import PrefetchingRolloutProxy
    proxy = PrefetchingRolloutProxy(Group(), Provider(), Tok())
    prompts = SimpleNamespace(batch={'input_ids': torch.tensor([[0, 97, 98], [0, 0, 99]]),
                                     'attention_mask': torch.tensor([[0, 1, 1], [0, 0, 1]])})
    assert proxy.generate_sequences(prompts) == 'out'
    assert events == [('prefetch', ('ab', 'c')), ('generate',)]
    assert proxy.world_size == 8 and proxy.begin_rollout_generation() == {'enabled': True}


def test_partial_validation_waves_restore_pool(monkeypatch):
    from omegaconf import OmegaConf
    from verl import DataProto
    from verl.trainer.ppo.hint_ladder_ray_trainer import HintLadderRayTrainer, RayPPOTrainer
    trainer = object.__new__(HintLadderRayTrainer)
    trainer.config = OmegaConf.create({'env': {'alfworld': {'allow_partial_validation_wave': True}}})
    workers = list(range(64))
    pool = SimpleNamespace(workers=workers, num_processes=64, prev_admissible_commands=[None]*64)
    trainer.val_envs = SimpleNamespace(envs=pool, validation_capacity=64)
    counts = []
    def rollout(self, chunk):
        counts.append(len(chunk)); assert len(pool.workers) == len(chunk) == pool.num_processes
        chunk.non_tensor_batch['success_rate'] = np.ones(len(chunk))
        return chunk
    monkeypatch.setattr(RayPPOTrainer, '_run_validation_rollout', rollout)
    batch = DataProto.from_dict(non_tensors={'validation_item_id': np.array([f'0:{i}' for i in range(134)], dtype=object)})
    result = trainer._run_validation_rollout(batch)
    assert counts == [64, 64, 6] and len(result) == 134
    assert pool.workers is workers and pool.num_processes == 64
