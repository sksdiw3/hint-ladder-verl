# 在线 L1 训练：提速版

基线 `592c9ee` 的在线 L1 运行一步约 9 分钟，只跑 16 局。本目录的 `train_full_fast.yaml` 和配套代码把一步的局数提到 128，并将 GLM 请求与 rollout 重叠。目标函数和 prompt 保持一致，但轨迹量和最大响应预算改变，不能当作完全相同预算的实验。

最新验收：[8 卡五步报告](../../../docs/hintladder/experiments/fast_verify_20260910/REPORT.md)。失败行已补充原生 SDL mask，预取请求必须在下一步前完成；85 项 CPU 测试、10 条真实 API 探针通过。下文速度数字仍为预期，实际吞吐以报告为准。

## 慢在哪里

前三步实测（`docs/hintladder/experiments/l1_online_full_20260910/metrics_snapshot.jsonl`）：整步 557 s，其中 Student rollout 470 s 占 84%，GLM hint 37 到 216 s 串在 rollout 之后。上一轮 L3 运行 128 局一步只要 107 s 的 rollout。每局成本涨了 35 倍，原因有三个：

1. `env.rollout.n` 从 8 改成了 1，一步 16 局，每卡只解码 2 条序列。解码是显存带宽瓶颈，2 条和 16 条的每步耗时几乎一样，GPU 在以 1/8 的利用率工作。PG=0 时组大小不进损失，这个改动对实验没有意义。
2. 响应从 13 token 变成带推理的 220 token，轮数从 30 到 50，一局串行解码约 1.1 万 token。这部分不可压缩，只能靠并行局数摊薄。
3. `keep_engine_awake_during_multiturn` 没开。每一轮都重新进入 vLLM 的 sharding manager：同步权重、唤醒 KV、生成、`sleep(level=1)`、清缓存，与 `free_cache_engine` 无关。一局 49 个来回，约 3 s 一个。

放大器：`enforce_eager: true` 关掉了 CUDA graph；一条跑到 4096 token 的失控响应会让那张卡上所有序列等它两分钟；GLM 请求超时 180 s、重试 12 次，一个坏请求能卡住一步十几分钟。

## 改了什么

### 配置（`train_full_fast.yaml`）

| 键 | 旧 | 新 | 理由 |
|---|---:|---:|---|
| `env.rollout.n` | 1 | 8 | 128 局/步，每卡 16 条。rollout 墙钟时间基本不变，每局成本降约 8 倍 |
| `rollout.keep_engine_awake_during_multiturn` | 未设 | true | 每局一次权重同步和唤醒/休眠，省约 150 s/步。仓库已实现，只是没启用 |
| `rollout.enforce_eager` / `free_cache_engine` | true / false | false / false | 开 CUDA graph。`vllm_rollout_spmd` 断言两者不能同为 false/true 以外的组合 |
| `data.max_response_length` | 4096 | 1024 | 正常最大 440，均值 220；把最坏一轮从 2 分钟压到约 30 s |
| `rollout.max_num_batched_tokens` | 8192 | 16384 | 16 条约 500 token 的 prompt 一次 prefill |
| `rollout.log_prob_max_token_len_per_gpu` | 8192 | 16384 | 32768 会 OOM：熵计算把全词表 logits 落成 fp32 |
| `actor.ppo_max_token_len_per_gpu` | 8192 | 12288 | 128 局后每卡约 700 行，更大的 micro-batch 提高利用率；`perf/max_memory_allocated_gb` < 62 再试 16384 |
| `env.alfworld.val_parallelism` | 64 | 140 | 每个 split 一波跑完，unseen 134 走 partial wave |
| `trainer.rollout_dump_freq` | 1 | 5 | 128 局的 dump 约 40 MB |
| `online.timeout` / `retries` | 180 / 12 | 25 / 4 | 中位请求 4 s，无重试时最大 19 s |
| `online.max_tokens` | 4096 | 768 | 网关返回隐藏推理 token，中位 205、最大 872；160 会大量截断 |
| `online.concurrency` | 64 | 128 | 预取后在途数更平滑 |
| `online.thinking` / `reasoning_effort` | 默认 / low | true / low | 明确写出：thinking 开、强度低 |
| `online.failure_budget_ratio` / `failure_budget_max` | 无 | 0.01 / 10 | 见下面的失败处理 |
| `online.persist_requests` | 无（等价 true） | false | 每步约 7000 个小文件只对步内恢复有用；hint 已随 rollout dump 归档 |

不变：`train_batch_size 16`、50 步、2 步历史、prompt 4096、采样参数、`enable_thinking=False`、L1 prompt 与插入点、同步教师、PG=0 / SDL=1、top-20 forward KL、lr、mini batch 256、223 步、每 25 步验证保存、seen 140 / unseen 134。

`train_full.yaml` 只改了 API 三个参数（timeout、retries、max_tokens），其它保持为历史配置。

### 代码

四个文件，都是小改动：

