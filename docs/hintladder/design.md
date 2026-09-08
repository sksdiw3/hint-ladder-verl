# Hint Ladder on verl-agent：E1–E4 代码架构与实施指南

> 当前实施范围补充：按后续决定，Hinter reward 和 Hinter GRPO 暂不实现，E4 仅提供外部训练接口与交替编排。以下保留原始设计；实际支持范围和验证结果以仓库 README、HINT_LADDER.md 和 validation.md 为准。

> 读者：写代码的 Codex，以及审代码的人。
> 目标：在 verl 生态里实现"多轮 agent 自蒸馏中自教师该拿多少特权信息"这条研究线的 E1–E4 实验，先做 ALFWorld。
> 本文是**契约**，不是建议。第 0 节的禁令优先级高于一切"看起来更好"的实现想法。
>
> 2026-09-07 已定决策：直接用 **Qwen3-4B**；功能对齐现有 swift 仓库，不做超出它的东西；ALFWorld 上**一条轨迹一条 hint**；**student 和 teacher 都不开 think**，响应只有 `<action>…</action>`。

---

## 0. 给 Codex 的硬约束（先读这一节）

1. **不准发明 hash。** 所有标识符用自然键：`gamefile`（相对 `ALFWORLD_DATA` 的路径）、`level`、`seed`、`round`、`step`。文件名、目录名、JSONL 主键里禁止出现内容哈希。唯一允许 sha256 的地方是每个产物目录下 `manifest.json` 的 `inputs[].sha256` 字段，用于事后溯源。
2. **不准写 bash 启动脚本。** 全仓库只允许一个 `scripts/env.sh`（激活 conda、导出 `ALFWORLD_DATA`）。所有阶段通过 `python -m hintladder.cli <stage> --config <yaml>` 启动。训练阶段由 CLI 组装 hydra override 列表并以子进程调用 verl 的 main，完整命令行写入 `runs/<exp>/launch_command.txt`。
3. **不准用环境变量传配置。** `hintladder/` 包内禁止读 `os.environ`，唯一例外 `ALFWORLD_DATA`。配置只来自 YAML 和 hydra override。
4. **不准改 verl 核心。** `verl/` 目录下只允许新增两个文件：`verl/trainer/main_hint_ladder.py` 和 `verl/trainer/ppo/hint_ladder_ray_trainer.py`，以及在 `verl/trainer/config/ppo_trainer.yaml` 的 `algorithm` 下新增一个 `hint_ladder` 配置组。第一阶段禁止修改 `dp_actor.py`、`rollout_loop.py`、`env_manager.py`；如果确实需要在 `env_manager` 里把 `gamefile` 透传到 batch，改动限定在这一件事，并写在 PR 描述里。
5. **不准写兜底。** 缺 hint、gamefile 对不上、token 对齐失败，一律 `raise`，不准 `try/except` 后静默跳过。
6. **不准提前抽象。** 只有一个 `HintProvider` 类、一种 bank 文件格式、一个 trainer 子类。没有插件系统、没有 registry、没有"以后可能用到"的参数。
7. **不准重造已有的东西。** 环境管理、多轮 rollout、SDL loss、验证循环、checkpoint 都用 SMRC-SD 现成的。我们只写"hint 从哪来、怎么进教师 prompt、怎么评"。
8. 每个阶段产物目录必须有 `manifest.json`：`{"stage", "config_path", "config", "git_commit", "inputs": [{"path", "sha256"}], "created_at"}`。
9. 指标统一前缀 `hint_ladder/`。
10. 测试全部 CPU 可跑，`pytest tests/hintladder -q` 必须过才算完成一个阶段。

---

## 1. 总体决策

### 1.1 基于哪个仓库

基于 **SMRC-SD 仓库**（`https://github.com/liujunzhuo/SMRC-SD`，它是 verl-agent 的扩展，Apache-2.0）。原因：

- verl-agent 提供 ALFWorld/WebShop 环境管理器、逐步多轮 rollout、观察 mask、`<think></think><action></action>` 响应格式、GRPO 训练与验证循环。
- SMRC-SD 在此之上已经实现并在 Qwen3-1.7B 上发表过：同一模型换 prompt 的教师前向（`RLSDRayTrainer._compute_teacher_log_probs` 钩子）、SDL 损失（`dp_actor.py` 中 `use_sdl_loss`，`chosen_token_k3` 与 top-k forward KL 两种模式）、GRPO 与蒸馏项合用。
- 它的 FullPath-SD 基线就是"原版 OPSD 搬到 ALFWorld"，可直接作为我们的对照臂，且有已发表数字可对齐（Qwen3-1.7B：GRPO 0.717 / FullPath-SD 0.746 / SMRC-SD 0.865，Avg@4）。

### 1.2 我们复用什么、新写什么、明确不用什么

