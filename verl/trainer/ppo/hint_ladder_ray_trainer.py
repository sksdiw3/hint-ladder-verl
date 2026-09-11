"""Hint Ladder's only trainer subclass.

fit is adapted from SMRC-SD skillsd_ray_trainer.py at 1a0996b (Apache-2.0).
Upstream unconditionally invokes a teacher and has no end-of-step budget hook.
The copied fit removes SkillBank, candidate-CE, debug-environment-variable and
rollout-only branches, and adds SDL-off, clean split validation and token budgets.
Rollout, loss, advantages, validation and model checkpoint implementations remain
native. Functions below wire those existing components; no second training loop.
"""
from pathlib import Path

import numpy as np
import ray
import torch
from omegaconf import OmegaConf

from verl import DataProto
from verl.trainer.ppo.skillsd_ray_trainer import SkillSDRayTrainer
from verl.trainer.ppo.ray_trainer import (
    RayPPOTrainer, ResourcePoolManager, Role, _timer, apply_invalid_action_penalty,
    compute_advantage, compute_response_mask,
)
from verl.trainer.ppo.reward import compute_reward
from verl.trainer.ppo.metric_utils import compute_data_metrics, compute_timing_metrics, compute_throughout_metrics
from verl.utils.metric import reduce_metrics
from verl.utils.torch_functional import masked_mean
from agent_system.multi_turn_rollout import adjust_batch

from hintladder.budget import ActiveTokenBudget
from hintladder.hint_bank import HintProvider
from hintladder.io import read_json, write_json, read_jsonl
from hintladder.keys import data_root, normalize_gamefile, read_game_list
from hintladder.teacher_prompt import build_teacher_batch, OPEN
from hintladder.online_l1 import make_provider
from hintladder.response_format import annotate_response_format


def save_budget(trainer):
    path = Path(trainer.config.trainer.default_local_dir) / f"global_step_{trainer.global_steps}"
    write_json(path / "hint_ladder_budget.json", trainer.budget.to_dict())


def restore_budget(trainer):
    if not trainer.global_steps:
        return
    resume = trainer.config.trainer.resume_from_path
    path = Path(resume) if resume else Path(trainer.config.trainer.default_local_dir) / f"global_step_{trainer.global_steps}"
    state = read_json(path / "hint_ladder_budget.json")
    trainer.budget = ActiveTokenBudget(trainer.budget.limit, used=state["used"])


def log_metrics(trainer, logger, metrics):
    metrics = {key: value.item() if isinstance(value, (np.generic, torch.Tensor)) else value
               for key, value in metrics.items()}
    # This is the complete update (or initial validation) record. With an
    # explicit step, W&B otherwise buffers it until the next update arrives.
    logger.log(data=metrics, step=trainer.global_steps, commit=True)
    path = Path(trainer.config.trainer.default_local_dir) / "metrics.jsonl"
    import json
    line = json.dumps({"step": trainer.global_steps, **metrics}, allow_nan=False) + "\n"
    with path.open("a") as stream:
        stream.write(line)


class PrefetchingRolloutProxy:
    """Wraps the rollout worker group for one training rollout.

    A turn's Student prompts are known before generation starts, so hint requests
    for those public states are submitted here and complete while the GPUs keep
    generating. Every other attribute is delegated unchanged. Validation never
    goes through this proxy.
    """

    def __init__(self, worker_group, provider, tokenizer):
        self._group, self._provider, self._tokenizer = worker_group, provider, tokenizer

    def generate_sequences(self, prompts):
        ids, mask = prompts.batch["input_ids"], prompts.batch["attention_mask"]
        # Same decode settings as build_teacher_batch, so the dedup keys match.
        self._provider.prefetch([self._tokenizer.decode(ids[i][mask[i].bool()].tolist(), skip_special_tokens=False,
                                                        clean_up_tokenization_spaces=False) for i in range(len(ids))])
        return self._group.generate_sequences(prompts)

    def __getattr__(self, name):
        return getattr(self._group, name)


