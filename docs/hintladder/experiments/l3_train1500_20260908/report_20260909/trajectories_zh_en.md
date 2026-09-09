# Base 与 step150：同题完整轨迹 / Matched-task trajectories

四组验证任务、八条 episode；所有已记录的决策步均展示，重复动作不省略。每一步为动作前观察及模型输出；中文是事后翻译，模型实际看到、输出的都是英文。

Four validation games, eight complete recorded decision sequences. Chinese text is a post-hoc translation, not model reasoning or model input. Repeated actions are retained.

按完整 `gamefile` 配对。人为选择两组退步、两组进步来解释行为；不是随机抽样，不能用这 8 条估计整体成功率。指定题型和所需成败组合后，按 gamefile、traj_uid 字典序取首条符合的轨迹。每题实际都有 4 次采样，下面同时列出该题全部 4 次的成功数。跨 checkpoint 的随机采样不是同一次随机抽样。

Pairs match exact gamefiles, not trajectory IDs or random draws. These outcome-selected examples illustrate behavior, not population performance. Within each named task/outcome stratum, selection uses lexicographic gamefile and trajectory ID order; all four-sample results are disclosed.

评测无 hint，temperature=0.4，上限30步。环境 `won` 判成功，导出 `episode_rewards=10` 表示成功、0 表示失败。look 类任务的实际成功条件涉及持有目标物体及灯开启，不能把自然语言 examine 等同于必须输出 examine 命令。

Evaluation uses no hints, temperature 0.4, and at most 30 actions. Success comes from the environment, not our translation. The terminal post-action observation is absent from the source dump; no terminal message is invented here.

[完整原始 prompt、逐步动作空间、原始输出与来源行号 / Raw prompts, admissible actions, outputs and provenance](trajectories.jsonl) · [总体实验报告](REPORT.md)

JSONL 每行是一条 episode，`turns[].raw` 保留原始日志记录的全部字段；不是 token ID 文件。表中的 HTML 换行用于展示，原始换行保留在 JSONL。输入 prompt 末尾的空 `<think>…</think>` 是聊天模板前缀；不应与模型 response 里违规生成的 thinking 标签混淆。

## 1. seen_ladle — valid_seen

`valid_seen/pick_clean_then_place_in_recep-Ladle-None-DiningTable-4/trial_T20190909_164840_568811/game.tw-pddl`

该题四次采样 / All four samples：base **4/4** → step150 **0/4**。

base 完成清洗和放置；step150 拿到汤勺并到达水槽后离开，随后反复移动。

Base cleans and places the ladle; step150 leaves the sink after collecting it and then repeatedly moves.

### Base / 训练前 — 成功 / success，12 步

**Task:** clean some ladle and put it in diningtable.

**题目：**清洗一把汤勺，并将它放到餐桌上。

`traj_uid: 038aa327-7e29-4b22-9271-bdabfc9b5180`

| 步 / Turn | 动作前观察 / Observation before action | 模型原始输出 / Model output | 动作中文释义 / Chinese action |
|---|---|---|---|
| 1 | EN: -= Welcome to TextWorld, ALFRED! =-<br><br>You are in the middle of a room. Looking quickly around you, you see a cabinet 2, a cabinet 1, a coffeemachine 1, a countertop 3, a countertop 2, a countertop 1, a diningtable 1, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a fridge 1, a garbagecan 1, a microwave 1, a sinkbasin 1, a stoveburner 4, a stoveburner 3, a stoveburner 2, a stoveburner 1, and a toaster 1.<br>中：欢迎来到 TextWorld，ALFRED！<br><br>你位于房间中央，快速环顾四周，看到：柜子 2、柜子 1、咖啡机 1、操作台 3、操作台 2、操作台 1、餐桌 1、抽屉 6、抽屉 5、抽屉 4、抽屉 3、抽屉 2、抽屉 1、冰箱 1、垃圾桶 1、微波炉 1、水槽 1、灶眼 4、灶眼 3、灶眼 2、灶眼 1、烤面包机 1。 | &lt;action&gt;go to sinkbasin 1&lt;/action&gt; | 前往水槽 1 |
| 2 | EN: You arrive at sinkbasin 1. On the sinkbasin 1, you see a apple 2, a fork 3, a potato 2, and a spoon 3.<br>中：你到达水槽 1。在水槽 1上，你看到：苹果 2、叉子 3、土豆 2、勺子 3。 | &lt;action&gt;examine sinkbasin 1&lt;/action&gt; | 查看水槽 1 |
| 3 | EN: On the sinkbasin 1, you see a apple 2, a fork 3, a potato 2, and a spoon 3.<br>中：在水槽 1上，你看到：苹果 2、叉子 3、土豆 2、勺子 3。 | &lt;action&gt;look&lt;/action&gt; | 查看周围 |
| 4 | EN: You are facing the sinkbasin 1. Next to it, you see nothing.<br>中：你正面对水槽 1，旁边没有看到任何东西。 | &lt;action&gt;look&lt;/action&gt; | 查看周围 |
| 5 | EN: You are facing the sinkbasin 1. Next to it, you see nothing.<br>中：你正面对水槽 1，旁边没有看到任何东西。 | &lt;action&gt;examine sinkbasin 1&lt;/action&gt; | 查看水槽 1 |
| 6 | EN: On the sinkbasin 1, you see a apple 2, a fork 3, a potato 2, and a spoon 3.<br>中：在水槽 1上，你看到：苹果 2、叉子 3、土豆 2、勺子 3。 | &lt;action&gt;take ladle 1 from sinkbasin 1&lt;/action&gt; | 从水槽 1拿起汤勺 1 |
| 7 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;go to diningtable 1&lt;/action&gt; | 前往餐桌 1 |
| 8 | EN: You arrive at diningtable 1. On the diningtable 1, you see a apple 3, a bowl 2, a bread 2, a egg 3, a knife 2, a ladle 2, a mug 2, a pan 1, a peppershaker 3, a peppershaker 2, a plate 3, a saltshaker 3, and a soapbottle 1.<br>中：你到达餐桌 1。在餐桌 1上，你看到：苹果 3、碗 2、面包 2、鸡蛋 3、刀 2、汤勺 2、马克杯 2、平底锅 1、胡椒瓶 3、胡椒瓶 2、盘子 3、盐瓶 3、洗手液瓶 1。 | &lt;action&gt;take ladle 2 from diningtable 1&lt;/action&gt; | 从餐桌 1拿起汤勺 2 |
| 9 | EN: You pick up the ladle 2 from the diningtable 1.<br>中：你从餐桌 1拿起汤勺 2。 | &lt;action&gt;go to sinkbasin 1&lt;/action&gt; | 前往水槽 1 |
| 10 | EN: You arrive at sinkbasin 1. On the sinkbasin 1, you see a apple 2, a fork 3, a potato 2, and a spoon 3.<br>中：你到达水槽 1。在水槽 1上，你看到：苹果 2、叉子 3、土豆 2、勺子 3。 | &lt;action&gt;clean ladle 2 with sinkbasin 1&lt;/action&gt; | 用水槽 1清洗汤勺 2 |
| 11 | EN: You clean the ladle 2 using the sinkbasin 1.<br>中：你用水槽 1清洗了汤勺 2。 | &lt;action&gt;go to diningtable 1&lt;/action&gt; | 前往餐桌 1 |
| 12 | EN: You arrive at diningtable 1. On the diningtable 1, you see a apple 3, a bowl 2, a bread 2, a egg 3, a knife 2, a mug 2, a pan 1, a peppershaker 3, a peppershaker 2, a plate 3, a saltshaker 3, and a soapbottle 1.<br>中：你到达餐桌 1。在餐桌 1上，你看到：苹果 3、碗 2、面包 2、鸡蛋 3、刀 2、马克杯 2、平底锅 1、胡椒瓶 3、胡椒瓶 2、盘子 3、盐瓶 3、洗手液瓶 1。 | &lt;action&gt;move ladle 2 to diningtable 1&lt;/action&gt; | 把汤勺 2放到餐桌 1 |

