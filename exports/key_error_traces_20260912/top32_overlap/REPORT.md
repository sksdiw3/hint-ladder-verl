# 有 / 无 L1 hint：Qwen3-4B reasoning 正文 top-32 重叠诊断

在 10 道既有训练题的 412 个有效 turn、87,246 个 reasoning 正文预测位置上，平均 top-32 交集为 **26.57/32 = 83.02%**，top-1 一致率 **86.35%**。

## 比较范围

- 模型是原始 Qwen3-4B，checkpoint_step=0，两侧完全相同权重；没有使用 step20 或 step110 权重。
- 复用既有 no_hint 学生轨迹以及同状态缓存的 L1 hint；每个位置两侧都接原始学生 token prefix。没有比较两条自行展开、已分叉的轨迹。
- 教师 prompt 按当前 teacher_prompt.insert_note 重新构造：学生 prompt + L1 hint + 简短使用说明。remove_note 可精确还原学生 prompt。历史分布缓存的旧版教师提示词没有直接复用。
- L1 由此前的 glm-5.3-flash 生成，生成时 thinking 开启、没有 oracle；此次没有调用 GLM、没有生成新轨迹、没有更新权重。
- 414 个原始 turn 中 2 个没有闭合 reasoning 标签、格式无效，按当前训练 mask 排除；其余 412 个 turn 的所有正文位置均评分。标签、action、EOS、跨边界 BPE token 不计入。
- 位置限定在正文，候选词表仍是完整词表，包括可能预测出的结构符号。原生 Qwen thinking 关闭，显式 reasoning prompt 与原轨迹相同。
- BF16 权重 / 模型计算，FP32 全词表 softmax；没有先执行采样 top-k/top-p 截断。T=0.6 对应当前温度，T=1.0 作为原始 logits 的参考。
- 主统计按 token 位置加权；同一 turn 的连续 token 和同题多 turn 不是独立样本。本结果是 10 题局部诊断，不是全量 benchmark。

## Forward KL 与当前 top-32 损失

定义同一学生前缀下，无 hint 分布为 $p_t(v)$，有 hint 教师分布为 $q_t(v)$。完整 forward KL 为：

$$D_{\mathrm{KL}}(q_t\|p_t)=\sum_{v\in V}q_t(v)\log\frac{q_t(v)}{p_t(v)}.$$

教师分布停止梯度。单个 $q\log(q/p)$ 项可以是负数，但完整 KL 非负。

当前训练令 $S_t=\operatorname{Top32}(q_t)$，将其余词汇合成一个 tail 桶：

$$\ell_t=\sum_{v\in S_t}q_t(v)\log\frac{q_t(v)}{p_t(v)}+q_{t,R}\log\frac{q_{t,R}}{p_{t,R}},\quad q_{t,R}=1-\sum_{v\in S_t}q_t(v),\quad p_{t,R}=1-\sum_{v\in S_t}p_t(v).$$

这里是教师 top-32 支持集；不取教师和学生 top-32 的交集来算 loss，也不把 32 项重新归一化成 1。top-32 + tail 是 33 类粗化分布的 KL，通常小于等于全词表 KL（数值误差除外）。

训练的分子只累加有效 reasoning 正文位置：$\mathcal L=\sum_t m_t\ell_t/N_{\mathrm{response}}$。当前 response_token_mean 分母沿用响应 token mask 的计数，不是只数正文 token。本报告给出的逐位置 KL 均值是正文均值，不能直接当作 W&B 中的 batch loss。

## Top-k 候选重叠

$$C_t=|\operatorname{Top32}(p_t)\cap\operatorname{Top32}(q_t)|,\quad O_t=C_t/32,\quad J_t=C_t/(64-C_t).$$

| K | 平均交集 token 数 | 交集 / K |
|---:|---:|---:|
| 1 | 0.86 | 86.35% |
| 8 | 6.66 | 83.28% |
| 16 | 13.31 | 83.20% |
| 20 | 16.63 | 83.15% |
| 32 | 26.57 | 83.02% |

top-32 交集的 P10 / 中位数 / P90 为 **22 / 27 / 30**；平均 Jaccard 为 **72.38%**。

| 加权方式 | 平均 top-32 重叠率 |
|---|---:|
| 每个正文位置等权 | 83.02% |
| 每个 turn 等权，再平均 | 82.83% |
| 每道题内按位置平均，再对 10 题等权 | 83.25% |

## 重叠词汇承载多少概率

| 指标（所有正文位置均值） | T=0.6 | T=1.0 |
|---|---:|---:|
| 无 hint 自己的 top-32 概率质量 | 100.00% | 100.00% |
| 有 hint 自己的 top-32 概率质量 | 100.00% | 100.00% |
| 交集在无 hint 分布中的概率质量 | 99.91% | 99.91% |
| 交集在有 hint 分布中的概率质量 | 99.50% | 99.50% |
| 有 hint 的 top-32 在无 hint 分布中的质量 | 99.91% | 99.91% |
| 无 hint 的 top-32 在有 hint 分布中的质量 | 99.50% | 99.50% |
| 无 hint 的 top-1 概率 | 95.84% | 93.08% |
| 有 hint 的 top-1 概率 | 95.19% | 92.07% |
| 无 hint entropy（nats） | 0.102891 | 0.177424 |
| 有 hint entropy（nats） | 0.119024 | 0.204441 |
| 完整 forward KL（nats） | 1.100353 | 0.662910 |
| 教师 top-32 + tail forward KL（nats） | 1.100353 | 0.662905 |