| 复用（不改） | 新写 | 不用 |
|---|---|---|
| `agent_system/`（环境、rollout、prompt 模板） | `hintladder/` 包（框架无关的 Python） | `verl/trainer/main_path_opd.py` |
| `verl/trainer/ppo/rlsd_ray_trainer.py`、`skillsd_ray_trainer.py` 的 fit 循环与教师钩子 | `verl/trainer/ppo/hint_ladder_ray_trainer.py`（一个子类，一个方法） | `path_privileged_utils.py`（3300 行，状态匹配逻辑与我们无关） |
| `verl/workers/actor/dp_actor.py` 的 SDL 损失 | `verl/trainer/main_hint_ladder.py`（入口，20 行） | `examples/smrc_sd/*.sh` 的环境变量启动方式 |
| `RayPPOTrainer._validate` 与 rollout dump | `configs/` 下每个实验臂一个 YAML | `skills/`、SkillBank、prefix buffer |

### 1.3 训练范式（与文献一致）

- 学生：干净 prompt，在线跑完整 episode（verl-agent 逐步 rollout）。**不开 think**：响应只有 `<action>…</action>`，用 SMRC-SD 已有的 `prompt_style: action_tag_only` 模板 + `require_think_tags: False`，Qwen3 原生 thinking 关闭（`enable_thinking=False`）。这与 swift 仓库"宏动作 = 一条命令"的设置一致。
- 教师：**同一份当前权重**（同步教师），输入 = 学生的逐步 prompt 插入一段私有便签，响应 token 与学生完全相同，只做前向取 logprob。
- 损失：`pg_loss_coef × GRPO 策略损失 + sdl_loss_coef × SDL`。两个预设：
  - `sd_only`（**默认，对齐 swift 的纯 on-policy 蒸馏**）：`pg_loss_coef: 0.0`，只有蒸馏项；
  - `grpo_sd`（对齐 Skill-SD/SDAR/SMRC-SD 文献）：`pg_loss_coef: 1.0`。
  SDL 默认 `sdl_loss_mode: topk_forward_kl`、`sdl_topk: 20`、含尾桶，这是 SMRC-SD 里最接近 swift"top-20 稀疏教师分布"的模式；`chosen_token_k3` 作为更省显存的备选。swift 用的 JSD(β=0.5) 在 `dp_actor.py` 里没有，第一阶段不加，记为已知偏差。损失覆盖响应内全部普通 token，mask 掉特殊 token。
- hint 粒度：**一局一条**，按 `gamefile` 键入，整局所有步共用。教师 prompt 每步都插同一条。
- hint 生成：**永远离线**。训练进程不调用任何 LLM API。E4 的 hinter 也是每轮先离线生成一份 bank 再训学生。

---

## 2. 目录结构

在 SMRC-SD 仓库根目录下新增：

```
hintladder/                         # 框架无关，禁止 import verl
  __init__.py
  cli.py                            # 唯一入口：python -m hintladder.cli <stage> --config x.yaml
  keys.py                           # gamefile 规范化（相对路径）、level 枚举、arm 命名
  privilege.py                      # 从 TextWorld 游戏抽取隐藏事实 + 回放 walkthrough
  ladder.py                         # L0/L1/L2/L3/FULLPATH 合同、生成 prompt、校验器、泄露审计（移植自 OPD 仓库 coevo/hints/ladder.py）
  hint_bank.py                      # bank 读写、HintProvider
  teacher_prompt.py                 # insert_note(prompt_text, note) 与不变量断言
  behavior.py                       # ALFWorld 行为指标（移植自 OPD 仓库 coevo/audit/alfworld.py）
  budget.py                         # active-token 预算计数器
  hstar.py                          # h* 判定与分档（移植自 OPD 仓库 coevo/curriculum/hstar.py）
  hinter_reward.py                  # E4 解析 reward（移植自 OPD 仓库 coevo/hinter_training/grpo_reward.py）
  stages/
    build_privilege_bank.py         # 阶段 P：生成 data/privilege/alfworld_<split>.jsonl
    build_hint_bank.py              # 阶段 H：调用 API 模型生成 data/hint_bank/<bank>/<level>.jsonl
    train_student.py                # 阶段 T：组装 override，子进程调用 verl.trainer.main_hint_ladder
    eval_behavior.py                # 阶段 B：从 validation dump 算行为指标
    e1_audit.py                     # 阶段 E1：冻结 checkpoint 上的静态审计
    e3_probe.py                     # 阶段 E3：pass@k 探针 → hstar_manifest.jsonl + level_map.json
    train_hinter.py                 # 阶段 E4：hinter GRPO（标准 verl main_ppo + 自定义 reward）
    alternate.py                    # 阶段 E4：学生/hinter 交替驱动
verl/trainer/main_hint_ladder.py
verl/trainer/ppo/hint_ladder_ray_trainer.py
configs/
  base_alfworld_qwen3_4b.yaml       # 公共训练参数（模型、GPU、batch、验证频率、响应格式）
  presets/
    sd_only.yaml                    # pg_loss_coef: 0.0（默认）
    grpo_sd.yaml                    # pg_loss_coef: 1.0
  arms/
    e2_L0.yaml                      # 无 hint 对照：sd_only 下 = 基座 checkpoint 只评测；grpo_sd 下 = 纯 GRPO（sdl 关）
    e2_L1.yaml
    e2_L2.yaml
    e2_L3.yaml
    e2_FULLPATH.yaml                # 原样贴 walkthrough，OPSD 原版对照
    e3_hstar.yaml
    e3_random.yaml
  hint_gen.yaml                     # API 模型、并发、重试
  e1_audit.yaml
  e3_probe.yaml
  e4_hinter_grpo.yaml
  e4_alternate.yaml
data/
  game_lists/
    alfworld_train_256.txt          # 固定训练游戏列表，一行一个 gamefile 相对路径
    alfworld_valid_seen_128.txt
    alfworld_valid_unseen_128.txt
  privilege/
    alfworld_train.jsonl
    alfworld_valid_seen.jsonl
    alfworld_valid_unseen.jsonl
  hint_bank/
    glm53flash_v1/                  # bank 名 = 生成模型 + 版本号，人工命名
      L1.jsonl
      L2.jsonl
      L3.jsonl
      FULLPATH.jsonl
      manifest.json
      validation_report.json
runs/
  <experiment_name>/                # = arm yaml 文件名 + _seed<k>，例如 e2_L3_seed0
    launch_command.txt
    manifest.json
    verl 的 checkpoint / rollouts / validation 输出
    behavior/                       # eval_behavior 的输出
scripts/
  env.sh                            # 唯一允许的 shell 文件
tests/hintladder/
```