- `hintladder/online_l1.py`：`OnlineL1Provider` 重写。持久线程池；`begin_step(step)` 在每步 rollout 前重置；`prefetch(prompts)` 非阻塞提交；`prepare_prompts(prompts)` 只等尾巴。重试时 seed 递增，避免同一个 seed 反复撞上同一段长推理。失败处理见下。
- `verl/trainer/ppo/hint_ladder_ray_trainer.py`：新增 `PrefetchingRolloutProxy`，套在 worker group 外面只截获 `generate_sequences`，每一轮生成前把这一轮的 prompt 解码后交给 `prefetch`，其它属性透传。只用于训练 rollout；验证走原 worker group，并在验证前后断言没有新增请求。
- `hintladder/teacher_prompt.py`：`build_teacher_batch` 只做一次 decode/encode 校验；把每行的 hint 和等级写进 `online_l1_hint`、`online_l1_level`。
- `hintladder/config.py`：online 参数范围校验，`timeout ≤ 60`、`retries ≤ 6`、`max_tokens ≤ 1024`，防止把 180/12 改回去。

没有改 `rollout_loop.py`、`fsdp_workers.py`、`dp_actor.py`、`ray_trainer.py`、环境代码。

### 失败处理

任何一条外部 API 的尾部事件都不该杀掉一个几十小时的运行。某个公开状态在 `retries` 次后仍拿不到合格 hint：

- 它的所有行按 **L0** 处理：不插便签，并将原生 SDL token mask 置零。即使前面的 optimizer minibatch 已改变学生权重，这些行的损失贡献和梯度仍为零。
- 每步预算 `min(failure_budget_max, max(1, 状态数 × failure_budget_ratio))`，超出才 raise。`failure_budget_max: 0` 恢复严格模式。
- 失败逐状态写进 `online_hints/step_XXXXXX/<key>.errors.json`，逐行计入 `hint_ladder/hint_failed_rows`，等级标为 `L0_FAILED`。
- 401 这类非重试 HTTP 错误立即抛出，那是配置错误不是尾部事件。

## 怎么跑

```bash
# 复制一份本地配置，填 endpoint；密钥只放 .secrets/ 下的文件
cp configs/experiments/l1_online_full_20260910/train_full_fast.yaml configs/local/l1_online_fast.yaml
# 编辑 configs/local/l1_online_fast.yaml 里的 base_url、api_key_file、输出目录

export ALFWORLD_DATA=/path/to/alfworld
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
python -m pytest tests/hintladder -q
python -m hintladder.cli train-student --config configs/local/l1_online_fast.yaml --seed 42 --checkpoint /models/Qwen3-4B
```

先跑 5 步冒烟（临时把 `trainer.total_training_steps` 和 `test_freq` 设成 5），确认下面的指标再跑全量。

## 盯什么

| 指标 | 期望 |
|---|---|
| `timing_s/gen` | ≤ 300 s，128 局 |
| `timing_s/step` | ≤ 8 min，含 8 倍于旧运行的数据 |
| `hint_ladder/hint_wait_seconds` | ≤ 20 s。这是留在关键路径上的 hint 时间；旧的 `hint_seconds` 已改名 |
| `hint_ladder/hint_prefetch_misses` | 0 |
| `hint_ladder/hint_request_p95_seconds` | ≤ 15 s |
| `hint_ladder/hint_failed_rows` | 接近 0；持续非零说明网关有问题 |
| `hint_ladder/level_counts/L1` 与 `L0_FAILED` | 后者应极少 |
| `response_length/clip_ratio` | < 0.5% |
| `perf/max_memory_allocated_gb` | < 62，决定能否升 `ppo_max_token_len_per_gpu` |
| 5 步无 `none_dealloc` | 否则把 `enforce_eager` 改回 true |

`hint_ladder/hint_span_seconds` 不存在了：预取后请求跨度和 rollout 重叠，没有独立意义。

## 预期

| | 旧运行 | 提速后 |
|---|---:|---:|
| 每步局数 | 16 | 128 |
| rollout | 470 s | 200 到 280 s |
| hint 关键路径 | 40 到 216 s | ≤ 20 s |
| 整步 | 9.2 min | 6 到 8 min |
| 每局成本 | 34.5 s | 3 到 4 s |

rollout 估算：CUDA graph 下 4B 模型每步解码约 15 ms，220 token 约 3.3 s 一轮，49 轮约 160 s，加 prefill 和一次同步。剩下的时间是 128 局带来的 old_log_prob、教师前向和更新，那是数据量的代价。

## 没做的事

- 不改 rollout 循环的逐轮同步结构，也不做异步逐轨迹 rollout。同 128 局下收益只有 1.5 倍左右，风险不小，另有方案文档。
- 不跳过已结束的环境：解码时间取决于串行步数不是行数，一张卡上只要还有一个活跃环境，这一轮就不会更快。
- 不改 `max_steps`、历史长度、prompt、采样温度，那是协议。

## 验证状态

CPU 测试在 `tests/hintladder/test_online_l1.py`（去重与 seed、预取零 miss、预算内失败转 L0、超预算终止、非重试错误直接抛出、代理先预取后委托）和 `test_config.py`（fast 配置组合、API 参数范围）。本次改动在无 GPU、无 numpy/torch 的机器上完成，跑过 `py_compile`、配置校验和一份等价的纯标准库测试；`pytest` 和 GPU 冒烟需要在训练镜像里执行。
