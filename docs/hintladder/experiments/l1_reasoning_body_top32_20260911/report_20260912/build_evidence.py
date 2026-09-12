"""Rebuild report tables and readable traces from retained evidence; no model/API calls."""
from pathlib import Path
import csv
import hashlib
import json
import re
import statistics

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
KEY = ROOT / 'exports/key_error_traces_20260912'


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def block(value):
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, indent=2)
    assert '````' not in value
    return '\n````text\n' + value + '\n````\n'


def task_from_prompt(text):
    return re.search(r'Your task is to: (.*?) Prior to this step,', text, re.S).group(1)


def build():
    metrics = read_jsonl(KEY / 'metrics.jsonl')
    assert [r['step'] for r in metrics] == list(range(1, 111))
    timeline = json.loads((KEY / 'error_timeline.json').read_text())
    errors = {r['step']: r for r in timeline['format_error_counts']}
    rows = []
    for r in metrics:
        step = r['step']
        count = errors.get(step, {}).get('error_counts', {})
        # Missing error file means zero only if the original metric also says zero.
        assert step in errors or r['hint_ladder/format_invalid_rows'] == 0
        assert sum(count.values()) == r['hint_ladder/format_invalid_rows']
        n = r['hint_ladder/format_total_rows']
        body = r['hint_ladder/reasoning_body_tokens']
        rows.append(dict(step=step, turns=n, empty_reasoning=count.get('empty_reasoning', 0),
            other_format_errors=sum(v for k, v in count.items() if k != 'empty_reasoning'),
            empty_ratio=count.get('empty_reasoning', 0) / n,
            format_invalid_ratio=r['hint_ladder/format_invalid_ratio'],
            reasoning_body_tokens=body, body_tokens_per_original_turn=body / n,
            whole_response_tokens_mean=r['response_length/mean'],
            supervised_token_ratio=r['hint_ladder/supervised_token_ratio'],
            update_skipped=r['hint_ladder/update_skipped_no_supervision'],
            train_episode_success_rate=r['episode/success_rate'],
            step_seconds=r['timing_s/step'], rollout_seconds=r['timing_s/gen'],
            teacher_forward_seconds=r['timing_s/teacher_forward'],
            update_seconds=r['timing_s/update_actor'],
            hint_wait_seconds=r['hint_ladder/hint_wait_seconds']))
    with (OUT / 'training_timeline.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    evaluations = []
    for r in metrics:
        if 'val/valid_seen/success_rate' not in r:
            continue
        e = {'step': r['step'], 'hint': False, 'max_response_tokens': 1024}
        for split in ['seen', 'unseen']:
            prefix = f'val/valid_{split}/'
            n = int(r[prefix + 'unique_games'])
            rate = r[prefix + 'text/success/mean@1']
            assert abs(rate * n - round(rate * n)) < 1e-7
            e[split] = {'successes': round(rate * n), 'games': n, 'success_rate': rate}
        evaluations.append(e)
    groups = {}
    time_keys = ['timing_s/step', 'timing_s/gen', 'timing_s/old_log_prob',
                 'timing_s/teacher_forward', 'timing_s/update_actor',
                 'hint_ladder/hint_wait_seconds', 'hint_ladder/hint_request_p50_seconds',
                 'hint_ladder/hint_request_p95_seconds', 'hint_ladder/hint_requests']
    for lo, hi in [(1, 18), (19, 21), (22, 110), (1, 110)]:
        values = [r for r in metrics if lo <= r['step'] <= hi]
        groups[f'{lo}-{hi}'] = {key: statistics.mean(r.get(key, 0) for r in values) for key in time_keys}
    summary = dict(completed_logged_steps=len(metrics), planned_steps=223,
        skipped_optimizer_steps=sum(r['update_skipped'] for r in rows),
        first_empty_reasoning_step=next(r['step'] for r in rows if r['empty_reasoning']),
        first_zero_supervision_step=next(r['step'] for r in rows if not r['reasoning_body_tokens']),
        total_logged_step_hours=sum(r['step_seconds'] for r in rows)/3600,
        hint_failed_states=sum(r['hint_ladder/hint_failed_states'] for r in metrics),
        hint_failed_rows=sum(r['hint_ladder/hint_failed_rows'] for r in metrics),
        evaluations=evaluations, timing_step_means=groups,
        milestones=[r for r in rows if r['step'] in [1,5,10,15,18,19,20,21,22,25,50,75,100,110]],
        caveat='body counts are trainer totals after distributed padding; turn denominator is pre-padding. '
               'Their quotient is approximate body tokens per original turn, not an exact unpadded mean.')
    save_json(OUT / 'summary.json', summary)

    trace_dir = OUT / 'traces'
    trace_dir.mkdir(exist_ok=True)
    bases = read_jsonl(KEY / 'base_matched_controls.jsonl')
    trains = read_jsonl(KEY / 'training_error_episodes.jsonl')
    index = ['# 真实完整轨迹', '',
        '原始英文 prompt、response、hint、动作均直接从保留 JSONL 提取，未改写。中文任务与说明是编辑注释。', '',
        '这是按现象选择的定性样例，不是随机抽样，也不能用这几条估计成功率。所有案例来自训练集。', '',
        '基础模型 online_l1 是推理时直接看 hint；训练案例则始终是无 hint 的 Student，附带 hint 只用于 Teacher 评分。', '',
        '训练记录 step 指 rollout/更新的日志步号：该批 rollout 在该步 optimizer 更新之前产生，不能称为同号 checkpoint 生成。', '',
        '| 案例 | 模型/条件 | 任务（中文） | 完整 turns | 观察结果 |',
        '|---|---|---|---:|---|']
    traces_metadata = []
    task_zh = {3: '借助台灯检查 CD', 7: '把洗手液瓶放到马桶上'}
    for wrapped in bases:
        e = wrapped['original']
        slug = f"base_pair{e['pair_id']}_{e['arm']}"
        name = f'{slug}.md'
        success = '成功' if e['success'] else '未成功'
        index.append(f"| [{slug}](traces/{name}) | 原始 Qwen3-4B / {e['arm']} | {task_zh[e['pair_id']]} | {len(e['turns'])} | {success}；结束原因 `{e['termination']}` |")
        parts = [f'# {slug}', '', f"任务：{e['task']}（{task_zh[e['pair_id']]}）。结果：{success}。",
                 f"split={e['split']}；checkpoint_step=0；完整 {len(e['turns'])} turns。",
                 '来源（旧全量文件可能已删除；完整原始记录包含在当前保留包）：', block(wrapped['source'])]
        for t in e['turns']:
            parts += [f"## Turn {t['turn_step'] + 1}", '', '模型实际输入（含 chat template）：', block(t['rendered_prompt']),
                      '实际 hint（空值表示无 hint）：', block(t['hint']),
                      '模型原始输出：', block(t['raw_output']),
                      f"执行动作：`{t['executed_action']}`；动作有效：{t['is_action_valid']}；格式错误：`{t['format_error']}`。",
                      '执行后环境状态（原始记录）：', block(t['next_state'])]
        (trace_dir / name).write_text('\n'.join(parts) + '\n')
        traces_metadata.append(dict(file=f'traces/{name}', source_jsonl='base_matched_controls.jsonl',
                                    pair_id=e['pair_id'], arm=e['arm'], turns=len(e['turns'])))

    training_titles = {10: '冷却生菜并放到餐桌', 20: '找到两部手机放进抽屉'}
    for e in trains:
        step = e['rollout_logging_step']
        if step not in (10, 20, 110):
            continue
        slug = f"train_step{step}_{e['selection']}"
        name = f'{slug}.md'
        title = training_titles.get(step, '加热鸡蛋并放进冰箱' if e['selection'].startswith('mixed') else '找到两个闹钟放到边桌')
        first = e['turns'][0]['original']
        turns = e['turns']
        assert e['starts_at_turn_zero'] and e['contiguous_logged_turns']
        assert [t['original']['turn_step'] for t in turns] == list(range(len(turns)))
        index.append(f"| [{slug}](traces/{name}) | 训练批次 step {step} / Student 无 hint | {title} | {len(turns)} | 空 reasoning {e['empty_reasoning_turns']}/{len(turns)} |")
        parts = [f'# {slug}', '', f'任务：{task_from_prompt(first["input"])}（{title}）。',
                 f"split=train；rollout_logging_step={step}；完整 {len(turns)} turns；空 reasoning {e['empty_reasoning_turns']} 条。",
                 'Student 没有收到下面附带的 hint；它只进入 Teacher 的前向评分。终局成功标签未单独保存在该导出 schema 中，不根据格式或单个 score 补造判断。',
                 '来源：', block(e['source']), f"轨迹 ID：`{e['traj_uid']}`。"]
        for t in turns:
            o = t['original']
            parts += [f"## Turn {o['turn_step'] + 1}", '', f"原始文件行号：{t['source_line']}。",
                      'Student 原始输入（包含任务、最近两轮观察/动作、当前观察、当前动作空间）：', block(o['input']),
                      'Teacher 评分使用的 hint：', block(o.get('online_l1_hint', '')),
                      'Student 原始输出：', block(o['output']),
                      f"执行动作：`{o['executed_action']}`；动作有效：{o['is_action_valid']}；格式有效：{o['sdl_format_valid']}；格式错误：`{o['sdl_format_error']}`；监督 token：{o['sdl_supervised_tokens']}。"]
        parts += ['', '后续观察可在下一 turn 的原始输入中核对；最后一个动作后的 observation 不在这个训练导出中，未补写。']
        (trace_dir / name).write_text('\n'.join(parts) + '\n')
        traces_metadata.append(dict(file=f'traces/{name}', source_jsonl='training_error_episodes.jsonl',
                                    step=step, traj_uid=e['traj_uid'], turns=len(turns)))

    index += ['', '原始 JSONL：', '',
              '- [4 局 base 对照](../../../../../exports/key_error_traces_20260912/base_matched_controls.jsonl)，93 turns。',
              '- [6 局完整训练轨迹](../../../../../exports/key_error_traces_20260912/training_error_episodes.jsonl)，300 turns；本页展开其中 4 局。',
              '- [40 条关键错误 turn](../../../../../exports/key_error_traces_20260912/key_error_turns.jsonl)，覆盖多个记录节点。',
              '', '图文页面合计 8 局、293 turns；保留 JSONL 合计 10 局、393 turns。历史来源文件 SHA256 是清理前留下的追溯信息；发布文件可通过清单重新校验。',
              '', '提示质量边界：pair3 的部分 hint 使用了 “both items in hand” 的不准确说法；台灯不需要拿在手上。这里保留原文，不能把 GLM 输出当作标准答案。']
    (OUT / '真实轨迹.md').write_text('\n'.join(index) + '\n')
    save_json(OUT / 'trace_index.json', traces_metadata)

    # A few complete real turns, including failure records around the transition.
    parts = ['# 关键 turn 原文', '', '以下均为真实训练日志输出。turn 显示从 1 开始；原始 turn_step 从 0 开始。Student 无 hint，附带 hint 仅用于 Teacher。', '']
    selected = []
    for e in read_jsonl(KEY / 'key_error_turns.jsonl'):
        if e['rollout_logging_step'] in (20, 110) and e['original']['turn_step'] in (0, 7):
            selected.append(e)
    for e in selected:
        original = e['original']
        match = e.get('matching_full_rollout_turn', {}).get('original')
        parts += [f"## Step {e['rollout_logging_step']} / Turn {original['turn_step']+1} / {original['reason']}", '']
        if match:
            parts += ['任务：' + task_from_prompt(match['input']), '', 'Teacher hint：', block(match.get('online_l1_hint', '')),
                      'Student 输入：', block(match['input'])]
        else:
            parts += [f"游戏来源：`{original['gamefile']}`。未保存匹配 prompt/hint，不补写。"]
        parts += ['Student 输出：', block(original['output']), '原始来源：', block(e['source'])]
    (OUT / '关键turn原文.md').write_text('\n'.join(parts) + '\n')

    # Preserve numeric data even on machines without plotting dependencies.
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 2, figsize=(12, 7.6), constrained_layout=True)
        steps = [r['step'] for r in rows]
        axes[0, 0].plot(steps, [r['whole_response_tokens_mean'] for r in rows])
        axes[0, 0].set(title='Mean response length (all tags/actions included)', ylabel='Tokens per response')
        axes[0, 1].plot(steps, [100*r['empty_ratio'] for r in rows], label='Empty reasoning')
        axes[0, 1].plot(steps, [100*r['format_invalid_ratio'] for r in rows], '--', label='All format errors')
        axes[0, 1].set(title='Format failure rate', ylabel='% of original turns', ylim=(-2, 102))
        axes[0, 1].legend()
        axes[1, 0].plot(steps, [r['reasoning_body_tokens'] for r in rows])
        skipped = [r for r in rows if r['update_skipped']]
        axes[1, 0].scatter([r['step'] for r in skipped], [0]*len(skipped), c='red', s=10, label='Optimizer skipped')
        axes[1, 0].set(title='Supervised body tokens per batch', ylabel='Tokens')
        axes[1, 0].legend()
        for split in ['seen', 'unseen']:
            axes[1, 1].plot([e['step'] for e in evaluations], [100*e[split]['success_rate'] for e in evaluations], 'o-', label=split)
        axes[1, 1].set(title='No-hint held-out success (1024-token budget)', ylabel='Success %', ylim=(0, 50))
        axes[1, 1].legend()
        for ax in axes.flat:
            ax.set_xlabel('Logged step')
            ax.grid(alpha=.2)
        for ax in [axes[0,0], axes[0,1], axes[1,0]]:
            ax.axvline(19, color='gray', linestyle=':', alpha=.6)
        fig.savefig(OUT / 'training_curves.png', dpi=160)
        plt.close(fig)
    except ImportError:
        print('matplotlib unavailable; CSV and summary are complete')
    print(json.dumps({'metrics':len(metrics), 'readable_episodes':len(traces_metadata),
                      'readable_turns':sum(t['turns'] for t in traces_metadata)}, ensure_ascii=False))


if __name__ == '__main__':
    build()
