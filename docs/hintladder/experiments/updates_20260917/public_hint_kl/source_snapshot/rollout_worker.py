"""Independent Base / Base+L1 / Base+L2 / Base+L3 free-running trajectories."""
import argparse
import json
import re
import subprocess
import sys
import time
import traceback
from common import ROOT, make_prompt, write_json


def rpc(proc, op, items=()):
    proc.stdin.write(json.dumps(dict(op=op, items=list(items)))+'\n')
    proc.stdin.flush()
    if op == 'close':
        return
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError('Native environment process exited')
        if line.startswith('@@ENV@@'):
            data = json.loads(line[7:])
            if not data['ok']:
                raise RuntimeError(data['error'])
            return data['results']


def main(worker):
    from transformers import AutoTokenizer
    from vllm import LLM, SamplingParams
    from agent_system.environments.env_package.alfworld.projection import alfworld_projection
    from hintladder.response_format import response_format_error, reasoning_body_mask
    from hintladder.teacher_prompt import insert_note, remove_note
    from hint_provider import HintProvider
    import torch

    selected = json.loads((ROOT/'selection.json').read_text())
    arms = ['base', 'base_l1', 'base_l2', 'base_l3']
    jobs = [dict(item, arm=arm, episode_id=f'{arm}:{item["sample_id"]}')
            for item in selected for arm in arms]
    jobs = [job for index, job in enumerate(jobs) if index % 8 == worker]
    out = ROOT/'rollouts'/f'worker_{worker}'
    out.mkdir(parents=True, exist_ok=True)
    if (out/'complete.json').exists():
        return
    episodes = {}
    started = time.monotonic()
    provider = HintProvider(out)
    proc = subprocess.Popen([sys.executable, '-u', str(ROOT/'env_worker.py')],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def snapshot(phase):
        temp = out/'episodes.jsonl.tmp'
        temp.write_text(''.join(json.dumps(e, ensure_ascii=False)+'\n' for e in episodes.values()))
        temp.replace(out/'episodes.jsonl')
        write_json(out/'progress.json', dict(worker=worker, phase=phase,
            seconds=time.monotonic()-started, total=len(episodes),
            completed=sum(e['complete'] for e in episodes.values()),
            turns=sum(len(e['turns']) for e in episodes.values()),
            successes=sum(e['success'] for e in episodes.values())))

    try:
        states = {s['sample_id']: s for s in rpc(proc, 'reset',
            [dict(sample_id=j['episode_id'], gamefile=j['gamefile']) for j in jobs])}
        for item in jobs:
            state = states[item['episode_id']]
            episodes[item['episode_id']] = dict(item, model_path='/models/base', checkpoint_step=0,
                task=state['observation'].split('Your task is to: ', 1)[1].strip(),
                hint_in_generation=item['arm'] != 'base', free_running=True,
                initial_state=state, turns=[], success=state['won'], complete=False)
        tok = AutoTokenizer.from_pretrained('/models/base', local_files_only=True)
        snapshot('loading_model')
        llm = LLM(model='/models/base', tokenizer='/models/base', dtype='bfloat16',
            tensor_parallel_size=1, gpu_memory_utilization=0.35, max_model_len=8192,
            max_num_seqs=16, enforce_eager=True, enable_prefix_caching=True,
            generation_config='vllm', seed=42, disable_log_stats=True)
        with (out/'turns.jsonl').open('w', buffering=1) as trace:
            for turn_index in range(50):
                active = [key for key, e in episodes.items() if not e['complete']]
                if not active:
                    break
                records = []
                for key in active:
                    episode, state = episodes[key], states[key]
                    public = make_prompt(episode, state)
                    rendered = tok.apply_chat_template([dict(role='user', content=public)],
                        tokenize=False, add_generation_prompt=True, enable_thinking=False)
                    recent = episode['turns'][-2:]
                    public_state = dict(task=episode['task'], step_count=turn_index,
                        current_step=turn_index+1, current_observation=state['observation'],
                        action_history=[dict(turn=t['turn'], observation=t['observation'],
                            action=t['executed_action']) for t in recent],
                        action_space=list(state['admissible_commands']))
                    for t in recent:
                        assert f"[Observation {t['turn']}: '{t['observation']}', Action {t['turn']}: '{t['executed_action']}']" in public
                    assert state['observation'] in public
                    records.append(dict(row_id=f'{key}:{turn_index+1}', episode_id=key,
                        sample_id=episode['sample_id'], arm=episode['arm'], split=episode['split'],
                        task=episode['task'], turn=turn_index+1, observation=state['observation'],
                        admissible_commands=state['admissible_commands'],
                        recent_history=public_state['action_history'], public_user_prompt=public,
                        public_rendered_prompt=rendered,
                        public_prompt_token_ids=tok.encode(rendered, add_special_tokens=False),
                        hint_public_input=public_state if episode['arm'] != 'base' else None,
                        generation_seed=42+episode['sample_id']*1000+turn_index))
                snapshot('glm_public_state_hint')
                notes = provider.batch(records)
                inputs, sampling = [], []
                for record in records:
                    note = notes.get(record['row_id'])
                    hint = note['hint'] if note else ''
                    rendered = insert_note(record['public_rendered_prompt'], hint)
                    user_prompt = insert_note(record['public_user_prompt'], hint)
                    if hint:
                        assert remove_note(rendered) == record['public_rendered_prompt']
                    assert tok.apply_chat_template([dict(role='user', content=user_prompt)],
                        tokenize=False, add_generation_prompt=True, enable_thinking=False) == rendered
                    ids = tok.encode(rendered, add_special_tokens=False)
                    assert len(ids)+1024 <= 8192
                    record.update(hint=hint, hint_level=note['level'] if note else 'L0',
                        hint_metadata=note, oracle_supplied=False, user_prompt=user_prompt,
                        rendered_prompt=rendered, prompt_token_ids=ids)
                    inputs.append(dict(prompt_token_ids=ids))
                    sampling.append(SamplingParams(n=1, temperature=0.6, top_p=0.95, top_k=20,
                        max_tokens=1024, seed=record['generation_seed'], detokenize=False))
                snapshot('generating')
                generated = llm.generate(inputs, sampling, use_tqdm=False)
                for record, result in zip(records, generated, strict=True):
                    completion = result.outputs[0]
                    ids = list(completion.token_ids)
                    output = tok.decode(ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)
                    commands, valid = alfworld_projection([output], [record['admissible_commands']], matched_reasoning=True)
                    match = re.search(r'<reasoning>(.*?)</reasoning>', output, re.S | re.I)
                    error = response_format_error(output, 'explicit_reasoning')
                    ids_tensor = torch.tensor([ids], dtype=torch.long)
                    body_tokens = int(reasoning_body_mask(ids_tensor, torch.ones_like(ids_tensor), tok).sum()) if not error else None
                    record.update(output=output,
                        raw_output=tok.decode(ids, skip_special_tokens=False, clean_up_tokenization_spaces=False),
                        response_token_ids=ids, generated_tokens=len(ids),
                        reasoning=match.group(1).strip() if match else None,
                        reasoning_body_tokens=body_tokens, format_error=error,
                        finish_reason=completion.finish_reason, executed_action=commands[0],
                        action_admissible=bool(valid[0]))
                next_states = rpc(proc, 'step', [dict(sample_id=r['episode_id'], command=r['executed_action']) for r in records])
                for record, state in zip(records, next_states, strict=True):
                    key = record['episode_id']
                    assert state['sample_id'] == key
                    record['next_state'] = state
                    episode = episodes[key]
                    episode['turns'].append(record)
                    episode['success'] = state['won']
                    episode['complete'] = state['won'] or state['done'] or turn_index == 49
                    if episode['complete']:
                        episode['termination'] = 'success' if state['won'] else 'environment_done' if state['done'] else 'max_steps'
                    states[key] = state
                    trace.write(json.dumps(record, ensure_ascii=False)+'\n')
                snapshot('rollout')
                print(json.dumps(dict(worker=worker, turn=turn_index+1,
                    completed=sum(e['complete'] for e in episodes.values()), total=len(episodes))), flush=True)
        assert all(e['complete'] for e in episodes.values())
        snapshot('complete')
        write_json(out/'complete.json', dict(worker=worker, episodes=len(episodes),
            turns=sum(len(e['turns']) for e in episodes.values()), seconds=time.monotonic()-started))
    except Exception:
        write_json(out/'error.json', dict(error=traceback.format_exc()))
        raise
    finally:
        provider.close()
        if proc.poll() is None:
            rpc(proc, 'close')
            proc.wait(timeout=30)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=int, required=True)
    main(parser.parse_args().worker)
