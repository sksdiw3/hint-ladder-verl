# Reasoning / thinking 实验归档（2026-09-10）

最新全量结果：**valid_seen 41/140 = 29.29%；valid_unseen 41/134 = 30.60%**。原始 Qwen3-4B，关闭原生 thinking，prompt 显式要求 reasoning；无 hint，每题一次，50 步、每步 4096-token 上限，8 卡分题并行。

- [总实验结论与所有 prompt](../../../../实验结论.md)
- [全量评测报告](full_eval/REPORT.md) · [Seen 全部 140 题](full_eval/valid_seen/ALL_RESULTS.md) · [Unseen 全部 134 题](full_eval/valid_unseen/ALL_RESULTS.md)
- [A：10 题原生 thinking](native10/REPORT.md) · [B：10 题要求 think](think10/REPORT.md) · [C：10 题要求 reasoning](reasoning10/REPORT.md)
- [本轮 checkpoint 删除记录](checkpoint_cleanup.json)

每个目录保留配置、任务清单、汇总与验证结果；`run.py` 为产生数据时的执行脚本证据，不是独立可启动安装包。样例为模型原始输出。完整原始轨迹与打包文件保留本地，没有提交模型权重、缓存或全部运行目录。`source_hashes.json` 记录直接复制文件的原始 SHA-256；README、报告与 ALL_RESULTS 的链接针对发布位置作了改写。

三轮 10 题推理均来自 train，不代表全量验证；全量每题一次协议与历史 L3 训练中的 128 题×4次、30步、64-token 响应预算不同，分差不能归因于单一开关，也不是训练带来的提升。
