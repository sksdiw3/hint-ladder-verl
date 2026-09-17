# Turn 级 hint 分层：公共信息、推理帮助与 Oracle

更新于 2026-09-17。这里记录最近讨论后实际用于 30 题对照的 L1–L3，以及尚未实施的 L4 方向。历史训练用过同名但含义不同的 Oracle L3，本文明确区分。

## 分层分的是什么

目前分层控制的是 **GLM 帮学生把决策推进到哪一步**：L1 提供方向，L2 提供局部分析与候选，L3 提供明确下一动作。三者在最新诊断中得到完全相同的公共状态，不依靠额外隐藏事实拉开等级。

语义层级、Oracle 信息权限、文字长度，以及带 hint 后的 next-token 分布变化是不同维度。KL 衡量后者，既不保证随 L1→L3 单调增加，也不能单独证明 hint 正确、有效或适合学习。

| 级别 | GLM 应提供什么 | 可以出现什么 | 应留给学生什么 | Oracle 权限 / 实施情况 |
|---|---|---|---|---|
| L0 | 不提供 hint | 原始公开状态 | 完整分析与决策 | 无；Base 对照 |
| L1 | 当前问题的轻量方向 | 物品用途、常见摆放规律、需要满足的目标条件 | 具体地点、具体操作与最终动作 | 无；已跑 30 题 |
| L2 | 当前状态的局部分析，解释可能性和理由 | 候选地点、可能的操作，例如“可能在 A / B，理由是……” | 不替学生确定唯一下一步；不展开整条任务路径 | 无；已跑 30 题 |
| L3（public） | 明确推荐一个当前合法动作，附简短理由 | 精确动作字符串，如 `go to fridge 1` | 仍由学生生成自己的 reasoning / action，可以不采纳 | 无；已跑 30 题，建议可能错误 |
| L4（拟议） | 在更强信息基础上给出可验证的指示 | 来自 Oracle 或先行环境探索的事实与动作 | 待下一轮设计明确 | **尚未实现或纳入这次对照** |

L4 不能仅靠把语气改得更肯定：如果声称“去 A，那里有物品 X”，需要实际 Oracle/环境证据支持。历史 walkthrough Oracle L3 是相关先例，但不能直接把它重命名后声称已经完成新的 L4 对照。

## 最新三层共享的输入

GLM 每个 turn 看到与 Student 相同的公共信息：

```json
{
  "task": "当前任务原文",
  "step_count": "已经执行的动作数",
  "current_step": "当前轮次",
  "current_observation": "当前环境反馈原文",
  "action_history": [
    {"turn": "最近保留轮次", "observation": "当时观察", "action": "实际执行动作"}
  ],
  "action_space": ["当前完整合法动作列表"]
}
```

`action_history` 最多两项，包含对应观察与已执行动作；不是完整历史，也不包含过往 reasoning。L1–L3 不获得隐藏 inventory、walkthrough、隐藏位置、未来反馈或 Student 当前未完成的 response。环境公开动作列表本身可能透露可操作物品，但不能凭空补成完整 inventory。

每层分别调用一次 GLM-5.3-Flash，不在同一次回复里联合生成三种 hint。独立 rollout 中，每到一个新状态生成该层 hint；KL 诊断中，每个无 hint Base 状态各生成 L1/L2/L3，再固定同一条 Base response prefix 评分。仅相同层级、公共状态、prompt、seed 与生成配置都匹配时复用已完成 hint。

生成设置是 temperature=0.7、thinking=enabled、reasoning_effort=low、首试 max_tokens=1536；传输或未完整输出可重试，后续尝试上限 3072，最多四次且 seed 改变。模型收到的 hint 是 GLM 可见的最终 `message.content`；隐藏推理不进入 Student。

## 实际 system prompts（原文）

以下与 [2026-09-16 实际归档](experiments/updates_20260917/public_hint_kl/protocol.json)逐字对应，未为了发布重新润色。

### L1：方向

```text
你在帮助另一个智能体完成任务。根据它的任务、当前观察和历史动作，给一个轻量的提示，帮助它结合当前进展想清楚眼前的问题。还在寻找物品时，可以引导它联想物品用途和常见摆放规律；所需物品已经出现时，提醒它围绕眼前资源和任务目标继续思考。把具体地点和具体操作留给它自己推断，不在提示中点名目的地或描述要执行的动作。只输出一两句简短的英文提示。
```

### L2：局部分析和候选

