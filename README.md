# Hint Ladder on verl

研究多轮 agent 自蒸馏时，Teacher 应该获得多少额外信息。Student 使用干净观察完成任务；同一份当前模型权重作为 Teacher，在前向评分时接收 hint，监督 Student 实际生成的响应 token。支持原有任务级离线 bank，以及新增的逐 turn 在线 L1。

这是 `sksdiw3/hint-ladder-verl` 的独立源码仓库。包含 Hint Ladder E1–E4 编排、所需原生 verl 代码和 agent 环境代码。当前 Hint Ladder 实现和验证范围是 **ALFWorld / Qwen3-4B**。保留了上游 WebShop 环境源码，但尚未实现或验证 WebShop 的 Hint Ladder privilege bank 与实验适配。

## 当前实验与审查入口

- **[完整实验报告（2026-09-12）](实验报告_20260912.md)**：在线无 oracle L1、仅监督 reasoning 正文、teacher top-32 + tail。全量计划223步，完成110步后暂停；step19开始大量空reasoning，42个记录步跳过optimizer。最后完整评测step100：**Seen 53/140=37.86%，Unseen 46/134=34.33%**；缺少同预算base，不能把历史成绩差直接解释成训练收益。
- **[8局真实完整轨迹，293 turns](docs/hintladder/experiments/l1_reasoning_body_top32_20260911/report_20260912/真实轨迹.md)**：base同题有/无hint、训练中的正常/空/异常reasoning，逐turn包含原始prompt、hint、response、动作及来源。另附[110步指标](exports/key_error_traces_20260912/metrics.jsonl)、[全部105个prefix的两侧top-10](exports/turn7_prefix_top10_20260912/完整turn_逐prefix_top10.md)。所有OPD checkpoints与批量trace已按要求删除；精选证据已发布，训练保持暂停。
- [top-32运行配置与启动快照](docs/hintladder/experiments/l1_reasoning_body_top32_20260911/README.md)：8卡、3,553个不同训练游戏、API并发128、GLM-5.3-flash thinking开启。相关实现与启动源码哈希一致，发布前108项CPU测试通过。

- **[2026-09-11：仅监督 reasoning 正文的全量 L1 实验](docs/hintladder/experiments/l1_reasoning_body_20260911/README.md)**：原始 Qwen3-4B，8 卡，3,553 题/223步；教师仅多 hint 与使用说明，标签及 action 不纳入直接 KL。108 项测试、412 条真实 token 边界核对通过；已按用户要求暂停，尚无完整训练step，见报告。

**[Claude / 人工审查指南](docs/hintladder/review_guide.md)** 汇总了研究契约、代码入口、运行证据和待核查问题。

- **[新 fast 版本：8 卡五步验收](docs/hintladder/experiments/fast_verify_20260910/REPORT.md)**：采用用户提供的 `hint-ladder-verl-fast` / `1decc33`，修复失败行的零监督 mask 和预取跨 step 生命周期。85 项 CPU 测试、10 个历史失败状态的真实 GLM API 检查已通过；5步训练及完整seen/unseen评测已完成，详见验收报告。每步 128 局，GLM-5.3-flash thinking=enabled / effort=low / 768 tokens / 并发128。

- **[历史：全量在线 L1 训练、并发与耗时（2026-09-10 21:21 +08:00）](docs/hintladder/experiments/l1_online_full_20260910/README.md)**：3,553 道训练题，8 卡，Student 每批 16 局，GLM-5.3-Flash API 并发 64；快照完成 3/223 步，耗时 **557 / 548 / 837 秒**。附原始数值日志、配置快照和超时重试证据。新增 W&B 完整提交修复与整局推理复用配置；**这是当时3步快照；后续fast和top-32结果见上方报告**。

- **[各轮实验结论、Prompt 与结果](实验结论.md)**：原始 Qwen3-4B 显式 reasoning 全量评测，Seen **41/140 = 29.29%**、Unseen **41/134 = 30.60%**；[274 题结果及配置归档](docs/hintladder/experiments/reasoning_eval_20260910/README.md)。每题一次、50步、4096-token 响应预算，不能与历史 action-only 协议直接归因比较。OPD checkpoints和批量trace已删除，保留指标与精选证据。

