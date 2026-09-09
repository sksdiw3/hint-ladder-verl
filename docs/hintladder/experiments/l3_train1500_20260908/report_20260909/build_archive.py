"""CPU-only archival export. Requires the original local runs/ artifacts.

Run from any directory: python3 /path/to/this/build_archive.py
Does not launch evaluation, training, API requests, or change source run files.
"""
import collections
import hashlib
import html
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
RUN = ROOT / "runs/l3_train1500_20260908"
RESUME = RUN / "resume100_20260909_1041"
ATTEMPTS = {"original": RUN, "resume100": RESUME}
SOURCES = {}
EXPORTS = []


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_source(path):
    data = path.read_bytes()
    SOURCES[str(path.relative_to(ROOT))] = {"bytes": len(data), "sha256": sha(data)}
    return data


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sanitize(text):
    # Never print a match. Preserve numerical metrics and traceback content.
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = text.replace("\r", "\n")
    patterns = [r"\bsk-[A-Za-z0-9_-]{16,}", r"\bwandb_v1_[A-Za-z0-9_-]+",
                r"\bgh[pousr]_[A-Za-z0-9_]{20,}", r"\bgithub_pat_[A-Za-z0-9_]+",
                r"(?i)(?:Bearer\s+)[A-Za-z0-9._~+/=-]{16,}"]
    count = 0
    for pattern in patterns:
        text, n = re.subn(pattern, "[REDACTED_CREDENTIAL]", text)
        count += n
    return text, count


def copy_log(source, name, clean=False):
    raw = read_source(source)
    data, redactions = sanitize(raw.decode("utf-8", errors="replace")) if clean else (raw.decode("utf-8"), 0)
    target = OUT / "logs" / name
    target.write_text(data)
    EXPORTS.append({"source": str(source.relative_to(ROOT)), "output": str(target.relative_to(OUT)),
                    "transformation": "ANSI stripped; CR replaced by LF; credential patterns redacted" if clean else "none; exact UTF-8 source",
                    "credential_redactions": redactions})
    if not clean:
        assert target.read_bytes() == raw


def load_episodes(path):
    episodes = collections.defaultdict(list)
    for line_no, line in enumerate(read_source(path).decode().splitlines(), 1):
        row = json.loads(line)
        episodes[row["traj_uid"]].append((line_no, row))
    games = collections.defaultdict(list)
    for uid, turns in episodes.items():
        turns.sort(key=lambda x: x[1]["turn_step"])
        first = turns[0][1]
        assert [r["turn_step"] for _, r in turns] == list(range(len(turns)))
        assert all(r["gamefile"] == first["gamefile"] and r["episode_rewards"] == first["episode_rewards"] for _, r in turns)
        assert first["episode_rewards"] in (0, 10)
        assert len(turns) == first["episode_lengths"]
        games[first["gamefile"]].append({"traj_uid": uid, "success": first["episode_rewards"] == 10, "turns": turns})
    assert len(games) == 128 and all(len(v) == 4 for v in games.values())
    return games


VOCAB = dict(zip(
    "cabinet coffeemachine countertop diningtable drawer fridge garbagecan microwave sinkbasin stoveburner toaster bed desk shelf sidetable laundryhamper safe apple fork potato spoon bowl bread egg knife ladle mug pan peppershaker plate saltshaker soapbottle cup butterknife houseplant alarmclock pencil cd cellphone desklamp keychain pen creditcard laptop".split(),
    "柜子 咖啡机 操作台 餐桌 抽屉 冰箱 垃圾桶 微波炉 水槽 灶眼 烤面包机 床 书桌 置物架 边桌 洗衣篮 保险箱 苹果 叉子 土豆 勺子 碗 面包 鸡蛋 刀 汤勺 马克杯 平底锅 胡椒瓶 盘子 盐瓶 洗手液瓶 杯子 黄油刀 盆栽 闹钟 铅笔 光盘 手机 台灯 钥匙串 笔 信用卡 笔记本电脑".split()))


def obj(text):
    return re.sub(r"[a-z]+", lambda m: VOCAB[m[0]], text)


