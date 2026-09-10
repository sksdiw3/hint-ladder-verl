"""Ten prompted-thinking Qwen3-4B rollouts; native thinking disabled, no hint."""
import argparse
import os
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import traceback

ROOT = Path(os.environ.get('AUDIT_OUTPUT_DIR', '/audit'))


def write_json(path, obj):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
    temp.replace(path)


def rpc(worker, request):
    worker.stdin.write(json.dumps(request) + '\n')
    worker.stdin.flush()
    while True:
        line = worker.stdout.readline()
        if not line:
            raise RuntimeError('Environment worker exited before replying')
        if line.startswith('@@ALFWORLD@@'):
            response = json.loads(line[len('@@ALFWORLD@@'):])
            if not response['ok']:
                raise RuntimeError(response['error'])
            return response['results']
        print('ENV_STDOUT', line.rstrip(), flush=True)


def make_prompt(episode, state, config):
    history = episode['turns'][-config['history_length']:]
    action_history = '\n'.join(
        f"[Observation {turn['turn_step'] + 1}: '{turn['observation']}', Action {turn['turn_step'] + 1}: '{turn['executed_action']}']"
        for turn in history)
    template = (ROOT / config['prompt_template_file']).read_text()
    prompt = template.format(task_description=episode['task'],
        step_count=len(episode['turns']), history_length=len(history),
        action_history=action_history, current_step=len(episode['turns'])+1,
        current_observation=state['observation'],
        admissible_actions='\n '.join(f"'{action}'" for action in state['admissible_commands']))
    assert config['reasoning_instruction'] in prompt
    assert config['enable_thinking'] is False
    return prompt


def parse_response(response, admissible):
    # Never execute an action merely mentioned inside native thinking.
    if '</think>' in response:
        reasoning_part, answer = response.rsplit('</think>', 1)
        reasoning = reasoning_part.split('<think>', 1)[-1].strip()
        complete_think = '<think>' in reasoning_part
    elif '<think>' in response:
        reasoning, answer, complete_think = response.split('<think>', 1)[1], '', False
    else:
        reasoning, answer, complete_think = '', response, False
    actions = re.findall(r'<action>\s*(.*?)\s*</action>', answer, flags=re.S | re.I)
    action = actions[0].strip() if len(actions) == 1 else None
    error = None if action is not None else 'missing_or_multiple_final_action_blocks'
    # Invalid generations consume one interaction and are recorded. No substitute
    # useful action (e.g. look) is silently selected for the model.
    command = action if action is not None else 'invalid_action'
    return dict(reasoning=reasoning, final_answer=answer.strip(),
                complete_think_block=complete_think, parsed_action=action,
                action_parse_error=error, executed_action=command,
                action_in_admissible_pool=action in admissible if action is not None else False,
                invalid_command_placeholder=action is None)


def snapshot(episodes, config, started, phase):
    write_json(ROOT / 'progress.json', dict(phase=phase,
        updated_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=time.time()-started,
        completed=sum(e['completed'] for e in episodes.values()),
        successes=sum(e['success'] for e in episodes.values()),
        total_turns=sum(len(e['turns']) for e in episodes.values()),
        episodes=[dict(episode_id=e['episode_id'], task=e['task'],
                       turns=len(e['turns']), success=e['success'],
                       completed=e['completed'], termination=e['termination'])
                  for e in episodes.values()]))
    with (ROOT / 'episodes.jsonl').open('w') as f:
        for episode in episodes.values():
            f.write(json.dumps(episode, ensure_ascii=False) + '\n')