---

## 3. 数据契约

### 3.1 键

- `gamefile`：相对 `ALFWORLD_DATA` 的路径，形如 `json_2.1.1/train/pick_heat_then_place_in_recep-Mug-None-Cabinet-3/trial_T20190909_014639_335717/game.tw-pddl`。`keys.normalize_gamefile()` 负责把绝对路径转相对、去掉重复斜杠。所有 bank 用它做主键。
- `level`：字符串枚举 `L0 | L1 | L2 | L3 | FULLPATH | HINTER`。
- `seed`：整数，同时用于 `env.seed` 和 `trainer` 的随机种子。
- `experiment_name`：`<arm yaml 文件名去后缀>_seed<seed>`。

### 3.2 privilege bank（`data/privilege/alfworld_<split>.jsonl`）

每行一个游戏。由 `build_privilege_bank.py` 在 CPU 上用 TextWorld 回放生成，不需要 GPU，不需要 API。

```json
{
  "gamefile": "json_2.1.1/train/.../game.tw-pddl",
  "split": "train",
  "task_type": "pick_heat_then_place_in_recep",
  "goal_text": "put a hot mug in cabinet.",
  "initial_observation": "You are in the middle of a room. Looking quickly around you, you see ...",
  "initial_admissible_commands": ["go to cabinet 1", "..."],
  "walkthrough_actions": ["go to countertop 1", "take mug 2 from countertop 1", "..."],
  "walkthrough_verified": true,
  "hidden_facts": {
    "goal_object": "mug 2",
    "goal_object_location": "countertop 1",
    "destination_receptacle": "cabinet 1",
    "goal_object_initial_states": {"hot": false, "clean": true}
  }
}
```

要求：
- `walkthrough_actions` 来自 TextWorld 游戏自带的专家 walkthrough（SMRC-SD 同源），必须在 TextWorld 里回放一遍并以 `won=True` 结束，否则 `walkthrough_verified=false` 且该游戏从训练列表里剔除。**不使用 AgentGym/ETO 的轨迹。**
- `hidden_facts` 从 `EnvInfos(facts=True)` 的初始 facts 里抽（`inreceptacle`/`on` 谓词 + 目标物体），OPD 仓库 `scripts/experiment_alfworld_fact_swap.py` 里有可参考的抽取代码。
- `initial_observation` 与 `initial_admissible_commands` 是 L2 盲写的唯一输入，必须原样保存。

### 3.3 hint bank（`data/hint_bank/<bank>/<level>.jsonl`）

每行一个 `(gamefile, level)`：

```json
{
  "gamefile": "...",
  "level": "L2",
  "hint": "No mug has been observed yet, so inspect receptacles one at a time ...",
  "word_count": 71,
  "generator": {"model": "glm-5.3-flash", "temperature": 0.7, "prompt_version": "v1"},
  "validation": {"ok": true, "errors": []}
}
```

- `FULLPATH.jsonl` 不调 API，`hint` 就是 walkthrough 动作用 ` -> ` 连接的字符串。
- `validation.ok=false` 的行保留在文件里但训练时 `HintProvider` 遇到必须 `raise`；`build_hint_bank.py` 负责重试直到全部 ok 或报告失败列表。
- 同一 bank 内每个 `(gamefile, level)` 只允许一行。