**环境结果 / Environment result:** episode_rewards=10.0；success。末动作之后的环境观察未保存 / Final post-action observation not recorded.

### Step150 / 训练后 — 失败 / failure，30 步

**Task:** clean some ladle and put it in diningtable.

**题目：**清洗一把汤勺，并将它放到餐桌上。

`traj_uid: 349a05fe-d632-458e-a0f0-e869f76f45de`

| 步 / Turn | 动作前观察 / Observation before action | 模型原始输出 / Model output | 动作中文释义 / Chinese action |
|---|---|---|---|
| 1 | EN: -= Welcome to TextWorld, ALFRED! =-<br><br>You are in the middle of a room. Looking quickly around you, you see a cabinet 2, a cabinet 1, a coffeemachine 1, a countertop 3, a countertop 2, a countertop 1, a diningtable 1, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a fridge 1, a garbagecan 1, a microwave 1, a sinkbasin 1, a stoveburner 4, a stoveburner 3, a stoveburner 2, a stoveburner 1, and a toaster 1.<br>中：欢迎来到 TextWorld，ALFRED！<br><br>你位于房间中央，快速环顾四周，看到：柜子 2、柜子 1、咖啡机 1、操作台 3、操作台 2、操作台 1、餐桌 1、抽屉 6、抽屉 5、抽屉 4、抽屉 3、抽屉 2、抽屉 1、冰箱 1、垃圾桶 1、微波炉 1、水槽 1、灶眼 4、灶眼 3、灶眼 2、灶眼 1、烤面包机 1。 | &lt;action&gt;<br>go to diningtable 1<br>&lt;/action&gt; | 前往餐桌 1 |
| 2 | EN: You arrive at diningtable 1. On the diningtable 1, you see a apple 3, a bowl 2, a bread 2, a egg 3, a knife 2, a ladle 2, a mug 2, a pan 1, a peppershaker 3, a peppershaker 2, a plate 3, a saltshaker 3, and a soapbottle 1.<br>中：你到达餐桌 1。在餐桌 1上，你看到：苹果 3、碗 2、面包 2、鸡蛋 3、刀 2、汤勺 2、马克杯 2、平底锅 1、胡椒瓶 3、胡椒瓶 2、盘子 3、盐瓶 3、洗手液瓶 1。 | &lt;action&gt;<br>take ladle 2 from diningtable 1<br>&lt;/action&gt; | 从餐桌 1拿起汤勺 2 |
| 3 | EN: You pick up the ladle 2 from the diningtable 1.<br>中：你从餐桌 1拿起汤勺 2。 | &lt;action&gt;<br>go to sinkbasin 1<br>&lt;/action&gt; | 前往水槽 1 |
| 4 | EN: You arrive at sinkbasin 1. On the sinkbasin 1, you see a apple 2, a fork 3, a potato 2, and a spoon 3.<br>中：你到达水槽 1。在水槽 1上，你看到：苹果 2、叉子 3、土豆 2、勺子 3。 | &lt;action&gt;<br>go to countertop 1<br>&lt;/action&gt; | 前往操作台 1 |
| 5 | EN: You arrive at countertop 1. On the countertop 1, you see a cup 1, and a fork 1.<br>中：你到达操作台 1。在操作台 1上，你看到：杯子 1、叉子 1。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |
| 6 | EN: You arrive at countertop 2. On the countertop 2, you see a bread 1, a butterknife 1, a fork 2, a houseplant 1, a knife 1, a ladle 1, a saltshaker 1, and a spoon 2.<br>中：你到达操作台 2。在操作台 2上，你看到：面包 1、黄油刀 1、叉子 2、盆栽 1、刀 1、汤勺 1、盐瓶 1、勺子 2。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |
| 7 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |
| 8 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |
| 9 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to countertop 1<br>&lt;/action&gt; | 前往操作台 1 |
| 10 | EN: You arrive at countertop 1. On the countertop 1, you see a cup 1, and a fork 1.<br>中：你到达操作台 1。在操作台 1上，你看到：杯子 1、叉子 1。 | &lt;action&gt;<br>go to diningtable 1<br>&lt;/action&gt; | 前往餐桌 1 |
| 11 | EN: You arrive at diningtable 1. On the diningtable 1, you see a apple 3, a bowl 2, a bread 2, a egg 3, a knife 2, a mug 2, a pan 1, a peppershaker 3, a peppershaker 2, a plate 3, a saltshaker 3, and a soapbottle 1.<br>中：你到达餐桌 1。在餐桌 1上，你看到：苹果 3、碗 2、面包 2、鸡蛋 3、刀 2、马克杯 2、平底锅 1、胡椒瓶 3、胡椒瓶 2、盘子 3、盐瓶 3、洗手液瓶 1。 | &lt;action&gt;<br>go to countertop 1<br>&lt;/action&gt; | 前往操作台 1 |
| 12 | EN: You arrive at countertop 1. On the countertop 1, you see a cup 1, and a fork 1.<br>中：你到达操作台 1。在操作台 1上，你看到：杯子 1、叉子 1。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |
| 13 | EN: You arrive at countertop 2. On the countertop 2, you see a bread 1, a butterknife 1, a fork 2, a houseplant 1, a knife 1, a ladle 1, a saltshaker 1, and a spoon 2.<br>中：你到达操作台 2。在操作台 2上，你看到：面包 1、黄油刀 1、叉子 2、盆栽 1、刀 1、汤勺 1、盐瓶 1、勺子 2。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |
| 14 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |
| 15 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |
| 16 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |
| 17 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to countertop 1<br>&lt;/action&gt; | 前往操作台 1 |
| 18 | EN: You arrive at countertop 1. On the countertop 1, you see a cup 1, and a fork 1.<br>中：你到达操作台 1。在操作台 1上，你看到：杯子 1、叉子 1。 | &lt;action&gt;<br>go to countertop 1<br>&lt;/action&gt; | 前往操作台 1 |
| 19 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to countertop 1<br>&lt;/action&gt; | 前往操作台 1 |
| 20 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |
| 21 | EN: You arrive at countertop 2. On the countertop 2, you see a bread 1, a butterknife 1, a fork 2, a houseplant 1, a knife 1, a ladle 1, a saltshaker 1, and a spoon 2.<br>中：你到达操作台 2。在操作台 2上，你看到：面包 1、黄油刀 1、叉子 2、盆栽 1、刀 1、汤勺 1、盐瓶 1、勺子 2。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |
| 22 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |
| 23 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |
| 24 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to countertop 1<br>&lt;/action&gt; | 前往操作台 1 |
| 25 | EN: You arrive at countertop 1. On the countertop 1, you see a cup 1, and a fork 1.<br>中：你到达操作台 1。在操作台 1上，你看到：杯子 1、叉子 1。 | &lt;action&gt;<br>go to countertop 1<br>&lt;/action&gt; | 前往操作台 1 |
| 26 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to diningtable 1<br>&lt;/action&gt; | 前往餐桌 1 |
| 27 | EN: You arrive at diningtable 1. On the diningtable 1, you see a apple 3, a bowl 2, a bread 2, a egg 3, a knife 2, a mug 2, a pan 1, a peppershaker 3, a peppershaker 2, a plate 3, a saltshaker 3, and a soapbottle 1.<br>中：你到达餐桌 1。在餐桌 1上，你看到：苹果 3、碗 2、面包 2、鸡蛋 3、刀 2、马克杯 2、平底锅 1、胡椒瓶 3、胡椒瓶 2、盘子 3、盐瓶 3、洗手液瓶 1。 | &lt;action&gt;<br>go to countertop 1<br>&lt;/action&gt; | 前往操作台 1 |
| 28 | EN: You arrive at countertop 1. On the countertop 1, you see a cup 1, and a fork 1.<br>中：你到达操作台 1。在操作台 1上，你看到：杯子 1、叉子 1。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |
| 29 | EN: You arrive at countertop 2. On the countertop 2, you see a bread 1, a butterknife 1, a fork 2, a houseplant 1, a knife 1, a ladle 1, a saltshaker 1, and a spoon 2.<br>中：你到达操作台 2。在操作台 2上，你看到：面包 1、黄油刀 1、叉子 2、盆栽 1、刀 1、汤勺 1、盐瓶 1、勺子 2。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |
| 30 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to countertop 2<br>&lt;/action&gt; | 前往操作台 2 |

