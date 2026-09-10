# Qwen3-4B：全量 seen / unseen，显式 reasoning 评测

原始 Qwen3-4B，未做本项目微调；`enable_thinking=False`，prompt 显式要求 `<reasoning>...</reasoning>`。使用本地全部可运行的 valid_seen 140 题与 valid_unseen 134 题，每题独立采样一次，无 hint。两个 split 分开计分。

成功率 = 环境原生 won=True 的完整 episode 数 / 对应 split 的全部游戏数。不是 pass@4、不是六类任务宏平均，也不是此前 128 题 × 4 次验证协议。

| Split | 成功 / 总题数 | 成功率 | 严格 reasoning+action 格式 | 截断 | 非法动作 |
|---|---:|---:|---:|---:|---:|
| valid_seen | 41/140 | 29.29% | 5681/5687 | 6 | 376 |
| valid_unseen | 41/134 | 30.60% | 5240/5247 | 6 | 248 |

本次实际耗时 972.3 秒，包含启动/加载与汇总开销。

## 参数与完整 Prompt

8 张 A100 各一份独立 BF16 模型副本，TP=1，max_num_seqs=40，GPU memory utilization=0.55；每题最多 50 步，每步最多 4096 tokens，上下文上限 8192；最近 2 步观察和动作；temperature=0.6、top_p=0.95、top_k=20。关闭物品编号随机化，全部合法动作包含 help。每次生成种子为 42 + episode_id×1000 + 零起算 turn_step。

```text
You are an expert agent operating in the ALFRED Embodied Environment. Your task is to: {task_description} Prior to this step, you have already taken {step_count} step(s). Below are the most recent {history_length} observations and the corresponding actions you took: {action_history} You are now at step {current_step} and your current observation is: {current_observation} Your admissible actions of the current situation are: [{admissible_actions}].  Now it's your turn to take an action. You should first reason step-by-step about the current situation. This reasoning process MUST be enclosed within <reasoning> </reasoning> tags. Once you've finished your reasoning, you should choose an admissible action for current step and present it within <action> </action> tags.
```

首步也使用完整模板：已执行 0 步，历史为空，当前第 1 步。原生 thinking 关闭时，聊天模板输入末尾有空 think 块；格式统计仅计算新生成文本。动作提取保持上一轮逻辑，不修补标签、不重采样、不代选合法动作；缺少唯一 action 时发送 invalid_action 占用一步。

## valid_seen 六类任务

| 任务类型 | 成功 / 题数 | 成功率 |
|---|---:|---:|
| look_at_obj_in_light | 5/13 | 38.46% |
| pick_and_place_simple | 25/35 | 71.43% |
| pick_clean_then_place_in_recep | 3/27 | 11.11% |
| pick_cool_then_place_in_recep | 2/25 | 8.00% |
| pick_heat_then_place_in_recep | 3/16 | 18.75% |
| pick_two_obj_and_place | 3/24 | 12.50% |

[全部逐题结果](valid_seen/ALL_RESULTS.md) · 全部完整轨迹（本地：`/mnt/disk4/zhangboyao/alfworld_base_reasoning_full_eval_20260910/valid_seen/FULL_TRACES.md`） · 逐题 JSONL（本地：`/mnt/disk4/zhangboyao/alfworld_base_reasoning_full_eval_20260910/valid_seen/episodes.jsonl`） · [结果 CSV](valid_seen/results.csv)

## valid_unseen 六类任务

| 任务类型 | 成功 / 题数 | 成功率 |
|---|---:|---:|
| look_at_obj_in_light | 6/18 | 33.33% |
| pick_and_place_simple | 13/24 | 54.17% |
| pick_clean_then_place_in_recep | 9/31 | 29.03% |
| pick_cool_then_place_in_recep | 2/21 | 9.52% |
| pick_heat_then_place_in_recep | 10/23 | 43.48% |
| pick_two_obj_and_place | 1/17 | 5.88% |

[全部逐题结果](valid_unseen/ALL_RESULTS.md) · 全部完整轨迹（本地：`/mnt/disk4/zhangboyao/alfworld_base_reasoning_full_eval_20260910/valid_unseen/FULL_TRACES.md`） · 逐题 JSONL（本地：`/mnt/disk4/zhangboyao/alfworld_base_reasoning_full_eval_20260910/valid_unseen/episodes.jsonl`） · [结果 CSV](valid_unseen/results.csv)

本次覆盖全部可运行验证游戏，但每题只有一次随机采样；不是多 seed 稳健性结论。它与历史 action-only、30 步、64-token 预算的验证协议不同，不能将分差全部归因于 reasoning。数据目录中额外 traj_data.json 不一定具有独立可运行的 game.tw-pddl，本次以全量可运行游戏为分母；没有根据成功、难度或 walkthrough 结果筛选。

发布说明：此目录为结果与配置归档，不包含全部原始轨迹。报告中的本地路径用于原机器复查；上述配置/汇总/原始生成样例保留源内容。所有汇总指标均来自已完成运行，无新增训练或评测。
