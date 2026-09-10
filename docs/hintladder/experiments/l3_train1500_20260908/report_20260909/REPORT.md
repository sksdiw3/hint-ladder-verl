# ALFWorld L3 Student 自蒸馏实验报告

> 状态更新（2026-09-10）：本报告描述归档时状态。文中本轮 checkpoint 已按用户要求删除，不能再从其本地路径恢复；日志与轨迹保留。最新推理评测及可比性说明见[当前实验结论](../../../../../实验结论.md)。

归档日期：2026-09-09，时间均为 UTC+08:00。实验标识：`l3_train1500_20260908`。这是本轮实际运行的结果报告；[此前 step15 快照](../README.md)仍作为历史记录保留。

**结论：当前 L3 纯自蒸馏设置没有取得验证能力提升，反而明显退步。** Seen 成功率由 base 的 **39/512 = 7.62%** 降至 step150 的 **7/512 = 1.37%**；unseen 由 **15/512 = 2.93%** 降至 **1/512 = 0.20%**。计划训练250步，实际恢复分支完成到151步，在152步 rollout 后的格式检查处报错退出；最新已保存、已评测的模型是 **step150**。不能把本轮写成已完成250步或训练成功。

English summary: This single-seed L3-only self-distillation run regressed on fixed, hint-free validation panels. Seen success fell from 39/512 to 7/512, and unseen from 15/512 to 1/512 at checkpoint 150. The resumed branch completed update 151 and failed before update 152. Checkpoint 150 is the latest saved and evaluated model, not the best-performing model.

## 1. 方法和数据

本轮训练的是 **Student**，属于 E2 的单个 L3 训练臂；不是训练 GLM/Hinter，也不是一次冻结模型的 E1 hint 对照实验。

1. 从 ALFWorld train 中按 seed0 固定顺序选择1,500个官方 walkthrough 可回放获胜的游戏。训练面板不是 ALFWorld 官方训练集总量。
2. 训练前用 API 模型 ID `glm-5.3-flash` 为每题生成一条固定 L3 hint，1,500条全部完成并通过当前程序检查。GLM 输入含初始观察、初始动作空间、目标、隐藏事实和官方 walkthrough；这是有意给 Teacher 的特权信息。
3. Student 在没有 hint 的观察下交互。随后，以同一份当前权重作为 Teacher，在上下文加入对应 L3，计算 Student 实际响应 token 的分布目标。Teacher 不另采样一条“正确轨迹”。
4. 使用 top-20 forward KL 加 tail bucket 更新 Student。PG=0、SDL=1；没有任务 reward 的直接策略梯度项，也没有 Hinter reward 或 Hinter GRPO。环境 reward 和优势仍在上游计算、记录。
5. 训练期间不再调用 GLM。训练后评测也是不带 hint 的 Student，衡量能否把指导转化为独立完成任务的能力。

数据面板与完整参数来源：[1,500题列表](../../../../../data/game_lists/alfworld_train_1500_seed0.txt)、[原始实际解析配置](../actual_config.json)、[训练公开配置](../../../../../configs/experiments/l3_train1500/train.yaml)、[数据/hint 哈希与初始快照](../snapshot.json)。12条真实 hint 和 GLM 输入已经归档在[中间实验目录](../hint_examples.md)及其[JSONL](../hint_examples.jsonl)。程序通过不代表 hint 事实和策略全部正确。

## 2. 主要实验参数