**环境结果 / Environment result:** episode_rewards=0.0；failure。末动作之后的环境观察未保存 / Final post-action observation not recorded.

## 2. seen_bowl — valid_seen

`valid_seen/look_at_obj_in_light-Bowl-None-DeskLamp-316/trial_T20190908_230702_962704/game.tw-pddl`

该题四次采样 / All four samples：base **0/4** → step150 **3/4**。

base 困在边桌附近；step150 虽然多次往返，最终在台灯开启后拿起碗，环境判成功。

Base stays around the side table; step150 makes repeated trips but eventually picks up the bowl with the lamp on and succeeds.

### Base / 训练前 — 失败 / failure，30 步

**Task:** examine the bowl with the desklamp.

**题目：**借助台灯查看碗。

`traj_uid: 041a9704-eea7-4ed5-8dcd-bd9604356c51`

| 步 / Turn | 动作前观察 / Observation before action | 模型原始输出 / Model output | 动作中文释义 / Chinese action |
|---|---|---|---|
| 1 | EN: -= Welcome to TextWorld, ALFRED! =-<br><br>You are in the middle of a room. Looking quickly around you, you see a bed 1, a desk 1, a drawer 2, a drawer 1, a garbagecan 1, a shelf 1, and a sidetable 1.<br>中：欢迎来到 TextWorld，ALFRED！<br><br>你位于房间中央，快速环顾四周，看到：床 1、书桌 1、抽屉 2、抽屉 1、垃圾桶 1、置物架 1、边桌 1。 | &lt;action&gt;look&lt;/action&gt; | 查看周围 |
| 2 | EN: You are in the middle of a room. Looking quickly around you, you see nothing.<br>中：你位于房间中央，快速环顾四周，没有看到任何东西。 | &lt;action&gt;go to sidetable 1&lt;/action&gt; | 前往边桌 1 |
| 3 | EN: You arrive at sidetable 1. On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：你到达边桌 1。在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 4 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 5 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 6 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine bowl&lt;/action&gt; | 查看碗 |
| 7 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 8 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine bowl&lt;/action&gt; | 查看碗 |
| 9 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 10 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine desklamp&lt;/action&gt; | 查看台灯 |
| 11 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine desklamp&lt;/action&gt; | 查看台灯 |
| 12 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 13 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 14 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 15 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 16 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 17 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 18 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 19 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 20 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 21 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine bowl with desklamp&lt;/action&gt; | 借助台灯查看碗 |
| 22 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 23 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 24 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine bowl 1&lt;/action&gt; | 查看碗 1 |
| 25 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 26 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine desklamp 1&lt;/action&gt; | 查看台灯 1 |
| 27 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine desklamp 1&lt;/action&gt; | 查看台灯 1 |
| 28 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 29 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine sidetable 1&lt;/action&gt; | 查看边桌 1 |
| 30 | EN: On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;examine bowl 1&lt;/action&gt; | 查看碗 1 |

