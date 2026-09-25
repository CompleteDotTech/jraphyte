"""TRACE-C14N-1, an explicit typed binary encoding (NOT RFC 8785 / JCS).

JSON is transport; hashes use a length-prefixed typed binary encoding. Finite
binary64 values are 8-byte big endian IEEE 754, including signed zero. Integers
are signed base-10 ASCII, bounded to +/- (2**53-1), and remain distinct from
floats. Object keys sort by UTF-8 bytes; strings are not normalized. Arrays
preserve order. Duplicate keys, surrogates, NaN/Infinity and depth >128 fail.
See docs/12_implementation.md and examples/runtime/canonical_vectors.json.
"""
from __future__ import annotations
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any
from .errors import ContractError, require

PROFILE = "TRACE-C14N-1"
MAX_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 128
MAX_INTEGER = 2**53 - 1

def _sized(tag: bytes, value: bytes) -> bytes:
    return tag + str(len(value)).encode("ascii") + b":" + value

def _encode(value: Any, depth: int) -> bytes:
    require(depth <= MAX_DEPTH, "JSON_DEPTH", "maximum nesting exceeded")
    if value is None:
        return b"n"
    if type(value) is bool:
        return b"t" if value else b"f"
    if type(value) is int:
        require(abs(value) <= MAX_INTEGER, "INTEGER_RANGE", "encode large integers as strings")
        return _sized(b"i", str(value).encode("ascii"))
    if type(value) is float:
        require(math.isfinite(value), "NONFINITE_JSON", "nonfinite number")
        return b"d" + struct.pack(">d", value)
    if isinstance(value, str):
        try:
            raw = value.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise ContractError("INVALID_UNICODE", "unpaired surrogate") from exc
        return _sized(b"s", raw)
    if type(value) is list:
        return b"a" + str(len(value)).encode() + b":" + b"".join(_encode(v, depth + 1) for v in value)
    if type(value) is dict:
        require(all(type(k) is str for k in value), "JSON_KEY", "string keys required")
        try:
            keys = sorted(value, key=lambda key: key.encode("utf-8", errors="strict"))
        except UnicodeError as exc:
            raise ContractError("INVALID_UNICODE", "invalid object key") from exc
        return b"o" + str(len(keys)).encode() + b":" + b"".join(
            _encode(k, depth + 1) + _encode(value[k], depth + 1) for k in keys)
    raise ContractError("JSON_TYPE", f"unsupported {type(value).__name__}")

def canonical_bytes(value: Any) -> bytes:
    data = PROFILE.encode() + b"\0" + _encode(value, 0)
    require(len(data) <= MAX_BYTES, "JSON_SIZE", "maximum encoded size exceeded")
    return data

def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()

def bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()

def text_digest(value: str) -> str:
    return bytes_digest(value.encode("utf-8", errors="strict"))

def dumps(value: Any) -> str:
    canonical_bytes(value)  # validate the data domain before transport serialization
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

def loads(data: str | bytes) -> Any:
    require(isinstance(data, (str, bytes)), "JSON_TYPE", "JSON text or UTF-8 bytes required")
    require(len(data) <= MAX_BYTES, "JSON_SIZE", "maximum input size exceeded")
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, "DUPLICATE_JSON_KEY", key)
            result[key] = value
        return result
    def constant(value: str) -> None:
        raise ContractError("NONFINITE_JSON", value)
    try:
        result = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
        canonical_bytes(result)
        return result
    except (json.JSONDecodeError, UnicodeError, RecursionError) as exc:
        raise ContractError("INVALID_JSON", str(exc)) from exc

def load(path: str | Path) -> Any:
    with Path(path).open("rb") as stream:
        return loads(stream.read(MAX_BYTES + 1))

def write(path: str | Path, value: Any) -> None:
    canonical_bytes(value)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
