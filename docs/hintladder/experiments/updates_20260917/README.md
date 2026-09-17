# OPD 实验结果与 hint 分层更新 · 2026-09-17

这次归档包含两种证据：冻结 Base Teacher 的实际 OPD 训练，以及原始 Base 上的 L1–L3 推理和同 prefix KL 诊断。二者使用不同的 L3 定义，不能合并成同一训练实验。

## 结果入口

| 实验 | 模型与 hint | 已完成的结果 | 证据 |
|---|---|---|---|
| 冻结教师 L1 OPD | Student 训练，Teacher 固定为原始 Qwen3-4B；无 Oracle 方向提示 | 155 个训练步；最近完整评测 step150：Seen **64/140 = 45.71%**，Unseen **59/134 = 44.03%** | [完整训练报告](frozen_teacher_training/README.md) |
| 冻结教师 Oracle L3 OPD | 相同冻结 Teacher；经环境验证的 walkthrough 继续动作 | 恢复分支到 step58；最近完整评测 step50：Seen **62/140 = 44.29%**，Unseen **56/134 = 41.79%** | [所有评测点与原始日志](frozen_teacher_training/README.md) |
| 新公共状态 L1–L3 诊断 | 全部使用原始 Qwen3-4B；三层均无 Oracle，无训练 | 30 题 × 4 组独立轨迹；reasoning 正文 KL(hint ‖ Base)：**L1 0.649，L2 1.106，L3 0.971 nats/token** | [KL 与推理报告](public_hint_kl/REPORT.md) |

L1 和 Oracle L3 在**相同 step50**的 Seen / Unseen 分别为 **42.86% / 40.30%** 和 **44.29% / 41.79%**。这是单次运行的观测差值，不能据此宣布等价、显著优劣或 Oracle 必然有害。历史完整 Base 评测采用 4096-token 响应预算，这两轮训练评测采用 1024；没有匹配的全量 step0 对照，不能直接相减归因训练收益。

冻结教师两轮均未记录空 reasoning 或整步零监督跳过，响应长度仍从首批约 223 tokens 降至约 165–170。此前随 Student 更新的 Teacher 版本出现了大量空 reasoning；本次只能支持“这些冻结教师运行未复现该退化”，还不能锁定唯一原因。

新 30 题诊断的独立 rollout 成功数为 Base **15/30**、L1 **20/30**、L2 **26/30**、L3 **25/30**。这不是全量验证集成绩，也不是训练后的成绩。L2 的 KL 在 27/30 题高于 L3，且平均 hint 长度远大于另两层；语义层级、文字长度、实际分布变化应分开衡量。

## 分层与可审查数据

- [当前 L1 / L2 / L3 设计、完整提示词、历史 Oracle 命名对照](../../hint_levels_20260917.md)
- [同一 Base 状态上的三层真实 hint 与完整 GLM 公共输入](public_hint_kl/hint_examples_same_state.md)
- [30 题、120 条独立轨迹浏览器](public_hint_kl/viewer.html)：下载后在浏览器打开；保留英文原始输出。
- [120 条完整轨迹 JSONL.gz](public_hint_kl/full_trajectories_30x4.jsonl.gz)、[992 个打分输入 JSONL.gz](public_hint_kl/scoring_inputs.jsonl.gz)、[逐 turn KL JSONL.gz](public_hint_kl/turn_kl_metrics.jsonl.gz)
- [训练逐题评测结果](frozen_teacher_training/evaluation_episodes.jsonl)、[指标 CSV](frozen_teacher_training/evaluation_metrics.csv)、[L3 每 turn Oracle/hint/Student 轨迹](frozen_teacher_training/traces/l3_training_step_000050.md)
- [原始来源与 SHA-256](source_manifest.json)、[离线核验脚本](verify_publication.py)、[发布文件校验清单](MANIFEST.sha256)

训练报告包含公共配置快照和当时的输入代码，KL 报告包含实际打分源码。它们记录运行事实，不会把未提交的其他实验代码混入本次归档。没有发布权重、认证文件或 API key。逐 token 指标和全部 API 请求响应仍在本地完整证据包，Git 中给出了该包的大小与哈希；这里不提供无法访问的下载链接。

## 本次更新边界

此次只整理、核验和发布已有结果，没有重新训练、调用 hint API 或运行 GPU 推理。两个 OPD 训练状态来自各自最后的暂停记录；报告中的机器/GPU 状态快照只代表记录日期。原始训练仍未完成计划的 223 步。
