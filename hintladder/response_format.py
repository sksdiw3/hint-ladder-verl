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
