# 全量在线 L1 OPD：代码、并发与耗时

快照时间：**2026-09-10 21:21:09 +08:00**。当前训练完成 **3/223 个 trainer step**，容器仍运行，最近保存的完整 checkpoint 是 step1。本文是训练早期记录，不是最终能力报告。

## 本次提交与当前进程的区别

| 内容 | 已运行进程 | 本次发布源码 / 下次启动配置 |
|---|---|---|
| 逐 turn 在线 L1、reasoning prompt、完整训练面板 | 已启用，前三步真实更新 | 提交此前未入库的实现 |
| W&B 完整指标行 | `log(data, step=step)`，SDK 默认 `commit=False` | Hint Ladder 完整指标行使用 `commit=True`；其他 trainer 默认行为保持不变 |
| 整局推理复用 | 未设置开关，有效默认值为 `False` | 新公开配置设置 `keep_engine_awake_during_multiturn=True`，复用仓库已有实现 |
| API 并发 / Student 每批局数 | 64 / 16 | 64 / 16，不改变实验 batch |
| 输出目录与 W&B run | 本文记录的运行身份 | 新输出目录和自动生成的新 W&B run ID |

**本次没有重启、热更新或替换当前训练进程。W&B 修复和复用开关尚未作用于此处的计时，不能声称已经加速。** 新配置已经通过 CPU 测试和 Hydra 配置组合检查，尚未做启用复用后的 8 卡性能验证。

运行时源码基于 `aa7cfe7` 加本地改动；[启动时源码差异](launch_source_changes.patch) 与[启动时文件 SHA256](launch_source_manifest.json) 保留了运行版本的来源。配置的原始有效覆盖值见 [actual_config_sanitized.json](actual_config_sanitized.json)：仅替换 API 地址与密钥文件路径，不包含密钥；它是合并后的 flat overrides，未包含的框架参数仍使用原生默认值。[manifest.json](manifest.json) 单独记录有效的复用开关默认值，避免伪装成启动时显式设置。

## 正在训练什么

1. 原始 Qwen3-4B 用无 hint 的 prompt，完成一批 ALFWorld 多轮交互。
2. 收集该批每个 turn 的公开状态：任务、当前 observation、最近两个已执行动作。
3. 在 Teacher forward 前，以最多 64 个并发请求让 **`glm-5.3-flash`** 生成 L1。相同公开状态在同一个 trainer step 内去重；下一 step 使用独立请求种子和缓存。
4. 同一份当前 Qwen3 权重作为 Teacher，把 L1 插入自己的 prompt，对 **Student 已生成的同一串 response token** 做前向评分。每个 token 看到的是 Student 的对应前缀，Teacher 分布停止梯度。
5. Student 在无 hint 输入下做 top-20 forward KL + tail bucket 自蒸馏。GLM 不生成监督答案，也不参与参数训练。

这不是提前生成 3,553 条固定 hint。这里“在线”表示 hint 根据当前 on-policy 轨迹状态产生；实现上等这一批 Student rollout 完成，再并发生成各 turn 的 hint，并不在每个 Student 动作之前等待 GLM。

目前没有挑选监督时机：成功、失败、绕圈 turn 都进入监督，所有普通 response token（包含 reasoning 和 action）参与 SDL，prompt/padding/特殊 token 不参与。一个 trainer step 包含一批轨迹采集和 actor 更新阶段；它可能包含多个 minibatch 的 optimizer 更新，不能把 223 简写成 223 次单独的 optimizer 调用。

## 实际实验参数

