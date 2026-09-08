"""An optional, owned vLLM child process with an explicit endpoint and deadline."""
from contextlib import contextmanager
from pathlib import Path
import shlex
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.parse import urlparse

from .api import ModelClient


@contextmanager
def model_service(policy, checkpoint, output):
    client = ModelClient(policy)
    process = None
    log = None
    try:
        if policy.get("launch", False):
            url = urlparse(policy["base_url"])
            if url.hostname != "127.0.0.1" or url.port is None:
                raise ValueError("owned vLLM service requires an explicit localhost port")
            argv = [sys.executable, "-m", "vllm.entrypoints.openai.api_server", "--host", url.hostname,
                    "--port", str(url.port), "--model", str(checkpoint), "--served-model-name", policy["model"],
                    "--tensor-parallel-size", str(policy.get("tensor_parallel_size", 1)),
                    "--gpu-memory-utilization", str(policy.get("gpu_memory_utilization", 0.65)),
                    "--max-model-len", str(policy.get("max_model_len", 8192)), "--enforce-eager"]
            Path(output).mkdir(parents=True, exist_ok=True)
            (Path(output) / "service_launch_command.txt").write_text(shlex.join(argv) + "\n")
            log = (Path(output) / "service.log").open("w")
            process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + float(policy.get("startup_timeout", 300))
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"vLLM exited with {process.returncode}; see service.log")
                try:
                    client.verify_model(str(checkpoint))
                    break
                except URLError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("vLLM readiness deadline exceeded; see service.log")
                    time.sleep(1)
        else:
            client.verify_model(str(checkpoint))
        yield client
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if log is not None:
            log.close()