```text
You are discussing the current ALFWorld state with another agent. You have the same task, observation, recent observation-action history, and available actions that it sees. Give an L2 hint in one paragraph of 3–5 sentences: explain one or two useful interpretations of the current evidence and plausible options, with a reason for considering them. Specific locations or operations may appear as possibilities, but leave the next action undecided. Stay with the immediate question rather than mapping out what to do after it is resolved. State observed facts clearly and treat unobserved facts as hypotheses. Address the agent naturally in English, using a collaborative rather than directive tone.
```

### L3（public）：明确动作建议，无 Oracle

```text
You are helping another agent act in ALFWorld. You see the same task, current observation, recent observation-action history, and admissible actions as the agent. Give an L3 hint: recommend one specific next action from the admissible actions, and briefly explain why it is useful for the task at this state. State the recommendation clearly and include the exact action text. You have no Oracle or hidden environment information: do not claim that an unobserved object is definitely at a location. Preserve all requirements of the task. Output one or two sentences in English.
```

例如真实任务 `heat some egg and put it in countertop.` 的第一轮，GLM 返回：

```text
Recommended next action: "go to fridge 1". Since the task requires heating an egg, the first step is to find one, and the fridge is the most likely place eggs are stored in the kitchen before searching other locations.
```

这是一条搜索建议，并非知道鸡蛋确实在冰箱里。该题的 Base turn3 打开冰箱后，观察中只有 bowl / pan / plate / potato，没有 egg；此时 L3 改为推荐去 countertop 1。完整同状态 L1/L2/L3、GLM 输入与原始输出见[真实示例](experiments/updates_20260917/public_hint_kl/hint_examples_same_state.md)。

## 给 Qwen 的注入方式与 OPD 区别

原 Student prompt 保持不变，只额外插入下面的便签及使用说明：

```text
<private_teacher_note>
{GLM hint}
</private_teacher_note>
Use this hint as optional guidance for your reasoning; check it against the current observation and admissible actions. Keep the required response format and do not mention the hint.
```

实际实现会断言移除便签后与原 prompt 相同。独立 `Base + Lx` 推理让 Qwen 带 hint 自行生成完整轨迹；OPD 训练则让无 hint Student 生成，只有评分 Teacher 接收 hint，在 Student prefix 下产生监督分布。不要把带 hint 的推理成功率当作 OPD 训练成功率。

目前的三层诊断是每个到达的 turn 都提供 hint。未来“选择哪些 turn 给 hint、选择哪些 turn 监督、学习适合学生的 hint”的设想仍未实现；这次没有训练 Hinter，也没有学习给 hint 的时机。

## 实测：语义等级并不等于分布变化大小

30 题无 hint Base 的 992 个 turns、221,620 个原始 token 位置上，固定 prefix 计算完整 151,936 词表的 KL。主指标只取 reasoning 正文，T=1、自然对数，每题内按 token 平均、题目间等权。

| Hint | KL(hint ‖ Base)，nats/token | 平均 hint 词数（空白分词） |
|---|---:|---:|
| L1 | 0.649295 | 32.5 |
| L2 | 1.105531 | 142.0 |
| L3（public） | 0.971287 | 46.4 |

27/30 题是 L2 > L3。L2 更长、包含更多局部分析，可能解释部分差异，但长度未控制，不能作独立因果归因。API 完成不等于语义质量合格；实际 hint 可能越界、复述或提出错误假设。现有输出全部保留，没有按效果或措辞重抽。[完整统计与限制](experiments/updates_20260917/public_hint_kl/REPORT.md)。

## 历史命名与已完成训练

| 日期 / 实验 | 当时标签 | 含义 |
|---|---|---|
| 早期两层方案 | L1 / L2 | 无 Oracle 方向提示 / 有 Oracle 明确动作 |
| 2026-09-14 冻结教师训练 | L3（Oracle） | walkthrough 经过环境验证的下一步参考动作，GLM 只原样返回动作 |
| 2026-09-16 的 30 题诊断 | L1 / L2 / L3（public） | 相同公共信息下，方向 / 局部分析 / 明确决策，均无 Oracle |

历史 Oracle L3 的实际 prompt：

```text
You provide an oracle hint for the current ALFWorld state. The supplied next_reference_action has been checked against the real environment. Reply with that exact action as the hint, preserving object and location numbers. Output only the action, with no explanation or additional steps.
```

历史 L1 训练的 GLM 输入还未对齐完整 observation/action history 和 action space；新 30 题协议已对齐。旧 L1 / Oracle L3 的训练成功率与长度请看[冻结教师训练报告](experiments/updates_20260917/frozen_teacher_training/README.md)。新 L2 / public L3 目前只有这批推理与 KL 数据，不声称已有对应 OPD 训练结果。
