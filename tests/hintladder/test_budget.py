from types import SimpleNamespace
import pytest
from hintladder.budget import ActiveTokenBudget


def test_budget_counts_and_restores(tmp_path):
    from verl.trainer.ppo.hint_ladder_ray_trainer import save_budget, restore_budget
    from omegaconf import OmegaConf
    budget = ActiveTokenBudget(10)
    budget.add(7)
    trainer = SimpleNamespace(budget=budget, global_steps=1, config=OmegaConf.create({"trainer": {"default_local_dir": str(tmp_path), "resume_from_path": None}}))
    save_budget(trainer)
    trainer.budget = ActiveTokenBudget(10)
    restore_budget(trainer)
    assert trainer.budget.used == 7
    trainer.budget.add(5)
    assert trainer.budget.exhausted and trainer.budget.to_dict()["overshoot"] == 2


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_bad_budget(limit):
    with pytest.raises(ValueError):
        ActiveTokenBudget(limit)


def test_native_numpy_metrics_are_serializable(tmp_path):
    import numpy as np
    from hintladder.io import read_jsonl
    from verl.trainer.ppo.hint_ladder_ray_trainer import log_metrics
    trainer = SimpleNamespace(global_steps=0, config=SimpleNamespace(trainer=SimpleNamespace(default_local_dir=str(tmp_path))))
    calls = []
    logger = SimpleNamespace(log=lambda **kwargs: calls.append(kwargs))
    log_metrics(trainer, logger, {"val/success_rate": np.float32(.5), "count": np.int64(2)})
    assert read_jsonl(tmp_path / "metrics.jsonl") == [{"step": 0, "val/success_rate": .5, "count": 2}]
    assert calls == [{"data": {"val/success_rate": .5, "count": 2}, "step": 0, "commit": True}]
