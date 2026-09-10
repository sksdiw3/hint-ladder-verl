# ALFWorld 训练集 10 题：Qwen3-4B 关闭原生 thinking + 用户指定完整提示词

完成 10 题，成功 6/10；共 304 步。成功以 ALFWorld 原生 `won` 为准，不依据模型自述。

这是从训练集随机抽取的 10 题演示，不是标准验证集评测，不能把该成功率直接与论文对比。

模型为原始 Qwen3-4B。设置 `enable_thinking=False`；用户提示明确要求 `<think>...</think>`。模板在输入末尾预填空 think 块，生成响应单独原样保存。观察和任务来自原生环境，另提供最近两步观察/动作、合法动作和动作输出格式。无 system 消息，无 hint。

完整提示词模板原文：

```text
You are an expert agent operating in the ALFRED Embodied Environment. Your task is to: {task_description} Prior to this step, you have already taken {step_count} step(s). Below are the most recent {history_length} observations and the corresponding actions you took: {action_history} You are now at step {current_step} and your current observation is: {current_observation} Your admissible actions of the current situation are: [{admissible_actions}].  Now it's your turn to take an action. You should first reason step-by-step about the current situation. This reasoning process MUST be enclosed within <think> </think> tags. Once you've finished your reasoning, you should choose an admissible action for current step and present it within <action> </action> tags.
```

配置：固定抽样 seed=42，从本地完整 train 的 3553 个游戏均匀无放回抽样；每题单次 rollout，最多 50 动作；每轮生成上限 4096 tokens；temperature=0.6，top_p=0.95，top_k=20；上下文上限 8192；历史仅保留最近两步观察和动作，不把之前的思考重新喂回；关闭物品编号随机化；单张 A100 80GB、BF16、vLLM TP=1。

解析保持与上一轮一致：存在 `</think>` 时从最后一个关闭标签之后提取唯一 `<action>`；有开标签但没有闭标签时不提取动作；没有 think 标签时从全文提取。不会修补标签，也不强制思考内容非空。若缺失动作，记录错误并向环境发送 `invalid_action`，不代选有效动作、不重采样。

输出截断 0 次；动作解析错误 0 次；包含完整 think 块的响应 0/304。

| ID | 任务 | 成功 | 动作数 | 完整轨迹 |
|---|---|---|---:|---|
| 01 | 加热盘子并放进冰箱 | 否 | 50 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_fullprompt_think10_20260910/episodes/01.md`） |
| 02 | 把蜡烛放到台面 | 否 | 50 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_fullprompt_think10_20260910/episodes/02.md`） |
| 03 | 用台灯查看 CD | 是 | 23 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_fullprompt_think10_20260910/episodes/03.md`） |
| 04 | 把两个钥匙扣放到扶手椅 | 否 | 50 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_fullprompt_think10_20260910/episodes/04.md`） |
| 05 | 把洗净的碗放到餐桌 | 否 | 50 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_fullprompt_think10_20260910/episodes/05.md`） |
| 06 | 把纸巾盒放到马桶 | 是 | 17 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_fullprompt_think10_20260910/episodes/06.md`） |
| 07 | 把洗手液瓶放到马桶 | 是 | 4 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_fullprompt_think10_20260910/episodes/07.md`） |
| 08 | 把信用卡放到架子 | 是 | 4 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_fullprompt_think10_20260910/episodes/08.md`） |
| 09 | 把两条手巾放到台面 | 是 | 26 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_fullprompt_think10_20260910/episodes/09.md`） |
| 10 | 把 CD 放到保险柜 | 是 | 30 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_fullprompt_think10_20260910/episodes/10.md`） |

文件：`FULL_TRACES.md` 为全部逐步全文；`episodes.jsonl` 每行一个完整 episode；`turns.jsonl` 每行一个动作回合，保留完整输入、生成 token IDs、未经修改的输出、执行动作、动作后观察及原生成功标志；`initial_prompts.json` 可核对最初喂入模型的文字；`selection.json` 保存固定抽样与游戏哈希；`config.json` / `runtime.json` 保存参数和依赖版本。

## 与上轮原生 thinking 对照

同样的 10 道 train 游戏，初始观察和动作空间逐题一致；模型、种子、采样参数、历史和预算相同。原生 thinking：7/10；本轮：6/10。本轮换用用户指定完整提示词，角色说明和历史排版也有变化，不能把差异只归因于 thinking 开关。仅一次配对采样，不能据此认定哪种方案普遍更优。

| ID | 原生 thinking 成功 / 步数 | 关闭原生 + 提示 think 成功 / 步数 |
|---|---|---|
| 1 | True / 24 | False / 50 |
| 2 | False / 50 | False / 50 |
| 3 | True / 11 | True / 23 |
| 4 | False / 50 | False / 50 |
| 5 | False / 50 | False / 50 |
| 6 | True / 24 | True / 17 |
| 7 | True / 28 | True / 4 |
| 8 | True / 4 | True / 4 |
| 9 | True / 32 | True / 26 |
| 10 | True / 5 | True / 30 |

原始生成格式统计（不包括输入中预填的空 think）：

```json
{
  "generated_open_think": 0,
  "generated_close_think": 29,
  "close_without_open": 29,
  "neither_think_tag": 275,
  "complete_reasoning_tag": 280,
  "direct_action_only": 0,
  "leading_token_counts": {
    "27": 270,
    "40": 5,
    "151668": 29
  },
  "mutually_exclusive_categories": {
    "other_text_and_or_action": 5,
    "close_without_open": 29,
    "reasoning_tag": 270
  }
}
```

没有完整 think 标签不等于没有分析文字；请以 raw_response 为准。此推理实验不施加格式奖励，也不要求完整 think 标签才能执行 action。

发布说明：此目录为结果与配置归档，不包含全部原始轨迹。报告中的本地路径用于原机器复查；上述配置/汇总/原始生成样例保留源内容。所有汇总指标均来自已完成运行，无新增训练或评测。
