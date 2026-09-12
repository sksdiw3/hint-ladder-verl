import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
VIS=Path('/home/research/.codex/visualizations/2026/09/07/01a07ba6-8242-7d21-a892-436408e5f2e2/alfworld-turn-prefix-top10.html')
meta=json.loads((ROOT/'turn.json').read_text())
records=[json.loads(s) for s in (ROOT/'prefix_top10.jsonl').open()]
assert len(records)==105
def token(t):
    return '`'+json.dumps(t,ensure_ascii=False).replace('|','&#124;').replace('`','&#96;')+'`'
def prob(p):
    return f'{100*p:.6f}%' if p>=1e-5 else f'{100*p:.5e}%'
lines=['# 一条完整 turn：每个学生 prefix 下的学生 / 教师 top-10','',
       '模型：原始 Qwen3-4B，checkpoint_step=0。数据：训练集题 7，turn 1。', '',
       '**两侧接同一个学生 response prefix**：学生 prompt 无 hint，教师 prompt 为同一 prompt 加缓存 L1 hint 和当前使用说明；没有让教师另起一条轨迹。', '',
       '覆盖全部 **105** 个 response token 预测位置，包括 85 个 reasoning 正文位置，以及标签、action、结束 token。位置从 1 开始；位置 i 的 response prefix 包含原轨迹前 i−1 个 token。没有对输入 prompt 本身的 token 逐个评分。', '',
       '表中 p 是温度 **T=0.6** 的全词表 softmax 概率，没有先做 top-k/top-p 截断，也没有在 top-10 内重新归一化。`raw logit` 为除温度之前的值。JSONL 和 CSV 另外保留 T=1.0 的概率、token ID、熵和目标 token 概率。', '',
       '## 完整 turn', '', '任务：'+meta['task_zh']+' / '+meta['task'], '', '当前 observation：','','```text',str(meta['current_observation']),'```','',
       'Admissible actions：','','```json',json.dumps(meta['admissible_actions'],ensure_ascii=False,indent=2),'```','',
       'L1 hint 原文：', '',meta['hint'],'','中文：'+meta['hint_zh'],'',
       '学生完整输出（含特殊结束 token）：','','```text',meta['raw_response'],'```','',
       '实际执行动作：`'+str(meta['executed_action'])+'`。执行后的环境反馈：','','```json',json.dumps(meta['next_state'],ensure_ascii=False,indent=2),'```','',
       '完整学生 prompt：[student_prompt.txt](student_prompt.txt)；完整教师 prompt：[teacher_prompt.txt](teacher_prompt.txt)。', '',
       '## 每个 prefix 的 top-10', '',
       '引号内保留空格；`\\n` 表示换行。token 是 BPE 子词，未必是完整英文单词。同分候选使用 torch.topk(10) 的实际排序，不把它当作唯一排序。']
csv_rows=[]
for r in records:
    lines += ['',f'### 位置 {r["position"]}/105 · {r["region"]}', '',
       f'Prefix 已有 {r["prefix_token_count"]} 个 response token；原轨迹下一个 token：{token(r["actual_next_token"]["text"])}，ID={r["actual_next_token"]["id"]}。','',
       '```text',r['response_prefix'] or '（空 response prefix；只有 prompt）','```','',
       '| 排名 | 学生 token | raw logit | 学生 p | 教师 token | raw logit | 教师 p |',
       '|---:|---|---:|---:|---|---:|---:|']
    for rank,(s,t) in enumerate(zip(r['student']['top10'],r['teacher']['top10']),1):
        lines.append(f'| {rank} | {token(s["text"])} | {s["raw_logit"]:g} | {prob(s["probability"]["0.6"])} | {token(t["text"])} | {t["raw_logit"]:g} | {prob(t["probability"]["0.6"])} |')
        for arm,item in [('student',s),('teacher',t)]:
            csv_rows.append({'position':r['position'],'response_index':r['response_index'],'region':r['region'],'prefix':r['response_prefix'],
                'actual_next_token_id':r['actual_next_token']['id'],'actual_next_token':r['actual_next_token']['text'],'arm':arm,'rank':rank,
                'token_id':item['id'],'token_text':item['text'],'raw_logit':item['raw_logit'],'probability_T0.6':item['probability']['0.6'],
                'probability_T1.0':item['probability']['1.0'],'log_probability_T0.6':item['log_probability']['0.6']})
lines += ['', '## 校验与范围', '',
    '- 原始 sampled response IDs 与保留的无 hint base turn 精确一致；teacher prompt 删除便签后精确还原 student prompt。',
    '- 每侧在 5 个位置独立截断输入再前向，共 10 项因果对齐检查；输入不包含目标 token 或后续 token。',
    f'- 独立 prefix 校验的最大 raw-logit 差为 {max(c["max_abs_logit_difference"] for c in meta["checks"]):g}，T=1 概率最大绝对差为 {max(c["max_abs_probability_difference_T1"] for c in meta["checks"]):.3g}。BF16 的低概率候选可因计算形状出现微小分数差异。',
    f'- 单卡峰值 PyTorch allocated {meta["peak_allocated_bytes"]/1024**3:.2f} GiB；没有训练、更新权重、重新 rollout 或调用 hint API。',
    '- 这是 base 的单条 turn 诊断，不是已删除训练 checkpoint 的输出，也不是全量统计。', '',
    '文件：[完整 JSONL](prefix_top10.jsonl) · [逐候选 CSV](prefix_top10.csv) · [完整 turn 元信息](turn.json)。','']
(ROOT/'完整turn_逐prefix_top10.md').write_text('\n'.join(lines))
with (ROOT/'prefix_top10.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=list(csv_rows[0]));writer.writeheader();writer.writerows(csv_rows)
(ROOT/'student_prompt.txt').write_text(meta['student_prompt'])
(ROOT/'teacher_prompt.txt').write_text(meta['teacher_prompt'])
(ROOT/'README.md').write_text('# 单条 turn 的全部 prefix 分布\n\n[完整 turn 与 105 个位置的 top-10](完整turn_逐prefix_top10.md)\n\n[JSONL](prefix_top10.jsonl) · [CSV](prefix_top10.csv) · [完整 turn](turn.json)\n\nQwen3-4B base；训练集题 7 / turn 1。105 个 response 预测位置，两侧使用相同学生 prefix。此包是删除旧批量缓存后，按用户新请求补算的一条诊断。\n')
# The fragment markup is authored literally in its HTML file; only insert data here.
markup=VIS.read_text()
payload=json.dumps({'meta':meta,'records':records},ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
assert '__OPD_PREFIX_DATA__' in markup
VIS.write_text(markup.replace('__OPD_PREFIX_DATA__',payload))
assert VIS.stat().st_size<1024*1024
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!='MANIFEST.sha256'}
(ROOT/'MANIFEST.sha256').write_text(''.join(f'{digest}  {name}\n' for name,digest in manifest.items()))
print(json.dumps({'positions':len(records),'csv_candidate_rows':len(csv_rows),'markdown_sections':sum(x.startswith('### 位置 ') for x in lines),
    'inline_bytes':VIS.stat().st_size,'directory':str(ROOT)},ensure_ascii=False))
