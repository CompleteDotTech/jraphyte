"""Replaceable embedding interfaces; built-in hashing is an offline lexical baseline."""
from __future__ import annotations
import hashlib
import math
import re
from typing import Protocol, Sequence
from ..errors import require


def terms(text: str) -> set[str]:
    return set(re.findall(r"[\w]+", text.casefold()))


class EmbeddingModel(Protocol):
    version: str
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class HashingEmbedding:
    """Deterministic token hashing, NOT a trained semantic embedding model."""
    version = "offline-token-hash-128-v1"
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        result = []
        for text in texts:
            vector = [0.0] * 128
            for token in terms(text):
                vector[int.from_bytes(hashlib.sha256(token.encode()).digest()[:4]) % 128] += 1.0
            result.append(vector)
        return result


class PrecomputedEmbedding:
    """Adapter for independently computed, exact-version embedding vectors."""
    def __init__(self, vectors: dict[str, list[float]], *, version: str):
        require(bool(version) and version not in {"latest", "default"}, "EMBEDDING_VERSION", "pin embedding version")
        self.vectors, self.version = vectors, version
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        require(all(t in self.vectors for t in texts), "EMBEDDING_MISSING", "precomputed vector unavailable")
        return [list(self.vectors[t]) for t in texts]


def cosine(a: list[float], b: list[float]) -> float:
    require(len(a) == len(b) and len(a) > 0 and all(type(x) in (int, float) and math.isfinite(x) for x in a+b),
            "EMBEDDING_VECTOR", "finite equal-dimension vectors required")
    denominator = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b)) / denominator if denominator else 0.0