def validate_clean(trainer):
    """Call upstream's complete validation loop once per fixed split."""
    original = trainer.config.trainer.validation_data_dir
    original_loader = trainer.val_dataloader
    pending = getattr(trainer.hint_provider, "pending_requests", None)
    from torch.utils.data import DataLoader, Subset
    result = {}
    try:
        for split, games in trainer.validation_games.items():
            if len(games) != len(trainer.val_dataset):
                trainer.val_dataloader = DataLoader(Subset(trainer.val_dataset, range(len(games))),
                    batch_size=len(games), collate_fn=original_loader.collate_fn, shuffle=False)
            else:
                trainer.val_dataloader = original_loader
            trainer.val_envs.envs.fixed_game_files = [str(data_root() / game) for game in games]
            trainer.config.trainer.validation_data_dir = str(Path(original) / split)
            values = RayPPOTrainer._validate(trainer)
            result.update({"val/" + split + "/" + key.removeprefix("val/"): value for key, value in values.items()})
    finally:
        trainer.config.trainer.validation_data_dir = original
        trainer.val_dataloader = original_loader
    if pending is not None and trainer.hint_provider.pending_requests != pending:
        raise RuntimeError("hint requests were submitted during clean validation")
    return result


class HintLadderRayTrainer(SkillSDRayTrainer):
    def __init__(self, *args, hint_provider, validation_games, **kwargs):
        super().__init__(*args, skill_provider=None, **kwargs)
        self.hint_provider = hint_provider
        self.validation_games = validation_games
        self.budget = ActiveTokenBudget(self.config.algorithm.hint_ladder.active_token_budget)
        self.use_sdl = bool(self.config.actor_rollout_ref.actor.use_sdl_loss)
        self.use_topk_sdl = self.config.actor_rollout_ref.actor.sdl_loss_mode == "topk_forward_kl"
        self._last_teacher_skill_metrics = {}

    def _run_validation_rollout(self, test_gen_batch):
        if not self.config.env.alfworld.get('allow_partial_validation_wave', False):
            return super()._run_validation_rollout(test_gen_batch)
        from contextlib import contextmanager
        @contextmanager
        def active_workers(count):
            pool = self.val_envs.envs
            workers, size, commands = pool.workers, pool.num_processes, pool.prev_admissible_commands
            try:
                pool.workers, pool.num_processes = workers[:count], count
                pool.prev_admissible_commands = [None] * count
                yield
            finally:
                pool.workers, pool.num_processes, pool.prev_admissible_commands = workers, size, commands
        capacity = self.val_envs.validation_capacity
        outputs, success_totals = [], {}
        for start in range(0, len(test_gen_batch), capacity):
            chunk = test_gen_batch[start:start + capacity]
            with active_workers(len(chunk)):
                output = RayPPOTrainer._run_validation_rollout(self, chunk)
            for key, values in output.non_tensor_batch.items():
                if 'success_rate' in key and len(values):
                    success_totals[key] = success_totals.get(key, 0.) + float(values[0]) * len(chunk)
            outputs.append(output)
        combined = DataProto.concat(outputs)
        for key, total in success_totals.items():
            combined.non_tensor_batch[key] = np.full(len(combined), total / len(test_gen_batch), dtype=np.float32)
        return combined

    def _compute_teacher_log_probs(self, batch):
        teacher = build_teacher_batch(batch, self.hint_provider, self.tokenizer, self.config.data.max_prompt_length)
        teacher.meta_info["calculate_entropy"] = False
        if self.use_topk_sdl:
            teacher.meta_info["return_topk"] = self.config.actor_rollout_ref.actor.sdl_topk
        output = self.actor_rollout_wg.compute_log_prob(teacher)
        log_probs = output.batch["old_log_probs"]
        responses = batch.batch["responses"]
        if log_probs.shape != responses.shape or not torch.isfinite(log_probs).all():
            raise ValueError("Teacher actual-token log probabilities have invalid shape or values")
        if self.use_topk_sdl:
            ids, probs = output.batch["teacher_topk_ids"], output.batch["teacher_topk_log_probs"]
            if ids.shape != probs.shape or ids.shape != (*responses.shape, teacher.meta_info["return_topk"]):
                raise ValueError("Teacher top-k distributions are not aligned with Student responses")
            if not torch.isfinite(probs).all():
                raise ValueError("nonfinite teacher top-k log probabilities")
            batch.batch["teacher_topk_ids"], batch.batch["teacher_topk_log_probs"] = ids, probs
        special = torch.tensor(self.tokenizer.all_special_ids, dtype=responses.dtype, device=responses.device)
        keep = ~torch.isin(responses, special)
        if "online_l1_level" in batch.non_tensor_batch:
            failed = torch.tensor([level == "L0_FAILED" for level in batch.non_tensor_batch["online_l1_level"]],
                                  dtype=torch.bool, device=responses.device)
            # A clean frozen Teacher is only equal before optimizer updates.
            # Native SDL masking keeps failed rows at zero loss/gradient after
            # earlier minibatches have already changed Student weights.
            keep = keep & ~failed[:, None]
        if "sdl_format_valid" in batch.non_tensor_batch:
            valid = torch.as_tensor(batch.non_tensor_batch['sdl_format_valid'],
                                    dtype=torch.bool, device=responses.device)
            keep = keep & valid[:, None]
        batch.batch["sdl_special_token_keep_mask"] = keep.to(batch.batch["response_mask"].dtype)
        active = int((batch.batch["response_mask"] * keep).sum().item())
        self._pending_active_tokens = active
        self._last_teacher_skill_metrics = {"hint_ladder/active_tokens_step": active}
        self._last_teacher_skill_metrics.update(getattr(self.hint_provider, 'metrics', {}))
        self._last_teacher_skill_metrics.update({f"hint_ladder/level_counts/{key}": value
                                                for key, value in teacher.meta_info["hint_ladder_level_counts"].items()})
        return log_probs

    def _rollout_dump_extra_infos(self, batch, reward_extra_infos_dict):
        result = super()._rollout_dump_extra_infos(batch, reward_extra_infos_dict)
        for key in ('online_l1_hint', 'online_l1_level', 'online_l1_request_sha256',
                    'sdl_format_valid', 'sdl_format_error'):
            if key in batch.non_tensor_batch:
                result[key] = batch.non_tensor_batch[key]
        return result

    def _update_actor_if_supervised(self, batch):
        # Do not run AdamW with all-zero supervision: momentum/weight decay and
        # the LR scheduler could still change state despite zero new gradients.
        if self.use_sdl and self._pending_active_tokens == 0 and self.config.actor_rollout_ref.actor.pg_loss_coef == 0:
            return {'hint_ladder/update_skipped_no_supervision': 1}
        output = self.actor_rollout_wg.update_actor(batch)
        return {'hint_ladder/update_skipped_no_supervision': 0, **reduce_metrics(output.meta_info['metrics'])}

    def fit(self):
        try:
            return self._fit()
        finally:
            if hasattr(self.hint_provider, "close"):
                self.hint_provider.close()

    def _fit(self):
        from verl.utils.tracking import Tracking
        logger = Tracking(project_name=self.config.trainer.project_name,
                          experiment_name=self.config.trainer.experiment_name,
                          default_backend=self.config.trainer.logger,
                          config=OmegaConf.to_container(self.config, resolve=True))
        self.global_steps = 0
        # A refreshed curriculum changes rows. Restore model/optimizer/step via
        # native checkpoint loading, then restore the fresh native dataloader.
        fresh_data_state = self.train_dataloader.state_dict()
        self._load_checkpoint()
        if self.config.algorithm.hint_ladder.reset_dataloader:
            self.train_dataloader.load_state_dict(fresh_data_state)
        restore_budget(self)
        if self.config.trainer.val_before_train:
            log_metrics(self, logger, validate_clean(self))
        if self.config.trainer.val_only or self.budget.exhausted or self.global_steps >= self.total_training_steps:
            return
        self.global_steps += 1
        for epoch in range(self.config.trainer.total_epochs):
            for batch_dict in self.train_dataloader:
                metrics, timing_raw = {}, {}
                batch = DataProto.from_single_dict(batch_dict)
                pop_keys = [key for key in ("raw_prompt_ids", "data_source", "multi_modal_data", "raw_prompt", "tools_kwargs", "env_kwargs")
                            if key in batch.non_tensor_batch]
                gen_batch = batch.pop(batch_keys=["input_ids", "attention_mask", "position_ids"], non_tensor_batch_keys=pop_keys)
                is_last_step = self.global_steps >= self.total_training_steps
                online = hasattr(self.hint_provider, "prefetch")
                rollout_group = self.actor_rollout_wg
                if online:
                    self.hint_provider.begin_step(self.global_steps)
                    rollout_group = PrefetchingRolloutProxy(self.actor_rollout_wg, self.hint_provider, self.tokenizer)
                with _timer("step", timing_raw):
                    with _timer("gen", timing_raw):
                        batch = self.traj_collector.multi_turn_loop(gen_batch=gen_batch, actor_rollout_wg=rollout_group,
                                                                   envs=self.envs, is_train=True, global_step=self.global_steps)
                    # Validate native gamefile plumbing even for the GRPO L0 arm.
                    for game in batch.non_tensor_batch["gamefile"]:
                        if online:
                            self.hint_provider.level_for(game)
                        else:
                            self.hint_provider.get(game)
                    for text in self.tokenizer.batch_decode(batch.batch["prompts"], skip_special_tokens=False):
                        if OPEN in text:
                            raise ValueError("private note leaked into Student rollout")
                    metrics.update(annotate_response_format(batch, self.tokenizer,
                        self.config.env.alfworld.prompt_style, self.config.trainer.default_local_dir,
                        self.global_steps))
                    batch = adjust_batch(self.config, batch)
                    batch.batch["response_mask"] = compute_response_mask(batch)
                    if self.config.trainer.balance_batch:
                        self._balance_batch(batch, metrics=metrics)
                    batch.meta_info["global_token_num"] = batch.batch["attention_mask"].sum(-1).tolist()
                    with _timer("reward", timing_raw):
                        reward_tensor, reward_extra = compute_reward(batch, self.reward_fn)
                    with _timer("old_log_prob", timing_raw):
                        if self.config.algorithm.hint_ladder.get('monitor_top1', False):
                            batch.meta_info['return_topk'] = 1
                        old = self.actor_rollout_wg.compute_log_prob(batch)
                        metrics["actor/entropy_loss"] = masked_mean(old.batch.pop("entropys"), batch.batch["response_mask"]).item()
                        if self.config.algorithm.hint_ladder.get('monitor_top1', False):
                            probs = old.batch.pop('teacher_topk_log_probs').squeeze(-1).exp()
                            old.batch.pop('teacher_topk_ids')
                            metrics['distribution/top1_at_rollout_temperature'] = masked_mean(probs, batch.batch['response_mask']).item()
                            metrics['distribution/entropy_at_rollout_temperature'] = metrics['actor/entropy_loss']
                            batch.meta_info.pop('return_topk')
                        batch = batch.union(old)
                    if self.use_sdl:
                        with _timer("teacher_forward", timing_raw):
                            batch.batch["teacher_log_probs"] = self._compute_teacher_log_probs(batch)
                        metrics.update(self._last_teacher_skill_metrics)
                        delta = batch.batch["teacher_log_probs"] - batch.batch["old_log_probs"]
                        metrics["skillsd/teacher_student_gap_mean"] = masked_mean(delta, batch.batch["response_mask"]).item()
                        if "online_l1_level" in batch.non_tensor_batch:
                            levels = list(batch.non_tensor_batch["online_l1_level"])
                        else:
                            levels = [self.hint_provider.level_for(game) for game in batch.non_tensor_batch["gamefile"]]
                        active_mask = batch.batch["response_mask"] * batch.batch["sdl_special_token_keep_mask"]
                        for level in sorted(set(levels)):
                            selected = torch.tensor([value == level for value in levels], device=delta.device)
                            metrics[f"hint_ladder/teacher_student_gap/{level}"] = masked_mean(delta[selected], active_mask[selected]).item()
                    with _timer("adv", timing_raw):
                        batch.batch["token_level_scores"] = reward_tensor
                        batch.non_tensor_batch.update({key: np.array(value) for key, value in reward_extra.items()})
                        if self.config.actor_rollout_ref.actor.use_invalid_action_penalty:
                            batch, invalid = apply_invalid_action_penalty(batch, invalid_action_penalty_coef=self.config.actor_rollout_ref.actor.invalid_action_penalty_coef)
                            metrics.update(invalid)
                        batch.batch["token_level_rewards"] = batch.batch["token_level_scores"]
                        batch = compute_advantage(batch, adv_estimator=self.config.algorithm.adv_estimator,
                                                  gamma=self.config.algorithm.gamma, lam=self.config.algorithm.lam,
                                                  num_repeat=self.config.actor_rollout_ref.rollout.n,
                                                  norm_adv_by_std_in_grpo=self.config.algorithm.norm_adv_by_std_in_grpo,
                                                  multi_turn=self.config.actor_rollout_ref.rollout.multi_turn.enable,
                                                  use_pf_ppo=False)
                    with _timer("update_actor", timing_raw):
                        batch.meta_info["multi_turn"] = self.config.actor_rollout_ref.rollout.multi_turn.enable
                        metrics.update(self._update_actor_if_supervised(batch))
                    # Count only after a successful actor update. With one PPO
                    # epoch and no SDL filters this is precisely its active mask.
                    if self.use_sdl:
                        self.budget.add(self._pending_active_tokens)
                    metrics["hint_ladder/active_tokens_cumulative"] = self.budget.used
                    is_last_step = is_last_step or self.budget.exhausted
                    if self.config.trainer.rollout_data_dir and self._should_dump_rollout(is_last_step):
                        self._dump_rollout_generations_from_batch(batch, reward_extra, self.config.trainer.rollout_data_dir)
                    if is_last_step or (self.config.trainer.test_freq > 0 and self.global_steps % self.config.trainer.test_freq == 0):
                        with _timer("testing", timing_raw):
                            metrics.update(validate_clean(self))
                    if is_last_step or (self.global_steps == 1 and self.config.trainer.get('save_first_step', False)) or (self.config.trainer.save_freq > 0 and self.global_steps % self.config.trainer.save_freq == 0):
                        with _timer("save_checkpoint", timing_raw):
                            self._save_checkpoint()
                            save_budget(self)
                metrics.update({"training/global_step": self.global_steps, "training/epoch": epoch})
                metrics.update(compute_data_metrics(batch=batch, use_critic=False))
                metrics.update(compute_timing_metrics(batch=batch, timing_raw=timing_raw))
                metrics.update(compute_throughout_metrics(batch=batch, timing_raw=timing_raw, n_gpus=self.resource_pool_manager.get_n_gpus()))
                log_metrics(self, logger, metrics)
                if self.budget.exhausted:
                    write_json(Path(self.config.trainer.default_local_dir) / "budget_exhausted.json",
                               {"step": self.global_steps, **self.budget.to_dict()})
                if is_last_step:
                    return
                self.global_steps += 1
        raise RuntimeError("training epochs ended before the requested step/token budget")


