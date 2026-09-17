"""Audit-only, aligned public-state hint generation; no Oracle or old hint input."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
import hashlib
import importlib.util
import json
import time
from common import ROOT, REPO, write_json


class HintProvider:
    def __init__(self, out):
        self.out = out / 'hint_requests'
        self.out.mkdir(exist_ok=True)
        self.systems = {level: (ROOT/f'{level}_prompt.txt').read_text().strip()
                        for level in ['l1', 'l2', 'l3']}
        spec = importlib.util.spec_from_file_location('configured_hint_api', REPO/'hintladder/api.py')
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        generator = json.loads((ROOT/'auth_manifest.json').read_text())['config']['stage.generator']
        config = {key: generator[key] for key in ['base_url', 'api_key_file']}
        credential = Path(config['api_key_file'])
        if not credential.is_absolute():
            config['api_key_file'] = str(REPO/credential)
        config.update(model='glm-5.3-flash', timeout=120)
        self.client = api.ModelClient(config)
        self.pool = ThreadPoolExecutor(max_workers=16)

    def generate(self, record):
        level = record['arm'].removeprefix('base_')
        payload = dict(model='glm-5.3-flash', messages=[
            dict(role='system', content=self.systems[level]),
            dict(role='user', content=json.dumps(record['hint_public_input'], ensure_ascii=False))],
            temperature=0.7, seed=record['generation_seed'], max_tokens=1536,
            thinking={'type': 'enabled'}, reasoning_effort='low')
        attempts = []
        started = time.monotonic()
        stem = record['row_id'].replace(':', '_')
        for attempt in range(1, 5):
            current = dict(payload, seed=payload['seed']+1000*(attempt-1),
                           max_tokens=1536 if attempt == 1 else 3072)
            write_json(self.out/f'{stem}_attempt{attempt}.request.json', current)
            try:
                response = self.client.request('/chat/completions', current)
                choice = response['choices'][0]
                hint = choice['message'].get('content')
                item = dict(attempt=attempt, returned_model=response.get('model'),
                    response_id=response.get('id'), usage=response.get('usage'),
                    hint=hint, finish_reason=choice.get('finish_reason'))
                attempts.append(item)
                write_json(self.out/f'{stem}_attempt{attempt}.response.json', item)
                if item['finish_reason'] == 'stop' and isinstance(hint, str) and hint.strip():
                    return dict(hint=hint, level=level.upper(), oracle_supplied=False,
                        returned_model=item['returned_model'], usage=item['usage'],
                        attempts=attempts, elapsed_seconds=time.monotonic()-started,
                        request_sha256=hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest())
            except (HTTPError, URLError, TimeoutError) as error:
                item = dict(attempt=attempt, error_type=type(error).__name__,
                            http_status=getattr(error, 'code', None))
                attempts.append(item)
                write_json(self.out/f'{stem}_attempt{attempt}.error.json', item)
            if attempt < 4:
                time.sleep(attempt)
        write_json(self.out/f'{stem}.failed.json', dict(attempts=attempts))
        raise RuntimeError(f'No completed hint after four attempts: {record["row_id"]}')

    def batch(self, records):
        futures = [(r['row_id'], self.pool.submit(self.generate, r))
                   for r in records if r['arm'] != 'base']
        return {key: future.result() for key, future in futures}

    def close(self):
        self.pool.shutdown(wait=True)
