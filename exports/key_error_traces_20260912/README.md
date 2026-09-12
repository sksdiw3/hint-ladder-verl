# OPD 关键错误轨迹保留包

先看：[关键错误速览](关键错误速览.md)。

按用户要求，在删除 OPD checkpoint 和大批原始 trace 前整理。原始响应不改写；来源路径、行号和源文件 SHA256 保留供核对。

- `key_error_turns.jsonl`：40 条关键格式错误，覆盖 step 1–110 的选定节点，包括 step 18–22 退化区间；同一类型每节点最多 2 条。
- `training_error_episodes.jsonl`：6 局训练错误轨迹，包含正常 / 空 reasoning 混合局，以及全部 turn 空 reasoning 的局。按 traj_uid 分组、turn_step 排序、去除重复行，保留原始 prompt / output / hint / action。
- `error_timeline.json`：所有已保存格式错误文件的逐步计数，以及 5 个节点从完整 rollout 核对的分母。没有分母的节点不擅自计算比例。
- `base_matched_controls.jsonl`：原始 Qwen3-4B 的题 3、题 7，无 hint / 有 L1 的 4 局对照。成功对照用于区分 base 表现和训练后格式退化。
- `failure_casebook_C1_D1.jsonl`：一局接近成功但关键动作失败，一局搜索方向错误。
- `earlier_format_failure/`：较早格式错误审计中已精选的错误轨迹与报告。
- `closure_distribution/`：reasoning 闭合位置的 16 个精选 prefix / 分布例子、少量续写对照和汇总；不是全量分布缓存。
- `top32_overlap/`：刚完成的 top-32 重叠汇总和 6 个例子；全量逐 token logits 已列入删除。
- `distribution_example_prompts.jsonl`：3 个分布例子的完整 student / teacher prompt、hint 和原始 token IDs。
- `base_identity/`、`metrics.jsonl`、`config_sanitized.json`：模型身份、训练曲线和实验参数。

训练日志中的 step 是该轮 rollout / 更新的记录步号，不能自动等同于 rollout 使用了更新完成后的同号 checkpoint。格式错误样例中若没有匹配的完整 rollout，只有原先保存的输出、动作和任务来源，不补造缺失 observation。

## 逐节点核对

| 记录 step | 轨迹数 | 去重 turn 数 | 空 reasoning | 全部格式错误 |
|---:|---:|---:|---:|---:|
| 5 | 128 | 4644 | 0 | 4 |
| 10 | 128 | 5000 | 0 | 11 |
| 20 | 128 | 4328 | 3890 | 3894 |
| 50 | 128 | 5220 | 5188 | 5220 |
| 110 | 128 | 4323 | 4278 | 4321 |

批量原始轨迹清理后，旧报告中的全量轨迹链接可能失效；以本目录实际保留文件为准。模型 checkpoint 按用户要求全部删除，训练保持暂停。