def obs_zh(text):
    if text.startswith("-= Welcome to TextWorld, ALFRED! =-\n\n"):
        return "欢迎来到 TextWorld，ALFRED！\n\n" + obs_zh(text.split("\n\n", 1)[1])
    if text == "Nothing happens.":
        return "没有任何变化。"
    room = "You are in the middle of a room. Looking quickly around you, you see "
    if text.startswith(room):
        rest = text[len(room):].rstrip(".")
        return "你位于房间中央，快速环顾四周，" + ("没有看到任何东西。" if rest == "nothing" else "看到：" + items(rest) + "。")
    match = re.fullmatch(r"You arrive at (.+?)\. (On the .+)", text)
    if match:
        return "你到达" + obj(match[1]) + "。" + obs_zh(match[2])
    match = re.fullmatch(r"On the (.+?), you see (.+)\.", text)
    if match:
        return "在" + obj(match[1]) + "上，你看到：" + items(match[2]) + "。"
    for pattern, render in [
        (r"You are facing the (.+)\. Next to it, you see nothing\.", lambda m: "你正面对" + obj(m[1]) + "，旁边没有看到任何东西。"),
        (r"You pick up the (.+) from the (.+)\.", lambda m: "你从" + obj(m[2]) + "拿起" + obj(m[1]) + "。"),
        (r"You clean the (.+) using the (.+)\.", lambda m: "你用" + obj(m[2]) + "清洗了" + obj(m[1]) + "。"),
        (r"You move the (.+) to the (.+)\.", lambda m: "你把" + obj(m[1]) + "放到" + obj(m[2]) + "。"),
        (r"You turn on the (.+)\.", lambda m: "你打开了" + obj(m[1]) + "。")]:
        match = re.fullmatch(pattern, text)
        if match:
            return render(match)
    raise ValueError("Untranslated observation template")


def items(text):
    return "、".join(obj(re.sub(r"^(?:and )?a ", "", t.strip())) for t in text.split(","))


def action_zh(text):
    if text == "look":
        return "查看周围"
    for pattern, render in [
        (r"go to (.+)", lambda m: "前往" + obj(m[1])),
        (r"take (.+) from (.+)", lambda m: "从" + obj(m[2]) + "拿起" + obj(m[1])),
        (r"move (.+) to (.+)", lambda m: "把" + obj(m[1]) + "放到" + obj(m[2])),
        (r"clean (.+) with (.+)", lambda m: "用" + obj(m[2]) + "清洗" + obj(m[1])),
        (r"examine (.+) with (.+)", lambda m: "借助" + obj(m[2]) + "查看" + obj(m[1])),
        (r"examine (.+)", lambda m: "查看" + obj(m[1])),
        (r"use (.+)", lambda m: "使用" + obj(m[1]))]:
        match = re.fullmatch(pattern, text)
        if match:
            return render(match)
    raise ValueError("Untranslated action template")


def cell(text):
    return html.escape(text).replace("|", "&#124;").replace("\n", "<br>")