### 3.4 level map（E3 用，`level_map.json`）

`{"<gamefile>": "L2", ...}`。固定臂不需要 level map，`HintProvider(bank_dir, level="L3")`；课程臂用 `HintProvider(bank_dir, level_map_path=...)`。两者是同一个类的两种构造参数，不是两个类。`level="L0"` 表示不插便签，且 trainer 必须把 `use_sdl_loss` 设为 False。

### 3.5 hstar manifest（E3 产物，`hstar_manifest.jsonl`）

```json
{"gamefile": "...", "checkpoint": "runs/e2_L2_seed0/global_step_100", "k": 8,
 "pass_at_k": {"L0": 0.0, "L1": 0.125, "L2": 0.75, "L3": 1.0},
 "h_star": "L2", "band": "scaffolded"}
```

分档规则移植 OPD 仓库 `coevo/curriculum/hstar.py`：`mastered`（L0 已过）、`frontier`（L0 有非零成功）、`scaffolded`（需要 L1/L2）、`oracle_only`（只有 L3 能过）、`unreachable`（L3 也不过）。

---

## 4. 核心机制：教师视图如何进训练

### 4.1 数据流（一个训练 step）

```
verl-agent rollout（学生，干净 prompt，逐步）
  → batch: input_ids / responses / attention_mask / non_tensor_batch{traj_uid, gamefile, step, ...}
  → HintLadderRayTrainer._compute_teacher_log_probs(batch):
        for i in batch:
            prompt_text = decode(student prompt ids)
            note = provider.get(gamefile_i)            # 一局一条，逐步复用
            teacher_prompt_text = insert_note(prompt_text, note)
            teacher_ids = encode(teacher_prompt_text) ++ responses_i    # 响应 token 原样
        teacher_batch → actor_rollout_wg.compute_log_prob(teacher_batch)   # 当前权重，no grad
        return teacher_log_probs                       # (bs, response_len)
  → batch.batch["teacher_log_probs"] = ...
  → actor.update_policy: pg_loss + sdl_loss_coef * SDL(student_log_probs, teacher_log_probs, old_log_probs)
```

这与 SMRC-SD 的 `build_path_privileged_teacher_batch` 是同一套张量构造（左 pad 到 `max_prompt_length`、拼接 responses、重算 position_ids），**直接照它的 40 行写一个 `build_teacher_batch(batch, provider, tokenizer, max_prompt_length)`**，去掉它里面所有 state matching / sample weight / metrics 逻辑。

### 4.2 `gamefile` 必须在 batch 里

verl-agent 原版的 rollout batch 没有 `gamefile`。SMRC-SD 的 `envs.py` 已经在 reset 时返回 `info["extra.gamefile"]`。Codex 需要确认这条链路在**训练 worker**（不只是固定 gamefile 的验证 worker）上也成立，并让 `env_manager.reset/step` 把它放进 `infos`，`rollout_loop` 把它放进 `batch.non_tensor_batch["gamefile"]`。这是第 0 节允许的唯一一处 `agent_system` 改动。找不到 `gamefile` 时 `raise`，不准用 `traj_uid` 或 prompt 文本做替代键。

### 4.3 便签插入位置（`teacher_prompt.insert_note`）

verl-agent 的 ALFWorld prompt 是单条 user 消息，没有 system 消息。我们用的两个模板是 `ALFWORLD_TEMPLATE_NO_HIS_ACTION_TAG_ONLY`（第 1 步，首行没有任务描述）和 `ALFWORLD_TEMPLATE_ACTION_TAG_ONLY`（之后各步，首行带 `Your task is to: …`）。插入规则唯一且确定：

```
锚点:        prompt 的第一行，它总是以 "You are an expert agent operating in the ALFRED Embodied Environment" 开头
插入后:      第一行原样保留，紧接其后插入
             "<private_teacher_note>\n{note}\n</private_teacher_note>\n"
             "This note is advisory. Decide from the current observation and admissible actions, and never mention the note.\n"
其余原文不变。
```

找不到锚点就 `raise`，不准退化成"插到开头"。

不变量（写成断言，也写成测试）：
- `remove_note(insert_note(p, n)) == p`；
- 插入后的文本只比原文多出一个 `<private_teacher_note>` 块，对两个模板变体都成立；
- 教师序列的响应段 token id 与学生的 `responses` 完全相等（逐元素比较，不是长度比较）；
- 教师 prompt 若超过 `max_prompt_length`，**报错**而不是截断（SMRC-SD 是尾部截断，我们不允许，因为截断会切掉任务描述；应该调大 `max_prompt_length` 或缩短 hint）。

### 4.4 配置键（新增 `algorithm.hint_ladder`）

