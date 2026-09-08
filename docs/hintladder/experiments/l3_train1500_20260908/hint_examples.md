# 12 条实际 L3 hint 样例

来自本次 1,500 条训练 bank，逐字保留生成结果。按固定训练列表顺序，每种任务类型取最早的两条；没有按成功率或 hint 文本质量挑选。

完整生成消息（system + user）、初始观察、初始动作空间、隐藏事实、已验证 walkthrough 见 [hint_examples.jsonl](hint_examples.jsonl)。其中只有 hint 进入 Teacher 前向；这些 oracle 输入不进入 Student rollout。

## 1. pick_clean_then_place_in_recep · 训练列表第 1 题

**任务：** clean some fork and put it in drawer.

**L3 hint（139 words）：**

Your supplied numbered goal object is fork 1, which currently sits on diningtable 1. Its initial states are that it is not hot, not clean, and not cool, so washing is required before storage. The destination instance is drawer 1.

Begin by walking over to the dining table, where the fork rests, and pick it up. Carrying it with you, head to the sink basin, the room's cleaning spot, and rinse the fork there until it registers as clean. Once cleaned, travel to drawer 1 and place the fork inside it to complete the task.

No heating or cooling is involved, since the fork's hot and cool states are irrelevant to the goal; only cleanliness matters. Keep the fork in your possession throughout rather than setting it down on intermediate surfaces, which avoids unnecessary extra movements around the kitchen.

Game: `json_2.1.1/train/pick_clean_then_place_in_recep-Fork-None-Drawer-11/trial_T20190907_145752_008234/game.tw-pddl`

## 2. pick_and_place_simple · 训练列表第 2 题

**任务：** put a cloth in drawer.

**L3 hint（133 words）：**

The numbered goal object is cloth 1, which begins on toilet 1 and must end inside drawer 2. Its supplied initial states are: hot is false, clean is false, and cool is false, so the cloth starts as an ordinary, untreated item and needs no heating, cooling, or washing. Begin by walking to the toilet, where the cloth rests, and pick it up so it is in your possession. Next, travel to drawer 2, since the task specifies that particular drawer rather than any other. Drawer 2 starts closed, so open it before placing anything inside. Finally, put the cloth into the open drawer, completing the goal. No cleaning or temperature change is needed at any point; the only requirements are retrieving the cloth from the toilet and depositing it in drawer 2.

Game: `json_2.1.1/train/pick_and_place_simple-Cloth-None-Drawer-409/trial_T20190912_061626_184198/game.tw-pddl`

## 3. pick_two_obj_and_place · 训练列表第 3 题

**任务：** put two spatula in drawer.

**L3 hint（123 words）：**

Your task is to place two spatulas inside drawer 10. The first goal object, spatula 1, rests on diningtable 1, while the second spatula can be found on countertop 1. Both utensils start out not hot, not clean, and not cool, so no heating, cooling, or washing is required before storing them.

Begin by walking to diningtable 1 and picking up spatula 1. Then travel to drawer 10, slide it open, and place the spatula inside. Next, head over to countertop 1, where the second spatula lies, and take it. Return to drawer 10, which should still be open, and set the second spatula down beside the first. Once both spatulas sit in drawer 10, the task is complete and you may finish.

Game: `json_2.1.1/train/pick_two_obj_and_place-Spatula-None-Drawer-16/trial_T20190906_235108_616160/game.tw-pddl`

## 4. pick_and_place_simple · 训练列表第 4 题

**任务：** put a cd in safe.

**L3 hint（126 words）：**

The task is to put cd 1 into safe 1. The cd begins inside drawer 5, and its supplied initial states are: not hot, not clean, and not cool, so no heating, cleaning, or cooling step is needed. Walk to drawer 5 and open it, then take cd 1 from drawer 5. With the disc in your possession, go to safe 1 and open it, since a closed safe cannot receive the object. Finally, move cd 1 to safe 1, which completes the goal of putting a cd in safe. Nothing else in the room, such as the bed, other drawers, dresser, garbagecan, laundryhamper, or sidetable, is required for this task. If any container blocks your way, simply open it before retrieving or depositing the cd.

