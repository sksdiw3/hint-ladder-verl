from pathlib import Path
import hashlib
import json
import os

ROOT = Path(os.environ.get('PROBE_ROOT', '/probe'))
REPO = Path('/workspace/hintladder')
MODELS = {'base': '/models/base', 'step50': '/models/step50'}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def save_jsonl(path, rows):
    Path(path).write_text(''.join(json.dumps(r, ensure_ascii=False, allow_nan=False)+'\n' for r in rows))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_prompt(episode, state):
    history = episode['turns'][-2:]
    history_text = '\n'.join(
        f"[Observation {t['turn']}: '{t['observation']}', Action {t['turn']}: '{t['executed_action']}']"
        for t in history)
    return (ROOT/'prompt_template.txt').read_text().format(
        task_description=episode['task'], step_count=len(episode['turns']), history_length=len(history),
        action_history=history_text, current_step=len(episode['turns'])+1,
        current_observation=state['observation'],
        admissible_actions='\n '.join(f"'{a}'" for a in state['admissible_commands']))