```yaml
algorithm:
  hint_ladder:
    enable: True
    bank_dir: data/hint_bank/glm53flash_v1
    level: L3                 # L0|L1|L2|L3|FULLPATH|HINTER；与 level_map_path 二选一
    level_map_path: null
    active_token_budget: null # 整数；达到后 trainer 停止。null 表示不限
```

SDL 相关键**直接**写在 actor 配置里，不做运行时拷贝（这是 `main_path_opd.py` 里最容易出错的部分，我们不复制它）：

```yaml
actor_rollout_ref:
  actor:
    pg_loss_coef: 0.0                    # sd_only 预设；grpo_sd 预设为 1.0。dp_actor.py 已读取这个键
    use_sdl_loss: True
    sdl_loss_coef: 1.0                   # sd_only 下蒸馏项是唯一损失，系数取 1；grpo_sd 下先用 SMRC-SD 的 0.01 再扫描
    sdl_loss_mode: topk_forward_kl       # 备选 chosen_token_k3
    sdl_topk: 20
    sdl_topk_include_tail: True
    sdl_loss_token_scope: all
    sdl_loss_mask_special_tokens: True
    sdl_loss_normalization: response_token_mean
    use_fused_kernels: False             # top-k SDL 的硬性要求
    strategy: fsdp                       # top-k SDL 的硬性要求
```

一致性检查（`main_hint_ladder.py` 里做，不一致就 `raise`）：`level: L0` 时 `use_sdl_loss` 必须为 False；`pg_loss_coef == 0` 且 `use_sdl_loss == False` 是空训练，直接拒绝；`sdl_loss_mode` 为 top-k 时 `use_fused_kernels` 必须为 False。

### 4.5 `HintLadderRayTrainer`

```python
class HintLadderRayTrainer(SkillSDRayTrainer):
    def __init__(self, *args, hint_provider, **kwargs):
        super().__init__(*args, skill_provider=None, **kwargs)
        self.hint_provider = hint_provider
        self.budget = ActiveTokenBudget(self.config.algorithm.hint_ladder.active_token_budget)
        self._last_teacher_skill_metrics = {}

    def _compute_teacher_log_probs(self, batch):
        teacher_batch = build_teacher_batch(batch, self.hint_provider, self.tokenizer,
                                            self.config.data.max_prompt_length)
        teacher_batch.meta_info["calculate_entropy"] = False
        if self.use_topk_sdl:                       # 由 actor.sdl_loss_mode 决定
            teacher_batch.meta_info["return_topk"] = self.config.actor_rollout_ref.actor.sdl_topk
        out = self.actor_rollout_wg.compute_log_prob(teacher_batch)
        if self.use_topk_sdl:                       # 照 PathPrivOPDRayTrainer 的对应 10 行，含形状检查
            batch.batch["teacher_topk_ids"] = out.batch["teacher_topk_ids"]
            batch.batch["teacher_topk_log_probs"] = out.batch["teacher_topk_log_probs"]
        self.budget.add(batch.batch["response_mask"].sum().item())
        self._last_teacher_skill_metrics = {
            "hint_ladder/active_tokens_cumulative": self.budget.used,
            "hint_ladder/level_counts/<level>": ...,     # 本 batch 各 level 的样本数
        }
        return out.batch["old_log_probs"]
```

如果 `SkillSDRayTrainer.fit()` 对 `skill_provider=None` 不兼容，**把 `fit()` 整段复制到我们的类里并删掉 skill 分支**，这是唯一允许复制大段代码的地方。预算耗尽时在 `fit()` 的 step 循环末尾 `break`，并写 `runs/<exp>/budget_exhausted.json`。

### 4.6 `main_hint_ladder.py`

照 `main_path_opd.py` 的骨架写，但只做四件事：读 `algorithm.hint_ladder`；构造 `HintProvider`；一致性检查（L0 ↔ sdl 关；bank 里覆盖训练游戏列表的全部 gamefile，缺一个就 `raise`）；启动 `HintLadderRayTrainer`。不做任何配置拷贝。

---

## 5. 实验映射

### 5.1 公共设置

| 项 | 值 |
|---|---|
| 模型 | Qwen3-4B，全参 FSDP，不做 1.7B |
| 训练游戏 | `data/game_lists/alfworld_train_256.txt`，所有臂、所有 seed 共用 |
| 验证 | `valid_seen` 128 局 + `valid_unseen` 128 局，各 4 次 rollout，`val_temperature=0.4` |
| 步数上限 | `env.max_steps=30`，`max_response_length=64`（响应只有一个 `<action>` 块） |
| 响应格式 | `env.alfworld.prompt_style: action_tag_only`、`env.alfworld.require_think_tags: False`、`+data.apply_chat_template_kwargs.enable_thinking: False`。三个键都显式写，不依赖 `require_think_tags: null` 的推导逻辑 |
| 训练预设 | 默认 `sd_only`；`grpo_sd` 只在 sd_only 明显不动时启用，且一次只换一个变量 |
| GPU | 8×A100，actor 与 rollout 同卡，教师前向复用 actor 权重不占额外卡 |
| seed | 0、1、2 |
| 评测时 | 学生不带任何便签（验证 rollout 本来就是干净 prompt，无需额外处理；写一条断言防止 provider 被误用到验证路径） |
| hint 粒度 | 一条轨迹一条，开局按 `gamefile` 取，整局每步教师 prompt 插同一条 |

