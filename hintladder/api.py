"""Explicit YAML-configured HTTP access for hint generation and audits."""
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen


class ModelClient:
    def __init__(self, config):
        self.config = dict(config)
        self.base_url = config["base_url"].rstrip("/")
        self.model = config["model"]
        self.timeout = float(config.get("timeout", 120))

    def request(self, route, payload=None):
        headers = {"Content-Type": "application/json"}
        if self.config.get("api_key_file"):
            headers["Authorization"] = "Bearer " + Path(self.config["api_key_file"]).read_text().strip()
        request = Request(self.base_url + route, headers=headers,
                          data=json.dumps(payload).encode() if payload is not None else None)
        with urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    def verify_model(self, checkpoint=None):
        models = self.request("/models")["data"]
        matches = [row for row in models if row["id"] == self.model]
        if len(matches) != 1:
            raise ValueError(f"configured model is not uniquely served: {self.model}")
        if checkpoint is not None and matches[0].get("root") != checkpoint:
            raise ValueError("served model root does not match the requested frozen checkpoint")

    def chat(self, messages, *, seed, temperature, max_tokens):
        payload = {"model": self.model, "messages": messages,
                            "seed": seed, "temperature": temperature, "max_tokens": max_tokens,
                            "chat_template_kwargs": {"enable_thinking": False}}
        if self.config.get("thinking") is False:
            payload["thinking"] = {"type": "disabled"}
        if self.config.get("reasoning_effort"):
            payload["reasoning_effort"] = self.config["reasoning_effort"]
        data = self.request("/chat/completions", payload)
        choice = data["choices"][0]
        if choice["finish_reason"] != "stop":
            raise ValueError(f"hint generation did not finish normally: {choice['finish_reason']}")
        return choice["message"]["content"]

    def sample_tokens(self, prompt_ids, *, seed, temperature, max_tokens):
        data = self.request("/completions", {"model": self.model, "prompt": list(prompt_ids),
                            "seed": seed, "temperature": temperature, "max_tokens": max_tokens,
                            "logprobs": 0, "return_tokens_as_token_ids": True})
        choice = data["choices"][0]
        if choice["finish_reason"] not in ("stop", "length"):
            raise ValueError("policy completion failed")
        tokens = choice["logprobs"]["tokens"]
        if any(not isinstance(t, str) or not t.startswith("token_id:") for t in tokens):
            raise ValueError("vLLM must return token_id:N response tokens; text re-tokenization is forbidden")
        return [int(token.split(":", 1)[1]) for token in tokens]

    def score_tokens(self, prompt_ids, target_ids):
        ids = list(prompt_ids) + list(target_ids)
        if not prompt_ids or not target_ids:
            raise ValueError("scoring requires nonempty prompt and target tokens")
        data = self.request("/completions", {"model": self.model, "prompt": ids,
                            "max_tokens": 1, "temperature": 0, "prompt_logprobs": 0})
        rows = data["choices"][0]["prompt_logprobs"]
        if len(rows) != len(ids):
            raise ValueError("teacher-forced prompt token count mismatch")
        result = []
        for index in range(len(prompt_ids), len(ids)):
            payload = rows[index][str(ids[index])]
            value = float(payload["logprob"])
            if not math.isfinite(value):
                raise ValueError("nonfinite actual-token log probability")
            result.append(value)
        return result
