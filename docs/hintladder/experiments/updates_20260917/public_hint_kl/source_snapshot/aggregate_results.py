"""Task-paired KL summaries and all 120 free-running trajectories."""
from collections import defaultdict
from pathlib import Path
import csv
import gzip
import hashlib
import json
import re
import statistics
import numpy as np

ROOT=Path(__file__).resolve().parent
ARMS=['base','base_l1','base_l2','base_l3']
LEVELS=['l1','l2','l3']


def read_jsonl(path):return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def avg(xs):
    xs=[x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def bootstrap(values,seed=20260916):
    data=np.asarray(values,dtype=float)
    rng=np.random.default_rng(seed)
    estimates=data[rng.integers(0,len(data),size=(10000,len(data)))].mean(axis=1)
    return dict(mean=float(data.mean()),ci95=[float(x) for x in np.quantile(estimates,[.025,.975])],tasks=len(data))


def free_metrics(episodes):
    result={}
    for cohort in ['additional20','previous10','all30']:
        group=[e for e in episodes if cohort=='all30' or (e['sample_id']<=10)==(cohort=='previous10')]
        result[cohort]={}
        for arm in ARMS:
            es=[e for e in group if e['arm']==arm];ts=[t for e in es for t in e['turns']]
            result[cohort][arm]=dict(tasks=len(es),successes=sum(e['success'] for e in es),
                success_rate=sum(e['success'] for e in es)/len(es),turns=len(ts),
                mean_turns=len(ts)/len(es),mean_response_tokens=avg(t['generated_tokens'] for t in ts),
                mean_reasoning_body_tokens_valid=avg(t['reasoning_body_tokens'] for t in ts),
                format_errors=sum(bool(t['format_error']) for t in ts),
                inadmissible_actions=sum(not t['action_admissible'] for t in ts),
                by_split={split:dict(tasks=sum(e['split']==split for e in es),
                    successes=sum(e['success'] for e in es if e['split']==split))
                    for split in ['valid_seen','valid_unseen']})
    return result


def main():
    assert (ROOT/'rollout_complete.json').exists() and (ROOT/'score_complete.json').exists()
    episodes=read_jsonl(ROOT/'previous10_trajectories.jsonl')
    for path in sorted(ROOT.glob('rollouts/worker_*/episodes.jsonl')):episodes.extend(read_jsonl(path))
    assert len(episodes)==120 and all(e['complete'] for e in episodes)
    lookup={(e['sample_id'],e['arm']):e for e in episodes}
    assert len(lookup)==120
    for sid in range(1,31):
        base=lookup[sid,'base']
        for arm in ARMS:
            e=lookup[sid,arm]
            assert e['checkpoint_step']==0 and e['model_path']=='/models/base'
            assert e['gamefile']==base['gamefile']
            assert e['turns'][0]['public_prompt_token_ids']==base['turns'][0]['public_prompt_token_ids']
            assert {k:v for k,v in e['initial_state'].items() if k!='sample_id'}=={k:v for k,v in base['initial_state'].items() if k!='sample_id'}
            for index,t in enumerate(e['turns']):
                assert t['turn']==index+1 and t['generated_tokens']==len(t['response_token_ids'])
                assert t['observation']==(e['initial_state']['observation'] if index==0 else e['turns'][index-1]['next_state']['observation'])
                if arm!='base':assert t['hint'] and t['hint_metadata']['oracle_supplied'] is False
    inputs=read_jsonl(ROOT/'scoring_inputs.jsonl')
    hint_lengths={}
    for level in LEVELS:
        words=[len(re.findall(r'\S+',row['hints'][level]['hint'])) for row in inputs]
        extra=[len(row['teacher_prompt_token_ids'][level])-len(row['prompt_token_ids']) for row in inputs]
        hint_lengths[level]=dict(states=len(inputs),mean_whitespace_words=avg(words),
            median_whitespace_words=statistics.median(words),
            mean_added_prompt_tokens_including_note_and_advisory=avg(extra))
    save(ROOT/'hint_length_summary.json',hint_lengths)
    turns=[r for p in sorted(ROOT.glob('scores/turns_*.jsonl')) for r in read_jsonl(p)]
    turns.sort(key=lambda r:r['score_row_index'])
    assert len(inputs)==len(turns)==sum(len(lookup[sid,'base']['turns']) for sid in range(1,31))
    assert [r['score_row_index'] for r in turns]==list(range(len(inputs)))
    expected_positions=0
    for inp,result in zip(inputs,turns,strict=True):
        assert inp['row_id']==result['row_id']
        base_turn=lookup[inp['sample_id'],'base']['turns'][inp['turn']-1]
        assert inp['response_token_ids']==base_turn['response_token_ids']
        assert inp['prompt_token_ids']==base_turn['prompt_token_ids']
        assert result['response_tokens']==len(inp['response_token_ids'])
        expected_positions+=result['response_tokens']
    checks=[json.loads(p.read_text()) for p in sorted(ROOT.glob('scores/complete_*.json'))]
    assert len(checks)==8 and sum(c['positions'] for c in checks)==expected_positions
    (ROOT/'full_trajectories_30x4.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in sorted(episodes,key=lambda e:(e['sample_id'],ARMS.index(e['arm'])))))
    (ROOT/'turn_kl_metrics.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in turns))
    free=free_metrics(episodes);save(ROOT/'rollout_summary.json',free)
    # Collapse tokens within task first, so long failed trajectories cannot
    # count as extra independently sampled tasks in the primary comparison.
    task_acc=defaultdict(lambda:defaultdict(float))
    for r in turns:
        for scope_key,m in r['statistics'].items():
            acc=task_acc[r['sample_id'],scope_key];acc['count']+=m['count'];acc['turn_count']+=1
            for field,value in m.items():
                if field!='count':acc[field]+=value*m['count']
    task_rows=[]
    for (sid,key),acc in sorted(task_acc.items()):
        scope,level,temp=key.split('|')
        task_rows.append(dict(sample_id=sid,split=lookup[sid,'base']['split'],
            cohort='previous10' if sid<=10 else 'additional20',scope=scope,level=level,
            temperature=float(temp),tokens=int(acc['count']),turns=int(acc['turn_count']),
            **{k:v/acc['count'] for k,v in acc.items() if k not in ['count','turn_count']}))
    save(ROOT/'task_kl_metrics.json',task_rows)
    with (ROOT/'task_kl_metrics.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(task_rows[0]));writer.writeheader();writer.writerows(task_rows)
    kl={}
    scopes=sorted({r['scope'] for r in task_rows})
    for cohort in ['all30','additional20','previous10','valid_seen','valid_unseen']:
        kl[cohort]={}
        for scope in scopes:
            for temp in [1.0,0.6]:
                for level in LEVELS:
                    rows=[r for r in task_rows if r['scope']==scope and r['temperature']==temp and r['level']==level and (cohort=='all30' or r['cohort']==cohort or r['split']==cohort)]
                    if not rows:continue
                    source=[t['statistics'][f'{scope}|{level}|{temp}'] for t in turns if f'{scope}|{level}|{temp}' in t['statistics'] and (cohort=='all30' or t['cohort']==cohort or t['split']==cohort)]
                    total=sum(r['tokens'] for r in rows)
                    metric_fields=[f for f in rows[0] if f not in ['sample_id','split','cohort','scope','level','temperature','tokens','turns']]
                    kl[cohort][f'{scope}|{level}|{temp}']=dict(tasks=len(rows),tokens=total,
                        equal_task_mean={field:avg(r[field] for r in rows) for field in metric_fields},
                        token_weighted_mean={field:sum(r[field]*r['tokens'] for r in rows)/total for field in metric_fields},
                        equal_turn_mean={field:avg(r[field] for r in source) for field in metric_fields},
                        forward_full_task_bootstrap=bootstrap([r['forward_full'] for r in rows]))
    save(ROOT/'kl_summary.json',kl)
    differences={}
    for cohort in ['all30','additional20','previous10']:
        selected={level:{r['sample_id']:r for r in task_rows if r['scope']=='reasoning_body' and r['temperature']==1 and r['level']==level and (cohort=='all30' or r['cohort']==cohort)} for level in LEVELS}
        differences[cohort]={}
        for first,second in [('l1','l2'),('l2','l3'),('l1','l3')]:
            common=sorted(set(selected[first])&set(selected[second]))
            delta=[selected[second][sid]['forward_full']-selected[first][sid]['forward_full'] for sid in common]
            differences[cohort][f'{second}_minus_{first}']=dict(bootstrap(delta),
                positive_tasks=sum(d>0 for d in delta),negative_tasks=sum(d<0 for d in delta))
    save(ROOT/'paired_kl_differences.json',differences)
    token_count=0
    for path in sorted(ROOT.glob('scores/tokens_*.jsonl.gz')):
        with gzip.open(path,'rt') as stream:
            for line in stream:
                record=json.loads(line)
                assert record['prefix_token_count']==record['response_index']
                token_count+=1
    assert token_count==expected_positions
    save(ROOT/'validation.json',dict(tasks=30,new_tasks=20,previous_tasks=10,
        free_running_episodes=120,new_free_running_episodes=80,base_turns=len(turns),
        scored_token_positions=token_count,hint_distributions_per_position=3,
        original_response_ids_verified=True,paired_initial_states_verified=True,
        original_base_weights_only=True,no_gradient_update=True,no_oracle=True,
        gpu_worker_checks=checks))
    build_viewer(lookup)
    build_plots(task_rows,kl)
    build_report(free,kl,differences,len(turns),token_count)
    print(json.dumps(dict(rollouts=free['additional20'],kl_primary={l:kl['all30'][f'reasoning_body|{l}|1.0'] for l in LEVELS},paired=differences['all30']),ensure_ascii=False,indent=2))


def build_viewer(lookup):
    data=[]
    samples=ROOT/'samples';samples.mkdir(exist_ok=True)
    for sid in range(1,31):
        e=lookup[sid,'base'];p=dict(sample_id=sid,task=e['task'],split=e['split'])
        lines=[f"# Sample {sid}: {e['task']}",'',e['split'],'']
        for arm in ARMS:
            ep=lookup[sid,arm]
            p[arm]=dict(success=ep['success'],termination=ep['termination'],turns=[
                {k:t.get(k) for k in ['turn','hint','observation','admissible_commands','recent_history','reasoning','output','executed_action','generated_tokens','reasoning_body_tokens','format_error','action_admissible','finish_reason']} |
                dict(feedback=t['next_state']['observation'],won=t['next_state']['won']) for t in ep['turns']])
            lines += [f"## {arm}: {'success' if ep['success'] else 'failure'}, {len(ep['turns'])} turns",'']
            for t in ep['turns']:
                lines += [f"### Turn {t['turn']}",'','Observation:','', '```text',t['observation'],'```','',
                    'Hint:','', '```text',t['hint'] or 'None','```','','Model output:','','```text',t['output'],'```','',
                    'Environment feedback:','','```text',t['next_state']['observation'],'```','']
        data.append(p);(samples/f'{sid:02d}_all_levels.md').write_text('\n'.join(lines)+'\n')
    save(ROOT/'viewer_data.json',data)
    packed=json.dumps(data,ensure_ascii=False).replace('<','\\u003c').replace('&','\\u0026')
    template=(ROOT/'viewer_template.html').read_text().replace('10题','30题').replace('10道','30道').replace('${p.task_zh}','${p.task}')
    (ROOT/'viewer.html').write_text(template.replace('__DATA__',packed))


def build_plots(task_rows,summary):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(7.5,4.5),layout='constrained')
    values={level:{r['sample_id']:r['forward_full'] for r in task_rows if r['scope']=='reasoning_body' and r['temperature']==1 and r['level']==level} for level in LEVELS}
    for sid in sorted(values['l1']):
        ax.plot(range(3),[values[l][sid] for l in LEVELS],color='#8b99a6',alpha=.35,linewidth=.8)
    means=[];lower=[];upper=[]
    for l in LEVELS:
        b=summary['all30'][f'reasoning_body|{l}|1.0']['forward_full_task_bootstrap']
        means.append(b['mean']);lower.append(b['mean']-b['ci95'][0]);upper.append(b['ci95'][1]-b['mean'])
    ax.errorbar(range(3),means,yerr=[lower,upper],fmt='o-',color='#145a86',capsize=5,linewidth=2,label='Mean across tasks; task bootstrap 95% CI')
    ax.set_xticks(range(3),['L1','L2','L3 (no Oracle)']);ax.set_ylabel('Full KL(hint || Base), nats/token')
    ax.set_title('Same Base prefixes: reasoning body, 30 tasks, T=1')
    ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
    fig.savefig(ROOT/'kl_reasoning_paired.png',dpi=180);fig.savefig(ROOT/'kl_reasoning_paired.pdf');plt.close(fig)
    regions=['reasoning_body','reasoning_close_tag','action_body']
    fig,ax=plt.subplots(figsize=(8,4.5),layout='constrained')
    for i,level in enumerate(LEVELS):
        ys=[summary['all30'][f'{region}|{level}|1.0']['equal_task_mean']['forward_full'] for region in regions]
        ax.bar(np.arange(3)+(i-1)*.24,ys,width=.24,label=level.upper())
    ax.set_xticks(range(3),['Reasoning body','Reasoning closing tag','Action body'])
    ax.set_ylabel('Task-equal full KL(hint || Base), nats/token');ax.set_title('Same Base prefixes; T=1; 30 tasks')
    ax.grid(axis='y',alpha=.2);ax.legend();fig.savefig(ROOT/'kl_by_region.png',dpi=180);plt.close(fig)


def build_report(free,kl,differences,turns,positions):
    lengths=json.loads((ROOT/'hint_length_summary.json').read_text())
    lines=['# L1–L3追加20题：独立轨迹与相同Base prefix的KL','',
        '新增20个互不重复的任务（Seen 10、Unseen 10），每题运行Base、Base+L1、Base+L2、Base+L3共80条独立轨迹。加上此前10题，累计每组30题、120条轨迹。所有分布来自同一原始Qwen3-4B基础权重；无训练或参数更新。L3沿用新定义：公开状态上的明确动作建议，不提供Oracle。','',
        '[完整轨迹浏览](viewer.html) · [全部120条JSONL](full_trajectories_30x4.jsonl) · [逐turn KL](turn_kl_metrics.jsonl) · [逐题KL CSV](task_kl_metrics.csv) · [参数](protocol.json) · [校验](validation.json)','',
        '**实测排序是L2 > L3 > L1，按reasoning正文完整词表forward KL计算。** 累计30题中，L2和L3各自在30/30题高于L1；L2在27/30题高于L3。这个排序在新增20题中同样成立，语义级别名称并不保证实际分布改变量单调增加。','',
        '## 计算定义','',
        '记s为无hint Base实际到达的公开环境状态，y为它实际采样的response，h_L为GLM只根据该公开状态生成的L级hint。在每个原始token prefix y_<t 上计算：','',
        '`p_t(v) = Base(v | s, y_<t)`','', '`q_L,t(v) = Base(v | s + h_L, y_<t)`','',
        '`forward KL = sum_v q_L,t(v) * [log q_L,t(v) - log p_t(v)]`','',
        '`reverse KL = sum_v p_t(v) * [log p_t(v) - log q_L,t(v)]`','',
        '主指标覆盖完整模型输出词表，T=1、自然对数、单位nats；不做top-k/top-p截断或Top32重归一化。另存T=0.6、Top32+tail粗粒化KL、entropy、top1概率及Top32重叠。GLM不看到当前response或其token prefix，只看与Base相同的任务、观察、最近两轮观察/动作和完整动作空间。GLM每状态给出一次hint，随后用同一个hint对该turn所有Base token位置进行教师强制前向。','',
        f'覆盖30条无hint Base轨迹、{turns}个turn、{positions:,}个原始token位置；每个位置对比L1/L2/L3。先在每题内按reasoning token平均，再对30题等权平均。另保留按token及按turn加权的汇总，避免长失败循环主导唯一结论。','',
        '## 主结果：reasoning正文的完整词表KL','',
        '|hint|KL(hint ‖ Base)，题目等权|任务bootstrap 95% CI|KL(Base ‖ hint)|按token加权的forward KL|Top32+tail forward KL|',
        '|---|---:|---|---:|---:|---:|']
    for level in LEVELS:
        s=kl['all30'][f'reasoning_body|{level}|1.0'];m=s['equal_task_mean'];b=s['forward_full_task_bootstrap']
        lines.append(f"|{level.upper()}|{m['forward_full']:.6f}|[{b['ci95'][0]:.6f}, {b['ci95'][1]:.6f}]|{m['reverse_full']:.6f}|{s['token_weighted_mean']['forward_full']:.6f}|{m['forward_top32_tail']:.6f}|")
    lines += ['', '新增20题单独统计：','', '|hint|题目等权forward KL|题目等权reverse KL|','|---|---:|---:|']
    for level in LEVELS:
        m=kl['additional20'][f'reasoning_body|{level}|1.0']['equal_task_mean']
        lines.append(f"|{level.upper()}|{m['forward_full']:.6f}|{m['reverse_full']:.6f}|")
    lines += ['', '![Paired task KL](kl_reasoning_paired.png)','', '同题配对差值（后一层减前一层）：','',
        '|差值|均值|任务bootstrap 95% CI|差值为正的题数|','|---|---:|---|---:|']
    for name,s in differences['all30'].items():lines.append(f"|{name}|{s['mean']:.6f}|[{s['ci95'][0]:.6f}, {s['ci95'][1]:.6f}]|{s['positive_tasks']}/{s['tasks']}|")
    lines += ['', 'KL衡量输入hint造成的分布变化，不是hint正确性、帮助程度或训练收益；更大不自动代表更好。每个状态只取一个hint样本，置信区间只反映这批任务间的变化，不包含重复生成hint的方差。','',
        f"本次992个Base状态上的hint平均长度为：L1 {lengths['l1']['mean_whitespace_words']:.1f}词、L2 {lengths['l2']['mean_whitespace_words']:.1f}词、L3 {lengths['l3']['mean_whitespace_words']:.1f}词（按空白分词）。L2提供较长的局部分析，可能与reasoning分布变化更大有关，但本实验没有控制hint长度，不能单独归因于级别或措辞。",'',
        '## 不同输出区域','', '![KL by region](kl_by_region.png)','',
        'reasoning正文和标签边界由原始token IDs的解码前缀定位；不重新编码response。跨越闭合标签边界的token归入闭合标签组。未闭合的reasoning单列，不伪装成有效正文；`valid_reasoning_body`另提供训练格式检查通过的正文统计。原始token级明细保存在`scores/tokens_*.jsonl.gz`，按`score_row_index`与`response_index`可精确还原prefix。','']
    for cohort,title in [('additional20','新增20题独立rollout'),('all30','累计30题独立rollout')]:
        lines += [f'## {title}','', '|条件|成功|Seen|Unseen|平均turn数|平均输出tokens|平均reasoning tokens（有效格式）|格式错误turn|','|---|---:|---:|---:|---:|---:|---:|---:|']
        for arm in ARMS:
            s=free[cohort][arm];seen=s['by_split']['valid_seen'];unseen=s['by_split']['valid_unseen']
            lines.append(f"|{arm}|{s['successes']}/{s['tasks']}|{seen['successes']}/{seen['tasks']}|{unseen['successes']}/{unseen['tasks']}|{s['mean_turns']:.2f}|{s['mean_response_tokens']:.2f}|{s['mean_reasoning_body_tokens_valid']:.2f}|{s['format_errors']}/{s['turns']}|")
    lines += ['', '独立rollout的状态会分岔；上述KL完全沿无hint Base的轨迹计算，不把各hint组自身路径上的概率拿来与Base错位比较。提示词保持上一批不变，实际输出可能越过预设剂量边界或包含错误；原始hint均保留，未按质量重抽。','',
        '## 运行与复现','', '8卡独立推理；每题最多50轮，每response最多1024token，temperature=0.6、top_p=0.95、top_k=20，原生thinking关闭、显式reasoning。GLM-5.3-Flash生成hint，thinking开启，reasoning_effort=low。相同level、公共状态、seed和系统提示词的已有hint可复用，其余重新请求，来源逐条标记。KL前向使用eval模式及inference_mode，log_softmax和概率运算使用FP32；只分块落词表logits，避免把所有序列位置的FP32词表同时留在显存。','',
        '检查包含已知不对称分布、相同分布KL=0、极小tail稳定性；每个GPU额外核对原始模型forward与拆分hidden/lm_head的logits、同长度输入上扰动所有未来token后的因果不变性，以及FP64参考KL。独立prefix与完整序列的跨长度数值差异另作诊断记录。所有检查结果保留在validation.json。','',
        '首次打分在跨序列长度的BF16最大logit差阈值处停止，记录位于score_attempts/initial_isolated_prefix_threshold，未纳入结果。抽查同长度原生前向与拆分计算完全一致，未来token扰动也不改变当前预测；独立prefix的某个位置虽有0.5625的最大logit差，其分布KL仅约1.74e-12。正式重跑采用同长度因果校验，不再把跨长度的原始logit最大差作为对齐失败的充分条件。','']
    (ROOT/'REPORT.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':main()