| 参数 | 当前运行值 |
|---|---|
| 模型 | 原始 Qwen3-4B；全部参数训练；BF16 + FSDP；没有加载旧 OPD checkpoint |
| GPU / rollout | 8 × A100 80GB，TP=1；每批 16 个游戏，每个 1 条轨迹，分配后每 GPU 2 局 |
| 训练集 | 本地完整 3,553 个 train 游戏；增加 15 个明确标记的 batch 对齐重复，共 3,568 行，1 epoch / 223 trainer step |
| 验证集 | seen 140、unseen 134；每题 1 次，分开报告，无 hint |
| 验证周期 | 跳过 step0；每 25 step 及最终 step 验证；最后一波可不足 64 个环境，不重复补齐 benchmark 题目 |
| Prompt | 显式 `<reasoning>...</reasoning>` + `<action>...</action>`；原生 `enable_thinking=False` |
| 历史 | 最近 2 次 observation + 已执行 action，不回灌此前 response / reasoning |
| 交互与输出预算 | 最多 50 actions；prompt 4,096、response 4,096、总上下文 8,192 tokens |
| Student / eval 采样 | temperature=0.6，top_p=0.95，top_k=20 |
| 训练目标 | PG=0，SDL=1；Teacher top-20 + 其余词表合并 tail，forward KL |
| 优化 | LR=1e-6；PPO epochs=1；mini batch=256；micro batch=1/GPU；动态 token budget=8,192/GPU；gradient checkpointing |
| GLM | `glm-5.3-flash`，temperature=0.7，max_tokens=4,096，reasoning_effort=low，enable_thinking=False |
| API | 最大并发 64；请求 timeout=180 秒；最多 12 次尝试；重试失败后终止，不以无 hint 结果替代 |
| 模型/数据 seed | 42；API 请求 seed 由公开状态 hash、当前 step 和 42 构成 |
| 保存 | step1、每 25 step、最终 step；保留最近 3 个 actor checkpoint；每个 step 保存 trace |
| 运行环境 | Python `/opt/hintladder/bin/python`；torch 2.10.0、vLLM 0.17.0、transformers 4.57.3、W&B 0.25.0 |

API 并发 64 是 GLM 请求上限，**不是 64 条 Student 轨迹同时解码**。实际 API 活跃数量随排队、完成和重试变化；Student 每批为 16 条轨迹，每条最多串行走 50 turn，因此不能从“8 卡”推断一步会很快。

历史 base 参考为 seen **41/140=29.29%**、unseen **41/134=30.60%**。本次复用了历史结果并跳过初始评测。历史独立评测使用 vLLM 0.19.1 / transformers 5.5.3，与本次原生 verl 的运行时和采样调度有差异；提示文本匹配不能保证完全相同的采样结果。

## GLM 实际看到的内容与 prompt

System prompt（[实际源文件](../../../../configs/experiments/l1_online_full_20260910/l1_prompt.txt)）：

```text
你在帮助另一个智能体完成任务。根据它的任务、当前观察和历史动作，给一个轻量的提示，帮助它结合当前进展想清楚眼前的问题。还在寻找物品时，可以引导它联想物品用途和常见摆放规律；所需物品已经出现时，提醒它围绕眼前资源和任务目标继续思考。把具体地点和具体操作留给它自己推断，不在提示中点名目的地或描述要执行的动作。只输出一两句简短的英文提示。
```

User 内容是 JSON，只有以下三个字段（这里是字段模板，不是具体采样）：

```json
{
  "task": "当前任务",
  "current_observation": "当前环境观察",
  "action_history": ["最近两个已执行动作，开局为空"]
}
```

不提供 Oracle、walkthrough、隐藏物体位置、gamefile、当前 Student response、旧 observation 文本或额外合法动作列表。公开观察本身可能含物体位置；“无 Oracle”不等于删除环境已经公开的信息。生成内容按模型名、结束状态、非空及私有标签检查；代码不保证所有 hint 都满足语义上的轻量要求。

Student 完整模板见 [ALFWORLD_TEMPLATE_REASONING](../../../../agent_system/environments/prompts/alfworld.py)。Teacher 插入点位于任务之后、历史之前，由 [teacher_prompt.py](../../../../hintladder/teacher_prompt.py) 构造；response token IDs 保持一致。

## 实测耗时

下表来自逐 step 原始数值日志；单位均为秒。