def run_training(config, stage):
    from verl.trainer.constants_ppo import get_ppo_ray_runtime_env
    if not ray.is_initialized():
        options = OmegaConf.to_container(config.get("ray_init", {}), resolve=True)
        options["runtime_env"] = OmegaConf.to_container(OmegaConf.merge(get_ppo_ray_runtime_env(), options.get("runtime_env", {})))
        ray.init(**options)
    ray.get(ray.remote(num_cpus=1)(_training_task).remote(config, stage))


def _training_task(config, stage):
    from transformers import set_seed
    from verl.single_controller.ray import RayWorkerGroup
    from verl.workers.fsdp_workers import ActorRolloutRefWorker, AsyncActorRolloutRefWorker
    from verl.utils import hf_tokenizer, hf_processor
    from verl.utils.fs import copy_to_local
    from verl.utils.dataset.rl_dataset import collate_fn
    from verl.trainer.main_ppo import create_rl_dataset, create_rl_sampler
    from agent_system.environments import make_envs
    from agent_system.multi_turn_rollout import TrajectoryCollector
    from agent_system.reward_manager import EpisodeRewardManager

    set_seed(int(config.env.seed))
    local = copy_to_local(config.actor_rollout_ref.model.path, use_shm=config.actor_rollout_ref.model.get("use_shm", False))
    tokenizer = hf_tokenizer(local, trust_remote_code=config.data.trust_remote_code)
    processor = hf_processor(local, trust_remote_code=config.data.trust_remote_code, use_fast=True)
    envs, val_envs = make_envs(config)
    provider = make_provider(OmegaConf.to_container(config.algorithm.hint_ladder, resolve=True), config.trainer.default_local_dir)
    splits = {split: read_game_list(path) for split, path in stage["stage.validation_games"].items()}
    worker = AsyncActorRolloutRefWorker if config.actor_rollout_ref.rollout.mode == "async" else ActorRolloutRefWorker
    pool = ResourcePoolManager({"global_pool": [config.trainer.n_gpus_per_node] * config.trainer.nnodes},
                               {Role.ActorRollout: "global_pool"})
    train_data = create_rl_dataset(config.data.train_files, config.data, tokenizer, processor)
    trainer = HintLadderRayTrainer(config=config, tokenizer=tokenizer, processor=processor,
                                  role_worker_mapping={Role.ActorRollout: ray.remote(worker)}, resource_pool_manager=pool,
                                  ray_worker_group_cls=RayWorkerGroup,
                                  reward_fn=EpisodeRewardManager(tokenizer=tokenizer, num_examine=0, normalize_by_length=False),
                                  val_reward_fn=EpisodeRewardManager(tokenizer=tokenizer, num_examine=0, normalize_by_length=False),
                                  train_dataset=train_data, val_dataset=create_rl_dataset(config.data.val_files, config.data, tokenizer, processor),
                                  collate_fn=collate_fn, train_sampler=create_rl_sampler(config.data, train_data),
                                  device_name=config.trainer.device, traj_collector=TrajectoryCollector(config, tokenizer, processor),
                                  envs=envs, val_envs=val_envs, hint_provider=provider, validation_games=splits)
    try:
        trainer.init_workers()
        trainer.fit()
    finally:
        envs.envs.close()
        val_envs.envs.close()