Game: `json_2.1.1/train/pick_and_place_simple-CD-None-Safe-317/trial_T20190906_180452_867280/game.tw-pddl`

## 5. pick_heat_then_place_in_recep · 训练列表第 5 题

**任务：** put a hot mug in coffeemachine.

**L3 hint（101 words）：**

Your task is to put a hot mug in coffeemachine 1. The goal object is mug 1, which starts on countertop 1 in a cold and dirty state, meaning it is neither hot, clean, nor cool. Begin by walking to countertop 1 and taking mug 1 from it. Next, carry the mug to microwave 1 and heat mug 1 with microwave 1, which transforms it into a hot mug. With the mug now heated, travel to coffeemachine 1 and place mug 1 inside it. This satisfies the requirement of a hot mug resting in the coffeemachine, and the task is complete.

Game: `json_2.1.1/train/pick_heat_then_place_in_recep-Mug-None-CoffeeMachine-30/trial_T20190907_220045_510017/game.tw-pddl`

## 6. pick_clean_then_place_in_recep · 训练列表第 7 题

**任务：** clean some plate and put it in microwave.

**L3 hint（117 words）：**

Your goal is to clean some plate and put it in microwave. The specific object is plate 1, currently located on shelf 2, and it starts out not clean, not hot, and not cool. First, make your way to shelf 2 and pick up plate 1. Next, travel to sinkbasin 1 and clean plate 1 with sinkbasin 1, which washes away the dirt so the plate counts as clean. Finally, head over to microwave 1, open it, and move plate 1 to microwave 1. Once the cleaned plate sits inside the microwave, the task is complete. No heating or cooling is required, only washing and placement, so follow the shelf, sink, and microwave sequence in that order.

Game: `json_2.1.1/train/pick_clean_then_place_in_recep-Plate-None-Microwave-7/trial_T20190907_170142_415879/game.tw-pddl`

## 7. pick_two_obj_and_place · 训练列表第 9 题

**任务：** put two alarmclock in shelf.

**L3 hint（137 words）：**

Your task is to put two alarm clocks on the shelf. The numbered goal object is alarmclock 2, which begins on desk 1, and the destination is shelf 1. Neither clock is hot, clean, or cool at the start; no special treatment is needed, only carrying and placing.

Begin by walking to the desk and picking up alarmclock 2. Carry it to the shelf and set it there, confirming it stays in place. Then return to the same desk, where alarmclock 1 also rests, and pick that clock up as well. Bring it back to the shelf and place it alongside the first one. Once both clocks rest on the shelf, the goal is satisfied. There is no need to open anything or use any heat, cleaning, or cooling device anywhere in the room during this task.

Game: `json_2.1.1/train/pick_two_obj_and_place-AlarmClock-None-Shelf-316/trial_T20190909_010429_853588/game.tw-pddl`

## 8. pick_cool_then_place_in_recep · 训练列表第 13 题

**任务：** put a cool bowl in cabinet.

**L3 hint（128 words）：**

Your goal is to put a cool bowl in a cabinet. The required object is bowl 1, which currently rests on diningtable 1. Its supplied initial states are: not hot, not clean, and not cool, so it must be chilled before storage. The designated destination is cabinet 18.

Begin by walking to diningtable 1 and taking bowl 1 from its surface. Then travel to fridge 1 and use the fridge to cool bowl 1, which changes its state to cool. Once chilled, carry bowl 1 to cabinet 18, open that cabinet, and place the bowl inside. This satisfies the task, since a cool bowl has been put in the specified cabinet. Work through these steps in order, moving between receptacles as described, and the objective will be complete.