| Step | 完整 step | Student rollout | GLM hint 阶段 | Teacher 阶段（含 GLM） | Student log-prob | Actor update | 保存 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 557.35 | 470.18 | 37.28 | 45.68 | 5.39 | 18.51 | 15.29 |
| 2 | 547.97 | 475.59 | 40.58 | 48.49 | 4.68 | 17.31 | 0 |
| 3 | 836.80 | 591.43 | 215.63 | 223.04 | 4.53 | 16.01 | 0 |

`hint_seconds` 是 `teacher_forward` 的子计时，**不能把两列相加**。完整 step 还包含数据整形、reward、trace 写出等工作；以上计时也不包含训练进程的首次模型加载/环境初始化。前三步平均 **647.37 秒 ≈ 10.79 分钟**；只看前两步约 9.21 分钟，不能把它当稳定速度或承诺完成时间。

已确认的耗时来源：

- **Rollout 占主要时间**：第 1/2 步约占完整 step 的 84%/87%。当前每卡只有 2 局，每局跨 turn 串行；原生生成路径每 turn 进入/退出 sharding manager，重复执行权重同步和引擎唤醒/休眠。
- **存在 GLM 长尾请求**：step3 共 439 个不同公开状态，其中 1 个首次尝试出现 `TimeoutError`，第二次成功；该请求耗时 **193.19 秒**，使整批 hint 阶段延长至 **215.63 秒**。其余请求的单请求耗时中位数为约 3.95 秒（包含该慢请求的总体中位数）。这不是并发被改成 1。
- **Step3 rollout 本身也变长**：最大 response 达到 4,096 tokens，截断比例约 0.154%；第 1/2 步最大 response 为 440/407。它与 rollout 延长同时出现，但未独立测量具体贡献。

**尚未量化**权重同步、环境推进、模型解码各自占 rollout 的多少，不能把 470 秒全部算成同步。整局复用只针对重复的推理生命周期开销，不能解决 API 超时，也不能凭静态代码给出加速倍数。

- [完整数值日志：metrics_snapshot.jsonl](metrics_snapshot.jsonl)
- [便于画图的 timing.csv](timing.csv)
- [逐 step API 请求统计与超时记录](hint_request_timing.json)

## W&B 与输出分布