class FrozenAPIWorker:
    """Only generation transport; the native collector owns all environment turns."""
    world_size = 1

    def __init__(self, client, tokenizer, config, note, seed):
        self.client, self.tokenizer, self.config = client, tokenizer, config
        self.note, self.seed, self.turn = note, seed, 0
        self.request_tokens = []

    def generate_sequences(self, batch):
        from hintladder.teacher_prompt import insert_note
        prompts, mask = batch.batch["input_ids"], batch.batch["attention_mask"]
        if len(prompts) != 1:
            raise ValueError("frozen probe transports one native environment at a time")
        clean_ids = prompts[0][mask[0].bool()].tolist()
        clean = self.tokenizer.decode(clean_ids, skip_special_tokens=False, clean_up_tokenization_spaces=False)
        if self.tokenizer.encode(clean, add_special_tokens=False) != clean_ids:
            raise ValueError("frozen probe prompt round-trip failed")
        request_ids = self.tokenizer.encode(insert_note(clean, self.note), add_special_tokens=False)
        if len(request_ids) > self.config.data.max_prompt_length:
            raise ValueError("hinted policy prompt exceeds max_prompt_length")
        tokens = self.client.sample_tokens(request_ids, seed=self.seed + self.turn,
                                            temperature=self.config.actor_rollout_ref.rollout.val_kwargs.temperature,
                                            max_tokens=self.config.data.max_response_length)
        if not tokens or len(tokens) > self.config.data.max_response_length:
            raise ValueError("invalid generated response token count")
        self.request_tokens.append({"prompt_ids": request_ids, "response_ids": tokens})
        self.turn += 1
        responses = torch.full((1, self.config.data.max_response_length), self.tokenizer.pad_token_id, dtype=prompts.dtype)
        responses[0, :len(tokens)] = torch.tensor(tokens, dtype=prompts.dtype)
        response_mask = torch.zeros_like(responses)
        response_mask[0, :len(tokens)] = 1
        attention = torch.cat([mask, response_mask], dim=-1)
        positions = attention.cumsum(-1) - 1
        positions.masked_fill_(attention == 0, 0)
        return DataProto.from_dict(tensors={"prompts": prompts.clone(), "responses": responses,
                                            "input_ids": torch.cat([prompts, responses], dim=-1),
                                            "attention_mask": attention, "position_ids": positions})


