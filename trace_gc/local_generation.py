"""Offline, hash-pinned local answer model adapter for an isolated paper pilot."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .canonical import bytes_digest, digest, loads
from .errors import boundary, require

MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"
MODEL_URL = "https://huggingface.co/" + MODEL_ID
SYSTEM = ("Return only a JSON object with exactly two keys: abstain (boolean) "
          "and claims (array). Each claim must be an object with exactly text "
          "(string) and evidence_ids (array of evidence ID strings). No markdown "
          "or explanation. Cite only evidence IDs present in the request.")


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@boundary
def verify_model_snapshot(root: str | Path, manifest_path: str | Path) -> dict:
    """Require a complete local snapshot before optional Transformers imports."""
    root = Path(root).resolve(strict=True)
    manifest_bytes = Path(manifest_path).read_bytes()
    manifest = loads(manifest_bytes)
    require(type(manifest) is dict and set(manifest) ==
            {"schema_version", "revision", "source", "license", "files"},
            "LOCAL_MODEL_MANIFEST", "manifest shape differs")
    require(manifest["schema_version"] == "local-generation-model-v1" and
            manifest["source"] == MODEL_URL and manifest["license"] == "apache-2.0" and
            type(manifest["revision"]) is str and re.fullmatch(r"[0-9a-f]{40}", manifest["revision"]),
            "LOCAL_MODEL_MANIFEST", "model identity differs")
    files = manifest["files"]
    require(type(files) is dict and bool(files), "LOCAL_MODEL_MANIFEST", "file hashes required")
    entries = list(root.iterdir())
    require(all(p.is_file() and not p.is_symlink() for p in entries),
            "LOCAL_MODEL_MANIFEST", "snapshot contains directory or symlink")
    observed = {p.name for p in entries}
    require(set(files) == observed, "LOCAL_MODEL_MANIFEST", "snapshot file set differs")
    index_bytes = None
    for name, expected in files.items():
        require(type(name) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name) and
                type(expected) is str and re.fullmatch(r"[0-9a-f]{64}", expected),
                "LOCAL_MODEL_MANIFEST", "unsafe file name or hash")
        target = root / name
        require(not target.is_symlink() and target.resolve(strict=True).parent == root,
                "LOCAL_MODEL_CHANGED", name)
        observed_hash = _file_hash(target) if name != "model.safetensors.index.json" else None
        if name == "model.safetensors.index.json":
            index_bytes = target.read_bytes()
            observed_hash = bytes_digest(index_bytes)
        require(observed_hash == expected, "LOCAL_MODEL_CHANGED", name)
    require("tokenizer.json" in files and "config.json" in files and
            "model.safetensors.index.json" in files and
            any(name.endswith(".safetensors") for name in files),
            "LOCAL_MODEL_MANIFEST", "model/tokenizer files absent")
    index = loads(index_bytes)
    require(type(index) is dict and type(index.get("weight_map")) is dict and
            bool(index["weight_map"]), "LOCAL_MODEL_MANIFEST", "weight index absent")
    referenced = set()
    for tensor, shard in index["weight_map"].items():
        require(type(tensor) is str and bool(tensor) and type(shard) is str and
                shard in files and shard.endswith(".safetensors"),
                "LOCAL_MODEL_MANIFEST", "index references unpinned shard")
        referenced.add(shard)
    require(referenced == {name for name in files if name.endswith(".safetensors")},
            "LOCAL_MODEL_MANIFEST", "index shard set differs")
    return {"model_id": MODEL_ID, "revision": manifest["revision"],
            "model_manifest_sha256": bytes_digest(manifest_bytes),
            "tokenizer_id": "tokenizer-sha256:" + files["tokenizer.json"],
            "file_count": len(files), "snapshot_files_sha256": digest(files)}


class LocalQwenAdapter:
    """One loaded model; generates raw bytes for ``paper_answer.draft_answer``."""
    def __init__(self, root: str | Path, manifest_path: str | Path, *,
                 device: str = "cpu", threads: int = 4, maximum_new_tokens: int = 256):
        require(device in {"cpu", "cuda:0"} and type(threads) is int and 1 <= threads <= 8 and
                type(maximum_new_tokens) is int and 1 <= maximum_new_tokens <= 512,
                "LOCAL_MODEL_CONFIG", "unsupported device or generation budget")
        root = Path(root).resolve(strict=True)
        manifest_path = Path(manifest_path).resolve(strict=True)
        identity = verify_model_snapshot(root, manifest_path)
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        torch.set_num_threads(threads)
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(root, local_files_only=True, trust_remote_code=False)
        self.model = AutoModelForCausalLM.from_pretrained(
            root, local_files_only=True, trust_remote_code=False,
            dtype=torch.bfloat16, device_map=device, low_cpu_mem_usage=True).eval()
        require(verify_model_snapshot(root, manifest_path) == identity,
                "LOCAL_MODEL_CHANGED", "snapshot changed while loading")
        self.identity = identity
        self.device = device
        self.maximum_new_tokens = maximum_new_tokens
        self.last_usage = None

    def generate(self, request_bytes: bytes) -> bytes:
        """Return exact generated bytes; invalid syntax remains a held model result."""
        self.last_usage = None
        self.last_attempt = {"request_sha256": bytes_digest(request_bytes),
                             "status": "held", "paid_api_calls": 0}
        request = loads(request_bytes)
        require(type(request) is dict and set(request) == {"instruction", "question", "evidence"},
                "LOCAL_MODEL_REQUEST", "paper answer request required")
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": request_bytes.decode("utf-8")}]
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        require(inputs["input_ids"].shape[1] <= 2048,
                "LOCAL_MODEL_BUDGET", "tokenized prompt exceeds pilot cap")
        with self.torch.inference_mode():
            output = self.model.generate(**inputs, max_new_tokens=self.maximum_new_tokens,
                                         do_sample=False, pad_token_id=self.tokenizer.eos_token_id)
        generated = output[0][inputs["input_ids"].shape[1]:]
        require(len(generated) < self.maximum_new_tokens,
                "LOCAL_MODEL_TRUNCATED", "output hit generation cap")
        response = self.tokenizer.decode(generated, skip_special_tokens=True).encode("utf-8")
        self.last_usage = {"input_tokens": int(inputs["input_ids"].shape[1]),
                           "output_tokens": int(len(generated)),
                           "request_sha256": bytes_digest(request_bytes),
                           "response_sha256": bytes_digest(response),
                           "model_manifest_sha256": self.identity["model_manifest_sha256"],
                           "device": self.device, "paid_api_calls": 0}
        self.last_attempt = {"request_sha256": bytes_digest(request_bytes),
                             "status": "generated", "paid_api_calls": 0}
        return response
