# ALFWorld 训练集 10 题：Qwen3-4B 原生 thinking

完成 10 题，成功 7/10；共 278 步。成功以 ALFWorld 原生 `won` 为准，不依据模型自述。

这是从训练集随机抽取的 10 题演示，不是标准验证集评测，不能把该成功率直接与论文对比。

模型为原始 Qwen3-4B。仅 `enable_thinking=True`；用户提示中没有 `<think>`、`/think` 或先分析再行动的要求。观察和任务来自原生环境，另提供最近两步观察/动作、合法动作和动作输出格式。无 system 消息，无 hint。

动作格式要求的原文：

```text
Choose exactly one admissible action for the current step and present it within <action> </action> tags.
```

配置：固定抽样 seed=42，从本地完整 train 的 3553 个游戏均匀无放回抽样；每题单次 rollout，最多 50 动作；每轮生成上限 4096 tokens；temperature=0.6，top_p=0.95，top_k=20；上下文上限 8192；历史仅保留最近两步观察和动作，不把之前的思考重新喂回；关闭物品编号随机化；单张 A100 80GB、BF16、vLLM TP=1。

解析只从原生 `</think>` 之后的最终回答提取唯一 `<action>`，避免执行思考中举例的动作；不强制思考内容非空。若缺失动作，记录错误并向环境发送 `invalid_action`，不代选有效动作、不重采样。

输出截断 1 次；动作解析错误 1 次；包含完整 think 块的响应 277/278。

| ID | 任务 | 成功 | 动作数 | 完整轨迹 |
|---|---|---|---:|---|
| 01 | 加热盘子并放进冰箱 | 是 | 24 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_native_think10_20260909/episodes/01.md`） |
| 02 | 把蜡烛放到台面 | 否 | 50 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_native_think10_20260909/episodes/02.md`） |
| 03 | 用台灯查看 CD | 是 | 11 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_native_think10_20260909/episodes/03.md`） |
| 04 | 把两个钥匙扣放到扶手椅 | 否 | 50 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_native_think10_20260909/episodes/04.md`） |
| 05 | 把洗净的碗放到餐桌 | 否 | 50 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_native_think10_20260909/episodes/05.md`） |
| 06 | 把纸巾盒放到马桶 | 是 | 24 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_native_think10_20260909/episodes/06.md`） |
| 07 | 把洗手液瓶放到马桶 | 是 | 28 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_native_think10_20260909/episodes/07.md`） |
| 08 | 把信用卡放到架子 | 是 | 4 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_native_think10_20260909/episodes/08.md`） |
| 09 | 把两条手巾放到台面 | 是 | 32 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_native_think10_20260909/episodes/09.md`） |
| 10 | 把 CD 放到保险柜 | 是 | 5 | 查看（本地：`/mnt/disk4/zhangboyao/alfworld_native_think10_20260909/episodes/10.md`） |

文件：`FULL_TRACES.md` 为全部逐步全文；`episodes.jsonl` 每行一个完整 episode；`turns.jsonl` 每行一个动作回合，保留完整输入、生成 token IDs、未经修改的输出、执行动作、动作后观察及原生成功标志；`initial_prompts.json` 可核对最初喂入模型的文字；`selection.json` 保存固定抽样与游戏哈希；`config.json` / `runtime.json` 保存参数和依赖版本。

发布说明：此目录为结果与配置归档，不包含全部原始轨迹。报告中的本地路径用于原机器复查；上述配置/汇总/原始生成样例保留源内容。所有汇总指标均来自已完成运行，无新增训练或评测。