def probe_input(game, tokenizer):
    raw_prompt = np.empty(1, dtype=object)
    raw_prompt[0] = [{"role": "user", "content": ""}]
    return DataProto.from_dict(tensors={"input_ids": torch.ones((1, 1), dtype=torch.long)},
        non_tensors={"data_source": np.array(["text"], dtype=object), "raw_prompt": raw_prompt,
                     "env_kwargs": np.array([{"gamefile": str(data_root() / game), "strict_gamefile": True}], dtype=object)},
        meta_info={"validate": True, "eos_token_id": tokenizer.eos_token_id, "pad_token_id": tokenizer.pad_token_id})


def reference_scores(record, trace, note, client, tokenizer, config):
    from agent_system.environments.env_manager import AlfWorldEnvironmentManager
    from hintladder.scoring import three_view_scores
    from hintladder.teacher_prompt import ANCHOR, insert_note
    if not trace["walkthrough_verified"] or [t["action"] for t in trace["turns"]] != record["walkthrough_actions"]:
        raise ValueError("reference trace is not the verified game walkthrough")
    renderer = AlfWorldEnvironmentManager(None, None, config)
    renderer.memory.reset(batch_size=1)
    renderer.tasks = [record["goal_text"]]
    result = []
    for turn in trace["turns"]:
        text = renderer.build_text_obs([turn["observation"]], [turn["admissible_commands"]], init=not result)[0]
        hint_only = insert_note(ANCHOR + ".\nChoose one action. Reply only with <action>command</action>.\n", note)
        views = {"clean": text, "hinted": insert_note(text, note), "hint_only": hint_only}
        prompts = {name: tokenizer.apply_chat_template([{"role": "user", "content": view}], tokenize=True,
                                                        add_generation_prompt=True, enable_thinking=False)
                   for name, view in views.items()}
        if any(len(ids) > config.data.max_prompt_length for ids in prompts.values()):
            raise ValueError("teacher-forced reference prompt exceeds max_prompt_length")
        target = tokenizer.encode(f"<action>{turn['action']}</action>", add_special_tokens=False)
        if any(token in tokenizer.all_special_ids for token in target):
            raise ValueError("reference action unexpectedly contains special tokens")
        result.append({"step": turn["step"], **three_view_scores(client, prompts, target)})
        renderer.memory.store({"text_obs": [turn["observation"]], "action": [turn["action"]]})
    return result


