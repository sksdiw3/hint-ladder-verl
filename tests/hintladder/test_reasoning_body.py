from types import SimpleNamespace

import numpy as np
import pytest
import torch
from omegaconf import OmegaConf

from hintladder.response_format import reasoning_body_mask
from hintladder.config import load_config, validate_student_config
from hintladder.io import ROOT
from verl import DataProto
from verl.trainer.ppo.hint_ladder_ray_trainer import HintLadderRayTrainer
from verl.trainer.ppo.skillsd_utils import compute_topk_forward_kl_with_tail, aggregate_sdl_per_token_loss


class PieceTokenizer:
    """Noncanonical token segmentation, including tokens crossing tag boundaries."""
    all_special_ids = [0, 1]

    def __init__(self, pieces):
        self.pieces = {i + 2: piece for i, piece in enumerate(pieces)}

    def decode(self, ids, **kwargs):
        return ''.join(self.pieces.get(int(i), '') for i in ids)


@pytest.mark.parametrize('pieces,selected', [
    (['<', 'reason', 'ing', '>', 'Check', ' here.', '</', 'reason', 'ing', '>',
      '<action>', 'look', '</action>'], [4, 5]),
    (['<reasoning>Check', ' here', ' now.</', 'reasoning>', '<action>look</action>'], [1]),
    (['<reasoning>\n', '检查物品。', '\n</reasoning>', '\n<action>look</action>'], [1]),
    (['<reasoning>', 'Check', '<action>look</action>'], []),
    (['<reasoning>', 'Check', '</reasoning><action>look'], []),
    (['<reasoning>', 'Check', '</reasoning><action>look</action> extra'], []),
])
def test_original_token_boundaries(pieces, selected):
    tokenizer = PieceTokenizer(pieces)
    response = torch.tensor([[0, *range(2, len(pieces) + 2), 1, 0]])
    mask = reasoning_body_mask(response, response.ne(0), tokenizer)
    assert mask[0].nonzero().flatten().tolist() == [i + 1 for i in selected]


def test_reasoning_scope_config():
    config, _ = load_config(ROOT / 'configs/experiments/l1_online_full_20260910/train_full_fast.yaml')
    config['actor_rollout_ref.actor.sdl_loss_token_scope'] = 'reasoning_body'
    validate_student_config(config)
    config['env.alfworld.prompt_style'] = 'action_tag_only'
    with pytest.raises(ValueError, match='reasoning_body'):
        validate_student_config(config)


def test_teacher_hook_body_only_zero_gradient(student, tokenizer, provider):
    texts = ['<reasoning>Find the object.</reasoning><action>look</action>',
             '<reasoning>Broken close.<action>look</action>']
    ids = [tokenizer.encode(text) + [tokenizer.eos_token_id] for text in texts]
    responses = torch.zeros((2, max(map(len, ids))), dtype=torch.long)
    for i, row in enumerate(ids):
        responses[i, :len(row)] = torch.tensor(row)
    prompts = student.batch['prompts']
    attention = torch.cat([prompts.ne(0), responses.ne(0)], -1).long()
    batch = DataProto.from_dict(tensors={'prompts': prompts, 'responses': responses,
        'input_ids': torch.cat([prompts, responses], -1), 'attention_mask': attention,
        'position_ids': (attention.cumsum(-1) - 1).clamp(min=0), 'response_mask': responses.ne(0).long()},
        non_tensors={'gamefile': student.non_tensor_batch['gamefile'],
                     'sdl_format_valid': np.array([True, False])})
    trainer = object.__new__(HintLadderRayTrainer)
    trainer.hint_provider, trainer.tokenizer = provider, tokenizer
    trainer.use_topk_sdl = True
    trainer.config = OmegaConf.create({'data': {'max_prompt_length': 512},
        'actor_rollout_ref': {'actor': {'sdl_topk': 2, 'sdl_loss_token_scope': 'reasoning_body'}}})
    teacher_logits = torch.tensor([.2, .4, -.3, .5, -.2]).expand(*responses.shape, 5).clone()
    values, top_ids = teacher_logits.log_softmax(-1).topk(2, dim=-1)
    trainer.actor_rollout_wg = SimpleNamespace(compute_log_prob=lambda teacher: DataProto.from_dict(tensors={
        'old_log_probs': torch.full(responses.shape, -1.),
        'teacher_topk_ids': top_ids, 'teacher_topk_log_probs': values}))
    trainer._compute_teacher_log_probs(batch)
    keep = batch.batch['sdl_special_token_keep_mask'].bool()
    assert tokenizer.decode(responses[0][keep[0]]) == 'Find the object.'
    assert not keep[1].any()
    assert trainer._pending_active_tokens == len('Find the object.')
    assert batch.select_idxs([1, 0]).non_tensor_batch['sdl_supervised_tokens'].tolist() == [0, len('Find the object.')]
    changed = teacher_logits.clone()
    changed[..., 0] += 1.
    changed.requires_grad_()
    per_token, _ = compute_topk_forward_kl_with_tail(changed, top_ids, values)
    loss = aggregate_sdl_per_token_loss(per_token, keep, normalization_mask=batch.batch['response_mask'],
                                      loss_normalization='response_token_mean')
    loss.backward()
    assert changed.grad[~keep].count_nonzero() == 0
    assert (changed.grad[keep].abs().sum(-1) > 0).all()