**环境结果 / Environment result:** episode_rewards=0.0；failure。末动作之后的环境观察未保存 / Final post-action observation not recorded.

### Step150 / 训练后 — 成功 / success，18 步

**Task:** examine the bowl with the desklamp.

**题目：**借助台灯查看碗。

`traj_uid: 51e7d43b-622b-4dc8-992d-d05e9185132a`

| 步 / Turn | 动作前观察 / Observation before action | 模型原始输出 / Model output | 动作中文释义 / Chinese action |
|---|---|---|---|
| 1 | EN: -= Welcome to TextWorld, ALFRED! =-<br><br>You are in the middle of a room. Looking quickly around you, you see a bed 1, a desk 1, a drawer 2, a drawer 1, a garbagecan 1, a shelf 1, and a sidetable 1.<br>中：欢迎来到 TextWorld，ALFRED！<br><br>你位于房间中央，快速环顾四周，看到：床 1、书桌 1、抽屉 2、抽屉 1、垃圾桶 1、置物架 1、边桌 1。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 2 | EN: You arrive at desk 1. On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 1, a desklamp 1, a houseplant 1, a keychain 2, a keychain 1, and a pen 1.<br>中：你到达书桌 1。在书桌 1上，你看到：闹钟 1、碗 1、光盘 2、光盘 1、手机 1、台灯 1、盆栽 1、钥匙串 2、钥匙串 1、笔 1。 | &lt;action&gt;<br>use desklamp 1<br>&lt;/action&gt; | 使用台灯 1 |
| 3 | EN: You turn on the desklamp 1.<br>中：你打开了台灯 1。 | &lt;action&gt;<br>go to sidetable 1<br>&lt;/action&gt; | 前往边桌 1 |
| 4 | EN: You arrive at sidetable 1. On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：你到达边桌 1。在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 5 | EN: You arrive at desk 1. On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 1, a desklamp 1, a houseplant 1, a keychain 2, a keychain 1, and a pen 1.<br>中：你到达书桌 1。在书桌 1上，你看到：闹钟 1、碗 1、光盘 2、光盘 1、手机 1、台灯 1、盆栽 1、钥匙串 2、钥匙串 1、笔 1。 | &lt;action&gt;<br>go to sidetable 1<br>&lt;/action&gt; | 前往边桌 1 |
| 6 | EN: You arrive at sidetable 1. On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：你到达边桌 1。在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 7 | EN: You arrive at desk 1. On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 1, a desklamp 1, a houseplant 1, a keychain 2, a keychain 1, and a pen 1.<br>中：你到达书桌 1。在书桌 1上，你看到：闹钟 1、碗 1、光盘 2、光盘 1、手机 1、台灯 1、盆栽 1、钥匙串 2、钥匙串 1、笔 1。 | &lt;action&gt;<br>go to sidetable 1<br>&lt;/action&gt; | 前往边桌 1 |
| 8 | EN: You arrive at sidetable 1. On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：你到达边桌 1。在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 9 | EN: You arrive at desk 1. On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 1, a desklamp 1, a houseplant 1, a keychain 2, a keychain 1, and a pen 1.<br>中：你到达书桌 1。在书桌 1上，你看到：闹钟 1、碗 1、光盘 2、光盘 1、手机 1、台灯 1、盆栽 1、钥匙串 2、钥匙串 1、笔 1。 | &lt;action&gt;<br>go to sidetable 1<br>&lt;/action&gt; | 前往边桌 1 |
| 10 | EN: You arrive at sidetable 1. On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：你到达边桌 1。在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 11 | EN: You arrive at desk 1. On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 1, a desklamp 1, a houseplant 1, a keychain 2, a keychain 1, and a pen 1.<br>中：你到达书桌 1。在书桌 1上，你看到：闹钟 1、碗 1、光盘 2、光盘 1、手机 1、台灯 1、盆栽 1、钥匙串 2、钥匙串 1、笔 1。 | &lt;action&gt;<br>use desklamp 1<br>&lt;/action&gt; | 使用台灯 1 |
| 12 | EN: You turn on the desklamp 1.<br>中：你打开了台灯 1。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 13 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>use desklamp 1<br>&lt;/action&gt; | 使用台灯 1 |
| 14 | EN: You turn on the desklamp 1.<br>中：你打开了台灯 1。 | &lt;action&gt;<br>use desklamp 1<br>&lt;/action&gt; | 使用台灯 1 |
| 15 | EN: You turn on the desklamp 1.<br>中：你打开了台灯 1。 | &lt;action&gt;<br>go to sidetable 1<br>&lt;/action&gt; | 前往边桌 1 |
| 16 | EN: You arrive at sidetable 1. On the sidetable 1, you see a alarmclock 3, a alarmclock 2, and a pencil 2.<br>中：你到达边桌 1。在边桌 1上，你看到：闹钟 3、闹钟 2、铅笔 2。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 17 | EN: You arrive at desk 1. On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 1, a desklamp 1, a houseplant 1, a keychain 2, a keychain 1, and a pen 1.<br>中：你到达书桌 1。在书桌 1上，你看到：闹钟 1、碗 1、光盘 2、光盘 1、手机 1、台灯 1、盆栽 1、钥匙串 2、钥匙串 1、笔 1。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 18 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>take bowl 1 from desk 1<br>&lt;/action&gt; | 从书桌 1拿起碗 1 |

