"""Offline checks for the published research evidence; stdlib only.

Usage: python docs/hintladder/experiments/updates_20260917/verify_publication.py
No model, API, GPU, or local original run directories are required.
"""
from collections import Counter, defaultdict
from pathlib import Path
import gzip
import hashlib
import json
import math
import re
import statistics
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
KL = ROOT/'public_hint_kl'
TRAIN = ROOT/'frozen_teacher_training'


def read_jsonl(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def close(a, b):
    assert math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10), (a,b)


def main():
    files = json.loads((ROOT/'source_manifest.json').read_text())
    copied = 0
    for entry in files:
        path = ROOT/entry['published_path']
        raw = path.read_bytes()
        if entry['encoding'].startswith('gzip'):
            raw = gzip.decompress(raw)
        elif entry['encoding'] != 'byte-identical':
            continue
        assert hashlib.sha256(raw).hexdigest() == entry['source_sha256'], path
        copied += 1
    episodes = read_jsonl(KL/'full_trajectories_30x4.jsonl.gz')
    assert len(episodes) == 120
    lookup = {(e['sample_id'],e['arm']):e for e in episodes}
    assert len(lookup) == 120
    for arm, expected in [('base',15),('base_l1',20),('base_l2',26),('base_l3',25)]:
        group = [e for e in episodes if e['arm'] == arm]
        assert len(group) == 30 and sum(e['success'] for e in group) == expected
        assert Counter(e['split'] for e in group) == {'valid_seen':15,'valid_unseen':15}
        for e in group:
            assert e['checkpoint_step'] == 0 and e['complete']
            assert e['gamefile'] == lookup[e['sample_id'],'base']['gamefile']
            for t in e['turns']:
                assert t['oracle_supplied'] is False
                assert t['generated_tokens'] == len(t['response_token_ids'])
    inputs = read_jsonl(KL/'scoring_inputs.jsonl.gz')
    turns = read_jsonl(KL/'turn_kl_metrics.jsonl.gz')
    assert len(inputs) == len(turns) == 992
    assert sum(len(r['response_token_ids']) for r in inputs) == 221620
    for source, scored in zip(inputs,turns):
        assert source['score_row_index'] == scored['score_row_index']
        assert source['row_id'] == scored['row_id']
        base = lookup[source['sample_id'],'base']['turns'][source['turn']-1]
        assert source['response_token_ids'] == base['response_token_ids']
        assert source['prompt_token_ids'] == base['prompt_token_ids']
        assert scored['response_tokens'] == len(base['response_token_ids'])
        assert set(source['hints']) == {'l1','l2','l3'}
        for h in source['hints'].values():
            assert h['public_input'] == source['public_input'] and h['hint'].strip()
    task_rows = json.loads((KL/'task_kl_metrics.json').read_text())
    primary = {level:[r for r in task_rows if r['scope']=='reasoning_body'
        and r['temperature']==1.0 and r['level']==level] for level in ['l1','l2','l3']}
    expected = [0.6492951906,1.1055311166,0.9712865104]
    means = {}
    for (level, rows), mean in zip(primary.items(),expected):
        assert len(rows) == 30
        means[level] = statistics.mean(r['forward_full'] for r in rows)
        close(means[level],mean)
    by_task={level:{r['sample_id']:r['forward_full'] for r in rows} for level,rows in primary.items()}
    assert sum(by_task['l2'][i]>by_task['l3'][i] for i in range(1,31)) == 27
    # Recompute task-level KL from the published per-turn sufficient statistics.
    for level, rows in primary.items():
        for r in rows:
            stats=[t['statistics'][f'reasoning_body|{level}|1.0'] for t in turns
                   if t['sample_id']==r['sample_id'] and f'reasoning_body|{level}|1.0' in t['statistics']]
            close(r['forward_full'],sum(s['forward_full']*s['count'] for s in stats)/sum(s['count'] for s in stats))
    protocol=json.loads((KL/'protocol.json').read_text())
    for name, expected_hash in protocol['prompt_sha256'].items():
        assert hashlib.sha256((KL/name).read_bytes()).hexdigest()==expected_hash
    design=(REPO/'docs/hintladder/hint_levels_20260917.md').read_text()
    for level in ['l1','l2','l3']:
        assert (KL/f'{level}_prompt.txt').read_text().strip() in design
    evals = read_jsonl(TRAIN/'evaluation_episodes.jsonl')
    assert len(evals)==2192
    summary=json.loads((TRAIN/'summary.json').read_text())
    for e in summary['evaluations']:
        rs=[r for r in evals if all(r[k]==e[k] for k in ['arm','step','split'])]
        assert len(rs)==len({r['gamefile'] for r in rs})==e['tasks']
        assert sum(r['success'] for r in rs)==e['successes']
        close(e['success_rate'],e['successes']/e['tasks'])
    parent=read_jsonl(TRAIN/'l3_parent_metrics.jsonl')
    resumed=read_jsonl(TRAIN/'l3_resume50_metrics.jsonl')
    effective=read_jsonl(TRAIN/'l3_effective_metrics.jsonl')
    assert effective==[r for r in parent if r['step']<=50]+resumed
    for arm, filename, last in [('l1','l1_metrics.jsonl',155),('l3','l3_effective_metrics.jsonl',58)]:
        rows=read_jsonl(TRAIN/filename)
        assert [r['step'] for r in rows]==list(range(1,last+1))
        assert sum(r['hint_ladder/empty_reasoning_rows'] for r in rows)==0
        assert sum(r['hint_ladder/update_skipped_no_supervision'] for r in rows)==0
        s=summary['effective_runs'][arm]
        close(s['response_tokens_last10_step_mean'],statistics.mean(r['response_length/mean'] for r in rows[-10:]))
    for split in ['valid_seen','valid_unseen']:
        a=read_jsonl(TRAIN/'traces'/f'l1_step50_{split}.jsonl')
        b=read_jsonl(TRAIN/'traces'/f'l3_step50_{split}.jsonl')
        assert a[0]['gamefile']==b[0]['gamefile']
        for rows in [a,b]:
            assert [r['turn_step'] for r in rows]==list(range(len(rows)))
    # Check links in new documentation, ignoring literal fenced examples.
    docs=list(ROOT.rglob('*.md'))+[REPO/'docs/hintladder/hint_levels_20260917.md']
    checked_links=0
    for path in docs:
        text=re.sub(r'```.*?```','',path.read_text(),flags=re.S)
        for href in re.findall(r'\]\(([^)]+)\)',text):
            if href.startswith(('http:', 'https:', '#', 'mailto:')):
                continue
            target=unquote(href.split('#',1)[0].strip('<>'))
            assert (path.parent/target).exists(), (str(path.relative_to(REPO)),target)
            checked_links+=1
    forbidden=[r'\bsk-[A-Za-z0-9_-]{20,}',r'\bwandb_v1_[A-Za-z0-9_-]{20,}',
               r'\bgh[pousr]_[A-Za-z0-9]{20,}',r'\bgithub_pat_[A-Za-z0-9_]{20,}',
               r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
    for path in ROOT.rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        assert path.stat().st_size < 50*1024**2, path.name
        assert path.name not in {'auth.json','auth_manifest.json'}
        raw=path.read_bytes()
        if path.suffix=='.gz':raw=gzip.decompress(raw)
        if path.suffix in {'.png','.pdf'}:continue
        content=raw.decode('utf-8')
        assert not any(re.search(p,content) for p in forbidden), 'Credential-like text in '+path.name
    manifest=ROOT/'MANIFEST.sha256'
    if manifest.exists():
        for line in manifest.read_text().splitlines():
            digest, name=line.split('  ',1)
            assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest, name
    result=dict(status='passed',source_copies_verified=copied,free_running_episodes=120,
        base_prefix_turns=992,original_token_positions=221620,reasoning_forward_kl=means,
        training_evaluation_episodes=2192,local_document_links_checked=checked_links,
        no_api_or_gpu_used=True)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