### 5.2 E1：静态审计（不训练）

**问题**：三档 hint 在同一批状态上是否分离；L3 是否泄露事实；带 hint 的冻结策略行为是否变化。

**输入**：一个 checkpoint（基座或某臂的 checkpoint）、privilege bank、hint bank、游戏列表。
**过程**（`e1_audit.py`，用 vLLM 起一个服务，1–2 张卡）：
1. 泄露审计：对 bank 里每条 L1/L2/L3 跑 `ladder.audit_leak(hint, hidden_facts)`，输出各级 `fact_leak_rate`。预期 L1=L2=0、L3≈1。
2. 带便签 rollout：对每个游戏、每个 level，把便签插进**行动策略**的 prompt 跑 4 局，记录 `behavior.py` 指标：首次导航是否直奔 `goal_object_location`、拾取前有无 look/open/examine、非法动作率、成功率。这一步就是"教师侧行为"。
3. 参考轨迹 lift：以 walkthrough 为参考，把每个动作渲染成 `<action>{a}</action>`（与学生响应格式一致，因为不开 think），在每个 walkthrough 状态上 teacher-forcing 三个视图（无便签 / 有便签 / 只有便签无观察），算 `lift` 和 `copy`。**注意**：OPD 仓库里用 ETO 探索型轨迹做参考时 L3 的 lift 为负、copy 倒挂；换成 walkthrough 后要重新看，若仍倒挂，`copy` 只作诊断、不进论文、不进 reward。

**输出**：`runs/e1_<bank>_<ckpt>/summary.json` + 每级每游戏一行的 `rows.jsonl`。
**验收**：泄露率符合预期；行为指标在 L2 与 L3 之间有分离；否则回到 hint 合同修改，不进入 E2。

### 5.3 E2：等预算剂量响应（主实验）

**臂**：`e2_L0`、`e2_L1`、`e2_L2`、`e2_L3`、`e2_FULLPATH`，各 3 个 seed。`sd_only` 预设下 `e2_L0` 不训练，只对基座 checkpoint 跑验证与行为评测（与 swift 仓库"L0 是未动的基座"一致），所以实际训练 12 个 run；`grpo_sd` 预设下 `e2_L0` 是纯 GRPO。每个臂一个 YAML，只允许相差 `level` 与 `use_sdl_loss`，预设通过 `extends` 切换。
**预算**：先跑 `e2_L3_seed0` 到 250 步，读取其 `hint_ladder/active_tokens_cumulative`，把这个数写进其它臂的 `active_token_budget`。所有臂固定同一批游戏与 `env.seed`。在线训练下无法保证状态完全相同，论文里如实说明，这是所有 agent OPSD 论文的比较方式。
**评测**：verl 自带 `val/.../success_rate`（seen/unseen）；`eval_behavior.py` 从 `validation_data_dir` 的 dump 里算行为指标，输出 `runs/<exp>/behavior/step_<n>.json`。
**预期**：L3、FULLPATH 成功率最高但 `query_before_pickup_rate` 下降、`direct_location_hit_rate` 上升；L2 行为干净；若 L3 与 L2 成功率无差、行为无差，按止损规则报"信号校准"而非"毒性"。
**Purified 汇端控制**：第一阶段不做。它需要 top-k 教师分布加"只有便签"第三视图，即每步两次额外前向和一个新的 `sdl_loss_mode=purified_topk`。等 raw 结果出来再决定。

### 5.4 E3：最小充分剂量 h* 与课程

**探针**（`e3_probe.py`，vLLM 服务，不训练）：对某个冻结 checkpoint，每个训练游戏在 L0/L1/L2/L3 下各跑 k=8 局带便签 rollout，h* = 第一个 `pass@k ≥ 0.5` 的 level，写 `hstar_manifest.jsonl` 与 `level_map.json`。
**臂**：`e3_hstar`（`level_map_path` 指向探针产物，`mastered` 的游戏从训练列表剔除或降权：实现方式是生成一个新的游戏列表文件，按权重重复行，不写采样器）、`e3_random`（每个游戏随机分配 L1/L2/L3，固定 seed 生成 level_map）。对照就是 E2 的固定 L2、L3。
**刷新**：每 100 步用最新 checkpoint 重跑探针、重写 level_map，训练脚本以新的 level_map 继续训练（新一轮 run 目录，`round` 递增，不做热更新）。

### 5.5 E4：开放 hinter（仅当 E2 出现现象后启动）

