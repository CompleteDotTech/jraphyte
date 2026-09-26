"""Optional local-only scalar cross-encoder; weights never enter the repository.

The caller supplies an authorized local snapshot and a reviewed byte manifest.
The declared upstream revision is metadata; verified local file hashes are the
actual identity. No Hub downloads, remote Python, pickle weights or API calls.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import time
from typing import Any

from trace_gc.pdf_source_v3 import digest
from .common import REPO, file_digest


def verify_snapshot(folder: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    folder = folder.resolve()
    if not folder.is_dir() or folder.is_relative_to(REPO):
        raise ValueError('external_local_model_snapshot_required')
    if not re.fullmatch(r'[a-f0-9]{40}', manifest.get('model_revision', '')):
        raise ValueError('pinned_model_revision_required')
    entries = manifest.get('files', {})
    if not entries or 'config.json' not in entries or not any(n.endswith('.safetensors') for n in entries):
        raise ValueError('complete_safetensors_snapshot_manifest_required')
    # Reject executable/pickled weights, links and unmanifested model inputs.
    actual = {}
    for path in folder.rglob('*'):
        if path.is_symlink():
            raise ValueError('model_snapshot_symlink_not_allowed')
        if not path.is_file():
            continue
        rel = path.relative_to(folder).as_posix()
        if path.suffix.lower() not in {'.json','.txt','.safetensors','.model'}:
            raise ValueError('model_snapshot_contains_unapproved_file_type')
        actual[rel] = file_digest(path)
    if actual != entries:
        raise ValueError('model_snapshot_manifest_mismatch')
    return {'model_revision': manifest['model_revision'], 'model_snapshot_sha256': digest(actual),
            'local_files_verified': len(actual), 'upstream_revision_independently_verified': False}


class LocalReranker:
    def __init__(self, folder: Path, manifest: dict[str, Any], *, batch_size: int = 16, max_tokens: int = 512):
        self.binding = verify_snapshot(folder, manifest)
        if type(batch_size) is not int or not 1 <= batch_size <= 256 or type(max_tokens) is not int or not 1 <= max_tokens <= 512:
            raise ValueError('invalid_local_reranker_budget')
        # Set before importing optional libraries. Explicit local_files_only also
        # applies when another module imported Transformers before this adapter.
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        started = time.perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(str(folder.resolve()), local_files_only=True, trust_remote_code=False)
        self.model = AutoModelForSequenceClassification.from_pretrained(str(folder.resolve()), local_files_only=True,
                                                                       trust_remote_code=False, use_safetensors=True)
        if self.model.config.num_labels != 1:
            raise ValueError('scalar_cross_encoder_required')
        self.model.to('cpu').eval()
        self.batch_size, self.max_tokens, self.torch = batch_size, max_tokens, torch
        self.binding.update(model_loading_seconds=time.perf_counter()-started, device='cpu',
                            rerank_max_tokens=max_tokens, rerank_truncation_policy='longest_first',
                            scoring='single scalar logit; ranking only, not a probability')

    def score(self, query: str, documents: list[str]) -> dict[str, Any]:
        started = time.perf_counter(); scores = []
        with self.torch.inference_mode():
            for i in range(0, len(documents), self.batch_size):
                docs = documents[i:i+self.batch_size]
                encoded = self.tokenizer([query]*len(docs), docs, padding=True, truncation='longest_first',
                                         max_length=self.max_tokens, return_tensors='pt')
                values = self.model(**encoded).logits.reshape(-1).cpu().tolist()
                scores.extend(float(v) for v in values)
        if not all(__import__('math').isfinite(v) for v in scores) or len(scores) != len(documents):
            raise ValueError('invalid_local_model_scores')
        return {**self.binding, 'scores': scores, 'inference_seconds': time.perf_counter()-started,
                'api_calls': 0, 'api_spend_usd': 0}
