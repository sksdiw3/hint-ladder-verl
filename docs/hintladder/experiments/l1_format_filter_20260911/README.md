# 训练响应格式错误：过滤SDL监督并继续

2026-09-11修复。前一轮已完成step23，step24因`Student emitted forbidden thinking tags`硬断言退出。用户要求格式错误过滤或重新rollout，本次采用逐turn过滤监督。

格式检查要求当前配置声明的输出结构：显式reasoning模式为一个非空`<reasoning>`块后接一个非空`<action>`块，action-only模式为一个`<action>`块；不允许原生think标签、截断/多余块或块外附加正文。只判断输出格式，不判断动作是否能成功：格式正确但选错动作仍保留监督。

坏格式turn的`sdl_special_token_keep_mask`整行置零，与已有L0_FAILED掩码取交集。保留原始token、执行动作、轨迹和任务成功率分母，不重写回答、不事后替换动作、不丢弃同一轨迹的其他正常turn。原来的response-token归一化分母保持不变，剩余token的监督权重不会被放大。

整批没有有效SDL token且PG=0时，跳过`update_actor`，因此不更新AdamW动量、权重衰减或学习率调度器，并记录`hint_ladder/update_skipped_no_supervision=1`；该批仍消耗数据批次、记录其step，但不能计作一次真实参数更新。累计有效监督token不增加。批次中正常行仍使用原生SDL计算，坏行贡献零梯度。

格式异常在每个step保存到`format_errors/step_XXXXXX.jsonl`，包含原始回答、原因、traj_uid、turn_step和实际执行动作。W&B记录`hint_ladder/format_invalid_rows`、`format_total_rows`及`format_invalid_ratio`；这些计数在分布式对齐补行前统计。常规训练trace增加`sdl_format_valid`和`sdl_format_error`列。

训练环境和评测的action解析规则、题目数、成功判定均未改变。私有hint泄漏、张量对齐及非有限数值等真正的实现错误仍报错。

验证：`pytest tests/hintladder -q` **99 passed**。包含原生top-k forward KL及反向传播的零梯度测试、整批无监督时不调用优化器、格式识别与错误轨迹落盘、补行/重排后标记对齐。使用已验证镜像`hintladder-runtime:verified-20260908`，未改worker和损失数学实现。

恢复计划：从`runs/l1_full_diskfix_20260911/train/global_step_20`继续到223。保留8卡、每步128局、GLM-5.3-Flash并发128、thinking enabled/effort low/max_tokens768、history2/response1024、LR1e-6、PG0/SDL1。临时目录挂到disk4，每5步保存、保留3个checkpoint，每25步及最终步完整seen/unseen评测。使用新run保存重跑的21–23步，旧失败运行保留。