**hinter 训练**（`train_hinter.py`）：标准 verl `main_ppo`，单轮文本任务，GRPO。prompt = 公开初始状态 + 目标 + 领域政策 + walkthrough；输出一条便签。自定义 reward（`hinter_reward.py`，通过 verl 的 `custom_reward_function.path` 挂载）：
- 硬门：`ladder.audit_leak` 命中事实或工具名 → reward 固定负下限；超 140 词 → 负下限。
- `lift`：调用冻结学生的 vLLM 服务，对参考轨迹（walkthrough 的 `<action>` 段，或最近一轮验证通过的学生成功轨迹）teacher-forcing 有/无便签两视图，取 clipped log-ratio 均值。
- 长度惩罚。
- `copy` 项**先不进 reward**，只记录，等 E1 证明它有区分度再加。
**交替**（`alternate.py`）：`rounds/round_<k>/` 目录，顺序为：用 hinter checkpoint 离线生成 `hint_bank/hinter_round<k>/HINTER.jsonl` → 学生训练 N 步（`level: HINTER`）→ 验证 pass@k → 与上一轮比较，退步则回滚学生和 hinter 到上一轮目录 → hinter GRPO 若干步。状态记录在 `rounds/round_<k>/status.json`，键是轮次整数。整个驱动是顺序的子进程调用，没有守护进程、没有端口发现、没有轮询脚本。

---

## 6. 配置与启动约定

### 6.1 arm YAML 的形状

扁平点号键，直接映射 hydra override：

```yaml
# configs/arms/e2_L3.yaml
extends: [../base_alfworld_qwen3_4b.yaml, ../presets/sd_only.yaml]
algorithm.hint_ladder.enable: true
algorithm.hint_ladder.bank_dir: data/hint_bank/glm53flash_v1
algorithm.hint_ladder.level: L3
algorithm.hint_ladder.active_token_budget: null
actor_rollout_ref.actor.use_sdl_loss: true
```

`extends` 是一个列表，按顺序合并，后者覆盖前者，arm 文件自身最后覆盖；被 extends 的文件不能再 extends（不嵌套）。由 `cli.py` 合并。`base_*.yaml` 里放模型路径、`env.*`、`data.*`、`trainer.*`、并行与显存参数，这些参数从 `examples/smrc_sd/run_trainer_alfworld.sh` 里**逐项抄成 YAML**，抄完删掉对该脚本的一切依赖。

### 6.2 启动

```
python -m hintladder.cli train-student --config configs/arms/e2_L3.yaml --seed 0
```

CLI 做的事：合并 YAML → 设置 `env.seed`、`trainer.experiment_name=e2_L3_seed0`、`trainer.rollout_data_dir`、`trainer.validation_data_dir` 到 `runs/e2_L3_seed0/` 下 → 写 `manifest.json` 与 `launch_command.txt` → `subprocess.run(["python3", "-m", "verl.trainer.main_hint_ladder", *overrides], check=True)`。数据预处理（verl-agent 的占位 parquet）由 CLI 在首次运行时生成到 `data/processed/`，之后复用。

其它阶段同理：`build-privilege-bank`、`build-hint-bank`、`eval-behavior`、`e1-audit`、`e3-probe`、`train-hinter`、`alternate`。每个子命令只接受 `--config` 和少数显式参数（`--seed`、`--checkpoint`），不接受任意 override。

### 6.3 日志指标

训练：`hint_ladder/active_tokens_cumulative`、`hint_ladder/level_counts/*`、沿用 `skillsd/teacher_student_gap_mean`（它就是逐 token 的 log 教师/学生比，是最直接的"便签有没有改变教师"信号）、`val/*/success_rate`。
行为（离线）：`direct_location_hit_rate`、`query_before_pickup_rate`、`invalid_action_rate`、`steps_to_pickup_mean`、`success_rate`，按 split 分别给出。

---

## 7. 测试清单（`tests/hintladder/`，全部 CPU）

1. `test_keys.py`：绝对路径/相对路径/重复斜杠归一化到同一个 `gamefile`。
2. `test_teacher_prompt.py`：`insert_note` 的三条不变量；超长 prompt 抛错；对 `ALFWORLD_TEMPLATE_NO_HIS_ACTION_TAG_ONLY` 与 `ALFWORLD_TEMPLATE_ACTION_TAG_ONLY` 两种模板都成立；锚点缺失时抛错。
3. `test_teacher_batch.py`：用一个小 tokenizer 构造 batch，验证教师序列响应段与 `responses` 逐元素相等、`attention_mask` 与 `position_ids` 形状正确、左 pad 正确。
4. `test_ladder.py`：L1 词数与"无事实"校验；L2 输入只含公开字段（构造函数收到隐藏字段就抛）；L3 泄露审计对实例名（`mug 2`、`countertop 1`）与类名别名都能命中；FULLPATH 渲染。
5. `test_hint_bank.py`：缺 gamefile 抛错；`validation.ok=false` 抛错；`level_map` 与固定 level 互斥。
6. `test_behavior.py`：用 3 条手写 rollout 夹具验证四个行为指标。
7. `test_budget.py`：累计与耗尽判定。
8. `test_hstar.py`：分档规则的边界用例。
9. `test_config.py`：`e2_L0.yaml` 必须 `use_sdl_loss=false`；`sd_only` 预设下 `pg_loss_coef` 必须为 0；每个 arm 只与 base 相差允许的键；base 里 `prompt_style`、`require_think_tags`、`enable_thinking` 三个键必须显式存在。

