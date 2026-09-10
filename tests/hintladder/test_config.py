from pathlib import Path
import ast
import pytest
from hydra import compose, initialize_config_dir

from hintladder.config import load_config, hydra_overrides, validate_student_config
from hintladder.io import ROOT


def test_arms_and_real_hydra_composition():
    for level in ("L0", "L1", "L2", "L3", "FULLPATH"):
        config, inputs = load_config(ROOT / f"configs/arms/e2_{level}.yaml")
        assert config["actor_rollout_ref.actor.pg_loss_coef"] == 0
        assert config["actor_rollout_ref.actor.use_sdl_loss"] == (level != "L0")
        if level == "L0":
            config["trainer.val_only"] = True
        validate_student_config(config)
        with initialize_config_dir(config_dir=str(ROOT / "verl/trainer/config"), version_base=None):
            result = compose(config_name="ppo_trainer", overrides=hydra_overrides(config))
        assert result.algorithm.hint_ladder.level == level
        assert result.data.apply_chat_template_kwargs.enable_thinking is False
        assert result.actor_rollout_ref.actor.entropy_coeff == 0


def test_reject_nested_extends(tmp_path):
    (tmp_path / "parent.yaml").write_text("extends: []\n")
    (tmp_path / "child.yaml").write_text("extends: [parent.yaml]\n")
    with pytest.raises(ValueError, match="nested"):
        load_config(tmp_path / "child.yaml")


def test_online_full_training_composes_with_persistent_scope():
    config, _ = load_config(ROOT / "configs/experiments/l1_online_full_20260910/train_full.yaml")
    validate_student_config(config)
    with initialize_config_dir(config_dir=str(ROOT / "verl/trainer/config"), version_base=None):
        result = compose(config_name="ppo_trainer", overrides=hydra_overrides(config))
    assert result.actor_rollout_ref.rollout.keep_engine_awake_during_multiturn is True
    assert result.actor_rollout_ref.rollout.tensor_model_parallel_size == 1
    assert result.data.train_batch_size == 16 and result.env.rollout.n == 1
    assert result.trainer.n_gpus_per_node == 8 and result.trainer.val_before_train is False
    assert result.algorithm.hint_ladder.online.concurrency == 64
    assert result.algorithm.hint_ladder.online.model == "glm-5.3-flash"


def test_empty_objective_and_wrong_topk_fail():
    config, _ = load_config(ROOT / "configs/arms/e2_L0.yaml")
    with pytest.raises(ValueError, match="empty training"):
        validate_student_config(config)
    config, _ = load_config(ROOT / "configs/arms/e2_L3.yaml")
    config["actor_rollout_ref.model.use_fused_kernels"] = True
    with pytest.raises(ValueError, match="fused"):
        validate_student_config(config)


def test_framework_boundary_and_no_extra_shell_launchers():
    for path in (ROOT / "hintladder").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(not x.name.startswith("verl") for x in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("verl")
        if path.name != "keys.py":
            assert "os.environ" not in path.read_text()


def test_all_stage_modules_exist():
    from hintladder.cli import STAGES
    import importlib
    for stage in STAGES:
        assert callable(importlib.import_module("hintladder.stages." + stage.replace("-", "_")).run)