| 项目 | 设置 |
|---|---|
| 基座 | 原始 Qwen3-4B；未先做任务 SFT/RFT；BF16 |
| 硬件 / 并行 | 8 × NVIDIA A100 SXM4 80GB；FSDP；vLLM sync，TP=1 |
| 训练集 | 1,500个固定游戏；Pick 341、Pick2 359、Clean 265、Heat 191、Cool 225、Look 119 |
| Hint | 每题离线固定 L3；GLM 并发8，temperature=0.7，响应预算4096 token，最终 hint 上限140个英文词，最多3次尝试 |
| Student 每次更新 | 16题 × 8条 rollout = 128 episodes；native rollout.n=1 |
| 优化目标 | 纯 SDL；PG=0，SDL=1；top20 forward KL + tail bucket；普通响应 token，special tokens masked |
| 归一化 / 优化 | response_token_mean；LR=1e-6；PPO epochs=1；mini-batch=256个 step samples；动态 micro-batch |
| 交互预算 | 每局最多30个动作；最近2步历史；prompt4096、response64 token |
| 输出 | action-tag-only；enable_thinking=False；生成 response 中禁止 think 标签 |
| 训练采样 | temperature=1.0，top-p=1，top-k=-1 |
| 验证采样 | temperature=0.4，top-p=1，top-k=-1；seen/unseen 各128题，每题4次 |
| 验证 / 保存 | 训练前一次；之后每25次更新验证、保存；每个输出目录保留最近2份 actor checkpoint |
| 计划 / 完成 | 计划250次更新；恢复分支最终完成151次更新，最近完整 checkpoint150 |
| 其他 | entropy=0；额外 KL 关闭；invalid-action penalty 配置0.1，但PG系数0 |
| 运行 | Ray48 CPU，object store2GiB；vLLM memory utilization=0.3；eager=true；torch.compile=false；无CPU offload |

