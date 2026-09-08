# ALFWorld：1,500 题、L3、8 卡 Student 自蒸馏

本目录归档 **2026-09-08 23:59:37 +08:00** 的运行快照。完整训练计划为 250 次更新；本快照只记录到 **step 15**，没有 step 25 的训练后验证，不能据此宣称任务能力提升。

## 本次在训练什么

这是一个 L3 Student 训练臂，使用原生 verl/FSDP/vLLM。先用 GLM 为每个训练游戏生成固定 L3 hint，再训练 Student；训练期间不调用 GLM，也不在线生成/改写 hint。

每个更新先由 Student 在 **不含 hint** 的上下文中完成 rollout。随后，同一份当前模型权重作为 Teacher，在原来的每步上下文中插入该游戏的私有 L3 hint，对 **Student 已生成的原始响应 token** 做前向评分。Teacher 不另采一条轨迹。Student 根据带 hint 的 Teacher 分布做 top-k forward KL 自蒸馏。

Teacher/Student 共享当前权重来源，Teacher targets 在优化前计算；本次 PG=0、SDL=1，没有训练 Hinter，也没有添加 Hinter reward/GRPO。环境成功 reward 用于记录和上游 batch/优势计算；是否有意外梯度路径是审查重点。

## 数据、hint 与选择规则

- 从 ALFWorld train 游戏按 seed 0 的固定候选顺序，取最早 1,500 个官方 walkthrough 可回放获胜的任务。已选 panel 见 [alfworld_train_1500_seed0.txt](../../../../data/game_lists/alfworld_train_1500_seed0.txt)。这不是“官方训练集只有 1,500 条”。
- 任务分布：Pick 341、Pick2 359、Clean 265、Heat 191、Cool 225、Look 119。
- 1,500 个训练游戏 walkthrough 全部验证通过；对应 1,500 条 L3 通过当前程序检查。源 bank 与 panel 的 SHA-256 在 [snapshot.json](snapshot.json)。
- API 模型 ID `glm-5.3-flash`；并发 8；temperature 0.7；响应上限 4,096 token；每条最多 3 次尝试；prompt version `v1`；最终 hint 上限 **140 个英文词**。4,096 是生成 API 的响应预算，不是 Student 的输出预算。
- 首批 16 条 pilot hint 经源记录一致性核对后复用；其余离线生成。有效 hint 支持断点复用，接口失败不会替换成占位文本。
- 验证固定为 seen 128 题、unseen 128 题，各题 4 次采样；不提供任何 hint。训练 panel 与两组验证按完整 gamefile 区分。

### GLM 看到的内容

`system` 消息来自 [generation_messages](../../../../hintladder/ladder.py)：要求不超过 140 词的 oracle 指导，明确写出编号目标对象、位置、目标容器和提供的初始状态，输出自然语言正文。

`user` 消息含五个字段：`initial_observation`、`initial_admissible_commands`、`goal_text`、`hidden_facts`、`walkthrough`。因此 L3 有意使用隐藏答案；这些字段不进入 Student。每个样例的完整消息见 [hint_examples.jsonl](hint_examples.jsonl)。消息由保存的 source record 和当前未修改的 prompt 模板重建；不是原始 HTTP 请求日志，不含认证信息，也不证明服务端采样可逐字复现。

程序检查包括字数、正文格式、指定实例名称与状态词是否出现。它不是完整语义验证器：不保证状态布尔值解释正确、不保证所有推断都有事实依据、不保证策略能让 Student 成功。特别应检查 Pick2 的第二个对象、look 任务的目标、容器状态及 `cool=false` 的自然语言解释。

[12 条可读样例](hint_examples.md) 按训练 panel 顺序，每个任务类型选前两条，逐字保留原始 hint，没有按效果或质量筛选。

## 实验参数

精确实际配置见 [actual_config.json](actual_config.json)，公开启动配置见 [train.yaml](../../../../configs/experiments/l3_train1500/train.yaml)。

| 项目 | 实际设置 |
|---|---|
| 基座 | 原版 Qwen3-4B，无本次任务 SFT/RFT；从 `/models/Qwen3-4B` 初始化 |
| GPU / 并行 | 单机 8 × A100 SXM4 80GB；FSDP；BF16；vLLM sync，TP=1 |
| 目标函数 | `sd_only`：PG=0、SDL=1；top-20 forward KL + tail bucket |
| SDL 范围 | 全部普通响应 token，mask special tokens；`response_token_mean` |
| 学习率 / PPO epochs | 1e-6 / 1 |
| 训练 batch | 16 道题 × 8 次环境 rollout＝128 episodes/update；native rollout.n=1 |
| 优化 batch | mini-batch 256 个 step samples；每卡 micro-batch 配置 1，动态 batch，上限 8,192 token/卡 |
| episode / 历史 | 最多 30 个动作；最近 2 步观察和动作，任务目标每步保留 |
| prompt / response | 4,096 / 64 token |
| 输出格式 | action-tag-only；不生成 think 标签；chat template enable_thinking=False |
| 训练采样 | temperature 1.0；top-p 1.0；top-k -1 |
| 验证采样 | temperature 0.4；top-p 1.0；top-k -1；每题 n=4 |
| 验证并行 | 64 个逻辑任务 × 4 次采样，256 个环境；每个 128 题 split 分两波 |
| 计划更新数 | 250；total_epochs=250 是迭代上限，不代表实际遍历数据 250 遍 |
| 验证 / 保存 | 训练前完整验证；每 25 次更新验证和保存；保留最近 2 个 actor checkpoint |
| rollout 导出 | 每 5 步，及最后一步 |
| 其他损失 | entropy=0；额外 KL 关闭；invalid-action penalty 配置 0.1，PG 系数为 0 |
| 运行细节 | eager=true；torch.compile=false；vLLM memory utilization=0.3；参数/优化器 CPU offload=false |
| Ray | 48 CPU；object store 2 GiB；任务独立临时目录 |
| W&B | 独立 project `alfworld-l3-train1500-20260908`；console + online wandb |

