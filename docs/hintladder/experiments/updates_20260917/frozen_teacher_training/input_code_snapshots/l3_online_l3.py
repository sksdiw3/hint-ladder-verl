"""Online, private Teacher L3 notes grounded in the game's walkthrough."""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing
import time

from .keys import normalize_gamefile
from .online_l1 import FAILED_LEVEL, OnlineL1Provider, public_state
from .walkthrough_oracle import align_walkthrough


class OracleUnavailable(ValueError):
    def __init__(self, oracle):
        self.oracle = oracle


class OnlineL3Provider(OnlineL1Provider):
    requires_state_context = True

    def __init__(self, config, output):
        super().__init__(config, output)
        self.oracle_pool = ProcessPoolExecutor(max_workers=int(config.get('oracle_workers', 8)),
                                               mp_context=multiprocessing.get_context('spawn'))

    def close(self):
        super().close()
        self.oracle_pool.shutdown(wait=True, cancel_futures=True)

    def level_for(self, game):
        normalize_gamefile(game)
        return 'L3'

    def _key(self, encoded):
        return encoded

    def _inputs(self, texts, contexts):
        if len(texts) != len(contexts):
            raise ValueError('L3 state context count mismatch')
        result = []
        for text, context in zip(texts, contexts):
            context = json.loads(context) if isinstance(context, str) else context
            game = normalize_gamefile(context['gamefile'])
            result.append(json.dumps(dict(prompt=text, gamefile=game,
                                           action_history=list(context['action_history'])), sort_keys=True))
        return result

    def prefetch_states(self, texts, contexts):
        selected = [(t, c) for t, c in zip(texts, contexts)
                    if (json.loads(c) if isinstance(c, str) else c).get('active', True)]
        if selected:
            super().prefetch(self._inputs(*zip(*selected)))

    def prepare_states(self, texts, contexts, games):
        for context, game in zip(contexts, games):
            ctx = json.loads(context) if isinstance(context, str) else context
            if normalize_gamefile(ctx['gamefile']) != normalize_gamefile(game):
                raise ValueError('L3 game identity changed during batching')
        encoded = self._inputs(texts, contexts)
        super().prepare_prompts(encoded)
        records = [self.records[item] for item in encoded]
        self.metrics.update({
            'hint_ladder/oracle_verified_rows': sum(r.get('oracle_status') == 'verified' for r in records),
            'hint_ladder/oracle_unavailable_rows': sum(r.get('oracle_status') == 'unavailable' for r in records),
            'hint_ladder/oracle_coverage': sum(r.get('oracle_status') == 'verified' for r in records) / max(1, len(records)),
        })
        return records

    def _public(self, encoded):
        item = json.loads(encoded)
        public = public_state(item['prompt'])
        oracle = self.oracle_pool.submit(align_walkthrough, item['gamefile'], item['action_history'],
                                         public['current_observation']).result()
        if oracle['status'] != 'verified':
            raise OracleUnavailable(oracle)
        return dict(task=public['task'], current_turn=len(item['action_history']) + 1,
                    current_observation=public['current_observation'], action_history=item['action_history'],
                    admissible_actions=oracle['admissible_actions'],
                    oracle=dict(reference_walkthrough=oracle['reference_walkthrough'],
                                next_reference_action=oracle['next_reference_action'],
                                reference_suffix_verified_from_current_state=True,
                                verified_continuation=oracle['verified_continuation']))

    def _request(self, encoded):
        started = time.monotonic()
        try:
            return super()._request(encoded)
        except OracleUnavailable as error:
            return dict(hint='', level=FAILED_LEVEL, oracle_status='unavailable',
                        oracle=error.oracle, oracle_supplied=False, attempt=1,
                        request_sha256=hashlib.sha256(encoded.encode()).hexdigest(),
                        training_step=self.step, elapsed_seconds=time.monotonic() - started)

    def _counts_against_failure_budget(self, record):
        return record.get('oracle_status') != 'unavailable'

    def _complete(self, payload, key, attempt, started):
        record = super()._complete(payload, key, attempt, started)
        public = json.loads(payload['messages'][1]['content'])
        # A valid reference path does not justify extra location claims. Some
        # native games allow a pickup from a different named receptacle after
        # navigation. Keep only the verified command; never invent its reason.
        action = public['oracle']['next_reference_action']
        if record['hint'].strip().removesuffix('.').strip().lower() != action.lower():
            raise ValueError('L3_hint_must_be_exact_reference_action')
        record.update(level='L3', oracle_supplied=True, oracle_status='verified',
                      oracle=public['oracle'], public_input=public)
        return record
