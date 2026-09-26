"""External data roots and immutable JSON receipts, without private path logging."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
import hashlib

REPO = Path(__file__).resolve().parents[2]


def data_root(explicit: str | Path | None = None) -> Path:
    value = explicit or os.environ.get("TRACE_GC_TEST_DATA_ROOT") or REPO.parent / "TRACE-GC_RealPaper_Test"
    root = Path(value).expanduser().resolve()
    if root == REPO or root.is_relative_to(REPO):
        raise ValueError("private_test_data_must_be_outside_checkout")
    return root


def external_output(path: str | Path) -> Path:
    value = Path(path).expanduser().resolve()
    if value == REPO or value.is_relative_to(REPO):
        raise ValueError("private_receipts_must_be_outside_checkout")
    return value


def resolve_source(root: Path, relative: str) -> Path:
    # Source-map paths are relative to the explicitly authorized test-data root.
    # Do not replay a Windows path from another machine or search arbitrary disks.
    rel = Path(relative)
    if rel.is_absolute() or ":" in relative or "\\" in relative:
        raise ValueError("source_map_requires_relative_paths")
    value = (root / rel).resolve()
    if not value.is_relative_to(root.resolve()):
        raise ValueError("source_map_escapes_data_root")
    return value


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_once(path: Path, value: Any) -> str:
    """Idempotent for identical bytes; reject collisions, never overwrite receipts."""
    data = (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if path.is_symlink() or path.read_bytes() != data:
            raise ValueError("immutable_receipt_conflict") from None
    return hashlib.sha256(data).hexdigest()


def code_hashes() -> dict[str, str]:
    paths = sorted((REPO / "src/abstract_validation_v3").glob("*.py")) + [REPO / "trace_gc/pdf_source_v3.py"]
    return {p.relative_to(REPO).as_posix(): file_digest(p) for p in paths}


def safe_id(value: str) -> str:
    import re
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", value) or ".." in value:
        raise ValueError("unsafe_receipt_identifier")
    return value
