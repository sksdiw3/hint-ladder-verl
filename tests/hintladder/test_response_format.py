import json
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from omegaconf import OmegaConf

from hintladder.response_format import annotate_response_format, response_format_error
from verl import DataProto
from verl.trainer.ppo.hint_ladder_ray_trainer import HintLadderRayTrainer
from verl.trainer.ppo.skillsd_utils import compute_topk_forward_kl_with_tail, aggregate_sdl_per_token_loss


@pytest.mark.parametrize('response,reason', [
    ('<reasoning>Check nearby.</reasoning><action>go to desk 1</action>', ''),
    ('<reasoning>A wrong plan.</reasoning><action>nonexistent command</action>', ''),
    ('<think>Check.</think><action>look</action>', 'forbidden_think_tag'),
    ('</think><reasoning>Check.</reasoning><action>look</action>', 'forbidden_think_tag'),
    ('<reasoning>Check.</reasoning><action>look', 'invalid_reasoning_action_format'),
    ('<action>look</action>', 'invalid_reasoning_action_format'),
    ('<reasoning>Check.</reasoning><action>look</action><action>look</action>', 'invalid_reasoning_action_format'),
    ('<reasoning>Check.</reasoning><action>look</action>Extra text', 'invalid_reasoning_action_format'),
    ('<reasoning> </reasoning><action>look</action>', 'empty_reasoning'),
    ('<reasoning>Check.</reasoning><action> </action>', 'empty_action'),
])
def test_response_formats(response, reason):
    assert response_format_error(response, 'explicit_reasoning') == reason


def test_action_only_format():
    assert response_format_error('<action>look</action>', 'action_tag_only') == ''
    assert response_format_error('<action>look', 'action_tag_only')


def test_annotation_preserves_trajectory_and_survives_reordering(student, tmp_path):
    tokenizer = SimpleNamespace(batch_decode=lambda *a, **kw: [
        '<think>wrong tags</think><action>look</action>',
        '<reasoning>Inspect.</reasoning><action>look</action>'])
    student.non_tensor_batch['traj_uid'] = np.array(['a', 'b'], dtype=object)
    student.non_tensor_batch['turn_step'] = np.array([4, 7])
    original = student.batch['responses'].clone()
    metrics = annotate_response_format(student, tokenizer, 'explicit_reasoning', tmp_path, 24)
    assert metrics['hint_ladder/format_invalid_rows'] == 1
    assert len(student) == 2 and torch.equal(student.batch['responses'], original)
    assert student.select_idxs([1, 0, 0]).non_tensor_batch['sdl_format_valid'].tolist() == [True, False, False]
    row = json.loads((tmp_path / 'format_errors/step_000024.jsonl').read_text())
    assert row['traj_uid'] == 'a' and row['turn_step'] == 4
    assert row['reason'] == 'forbidden_think_tag' and '<think>' in row['output']


@pytest.mark.parametrize('valid', [[False, True], [False, False]])
def test_format_filter_zero_gradient_and_empty_batch_no_optimizer_step(student, provider, tokenizer, valid):
    trainer = object.__new__(HintLadderRayTrainer)
    trainer.hint_provider, trainer.tokenizer = provider, tokenizer
    trainer.use_topk_sdl = trainer.use_sdl = True
    trainer.config = OmegaConf.create({'data': {'max_prompt_length': 512},
        'actor_rollout_ref': {'actor': {'sdl_topk': 2, 'pg_loss_coef': 0.0}}})
    student.non_tensor_batch['sdl_format_valid'] = np.array(valid)
    teacher_logits = torch.tensor([.2, .4, -.3, .5, -.2]).expand(2, 4, 5).clone()
    values, ids = teacher_logits.log_softmax(-1).topk(2, dim=-1)
    calls = []
    trainer.actor_rollout_wg = SimpleNamespace(
        compute_log_prob=lambda batch: DataProto.from_dict(tensors={
            'old_log_probs': torch.full((2, 4), -1.),
            'teacher_topk_ids': ids, 'teacher_topk_log_probs': values}),
        update_actor=lambda batch: calls.append(batch) or DataProto(meta_info={'metrics': {'actor/sdl_loss': [0.2]}}))
    trainer._compute_teacher_log_probs(student)
    mask = student.batch['response_mask'] * student.batch['sdl_special_token_keep_mask']
    assert trainer._pending_active_tokens == (3 if any(valid) else 0)
    changed = teacher_logits.clone()
    changed[..., 0] += 1.0
    changed.requires_grad_(True)
    losses, _ = compute_topk_forward_kl_with_tail(changed, ids, values)
    loss = aggregate_sdl_per_token_loss(losses, mask, normalization_mask=student.batch['response_mask'],
                                        loss_normalization='response_token_mean')
    loss.backward()
    assert changed.grad[0].count_nonzero() == 0
    assert bool(changed.grad[1].abs().sum() > 0) == any(valid)
    result = trainer._update_actor_if_supervised(student)
    assert len(calls) == int(any(valid))
    assert result['hint_ladder/update_skipped_no_supervision'] == int(not any(valid))