完整启动顺序见[初始实验说明](../README.md#新环境上的运行顺序)。从100步恢复时仍使用8卡，恢复模型、优化器、调度器、RNG、dataloader与 SDL token budget，下一次更新为101；新建输出目录和 W&B run，保持独立日志。已评测过100步，所以恢复时 `val_before_train=false`。部署/恢复字段的全部变化见[实际配置差异](logs/resume100_effective_config_diff.json)，恢复后的首次更新证据见[restart_verified](logs/resume100_restart_verified.json)。

## 3. 成功率怎么算

每个 split 固定128个游戏，每题采样4次，共512条完整 episode。由环境最终 `won` 判断完成目标；验证原始日志中 `episode_rewards=10` 为成功、0为失败。

`success_rate = 成功的 episode 数 / 512`。

因为每题采样次数相同，这也等于“各题四次成功率的平均”，可称 Avg@4。它**不是**四次里任意一次成功即算过的 pass@4，也不是六种任务类型成功率的简单平均。seen/unseen 分开报告，不混成一个没有分母说明的 Avg。

原始验证 JSONL 一行是一个动作步。必须先按 `traj_uid` 分组，再按 `turn_step` 排序，每条 episode 只计一次；`score`/`episode_rewards` 在逐步记录里重复，不能相加或直接按行平均。本次重新检查了 **14个验证文件、7,168条 episode**：每次验证均为128题×4次，步序连续，逐局成功数与训练指标日志完全一致。[validation_summary.jsonl](validation_summary.jsonl)含每次验证的总数、六类分组及每题4次的成功数，并记录原始文件 SHA-256。

W&B 主要看 `val/valid_seen/success_rate` 与 `val/valid_unseen/success_rate`。`episode/success_rate` 是当次128条训练 rollout 的成功率，对应该次参数更新之前的策略；题目批次和采样温度与固定验证不同。`actor/sdl_loss` 和 `skillsd/teacher_student_gap_mean` 分别是蒸馏损失和两种上下文下的 token 对数概率差，不能代替成功率。

## 4. 全部验证结果

| 权重 step | 运行来源 | Seen 成功/总数 | Seen 成功率 | Unseen 成功/总数 | Unseen 成功率 |
|---|---|---|---|---|---|
| 0：base | original | 39/512 | 7.62% | 15/512 | 2.93% |
| 25 | original | 1/512 | 0.20% | 0/512 | 0.00% |
| 50 | original | 5/512 | 0.98% | 1/512 | 0.20% |
| 75 | original | 9/512 | 1.76% | 0/512 | 0.00% |
| 100 | original | 10/512 | 1.95% | 0/512 | 0.00% |
| 125 | resume100 | 9/512 | 1.76% | 4/512 | 0.78% |
| 150 | resume100 | 7/512 | 1.37% | 1/512 | 0.20% |

Step150 比 base：seen **−6.25个百分点**，unseen **−2.734375个百分点**。训练后各次验证均未超过 base。若只在训练过的 checkpoint 中选，seen 最高是100步、unseen 最高是125步；这两个峰值来自不同权重，不能合并声称某个 checkpoint 达到了两项最高成绩。150步是最近模型，不是最佳模型。

SDL loss 从首次更新约1.0315降到恢复分支最后一次更新约0.07385，但任务能力没有随之提高。最后一条训练 batch 成功率为14/128=10.94%；它不能覆盖或推翻固定验证的低分。恢复运行最后20次训练 batch 的成功率均值约5.43%，也不是额外的全量验证结果。

## 5. 两次运行与停止原因

| 运行 | 实际完成范围 | 最后完成点 / 停止 | 产物与解释 |
|---|---|---|---|
| original | 更新1–116，外加step0验证 | 9月9日07:11:09 首个 worker 被 Ray 记录退出 | 最后保存100步；worker stderr 报 CPython `none_dealloc` |
| resume100 | 从100恢复，重新执行101–151 | 9月9日14:15:31 supervisor 记录失败，returncode=1 | 152步 rollout 后检查 response 失败；最后保存并评测150步 |

原运行101–116与恢复运行101–116是两次不同采样/执行，不能把它们无标识拼接。最终模型路径为 original1–100 → resume101–151；本归档分别保留两个完整指标文件。

第一次直接错误为：

```text
Fatal Python error: none_dealloc: deallocating None: bug likely caused by a refcount error in a C extension
```

证据：[首个失败 worker 完整 stderr](logs/original_first_failed_worker.log)、[带时间的 Ray worker 退出事件](logs/original_ray_failure_events.json)。该 worker 在 `generate_sequences` 调用栈上崩溃，Ray 随后报告连接 EOF。通用 Ray 提示列出的 OOM/强制停止等是候选解释，不是本次已经证实的根因；本归档不能确定具体哪个 C extension 出错。重新启动也不代表修复了该底层问题。

第二次主异常为：

```text
ray.exceptions.RayTaskError(ValueError)
ValueError: Student emitted forbidden thinking tags
```

证据：[恢复运行完整训练日志](logs/resume100_training.log)、[退出状态](logs/resume100_status.json)、[检查代码](../../../../../verl/trainer/ppo/hint_ladder_ray_trainer.py)。在 rollout 返回后、Teacher 评分和参数更新之前，训练器遍历解码后的 response，只要发现 `<think>` 或 `</think>` 就直接抛错。因此完成151步，而非152步。日志里的部分 ALFWorld worker SIGABRT 与环境清理同时出现，应和这个主异常区分。

本归档没有捕获到触发退出的具体 response、gamefile或出现数量，不能补写一条“152步坏样本”。已有轨迹 prompt 中聊天模板自动附带的空 think 前缀也不等于 response 违规。后续修复需要保留真实坏样本，再判断如何处理生成格式和训练契约。

普通更新耗时的中位数：original约232.4秒，resume约226.4秒；每25步还有验证和保存开销。停止后检查8张GPU均仅占1MiB、利用率0，容器只剩 `sleep`。本报告整理过程未启动新的评测或训练。

## 6. Base / 训练后完整中英文轨迹

**[打开四组完整中英文对照](trajectories_zh_en.md)**，或下载[逐 episode 原始 JSONL](trajectories.jsonl)。共4个验证游戏、8条 episode、161个决策步。包含完整题目、每步动作前观察、原始英文输出、中文释义，以及 JSONL 中完整 prompt、逐步可行动作列表、环境返回的动作合法性字段、源文件和原始行号。

| 同一个验证任务 | Split | 该题全部4次：base → step150 | 展示的轨迹 |
|---|---|---|---|
| 清洗汤勺并放到餐桌 | seen | 4/4 → 0/4 | base12步成功；训练后30步失败 |
| 借台灯查看碗 | seen | 0/4 → 3/4 | base30步失败；训练后18步成功 |
| 把铅笔放到置物架 | unseen | 3/4 → 0/4 | base8步成功；训练后30步失败 |
| 借台灯查看马克杯 | unseen | 0/4 → 1/4 | base30步失败；训练后3步成功 |

这是按成败类型选择的定性样例，不是随机样本。游戏按完整路径匹配，指定组合内按 gamefile、traj_uid 字典序确定样例；没有把不同 trial 的同名题目当成同题。所选两条进步轨迹不代表总体效果，总体结论应以512条/split的验证结果为准。

可观察到训练后有“已找到目标/已拿到物品，却持续移动、不执行清洗或放置”的失败；base 也存在反复查看、对不存在或未编号对象发动作等问题。局部行为变化是证据，尚不能推出单一训练根因。中文是事后翻译；既不是模型隐藏思维，也没有送给模型。原始日志未保存最后一个动作执行后的终止观察，本报告不虚构那条观察。

## 7. 结论边界与后续审查

当前有证据支持：本配置下任务能力退步、训练运行确实完成了参数更新、两次中止的直接错误不同。尚没有证据支持“L3 hint 普遍有效”“蒸馏已学会任务”，或“低分一定由历史长度/response长度导致”。一个seed、一个训练臂，不能推出所有 L3 自蒸馏均无效。

建议后续先做静态审查和最小对照设计：检查 Teacher hint 的事实质量和分布目标是否有用；核查 PG=0 的梯度路径、token 对齐和损失聚合；审查发现目标后不执行操作的行为变化；为格式失败保存坏样本。PG=0、同权重 Teacher、hint 语义错误都只是需要验证的解释，目前没有消融将它们分别定责。与论文比较还需对齐是否先做任务SFT/RFT、游戏面板、thinking、动作预算和采样方式；不能把这里的原始4B成功率与其他论文训练后的结果当作同一实验的前后值。

## 8. 日志、checkpoint 与可复查性

| 文件 | 内容 |
|---|---|
| [original_metrics.jsonl](logs/original_metrics.jsonl) | 原样复制：step0–116，共117条指标记录 |
| [resume100_metrics.jsonl](logs/resume100_metrics.jsonl) | 原样复制：step101–151，共51条；不要与旧分支重叠步混合 |
| [original_trainer_stdout.log](logs/original_trainer_stdout.log) | 原运行活跃 Ray trainer 的 stdout；原外层 training.log 曾缓冲停更，因此使用实际活跃日志 |
| [original_first_failed_worker.log](logs/original_first_failed_worker.log) | 第一次失败 worker 的完整 stderr |
| [original_ray_failure_events.json](logs/original_ray_failure_events.json) | 第一次 worker 退出时间及对应源行号；明确是摘录 |
| [resume100_training.log](logs/resume100_training.log) | 恢复运行的完整外层 stdout/stderr |
| [validation_summary.jsonl](validation_summary.jsonl) | 14次 split 评测重算结果，含每题成功数与六类统计 |
| [manifest.json](manifest.json) | 源文件与公开文件的 SHA-256、导出时间、日志转换方式、轨迹数量 |
| [build_archive.py](build_archive.py) | CPU归档/重算脚本；依赖本地原始 runs/，不会启动训练或API |

控制台日志移除 ANSI 颜色、将回车转为换行，并执行凭据格式过滤；本次过滤命中0项。指标 JSONL 与三个恢复状态/配置/验证 JSON 保持原始字节。没有上传整个 Ray 临时目录、模型权重、凭据或所有逐步 trace；四组轨迹中的 `raw` 字段保留源 JSON 记录内容，其他字段是新增的来源标记和中文翻译。大量验证源 trace 保留在本地，可用清单哈希核对。

截至本次核查，原目录完整 actor checkpoint 为75、100；恢复目录为125、150，均含恢复所需 data 与 budget。25、50只剩少量元数据目录，不应当作可恢复模型。它们没有被纳入 Git。最新模型本地位置：

```text
runs/l3_train1500_20260908/resume100_20260909_1041/train/global_step_150
```

本次发布只新增报告/证据及文档入口，不修改训练逻辑。验证包括7,168条验证 episode 的重算、8条导出 episode 的源行逐字段核对、161步连续性与中文对象编号核对、JSON解析、文件哈希、文档链接和发布文件的凭据模式检查；不以文档发布为由重跑GPU实验。

W&B：[原运行](https://wandb.ai/2606478269-ustc/alfworld-l3-train1500-20260908/runs/l3-train1500-seed0-20260908) / [从100步恢复](https://wandb.ai/2606478269-ustc/alfworld-l3-train1500-20260908/runs/l3-train1500-resume100-20260909-1041)。W&B 可见性由账户设置决定，上述固定日志可以直接在仓库中阅读。