- [本轮实验报告与完整指标日志（2026-09-09）](docs/hintladder/experiments/l3_train1500_20260908/report_20260909/REPORT.md)：Qwen3-4B、8 张 A100、1,500 题 L3 纯 SDL；计划250步，恢复分支完成151步后在152步报错退出。最新已评测 checkpoint150 的 seen/unseen 为 **1.37% / 0.20%**，低于 base。
- [四组 base / step150 完整中英文轨迹](docs/hintladder/experiments/l3_train1500_20260908/report_20260909/trajectories_zh_en.md)：同题验证对照，8条 episode、161个动作步，附原始 prompt、逐步动作空间及来源 JSONL；含进步和退步样例，属于按结果选择的定性展示。
- [初始实验参数、启动方法与 step15 历史快照](docs/hintladder/experiments/l3_train1500_20260908/README.md)：保留2026-09-08 23:59 +08:00 的原始记录，当前结论以新报告为准。
- [六类任务的 12 条真实 L3 hint](docs/hintladder/experiments/l3_train1500_20260908/hint_examples.md)，以及 [GLM 实际输入消息与生成结果](docs/hintladder/experiments/l3_train1500_20260908/hint_examples.jsonl)。样例来自完整训练 bank，按固定规则选取，没有按效果筛选。
- [近期 Qwen3-4B / ALFWorld 论文对照](docs/hintladder/literature_qwen3_4b.md)：ATOD、D2Skill、SAPO、MASA、T²PO、From History to State；区分原始模型、SFT/RFT、RL 与推理时 skill 增强。
- [实验配置](configs/experiments/l3_train1500/train.yaml) 与 [实际运行解析配置快照](docs/hintladder/experiments/l3_train1500_20260908/actual_config.json)。公开生成配置使用占位 API 地址，运行前需要自行配置。

历史 action-only 基座在固定 seen/unseen 各 128 题、每题 4 次采样下，成功率为 **7.62% / 2.93%**。这是 30 步、action-only、历史长度 2 的特定设置；与论文的交互预算、模型版本、提示词和任务集尚未对齐。训练损失下降不等于验证能力提升。

## 当前范围

| 阶段 | 实现内容 | 验证边界 |
| --- | --- | --- |
| 数据与 hint | 官方 walkthrough 回放、固定 game lists、L1/L2/L3/FULLPATH 离线 bank、泄露检查 | 本次 1,500 个训练游戏 walkthrough 与 L3 程序检查通过；程序检查不保证所有提示语义正确 |
| 在线 L1 | GLM-5.3-Flash 按当前 Student turn 的公开状态生成 hint，仅用于 Teacher 评分；全量 train 与不等长 seen/unseen 面板 | 8卡完成5步验收；后续reasoning-body/top32完成110/223步，空正文退化，42步跳过更新；详见最新报告 |
| E1 | 冻结模型 rollout、行为审计、参考动作的 clean/hinted/hint-only 三视图评分 | 原工作区完成单任务 GPU smoke；没有完成正式统计实验 |
| E2 | 各 hint 等级与 seed 的 Student 训练编排、SDL token 预算、恢复训练 | 8 卡 L3 单臂恢复分支完成151步；checkpoint150验证退步。完整250步、多臂、多seed未完成 |
| E3 | h-star 探针、匹配游戏池的 h-star/random 课程、周期刷新 | CPU 合同与编排测试；完整 GPU 实验未运行 |
| E4 | 离线 bank → Student 更新 → seen/unseen 验收 → 回滚或外部 Hinter 更新 | CPU 编排测试；**Hinter reward 与 Hinter GRPO 暂未实现** |

默认预设 `sd_only` 为 PG=0、SDL=1、top-20 forward KL + tail；最新实验显式覆盖为 **top-32、reasoning_body**。Student rollout 和最终 seen/unseen 验证不接收 hint。`grpo_sd` 预设为 PG=1、SDL=0.01。

E1 smoke 不构成进入 E2 的研究依据；`stage.smoke: true` 会强制 `accepted_for_e2: false`。E4 的外部训练接口要求真实 trainer 返回产物，缺少命令时明确报错。

## 代码入口

- `hintladder/`：自然键、hint bank、Teacher prompt、token 预算、审计与实验编排。
- `hintladder/online_l1.py`：公开状态提取、可配置并发（最新128）、rollout期间异步预取、按step去重及失败降级；[在线训练配置和启动说明](docs/hintladder/experiments/l1_online_full_20260910/README.md#启动与复现)。
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

准备 ALFWorld 数据，令 `ALFWORLD_DATA` 指向包含 `json_2.1.1/` 与 `logic/` 的目录。每个游戏需要 `game.tw-pddl` 和 `traj_data.json`。完整数据、模型、hint bank 和 checkpoint 需在本地准备；仓库包含明确标记的 hint 样例、指标日志、控制台日志与部分验证轨迹。

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


## 2026-09-12 本地实验产物清理

按用户要求，OPD 已保存 checkpoints 和批量原始 trace 已删除，训练保持暂停。指标、配置、报告和少量关键错误样例已保留。请从 [关键错误速览](exports/key_error_traces_20260912/关键错误速览.md) 和 [保留包说明](exports/key_error_traces_20260912/README.md) 查看；旧文档中的 checkpoint 与全量 trace 路径不再代表文件仍存在。
