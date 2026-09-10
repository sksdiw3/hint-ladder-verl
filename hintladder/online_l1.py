"""Public-state L1 hints for teacher scoring of on-policy Student turns."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError

from .api import ModelClient
from .keys import normalize_gamefile
from .teacher_prompt import OPEN, CLOSE


def public_state(prompt):
    """Parse only the fixed public prompt, never the sampled response or game file."""
    if OPEN in prompt or CLOSE in prompt:
        raise ValueError("Online hint input already contains a private note")
    task = re.search(r"Your task is to: (.*?) Prior to this step,", prompt, re.S)
    history = re.search(r"corresponding actions you took: (.*?) You are now at step (\d+) and your current observation is: ", prompt, re.S)
    if task is None or history is None:
        raise ValueError("Online L1 requires the matched reasoning prompt")
    observation = prompt[history.end():].split(" Your admissible actions of the current situation are: [", 1)
    if len(observation) != 2:
        raise ValueError("Missing current observation boundary")
    actions = re.findall(r", Action \d+: '([^']*)'\]", history.group(1))
    if len(actions) != min(2, int(history.group(2)) - 1):
        raise ValueError("Online L1 history must contain the last two executed actions")
    return dict(task=task.group(1), current_observation=observation[0], action_history=actions)


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


class OnlineL1Provider:
    def __init__(self, config, output):
        self.config = dict(config)
        if self.config['model'] != 'glm-5.3-flash':
            raise ValueError("This online L1 experiment requires glm-5.3-flash")
        self.system = Path(self.config['prompt_path']).read_text()
        self.root = Path(output) / 'online_hints'
        self.root.mkdir(parents=True, exist_ok=True)
        self.step = 0
        self.records = {}
        self.metrics = {}

    def level_for(self, game):
        normalize_gamefile(game)
        return 'L1'

    def get(self, game):
        raise ValueError("Online L1 requires a current prompt, not a game-level lookup")

    def validate_coverage(self, games, **kwargs):
        for game in games:
            if '/train/' not in normalize_gamefile(game):
                raise ValueError("Online training hints require train split games")

    def _request(self, prompt):
        public = public_state(prompt)
        public_hash = hashlib.sha256(json.dumps(public, sort_keys=True).encode()).hexdigest()
        payload = dict(model=self.config['model'], messages=[dict(role='system', content=self.system),
            dict(role='user', content=json.dumps(public, ensure_ascii=False))],
            temperature=self.config.get('temperature', .7), max_tokens=self.config.get('max_tokens', 4096),
            reasoning_effort='low', chat_template_kwargs={'enable_thinking': False},
            seed=(int(public_hash[:8], 16) + self.step + int(self.config.get('seed', 42))) % (2**31))
        key = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        directory = self.root / f'step_{self.step:06d}'
        directory.mkdir(exist_ok=True)
        path = directory / (key + '.json')
        if path.exists():
            record = json.loads(path.read_text())
            if record['request_sha256'] != key or record['returned_model'] != self.config['model']:
                raise ValueError("Invalid online hint cache")
            return record
        atomic_json(directory / (key + '.request.json'), payload)
        errors = []
        started = time.monotonic()
        for attempt in range(1, int(self.config.get('retries', 12)) + 1):
            try:
                response = ModelClient(self.config).request('/chat/completions', payload)
                if response.get('model') != self.config['model']:
                    raise RuntimeError("Hint endpoint returned a different model")
                choice = response['choices'][0]
                hint = choice['message'].get('content')
                if choice.get('finish_reason') != 'stop' or not isinstance(hint, str) or not hint.strip():
                    raise ValueError('incomplete_or_empty_hint')
                if OPEN in hint or CLOSE in hint:
                    raise ValueError('nested_private_note')
                record = dict(hint=hint, requested_model=self.config['model'], returned_model=response['model'],
                    finish_reason=choice['finish_reason'], usage=response.get('usage') or {},
                    request_sha256=key, oracle_supplied=False, level='L1', training_step=self.step,
                    elapsed_seconds=time.monotonic()-started, attempt=attempt)
                atomic_json(path, record)
                return record
            except (HTTPError, URLError, TimeoutError, ValueError) as error:
                errors.append(dict(attempt=attempt, type=type(error).__name__, status=getattr(error, 'code', None)))
                atomic_json(directory / (key + '.errors.json'), errors)
                if isinstance(error, HTTPError) and error.code not in (429, 500, 502, 503, 504):
                    break
                if attempt < int(self.config.get('retries', 12)):
                    time.sleep(min(60, 2**min(attempt, 6)))
        raise RuntimeError(f'Online hint request exhausted retries: step={self.step}, request={key}')

    def prepare_prompts(self, prompts):
        # Batch balancing may repeat a row. Identical public states share a hint
        # within this update; each later update has a distinct request seed.
        unique = {}
        for prompt in prompts:
            key = json.dumps(public_state(prompt), sort_keys=True)
            unique.setdefault(key, prompt)
        started = time.monotonic()
        self.records = {}
        records_by_state = {}
        with ThreadPoolExecutor(max_workers=int(self.config.get('concurrency', 64))) as pool:
            futures = {pool.submit(self._request, prompt): key for key, prompt in unique.items()}
            for future in as_completed(futures):
                records_by_state[futures[future]] = future.result()
                atomic_json(self.root / 'progress.json', dict(step=self.step, requested=len(unique),
                    completed=len(records_by_state), elapsed_seconds=time.monotonic()-started))
        self.records = {p: records_by_state[json.dumps(public_state(p), sort_keys=True)] for p in prompts}
        self.metrics = {'hint_ladder/hint_requests': len(unique), 'hint_ladder/hint_seconds': time.monotonic()-started,
            'hint_ladder/hint_words_mean': sum(len(r['hint'].split()) for r in records_by_state.values()) / len(unique)}

    def get_for_prompt(self, game, prompt):
        self.level_for(game)
        return self.records[prompt]['hint']


def make_provider(config, output):
    if config.get('online', {}).get('enable', False):
        return OnlineL1Provider(config['online'], output)
    from .hint_bank import HintProvider
    return HintProvider(config['bank_dir'], level=config['level'], level_map_path=config['level_map_path'])
