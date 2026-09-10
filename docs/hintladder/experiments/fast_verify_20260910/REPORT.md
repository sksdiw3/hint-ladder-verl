# 用户提供的 fast 版本：五步训练验收

代码来源：`/mnt/disk4/zhangboyao/hint-ladder-verl-fast`，用户提交 `1decc33`，基于 `592c9ee`。目标是验证5个真实 trainer step及最后一次完整 seen/unseen 评测，不自动转入223步全量训练。

## 启动前检查

- 在已验证的 `hintladder-runtime:verified-20260908` 镜像中运行 `pytest tests/hintladder -q`：**85 passed**，两项依赖弃用警告。
- 同一 GLM 网关、相同10个历史失败状态：**10/10 首次返回 stop**，型号均为 `glm-5.3-flash`，正文28–41个英文词，总completion139–557，2.90–7.76秒。该样本按历史失败选择，不代表全量成功率或质量评测。见 [api_preflight.jsonl](api_preflight.jsonl)。
- GLM保持 thinking 开启、reasoning_effort=low；未采用不可用的 disabled 模式。

## 相对提供版本的必要修复

1. `L0_FAILED` 行除了不插入 hint，还将既有 `sdl_special_token_keep_mask` 置零。测试通过原生 top-k forward KL 和反向传播验证：学生权重变化后，失败行梯度仍为零，其余行仍有梯度。
2. Teacher 阶段等待所有已提交预取任务完成，包含已结束环境多出的状态；`begin_step` 拒绝带未完成请求跨步。训练退出时关闭线程池。
3. thinking=true 显式发送 `thinking: {type: enabled}`；实际返回不同模型时直接报错，不作为 L0 降级。

未改 worker、基础 PPO trainer、rollout loop、环境或 SDL 数学实现。保留提供版本的失败预算 `min(max_count, max(1, floor(states * ratio)))`，当前ratio=1%、max_count=10；其统计分母是当前训练批次所需的去重公开状态。该规则对不足100个状态至少允许1个，与早先严格floor版本不同。

## 本次参数

| 参数 | 值 |
|---|---|
| 模型 / GPU | 原始 Qwen3-4B / 8×A100 80GB |
| 训练面板 | 全量3553个ALFWorld训练游戏，补齐到整批；仅执行前5个trainer step |
| 每步轨迹 | 16个游戏×8次采样=128局 |
| 学生协议 | 原生thinking关闭，显式reasoning/action prompt，50动作，历史2轮，prompt4096，response1024 |
| 采样 | temperature0.6 / top_p0.95 / top_k20 |
| 教师 / hint | 当前学生权重前向评分；GLM在线生成无Oracle L1；学生rollout和评测不接收hint |
| GLM | thinking enabled / effort low / max_tokens768 / 并发128 / timeout25s / retries4 |
| 目标 | PG=0 / SDL=1 / top20 forward KL + tail / LR1e-6 |
| 批量 | PPO mini batch256、1 epoch；评分token16384、更新token12288 |
| 提速 | 持久vLLM作用域、CUDA graph、逐turn预取hint；persist_requests=false |
| 评测 / 保存 | 跳过初始评测；step5完整seen140、unseen134；step1和5保存 |
| W&B | project `alfworld-l1-fast-verify-20260910`，run `fast-5step-seed42-20260910` |

输出：`runs/adopt_fast_20260910/train`。本地启动配置：`configs/local/fast_verify_5step.yaml`，仅本地保存endpoint与凭据文件路径；公开配置见 [config_sanitized.json](config_sanitized.json)。API key不进入公开产物。

## 实际结果

已完成 **5/5** 个真实 trainer step、完整 seen/unseen 评测和 checkpoint 保存。容器正常退出（exit code 0，OOMKilled=false），8张GPU已释放；最近 checkpoint 为 step5。

实际训练源码提交为 `6b5e2b8`；后续提交只更新实验文档与证据。结束时核对28个源码文件，其哈希与启动记录完全一致。容器从2026-09-10 23:59:20运行到2026-09-11 00:44:10（UTC+08），包括初始化、5步训练、评测及退出，共44分50秒。

| step | 整步秒 | rollout秒 | hint等待秒 | Teacher前向秒 | 参数更新秒 | 失败状态 | 预取miss |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 506.3 | 248.2 | 0.171 | 52.7 | 141.1 | 0 | 0 |
| 2 | 462.0 | 225.8 | 0.165 | 51.5 | 139.1 | 0 | 0 |
| 3 | 422.5 | 218.1 | 0.160 | 46.0 | 117.3 | 0 | 0 |
| 4 | 399.4 | 201.5 | 0.166 | 44.2 | 114.1 | 0 | 0 |
| 5 | 773.4 | 196.2 | 0.134 | 39.1 | 98.2 | 1 | 0 |