**环境结果 / Environment result:** episode_rewards=10.0；success。末动作之后的环境观察未保存 / Final post-action observation not recorded.

## 3. unseen_pencil — valid_unseen

`valid_unseen/pick_and_place_simple-Pencil-None-Shelf-308/trial_T20190908_121952_610012/game.tw-pddl`

该题四次采样 / All four samples：base **1/4** → step150 **0/4**。

base 完成拿取和放置；step150 拿到铅笔后仍只移动，没有执行放置。

Base picks up and places the pencil; step150 picks it up but keeps moving without placing it.

### Base / 训练前 — 成功 / success，8 步

**Task:** put a pencil in shelf.

**题目：**把一支铅笔放到置物架上。

`traj_uid: 5a435fdf-0a63-469b-9dd3-4e2dca96b4ea`

| 步 / Turn | 动作前观察 / Observation before action | 模型原始输出 / Model output | 动作中文释义 / Chinese action |
|---|---|---|---|
| 1 | EN: -= Welcome to TextWorld, ALFRED! =-<br><br>You are in the middle of a room. Looking quickly around you, you see a bed 1, a desk 2, a desk 1, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a garbagecan 1, a laundryhamper 1, a safe 1, a shelf 6, a shelf 5, a shelf 4, a shelf 3, a shelf 2, and a shelf 1.<br>中：欢迎来到 TextWorld，ALFRED！<br><br>你位于房间中央，快速环顾四周，看到：床 1、书桌 2、书桌 1、抽屉 6、抽屉 5、抽屉 4、抽屉 3、抽屉 2、抽屉 1、垃圾桶 1、洗衣篮 1、保险箱 1、置物架 6、置物架 5、置物架 4、置物架 3、置物架 2、置物架 1。 | &lt;action&gt;go to shelf 1&lt;/action&gt; | 前往置物架 1 |
| 2 | EN: You arrive at shelf 1. On the shelf 1, you see a keychain 2.<br>中：你到达置物架 1。在置物架 1上，你看到：钥匙串 2。 | &lt;action&gt;examine shelf 1&lt;/action&gt; | 查看置物架 1 |
| 3 | EN: On the shelf 1, you see a keychain 2.<br>中：在置物架 1上，你看到：钥匙串 2。 | &lt;action&gt;take keychain 2 from shelf 1&lt;/action&gt; | 从置物架 1拿起钥匙串 2 |
| 4 | EN: You pick up the keychain 2 from the shelf 1.<br>中：你从置物架 1拿起钥匙串 2。 | &lt;action&gt;move keychain 2 to shelf 1&lt;/action&gt; | 把钥匙串 2放到置物架 1 |
| 5 | EN: You move the keychain 2 to the shelf 1.<br>中：你把钥匙串 2放到置物架 1。 | &lt;action&gt;go to desk 1&lt;/action&gt; | 前往书桌 1 |
| 6 | EN: You arrive at desk 1. On the desk 1, you see a desklamp 1, a keychain 1, and a pencil 1.<br>中：你到达书桌 1。在书桌 1上，你看到：台灯 1、钥匙串 1、铅笔 1。 | &lt;action&gt;take pencil 1 from desk 1&lt;/action&gt; | 从书桌 1拿起铅笔 1 |
| 7 | EN: You pick up the pencil 1 from the desk 1.<br>中：你从书桌 1拿起铅笔 1。 | &lt;action&gt;go to shelf 1&lt;/action&gt; | 前往置物架 1 |
| 8 | EN: You arrive at shelf 1. On the shelf 1, you see a keychain 2.<br>中：你到达置物架 1。在置物架 1上，你看到：钥匙串 2。 | &lt;action&gt;move pencil 1 to shelf 1&lt;/action&gt; | 把铅笔 1放到置物架 1 |