def main():
    (OUT / "logs").mkdir(exist_ok=True)
    for attempt, run in ATTEMPTS.items():
        copy_log(run / "train/metrics.jsonl", attempt + "_metrics.jsonl")
    copy_log(RUN / "training_live.log", "original_trainer_stdout.log", True)
    copy_log(RUN / "runtime_tmp/ray_l3train1500/session_2026-09-08_22-54-11_381787_105/logs/worker-ac9c5406e55317b800526317089bfc02196d7835572a6c7e39b144ef-01000000-27003.err", "original_first_failed_worker.log", True)
    ray_events = []
    for name in ["raylet.out", "gcs_server.out"]:
        source = RUN / "runtime_tmp/ray_l3train1500/session_2026-09-08_22-54-11_381787_105/logs" / name
        for line_no, line in enumerate(read_source(source).decode(errors="replace").splitlines(), 1):
            if "ac9c5406e55317b800526317089bfc02196d7835572a6c7e39b144ef" in line and any(k in line.lower() for k in ["failed", "dead", "exit", "disconnect"]):
                cleaned, _ = sanitize(line)
                ray_events.append({"source": str(source.relative_to(ROOT)), "source_line": line_no, "text": cleaned})
    write_json(OUT / "logs/original_ray_failure_events.json", ray_events)
    copy_log(RESUME / "training.log", "resume100_training.log", True)
    for name in ["status.json", "effective_config_diff.json", "restart_verified.json"]:
        copy_log(RESUME / name, "resume100_" + name)
    summaries, panels = [], {}
    for attempt, steps in [("original", [0, 25, 50, 75, 100]), ("resume100", [125, 150])]:
        metrics = {r["step"]: r for r in map(json.loads, (ATTEMPTS[attempt] / "train/metrics.jsonl").read_text().splitlines())}
        for step in steps:
            for split in ["valid_seen", "valid_unseen"]:
                source = ATTEMPTS[attempt] / f"train/validation/{split}/{step}.jsonl"
                games = load_episodes(source)
                wins = sum(e["success"] for es in games.values() for e in es)
                rate = wins / 512
                assert rate == metrics[step][f"val/{split}/success_rate"]
                families = collections.defaultdict(lambda: [0, 0])
                for game, episodes in games.items():
                    family = game.split("/")[-3].split("-")[0]
                    families[family][0] += sum(e["success"] for e in episodes)
                    families[family][1] += len(episodes)
                summaries.append({"attempt": attempt, "checkpoint_step": step, "split": split,
                                  "tasks": len(games), "episodes": 512, "successes": wins, "success_rate": rate,
                                  "source": str(source.relative_to(ROOT)), "source_sha256": SOURCES[str(source.relative_to(ROOT))]["sha256"],
                                  "task_results": [{"gamefile": g, "successes": sum(e["success"] for e in es), "samples": len(es)} for g, es in sorted(games.items())],
                                  "families": {f: {"successes": w, "episodes": n, "success_rate": w / n} for f, (w, n) in sorted(families.items())}})
                if step in [0, 150]:
                    panels[split, step] = games
    (OUT / "validation_summary.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in summaries))
    specs = [
        ("seen_ladle", "valid_seen", "pick_clean_then_place_in_recep-Ladle-None-DiningTable-4", True, False, "清洗一把汤勺，并将它放到餐桌上。", "base 完成清洗和放置；step150 拿到汤勺并到达水槽后离开，随后反复移动。", "Base cleans and places the ladle; step150 leaves the sink after collecting it and then repeatedly moves."),
        ("seen_bowl", "valid_seen", "look_at_obj_in_light-Bowl-None-DeskLamp-316", False, True, "借助台灯查看碗。", "base 困在边桌附近；step150 虽然多次往返，最终在台灯开启后拿起碗，环境判成功。", "Base stays around the side table; step150 makes repeated trips but eventually picks up the bowl with the lamp on and succeeds."),
        ("unseen_pencil", "valid_unseen", "pick_and_place_simple-Pencil-None-Shelf-308", True, False, "把一支铅笔放到置物架上。", "base 完成拿取和放置；step150 拿到铅笔后仍只移动，没有执行放置。", "Base picks up and places the pencil; step150 picks it up but keeps moving without placing it."),
        ("unseen_mug", "valid_unseen", "look_at_obj_in_light-Mug-None-DeskLamp-308", False, True, "借助台灯查看马克杯。", "base 反复查看杯子、使用台灯，却没有拿起杯子；step150 前往书桌、拿杯子、使用台灯，3 步成功。", "Base repeatedly examines the mug and uses the lamp without picking up the mug; step150 goes to the desk, takes the mug, and uses the lamp in three steps.")]
    md = ["# Base 与 step150：同题完整轨迹 / Matched-task trajectories", "",
          "四组验证任务、八条 episode；所有已记录的决策步均展示，重复动作不省略。每一步为动作前观察及模型输出；中文是事后翻译，模型实际看到、输出的都是英文。", "",
          "Four validation games, eight complete recorded decision sequences. Chinese text is a post-hoc translation, not model reasoning or model input. Repeated actions are retained.", "",
          "按完整 `gamefile` 配对。人为选择两组退步、两组进步来解释行为；不是随机抽样，不能用这 8 条估计整体成功率。指定题型和所需成败组合后，按 gamefile、traj_uid 字典序取首条符合的轨迹。每题实际都有 4 次采样，下面同时列出该题全部 4 次的成功数。跨 checkpoint 的随机采样不是同一次随机抽样。", "",
          "Pairs match exact gamefiles, not trajectory IDs or random draws. These outcome-selected examples illustrate behavior, not population performance. Within each named task/outcome stratum, selection uses lexicographic gamefile and trajectory ID order; all four-sample results are disclosed.", "",
          "评测无 hint，temperature=0.4，上限30步。环境 `won` 判成功，导出 `episode_rewards=10` 表示成功、0 表示失败。look 类任务的实际成功条件涉及持有目标物体及灯开启，不能把自然语言 examine 等同于必须输出 examine 命令。", "",
          "Evaluation uses no hints, temperature 0.4, and at most 30 actions. Success comes from the environment, not our translation. The terminal post-action observation is absent from the source dump; no terminal message is invented here.", "",
          "[完整原始 prompt、逐步动作空间、原始输出与来源行号 / Raw prompts, admissible actions, outputs and provenance](trajectories.jsonl) · [总体实验报告](REPORT.md)", "",
          "JSONL 每行是一条 episode，`turns[].raw` 保留原始日志记录的全部字段；不是 token ID 文件。表中的 HTML 换行用于展示，原始换行保留在 JSONL。输入 prompt 末尾的空 `<think>…</think>` 是聊天模板前缀；不应与模型 response 里违规生成的 thinking 标签混淆。", ""]
    exports = []
    for index, (pair_id, split, family, before_ok, after_ok, task_zh, analysis_zh, analysis_en) in enumerate(specs, 1):
        base, post = panels[split, 0], panels[split, 150]
        assert set(base) == set(post)
        game = sorted(g for g in base if g.split("/")[-3] == family and any(e["success"] == before_ok for e in base[g]) and any(e["success"] == after_ok for e in post[g]))[0]
        before_wins = sum(e["success"] for e in base[game])
        after_wins = sum(e["success"] for e in post[game])
        md += [f"## {index}. {pair_id} — {split}", "", f"`{game.split('json_2.1.1/')[1]}`", "",
               f"该题四次采样 / All four samples：base **{before_wins}/4** → step150 **{after_wins}/4**。", "", analysis_zh, "", analysis_en, ""]
        for step, desired in [(0, before_ok), (150, after_ok)]:
            e = sorted((e for e in panels[split, step][game] if e["success"] == desired), key=lambda e: e["traj_uid"])[0]
            attempt = "original" if step == 0 else "resume100"
            source = ATTEMPTS[attempt] / f"train/validation/{split}/{step}.jsonl"
            task_en = re.search(r"Your task is to: (.*?)\n", e["turns"][0][1]["input"])[1]
            record = {"schema": "hintladder_bilingual_matched_eval_v1", "pair_id": pair_id, "dataset_role": "validation", "split": split,
                      "attempt": attempt, "checkpoint_step": step, "policy": "Qwen3-4B base" if step == 0 else "L3 SDL student step150",
                      "gamefile": game, "traj_uid": e["traj_uid"], "task_en": task_en, "task_zh": task_zh,
                      "student_hint": None, "success": e["success"], "num_turns": len(e["turns"]),
                      "all_four_sample_successes": before_wins if step == 0 else after_wins,
                      "source_file": str(source.relative_to(ROOT)), "source_sha256": SOURCES[str(source.relative_to(ROOT))]["sha256"], "turns": []}
            md += [f"### {'Base / 训练前' if step == 0 else 'Step150 / 训练后'} — {'成功 / success' if desired else '失败 / failure'}，{len(e['turns'])} 步", "",
                   f"**Task:** {task_en}\n\n**题目：**{task_zh}", "", f"`traj_uid: {e['traj_uid']}`", "",
                   "| 步 / Turn | 动作前观察 / Observation before action | 模型原始输出 / Model output | 动作中文释义 / Chinese action |", "|---|---|---|---|"]
            for line_no, raw in e["turns"]:
                obs = re.search(r"(?:Your|your) current observation is: (.*?)\n(?:Your task is to:|Your admissible actions)", raw["input"], re.S)[1].strip()
                translated_obs, translated_action = obs_zh(obs), action_zh(raw["executed_action"])
                record["turns"].append({"source_line": line_no, "observation_en": obs, "observation_zh": translated_obs,
                                        "executed_action_zh": translated_action, "raw": raw})
                md.append(f"| {raw['turn_step'] + 1} | EN: {cell(obs)}<br>中：{cell(translated_obs)} | {cell(raw['output'])} | {cell(translated_action)} |")
            md += ["", f"**环境结果 / Environment result:** episode_rewards={e['turns'][0][1]['episode_rewards']}；{'success' if desired else 'failure'}。末动作之后的环境观察未保存 / Final post-action observation not recorded.", ""]
            exports.append(record)
    (OUT / "trajectories_zh_en.md").write_text("\n".join(md))
    (OUT / "trajectories.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in exports))
    manifest = {"schema": "hintladder_experiment_archive_v1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_code_head_at_export": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "attempts": {"original": {"completed_steps": [1, 116]}, "resume100": {"restored_step": 100, "completed_steps": [101, 151]}},
                "raw_validation_files_checked": len(summaries), "validation_episodes_checked": 512 * len(summaries),
                "exported_pairs": len(specs), "exported_episodes": len(exports), "exported_turns": sum(r["num_turns"] for r in exports),
                "selection": "Four named task/outcome strata; lexicographic gamefile then traj_uid among matching outcomes; not representative sampling.",
                "log_exports": EXPORTS, "sources": SOURCES,
                "outputs": {str(p.relative_to(OUT)): {"bytes": p.stat().st_size, "sha256": sha(p.read_bytes())} for p in sorted(OUT.rglob("*")) if p.is_file() and p.name != "manifest.json" and "__pycache__" not in p.parts}}
    write_json(OUT / "manifest.json", manifest)
    print(json.dumps({k: manifest[k] for k in ["raw_validation_files_checked", "validation_episodes_checked", "exported_pairs", "exported_episodes", "exported_turns"]}))


if __name__ == "__main__":
    main()