每步128局。Teacher前向列已经包含hint等待，不能再相加。最后一步还包含完整评测和保存，必须单独扣除后比较训练耗时。

原始 [metrics.jsonl](metrics.jsonl)、[timing.csv](timing.csv)、[状态](status.json)、[启动源码校验](launch_source_manifest.json)。

[W&B run](https://wandb.ai/2606478269-ustc/alfworld-l1-fast-verify-20260910/runs/fast-5step-seed42-20260910)。

训练进程正常退出后，对该run的本地日志补做一次`wandb sync`；云端状态已核对为 **finished**，step5及seen/unseen指标与本地一致，见[wandb_status.json](wandb_status.json)。

### 耗时和稳定性

扣除评测与checkpoint保存，5步分别为 **490.3 / 462.0 / 422.5 / 399.4 / 369.2秒**，平均 **428.7秒（7.14分钟）/step**。第5步整步773.4秒，其中完整seen/unseen评测389.4秒、保存14.8秒。

- 每步128局。逐turn请求预取与学生rollout重叠，Teacher前额外hint等待仅 **0.134–0.171秒**，5步均无预取miss。单个成功请求的每步p95为6.70–7.42秒，包含该请求重试耗时，不能把接近零的末尾等待误认为API本身只需要0.1秒。
- 5步所需的去重hint状态共 **8,838**，共33次额外重试。第5步1个状态4次响应校验均失败，对应1条训练行记为`L0_FAILED`，其SDL监督掩码为零；未超过本步10个状态的预算，训练继续完成。该状态累计等待52.22秒，但已被预取覆盖。
- 提供版本的错误记录只保存异常类别，此次4次均为`ValueError`，未保存具体校验分支或原始返回。因此不能从现有日志断定究竟是截断、空正文还是其他响应校验失败；没有HTTP错误码证据。完整可用记录见[trace_audit.json](trace_audit.json)。
- `hint_requests`统计当前训练批次所需的去重状态，不包含未用于训练的额外预取状态，也不是包含重试的HTTP调用总数。并发128为配置上限，本次没有测量实际最大并发。
- 无OOM，所有5步SDL loss、grad norm均有限且非零。报告的最高GPU分配内存为 **76.92 GiB**，显存余量有限，本次结果不能证明增大token预算仍然安全。

此前暂停的`l1_online_full_20260910`常规step2–6平均661.4秒，每步16局；本次常规step2–4平均427.9秒，每步128局。每步轨迹量扩大8倍，同时平均整步时间下降约35%。但输出上限也从4096降到1024，并改变了图执行、引擎休眠和请求参数，因此这不是相同预算下的单变量加速实验。主要实现变化是持久vLLM作用域、CUDA graph、hint预取与更大的评分/更新token预算。

### 最终无hint评测

以step5权重评测，每题1次，按环境episode reward是否大于0判断成功，逐`traj_uid`去重；不是按turn数平均，也不是按六类任务宏平均。

| split | 不同题目 / 轨迹 | 成功数 | 成功率 | 保存turn行数 |
|---|---:|---:|---:|---:|
| Seen | 140 / 140 | 52 | **37.14%** | 5,288 |
| Unseen | 134 / 134 | 57 | **42.54%** | 5,013 |

逐轨迹重算结果与trainer记录的`val/<split>/text/success/mean@1`一致；所有评测输入均未包含`<private_teacher_note>`，验证阶段也没有新增hint请求。核对结果见[trace_audit.json](trace_audit.json)。

历史base的29.29% / 30.60%使用4096-token输出上限和不同运行时；本次为1024。此次跳过了初始评测，所以没有完全相同协议的step0对照，**不能将差值直接认定为训练带来的提升**。训练批成功率从6.25%到46.875%来自不同游戏批次，同样不能替代固定验证集的对照。

本次证明这套配置可以完成真实rollout、在线hint、Teacher前向、反向更新、完整评测和保存；未自动启动223步训练。全量数据面板用于采样，但这里只执行5个trainer step。

### 本地完整产物

- checkpoint：`runs/adopt_fast_20260910/train/global_step_5`，同时保留step1，各约32GiB；权重未提交Git。
- 第5步训练trace：`runs/adopt_fast_20260910/train/rollouts/5.jsonl`，128局、4,456个turn，含每行hint及失败标记；学生输入本身不含hint。
- 完整评测trace：`runs/adopt_fast_20260910/train/validation/{valid_seen,valid_unseen}/5.jsonl`。
- 容器完整console：`runs/adopt_fast_20260910/console.log`。公开仓库保存脱敏配置、逐步指标和审计结果；本地凭据与模型文件未提交。
