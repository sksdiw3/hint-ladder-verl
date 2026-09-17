"""Prepare three matched-state hints on all thirty original Base trajectories."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
import hashlib
import json
import time
import traceback
from common import ROOT, write_json, read_jsonl
from hint_provider import HintProvider

LEVELS=['l1','l2','l3']


def key(level, seed, public):
    return (level,seed,json.dumps(public,sort_keys=True,ensure_ascii=False))


def public_for(turn):
    return dict(task=turn['task'],step_count=turn['turn']-1,current_step=turn['turn'],
        current_observation=turn['observation'],action_history=turn['recent_history'],
        action_space=turn['admissible_commands'])


def main():
    from transformers import AutoTokenizer
    from hintladder.teacher_prompt import insert_note,remove_note
    out=ROOT/'prefix_hints';out.mkdir(exist_ok=True)
    records_dir=out/'records';records_dir.mkdir(exist_ok=True)
    provider=HintProvider(out)
    tokenizer=AutoTokenizer.from_pretrained('/models/base',local_files_only=True)
    previous=read_jsonl(ROOT/'previous10_trajectories.jsonl')
    protocol=json.loads((ROOT/'protocol.json').read_text())
    for level in LEVELS:
        name=f'{level}_prompt.txt'
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==protocol['prompt_sha256'][name]
    expected_ids=set(range(1,31))
    bases={};hint_cache={};submitted=set();pending={};completed={}
    started=time.monotonic();last_refresh=0

    def refresh(episodes):
        for episode in episodes:
            if episode['arm']=='base':
                bases[episode['sample_id']]=episode
            else:
                level=episode['arm'].removeprefix('base_')
                for t in episode['turns']:
                    if t['hint']:
                        k=key(level,t['generation_seed'],t['hint_public_input'])
                        hint_cache.setdefault(k,dict(note=t['hint_metadata'],
                            source_row_id=t['row_id'],source_sample_id=episode['sample_id']))

    def obtain(job):
        path=records_dir/f"{job['sample_id']:03d}_{job['turn']:03d}_{job['level']}.json"
        if path.exists():
            record=json.loads(path.read_text())
            assert record['public_input']==job['public_input']
            return record
        cached=job['cached']
        if cached:
            note=cached['note'];source='exact_state_free_rollout'
        else:
            request=dict(row_id=f"prefix_{job['level']}:{job['sample_id']}:{job['turn']}",
                arm='base_'+job['level'],generation_seed=job['seed'],hint_public_input=job['public_input'])
            note=provider.generate(request);source='new_matched_base_state'
        assert note['hint'] and note['level']==job['level'].upper()
        assert note['oracle_supplied'] is False and note['returned_model']=='glm-5.3-flash'
        result=dict(sample_id=job['sample_id'],turn=job['turn'],level=job['level'],
            public_input=job['public_input'],generation_seed=job['seed'],hint=note['hint'],
            metadata=note,source=source,
            reused_row_id=cached['source_row_id'] if cached else None)
        write_json(path,result)
        return result

    refresh(previous)
    try:
        with ThreadPoolExecutor(max_workers=64) as pool:
            while True:
                if time.monotonic()-last_refresh>=3:
                    current=[]
                    for path in sorted(ROOT.glob('rollouts/worker_*/episodes.jsonl')):
                        current.extend(read_jsonl(path))
                    refresh(current);last_refresh=time.monotonic()
                    for sid,episode in sorted(bases.items()):
                        for t in episode['turns']:
                            public=public_for(t)
                            for level in LEVELS:
                                uid=(sid,t['turn'],level)
                                if uid in submitted:continue
                                submitted.add(uid)
                                job=dict(sample_id=sid,turn=t['turn'],level=level,
                                    public_input=public,seed=t['generation_seed'],
                                    cached=hint_cache.get(key(level,t['generation_seed'],public)))
                                pending[pool.submit(obtain,job)]=uid
                if pending:
                    ready,_=wait(pending,timeout=1,return_when=FIRST_COMPLETED)
                    for future in ready:
                        uid=pending.pop(future);completed[uid]=future.result()
                else:time.sleep(1)
                write_json(ROOT/'prefix_hint_progress.json',dict(base_tasks_observed=len(bases),
                    base_tasks_complete=sum(e['complete'] for e in bases.values()),
                    hints_submitted=len(submitted),hints_completed=len(completed),
                    pending=len(pending),seconds=time.monotonic()-started))
                if set(bases)==expected_ids and all(e['complete'] for e in bases.values()) and not pending:
                    required=sum(len(e['turns'])*3 for e in bases.values())
                    if len(completed)==required:break
                if time.monotonic()-started>7200:raise TimeoutError('Matched hint preparation exceeded two hours')
        rows=[]
        for sid,episode in sorted(bases.items()):
            for t in episode['turns']:
                assert t['arm']=='base' and not t['hint']
                assert tokenizer.encode(t['public_rendered_prompt'],add_special_tokens=False)==t['prompt_token_ids']
                notes={level:completed[sid,t['turn'],level] for level in LEVELS}
                teacher_ids={}
                for level,note in notes.items():
                    rendered=insert_note(t['public_rendered_prompt'],note['hint'])
                    assert remove_note(rendered)==t['public_rendered_prompt']
                    ids=tokenizer.encode(rendered,add_special_tokens=False)
                    assert len(ids)+len(t['response_token_ids'])<=8192
                    teacher_ids[level]=ids
                row=dict(score_row_index=len(rows),row_id=t['row_id'],sample_id=sid,
                    cohort='previous10' if sid<=10 else 'additional20',split=episode['split'],
                    task=episode['task'],gamefile=episode['gamefile'],turn=t['turn'],
                    public_input=public_for(t),public_user_prompt=t['public_user_prompt'],
                    public_rendered_prompt=t['public_rendered_prompt'],
                    prompt_token_ids=t['prompt_token_ids'],response_token_ids=t['response_token_ids'],
                    output=t['output'],format_error=t['format_error'],
                    teacher_prompt_token_ids=teacher_ids,hints=notes)
                rows.append(row)
        (ROOT/'scoring_inputs.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
        write_json(ROOT/'prefix_hints_complete.json',dict(tasks=len(bases),base_turns=len(rows),
            hints=len(completed),reused=sum(n['source']=='exact_state_free_rollout' for n in completed.values()),
            newly_generated=sum(n['source']=='new_matched_base_state' for n in completed.values()),
            positions=sum(len(r['response_token_ids']) for r in rows),seconds=time.monotonic()-started))
        print('PREFIX_HINTS_COMPLETE',len(rows),len(completed),flush=True)
    except Exception:
        write_json(ROOT/'prefix_hints_error.json',dict(error=traceback.format_exc()))
        raise
    finally:
        provider.close()


if __name__=='__main__':main()
