# 用户提供的 fast 版本：五步训练验收

代码来源：`/mnt/disk4/zhangboyao/hint-ladder-verl-fast`，用户提交 `1decc33`，基于 `592c9ee`。目标是验证5个真实 trainer step及最后一次完整 seen/unseen 评测，不自动转入223步全量训练。

## 启动前检查

- 在已验证的 `hintladder-runtime:verified-20260908` 镜像中运行 `pytest tests/hintladder -q`：**85 passed**，两项依赖弃用警告。
- 同一 GLM 网关、相同10个历史失败状态：**10/10 首次返回 stop**，型号均为 `glm-5.3-flash`，正文28–41个英文词，总completion139–557，2.90–7.76秒。该样本按历史失败选择，不代表全量成功率或质量评测。见 [api_preflight.jsonl](api_preflight.jsonl)。
- GLM保持 thinking 开启、reasoning_effort=low；未采用不可用的 disabled 模式。

## 相对提供版本的必要修复

1. `L0_FAILED` 行除了不插入 hint，还将既有 `sdl_special_token_keep_mask` 置零。测试通过原生 top-k forward KL 和反向传播验证：学生权重变化后，失败行梯度仍为零，其余行仍有梯度。
2. Teacher 阶段等待所有已提交预取任务完成，包含已结束环境多出的状态；`begin_step` 拒绝带未完成请求跨步。训练退出时关闭线程池。
3. thinking=true 显式发送 `thinking: {type: enabled}`；实际返回不同模型时直接报错，不作为 L0 降级。

未改 worker、基础 PPO trainer、rollout loop、环境或 SDL 数学实现。保留提供版本的失败预算 `min(max_count, max(1, floor(states * ratio)))`，当前ratio=1%、max_count=10；其统计分母是当前训练批次所需的去重公开状态。该规则对不足100个状态至少允许1个，与早先严格floor版本不同。

## 本次参数

| 参数 | 值 |
|---|---|
| 模型 / GPU | 原始 Qwen3-4B / 8×A100 80GB |
| 训练面板 | 全量3553个ALFWorld训练游戏，补齐到整批；仅执行前5个trainer step |
| 每步轨迹 | 16个游戏×8次采样=128局 |
| 学生协议 | 原生thinking关闭，显式reasoning/action prompt，50动作，历史2轮，prompt4096，response1024 |
| 采样 | temperature0.6 / top_p0.95 / top_k20 |
| 教师 / hint | 当前学生权重前向评分；GLM在线生成无Oracle L1；学生rollout和评测不接收hint |
| GLM | thinking enabled / effort low / max_tokens768 / 并发128 / timeout25s / retries4 |
| 目标 | PG=0 / SDL=1 / top20 forward KL + tail / LR1e-6 |
| 批量 | PPO mini batch256、1 epoch；评分token16384、更新token12288 |
| 提速 | 持久vLLM作用域、CUDA graph、逐turn预取hint；persist_requests=false |
| 评测 / 保存 | 跳过初始评测；step5完整seen140、unseen134；step1和5保存 |
| W&B | project `alfworld-l1-fast-verify-20260910`，run `fast-5step-seed42-20260910` |

输出：`runs/adopt_fast_20260910/train`。本地启动配置：`configs/local/fast_verify_5step.yaml`，仅本地保存endpoint与凭据文件路径；公开配置见 [config_sanitized.json](config_sanitized.json)。API key不进入公开产物。

## 实际结果

启动前状态：CPU与API检查通过，尚无GPU更新结果。后续以这里的完成步数、metrics和退出状态为准；不能用GPU占用或CPU测试代替真实训练完成。
