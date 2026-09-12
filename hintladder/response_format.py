"""Exclude malformed responses from SDL without changing executed episodes."""
import json
import re
from pathlib import Path

import numpy as np


def response_format_error(text, prompt_style):
    lower = text.lower()
    if '<think>' in lower or '</think>' in lower:
        return 'forbidden_think_tag'
    if prompt_style == 'explicit_reasoning':
        match = re.fullmatch(r'\s*<reasoning>(.*?)</reasoning>\s*<action>([^<>]+)</action>\s*',
                             text, flags=re.S | re.I)
        tags = ('<reasoning>', '</reasoning>', '<action>', '</action>')
        if not match or any(lower.count(tag) != 1 for tag in tags):
            return 'invalid_reasoning_action_format'
        if not match[1].strip():
            return 'empty_reasoning'
        if not match[2].strip():
            return 'empty_action'
    elif prompt_style == 'action_tag_only':
        match = re.fullmatch(r'\s*<action>([^<>]+)</action>\s*', text, flags=re.S | re.I)
        if not match or not match[1].strip():
            return 'invalid_action_format'
    else:
        raise ValueError(f'Unsupported prompt style: {prompt_style}')
    return ''


def reasoning_body_mask(responses, response_mask, tokenizer):
    """Select original response tokens wholly inside the reasoning body.

    Tags are ordinary BPE tokens, and a token can straddle a body/tag boundary.
    Locate both boundaries by decoding prefixes of the ORIGINAL sampled IDs;
    re-encoding the text could change their segmentation. Exclude straddling
    tokens, both reasoning tags, the complete action block and special tokens.
    Malformed/truncated responses retain the existing zero-supervision policy.
    """
    import torch

    keep = torch.zeros_like(response_mask, dtype=torch.bool)
    specials = set(tokenizer.all_special_ids)
    for row, (tokens, active) in enumerate(zip(responses.tolist(), response_mask.tolist())):
        positions = [i for i, value in enumerate(active) if value]
        ids = [tokens[i] for i in positions]
        clean = tokenizer.decode(ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)
        if response_format_error(clean, 'explicit_reasoning'):
            continue
        text = tokenizer.decode(ids, skip_special_tokens=False, clean_up_tokenization_spaces=False)
        opening = re.search(r'<reasoning>', text, re.I)
        closing = re.search(r'</reasoning>', text, re.I)
        if opening is None or closing is None:
            continue
        decoded = {len(ids): text, 0: ''}

        def prefix(count):
            if count not in decoded:
                decoded[count] = tokenizer.decode(ids[:count], skip_special_tokens=False,
                                                   clean_up_tokenization_spaces=False)
            return decoded[count]

        def covering_prefix(char_end):
            target = text[:char_end]
            low, high = 0, len(ids)
            while low < high:
                middle = (low + high) // 2
                if prefix(middle).startswith(target):
                    high = middle
                else:
                    low = middle + 1
            return low

        start = covering_prefix(opening.end())
        end = covering_prefix(closing.start())
        if prefix(end) != text[:closing.start()]:
            end -= 1
        for index in range(start, end):
            if ids[index] not in specials:
                keep[row, positions[index]] = True
    return keep


def annotate_response_format(batch, tokenizer, prompt_style, output_dir, step):
    """Annotate original rows before padding/reordering; save every bad response."""
    texts = tokenizer.batch_decode(batch.batch['responses'], skip_special_tokens=True)
    reasons = [response_format_error(text, prompt_style) for text in texts]
    batch.non_tensor_batch['sdl_format_valid'] = np.array([not reason for reason in reasons], dtype=bool)
    batch.non_tensor_batch['sdl_format_error'] = np.array(reasons, dtype=object)
    bad = [i for i, reason in enumerate(reasons) if reason]
    if bad:
        directory = Path(output_dir) / 'format_errors'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f'step_{step:06d}.jsonl'
        with path.open('w') as stream:
            for i in bad:
                row = {'step': step, 'rollout_row': i, 'reason': reasons[i], 'output': texts[i]}
                for key in ('gamefile', 'traj_uid', 'turn_step', 'executed_action', 'is_action_valid'):
                    if key in batch.non_tensor_batch:
                        value = batch.non_tensor_batch[key][i]
                        row[key] = value.item() if isinstance(value, np.generic) else value
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        print(f'[format] step={step} excluded {len(bad)}/{len(texts)} response rows from SDL; {path}', flush=True)
    return {'hint_ladder/format_invalid_rows': len(bad),
            'hint_ladder/format_total_rows': len(texts),
            'hint_ladder/format_invalid_ratio': len(bad) / max(1, len(texts))}
