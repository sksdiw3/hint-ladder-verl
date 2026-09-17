"""Public-state L1 hints for teacher scoring of on-policy Student turns.

Hints come from an OpenAI-compatible endpoint. Requests for a turn's public
states are submitted while the Student rollout is still running (``prefetch``)
and collected right before the Teacher forward (``prepare_prompts``), so the
API round trip overlaps GPU work instead of following it.

A public state whose request fails after every retry is trained as an L0 row:
the Teacher receives no note, its distribution equals the Student's, and the
row contributes no distillation gradient. Such rows are recorded per step and
capped; exceeding the cap stops training. No placeholder hint is ever used.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import time

from .api import ModelClient
from .keys import normalize_gamefile
from .teacher_prompt import OPEN, CLOSE

FAILED_LEVEL = "L0_FAILED"
RETRYABLE_HTTP = (408, 429, 500, 502, 503, 504)


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


def state_key(prompt):
    """Deduplication key: identical public states share one request within a step."""
    return json.dumps(public_state(prompt), sort_keys=True)


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def _quantile(values, q):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


class OnlineL1Provider:
    """One provider per training run; ``begin_step`` resets it for each update."""

    def __init__(self, config, output):
        self.config = dict(config)
        if self.config["model"] != "glm-5.3-flash":
            raise ValueError("This online L1 experiment requires glm-5.3-flash")
        self.system = Path(self.config["prompt_path"]).read_text()
        self.root = Path(output) / "online_hints"
        self.root.mkdir(parents=True, exist_ok=True)
        self.client = ModelClient(self.config)
        self.pool = ThreadPoolExecutor(max_workers=int(self.config.get("concurrency", 128)))
        self.retries = int(self.config.get("retries", 4))
        self.persist = bool(self.config.get("persist_requests", True))
        self.failure_budget_ratio = float(self.config.get("failure_budget_ratio", 0.01))
        self.failure_budget_max = int(self.config.get("failure_budget_max", 10))
        self.step = None
        self._futures = {}
        self._prefetched = 0
        self.records = {}
        self.metrics = {}

    # ---- interface shared with HintProvider -------------------------------

    def level_for(self, game):
        normalize_gamefile(game)
        return "L1"

    def get(self, game):
        raise ValueError("Online L1 requires a current prompt, not a game-level lookup")

    def validate_coverage(self, games, **kwargs):
        for game in games:
            if "/train/" not in normalize_gamefile(game):
                raise ValueError("Online training hints require train split games")

    # ---- per-step lifecycle -------------------------------------------------

    def begin_step(self, step):
        """Reset per-step state. Call once before the Student rollout of that step."""
        if any(not future.done() for future in self._futures.values()):
            raise RuntimeError("Previous hint step still has pending requests")
        for future in self._futures.values():
            future.result()
        self.step = int(step)
        self._futures, self._prefetched = {}, 0
        self.records, self.metrics = {}, {}

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)

    @property
    def pending_requests(self):
        return len(self._futures)

    def prefetch(self, prompts):
        """Submit requests for unseen public states and return immediately."""
        self._require_step()
        for prompt in prompts:
            self._prefetched += self._submit(prompt)

    def prepare_prompts(self, prompts):
        """Block until every prompt has a hint or a recorded failure."""
        self._require_step()
        started = time.monotonic()
        keys = [state_key(prompt) for prompt in prompts]
        misses = sum(self._submit(prompt) for prompt in prompts)
        # Finished/padded environments can have extra prefetched states. Drain
        # them before the next step changes the request seed and output path.
        for future in self._futures.values():
            future.result()
        results = {key: self._futures[key].result() for key in dict.fromkeys(keys)}
        failed = [key for key, record in results.items() if record["level"] == FAILED_LEVEL]
        budget = self._failure_budget(len(results))
        if len(failed) > budget:
            raise RuntimeError(f"{len(failed)} public states have no hint after {self.retries} attempts "
                               f"(budget {budget}); see {self._step_dir()}")
        self.records = {prompt: results[key] for prompt, key in zip(prompts, keys)}
        succeeded = [record for record in results.values() if record["level"] != FAILED_LEVEL]
        elapsed = [record["elapsed_seconds"] for record in succeeded]
        self.metrics = {
            "hint_ladder/hint_requests": len(results),
            "hint_ladder/hint_prefetch_submitted": self._prefetched,
            "hint_ladder/hint_prefetch_misses": misses,
            "hint_ladder/hint_wait_seconds": time.monotonic() - started,
            "hint_ladder/hint_request_p50_seconds": _quantile(elapsed, 0.5),
            "hint_ladder/hint_request_p95_seconds": _quantile(elapsed, 0.95),
            "hint_ladder/hint_request_max_seconds": max(elapsed, default=0.0),
            "hint_ladder/hint_retries": sum(record["attempt"] - 1 for record in results.values()),
            "hint_ladder/hint_failed_states": len(failed),
            "hint_ladder/hint_failed_rows": sum(results[key]["level"] == FAILED_LEVEL for key in keys),
            "hint_ladder/hint_words_mean": (sum(len(record["hint"].split()) for record in succeeded) / len(succeeded)
                                            if succeeded else 0.0),
        }

    def get_for_prompt(self, game, prompt):
        self.level_for(game)
        return self.records[prompt]["hint"]

    def level_for_prompt(self, game, prompt):
        self.level_for(game)
        return self.records[prompt]["level"]

    # ---- internals ----------------------------------------------------------

    def _require_step(self):
        if self.step is None:
            raise ValueError("begin_step(step) must be called before requesting hints")

    def _step_dir(self):
        return self.root / f"step_{self.step:06d}"

    def _failure_budget(self, states):
        if self.failure_budget_max == 0:
            return 0
        return min(self.failure_budget_max, max(1, int(states * self.failure_budget_ratio)))

    def _submit(self, prompt):
        key = state_key(prompt)
        if key in self._futures:
            return 0
        self._futures[key] = self.pool.submit(self._request, prompt)
        return 1

    def _payload(self, public, seed):
        payload = dict(model=self.config["model"],
                       messages=[dict(role="system", content=self.system),
                                 dict(role="user", content=json.dumps(public, ensure_ascii=False))],
                       temperature=self.config.get("temperature", 0.7),
                       max_tokens=int(self.config.get("max_tokens", 768)),
                       chat_template_kwargs={"enable_thinking": False},
                       seed=seed)
        payload["reasoning_effort"] = self.config.get("reasoning_effort", "low")
        if self.config.get("thinking") is False:
            payload["thinking"] = {"type": "disabled"}
        elif self.config.get("thinking") is True:
            payload["thinking"] = {"type": "enabled"}
        return payload

    def _request(self, prompt):
        """Runs in the pool. Returns a record; only non-retryable errors propagate."""
        public = public_state(prompt)
        public_hash = hashlib.sha256(json.dumps(public, sort_keys=True).encode()).hexdigest()
        base_seed = (int(public_hash[:8], 16) + self.step + int(self.config.get("seed", 42))) % (2 ** 31)
        payload = self._payload(public, base_seed)
        key = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        cached = self._read_cache(key)
        if cached is not None:
            return cached
        started = time.monotonic()
        errors = []
        for attempt in range(1, self.retries + 1):
            payload["seed"] = (base_seed + attempt - 1) % (2 ** 31)
            try:
                record = self._complete(payload, key, attempt, started)
            except (OSError, ValueError) as error:
                # OSError covers HTTPError, URLError, socket timeouts and resets.
                status = getattr(error, "code", None)
                errors.append(dict(attempt=attempt, type=type(error).__name__, status=status))
                if status is not None and status not in RETRYABLE_HTTP:
                    raise  # authentication or malformed-request errors are bugs, not tail events
                if attempt < self.retries:
                    time.sleep(min(8, 2 ** attempt))
                continue
            self._write_cache(key, payload, record)
            return record
        failure = dict(hint="", level=FAILED_LEVEL, request_sha256=key, errors=errors,
                       training_step=self.step, elapsed_seconds=time.monotonic() - started, attempt=self.retries)
        self._step_dir().mkdir(exist_ok=True)
        atomic_json(self._step_dir() / (key + ".errors.json"), failure)
        return failure

    def _complete(self, payload, key, attempt, started):
        response = self.client.request("/chat/completions", payload)
        if response.get("model") != self.config["model"]:
            raise RuntimeError("Hint endpoint returned a different model")
        choices = response.get("choices") or []
        if not choices:
            raise ValueError("hint response has no choices")
        choice = choices[0]
        hint = (choice.get("message") or {}).get("content")
        if choice.get("finish_reason") != "stop" or not isinstance(hint, str) or not hint.strip():
            raise ValueError("incomplete_or_empty_hint")
        if OPEN in hint or CLOSE in hint:
            raise ValueError("nested_private_note")
        return dict(hint=hint, level="L1", requested_model=self.config["model"], returned_model=response["model"],
                    finish_reason=choice["finish_reason"], usage=response.get("usage") or {},
                    request_sha256=key, oracle_supplied=False, training_step=self.step,
                    elapsed_seconds=time.monotonic() - started, attempt=attempt)

    def _read_cache(self, key):
        if not self.persist:
            return None
        path = self._step_dir() / (key + ".json")
        if not path.exists():
            return None
        record = json.loads(path.read_text())
        if record["request_sha256"] != key or record["returned_model"] != self.config["model"]:
            raise ValueError("Invalid online hint cache")
        return record

    def _write_cache(self, key, payload, record):
        if not self.persist:
            return
        self._step_dir().mkdir(exist_ok=True)
        atomic_json(self._step_dir() / (key + ".request.json"), payload)
        atomic_json(self._step_dir() / (key + ".json"), record)


def make_provider(config, output):
    if config.get("online", {}).get("enable", False):
        return OnlineL1Provider(config["online"], output)
    from .hint_bank import HintProvider
    return HintProvider(config["bank_dir"], level=config["level"], level_map_path=config["level_map_path"])
