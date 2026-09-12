# Claude / 人工审查入口

本仓库是 `sksdiw3/hint-ladder-verl`。请从以下材料审查本次实验，避免把 smoke、运行快照和研究结论混为一谈。

## 最新：2026-09-12 reasoning-body / top-32 结果

先读 [完整实验报告](../../实验报告_20260912.md)，再看 [8局真实轨迹](experiments/l1_reasoning_body_top32_20260911/report_20260912/真实轨迹.md)、[110步原始指标](../../exports/key_error_traces_20260912/metrics.jsonl)、[实际配置](../../configs/experiments/l1_reasoning_body_top32_20260911/train_full.yaml)。训练110/223步后暂停，42步跳过optimizer，所有OPD checkpoints及批量trace已按要求删除。

本轮核查重点：Teacher移除hint与说明后是否逐字还原Student；同一原始prefix及原始token-ID mask是否正确；teacher top-32+tail、response_token_mean、PG=0是否按配置生效；无监督批次是否跳过optimizer。分别审查step19空正文出现、step22整批零监督与最终任务评测，不能把高top-k重叠等同于无梯度差异，也不能将base诊断视为训练中各checkpoint的分布。

可直接交给审查者的任务：

> 请先阅读2026-09-12完整报告及其真实轨迹、逐步指标与配置，再核对源码。区分已观察到的长度/格式退化、确定的实现契约与尚未验证的因果假设。核查为什么仅监督reasoning正文仍可能改变结束行为，是否存在mask/温度/归一化/分布式聚合问题。输出证据、文件行号、影响及最小验证方案。不要重启训练、占用GPU、调用hint API或读取凭据。

## 历史：2026-09-10 在线 L1 快照

以下章节保留早期协议和审查背景；其中top-20、4096-token、并发64、首次评测尚未发生等描述不是当前top-32实验设置。

当前新增代码请先读 [全量在线 L1 方法、参数、计时及发布边界](experiments/l1_online_full_20260910/README.md)，配合 [实际启动配置](experiments/l1_online_full_20260910/actual_config_sanitized.json) 和 [前三步原始数值日志](experiments/l1_online_full_20260910/metrics_snapshot.jsonl)。后面的 L3 阅读顺序保留为历史实验入口。

- [online_l1.py](../../hintladder/online_l1.py) 从已采集的 Student 轨迹提取公开状态，GLM-5.3-Flash 并发 64，仅向 Teacher 提供 L1。优先核查当前 observation / 历史动作边界、同 step 去重、API 失败处理，以及 Student response token 的对齐。
- 新实验是 reasoning prompt、50 步、4,096 response tokens、每题 1 次；验证 seen 140 / unseen 134。下面历史 L3 的 action-only、30 步、Avg@4 不是这次的配置。
- 本次增加 W&B 完整行提交修复，并在下一次启动配置启用已有的整局推理复用。当前训练没有重启，公布耗时来自旧开关设置；不要把代码/CPU 检查当作提速证据。训练后 held-out 结果尚未产生。

## 建议阅读顺序

1. [研究与实施契约](../../HINT_LADDER.md) 和 [原始设计](design.md)：E1–E4 范围；Hinter reward/GRPO 尚未实现。
2. [2026-09-09 结果报告](experiments/l3_train1500_20260908/report_20260909/REPORT.md)：全部验证结果、两次运行与退出原因；恢复分支完成151步，checkpoint150验证退步。方法、超参数和启动命令另见[初始实验说明](experiments/l3_train1500_20260908/README.md)。
3. [四组同题中英文轨迹](experiments/l3_train1500_20260908/report_20260909/trajectories_zh_en.md)、[完整指标与控制台日志](experiments/l3_train1500_20260908/report_20260909/logs)、[验证重算](experiments/l3_train1500_20260908/report_20260909/validation_summary.jsonl)、[实际解析配置](experiments/l3_train1500_20260908/actual_config.json)。旧的[step15指标](experiments/l3_train1500_20260908/metrics_snapshot.jsonl)和[初始时间快照](experiments/l3_train1500_20260908/snapshot.json)仅是历史记录。
4. [12 条真实任务与 hint](experiments/l3_train1500_20260908/hint_examples.md)，以及包含完整 GLM 输入消息的 [JSONL](experiments/l3_train1500_20260908/hint_examples.jsonl)。
5. [近期论文对照](literature_qwen3_4b.md)：原始、SFT/RFT、RL、推理时 skill 的结果应分别比较。