---

## 8. 分阶段计划与验收

| 阶段 | 内容 | 验收 |
|---|---|---|
| 0 环境验证 | 按 SMRC-SD README 装环境，用**它自己的脚本** `run_grpo_alfworld_qwen3_1p7b.sh` 改 `MODEL_PATH=Qwen/Qwen3-4B`、8 卡，跑 50 步 | 不崩、`val/.../success_rate` 随步数上升、rollout dump 里响应可解析。4B 没有已发表数字可对齐，只验环境。记录基座 4B 在 seen/unseen 的成功率作为 L0 |
| 1 基建 | 第 2–4 节全部代码；privilege bank；一个 hint bank；4 个训练臂各跑 10 步冒烟（sd_only） | 测试全过；每个臂 `teacher_student_gap_mean` 非零且 L3 明显大于 L1；泄露审计 L1/L2 为 0；rollout dump 里没有 `<think>` 出现 |
| 2 E2 | 4 个训练臂 × 3 seed = 12 个 run，加基座 L0 评测；E1 审计 | 有剂量响应图与行为指标表；写止损判断 |
| 3 E3 | 探针 + 两个课程臂 | h* 分布合理（不是全 L3）；课程臂与固定臂可比 |
| 4 E4 | hinter GRPO + 交替 | 仅在 E2 现象成立时启动；否则按退路写论文 |

---

## 9. 禁令清单（再说一遍，方便贴给 Codex）

- 不发明 hash；不写 bash 启动脚本；不读环境变量；不改 verl 核心；不写兜底；不提前抽象；不重造已有组件。
- 训练进程不调用 LLM API。
- 教师 prompt 超长报错，不截断。
- 一个 `HintProvider`，一种 bank 格式，一个 trainer 子类，一个 CLI。
- 每个阶段一个 `manifest.json`；每个 run 一个 `launch_command.txt`。
- 改 `agent_system` 只允许为了透传 `gamefile`。
- 复制大段代码只允许 `SkillSDRayTrainer.fit()` 这一处，且要在文件头注明来源与删改内容。

---

## 10. 已知风险与开放问题

1. **系数**：`sd_only` 下 `sdl_loss_coef=1.0`，真正要调的是学习率（先用 SMRC-SD 的 1e-6，L3 臂上试 `{1e-6, 3e-6}`）；`grpo_sd` 下 `sdl_loss_coef` 从 SMRC-SD 的 0.01 起扫 `{0.01, 0.05, 0.2}`。都只在 L3 臂上扫，其余臂沿用。
2. **同步教师 vs 冻结基座教师**：文献都用同步教师。若同步教师下 L1/L2 信号过弱，可加一个 `teacher_source: current | base` 开关（verl 已有 ref policy，可复用其权重做教师前向），但这是第二阶段的事。
3. **等预算的定义**：按"进入 SDL 的响应 token 数"计。L0 臂没有 SDL，按训练 step 数与 L3 对齐。
4. **参考轨迹**：不开 think 后 walkthrough 渲染成 `<action>…</action>` 与学生响应格式一致，E1/E4 直接用它做参考；E4 可再加环境验证过的学生成功轨迹扩充参考池。
5. **E1 的 `copy` 指标在 OPD 仓库第一批数据里倒挂**，换参考后未验证。在它通过正向检验前不进任何 reward。
6. **纯蒸馏可能起得慢**：agent 论文都合用 RL；我们为对齐 swift 默认 `sd_only`。若 L3 臂 100 步内 seen 成功率相对基座没有提升，切 `grpo_sd` 预设重跑，并在论文里说明。Qwen3-4B 基座的 ALFWorld 成功率在阶段 0 记录，不要沿用 1.7B 的 7% 直觉。
8. **响应极短**：不开 think 后每步响应约 5–10 个 token，SDL 每步信号少、噪声大。这是与 swift 对齐的代价；`sdl_loss_normalization: response_token_mean` 下不会因为短而放大梯度，但需要更多步数。不要为此偷偷把 think 加回来。
7. **状态与参考失配**：L3 便签写的是位置事实而非动作路径，学生走偏后事实仍然为真，比 FULLPATH 更稳；FULLPATH 臂预期会复现 SMRC-SD 描述的失配问题，这本身是论文可以报告的对照。