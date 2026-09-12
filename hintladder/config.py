from pathlib import Path
import json
import yaml

from .hint_bank import HintProvider
from .io import ROOT
from .keys import read_game_list


def load_config(path):
    path = Path(path).resolve()
    own = yaml.safe_load(path.read_text())
    if not isinstance(own, dict):
        raise ValueError("config must be a YAML mapping")
    parents = own.pop("extends", [])
    if not isinstance(parents, list):
        raise ValueError("extends must be a list")
    merged, inputs = {}, []
    for parent in parents:
        parent_path = (path.parent / parent).resolve()
        value = yaml.safe_load(parent_path.read_text())
        if not isinstance(value, dict) or "extends" in value:
            raise ValueError("extends may not be nested")
        merged.update(value)
        inputs.append(str(parent_path))
    merged.update(own)
    return merged, inputs


def hydra_overrides(flat):
    # ++ is Hydra's explicit add-or-override operator. It handles actor SDL
    # fields absent from the upstream YAML without copying algorithm configs.
    result = []
    for key, value in flat.items():
        if key in ("extends",) or key.startswith("stage."):
            continue
        if not isinstance(key, str) or key.startswith("+") or "=" in key:
            raise ValueError(f"invalid flat Hydra key: {key}")
        result.append("++" + key + "=" + json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return result


def validate_student_config(flat, *, coverage=False):
    a = "actor_rollout_ref.actor."
    h = "algorithm.hint_ladder."
    if flat.get("algorithm.adv_estimator") != "grpo" or flat.get("reward_model.enable", False):
        raise ValueError("Hint Ladder supports native GRPO advantages and episode rewards only")
    if flat.get("reward_model.launch_reward_fn_async", False) or flat.get("algorithm.use_pf_ppo", False):
        raise ValueError("asynchronous rewards and PF-PPO are outside this experiment")
    if flat.get("actor_rollout_ref.rollout.n") != 1:
        raise ValueError("native agent rollout requires rollout.n=1; use env.rollout.n for groups")
    if flat.get(a + "ppo_epochs", 1) != 1:
        raise ValueError("active-token accounting requires one PPO epoch")
    scope = flat.get(a + "sdl_loss_token_scope")
    if flat.get(a + "sdl_loss_mask_special_tokens") is not True or scope not in ("all", "reasoning_body"):
        raise ValueError("SDL requires special-token masking and scope all or reasoning_body")
    if scope == "reasoning_body" and flat.get("env.alfworld.prompt_style") != "explicit_reasoning":
        raise ValueError("reasoning_body supervision requires the explicit_reasoning prompt")
    if flat.get(a + "sdl_loss_sample_filter", "all") != "all" or flat.get(a + "sdl_loss_sample_weighting", False):
        raise ValueError("SDL filtering/weighting would change the declared active-token budget")
    if flat.get(a + "use_candidate_ce_loss", False) or flat.get(a + "use_sdar_loss", False):
        raise ValueError("candidate CE and SDAR are outside the declared objective")
    if flat.get(a + "sdl_loss_normalization") != "response_token_mean":
        raise ValueError("SDL normalization must be response_token_mean")
    if flat.get("env.alfworld.prompt_style") not in ("action_tag_only", "explicit_reasoning") or flat.get("env.alfworld.require_think_tags") is not False or flat.get("data.apply_chat_template_kwargs.enable_thinking") is not False:
        raise ValueError("explicit action/reasoning prompt and disabled native thinking are required")
    online = flat.get(h + "online.enable", False)
    if online and (flat.get(h + 'level') != 'L1' or flat.get('env.alfworld.prompt_style') != 'explicit_reasoning' or flat.get('env.history_length') != 2):
        raise ValueError("Online public-only L1 requires the matched reasoning prompt and history length 2")
    if online:
        # One slow request must not stall a step: the median hint takes ~4 s.
        bounds = {"concurrency": (1, 512), "timeout": (1, 60), "retries": (1, 6), "max_tokens": (64, 1024),
                  "failure_budget_ratio": (0.0, 0.05), "failure_budget_max": (0, 100)}
        for name, (low, high) in bounds.items():
            value = flat.get(h + "online." + name)
            if value is not None and not low <= float(value) <= high:
                raise ValueError(f"{h}online.{name}={value} is outside [{low}, {high}]")
    level, mapping = flat.get(h + "level"), flat.get(h + "level_map_path")
    if (level is None) == (mapping is None):
        raise ValueError("exactly one hint level selector is required")
    sdl = flat.get(a + "use_sdl_loss", False)
    pg = float(flat.get(a + "pg_loss_coef", 0))
    val_only = flat.get("trainer.val_only", False)
    if level == "L0" and sdl:
        raise ValueError("L0 must disable SDL")
    if not val_only and not sdl and pg == 0:
        raise ValueError("empty training: pg_loss_coef=0 and SDL disabled")
    if float(flat.get(a + "entropy_coeff", 0)) != 0:
        raise ValueError("entropy_coeff must be zero for the declared PG + SDL objective")
    if flat.get(a + "use_kl_loss", False) or flat.get("algorithm.use_kl_in_reward", False):
        raise ValueError("the first-phase objective does not include an extra KL loss")
    if flat.get(a + "sdl_loss_mode") == "topk_forward_kl":
        if flat.get(a + "use_fused_kernels") is not False or flat.get("actor_rollout_ref.model.use_fused_kernels") is not False:
            raise ValueError("top-k SDL requires both actor and model fused kernels disabled")
        if flat.get(a + "strategy") != "fsdp":
            raise ValueError("first-phase top-k SDL requires FSDP")
    if flat.get(a + "sdl_loss_mode") not in ("topk_forward_kl", "chosen_token_k3"):
        raise ValueError("unsupported SDL mode")
    if flat.get("algorithm.path_opd.enable", False) or flat.get("algorithm.vmpr.enable", False):
        raise ValueError("path routing and prefix buffers must remain disabled")
    if coverage and not online:
        provider = HintProvider(flat[h + "bank_dir"], level=level, level_map_path=mapping)
        provider.validate_coverage(read_game_list(flat["stage.train_games"]), training=not val_only)
    return flat


def output_dir(flat, default):
    return ROOT / flat.get("stage.output_dir", "runs/" + default)
