# 训练响应格式错误：过滤SDL监督并继续

2026-09-11修复。前一轮已完成step23，step24因`Student emitted forbidden thinking tags`硬断言退出。用户要求格式错误过滤或重新rollout，本次采用逐turn过滤监督。

格式检查要求当前配置声明的输出结构：显式reasoning模式为一个非空`<reasoning>`块后接一个非空`<action>`块，action-only模式为一个`<action>`块；不允许原生think标签、截断/多余块或块外附加正文。只判断输出格式，不判断动作是否能成功：格式正确但选错动作仍保留监督。

坏格式turn的`sdl_special_token_keep_mask`整行置零，与已有L0_FAILED掩码取交集。保留原始token、执行动作、轨迹和任务成功率分母，不重写回答、不事后替换动作、不丢弃同一轨迹的其他正常turn。原来的response-token归一化分母保持不变，剩余token的监督权重不会被放大。

整批没有有效SDL token且PG=0时，跳过`update_actor`，因此不更新AdamW动量、权重衰减或学习率调度器，并记录`hint_ladder/update_skipped_no_supervision=1`；该批仍消耗数据批次、记录其step，但不能计作一次真实参数更新。累计有效监督token不增加。批次中正常行仍使用原生SDL计算，坏行贡献零梯度。

格式异常在每个step保存到`format_errors/step_XXXXXX.jsonl`，包含原始回答、原因、traj_uid、turn_step和实际执行动作。W&B记录`hint_ladder/format_invalid_rows`、`format_total_rows`及`format_invalid_ratio`；这些计数在分布式对齐补行前统计。常规训练trace增加`sdl_format_valid`和`sdl_format_error`列。

训练环境和评测的action解析规则、题目数、成功判定均未改变。私有hint泄漏、张量对齐及非有限数值等真正的实现错误仍报错。

验证：`pytest tests/hintladder -q` **99 passed**。包含原生top-k forward KL及反向传播的零梯度测试、整批无监督时不调用优化器、格式识别与错误轨迹落盘、补行/重排后标记对齐。使用已验证镜像`hintladder-runtime:verified-20260908`，未改worker和损失数学实现。

已于2026-09-11 11:29（UTC+8）启动：从`runs/l1_full_diskfix_20260911/train/global_step_20`继续到223。保留8卡、每步128局、GLM-5.3-Flash并发128、thinking enabled/effort low/max_tokens768、history2/response1024、LR1e-6、PG0/SDL1。临时目录挂到disk4，每5步保存、保留3个checkpoint，每25步及最终步完整seen/unseen评测。使用新run保存重跑的21–23步，旧失败运行保留。

复查旧训练trace发现明显格式退化：step10有5006/5032行符合完整结构；step15仅121/5056；step20仅136/4816。Step20的4680个不合格响应全部缺少`</reasoning>`，其中38条还缺少`</action>`；该批没有think标签。环境只要求能抽取合法action，因此很多缺reasoning闭合标签的回答仍能执行。此次SDL过滤采用prompt声明的完整格式，评测和环境解析继续沿用原规则。该差异已告知用户：从step20恢复时可能只有很少响应参与监督，不能把零崩溃或过滤后的低loss视为能力提升。

11:37（UTC+8）实测：已完成恢复后的step21，并继续执行step22。Step21耗时321.02秒，其中rollout 127.64秒、old log-prob 27.65秒、teacher forward 45.03秒、actor update 109.74秒。5684/5844个turn格式不合格（97.26%），均缺少`</reasoning>`，其中166个还缺少`</action>`；160个turn格式合格，最终有效监督token为15028。`update_skipped_no_supervision=0`，grad_norm为0.28756，确认本步完成真实参数更新。

Step21的2234次hint请求没有最终失败，等待尚未完成的预取仅0.17秒。训练成功率为19/128（14.84%）；这属于本批训练rollout，不是验证集成绩。SDL loss为0.00417，但其response-token分母包含大量被屏蔽的行，不能与修复前未过滤的loss直接比较，也不能据此宣称能力提升。此次只通过掩码去掉坏turn的监督，仍计算这些行的前向；未实现重新采样或跳过坏行计算。

最新恢复来源仍为step20，新run首次checkpoint和完整seen/unseen评测计划在step25。当前证据仅覆盖恢复后的一个完整训练step，尚未证明后续全量训练稳定或格式退化得到恢复。

本地运行目录：`runs/l1_format_filter_20260911`。W&B：[full-fast-formatfilter-resume20-20260911](https://wandb.ai/2606478269-ustc/alfworld-l1-online-full-fast/runs/full-fast-formatfilter-resume20-20260911)。本目录保存脱敏配置、启动记录、历史格式审计和step21指标，原始格式错误输出保存在运行目录的`train/format_errors/step_000021.jsonl`。