**环境结果 / Environment result:** episode_rewards=10.0；success。末动作之后的环境观察未保存 / Final post-action observation not recorded.

### Step150 / 训练后 — 失败 / failure，30 步

**Task:** put a pencil in shelf.

**题目：**把一支铅笔放到置物架上。

`traj_uid: 0d195dbd-a04d-4774-8394-4e7edc437042`

| 步 / Turn | 动作前观察 / Observation before action | 模型原始输出 / Model output | 动作中文释义 / Chinese action |
|---|---|---|---|
| 1 | EN: -= Welcome to TextWorld, ALFRED! =-<br><br>You are in the middle of a room. Looking quickly around you, you see a bed 1, a desk 2, a desk 1, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a garbagecan 1, a laundryhamper 1, a safe 1, a shelf 6, a shelf 5, a shelf 4, a shelf 3, a shelf 2, and a shelf 1.<br>中：欢迎来到 TextWorld，ALFRED！<br><br>你位于房间中央，快速环顾四周，看到：床 1、书桌 2、书桌 1、抽屉 6、抽屉 5、抽屉 4、抽屉 3、抽屉 2、抽屉 1、垃圾桶 1、洗衣篮 1、保险箱 1、置物架 6、置物架 5、置物架 4、置物架 3、置物架 2、置物架 1。 | &lt;action&gt;<br>go to shelf 1<br>&lt;/action&gt; | 前往置物架 1 |
| 2 | EN: You arrive at shelf 1. On the shelf 1, you see a keychain 2.<br>中：你到达置物架 1。在置物架 1上，你看到：钥匙串 2。 | &lt;action&gt;<br>go to shelf 2<br>&lt;/action&gt; | 前往置物架 2 |
| 3 | EN: You arrive at shelf 2. On the shelf 2, you see a alarmclock 1.<br>中：你到达置物架 2。在置物架 2上，你看到：闹钟 1。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 4 | EN: You arrive at desk 1. On the desk 1, you see a desklamp 1, a keychain 1, and a pencil 1.<br>中：你到达书桌 1。在书桌 1上，你看到：台灯 1、钥匙串 1、铅笔 1。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 5 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 6 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 7 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to shelf 1<br>&lt;/action&gt; | 前往置物架 1 |
| 8 | EN: You arrive at shelf 1. On the shelf 1, you see a keychain 2.<br>中：你到达置物架 1。在置物架 1上，你看到：钥匙串 2。 | &lt;action&gt;<br>go to shelf 1<br>&lt;/action&gt; | 前往置物架 1 |
| 9 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 10 | EN: You arrive at desk 1. On the desk 1, you see a desklamp 1, a keychain 1, and a pencil 1.<br>中：你到达书桌 1。在书桌 1上，你看到：台灯 1、钥匙串 1、铅笔 1。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 11 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>take pencil 1 from desk 1<br>&lt;/action&gt; | 从书桌 1拿起铅笔 1 |
| 12 | EN: You pick up the pencil 1 from the desk 1.<br>中：你从书桌 1拿起铅笔 1。 | &lt;action&gt;<br>go to shelf 1<br>&lt;/action&gt; | 前往置物架 1 |
| 13 | EN: You arrive at shelf 1. On the shelf 1, you see a keychain 2.<br>中：你到达置物架 1。在置物架 1上，你看到：钥匙串 2。 | &lt;action&gt;<br>go to shelf 1<br>&lt;/action&gt; | 前往置物架 1 |
| 14 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to shelf 1<br>&lt;/action&gt; | 前往置物架 1 |
| 15 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to shelf 1<br>&lt;/action&gt; | 前往置物架 1 |
| 16 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 17 | EN: You arrive at desk 1. On the desk 1, you see a desklamp 1, and a keychain 1.<br>中：你到达书桌 1。在书桌 1上，你看到：台灯 1、钥匙串 1。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 18 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to shelf 1<br>&lt;/action&gt; | 前往置物架 1 |
| 19 | EN: You arrive at shelf 1. On the shelf 1, you see a keychain 2.<br>中：你到达置物架 1。在置物架 1上，你看到：钥匙串 2。 | &lt;action&gt;<br>go to desk 2<br>&lt;/action&gt; | 前往书桌 2 |
| 20 | EN: You arrive at desk 2. On the desk 2, you see a bowl 1, a cellphone 3, a mug 2, a mug 1, and a pencil 2.<br>中：你到达书桌 2。在书桌 2上，你看到：碗 1、手机 3、马克杯 2、马克杯 1、铅笔 2。 | &lt;action&gt;<br>go to desk 2<br>&lt;/action&gt; | 前往书桌 2 |
| 21 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to desk 2<br>&lt;/action&gt; | 前往书桌 2 |
| 22 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to shelf 2<br>&lt;/action&gt; | 前往置物架 2 |
| 23 | EN: You arrive at shelf 2. On the shelf 2, you see a alarmclock 1.<br>中：你到达置物架 2。在置物架 2上，你看到：闹钟 1。 | &lt;action&gt;<br>go to shelf 1<br>&lt;/action&gt; | 前往置物架 1 |
| 24 | EN: You arrive at shelf 1. On the shelf 1, you see a keychain 2.<br>中：你到达置物架 1。在置物架 1上，你看到：钥匙串 2。 | &lt;action&gt;<br>go to shelf 1<br>&lt;/action&gt; | 前往置物架 1 |
| 25 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to desk 2<br>&lt;/action&gt; | 前往书桌 2 |
| 26 | EN: You arrive at desk 2. On the desk 2, you see a bowl 1, a cellphone 3, a mug 2, a mug 1, and a pencil 2.<br>中：你到达书桌 2。在书桌 2上，你看到：碗 1、手机 3、马克杯 2、马克杯 1、铅笔 2。 | &lt;action&gt;<br>go to desk 2<br>&lt;/action&gt; | 前往书桌 2 |
| 27 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to shelf 2<br>&lt;/action&gt; | 前往置物架 2 |
| 28 | EN: You arrive at shelf 2. On the shelf 2, you see a alarmclock 1.<br>中：你到达置物架 2。在置物架 2上，你看到：闹钟 1。 | &lt;action&gt;<br>go to shelf 1<br>&lt;/action&gt; | 前往置物架 1 |
| 29 | EN: You arrive at shelf 1. On the shelf 1, you see a keychain 2.<br>中：你到达置物架 1。在置物架 1上，你看到：钥匙串 2。 | &lt;action&gt;<br>go to shelf 1<br>&lt;/action&gt; | 前往置物架 1 |
| 30 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;<br>go to desk 2<br>&lt;/action&gt; | 前往书桌 2 |

