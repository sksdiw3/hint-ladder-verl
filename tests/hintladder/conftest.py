from pathlib import Path
import sys

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verl import DataProto
from hintladder.teacher_prompt import ANCHOR
from hintladder.hint_bank import write_bank, HintProvider


class CharacterTokenizer:
    pad_token_id = 0
    eos_token_id = 1
    all_special_ids = [0, 1]

    def encode(self, text, **kwargs):
        return [ord(char) + 2 for char in text]

    def decode(self, ids, **kwargs):
        return "".join(chr(int(token) - 2) for token in ids if int(token) > 1)

    def batch_decode(self, rows, **kwargs):
        return [self.decode(row, **kwargs) for row in rows]


@pytest.fixture
def tokenizer():
    return CharacterTokenizer()


@pytest.fixture
def student(tokenizer):
    prompt = tokenizer.encode(ANCHOR + ".\nObservation remains exactly here.\n")
    prompts = torch.tensor([[0, 0] + prompt, [0] + prompt + [ord(' ') + 2]])
    responses = torch.tensor([[19, 23, 1, 0], [29, 31, 37, 1]])
    mask = torch.cat([prompts.ne(0).long(), responses.ne(0).long()], dim=-1)
    return DataProto.from_dict(tensors={"prompts": prompts, "responses": responses,
        "input_ids": torch.cat([prompts, responses], -1), "attention_mask": mask,
        "position_ids": (mask.cumsum(-1) - 1).clamp(min=0), "response_mask": responses.ne(0).long()},
        non_tensors={"gamefile": np.array(["json_2.1.1/train/a/game.tw-pddl"] * 2, dtype=object)})


@pytest.fixture
def provider(tmp_path):
    write_bank(tmp_path / "L2.jsonl", [{"gamefile": "json_2.1.1/train/a/game.tw-pddl", "level": "L2",
        "hint": "Inspect the room carefully.", "word_count": 4, "validation": {"ok": True, "errors": []}}])
    return HintProvider(tmp_path, level="L2")


@pytest.fixture
def facts():
    return {"goal_object": "mug 2", "goal_object_location": "countertop 1", "destination_receptacle": "cabinet 1",
            "goal_object_initial_states": {"hot": False, "clean": True}}