[当前 W&B run](https://wandb.ai/2606478269-ustc/alfworld-l1-online-full-20260910/runs/l1-online-full-seed42-20260910)。核对时本地已完成 step3，W&B history / summary 只提交到 step2。当前代码显式传 `step`，安装的 SDK 默认 `commit=False`，最新行暂存到下一次 step 才提交；这与本地/云端相差一步吻合。

此次修复在 Hint Ladder 一次完整指标记录调用中传 `commit=True`，`Tracking` 仅向 W&B 转发该可选参数，不改变其他 backend 的接口。它结束当前 history row，**不保证网络上传零延迟，也不自动修改已保存的柱状图面板**；面板应选 Line plot，横轴 Step / `training/global_step`。

| Step | 训练批成功率 | 平均 response tokens | Entropy（nat） | Top-1 概率 |
|---|---:|---:|---:|---:|
| 1 | 2/16 = 12.5% | 219.56 | 0.08129 | 0.96109 |
| 2 | 4/16 = 25.0% | 217.13 | 0.09167 | 0.95613 |
| 3 | 4/16 = 25.0% | 225.44 | 0.09075 | 0.95598 |

分布统计基于 Student 已生成 response 的逐 token 前缀，令 `p=softmax(logits/0.6)`：entropy 为 `-sum(p*ln(p))`，top1 为 `max(p)`，再对有效 response mask 求均值。它们使用全词表归一化、**在 top-k/top-p 采样截断之前**计算。不是原始温度 1 的分布，也不是截断重归一化后的采样分布；不能直接对比此前 standalone raw T=1 的表。

本轮记录的是分布汇总，不保存每个 token 的完整词表 logits。普通 token 的 SDL mask 与统计时的 response mask 不完全相同，统计包括有效 response 中的特殊 token。图表里 `actor/entropy_loss` 与这里的 entropy 是同一均值，不代表使用了 entropy bonus。

训练批成功率来自不同的 16 题批次；前三点不能证明训练提高能力。核心能力指标需等完整、无 hint 的 seen/unseen 验证。

## 代码入口与验证

- [online_l1.py](../../../../hintladder/online_l1.py)：公开状态提取、并发、缓存、重试、耗时。
- [hint_ladder_ray_trainer.py](../../../../verl/trainer/ppo/hint_ladder_ray_trainer.py)：在线 Teacher 评分、分布汇总、partial validation waves、trace 与 checkpoint。
- [tracking.py](../../../../verl/utils/tracking.py)：W&B 完整行提交的向后兼容参数。
- [rollout_loop.py](../../../../agent_system/multi_turn_rollout/rollout_loop.py) / [fsdp_workers.py](../../../../verl/workers/fsdp_workers.py)：此前已存在的整局推理作用域，当前提交只在新配置启用。
- [训练配置](../../../../configs/experiments/l1_online_full_20260910/train_full.yaml) / [固定完整面板](../../../../data/game_lists/)。

发布前：**73 tests passed，2 条依赖弃用 warning**，用当前训练镜像中的 `/opt/hintladder/bin/python` 在无网络、无 GPU 的独立容器执行 `pytest tests/hintladder -q`。覆盖在线输入边界、同 step 去重/跨 step 更新、无静默回退、hint 插入、动作解析、134 题最后 6 个验证环境的恢复，以及此次完整行提交与配置组合。

启动前的 [setup_validation.json](setup_validation.json) 另记录：3,553 unique / 3,568 rows；140/134 验证条目；全部 4,131 条历史 base turn 的 prompt 重建匹配；200 条选定 chat-template token 序列一致。这些是数据与 prompt 兼容证据，不是重新跑过 baseline，也不是新性能配置的 GPU 验证。

## 启动与复现

公开 [train_full.yaml](../../../../configs/experiments/l1_online_full_20260910/train_full.yaml) 是**下一次启动使用的复用配置**，API 地址为占位符。先把它与父配置合并成不入库的本地副本，再设置自己的 endpoint、已有密钥文件路径、模型与 W&B 身份。以下命令仅是使用说明，本次提交没有执行它们：

```bash
python - <<'PY'
from pathlib import Path
import yaml
from hintladder.config import load_config
config, _ = load_config('configs/experiments/l1_online_full_20260910/train_full.yaml')
Path('configs/local').mkdir(parents=True, exist_ok=True)
Path('configs/local/l1_online_full.yaml').write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
PY
# 编辑 configs/local/l1_online_full.yaml 中的 API 地址、密钥文件路径及输出目录。
# ALFWORLD_DATA 指向包含 json_2.1.1/ 与 logic/ 的已准备数据目录。
# 通过本地环境设置自己的 WANDB_ENTITY；WANDB_RUN_ID 留空以生成新 run。
python -m hintladder.cli train-student \
  --config configs/local/l1_online_full.yaml --seed 42 \
  --checkpoint /models/Qwen3-4B
```

CLI 使用 8 卡来自配置中的 `trainer.n_gpus_per_node=8`，不是另起 8 个训练进程命令。复现本文旧计时配置时，需将 `actor_rollout_ref.rollout.keep_engine_awake_during_multiturn` 改回 `False`；API 服务延迟、运行环境与采样路径仍会影响耗时。

本地原运行根目录为 `runs/l1_online_full_20260910/`。提交前的源配置另存于该目录的 `publication_source_before_fixes/`，实际启动配置保留在 `train/resolved_config.json`；当前公开 YAML 已不是原配置，不能用它冒充旧运行的恢复配置。模型、checkpoint、完整大体积 traces 和凭据均留在本地。