**环境结果 / Environment result:** episode_rewards=0.0；failure。末动作之后的环境观察未保存 / Final post-action observation not recorded.

## 4. unseen_mug — valid_unseen

`valid_unseen/look_at_obj_in_light-Mug-None-DeskLamp-308/trial_T20190908_201421_021646/game.tw-pddl`

该题四次采样 / All four samples：base **0/4** → step150 **1/4**。

base 反复查看杯子、使用台灯，却没有拿起杯子；step150 前往书桌、拿杯子、使用台灯，3 步成功。

Base repeatedly examines the mug and uses the lamp without picking up the mug; step150 goes to the desk, takes the mug, and uses the lamp in three steps.

### Base / 训练前 — 失败 / failure，30 步

**Task:** examine the mug with the desklamp.

**题目：**借助台灯查看马克杯。

`traj_uid: 2a803f48-1a67-41bd-864a-0521204c0ca7`

| 步 / Turn | 动作前观察 / Observation before action | 模型原始输出 / Model output | 动作中文释义 / Chinese action |
|---|---|---|---|
| 1 | EN: -= Welcome to TextWorld, ALFRED! =-<br><br>You are in the middle of a room. Looking quickly around you, you see a bed 1, a desk 2, a desk 1, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a garbagecan 1, a laundryhamper 1, a safe 1, a shelf 6, a shelf 5, a shelf 4, a shelf 3, a shelf 2, and a shelf 1.<br>中：欢迎来到 TextWorld，ALFRED！<br><br>你位于房间中央，快速环顾四周，看到：床 1、书桌 2、书桌 1、抽屉 6、抽屉 5、抽屉 4、抽屉 3、抽屉 2、抽屉 1、垃圾桶 1、洗衣篮 1、保险箱 1、置物架 6、置物架 5、置物架 4、置物架 3、置物架 2、置物架 1。 | &lt;action&gt;look&lt;/action&gt; | 查看周围 |
| 2 | EN: You are in the middle of a room. Looking quickly around you, you see nothing.<br>中：你位于房间中央，快速环顾四周，没有看到任何东西。 | &lt;action&gt;look&lt;/action&gt; | 查看周围 |
| 3 | EN: You are in the middle of a room. Looking quickly around you, you see nothing.<br>中：你位于房间中央，快速环顾四周，没有看到任何东西。 | &lt;action&gt;look&lt;/action&gt; | 查看周围 |
| 4 | EN: You are in the middle of a room. Looking quickly around you, you see nothing.<br>中：你位于房间中央，快速环顾四周，没有看到任何东西。 | &lt;action&gt;look&lt;/action&gt; | 查看周围 |
| 5 | EN: You are in the middle of a room. Looking quickly around you, you see nothing.<br>中：你位于房间中央，快速环顾四周，没有看到任何东西。 | &lt;action&gt;look&lt;/action&gt; | 查看周围 |
| 6 | EN: You are in the middle of a room. Looking quickly around you, you see nothing.<br>中：你位于房间中央，快速环顾四周，没有看到任何东西。 | &lt;action&gt;look&lt;/action&gt; | 查看周围 |
| 7 | EN: You are in the middle of a room. Looking quickly around you, you see nothing.<br>中：你位于房间中央，快速环顾四周，没有看到任何东西。 | &lt;action&gt;go to desk 1&lt;/action&gt; | 前往书桌 1 |
| 8 | EN: You arrive at desk 1. On the desk 1, you see a creditcard 3, a desklamp 1, a laptop 2, a mug 1, a pen 1, and a pencil 1.<br>中：你到达书桌 1。在书桌 1上，你看到：信用卡 3、台灯 1、笔记本电脑 2、马克杯 1、笔 1、铅笔 1。 | &lt;action&gt;examine desk 1&lt;/action&gt; | 查看书桌 1 |
| 9 | EN: On the desk 1, you see a creditcard 3, a desklamp 1, a laptop 2, a mug 1, a pen 1, and a pencil 1.<br>中：在书桌 1上，你看到：信用卡 3、台灯 1、笔记本电脑 2、马克杯 1、笔 1、铅笔 1。 | &lt;action&gt;examine mug 1&lt;/action&gt; | 查看马克杯 1 |
| 10 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine desklamp 1&lt;/action&gt; | 查看台灯 1 |
| 11 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine desk 1&lt;/action&gt; | 查看书桌 1 |
| 12 | EN: On the desk 1, you see a creditcard 3, a desklamp 1, a laptop 2, a mug 1, a pen 1, and a pencil 1.<br>中：在书桌 1上，你看到：信用卡 3、台灯 1、笔记本电脑 2、马克杯 1、笔 1、铅笔 1。 | &lt;action&gt;examine mug 1&lt;/action&gt; | 查看马克杯 1 |
| 13 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;use desklamp 1&lt;/action&gt; | 使用台灯 1 |
| 14 | EN: You turn on the desklamp 1.<br>中：你打开了台灯 1。 | &lt;action&gt;examine mug 1&lt;/action&gt; | 查看马克杯 1 |
| 15 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine mug 1&lt;/action&gt; | 查看马克杯 1 |
| 16 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;use desklamp 1&lt;/action&gt; | 使用台灯 1 |
| 17 | EN: You turn on the desklamp 1.<br>中：你打开了台灯 1。 | &lt;action&gt;examine mug 1&lt;/action&gt; | 查看马克杯 1 |
| 18 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine mug 1&lt;/action&gt; | 查看马克杯 1 |
| 19 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;use desklamp 1&lt;/action&gt; | 使用台灯 1 |
| 20 | EN: You turn on the desklamp 1.<br>中：你打开了台灯 1。 | &lt;action&gt;examine mug 1&lt;/action&gt; | 查看马克杯 1 |
| 21 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine mug 1&lt;/action&gt; | 查看马克杯 1 |
| 22 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;use desklamp 1&lt;/action&gt; | 使用台灯 1 |
| 23 | EN: You turn on the desklamp 1.<br>中：你打开了台灯 1。 | &lt;action&gt;examine mug 1&lt;/action&gt; | 查看马克杯 1 |
| 24 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine mug 1&lt;/action&gt; | 查看马克杯 1 |
| 25 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;use desklamp 1&lt;/action&gt; | 使用台灯 1 |
| 26 | EN: You turn on the desklamp 1.<br>中：你打开了台灯 1。 | &lt;action&gt;examine mug 1&lt;/action&gt; | 查看马克杯 1 |
| 27 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine mug 1&lt;/action&gt; | 查看马克杯 1 |
| 28 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;use desklamp 1&lt;/action&gt; | 使用台灯 1 |
| 29 | EN: You turn on the desklamp 1.<br>中：你打开了台灯 1。 | &lt;action&gt;examine mug 1&lt;/action&gt; | 查看马克杯 1 |
| 30 | EN: Nothing happens.<br>中：没有任何变化。 | &lt;action&gt;examine mug 1&lt;/action&gt; | 查看马克杯 1 |