候选 token 大量重叠仍可能有不同的概率排序和权重；top-1 相同也不代表整段推理相同。对同一已给定学生 prefix 的预测，不能直接推断教师自己 rollout 的结果。

T=0.6 下，top-1 不同的 11,908 个位置（13.65%）承担了总 forward KL 的 **90.39%**。这些位置平均 KL 为 7.2870 nats，top-1 相同的位置为 0.1225 nats。全部正文位置 KL 的中位数仅 3.79433e-05 nats，平均值明显受少数分歧位置影响。

## Reasoning 的不同位置

| 位置范围 | 位置数 | 平均 top-32 重叠率 | top-1 一致率 |
|---|---:|---:|---:|
| 每 turn 第一个正文 token（可能是换行） | 412 | 76.28% | 11.17% |
| 其余正文 token | 86834 | 83.05% | 86.71% |
| 每 turn 前 10 个正文 token | 4120 | 75.33% | 76.82% |
| 第 11 个及之后正文 token | 83126 | 83.40% | 86.82% |

## 逐题结果

| 题号 | 任务 | turn 数 | 正文位置数 | 平均重叠数 / 32 | 重叠率 | top-1 一致率 |
|---:|---|---:|---:|---:|---:|---:|
| 1 | 加热一个盘子，然后放进冰箱 | 49 | 9450 | 26.72 | 83.51% | 85.98% |
| 2 | 把一根蜡烛放到台面上 | 50 | 10774 | 26.79 | 83.72% | 87.14% |
| 3 | 借助台灯检查 CD | 50 | 10747 | 25.44 | 79.51% | 83.73% |
| 4 | 找到两个钥匙串，放到扶手椅上 | 50 | 10955 | 26.85 | 83.91% | 87.07% |
| 5 | 把洗干净的碗放到餐桌上 | 49 | 10277 | 26.65 | 83.30% | 86.49% |
| 6 | 把纸巾盒放到马桶上 | 27 | 5250 | 26.54 | 82.93% | 86.55% |
| 7 | 把洗手液瓶放到马桶上 | 33 | 6903 | 26.39 | 82.48% | 85.44% |
| 8 | 把信用卡放到架子上 | 4 | 424 | 27.54 | 86.07% | 91.75% |
| 9 | 把两条擦手巾放到台面上 | 50 | 12031 | 27.45 | 85.77% | 89.19% |
| 10 | 把 CD 放到保险箱里 | 50 | 10435 | 26.03 | 81.33% | 84.68% |

## 真实位置示例

下面选取 3 道题 turn 1 的首个非空白正文 token，以及前 64 个正文 token 中重叠最小的位置；这是明确挑选的说明性例子，不代表随机样本。候选 token 字符串保留空格与 BPE 子词，比较依据始终是 token ID。全部候选列表见 examples.jsonl。

### 题 3 / turn 1 / first_content

任务：examine the cd with the desklamp.

Hint：To examine the CD under light, you'll need both items in hand — think about where small discs and desk lamps typically live in a bedroom, like surfaces or storage near the workspace. Start by checking the likely spots around the desk area.

已给定的学生 response prefix：

```text
<reasoning>

```

原轨迹接下来的 token：`"I"`；交集 **24/32**。

无 hint top-1：`"I"`，p=0.9999；有 hint top-1：`"I"`，q=0.9956。

有 hint top-32 中新增的候选：`"Based"`, `" The"`, `"Begin"`, `"_I"`, `"There"`, `"You"`, `".I"`, `":I"`。

### 题 3 / turn 1 / lowest_overlap_first64

任务：examine the cd with the desklamp.

Hint：To examine the CD under light, you'll need both items in hand — think about where small discs and desk lamps typically live in a bedroom, like surfaces or storage near the workspace. Start by checking the likely spots around the desk area.

已给定的学生 response prefix：

```text
<reasoning>
I need to examine the cd with the desklamp. To do this, I first need to locate the desklamp and the cd.
```

原轨迹接下来的 token：`" The"`；交集 **17/32**。

无 hint top-1：`" The"`，p=1.0000；有 hint top-1：`" The"`，q=0.8891。

有 hint top-32 中新增的候选：`" Des"`, `" Both"`, `" Likely"`, `" Typically"`, `" They"`, `" A"`, `" Desk"`, `" based"`, `" since"`, `" DES"`, `"Given"`, `" Common"`。

### 题 7 / turn 1 / first_content

任务：put some soapbottle on toilet.

Hint：Soap bottles are usually kept near where people wash their hands, so check the visible bathroom surfaces first before rummaging through drawers. Once you find one, remember you'll need to be holding it to place it somewhere new.