def main(preflight=False):
    from transformers import AutoTokenizer
    import transformers
    config = json.loads((ROOT / 'config.json').read_text())
    selection = json.loads((ROOT / 'selection.json').read_text())
    tokenizer = AutoTokenizer.from_pretrained(config['model'], local_files_only=True)
    (ROOT / 'chat_template.jinja').write_text(tokenizer.chat_template)
    started = time.time()
    worker = subprocess.Popen(['/opt/hintladder/bin/python', '-u', '/audit/env_worker.py'],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    episodes = {}
    try:
        states = {r['episode_id']: r for r in rpc(worker, dict(op='reset', episodes=selection['episodes']))}
        for item in selection['episodes']:
            state = states[item['episode_id']]
            task = state['observation'].split('Your task is to: ', 1)[1].strip()
            episodes[item['episode_id']] = dict(schema='alfworld_fullprompt_reasoning_episode_v1',
                **item, model='Qwen3-4B base', checkpoint_step=0, hint=None,
                enable_thinking=config['enable_thinking'], explicit_reasoning_instruction=config['explicit_reasoning_instruction'],
                task=task, initial_observation=state['observation'],
                initial_admissible_commands=state['admissible_commands'],
                turns=[], completed=False, success=state['won'], termination=None,
                final_environment_state=state)
        initial_prompts = []
        for episode_id, episode in episodes.items():
            prompt = make_prompt(episode, states[episode_id], config)
            rendered = tokenizer.apply_chat_template([dict(role='user', content=prompt)],
                        add_generation_prompt=True, tokenize=False, enable_thinking=config['enable_thinking'])
            assert rendered.endswith('<|im_start|>assistant\n<think>\n\n</think>\n\n')
            initial_prompts.append(dict(episode_id=episode_id, task=episode['task'],
                                       user_prompt=prompt, rendered_prompt=rendered))
        baseline = {e['episode_id']: e for e in map(json.loads, Path('/baseline/episodes.jsonl').read_text().splitlines())}
        for i, episode in episodes.items():
            assert episode['gamefile'] == baseline[i]['gamefile']
            assert episode['initial_observation'] == baseline[i]['initial_observation']
            assert episode['initial_admissible_commands'] == baseline[i]['initial_admissible_commands']
            new_prompt = next(p['user_prompt'] for p in initial_prompts if p['episode_id'] == i)
            assert new_prompt.startswith('You are an expert agent operating in the ALFRED Embodied Environment.')
            assert 'already taken 0 step(s)' in new_prompt
            assert 'most recent 0 observations' in new_prompt
            assert 'You are now at step 1' in new_prompt
            assert new_prompt == baseline[i]['turns'][0]['user_prompt'].replace('<think>', '<reasoning>').replace('</think>', '</reasoning>')
        write_json(ROOT / 'initial_prompts.json', initial_prompts)
        if preflight:
            # Exercise the CPU environment boundary with genuine admissible actions.
            answers = rpc(worker, dict(op='step', actions=[dict(episode_id=i, command='look') for i in states]))
            assert len(answers) == len(selection['episodes']) and all(a['observation'] for a in answers)
            assert parse_response('<think>Maybe <action>look</action>.</think><action>go to desk 1</action>', ['look', 'go to desk 1'])['executed_action'] == 'go to desk 1'
            assert parse_response('<think>unfinished <action>look</action>', ['look'])['parsed_action'] is None
            assert parse_response('</think>Analysis here. <action>look</action>', ['look'])['executed_action'] == 'look'
            write_json(ROOT / 'preflight.json', dict(passed=True, native_resets=10,
                native_steps=10, explicit_reasoning_tag_instruction=True,
                native_thinking_disabled=True, empty_think_prefill=True, matched_initial_states=True, reasoning_action_extraction_checks=True))
            print('PREFLIGHT_PASS: 10 native resets/steps; explicit reasoning-tag prompt; disabled native template; matched initial states; parser boundaries', flush=True)
            return
        snapshot(episodes, config, started, 'loading_model')
        import torch
        import vllm
        from vllm import LLM, SamplingParams
        write_json(ROOT / 'runtime.json', dict(torch=torch.__version__, transformers=transformers.__version__,
                    vllm=vllm.__version__, model=config['model'], tensor_parallel_size=1,
                    dtype='bfloat16', max_model_len=8192, generation_config='vllm',
                    template_sha256=hashlib.sha256(tokenizer.chat_template.encode()).hexdigest()))
        llm = LLM(model=config['model'], tokenizer=config['model'], dtype='bfloat16',
                  tensor_parallel_size=1, gpu_memory_utilization=0.35,
                  max_model_len=8192, max_num_seqs=10, enforce_eager=True,
                  enable_prefix_caching=True, generation_config='vllm', seed=config['seed'])
        with (ROOT / 'turns.jsonl').open('w', buffering=1) as trace:
            for turn_step in range(config['max_steps']):
                active = [i for i,e in episodes.items() if not e['completed']]
                if not active:
                    break
                prepared, requests, sampling = [], [], []
                for i in active:
                    user_prompt = make_prompt(episodes[i], states[i], config)
                    rendered = tokenizer.apply_chat_template([dict(role='user', content=user_prompt)],
                                add_generation_prompt=True, tokenize=False, enable_thinking=config['enable_thinking'])
                    ids = tokenizer.encode(rendered, add_special_tokens=False)
                    assert len(ids)+config['max_new_tokens'] <= 8192, len(ids)
                    seed = config['seed'] + i*1000 + turn_step
                    prepared.append(dict(episode_id=i, split='train', turn_step=turn_step,
                        observation=states[i]['observation'],
                        admissible_commands=states[i]['admissible_commands'],
                        user_prompt=user_prompt, rendered_prompt=rendered,
                        prompt_token_ids=ids, generation_seed=seed))
                    requests.append(dict(prompt_token_ids=ids))
                    sampling.append(SamplingParams(n=1, temperature=config['temperature'],
                        top_p=config['top_p'], top_k=config['top_k'],
                        max_tokens=config['max_new_tokens'], seed=seed, detokenize=False))
                print('GENERATE', json.dumps(dict(turn=turn_step+1, active=active)), flush=True)
                generation_start = time.time()
                outputs = llm.generate(requests, sampling, use_tqdm=False)
                generated = []
                for record, output in zip(prepared, outputs, strict=True):
                    completion = output.outputs[0]
                    ids = list(completion.token_ids)
                    response = tokenizer.decode(ids, skip_special_tokens=True)
                    parsed = parse_response(response, record['admissible_commands'])
                    generated.append(dict(**record, response=response,
                        raw_response=tokenizer.decode(ids, skip_special_tokens=False),
                        response_token_ids=ids, generated_tokens=len(ids),
                        finish_reason=completion.finish_reason,
                        generation_batch_seconds=time.time()-generation_start, **parsed))
                transitions = rpc(worker, dict(op='step', actions=[dict(episode_id=g['episode_id'], command=g['executed_action']) for g in generated]))
                for record, state in zip(generated, transitions, strict=True):
                    i = record['episode_id']
                    assert state['episode_id'] == i
                    record['next_observation'] = state['observation']
                    record['next_admissible_commands'] = state['admissible_commands']
                    record['environment_won'] = state['won']
                    record['environment_lost'] = state['lost']
                    record['environment_done'] = state['done']
                    record['environment_score'] = state['score']
                    episodes[i]['turns'].append(record)
                    episodes[i]['success'] = state['won']
                    episodes[i]['final_environment_state'] = state
                    states[i] = state
                    if state['won'] or state['done'] or turn_step+1 == config['max_steps']:
                        episodes[i]['completed'] = True
                        episodes[i]['termination'] = 'success' if state['won'] else 'environment_done' if state['done'] else 'max_steps'
                        print('EPISODE_DONE', json.dumps(dict(episode_id=i, task=episodes[i]['task'], success=state['won'], turns=turn_step+1)), flush=True)
                    trace.write(json.dumps(record, ensure_ascii=False)+'\n')
                snapshot(episodes, config, started, 'rollout')
                print('PROGRESS', json.dumps(dict(turn=turn_step+1, successes=sum(e['success'] for e in episodes.values()), completed=sum(e['completed'] for e in episodes.values()))), flush=True)
        snapshot(episodes, config, started, 'complete')
        if not os.environ.get('AUDIT_OUTPUT_DIR'):
            subprocess.run(['/usr/local/bin/python', '/audit/build_report.py'], check=True)
    except Exception:
        write_json(ROOT / 'error.json', dict(error=traceback.format_exc()))
        if episodes:
            snapshot(episodes, config, started, 'failed')
        raise
    finally:
        if worker.poll() is None:
            worker.stdin.write(json.dumps(dict(op='close'))+'\n')
            worker.stdin.flush()
            worker.wait(timeout=30)


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('--preflight', action='store_true')
    main(args.parse_args().preflight)