def run_frozen_probe(config, stage):
    from functools import partial
    from statistics import mean
    from transformers import AutoTokenizer
    from agent_system.multi_turn_rollout import TrajectoryCollector
    from agent_system.environments.env_manager import AlfWorldEnvironmentManager
    from agent_system.environments.env_package.alfworld import build_alfworld_envs, alfworld_projection
    from hintladder.api import ModelClient
    from hintladder.behavior import episode_metrics
    from hintladder.io import write_jsonl
    from hintladder.ladder import audit_leak

    mode = config.algorithm.hint_ladder.mode
    if mode not in ("e1", "probe"):
        raise ValueError(f"unknown frozen probe mode: {mode}")
    tokenizer = AutoTokenizer.from_pretrained(config.actor_rollout_ref.model.path)
    client = ModelClient(stage["stage.policy"])
    client.verify_model(str(config.actor_rollout_ref.model.path))
    records, references = {}, {}
    for path in stage["stage.privilege_banks"]:
        for row in read_jsonl(path):
            game = normalize_gamefile(row["gamefile"])
            if game in records:
                raise ValueError(f"duplicate privilege game {game}")
            records[game] = row
    if mode == "e1":
        for path in stage["stage.reference_banks"]:
            for row in read_jsonl(path):
                game = normalize_gamefile(row["gamefile"])
                if game in references:
                    raise ValueError("duplicate walkthrough reference")
                references[game] = row
    # This service process and Ray worker processes are sequentially owned by
    # the CLI. Disable dashboard to keep this local Ray instance independent.
    if not ray.is_initialized():
        options = OmegaConf.to_container(config.get("ray_init", {}), resolve=True)
        options.update(include_dashboard=False, num_cpus=int(stage.get("stage.env_cpus", 4)))
        options.setdefault("object_store_memory", 1073741824)
        ray.init(**options)
    alf_config = Path(__file__).resolve().parents[3] / "agent_system/environments/env_package/alfworld/configs/config_tw.yaml"
    raw_env = build_alfworld_envs(str(alf_config), config.env.seed, 1, 1, {"num_cpus": 0.1},
                                  is_train=False, env_kwargs={"eval_dataset": "eval_in_distribution"})
    envs = AlfWorldEnvironmentManager(raw_env, partial(alfworld_projection, require_think_tags=False), config)
    collector = TrajectoryCollector(config, tokenizer)
    output = Path(stage["stage.output_dir"])
    k = int(stage["stage.k"])
    if k <= 0:
        raise ValueError("probe k must be positive")
    rows, rollout_rows, score_rows = [], [], []
    try:
        for game in read_game_list(stage["stage.games"]):
            record = records[game]
            for level in stage["stage.levels"]:
                note = HintProvider(config.algorithm.hint_ladder.bank_dir, level=level).get(game)
                episodes = []
                for replica in range(k):
                    seed = int(config.env.seed) + replica
                    worker = FrozenAPIWorker(client, tokenizer, config, note, seed)
                    initial = probe_input(game, tokenizer)
                    batch = collector.multi_turn_loop(initial, worker, envs, is_train=False)
                    turns = []
                    for index in range(len(batch)):
                        actual = normalize_gamefile(batch.non_tensor_batch["gamefile"][index])
                        if actual != game:
                            raise ValueError(f"probe reset to a different game: {actual}")
                        turn = {"gamefile": game, "level": level, "seed": seed,
                                "step": int(batch.non_tensor_batch["turn_step"][index]),
                                "input": tokenizer.decode(batch.batch["prompts"][index], skip_special_tokens=True),
                                "output": tokenizer.decode(batch.batch["responses"][index], skip_special_tokens=True),
                                "executed_action": str(batch.non_tensor_batch["executed_action"][index]),
                                "is_action_valid": bool(batch.non_tensor_batch["is_action_valid"][index]),
                                "admissible_commands": list(batch.non_tensor_batch["vmpr_admissible_actions"][index]),
                                "next_observation": str(batch.non_tensor_batch["vmpr_next_observation"][index]),
                                **worker.request_tokens[index]}
                        turns.append(turn)
                    won = float(batch.non_tensor_batch["episode_rewards"][0]) > 0
                    episodes.append(episode_metrics(turns, record["hidden_facts"], won))
                    rollout_rows.extend(turns)
                row = {"gamefile": game, "level": level, "seed": int(config.env.seed), "episodes": episodes,
                       "fact_leaks": audit_leak(note, record["hidden_facts"])}
                if mode == "e1":
                    scores = reference_scores(record, references[game], note, client, tokenizer, config)
                    score_rows.extend({"gamefile": game, "level": level, **score} for score in scores)
                    row.update({key: mean(score[key] for score in scores) for key in ("hint_ladder/lift", "hint_ladder/copy")})
                rows.append(row)
                # Flush complete natural-key rows after each arm/game so an API
                # failure leaves useful, explicitly partial evidence on disk.
                write_jsonl(output / "rows.jsonl", rows)
                write_jsonl(output / "rollouts.jsonl", rollout_rows)
                if mode == "e1":
                    write_jsonl(output / "reference_scores.jsonl", score_rows)
    finally:
        raw_env.close()
        ray.shutdown()
