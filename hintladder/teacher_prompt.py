from copy import deepcopy
import re

ANCHOR = "You are an expert agent operating in the ALFRED Embodied Environment"
OPEN = "<private_teacher_note>"
CLOSE = "</private_teacher_note>"
ADVISORY = "This note is advisory. Decide from the current observation and admissible actions, and never mention the note.\n"


def insert_note(prompt_text: str, note: str) -> str:
    if OPEN in prompt_text or CLOSE in prompt_text:
        raise ValueError("Student prompt already contains a private note")
    if OPEN in note or CLOSE in note:
        raise ValueError("nested private-note tags in hint")
    # Decoded chat templates may put role tokens and a blank line before the
    # first user-content line. Match the ALFWorld header, never a chat token.
    anchors = list(re.finditer(r"(?m)^" + re.escape(ANCHOR) + r"[^\n]*\n", prompt_text))
    if len(anchors) != 1:
        raise ValueError("expected exactly one ALFWorld first-line anchor")
    if not note.strip():
        return prompt_text
    index = anchors[0].end()
    result = prompt_text[:index] + OPEN + "\n" + note + "\n" + CLOSE + "\n" + ADVISORY + prompt_text[index:]
    if remove_note(result) != prompt_text:
        raise AssertionError("private-note insertion changed the Student text")
    return result


def remove_note(prompt_text: str) -> str:
    if prompt_text.count(OPEN) != 1 or prompt_text.count(CLOSE) != 1:
        raise ValueError("expected one private note")
    start = prompt_text.index(OPEN)
    end = prompt_text.index(CLOSE, start) + len(CLOSE)
    suffix = "\n" + ADVISORY
    if prompt_text[end:end + len(suffix)] != suffix:
        raise ValueError("private note advisory was changed")
    return prompt_text[:start] + prompt_text[end + len(suffix):]


def build_teacher_batch(batch, provider, tokenizer, max_prompt_length):
    """Use the caller's native DataProto without importing the framework here."""
    import torch

    if batch.meta_info.get("validate", False):
        raise ValueError("private hints must never be used by Student validation")
    responses = batch.batch["responses"]
    prompts = batch.batch["prompts"]
    mask = batch.batch["attention_mask"]
    if mask.shape != (len(responses), prompts.shape[1] + responses.shape[1]):
        raise ValueError("Student attention mask does not align with prompt and response")
    games = batch.non_tensor_batch["gamefile"]
    if len(games) != len(responses):
        raise ValueError("gamefile count does not match batch size")
    pad_id = tokenizer.pad_token_id
    if pad_id is None:
        raise ValueError("tokenizer must define pad_token_id")
    teacher_prompts = torch.full((len(responses), max_prompt_length), pad_id,
                                dtype=prompts.dtype, device=prompts.device)
    teacher_mask = torch.zeros_like(teacher_prompts, dtype=mask.dtype)
    counts = {}
    for i, game in enumerate(games):
        ids = prompts[i][mask[i, :prompts.shape[1]].bool()].tolist()
        text = tokenizer.decode(ids, skip_special_tokens=False, clean_up_tokenization_spaces=False)
        if tokenizer.encode(text, add_special_tokens=False) != ids:
            raise ValueError("Student prompt decode/encode token alignment failed")
        level = provider.level_for(game)
        encoded = tokenizer.encode(insert_note(text, provider.get(game)), add_special_tokens=False)
        if len(encoded) > max_prompt_length:
            raise ValueError(f"Teacher prompt for {game} exceeds max_prompt_length ({len(encoded)} > {max_prompt_length})")
        if not encoded:
            raise ValueError("empty teacher prompt")
        teacher_prompts[i, -len(encoded):] = torch.tensor(encoded, dtype=prompts.dtype, device=prompts.device)
        teacher_mask[i, -len(encoded):] = 1
        counts[level] = counts.get(level, 0) + 1
    attention = torch.cat([teacher_mask, mask[:, prompts.shape[1]:]], dim=-1)
    inputs = torch.cat([teacher_prompts, responses.clone()], dim=-1)
    if not torch.equal(inputs[:, max_prompt_length:], responses):
        raise AssertionError("teacher response IDs differ from Student response IDs")
    position = attention.long().cumsum(-1) - 1
    position.masked_fill_(attention == 0, 0)
    meta = deepcopy(batch.meta_info)
    meta["hint_ladder_level_counts"] = counts
    return type(batch).from_dict(tensors={
        "prompts": teacher_prompts, "input_ids": inputs, "responses": responses.clone(),
        "attention_mask": attention, "position_ids": position,
    }, non_tensors=deepcopy(batch.non_tensor_batch), meta_info=meta)