Game: `json_2.1.1/train/pick_cool_then_place_in_recep-Bowl-None-Cabinet-19/trial_T20190908_043325_612655/game.tw-pddl`

## 9. pick_cool_then_place_in_recep · 训练列表第 17 题

**任务：** put a cool pan in diningtable.

**L3 hint（130 words）：**

Your task is to put pan 1 in diningtable 1. Pan 1 rests on stoveburner 4 and starts out not hot, not clean, and not cool, so it must be cooled before placement. Walk to stoveburner 4 and pick up the pan that sits there. Then travel to fridge 1 and use it to chill the pan, which changes its state to cool. Once the pan is cool, carry it over to diningtable 1 and set it down there, completing the goal. No cleaning or heating is required, since the goal only asks for a cool pan on the dining table, and the pan begins coolable regardless of its current temperature or cleanliness. Follow this order: retrieve from the stoveburner, cool at the fridge, then deposit at the dining table.

Game: `json_2.1.1/train/pick_cool_then_place_in_recep-Pan-None-DiningTable-11/trial_T20190908_204347_530034/game.tw-pddl`

## 10. pick_heat_then_place_in_recep · 训练列表第 21 题

**任务：** put a hot potato in diningtable.

**L3 hint（130 words）：**

Your task is to place a hot potato on the dining table, and the specific goal object is potato 3, currently resting on countertop 2. Its initial state is unheated: it is not hot, not clean, and not cool. The destination receptacle is diningtable 1.

Begin by walking to countertop 2 and picking up potato 3 from its surface. Since the potato must be hot, carry it to the microwave and heat it there until it becomes hot. Once heated, travel to diningtable 1 while holding the potato. Finally, set the potato down onto the table, completing the goal. The heating step is essential, because placing a cold or room-temperature potato on the table will not satisfy the requirement; only a hot potato placed on diningtable 1 counts as success.

Game: `json_2.1.1/train/pick_heat_then_place_in_recep-Potato-None-DiningTable-16/trial_T20190908_015113_664393/game.tw-pddl`

## 11. look_at_obj_in_light · 训练列表第 39 题

**任务：** examine the pen with the desklamp.

**L3 hint（135 words）：**

The numbered goal object is pen 4, which begins resting on dresser 1. No destination instance applies to this task; nothing must be carried elsewhere or placed into another receptacle. The pen's supplied initial states are that it is not hot, not clean, and not cool, meaning no heating, cleaning, or cooling step is required before examination.

Begin by walking to dresser 1, since that is where the pen lies and where the lamp is situated. Once there, turn the desklamp on so it illuminates the area. Then pick up pen 4 from dresser 1, holding it in the lamplight. With the lamp shining and the pen in hand, the examination completes the task. The key sequence is simply: reach the dresser, activate the lamp, and take the pen, letting the light reveal its details.

Game: `json_2.1.1/train/look_at_obj_in_light-Pen-None-DeskLamp-305/trial_T20190907_115838_075745/game.tw-pddl`

## 12. look_at_obj_in_light · 训练列表第 41 题

**任务：** look at pencil under the desklamp.

**L3 hint（130 words）：**

The goal object is pencil 1, and the task is to look at it under the desklamp. Pencil 1 currently rests on shelf 1, and no destination receptacle is supplied, so you only need to view it by lamplight rather than carry it somewhere. Its supplied initial states are hot false, clean false, and cool false, meaning the pencil is ordinary and needs no heating, cleaning, or cooling beforehand. Start by walking to shelf 1 and taking pencil 1 into your inventory. Then move toward shelf 2, where the desklamp sits, and use the desklamp to switch on its light. With the pencil held and the lamp illuminated, examine the pencil under the light to finish. If shelf 2 lacks the lamp, check the nearby desks for desklamp 1 instead.

Game: `json_2.1.1/train/look_at_obj_in_light-Pencil-None-DeskLamp-320/trial_T20190908_143815_342227/game.tw-pddl`