已给定的学生 response prefix：

```text
<reasoning>

```

原轨迹接下来的 token：`"I"`；交集 **25/32**。

无 hint top-1：`"I"`，p=0.9997；有 hint top-1：`"I"`，q=1.0000。

有 hint top-32 中新增的候选：`"_I"`, `"There"`, `":I"`, `"Begin"`, `".I"`, `"Beginning"`, `"You"`。

### 题 7 / turn 1 / lowest_overlap_first64

任务：put some soapbottle on toilet.

Hint：Soap bottles are usually kept near where people wash their hands, so check the visible bathroom surfaces first before rummaging through drawers. Once you find one, remember you'll need to be holding it to place it somewhere new.

已给定的学生 response prefix：

```text
<reasoning>
I need to put a soapbottle on the toilet. First, I should locate the soapbottle. Since
```

原轨迹接下来的 token：`" I"`；交集 **10/32**。

无 hint top-1：`" the"`，p=0.5000；有 hint top-1：`" soap"`，q=1.0000。

有 hint top-32 中新增的候选：`"皂"`, `"Soap"`, `" soup"`, `"SOAP"`, `" socks"`, `" soy"`, `" toilet"`, `" foam"`, `" sap"`, `" sofa"`, `" shower"`, `" shampoo"`。

### 题 10 / turn 1 / first_content

任务：put some cd on safe.

Hint：You need to find a CD first—think about where small media items like that typically get stored in a bedroom, such as inside furniture with storage spaces. Start checking likely spots nearby.

已给定的学生 response prefix：

```text
<reasoning>

```

原轨迹接下来的 token：`"I"`；交集 **24/32**。

无 hint top-1：`"I"`，p=1.0000；有 hint top-1：`"I"`，q=1.0000。

有 hint top-32 中新增的候选：`"_I"`, `"There"`, `".I"`, `"You"`, `"Based"`, `":I"`, `"-I"`, `"From"`。

### 题 10 / turn 1 / lowest_overlap_first64

任务：put some cd on safe.

Hint：You need to find a CD first—think about where small media items like that typically get stored in a bedroom, such as inside furniture with storage spaces. Start checking likely spots nearby.

已给定的学生 response prefix：

```text
<reasoning>
I need to put some CD on the safe. To do this, I first need to find a CD. The
```

原轨迹接下来的 token：`" CD"`；交集 **7/32**。

无 hint top-1：`" CD"`，p=1.0000；有 hint top-1：`" hint"`，q=1.0000。

有 hint top-32 中新增的候选：`" hint"`, `" private"`, `" hints"`, `" prompt"`, `" clue"`, `"提示"`, `"_hint"`, `" Hint"`, `" Private"`, `" user"`, `"Private"`, `"Hint"`。

## 审计与限制

- 8 个 worker 全部完成；唯一位置计数与输入 mask 完全一致，无丢失或重复。最慢 worker 评分耗时 8.0 秒（不含模型加载），单 GPU 峰值 PyTorch allocated 8.11 GiB。
- 每个 worker 首批都将 hidden→lm_head 路径与原生模型 forward 对照，logits 最大误差 0；full KL 与 FP64 独立复核。
- 另取 2 个 turn、各 5 个正文位置、两种输入条件共 20 项，独立截断输入到预测位置之前再前向；与整段 causal prefill 对应位置的全词表 logits 最大差异均为 0，top-32 全部一致。检查输入不包含目标 token 或未来 token，排除这些位置因读取未来内容而变尖锐的解释。
- BF16 在第 32/33 名存在并列分数的情况，两侧任一侧出现并列的比例为 48.03%。统计使用 torch.topk(K=32) 的实际结果；精确交集计数依赖边界并列 token 的成员选择，未报告跨硬件的并列消解不确定区间。
- 本次准备阶段修正了容器默认 sleep 入口；首轮校验发现 topk(33)[:32] 与 topk(32) 对同分候选的顺序/成员不保证一致，之后明确使用 topk(32) 并重新完整评分。失败尝试未混入结果。
- 此结果只描述原始模型在现有轨迹上的局部分布变化，不能据此断定训练后 empty_reasoning 的原因，也不能据此判断 hint 一定提高成功率。

## 文件

- `summary.json`：全部统计、分位数、逐题结果、完整配置和数值校验。
- `per_task.csv` / `per_turn.jsonl`：按题 / 按 turn 的统计。
- `positions.jsonl.gz`：全部位置的两侧 top-32 token IDs、原始 logits、熵、概率质量、KL。
- `inputs.jsonl.gz`：逐 turn 的完整 prompt、hint、原始 response IDs 和正文 mask 位置。
- `examples.jsonl`：上述具体位置的可读候选词与概率；null 表示未保存其在另一侧 top-32 之外的单 token 概率，不表示概率为零。
- `prepare.py` / `worker.py` / `aggregate.py` / `launch.py`：本次诊断代码。
- `check_prefix.py` / `prefix_validation.json`：独立截断前缀的 20 项检查。
- `MANIFEST.sha256`：导出文件校验。
