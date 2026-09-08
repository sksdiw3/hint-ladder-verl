# Hint Ladder E1–E4

本目录基于 SMRC-SD `1a0996ba133527b70beb47d01df3899175893a90`，独立于 OPD-hinter。原始要求保存在 `docs/hintladder/design.md`。本仓库由 `sksdiw3` 独立维护，来源与导出边界见 `THIRD_PARTY.md`。本阶段实现 ALFWorld；不宣称已经实现 WebShop 的 privilege bank 或 Hint Ladder 适配。

按后续范围调整，Hinter reward 与 Hinter GRPO **暂不实现**。E4 已提供离线 bank → Student 更新 → 固定 seen/unseen 验收 → 回滚或外部 Hinter 更新的顺序驱动，以及可恢复的外部训练接口。未配置外部命令时明确报错，不产生假的训练结果。`copy` 始终只作诊断。

## 执行流程

所有命令在本目录执行。配置采用平铺的 Hydra 点分键；`extends` 必须是列表，只合并一层。

```console
python -m hintladder.cli build-privilege-bank --config configs/privilege.yaml --seed 0
python -m hintladder.cli build-hint-bank --config configs/hint_gen.yaml --seed 0
python -m hintladder.cli e1-audit --config configs/e1_audit.yaml --seed 0 --checkpoint /path/to/Qwen3-4B
python -m hintladder.cli train-student --config configs/e2_sweep.yaml --seed 0
python -m hintladder.cli e3-probe --config configs/e3_probe.yaml --seed 0 --checkpoint /path/to/global_step_250
python -m hintladder.cli train-student --config configs/arms/e3_hstar.yaml --seed 0 --checkpoint /path/to/global_step_250
python -m hintladder.cli eval-behavior --config configs/eval_behavior.yaml --seed 0
python -m hintladder.cli alternate --config configs/e4_alternate.yaml --seed 0
```

正式配置里的模型路径、GPU 数量、产物路径需要符合运行环境。E2 sweep 读取 E1 的 `accepted_for_e2`；E4 读取人工研究判定 `phenomenon_observed: true`，并要求真实外部 Hinter trainer。代码不会把 smoke 的成功运行当成 E1/E2 研究现象成立。

| 阶段 | 已实现行为 | 主要产物 |
| --- | --- | --- |
| 数据 | TextWorld 回放官方嵌入 walkthrough；只选获胜游戏；记录初始事实与逐步公开观察 | privilege JSONL、固定 game lists、walkthrough states、manifest |
| E1 | 冻结 policy 的原生多轮 rollout；L1/L2/L3 泄露检查；同一参考动作 token 的 clean/hinted/hint-only 三视图评分 | rows、rollouts、reference_scores、summary |
| E2 | 5 级 × 3 seeds；L3 seed0 的 250 步作为 SDL token 预算；完整 step 后停止并记录 overshoot | 原生 checkpoints、budget、metrics、干净验证 dump |
| E3 | L0–L3 各 k 次；首个成功比例 ≥0.5 的级别；同一训练池的 h-star/random map；每 100 步重新探测 | hstar_manifest、level maps、刷新轮次状态 |
| E4 | 每轮 HINTER bank、Student 更新、seen/unseen 均不退步验收、失败回滚、外部 Hinter 更新与恢复 | training_request/response、round status、result |

设计中的 `pass_at_k` 字段保留，但定义明确为 k 次的成功比例（Avg@k），不是“至少一次成功”的 pass@k 估计。E3 的 mastered 与 unreachable 都从两个课程臂的训练池中剔除。

先运行 `e3_hstar`，再以同一初始 checkpoint 和 seed 运行 `e3_random`；后者读取前者每轮的探针面板和 random map，保证刷新后仍使用完全相同的游戏池。

## GLM hint 生成

`configs/hint_gen.yaml` 使用实际模型 ID `glm-5.3-flash`，凭据仅通过 `stage.generator.api_key_file` 引用本地权限受限文件；`.secrets/` 已忽略。manifest 和 launch command 中不包含凭据内容。只保存最终 hint 正文。

L1/L2 的 API 输入严格限制为初始公开观察和 admissible commands；L3 才接收隐藏事实与 walkthrough。FULLPATH 直接来自 CPU 已验证 walkthrough，不调用模型。生成失败有有限重试及失败报告；无合格 bank 时训练会报错。生成器的推理配置与 Qwen Student/Teacher 的 no-thinking 设置独立。

## Student 与 Teacher 合同

训练沿用原生 collector、FSDP actor、GRPO advantage、episode reward 和 checkpoint。`HintLadderRayTrainer` 是唯一新增 trainer 子类。Teacher 使用同一步 Student 权重，在 ALFRED 首行后插入便签；响应 token ID 完全复用 Student rollout。提示超过上限报错，绝不截断。

默认 `sd_only`：PG=0、SDL=1、top-20 forward KL + tail、ordinary response tokens、response_token_mean，entropy=0、额外 KL 关闭。`grpo_sd` 为 PG=1、SDL=0.01。`sd_only` 下 L0 仅做基座验证。Student rollout 与 seen/unseen 验证始终不携带便签。

每次 actor update 成功后计入实际 SDL mask token 数；预算状态存于 `global_step_N/hint_ladder_budget.json`。恢复训练传入原生 `global_step_N` 目录，可恢复模型、optimizer、dataloader 和预算。HF 目录仅用于权重初始化或冻结 probe。

`verl/` 仅新增两个入口/桥接文件，原配置只新增 `algorithm.hint_ladder` 组。`agent_system/environments/env_manager.py` 的改动仅处理每个 worker 的 `gamefile` 透传与一致性检查。

## 数据与运行环境

设置 `ALFWORLD_DATA` 指向包含 `json_2.1.1/` 与 `logic/` 的目录。使用 ALFWorld 官方 release 的 `json_2.1.2_tw-pddl.zip` 和 `json_2.1.1_json.zip`；前者实际内层目录仍名为 `json_2.1.1`。逻辑文件来自 ALFWorld 安装包。原生环境还需要同目录的 `traj_data.json`，只下载 tw-pddl 不够。

运行环境的主要包版本、原工作区 GPU smoke 结果和此次导出的验证边界见 [validation.md](docs/hintladder/validation.md)。继承的依赖文件不是已验证 GPU 环境的完整锁文件。

在仓库根目录执行；请先按 README 准备本地数据、模型和 hint bank。下列训练命令需要 GPU：

```console
python -m pytest tests/hintladder -q
python -m hintladder.cli train-student --config configs/smoke/train.yaml --seed 0 --checkpoint /path/to/Qwen3-4B
```

每个阶段目录均写 manifest，输入 sha256 仅作溯源。`git_commit` 记录运行时的仓库 HEAD；运行前应提交代码和配置变更，以便追溯。真实 GPU smoke 与全规模实验的证据分开记录，不据短 smoke 断言模型能力提升。
