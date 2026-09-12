# 单条 turn 的全部 prefix 分布

[完整 turn 与 105 个位置的 top-10](完整turn_逐prefix_top10.md)

[JSONL](prefix_top10.jsonl) · [CSV](prefix_top10.csv) · [完整 turn](turn.json)

Qwen3-4B base；训练集题 7 / turn 1。105 个 response 预测位置，两侧使用相同学生 prefix。此包是删除旧批量缓存后，按用户新请求补算的一条诊断。

GitHub 发布保留数值、prompt、完整 Markdown 和评分脚本；本地界面预览 HTML/PNG 与其原始清单不包含在此次发布中。发布文件用 [PUBLIC_MANIFEST.sha256](PUBLIC_MANIFEST.sha256) 校验。`viewer_validation.json` 是此前本地交互页面的历史验证记录，不代表 GitHub 上提供了交互页面。
