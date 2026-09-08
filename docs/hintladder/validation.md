# 验证记录与运行环境

本文件区分原工作区的 GPU smoke 与此次独立源码导出的验证。短 smoke 只证明相应执行链路，不用于宣称能力提升或正式 E1–E4 实验完成。

## 1,500 题 L3 运行与本次发布

2026-09-08 新增 [8 卡 L3 单臂实验快照](experiments/l3_train1500_20260908/README.md)。1,500 条训练 hint 的生成/程序检查已完成；正式运行从原始 Qwen3-4B 开始，快照记录到 step 15。step 0 是基座验证，seen/unseen 为 7.62% / 2.93%；完整训练与训练后能力改善尚未在该快照验证。

本次还同步了 CPU 并行 walkthrough 回放、hint 生成进度保存/恢复和 native 子进程无缓冲输出。运行 `python -m pytest tests/hintladder -q`：**65 passed**，包括新增的真实 spawned-process 顺序检查与注入失败后的生成恢复检查。详细参数、提示词输入和原始指标摘录可从 [审查指南](review_guide.md) 进入。

## 原工作区验证（2026-09-08）

- ALFWorld 官方 walkthrough CPU 回放：固定 train 256、seen 128、unseen 128 个游戏均通过；路径列表随源码保留。
- GLM `glm-5.3-flash`：8 个 smoke 游戏的 L1/L2/L3，共 24 条 hint；另外 8 条 FULLPATH 来自官方 walkthrough。
- 原生 verl Student 训练：Qwen3-4B、2 张 A100、混合四级 hint，完成 1 个真实更新 step，`actor/sdl_loss=0.735323520784732`，累计有效 SDL tokens 为 236，保存了原生 checkpoint。
- 恢复训练：从 step 1 恢复并切换到 2 个游戏的训练列表，在 step 2 达到预算停止。预算 237 tokens，实际累计 368，完整 step 带来的 overshoot 为 131。
- E1：冻结的基座 Qwen3-4B，1 个游戏 × L0/L1/L2/L3 × k=1，每局最多 3 步。共 4 episodes、12 actions；L3 成功，其余三级在步数上限内未成功。另有 12 行参考动作评分，每行包括三视图。

历史产物位置为原工作区的 `runs/train_seed0/`、`runs/train_resume_seed0/` 和 `runs/e1_audit_seed0/`。这些日志、生成内容和 checkpoint 不包含在本仓库中，因此上面的结果是原工作区记录，不是全新 clone 上重跑所得。

历史单任务 E1 summary 生成于 smoke 闸门修正前，曾含 `accepted_for_e2: true`，该标记不能作为正式 E2 准入证据。当前代码对 `stage.smoke: true` 强制禁止准入。没有运行完整 E2 sweep、完整 E3 GPU 课程或 E4 Hinter 训练。

## 原工作区 GPU 主要包版本

以下是执行验证时的环境记录，非从零安装的完整锁文件。CUDA 扩展需要与实际 PyTorch、CUDA 和设备匹配。

| 包 | 版本 |
| --- | --- |
| Python | 3.11 |
| torch | 2.10.0+cu128 |
| vllm | 0.17.0 |
| transformers | 4.57.3 |
| huggingface-hub | 0.36.2 |
| trl | 0.24.0 |
| flash-attn | 2.8.3 |
| flashinfer-python | 0.6.4 |
| compressed-tensors | 0.13.0 |
| xgrammar | 0.1.29 |
| tensordict | 0.6.2 |
| ray | 2.54.0 |
| torchdata | 0.11.0 |
| textworld | 1.7.0 |
| alfworld | 0.4.2 |

上游 `requirements.txt`、`setup.py` 的部分依赖范围与此组合不同。此次发布不更改底层训练框架或重建运行镜像，不能将上游依赖文件当成本次 smoke 的可复现锁文件。

## 独立导出验证

2026-09-08 从独立仓库目录运行 `python -m pytest tests/hintladder -q`：**63 passed，1 个上游 Ray 弃用警告，3.05 秒**。测试覆盖 Teacher token 对齐、hint 合同与覆盖率、预算与恢复状态、真实 Hydra 配置组合、冻结 collector 输入输出以及 E2–E4 编排。

CPU 验证环境：Python 3.11、torch 2.6.0+cu124、transformers 4.56.2、tensordict 0.6.2、hydra-core 1.3.2、pytest 8.4.1。此次导出不会启动 GPU 实验或调用 hint API。