[W&B 运行](https://wandb.ai/2606478269-ustc/alfworld-l3-train1500-20260908/runs/l3-train1500-seed0-20260908) 的可见性由账户权限决定。本仓库的固定快照可独立阅读。

公开启动配置与实际快照只有部署层面的区别：使用单独的 reproduction 输出、processed cache 和 Ray 临时目录，不绑定原运行的 W&B run ID/entity/日志目录。实验超参数保持一致。模型路径可由 CLI 的 `--checkpoint` 覆盖。

## 已有证据与未完成部分

- 单独的 8 卡 preflight 在 16 个 pilot 游戏上完成 1 次真实更新，并保存 checkpoint。正式运行重新从原始 Qwen3-4B 开始，没有继承 preflight 训练权重。
- 正式基座验证：seen **39/512 = 7.6171875%**；unseen **15/512 = 2.9296875%**。主指标是 Avg@4，即每题四次的成功率平均；不是四次中任意成功一次的 pass@4。
- 基座失败轨迹均达到 30 步上限；导出动作符合格式、被环境接口判为合法，任务目标每步保留。失败集中在反复查看、来回移动和操作错误目标。这个审计不构成对所有环境实现 bug 的排除。
- 正式 step 1：SDL loss **1.0314760388407325**，active SDL tokens **42,923**，单步 **216.48 秒**。第 1 步实际参数更新完成后才写入指标。
- [metrics_snapshot.jsonl](metrics_snapshot.jsonl) 包含 step 0–15。step 0 是初始验证，step 1–15 是实际更新；每步训练成功率对应不同采样任务，不能当作固定验证集曲线。
- 本快照尚无训练后验证或正式 checkpoint。首次计划保存/验证在 step 25。完整 250 步、多 seed、多 hint 等级的结论均未完成。
- 与论文的原始 4B 结果仍有差距。详见 [论文对照](../../literature_qwen3_4b.md)；没有匹配对照足以把低分归因于历史长度、thinking 或某一个参数。

## 新环境上的运行顺序

以下命令是显式的数据构建/API/GPU 操作；静态审查只需阅读配置、样例和代码。需要安装 [已验证运行环境](../../validation.md)，准备 ALFWorld 官方数据和模型，设置 `ALFWORLD_DATA`。公开仓库只含 12 条样例，不含完整 1,500 条 hint bank，不能用样例文件代替完整训练 bank。

```bash
# 仓库根目录；使用实际准备好的路径。
export ALFWORLD_DATA=/path/to/alfworld

# 用已经选定的 1,500 题 panel 重建 privilege，不重新抽样。
python -u -m hintladder.cli build-privilege-bank \
  --config configs/experiments/l3_train1500/privilege.yaml --seed 0

# 先在自己的本地配置副本中填写可用 API endpoint 和凭据文件路径。
# 下列模板 endpoint 是 example.invalid，直接使用会失败。
python -u -m hintladder.cli build-hint-bank \
  --config configs/experiments/l3_train1500/hint_gen.yaml --seed 0

# 根据自己的账户设置 WANDB_ENTITY 并预先完成 wandb login。
export WANDB_DIR="$PWD/runs/l3_train1500_reproduction/wandb"
mkdir -p "$WANDB_DIR"
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 python -u -m hintladder.cli train-student \
  --config configs/experiments/l3_train1500/train.yaml \
  --seed 0 --checkpoint /path/to/Qwen3-4B
```

恢复需传入已有的 `global_step_N` 目录，其中必须包含原生模型/优化器、`data.pt` 与 `hint_ladder_budget.json`；不要把同一个输出目录用于独立重复实验。

## 本次同步的实现改动

- privilege 构建支持独立 CPU 进程，并保持候选顺序，避免 TextWorld parser 的线程共享问题。
- hint 生成每 8 个结果保存一次，失败时保留已收集结果；恢复使用原任务索引决定的 seed。
- native Python 子进程显式启用 `-u`，避免外层日志缓冲。当前快照运行在修正前已启动，可直接读取其 Ray trainer stdout。
- 增加并发/断点恢复测试。相关 CPU 测试共 **65 项通过**；没有为了发布文档再启动 GPU 实验。
