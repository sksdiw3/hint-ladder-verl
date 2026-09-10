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


def test_online_dedup_scope_cache_and_fresh_update(tmp_path, monkeypatch):
    p = tmp_path/'prompt.txt'; p.write_text('Give a public-only hint.')
    provider = OnlineL1Provider(dict(model='glm-5.3-flash', prompt_path=str(p), base_url='http://unused', concurrency=64), tmp_path)
    calls = []
    def request(self, route, payload):
        calls.append(payload)
        assert set(json.loads(payload['messages'][1]['content'])) == {'task', 'current_observation', 'action_history'}
        return dict(model='glm-5.3-flash', choices=[dict(finish_reason='stop', message=dict(content='Consider the resources already here.'))])
    monkeypatch.setattr('hintladder.online_l1.ModelClient.request', request)
    provider.step = 1
    provider.prepare_prompts([prompt(), prompt()])
    provider.prepare_prompts([prompt()])
    assert len(calls) == 1
    provider.step = 2
    provider.prepare_prompts([prompt()])
    assert len(calls) == 2 and calls[0]['seed'] != calls[1]['seed']
    assert provider.records[prompt()]['oracle_supplied'] is False


def test_online_never_falls_back_on_api_failure(tmp_path, monkeypatch):
    p = tmp_path/'prompt.txt'; p.write_text('Give a hint.')
    provider = OnlineL1Provider(dict(model='glm-5.3-flash', prompt_path=str(p), base_url='http://unused', retries=1), tmp_path)
    monkeypatch.setattr('hintladder.online_l1.ModelClient.request', lambda *a: dict(model='glm-5.3-flash', choices=[dict(finish_reason='length', message=dict(content='partial'))]))
    with pytest.raises(RuntimeError, match='exhausted'):
        provider.prepare_prompts([prompt()])


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
