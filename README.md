# Hint Ladder on verl

研究多轮 agent 自蒸馏时，Teacher 应该获得多少额外信息。Student 使用干净观察完成任务；同一份当前模型权重作为 Teacher，在前向评分时接收离线生成的 hint，监督 Student 实际生成的响应 token。

这是 `sksdiw3/hint-ladder-verl` 的独立源码仓库。包含 Hint Ladder E1–E4 编排、所需原生 verl 代码和 agent 环境代码。当前 Hint Ladder 实现和验证范围是 **ALFWorld / Qwen3-4B**。保留了上游 WebShop 环境源码，但尚未实现或验证 WebShop 的 Hint Ladder privilege bank 与实验适配。

## 当前实验与审查入口

**[Claude / 人工审查指南](docs/hintladder/review_guide.md)** 汇总了研究契约、代码入口、运行证据和待核查问题。

- [1,500 题 L3 实验：完整参数、运行方法与结果边界](docs/hintladder/experiments/l3_train1500_20260908/README.md)：Qwen3-4B、8 张 A100、250 次更新、纯 SDL。2026-09-08 23:59 +08:00 的归档快照记录到第 15 次更新；不是已完成训练或能力提升的声明。
- [六类任务的 12 条真实 L3 hint](docs/hintladder/experiments/l3_train1500_20260908/hint_examples.md)，以及 [GLM 实际输入消息与生成结果](docs/hintladder/experiments/l3_train1500_20260908/hint_examples.jsonl)。样例来自完整训练 bank，按固定规则选取，没有按效果筛选。
- [近期 Qwen3-4B / ALFWorld 论文对照](docs/hintladder/literature_qwen3_4b.md)：ATOD、D2Skill、SAPO、MASA、T²PO、From History to State；区分原始模型、SFT/RFT、RL 与推理时 skill 增强。
- [实验配置](configs/experiments/l3_train1500/train.yaml) 与 [实际运行解析配置快照](docs/hintladder/experiments/l3_train1500_20260908/actual_config.json)。公开生成配置使用占位 API 地址，运行前需要自行配置。

本次基座在固定 seen/unseen 各 128 题、每题 4 次采样下，成功率为 **7.62% / 2.93%**。这是 30 步、action-only、历史长度 2 的特定设置；与论文的交互预算、模型版本、提示词和任务集尚未对齐。训练损失下降不等于验证能力提升。

## 当前范围

| 阶段 | 实现内容 | 验证边界 |
| --- | --- | --- |
| 数据与 hint | 官方 walkthrough 回放、固定 game lists、L1/L2/L3/FULLPATH 离线 bank、泄露检查 | 本次 1,500 个训练游戏 walkthrough 与 L3 程序检查通过；程序检查不保证所有提示语义正确 |
| E1 | 冻结模型 rollout、行为审计、参考动作的 clean/hinted/hint-only 三视图评分 | 原工作区完成单任务 GPU smoke；没有完成正式统计实验 |
| E2 | 各 hint 等级与 seed 的 Student 训练编排、SDL token 预算、恢复训练 | 8 卡 L3 单臂真实更新已有记录；完整 250 步结果与多臂、多 seed sweep 尚未在本快照完成 |
| E3 | h-star 探针、匹配游戏池的 h-star/random 课程、周期刷新 | CPU 合同与编排测试；完整 GPU 实验未运行 |
| E4 | 离线 bank → Student 更新 → seen/unseen 验收 → 回滚或外部 Hinter 更新 | CPU 编排测试；**Hinter reward 与 Hinter GRPO 暂未实现** |

默认训练目标是 `sd_only`：PG=0、SDL=1，使用 top-20 forward KL 和 tail bucket。Student rollout 和最终 seen/unseen 验证不接收 hint。`grpo_sd` 预设为 PG=1、SDL=0.01。

E1 smoke 不构成进入 E2 的研究依据；`stage.smoke: true` 会强制 `accepted_for_e2: false`。E4 的外部训练接口要求真实 trainer 返回产物，缺少命令时明确报错。

## 代码入口

- `hintladder/`：自然键、hint bank、Teacher prompt、token 预算、审计与实验编排。
- `verl/trainer/main_hint_ladder.py`：原生 verl 入口。
- `verl/trainer/ppo/hint_ladder_ray_trainer.py`：Teacher 桥接、冻结探针、训练与恢复。
- `agent_system/`：环境管理、多轮 rollout 和 episode reward。
- `configs/`：正式实验臂与小规模验证配置。
- `tests/hintladder/`：CPU 测试。
- `data/game_lists/`、`data/smoke/*_games.txt`：固定的相对游戏路径；不包含游戏本体。

## 使用

使用已准备好的 Python 3.11 环境，在仓库根目录执行命令。GPU 运行需要兼容的 PyTorch、vLLM、FlashAttention、Ray 与 TextWorld/ALFWorld；实际验证过的版本见 [运行环境与验证记录](docs/hintladder/validation.md)。继承的 `requirements*.txt` 和安装元数据保留上游依赖范围，**不是本项目 GPU 验证环境的锁文件**；目前提供的是从源码目录运行的工作流。

```console
git clone git@github.com:sksdiw3/hint-ladder-verl.git
cd hint-ladder-verl
python -m hintladder.cli --help
python -m pytest tests/hintladder -q
```

准备 ALFWorld 数据，令 `ALFWORLD_DATA` 指向包含 `json_2.1.1/` 与 `logic/` 的目录。每个游戏需要 `game.tw-pddl` 和 `traj_data.json`。完整数据、模型、hint bank、checkpoint 和运行日志均需在本地准备；仓库只包含明确标记的 hint 样例和指标快照。

生成 hint 前，在 `configs/smoke/hint_gen_v2.yaml` 中配置自己的 OpenAI-compatible `/v1` 服务地址和 `api_key_file` 路径。`glm-5.3-flash` 是此前实际使用的模型 ID；`.secrets/` 中的凭据文件仅供本地使用。

下面是需要用户自行执行的 smoke 流程；生成 hint 会调用 API，训练与 E1 会使用 GPU：

```console
python -m hintladder.cli build-privilege-bank --config configs/smoke/privilege.yaml --seed 0
python -m hintladder.cli build-hint-bank --config configs/smoke/hint_gen_v2.yaml --seed 0
python -m hintladder.cli train-student --config configs/smoke/train.yaml --seed 0 --checkpoint /path/to/Qwen3-4B
python -m hintladder.cli e1-audit --config configs/smoke/e1_audit.yaml --seed 0 --checkpoint /path/to/Qwen3-4B
```

`train.yaml` 使用 `configs/smoke/mixed_level_map.json` 对四个训练游戏分别指定 L1/L2/L3/FULLPATH，默认 2 GPU、1 个更新 step、每局最多 3 步。E1 smoke 使用 1 个游戏 × 4 级 × k=1、每局最多 3 步，评分模型为传入的冻结 checkpoint。可调整 YAML 中的模型路径、GPU 数量、batch 和产物路径。

正式配置、目标函数、E3 对齐方式与 E4 接口见 [实施说明](HINT_LADDER.md)。[原始设计](docs/hintladder/design.md) 保留研究契约，文中 Hinter reward/GRPO 部分已按后续决定延期。

## 来源

基于 SMRC-SD `1a0996ba133527b70beb47d01df3899175893a90` 的源码快照，复用 verl / verl-agent 环境与训练实现。新仓库使用独立 Git 历史；上游版权、许可证和来源说明保留在 [LICENSE](LICENSE)、[Notice.txt](Notice.txt) 和 [THIRD_PARTY.md](THIRD_PARTY.md)。
