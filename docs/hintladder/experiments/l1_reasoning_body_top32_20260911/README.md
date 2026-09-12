# 全量在线 L1：reasoning 正文监督，teacher top-32 + tail

状态：已按用户要求于2026-09-12 00:29（UTC+8）暂停，完成110/223个记录步，其中42步因零监督跳过optimizer。随后所有OPD checkpoints和批量trace已按要求删除；保留指标与精选轨迹，不自动恢复。

**完整结果以 [2026-09-12 实验报告](../../../../实验报告_20260912.md) 为准**：[8局真实完整轨迹](report_20260912/真实轨迹.md)、[110步数值日志](../../../../exports/key_error_traces_20260912/metrics.jsonl)、[逐步统计](report_20260912/summary.json)。step19开始大量空reasoning，step22首次整批零监督；最后完整评测step100为Seen53/140=37.86%、Unseen46/134=34.33%。下文首步和checkpoint描述是启动时的历史快照，不表示文件现在仍存在。

## 本次变更

相对于 [top-20 reasoning-body 配置](../../../../configs/experiments/l1_reasoning_body_20260911/train_full.yaml)，唯一训练超参数变化是：
```yaml
actor_rollout_ref.actor.sdl_topk: 32
```

其余配置差异只有输出目录、Ray 临时目录及 W&B run 标识。保持 forward KL、tail 桶、reasoning 正文 mask、Teacher prompt、GLM hint prompt，以及采样 top-k=20。具体配置见 [train_full.yaml](../../../../configs/experiments/l1_reasoning_body_top32_20260911/train_full.yaml)。

## Teacher 和监督契约

Student rollout 不接收 hint。Teacher 是同一当前 Qwen 权重，使用 Student 原始 prompt 加当前 L1 hint 与简短使用说明；在 Student 实际生成的相同 prefix 下评分。移除新增便签和说明后必须逐字恢复 Student prompt。

只对完整有效响应中 reasoning 正文的预测位置计算直接 KL。排除 reasoning 标签、整个 action 块、标签外文本及特殊 token；跨标签边界的 BPE token 整个排除。格式错误行过滤，预算内 hint 失败行零监督。共享参数更新仍可间接影响标签和动作生成。

损失为 teacher top-32 显式 token 加其余词表的一个 tail 概率桶，方向 teacher→student forward KL。PG=0、SDL=1，response_token_mean 分母沿用原 response 有效 token 数。

## 运行参数

| 项目 | 设置 |
|---|---|
| 初始模型 | 原始 Qwen3-4B，resume disabled |
| 训练任务 | 3,553 个不同官方 train 游戏，末批补 15 条重复项，总计 3,568 行 |
| 训练步数 | 1 epoch，223 steps |
| 每步 rollout | 16 题 × 8 次 = 128 局 |
| GPU | 8 × A100-SXM4-80GB；FSDP，rollout TP=1 |
| 优化 | LR 1e-6，1 PPO epoch，mini-batch 256 turn rows |
| Student 采样 | temperature=0.6，top-p=0.95，sampling top-k=20 |
| 上下文与长度 | history=2，不累计 assistant reasoning；最多50 turns，prompt≤4096，response≤1024 |
| thinking 与输出 | Qwen 原生 thinking 关闭，显式 reasoning/action prompt |
| L1 hint | glm-5.3-flash，thinking=true，effort=low，max_tokens=768，concurrency=128 |
| hint 输入 | task、current observation、最近两个 executed actions；无 oracle |
| hint 失败 | timeout25秒，最多4次；每步失败状态预算 min(1%,10)，预算内零监督 |
| 显存配置 | old-logprob max tokens/GPU=16384；actor update=12288；vLLM memory utilization=0.3 |
| 评测 | 无 hint；每25步及最终步，完整 seen140/unseen134 分开记录，每题1次 |
| 初始评测 | 跳过；历史4096-token base成绩不是本轮1024-token配置的严格对照 |
| 保存 | step1和每5步 checkpoint，保留最近3个；trace每5步及最终步 |
| 输出目录 | runs/l1_reasoning_body_top32_20260911 |
| W&B project | alfworld-l1-reasoning-body |
| W&B run | base-l1-reasoning-body-top32-20260911 |

W&B：[本次 run](https://wandb.ai/2606478269-ustc/alfworld-l1-reasoning-body/runs/base-l1-reasoning-body-top32-20260911)。

## 检查与复现

本次 `pytest tests/hintladder -q`：108 passed。当前相关测试结果、源码哈希、公开配置和启动清单保存在本目录及本地 run 目录。此前同一 mask/prompt 实现已在412条实际响应上验证，详见 [原始 token 审计](../l1_reasoning_body_20260911/mask_audit.json)；这是复用的实现验证，不是本次训练结果。

本地启动器：runs/l1_reasoning_body_top32_20260911/launch.py。公开配置的 API endpoint 是占位符；本地 configs/local 配置复用已授权的服务地址。凭据通过只读 secrets 和 netrc 挂载，不包含在公开文件中。

本地完整控制台日志：runs/l1_reasoning_body_top32_20260911/training.log。
逐 step 数值：runs/l1_reasoning_body_top32_20260911/train/metrics.jsonl。


## 首步运行证据（2026-09-11 17:42 UTC+8）

第1/223步完成；step1 checkpoint 已验证8份模型、8份optimizer、8份extra state，以及data.pt、预算状态和Hugging Face权重齐全。原始指标见 [step1_metrics.json](step1_metrics.json)。

| 项目 | 实测 |
|---|---:|
| 整步秒数 | 524.508888 |
| Rollout秒数 | 247.874071 |
| Old-logprob秒数 | 36.269699 |
| Teacher forward秒数 | 69.051121 |
| Actor update秒数 | 143.393954 |
| 保存秒数 | 15.681044 |
| Hint额外等待秒数 | 0.173260 |
| 监督正文token数 | 1259648.000000 |
| Hint失败状态数 | 0.000000 |
| 训练batch成功率 | 0.054688 |

本批训练成功率为7/128=5.47%，来自首次更新前采样，不是训练后 held-out 成绩。首次完整 seen/unseen 评测按配置在step25执行。首步时间包括保存，不包括启动初始化；不能用一个step精确预测全量时间。
