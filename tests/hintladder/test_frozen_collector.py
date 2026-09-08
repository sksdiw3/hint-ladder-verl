from pathlib import Path

import torch
from hydra import compose, initialize_config_dir

from hintladder.config import hydra_overrides, load_config
from hintladder.teacher_prompt import ANCHOR, OPEN


def test_probe_uses_native_preprocessing_and_preserves_generated_ids(tokenizer, monkeypatch, tmp_path):
    from agent_system.multi_turn_rollout import TrajectoryCollector
    from verl.trainer.ppo.hint_ladder_ray_trainer import FrozenAPIWorker, probe_input

    class ChatTokenizer(type(tokenizer)):
        def apply_chat_template(self, messages, **kwargs):
            return "".join(message["content"] for message in messages)

        def __call__(self, text, **kwargs):
            ids = torch.tensor([self.encode(text)])
            return {"input_ids": ids, "attention_mask": torch.ones_like(ids)}

    tokenizer = ChatTokenizer()
    root = Path(__file__).resolve().parents[2]
    flat, _ = load_config(root / "configs/base_alfworld_qwen3_4b.yaml")
    with initialize_config_dir(version_base=None, config_dir=str(root / "verl/trainer/config")):
        cfg = compose(config_name="ppo_trainer", overrides=hydra_overrides(flat))
    monkeypatch.setenv("ALFWORLD_DATA", str(tmp_path))
    initial = probe_input("a/game.tw-pddl", tokenizer)
    prompt = ANCHOR + ".\nYour admissible actions of the current situation are: ['look'].\n"
    prepared = TrajectoryCollector(cfg, tokenizer).preprocess_batch(initial, {"text": [prompt]})
    response_ids = tokenizer.encode("<action>look</action>")

    class Client:
        def sample_tokens(self, prompt_ids, **kwargs):
            assert OPEN in tokenizer.decode(prompt_ids)
            return response_ids

    worker = FrozenAPIWorker(Client(), tokenizer, cfg, "Inspect carefully.", 0)
    result = worker.generate_sequences(prepared)
    assert OPEN not in tokenizer.decode(result.batch["prompts"][0])
    assert result.batch["responses"][0, :len(response_ids)].tolist() == response_ids
    assert worker.request_tokens[0]["response_ids"] == response_ids
    assert result.batch["attention_mask"][0, -cfg.data.max_response_length:].sum() == len(response_ids)
