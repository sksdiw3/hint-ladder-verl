# 在线 L1：只监督 reasoning 正文

2026-09-11 17:09:56（UTC+8）启动新的全量实验，从原始 Qwen3-4B 开始，未恢复旧 step20 checkpoint。W&B：[base-l1-reasoning-body-20260911](https://wandb.ai/2606478269-ustc/alfworld-l1-reasoning-body/runs/base-l1-reasoning-body-20260911)。运行目录 `runs/l1_reasoning_body_20260911`；本地完整日志 `training.log`。**已按用户要求于17:20:22暂停。尚无完整step指标或checkpoint；首步rollout产生6,236个turn，2行格式错误已过滤，首个完整step结束前终止。本轮不作为完成训练的结果，不自动恢复。**

## 教师输入

Student 每轮仍使用同一个 ALFWorld 显式 reasoning prompt：任务、最近两步原始 observation/executed action、当前 observation、admissible actions，以及 `<reasoning>...</reasoning><action>...</action>` 格式要求。原生 Qwen thinking 关闭；不累计之前 assistant 的推理。

Qwen Teacher 在 Student 输入的任务/历史交界处插入当前 L1 hint：

```text
<private_teacher_note>
{current_L1_hint}
</private_teacher_note>
Use this hint as optional guidance for your reasoning; check it against the current observation and admissible actions. Keep the required response format and do not mention the hint.
```

其余输入文本、角色及原生空 think 前缀保持一致。删除这段新增文本后，必须逐字恢复 Student prompt；412 条真实输入也通过了移除便签后的原始 token ID 一致性检查。Teacher 使用同一当前 Qwen 权重，在 Student 已采样的响应 prefix 下评分，不另生成一段教师轨迹。

GLM hint 生成器保持此前设置及 `configs/experiments/l1_online_full_20260910/l1_prompt.txt`。它接收任务、当前观察、最近两个执行动作，不接收 oracle、历史观察或学生响应。上述 Qwen Teacher prompt 与 GLM hint 生成 prompt 是两个不同输入。

## 监督范围与数值

新增 `actor_rollout_ref.actor.sdl_loss_token_scope: reasoning_body`。只对完整、格式合格响应中 `<reasoning>` 和 `</reasoning>` 之间的原始响应 token 计算直接 OPD loss。排除两个 reasoning 标签、整个 action 块及标签外空白、EOS/PAD 等特殊 token。正文内部空白可被监督；跨越正文/标签边界的 token 整个排除。

```text
<reasoning>      正文内容      </reasoning>  <action>动作</action>
    mask=0       mask=1          mask=0           mask=0
```

边界从实际采样 token IDs 的前缀解码确定，不重新分词后套索引。掩码与既有格式有效、hint 成功、response 有效掩码取交集，再交给原生 actor 的 SDL keep mask；padding/reordering 后仍逐行对齐。格式异常和预算内 hint 失败的行零监督；整批无监督时不调用 optimizer。

损失仍为 teacher→student 的 top-20 forward KL 加 tail bucket，PG=0、SDL=1、entropy penalty=0。沿用 `response_token_mean`，分母包含原响应有效 token，未放大剩余正文 token 的权重。被排除预测位置没有直接 KL 项，但共享权重的更新仍可能改变标签和动作的概率，不能保证格式不再退化。

W&B 保留 entropy/top1（rollout temperature=0.6 下的全词表分布）和格式异常率，新增/保留 `hint_ladder/reasoning_body_tokens`、`active_tokens_step`、`supervised_token_ratio`、`actor/sdl_token_scope_reasoning_body`。训练 trace 增加每行 `sdl_reasoning_body_tokens`、`sdl_supervised_tokens`。

## 实验参数

| 参数 | 设置 |
|---|---|
| 初始模型 | 原始 Qwen3-4B；resume disabled |
| 训练集 | 3,553 个不同官方训练任务；末批补齐 15 条重复项，共 3,568 行 |
| 每步采样 | 16 道题 × 每题 8 次 = 128 局 |
| 训练计划 | 1 epoch，223 steps |
| GPU | 8 × A100-SXM4-80GB，FSDP；rollout TP=1 |
| 学习率 | 1e-6，PPO epochs=1，mini-batch=256 turn rows |
| Student | temperature=0.6，top-p=0.95，top-k=20，最多 50 turns |
| 上下文 | history=2，prompt≤4096，response≤1024，max model len=8192 |
| GLM | glm-5.3-flash，thinking enabled，effort=low，max_tokens=768，concurrency=128 |
| GLM 失败处理 | timeout=25秒，最多4次；失败状态预算 min(1%, 10)，预算内置 L0 |
| 评测 | 每25步及最终步：完整 seen 140 / unseen 134 分开；每题一次，无 hint |
| 初始评测 | 按用户之前要求跳过；历史 4096-token base 评测不能直接作为本轮 1024-token 配置的严格同协议基线 |
| 保存 | step1及每5步保存，保留最近3个；trace每5步及最终步 |
| 临时文件 | 本 run 的 disk4 `tmp/` 挂到容器 `/tmp` |

[公开配置](../../../../configs/experiments/l1_reasoning_body_20260911/train_full.yaml) 中 API endpoint 为占位符，凭据仅通过忽略的本地 secrets 挂载。

## 验证

- `pytest tests/hintladder -q`：108 passed，包括原生 forward KL 反向传播验证正文有梯度、闭合标签/动作预测位置零梯度；跨标签 BPE、中文、截断和错误格式。
- [真实 token 审计](mask_audit.json)：412 条响应，95,764 个有效 token，87,246 个正文监督 token；412/412 与 fast tokenizer 原始 offset 独立核对一致；闭合标签及 action 被选中数均为0。构建掩码耗时0.63秒。
- 本地 `runs/l1_reasoning_body_20260911/mask_audit_rows.jsonl` 提供逐行计数及10组完整 Student/Teacher prompt、响应及所选正文。
- 本地 `runs/l1_reasoning_body_20260911/` 曾保存启动清单和差异；本次实现及配置已随 [2026-09-12 总报告](../../../../实验报告_20260912.md) 发布。后续 top-32 运行的[公开启动清单](../l1_reasoning_body_top32_20260911/launch_manifest.json)保存相同核心实现的源文件哈希。历史批量 trace 和 checkpoints 已清理，当前可用证据以总报告链接为准。
