#!/usr/bin/env python3
"""Deterministic public source ZIP; exclude secrets, papers, models and outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "0.4.0"
DENIED_DIRS = {".git", ".venv", "venv", "__pycache__", ".cache", ".pytest_cache", ".mypy_cache",
               ".ruff_cache", "build", "dist", "tmp", "temp", "outputs", "model_weights", "weights",
               "models", "huggingface", "trace-gc_realpaper_test", "validation_v3_private"}
DENIED_SUFFIXES = {".pdf", ".pt", ".pth", ".bin", ".safetensors", ".ckpt", ".gguf", ".onnx", ".h5",
                   ".hdf5", ".npy", ".npz", ".pkl", ".pickle", ".pyc", ".pyo", ".sqlite", ".sqlite3",
                   ".db", ".tmp", ".log", ".zip", ".whl", ".tar", ".gz", ".bz2", ".7z", ".pem", ".key"}
SOURCE_SUFFIXES = {".py", ".md", ".rst", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg",
                   ".csv", ".tsv", ".mmd", ".svg", ".png", ".jpg", ".jpeg", ".html", ".css", ".js", ".ts",
                   ".tsx", ".jsx", ".sh", ".ps1", ".bat", ".patch"}
SPECIAL_NAMES = {"license", "notice", "makefile", ".gitignore", ".gitattributes", ".env.example"}
SECRET = re.compile(rb"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{40,}|\bAIza[0-9A-Za-z_-]{35}\b")


def safe_name(name: str) -> bool:
    if "\\" in name:
        return False
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or not p.parts or ":" in p.parts[0]:
        return False
    parts = [x.lower() for x in p.parts]
    if any(x in DENIED_DIRS or x.endswith(".egg-info") for x in parts):
        return False
    leaf = parts[-1]
    if leaf == ".env" or (leaf.startswith(".env.") and leaf != ".env.example"):
        return False
    if any(s.lower() in DENIED_SUFFIXES for s in p.suffixes):
        return False
    if leaf.endswith(("-wal", "-shm", ".swp", "~")):
        return False
    return leaf in SPECIAL_NAMES or p.suffix.lower() in SOURCE_SUFFIXES


def included(path: Path, root: Path | None = None) -> bool:
    root = (root or ROOT).resolve()
    try:
        rel = path.relative_to(root)
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root and parent.is_relative_to(root)):
            return False
        return path.is_file() and path.resolve().is_relative_to(root) and safe_name(rel.as_posix())
    except (OSError, ValueError):
        return False


def safe_bytes(name: str, data: bytes) -> bool:
    # File signatures stop a PDF or key renamed to an allowed source extension.
    if data.startswith((b"%PDF-", b"GGUF", b"PK\x03\x04", b"\x1f\x8b")) or SECRET.search(data):
        return False
    if PurePosixPath(name).suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        try:
            decoded = data.decode("utf-8")
        except UnicodeDecodeError:
            # A tracked legacy Markdown report contains a CP1252 multiplication
            # sign. Keep its original bytes in the archive, while rejecting
            # binary data and undefined CP1252 byte values.
            try:
                decoded = data.decode("cp1252")
            except UnicodeDecodeError:
                return False
        if any((ord(char) < 32 and char not in "\t\n\r\f") or 0x7f <= ord(char) < 0xa0
               for char in decoded):
            return False
    return True


def archive_bytes(root: Path, *, tracked_only: bool = True) -> dict[str, bytes]:
    root = root.resolve()
    if tracked_only:
        proc = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=False)
        if proc.returncode:
            raise ValueError("tracked_source_listing_unavailable; use --snapshot only for an audited non-Git snapshot")
        paths = [root / p.decode() for p in proc.stdout.split(b"\0") if p]
    else:
        paths = list(root.rglob("*"))
    payload = {}
    for path in sorted(paths):
        if not included(path, root) or path == root / "MANIFEST.json":
            continue
        name = path.relative_to(root).as_posix()
        data = path.read_bytes()
        if not safe_bytes(name, data):
            # Do not log suspect content or potentially private paper names.
            raise ValueError("unsafe_source_content; inspect staged files locally")
        payload[name] = data
    if not payload:
        raise ValueError("empty_source_package")
    entries = [{"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in sorted(payload.items())]
    manifest = {"release": RELEASE, "hash_algorithm": "SHA-256", "manifest_self_excluded": True,
                "source_only": True, "file_count": len(entries), "files": entries}
    encoded = (json.dumps(manifest, indent=2) + "\n").encode()
    (root / "MANIFEST.json").write_bytes(encoded)
    payload["MANIFEST.json"] = encoded
    return payload


def audit_archive(target: Path) -> dict:
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names) or archive.testzip() is not None:
            raise ValueError("invalid_zip_members_or_crc")
        roots = {PurePosixPath(n).parts[0] for n in names}
        if len(roots) != 1:
            raise ValueError("archive_requires_one_source_root")
        root = next(iter(roots))
        actual = {}
        for name in names:
            if not safe_name(name):
                raise ValueError("forbidden_archive_member")
            rel = str(PurePosixPath(name).relative_to(root))
            data = archive.read(name)
            if not safe_bytes(rel, data):
                raise ValueError("forbidden_archive_content")
            actual[rel] = data
        manifest = json.loads(actual.pop("MANIFEST.json"))
        entries = manifest["files"]
        expected = {item["path"] for item in entries}
        if len(entries) != len(expected) or set(actual) != expected or manifest["file_count"] != len(entries):
            raise ValueError("manifest_member_set_mismatch")
        for item in entries:
            data = actual[item["path"]]
            if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ValueError("manifest_content_mismatch")
    return {"status": "PASS", "files_in_zip": len(names), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "bytes": target.stat().st_size, "private_pdfs": 0, "model_weights": 0, "env_secrets": 0}


def package(root: Path, target: Path, *, tracked_only: bool = True) -> dict:
    root, target = root.resolve(), target.resolve()
    if target.is_relative_to(root):
        raise ValueError("ZIP output must be outside the project directory")
    payload = archive_bytes(root, tracked_only=tracked_only)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(root.name+"/"+name, date_time=(1980,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    result = audit_archive(target)
    target.with_suffix(target.suffix+".sha256").write_text(result["sha256"]+"  "+target.name+"\n", encoding="ascii")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT.parent/(ROOT.name+".zip"))
    parser.add_argument("--snapshot", action="store_true", help="package an audited non-Git source snapshot; never use on a private data root")
    parser.add_argument("--audit", type=Path, help="verify an existing source ZIP without changing it")
    args = parser.parse_args()
    result = audit_archive(args.audit) if args.audit else package(ROOT, args.output, tracked_only=not args.snapshot)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
