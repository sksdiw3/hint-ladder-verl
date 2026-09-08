# Qwen3-4B 在 ALFWorld 上的论文对照

核查日期：2026-09-08。以下是围绕当前实验核查的六篇论文，不是穷尽检索或同协议排行榜。数值均来自论文原文；“原始”指未进行该论文额外的任务适配，不等于未经指令训练的预训练模型。

| 论文与来源 | Backbone | 原始 / 无 skill 对照 | 额外训练或增强后的 ALFWorld 成功率 |
|---|---|---|---|
| [ATOD，Table 1](https://arxiv.org/html/2606.27814) | Qwen3-4B | Vanilla **24.22%** | GRPO **76.56%**；OPD **80.47%**；ATOD **85.16%** |
| [D2Skill，Table 1](https://arxiv.org/html/2603.28716) | Qwen3-4B-Instruct-2507 | Origin **17.2%** | GRPO **53.9%**；D2Skill(O3) **72.7%**。独立的 SFT 起点为 **47.7%**，SFT + D2Skill 120 步为 **95.3%** |
| [SAPO，Table 6](https://arxiv.org/html/2606.08755) | Qwen3-4B-Instruct-2507 | Origin **17.2%** | SAPO **82.0%** |
| [MASA，Table 1](https://arxiv.org/html/2605.30723) | Qwen3-4B | No Skill **17.1%** | 推理时加 MASA skill 后 **31.4%**；这行不是 agent policy 的 RL 结果 |
| [T²PO，Table 1](https://arxiv.org/html/2605.02178) | Qwen3-4B / Qwen3-4B-RFT | 主表未列原始 4B；SFT 后 **64.06%** | 从 RFT 模型开始：GRPO **77.35 ± 0.62%**；GiGPO **80.47 ± 2.43%**；T²PO **90.23 ± 1.38%** |
| [From History to State，Table 1](https://arxiv.org/html/2605.05413) | Qwen3-4B | 主表未列 | SFT seen/unseen **59.5 ± 3.5% / 56.7 ± 3.3%**；SFT+RL **76.4 ± 1.5% / 81.3 ± 1.9%** |

SAPO 和 D2Skill 列出的部分基线数值相同，不能计为两次独立复现。原版 Qwen3-4B 与 Qwen3-4B-Instruct-2507 也不能视为同一个 checkpoint。

## 与本次实验的协议差异

| 设置 | 本次 Hint Ladder | T²PO | D2Skill | ATOD |
|---|---|---|---|---|
| 初始模型 | 原版 Qwen3-4B，无 ALFWorld SFT/RFT | RL 从 RFT checkpoint 开始 | 区分原始与 SFT 两组 | 主表含 Vanilla Qwen3-4B |
| 最大交互步数 | **30** | **50** | **50** | **50** |
| 最大响应 token | **64** | **500** | **512** | **512** |
| 历史长度 | **2** | **2** | **2** | 本次未确认准确值 |
| 推理输出 | 禁止生成 think 标签，只输出 action | thinking budget 450 | 本次未独立确认完整输出契约 | 配置表写 enable thinking Off，但附录 prompt 要求 think 标签 |
| 验证 | 固定 seen/unseen 各 128 题，Avg@4 | validation batch 128；不能据此认定与本次 panel 相同 | 128 held-out 任务，报告训练期最好分数；验证仍检索 skill | validation batch 128；具体 panel 未与本次逐题对齐 |

参数来源：[T²PO Appendix A/B](https://arxiv.org/html/2605.02178#A2)、[D2Skill Appendix C](https://arxiv.org/html/2603.28716#A3)、[ATOD Appendix C/D](https://arxiv.org/html/2606.27814#A3)。这里将文中不明确的信息保留为未确认，不用猜测补全。

T²PO 的 RFT 先用原始模型采样，再按环境结果筛选高质量轨迹做监督微调。这与直接从原版模型开始 SDL 的初始化不同。[原文 Appendix B.1](https://arxiv.org/html/2605.02178#A2.S1)

## 对当前结果的解释边界

当前基座 seen/unseen **7.62% / 2.93%** 数值上低于上述几个原始模型对照，但尚不能把差距归因于某一个配置。尤其不能单凭“2 步历史”或 enable_thinking 开关解释：T²PO/D2Skill 同样用 2 步历史，ATOD 的开关与显式 prompt 又不是同一概念。

应先对齐模型版本、实际 prompt / action parser、步数预算、响应预算、任务列表、采样次数和 checkpoint 选择规则，再比较方法收益。D2Skill/MASA 的推理时 skill 增强与本项目的 clean Student 评估具有额外信息差异。当前损失下降不能证明达到论文中的任务成功率。

推荐审查顺序：T²PO 的 SFT/RFT 标记 → ATOD 的 Vanilla 对照与提示词 → D2Skill 的模型版本和 SFT 分组 → MASA 的推理时额外信息 → From History to State 的 seen/unseen 列。
