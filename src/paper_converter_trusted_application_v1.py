"""Application-owned current closure observation for a distinct converter attempt.

The owning application must supply an independently reviewed enrollment SHA.
This module has no CLI and never signs a reconciliation or launches a worker.
"""
from __future__ import annotations

from contextlib import contextmanager
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess

from src import paper_converter_smoke as smoke

VERSION = "paper-converter-root-enrollment-v1"
PROCESS_QUERY = r'''
$ErrorActionPreference = 'Stop'
@(Get-CimInstance Win32_Process | ForEach-Object {
  [ordered]@{
    pid = [int]$_.ProcessId
    parent_pid = [int]$_.ParentProcessId
    name = [string]$_.Name
    executable = [string]$_.ExecutablePath
    command_line = [string]$_.CommandLine
    created_at = if ($_.CreationDate) { ([datetime]$_.CreationDate).ToUniversalTime().ToString('o') } else { $null }
  }
}) | ConvertTo-Json -Compress -Depth 4
'''


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def current_processes() -> list[dict]:
    """Fail closed if Windows process visibility or serialization is incomplete."""
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                             PROCESS_QUERY], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=30, check=False)
    if result.returncode or result.stderr:
        raise RuntimeError("current Windows process census unavailable")
    try:
        raw = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError("current Windows process census malformed") from exc
    rows = [row for row in (raw if isinstance(raw, list) else [raw])
            if isinstance(row, dict) and row.get("pid") != 0]
    if not rows or any(not isinstance(row, dict) or
                       set(row) != {"pid", "parent_pid", "name", "executable",
                                    "command_line", "created_at"} for row in rows):
        raise RuntimeError("current Windows process census incomplete")
    ids = [row["pid"] for row in rows]
    if len(ids) != len(set(ids)) or any(type(pid) is not int or pid <= 0 for pid in ids):
        raise RuntimeError("current Windows process identities ambiguous")
    return rows


class RootEnrolledConverterApplication:
    """Bind externally enrolled authority to an owned, fresh process census."""

    def __init__(self, data_root: Path, enrollment_path: Path,
                 reviewed_enrollment_sha256: str):
        supplied = Path(enrollment_path)
        if not supplied.is_absolute() or not supplied.is_file():
            raise RuntimeError("absolute existing application enrollment required")
        for component in (supplied, *supplied.parents):
            if component.exists():
                state = component.lstat()
                if component.is_symlink() or \
                        (getattr(state, "st_file_attributes", 0) & 0x400):
                    raise RuntimeError("linked application enrollment forbidden")
        self.root = Path(data_root).resolve(strict=True)
        self.path = supplied.resolve(strict=True)
        if self.path.is_relative_to(self.root):
            raise RuntimeError("application enrollment must be external to trial data")
        self.reviewed_sha256 = reviewed_enrollment_sha256
        self._enrollment()

    def _enrollment(self) -> dict:
        raw = self.path.read_bytes()
        if _sha(raw) != self.reviewed_sha256:
            raise RuntimeError("root-reviewed application enrollment changed")
        body = json.loads(raw)
        required = {"version", "status", "data_root", "authority_sha256",
                    "old_registry_sha256", "old_output", "successor_plan_sha256",
                    "successor_output", "old_runtime_executable_relative",
                    "old_intent_started_at", "old_invalidation_at"}
        if (type(body) is not dict or set(body) != required or body["version"] != VERSION or
                body["status"] != "ROOT_APPROVED_DISTINCT_SUCCESSOR" or
                body["data_root"] != str(self.root) or
                not isinstance(body["old_output"], str) or
                not isinstance(body["successor_output"], str)):
            raise RuntimeError("root-reviewed application enrollment differs")
        return body

    def verify_authority(self, proof: dict) -> bool:
        body = self._enrollment()
        return (proof.get("authority_sha256") == body["authority_sha256"] and
                proof.get("old_registry_sha256") == body["old_registry_sha256"] and
                proof.get("old_output") == body["old_output"] and
                proof.get("old_runtime_executable_relative") ==
                    body["old_runtime_executable_relative"] and
                proof.get("successor_plan", {}).get("sha256") ==
                    body["successor_plan_sha256"] and
                proof.get("successor_output") == body["successor_output"] and
                proof.get("old_engine") == "docling" and
                proof.get("historical_outcome") == "UNKNOWN_UNATTESTED_NO_RETRY")

    def _observe(self, proof: dict) -> dict:
        body = self._enrollment()
        if not smoke.engine_lock_owned(self.root) or not self.verify_authority(proof):
            raise RuntimeError("owned converter engine lock or enrollment absent")
        start = smoke.stamp(body["old_intent_started_at"])
        invalidated = smoke.stamp(body["old_invalidation_at"])
        old_executable = smoke.child(self.root, body["old_runtime_executable_relative"])
        old_output = str((self.root / proof["old_output"]).resolve(strict=True)).casefold()
        rows = current_processes()
        for row in rows:
            name = row["name"].casefold()
            executable = row["executable"].casefold()
            command = row["command_line"].casefold()
            created = smoke.stamp(row["created_at"]) if row["created_at"] else None
            if row["pid"] == proof["old_controller_pid"] and \
                    (created is None or created <= invalidated):
                raise RuntimeError("original controller remains live or identity ambiguous")
            if row["parent_pid"] == proof["old_controller_pid"] and \
                    (created is None or created >= start):
                raise RuntimeError("possible original controller descendant remains")
            if name.startswith("python") and name.endswith(".exe") and \
                    (not row["executable"] or not row["command_line"] or
                     created is None):
                raise RuntimeError("Python process identity unavailable to closure observer")
            if executable == str(old_executable).casefold() or \
                    ("paper_converter_worker.py" in command and
                     (old_output in command or proof["old_output"].casefold() in command)):
                raise RuntimeError("possible original converter worker remains")
            if "paper_converter_worker.py" in command and not row["executable"]:
                raise RuntimeError("converter process visibility incomplete")
        return {"old_controller_pid": proof["old_controller_pid"],
                "old_worker_pid": proof["old_worker_pid"],
                "observed_at": smoke.now(),
                "controller_absent": True, "worker_absent": True,
                "descendants_absent": True, "provider_idle": True,
                "launch_exclusion_held": True}

    @contextmanager
    def hold_live_exclusion(self, root: Path, proof: dict):
        if Path(root).resolve(strict=True) != self.root or not self.verify_authority(proof):
            raise RuntimeError("enrolled data root or proof differs")
        observation = self._observe(proof)
        from src.paper_converter_reconciliation import verify_live_exclusion
        verify_live_exclusion(proof, observation)
        app = self
        class Exclusion:
            def reobserve(self):
                observed = app._observe(proof)
                verify_live_exclusion(proof, observed)
                return observed
        try:
            yield Exclusion()
        finally:
            # A fresh observation is required before the owner's lock releases.
            verify_live_exclusion(proof, self._observe(proof))