## 核心代码

| 审查内容 | 代码 |
|---|---|
| 官方 walkthrough 与初始事实提取 | [privilege.py](../../hintladder/privilege.py)、[build_privilege_bank.py](../../hintladder/stages/build_privilege_bank.py) |
| L1/L2/L3 提示词与程序检查 | [ladder.py](../../hintladder/ladder.py)、[build_hint_bank.py](../../hintladder/stages/build_hint_bank.py) |
| Teacher 私有上下文和实际 token 对齐 | [teacher_prompt.py](../../hintladder/teacher_prompt.py) |
| clean rollout → Teacher forward → SDL update | [hint_ladder_ray_trainer.py](../../verl/trainer/ppo/hint_ladder_ray_trainer.py) |
| KL 损失实现与聚合 | [dp_actor.py](../../verl/workers/actor/dp_actor.py)、[skillsd_utils.py](../../verl/trainer/ppo/skillsd_utils.py) |
| 多轮观察、历史和成功判定 | [env_manager.py](../../agent_system/environments/env_manager.py)、[rollout_loop.py](../../agent_system/multi_turn_rollout/rollout_loop.py) |
| 固定验证分组与 Avg@4 | [ray_trainer.py](../../verl/trainer/ppo/ray_trainer.py) |
| CPU 测试 | [tests/hintladder](../../tests/hintladder) |

## 需要重点审查的问题

- Student rollout 和验证是否始终 clean；Teacher 是否只对同一批 Student 实际响应 token 评分，有没有重采样、错位或 retokenization 替换。
- Teacher 与 Student 使用同一份当前权重；Teacher target 是否在更新前计算并停止梯度。PG 系数为 0 的情况下，reward、invalid-action penalty 与优势是否仍可能意外进入优化目标。
- top-20 forward KL 和 tail bucket 的方向、mask、跨 GPU / micro-batch 聚合、active-token 计数是否与配置一致。
- L3 检查主要匹配文字、长度与格式，不是语义验证器。尤其核查 `cool=false` 与“cold”的表述、容器初始状态、第二个目标物体和到达/交互前提是否被 hint 错误描述。
- `hidden_facts_from_initial` 围绕 walkthrough 的第一个拾取对象提取结构化字段。Pick2 的第二个对象仍可出现在 walkthrough 中，但不受同等结构化字段检查；look 任务也可能没有 destination 字段。
- 初始基座低分是否与 30 步、action-only prompt、64 token、模型版本或任务 panel 有关；目前没有消融足以认定原因。2 步历史本身不是已经确认的根因。
- 验证是否按独立轨迹汇总，并保持每题 4 次；不要把 pass@4、Avg@4、每动作 reward 平均值或训练 batch 成功率混用。
- 数据选择只保留 walkthrough 可验证的训练任务是否造成分布偏差；单个 seed、单个 L3 臂和损失下降是否被过度解释。

## 历史 L3 审查任务

> 请对本仓库做静态代码与研究协议审查。先阅读本指南、2026-09-09结果报告、actual_config.json和分运行的完整指标；不要把旧step15快照当作当前结果，也不要混合原运行与恢复运行重叠的101–116步。请检查 Teacher/Student 信息边界、token 对齐、SDL 损失和多 GPU 聚合、hint 事实准确性、验证指标以及与论文的可比性。结合总体退步与中英文同题轨迹，区分已观察行为和因果假设；核查152步 thinking 标签检查为什么直接终止训练。逐条给出严重度、文件/行号、证据、影响和建议；把确认的 bug、合理风险和需要额外实验的问题分开。不要启动 GPU 训练、调用 hint API、修改实验或读取凭据。
