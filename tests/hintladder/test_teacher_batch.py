import pytest
import torch
from hintladder.teacher_prompt import build_teacher_batch


def test_native_dataproto_alignment(student, provider, tokenizer):
    original = student.batch["input_ids"].clone()
    teacher = build_teacher_batch(student, provider, tokenizer, 512)
    assert torch.equal(teacher.batch["input_ids"][:, 512:], student.batch["responses"])
    assert torch.equal(teacher.batch["attention_mask"][:, 512:], student.batch["response_mask"])
    assert torch.equal(student.batch["input_ids"], original)
    assert teacher.batch["attention_mask"].shape == teacher.batch["position_ids"].shape
    assert teacher.batch["prompts"][0, 0] == 0
    for pos, mask in zip(teacher.batch["position_ids"], teacher.batch["attention_mask"]):
        assert torch.equal(pos[mask.bool()], torch.arange(int(mask.sum())))


def test_overflow_and_validation_fail(student, provider, tokenizer):
    with pytest.raises(ValueError, match="exceeds"):
        build_teacher_batch(student, provider, tokenizer, 32)
    student.meta_info["validate"] = True
    with pytest.raises(ValueError, match="validation"):
        build_teacher_batch(student, provider, tokenizer, 512)


def test_missing_gamefile_and_token_roundtrip(student, provider, tokenizer):
    del student.non_tensor_batch["gamefile"]
    with pytest.raises(KeyError):
        build_teacher_batch(student, provider, tokenizer, 512)


def test_teacher_hook_topk_and_active_mask(student, provider, tokenizer):
    from types import SimpleNamespace
    from omegaconf import OmegaConf
    from verl import DataProto
    from verl.trainer.ppo.hint_ladder_ray_trainer import HintLadderRayTrainer
    trainer = object.__new__(HintLadderRayTrainer)
    trainer.hint_provider, trainer.tokenizer, trainer.use_topk_sdl = provider, tokenizer, True
    trainer.config = OmegaConf.create({"data": {"max_prompt_length": 512}, "actor_rollout_ref": {"actor": {"sdl_topk": 2}}})
    def score(batch):
        assert batch.meta_info["return_topk"] == 2
        assert torch.equal(batch.batch["responses"], student.batch["responses"])
        return DataProto.from_dict(tensors={"old_log_probs": torch.full((2, 4), -1.),
                 "teacher_topk_ids": torch.zeros((2, 4, 2), dtype=torch.long),
                 "teacher_topk_log_probs": torch.full((2, 4, 2), -1.)})
    trainer.actor_rollout_wg = SimpleNamespace(compute_log_prob=score)
    result = trainer._compute_teacher_log_probs(student)
    assert result.shape == (2, 4)
    assert trainer._pending_active_tokens == 5
    assert student.batch["sdl_special_token_keep_mask"].sum() == 5


def test_topk_shape_failure(student, provider, tokenizer):
    from types import SimpleNamespace
    from omegaconf import OmegaConf
    from verl import DataProto
    from verl.trainer.ppo.hint_ladder_ray_trainer import HintLadderRayTrainer
    trainer = object.__new__(HintLadderRayTrainer)
    trainer.hint_provider, trainer.tokenizer, trainer.use_topk_sdl = provider, tokenizer, True
    trainer.config = OmegaConf.create({"data": {"max_prompt_length": 512}, "actor_rollout_ref": {"actor": {"sdl_topk": 2}}})
    trainer.actor_rollout_wg = SimpleNamespace(compute_log_prob=lambda batch: DataProto.from_dict(tensors={
        "old_log_probs": torch.zeros(2, 4), "teacher_topk_ids": torch.zeros(2, 3, 2), "teacher_topk_log_probs": torch.zeros(2, 3, 2)}))
    with pytest.raises(ValueError, match="aligned"):
        trainer._compute_teacher_log_probs(student)


def test_failed_rows_remain_zero_gradient_after_student_changes(student, tokenizer):
    from types import SimpleNamespace
    from omegaconf import OmegaConf
    from verl import DataProto
    from verl.trainer.ppo.hint_ladder_ray_trainer import HintLadderRayTrainer
    from verl.trainer.ppo.skillsd_utils import compute_topk_forward_kl_with_tail, aggregate_sdl_per_token_loss
    class Provider:
        metrics = {}
        def prepare_prompts(self, texts):
            self.records = {text: {'request_sha256': str(i)} for i, text in enumerate(texts)}
            self.failed = texts[0]
        def get_for_prompt(self, game, text):
            return '' if text == self.failed else 'Consider the visible resources.'
        def level_for_prompt(self, game, text):
            return 'L0_FAILED' if text == self.failed else 'L1'
    trainer = object.__new__(HintLadderRayTrainer)
    trainer.hint_provider, trainer.tokenizer, trainer.use_topk_sdl = Provider(), tokenizer, True
    trainer.config = OmegaConf.create({'data': {'max_prompt_length': 512},
                                      'actor_rollout_ref': {'actor': {'sdl_topk': 2}}})
    frozen = torch.tensor([.2, .4, -.3, .5, -.2]).expand(2, 4, 5).clone()
    values, ids = frozen.log_softmax(-1).topk(2, dim=-1)
    def score(teacher):
        clean = student.batch['prompts'][0]
        hinted = teacher.batch['prompts'][0]
        assert torch.equal(clean[clean.ne(0)], hinted[hinted.ne(0)])
        assert teacher.meta_info['hint_ladder_level_counts'] == {'L0_FAILED': 1, 'L1': 1}
        return DataProto.from_dict(tensors={'old_log_probs': torch.full((2, 4), -1.),
            'teacher_topk_ids': ids, 'teacher_topk_log_probs': values})
    trainer.actor_rollout_wg = SimpleNamespace(compute_log_prob=score)
    trainer._compute_teacher_log_probs(student)
    assert trainer._pending_active_tokens == 3
    mask = student.batch['response_mask'] * student.batch['sdl_special_token_keep_mask']
    assert mask[0].sum() == 0 and mask[1].sum() == 3
    initial, _ = compute_topk_forward_kl_with_tail(frozen, ids, values)
    assert torch.allclose(initial[0], torch.zeros_like(initial[0]), atol=1e-7)
    changed = frozen.clone()
    changed[..., 0] += 1.
    changed.requires_grad_(True)
    per_token, _ = compute_topk_forward_kl_with_tail(changed, ids, values)
    assert per_token[0].sum() > 0
    loss = aggregate_sdl_per_token_loss(per_token, mask, normalization_mask=student.batch['response_mask'],
                                      loss_normalization='response_token_mean')
    loss.backward()
    assert changed.grad[0].count_nonzero() == 0
    assert changed.grad[1].abs().sum() > 0