**环境结果 / Environment result:** episode_rewards=0.0；failure。末动作之后的环境观察未保存 / Final post-action observation not recorded.

### Step150 / 训练后 — 成功 / success，3 步

**Task:** examine the mug with the desklamp.

**题目：**借助台灯查看马克杯。

`traj_uid: d3d178bd-6a21-4c43-9602-97f588204bfa`

| 步 / Turn | 动作前观察 / Observation before action | 模型原始输出 / Model output | 动作中文释义 / Chinese action |
|---|---|---|---|
| 1 | EN: -= Welcome to TextWorld, ALFRED! =-<br><br>You are in the middle of a room. Looking quickly around you, you see a bed 1, a desk 2, a desk 1, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a garbagecan 1, a laundryhamper 1, a safe 1, a shelf 6, a shelf 5, a shelf 4, a shelf 3, a shelf 2, and a shelf 1.<br>中：欢迎来到 TextWorld，ALFRED！<br><br>你位于房间中央，快速环顾四周，看到：床 1、书桌 2、书桌 1、抽屉 6、抽屉 5、抽屉 4、抽屉 3、抽屉 2、抽屉 1、垃圾桶 1、洗衣篮 1、保险箱 1、置物架 6、置物架 5、置物架 4、置物架 3、置物架 2、置物架 1。 | &lt;action&gt;<br>go to desk 1<br>&lt;/action&gt; | 前往书桌 1 |
| 2 | EN: You arrive at desk 1. On the desk 1, you see a creditcard 3, a desklamp 1, a laptop 2, a mug 1, a pen 1, and a pencil 1.<br>中：你到达书桌 1。在书桌 1上，你看到：信用卡 3、台灯 1、笔记本电脑 2、马克杯 1、笔 1、铅笔 1。 | &lt;action&gt;<br>take mug 1 from desk 1<br>&lt;/action&gt; | 从书桌 1拿起马克杯 1 |
| 3 | EN: You pick up the mug 1 from the desk 1.<br>中：你从书桌 1拿起马克杯 1。 | &lt;action&gt;<br>use desklamp 1<br>&lt;/action&gt; | 使用台灯 1 |

**环境结果 / Environment result:** episode_rewards=10.0；success。末动作之后的环境观察未保存 / Final post-action observation not recorded.
