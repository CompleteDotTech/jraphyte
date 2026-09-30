"""Single-owner, query-independent Docling to V4 corpus assessment producer.

Private conversion documents and per-paper receipts belong under the data root.
This module never reads queries, labels, target IDs, or graph credentials.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import ctypes
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from trace_gc.pdf_source_parallel_v4 import SourceGeometry, digest_value
from trace_gc.pdf_structure_parallel_v4 import assess_document

from .common import REPO, child, data_root, digest, method_hashes, write_once
from .fields import parse_bound_json, source_path, verify_pinned_source
from .retrieval import ASSESSMENT_VERSION, verify_source_bound_assessment
from .retrieval_policy import eligibility
from .runtime import runtime_receipt

VERSION = "retrieval-assessment-producer-v1"
ID = re.compile(r"[A-Za-z0-9_-]+\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
METHOD = "parallel_structure_v4"
CONVERTER_PACKAGES = ("docling", "docling-core", "docling-ibm-models", "rapidocr", "torch")
DEFAULT_MAX_DOCUMENTS_PER_SESSION = 64


class _FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


def _windows_process_handle(pid: int):
    """Bind a Windows process by kernel handle and exact creation time."""
    if os.name != "nt":
        return None, None
    api = ctypes.windll.kernel32
    api.OpenProcess.restype = ctypes.c_void_p
    handle = api.OpenProcess(0x00100000 | 0x1000 | 0x0001, False, pid)
    if not handle:
        raise ValueError("owned_worker_process_unavailable")
    created, exited, kernel, user = (_FileTime() for _ in range(4))
    if not api.GetProcessTimes(ctypes.c_void_p(handle), ctypes.byref(created), ctypes.byref(exited),
                               ctypes.byref(kernel), ctypes.byref(user)):
        api.CloseHandle(ctypes.c_void_p(handle))
        raise ValueError("owned_worker_process_identity_unavailable")
    return handle, (created.high << 32) | created.low


def _close_windows_handle(handle):
    if handle is not None:
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(handle))


def _terminate_windows_handle(handle) -> bool:
    """Terminate and wait on the already-open exact process, never a reused PID."""
    api = ctypes.windll.kernel32
    bound = ctypes.c_void_p(handle)
    if api.WaitForSingleObject(bound, 0) == 0:
        return True
    if not api.TerminateProcess(bound, 1):
        return False
    return api.WaitForSingleObject(bound, 10000) == 0


def _windows_handle_exited(handle) -> bool:
    return ctypes.windll.kernel32.WaitForSingleObject(ctypes.c_void_p(handle), 10000) == 0


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(path: Path, expected: str | None = None):
    raw = path.read_bytes()
    if expected is not None and _sha(raw) != expected:
        raise ValueError("producer_artifact_hash_mismatch:" + path.name)
    return parse_bound_json(raw), _sha(raw)


def _runtime() -> dict:
    return {"python": sys.version.split()[0],
            "executable_sha256": digest(Path(sys.executable)),
            "packages": {name: importlib.metadata.version(name) for name in CONVERTER_PACKAGES}}


def _profile(root: Path, profile: dict, *, verify_runtime: bool = False) -> dict:
    """Require the same pinned local CPU profile used by the converter worker."""
    if not isinstance(profile, dict) or set(profile) != {"engine", "runtime", "limits"}:
        raise ValueError("explicit_converter_profile_required")
    engine = profile["engine"]
    if not isinstance(engine, dict) or set(engine) != {"name", "revision", "device", "decoding", "assets"}:
        raise ValueError("pinned_docling_engine_required")
    if (engine["name"], engine["revision"], engine["device"]) != ("docling", "2.130.0", "cpu"):
        raise ValueError("unsupported_docling_profile")
    options = engine["decoding"]
    required = {"layout_directory", "det_model", "cls_model", "rec_model", "rec_keys", "cpu_threads"}
    if not isinstance(options, dict) or set(options) != required or options["cpu_threads"] != 4:
        raise ValueError("unsupported_docling_options")
    assets = engine["assets"]
    if not isinstance(assets, list) or not assets or len({a.get("relative") for a in assets if isinstance(a, dict)}) != len(assets):
        raise ValueError("unique_converter_assets_required")
    pinned = {}
    for asset in assets:
        if (not isinstance(asset, dict) or set(asset) != {"relative", "sha256"} or
                not isinstance(asset["sha256"], str) or not SHA.fullmatch(asset["sha256"])):
            raise ValueError("invalid_converter_asset")
        path = child(root, asset["relative"])
        if not path.is_file() or path.is_symlink() or digest(path) != asset["sha256"]:
            raise ValueError("converter_asset_missing_or_changed")
        pinned[asset["relative"]] = asset["sha256"]
    layout = child(root, options["layout_directory"])
    if (not layout.is_dir() or layout.name != "docling-project--docling-layout-heron" or
            not (layout / "model.safetensors").is_file() or
            {p.relative_to(root).as_posix() for p in layout.iterdir() if p.is_file()} - set(pinned)):
        raise ValueError("docling_layout_snapshot_not_pinned")
    if any(options[key] not in pinned for key in ("det_model", "cls_model", "rec_model", "rec_keys")):
        raise ValueError("docling_ocr_assets_not_pinned")
    runtime = profile["runtime"]
    if (not isinstance(runtime, dict) or set(runtime) != {"python", "executable", "executable_sha256", "packages"} or
            not isinstance(runtime["packages"], dict) or set(runtime["packages"]) != set(CONVERTER_PACKAGES) or
            not isinstance(runtime["executable_sha256"], str) or not SHA.fullmatch(runtime["executable_sha256"])):
        raise ValueError("explicit_converter_runtime_required")
    executable = child(root, runtime["executable"])
    if not executable.is_file() or digest(executable) != runtime["executable_sha256"]:
        raise ValueError("converter_interpreter_changed")
    if verify_runtime and {"python": runtime["python"], "executable_sha256": runtime["executable_sha256"],
                           "packages": runtime["packages"]} != _runtime():
        raise ValueError("converter_runtime_mismatch")
    limits = profile["limits"]
    if (not isinstance(limits, dict) or set(limits) != {"timeout_seconds", "max_document_bytes", "max_attempts"} or
            type(limits["timeout_seconds"]) is not int or not 1 <= limits["timeout_seconds"] <= 3600 or
            type(limits["max_document_bytes"]) is not int or not 1 <= limits["max_document_bytes"] <= 16 * 1024**2 or
            limits["max_attempts"] != 1):
        raise ValueError("bounded_single_converter_attempt_required")
    return profile


@contextmanager
def _owner(path: Path):
    """OS-held lock. An interrupted worker is reconciled separately."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            handle.write(b"\0"); handle.flush(); handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError("assessment_producer_already_owned") from exc
            try:
                yield
            finally:
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ValueError("assessment_producer_already_owned") from exc
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _freeze(root: Path, manifest_path: Path, profile_path: Path, output: Path,
            source_root: Path | None, *, selected_ids: list[str] | None = None,
            migration: dict | None = None,
            max_documents_per_session: int = DEFAULT_MAX_DOCUMENTS_PER_SESSION) -> tuple[dict, dict]:
    if type(max_documents_per_session) is not int or not 1 <= max_documents_per_session <= 256:
        raise ValueError("bounded_converter_session_limit_required")
    manifest, manifest_hash = _read(manifest_path)
    profile, profile_hash = _read(profile_path)
    _profile(root, profile)
    rows = manifest.get("pdfs")
    if (manifest.get("stage") != "retrieval_source_first_no_predictions" or
            manifest.get("query_independent") is not True or
            any(key in manifest for key in ("queries", "query", "targets", "target_id", "labels")) or
            not isinstance(rows, list) or not rows):
        raise ValueError("retrieval_preparation_manifest_required")
    ids = [r.get("sample_id") for r in rows if isinstance(r, dict)]
    if len(ids) != len(rows) or len(ids) != len(set(ids)) or not all(isinstance(x, str) and ID.fullmatch(x) for x in ids):
        raise ValueError("exact_unique_manifest_ids_required")
    if any(any(key in row for key in ("query", "queries", "target", "target_id", "labels")) for row in rows):
        raise ValueError("query_or_target_dependent_source_row_forbidden")
    if selected_ids is not None:
        if not selected_ids or len(selected_ids) != len(set(selected_ids)) or not set(selected_ids) <= set(ids):
            raise ValueError("invalid_exposed_smoke_selection")
        ids = [sid for sid in ids if sid in set(selected_ids)]
    code = method_hashes(REPO)
    evaluator = runtime_receipt()
    protocol = {"schema_version": VERSION, "manifest_relative": manifest_path.relative_to(root).as_posix(),
                "manifest_sha256": manifest_hash, "profile_relative": profile_path.relative_to(root).as_posix(),
                "profile_sha256": profile_hash, "source_root": str(source_root.resolve()) if source_root else None,
                "ids": ids, "scope": "EXPOSED_SMOKE" if selected_ids is not None else "FULL_CORPUS",
                "code_sha256": code, "evaluator_runtime": evaluator,
                "source_geometry_policy": "source_fraction_v1",
                "scholarly_abstract": "disabled_no_gold_or_labels", "query_independent": True,
                "assessment_method": METHOD, "extractor_version": ASSESSMENT_VERSION}
    protocol["converter_session"] = {"max_documents": max_documents_per_session,
                                      "drain": "external_request_after_verified_row_v1",
                                      "drain_timeout_seconds": 30}
    if migration is not None:
        if (not isinstance(migration, dict) or set(migration) != {"relative", "sha256"} or
                digest(child(root, migration["relative"])) != migration["sha256"]):
            raise ValueError("assessment_migration_manifest_mismatch")
        protocol["migration"] = migration
    path = output / "protocol.json"
    if path.exists():
        if _read(path)[0] != protocol:
            raise ValueError("assessment_producer_protocol_changed")
    else:
        output.mkdir(parents=True, exist_ok=False)
        write_once(path, protocol)
    return manifest, protocol


def _verified_row(root: Path, row: dict, source_root: Path | None):
    if row.get("physical_page") != 1:
        raise ValueError("first_physical_page_required")
    native, page_size, page_cache = verify_pinned_source(root, row, source_root)
    decision = eligibility(row, native, page_cache)["abstract"]
    if decision not in {"eligible", "native_error", "page_mismatch", "empty_native"}:
        raise ValueError("unexpected_eligibility_state")
    return native, page_size, decision


def _check_code(protocol: dict):
    if method_hashes(REPO) != protocol["code_sha256"]:
        raise ValueError("assessment_producer_code_changed")
    if runtime_receipt() != protocol["evaluator_runtime"]:
        raise ValueError("assessment_evaluator_runtime_changed")


class ConverterSession:
    """One owned CPU worker with a protocol-bounded document residence."""

    def __init__(self, root: Path, output: Path, profile: dict):
        self.root, self.output, self.profile = root, output, profile
        self.process = None
        self.log = None
        self.documents = 0
        self.last_drain_receipt = None
        self.worker_pid = None
        self.session_start = None
        self.worker_handle = None
        self.worker_created_ticks = None

    def _launch_hold(self, launch_id: str, reason: str):
        write_once(self.output / "sessions" / "launch-failures" / (launch_id + ".json"),
                   {"status": "HOLD_OWNED_CONVERTER_LAUNCH_UNKNOWN", "reason": reason,
                    "launch_id": launch_id, "launcher_pid": self.process.pid if self.process else None,
                    "worker_pid": self.worker_pid, "session_start": self.session_start,
                    "protocol_sha256": digest(self.output / "protocol.json")})
        raise ValueError(reason)

    def _drain_timeout(self) -> int:
        protocol, _ = _read(self.output / "protocol.json")
        session = protocol.get("converter_session")
        if (not isinstance(session, dict) or session.get("drain") !=
                "external_request_after_verified_row_v1" or
                type(session.get("drain_timeout_seconds")) is not int or
                not 1 <= session["drain_timeout_seconds"] <= 60):
            raise ValueError("converter_drain_protocol_changed")
        return session["drain_timeout_seconds"]

    def _start(self):
        if self.process is not None:
            return
        path = self.output / "converter-session.log"
        self.log = path.open("ab")
        launch_id = uuid.uuid4().hex
        command = [str(child(self.root, self.profile["runtime"]["executable"])), "-B", "-s", "-m",
                   "src.parallel_source_v4.assessment_producer", "convert-session", "--data-root", str(self.root),
                   "--output", self.output.relative_to(self.root).as_posix(), "--launch-id", launch_id]
        self.process = subprocess.Popen(command, cwd=REPO, stdin=subprocess.PIPE,
                                        stdout=self.log, stderr=self.log, bufsize=0)
        launch = self.output / "sessions" / "launches" / (launch_id + ".json")
        deadline = time.monotonic() + self.profile["limits"]["timeout_seconds"]
        while time.monotonic() < deadline:
            if launch.is_file():
                body, _ = _read(launch)
                if (body.get("launch_id") != launch_id or
                        not (body.get("launcher_pid") == self.process.pid or
                             body.get("worker_pid") == self.process.pid) or
                        body.get("protocol_sha256") != digest(self.output / "protocol.json") or
                        type(body.get("worker_pid")) is not int or
                        not isinstance(body.get("session_start"), dict) or
                        set(body["session_start"]) != {"relative", "sha256"}):
                    self._launch_hold(launch_id, "converter_launch_identity_mismatch")
                start = body["session_start"]
                start_body, _ = _read(child(self.root, start["relative"]), start["sha256"])
                if (start_body.get("worker_pid") != body["worker_pid"] or
                        start_body.get("launcher_pid") != body["launcher_pid"] or
                        start_body.get("process_created_ticks") != body.get("process_created_ticks") or
                        start_body.get("protocol_sha256") != body["protocol_sha256"] or
                        start_body.get("converter_profile_sha256") !=
                        _read(self.output / "protocol.json")[0]["profile_sha256"]):
                    self._launch_hold(launch_id, "converter_launch_session_start_mismatch")
                try:
                    handle, ticks = _windows_process_handle(body["worker_pid"])
                except ValueError:
                    self._launch_hold(launch_id, "converter_launch_process_unavailable")
                if os.name == "nt" and ticks != body.get("process_created_ticks"):
                    _close_windows_handle(handle)
                    self._launch_hold(launch_id, "converter_launch_process_replaced")
                self.worker_pid, self.session_start = body["worker_pid"], body["session_start"]
                self.worker_handle, self.worker_created_ticks = handle, ticks
                return
            if self.process.poll() is not None:
                self._launch_hold(launch_id, "converter_launch_exited_without_identity")
            time.sleep(0.1)
        self._launch_hold(launch_id, "converter_launch_identity_timeout")

    def convert(self, sid: str, result_path: Path) -> int:
        self._start()
        if self.process.poll() is not None:
            return self.process.returncode
        self.process.stdin.write((json.dumps({"sample_id": sid}) + "\n").encode("utf-8"))
        self.process.stdin.flush()
        deadline = time.monotonic() + self.profile["limits"]["timeout_seconds"]
        while time.monotonic() < deadline:
            if result_path.is_file():
                conversion, _ = _read(result_path)
                pid, start = conversion.get("worker_pid"), conversion.get("session_start")
                if (type(pid) is not int or pid <= 0 or not isinstance(start, dict) or
                        set(start) != {"relative", "sha256"} or
                        (self.worker_pid is not None and (pid != self.worker_pid or start != self.session_start))):
                    raise ValueError("converter_session_worker_identity_changed")
                self.worker_pid, self.session_start = pid, start
                self.documents += 1
                return 0
            code = self.process.poll()
            if code is not None:
                return code or 1
            time.sleep(0.1)
        self.close(force=True)
        return 124

    def close(self, *, force: bool = False):
        process = self.process
        proven_exit = False
        try:
            if process is None:
                proven_exit = True
                return
            if force:
                if os.name == "nt":
                    if self.worker_handle is None or self.worker_pid is None:
                        raise ValueError("converter_worker_identity_unknown_no_safe_kill")
                    if not _terminate_windows_handle(self.worker_handle):
                        raise ValueError("converter_worker_exit_unproven")
                if process.poll() is None:
                    process.kill()  # only the launcher started by this controller
                process.wait(timeout=10)
                proven_exit = True
                write_once(self.output / "sessions" / "drains" / (uuid.uuid4().hex + "-forced.json"),
                           {"status": "OWNED_WORKER_TERMINATED_AFTER_UNKNOWN_CONVERSION",
                            "worker_pid": self.worker_pid, "session_start": self.session_start,
                            "launcher_pid": process.pid,
                            "protocol_sha256": digest(self.output / "protocol.json")})
                return
            if process.poll() is not None:
                raise ValueError("converter_drain_outcome_unknown")
            if os.name == "nt" and self.worker_handle is None:
                raise ValueError("converter_worker_identity_unknown_no_safe_drain")
            nonce = uuid.uuid4().hex
            receipt = self.output / "sessions" / "drains" / (nonce + ".json")
            drain_timeout = self._drain_timeout()
            try:
                process.stdin.write((json.dumps({"drain": nonce}) + "\n").encode())
                process.stdin.flush()
                process.wait(timeout=drain_timeout)
            except (BrokenPipeError, subprocess.TimeoutExpired) as exc:
                self.close(force=True)
                raise ValueError("converter_drain_outcome_unknown") from exc
            if process.returncode != 0 or not receipt.is_file():
                raise ValueError("converter_drain_outcome_unknown")
            if os.name == "nt" and not _windows_handle_exited(self.worker_handle):
                raise ValueError("converter_worker_exit_unproven")
            outcome, _ = _read(receipt)
            if (outcome.get("nonce") != nonce or outcome.get("documents") != self.documents or
                    outcome.get("protocol_sha256") != digest(self.output / "protocol.json") or
                    not isinstance(outcome.get("session_start"), dict) or
                    set(outcome["session_start"]) != {"relative", "sha256"}):
                raise ValueError("converter_drain_receipt_mismatch")
            start = outcome["session_start"]
            start_path = child(self.root, start["relative"])
            if (digest(start_path) != start["sha256"] or
                    _read(start_path)[0].get("worker_pid") != outcome.get("worker_pid") or
                    (self.worker_pid is not None and
                     (outcome["worker_pid"] != self.worker_pid or start != self.session_start))):
                raise ValueError("converter_drain_session_identity_mismatch")
            self.last_drain_receipt = {"relative": receipt.relative_to(self.root).as_posix(),
                                       "sha256": digest(receipt)}
            proven_exit = True
        finally:
            if proven_exit:
                self.process = None
                _close_windows_handle(self.worker_handle)
                self.worker_handle = None
                if self.log is not None:
                    self.log.close(); self.log = None


def _external_drain(output: Path, protocol: dict, session: ConverterSession,
                    last_verified: Path | None = None) -> bool:
    """Honor an external write-once request at a verified row boundary."""
    requests = output / "control" / "drain-requests"
    candidates = sorted(requests.glob("*.json")) if requests.exists() else []
    ack_paths = sorted((output / "control").glob("drain-ack-*.json"))
    if not candidates and not ack_paths:
        return False
    request_ids = {path.stem for path in candidates}
    if any(not re.fullmatch(r"[a-f0-9]{32}\.json", path.name) for path in candidates):
        raise ValueError("invalid_external_drain_request_name")
    if any(not re.fullmatch(r"drain-ack-[a-f0-9]{32}\.json", path.name) or
           path.stem.removeprefix("drain-ack-") not in request_ids for path in ack_paths):
        raise ValueError("orphan_external_drain_ack")
    pending = []
    for request in candidates:
        body, request_sha = _read(request)
        if (not isinstance(body, dict) or set(body) != {"version", "request_id", "protocol_sha256", "requested_at"} or
                body["version"] != "assessment-graceful-drain-v1" or
                body["request_id"] != request.stem or
                body["protocol_sha256"] != digest(output / "protocol.json") or
                not isinstance(body["requested_at"], str) or not body["requested_at"]):
            raise ValueError("invalid_external_drain_request")
        ack = output / "control" / ("drain-ack-" + body["request_id"] + ".json")
        if not ack.exists():
            pending.append((body, request_sha, ack))
            continue
        prior, _ = _read(ack)
        if (prior.get("version") != "assessment-graceful-drain-ack-v1" or
                prior.get("status") != "STOPPED_DRAINED" or
                prior.get("request_sha256") != request_sha or
                prior.get("protocol_sha256") != body["protocol_sha256"]):
            raise ValueError("external_drain_request_changed")
        if prior.get("last_verified_row") is not None:
            if (not isinstance(prior["last_verified_row"], str) or
                    not re.fullmatch(r"[A-Za-z0-9_-]+\.json", prior["last_verified_row"])):
                raise ValueError("external_drain_row_name_invalid")
            row = output / "rows" / prior["last_verified_row"]
            if (not row.is_file() or digest(row) != prior.get("last_verified_row_sha256")):
                raise ValueError("external_drain_row_changed")
        if prior.get("child_drain") is not None:
            drained = prior["child_drain"]
            if digest(child(session.root, drained["relative"])) != drained["sha256"]:
                raise ValueError("external_drain_child_receipt_changed")
    if len(pending) > 1:
        raise ValueError("multiple_pending_external_drains")
    if not pending:
        return False
    body, request_sha, ack = pending[0]
    if last_verified is not None and not last_verified.is_file():
        raise ValueError("external_drain_without_verified_row")
    session.close()
    write_once(ack, {"version": "assessment-graceful-drain-ack-v1", "request_sha256": request_sha,
                     "protocol_sha256": body["protocol_sha256"],
                     "last_verified_row": last_verified.name if last_verified else None,
                     "last_verified_row_sha256": digest(last_verified) if last_verified else None,
                     "child_drain": session.last_drain_receipt,
                     "status": "STOPPED_DRAINED"})
    return True


def _attempt(root: Path, output: Path, row: dict, profile: dict, protocol: dict,
             source_root: Path | None, native: list[dict], page_size: list[float],
             session: ConverterSession) -> dict:
    sid = row["sample_id"]
    folder = output / "attempts" / sid
    if folder.exists():
        if not (folder / "intent.json").is_file():
            raise ValueError("unsealed_converter_attempt_requires_reconciliation:" + sid)
        intent, _ = _read(folder / "intent.json")
        if (intent.get("sample_id") != sid or intent.get("protocol_sha256") != digest(output / "protocol.json") or
                any(intent.get(key + "_sha256") != row[key + "_sha256"] for key in ("source", "page", "image", "native"))):
            raise ValueError("interrupted_attempt_identity_mismatch")
        if not (folder / "conversion.json").is_file():
            raise ValueError("unsealed_converter_attempt_requires_reconciliation:" + sid)
        returncode = 0
    else:
        folder.mkdir(parents=True, exist_ok=False)
        intent = {"schema_version": "retrieval-docling-attempt-v1", "sample_id": sid,
                  "protocol_sha256": digest(output / "protocol.json"),
                  "source_sha256": row["source_sha256"], "page_sha256": row["page_sha256"],
                  "image_sha256": row["image_sha256"], "native_sha256": row["native_sha256"],
                  "controller_pid": os.getpid(), "started_ns": time.time_ns()}
        write_once(folder / "intent.json", intent)
        started = time.perf_counter()
        returncode = session.convert(sid, folder / "conversion.json")
        if not (folder / "conversion.json").is_file():
            write_once(folder / "worker-failure.json", {"status": "UNKNOWN_CONVERSION_OUTCOME",
                "returncode": returncode, "wall_seconds": time.perf_counter() - started,
                "intent_sha256": digest(folder / "intent.json")})
            raise ValueError("unsealed_converter_attempt_requires_reconciliation:" + sid)
    result_path = folder / "conversion.json"
    if result_path.is_file():
        conversion, conversion_hash = _read(result_path)
        worker = set(conversion) == {"status", "docling_status", "document_sha256", "worker_pid", "runtime", "session_start", "wall_seconds", "peak_process_memory_bytes", "error_class", "model_called"}
        if (not worker or conversion.get("status") not in {"success", "error"} or
                conversion.get("model_called") is not True or
                conversion.get("runtime") != {k: profile["runtime"][k] for k in ("python", "executable_sha256", "packages")} or
                type(conversion.get("worker_pid")) is not int):
            raise ValueError("invalid_converter_result_status")
        if conversion.get("status") == "success" and returncode != 0:
            raise ValueError("converter_exit_status_conflict")
    else:
        raise ValueError("converter_result_missing_after_attempt")
    wall = conversion["wall_seconds"]
    document_path = folder / "document.json"
    if conversion.get("document_sha256") is not None:
        document, document_hash = _read(document_path, conversion["document_sha256"])
    else:
        document, document_hash = {}, None
        if document_path.exists():
            raise ValueError("unbound_converter_document")
    if conversion["status"] == "success" and document_hash is None:
        raise ValueError("successful_converter_document_missing")
    _check_code(protocol)
    current, current_size, current_decision = _verified_row(root, row, source_root)
    if (current_decision != "eligible" or current_size != page_size or digest_value(current) != digest_value(native)):
        raise ValueError("source_changed_during_conversion")
    geometry = SourceGeometry.from_pdf(source_path(root, row, source_root).read_bytes(), native,
                                       expected_source_sha256=row["source_sha256"])
    assessment = assess_document(document, page_size=page_size,
        source_sha256=row["source_sha256"], page_sha256=row["page_sha256"],
        native_lines=native, scholarly_abstract="", max_input_chars=4000,
        conversion_status=conversion["status"], source_geometry=geometry)
    assessment["source_hash_verification"] = "verified_original_page_native_image_before_and_after_conversion"
    assessment["conversion_stage"] = {"status": conversion["status"],
        "input_hashes": {"docling": conversion_hash,
                         **({"docling_document": document_hash} if document_hash else {})},
        "new_model_conversion": True, "attempt_sha256": digest(folder / "intent.json"),
        "session_start": conversion.get("session_start"),
        "converter_profile_sha256": protocol["profile_sha256"], "wall_seconds": wall}
    from trace_gc.pdf_structure_parallel_v4 import seal
    assessment = seal(assessment)
    verify_source_bound_assessment(assessment, native, page_size=page_size,
        source_sha256=row["source_sha256"], page_sha256=row["page_sha256"], source_geometry=geometry)
    assessment_path = output / "assessments" / METHOD / (sid + ".json")
    assessment_hash = write_once(assessment_path, assessment)
    return {"state": "complete" if conversion["status"] == "success" else "error",
            "assessment_relative": assessment_path.relative_to(root).as_posix(),
            "assessment_sha256": assessment_hash, "conversion_relative": result_path.relative_to(root).as_posix(),
            "conversion_sha256": conversion_hash, "document_sha256": document_hash,
            "wall_seconds": wall, "assessment_status": assessment["status"]}


def _verify_receipt(root: Path, row: dict, receipt: dict, output: Path, source_root: Path | None,
                    protocol: dict) -> None:
    sid = row["sample_id"]
    if receipt.get("sample_id") != sid or receipt.get("protocol_sha256") != digest(output / "protocol.json"):
        raise ValueError("assessment_receipt_identity_mismatch:" + sid)
    native, size, decision = _verified_row(root, row, source_root)
    if receipt.get("source_hashes") != {key: row[key + "_sha256"] for key in ("source", "page", "image", "native")}:
        raise ValueError("assessment_receipt_source_mismatch:" + sid)
    if decision != receipt.get("eligibility"):
        raise ValueError("assessment_receipt_eligibility_mismatch:" + sid)
    if decision != "eligible":
        if receipt.get("state") != "ineligible" or receipt.get("assessment_relative") is not None:
            raise ValueError("ineligible_assessment_receipt_invalid:" + sid)
        return
    if receipt.get("schema_version") == "retrieval-assessment-migrated-row-v1":
        from .assessment_migration import verify_migrated_receipt
        verify_migrated_receipt(root, row, receipt, output, source_root, protocol, native, size)
        return
    if receipt.get("schema_version") not in (None, "retrieval-assessment-row-v1"):
        raise ValueError("assessment_receipt_schema_unknown:" + sid)
    if receipt.get("state") not in {"complete", "error"}:
        raise ValueError("eligible_assessment_receipt_invalid:" + sid)
    attempt = output / "attempts" / sid
    intent, _ = _read(attempt / "intent.json")
    conversion, conversion_hash = _read(child(root, receipt["conversion_relative"]), receipt["conversion_sha256"])
    if (intent.get("sample_id") != sid or intent.get("protocol_sha256") != receipt["protocol_sha256"] or
            conversion_hash != receipt["conversion_sha256"] or
            conversion.get("status") != ("success" if receipt["state"] == "complete" else "error")):
        raise ValueError("assessment_converter_lineage_mismatch:" + sid)
    worker_keys = {"status", "docling_status", "document_sha256", "worker_pid", "runtime", "session_start", "wall_seconds", "peak_process_memory_bytes", "error_class", "model_called"}
    if (set(conversion) != worker_keys or conversion.get("model_called") is not True or
            (conversion["status"] == "success" and conversion["error_class"] is not None) or
            receipt.get("document_sha256") != conversion.get("document_sha256") or
            receipt.get("wall_seconds") != conversion.get("wall_seconds")):
        raise ValueError("assessment_converter_receipt_shape_mismatch:" + sid)
    descriptor = conversion["session_start"]
    if (not isinstance(descriptor, dict) or set(descriptor) != {"relative", "sha256"} or
            not isinstance(descriptor["sha256"], str) or not SHA.fullmatch(descriptor["sha256"])):
        raise ValueError("converter_session_start_descriptor_invalid:" + sid)
    start, _ = _read(child(root, descriptor["relative"]), descriptor["sha256"])
    if (start.get("schema_version") != "retrieval-docling-session-start-v1" or
            start.get("protocol_sha256") != receipt["protocol_sha256"] or
            start.get("converter_profile_sha256") != protocol["profile_sha256"] or
            start.get("worker_pid") != conversion["worker_pid"] or
            start.get("runtime") != conversion["runtime"] or
            start.get("code_sha256") != protocol["code_sha256"] or
            start.get("network_guard") != "nonlocal_connect_denied"):
        raise ValueError("converter_session_start_lineage_mismatch:" + sid)
    if conversion.get("status") == "success" and (set(conversion) != worker_keys or
            conversion.get("docling_status") != "ConversionStatus.SUCCESS" or
            conversion.get("runtime") != {k: _read(child(root, protocol["profile_relative"]))[0]["runtime"][k]
                                          for k in ("python", "executable_sha256", "packages")} or
            type(conversion.get("worker_pid")) is not int):
        raise ValueError("assessment_converter_success_not_authenticated:" + sid)
    if conversion["document_sha256"] is not None:
        document, _ = _read(attempt / "document.json", conversion["document_sha256"])
        if conversion["status"] == "success":
            from .extraction import validate_cached_input
            validate_cached_input("docling_document", document, page_size=size)
    elif (attempt / "document.json").exists():
        raise ValueError("unbound_converter_document:" + sid)
    assessment, _ = _read(child(root, receipt["assessment_relative"]), receipt["assessment_sha256"])
    if (assessment.get("conversion_stage", {}).get("input_hashes", {}).get("docling") != conversion_hash or
            assessment.get("conversion_stage", {}).get("attempt_sha256") != digest(attempt / "intent.json") or
            assessment.get("conversion_stage", {}).get("converter_profile_sha256") != protocol["profile_sha256"] or
            assessment.get("conversion_stage", {}).get("session_start") != conversion.get("session_start") or
            assessment.get("status") != receipt.get("assessment_status") or
            assessment.get("conversion_stage", {}).get("input_hashes", {}).get("docling_document") != conversion.get("document_sha256")):
        raise ValueError("assessment_converter_provenance_mismatch:" + sid)
    geometry = SourceGeometry.from_pdf(source_path(root, row, source_root).read_bytes(), native,
                                       expected_source_sha256=row["source_sha256"])
    verify_source_bound_assessment(assessment, native, page_size=size,
        source_sha256=row["source_sha256"], page_sha256=row["page_sha256"], source_geometry=geometry)


def _run(root: Path, manifest_path: Path, profile_path: Path, output: Path,
         source_root: Path | None, selected_ids: list[str] | None = None,
         *, migration: dict | None = None, migration_initializer=None,
         max_documents_per_session: int = DEFAULT_MAX_DOCUMENTS_PER_SESSION) -> dict:
    with _owner(output.parent / ("." + output.name + ".owner.lock")):
        manifest, protocol = _freeze(root, manifest_path, profile_path, output, source_root,
                                     selected_ids=selected_ids, migration=migration,
                                     max_documents_per_session=max_documents_per_session)
        if migration_initializer is not None:
            if migration is None:
                raise ValueError("assessment_migration_manifest_required")
            migration_initializer(root, output, manifest, protocol, source_root)
        profile, _ = _read(profile_path, protocol["profile_sha256"])
        rows = {r["sample_id"]: r for r in manifest["pdfs"]}
        session = ConverterSession(root, output, profile)
        last_verified = None
        if (output / "control" / "drain-requests").exists():
            saw_gap = False
            for prior_id in protocol["ids"]:
                prior_path = output / "rows" / (prior_id + ".json")
                if prior_path.is_file():
                    if saw_gap:
                        raise ValueError("external_drain_noncontiguous_completed_rows")
                    _verify_receipt(root, rows[prior_id], _read(prior_path)[0],
                                    output, source_root, protocol)
                    last_verified = prior_path
                else:
                    saw_gap = True
        try:
            for sid in protocol["ids"]:
                if _external_drain(output, protocol, session, last_verified):
                    return {"status": "STOPPED_DRAINED", "document_count": len(protocol["ids"]),
                            "eligible_count": None, "state_counts": {}}
                _check_code(protocol)
                row = rows[sid]
                receipt_path = output / "rows" / (sid + ".json")
                if receipt_path.is_file():
                    _verify_receipt(root, row, _read(receipt_path)[0], output, source_root, protocol)
                    last_verified = receipt_path
                    continue
                native, size, decision = _verified_row(root, row, source_root)
                data = {"schema_version": "retrieval-assessment-row-v1", "sample_id": sid,
                        "protocol_sha256": digest(output / "protocol.json"), "eligibility": decision,
                        "source_hashes": {key: row[key + "_sha256"] for key in ("source", "page", "image", "native")}}
                if decision == "eligible":
                    data.update(_attempt(root, output, row, profile, protocol, source_root, native, size, session))
                else:
                    data.update(state="ineligible", assessment_relative=None, assessment_sha256=None)
                write_once(receipt_path, data)
                _verify_receipt(root, row, data, output, source_root, protocol)
                last_verified = receipt_path
                if session.documents == protocol["converter_session"]["max_documents"]:
                    session.close()
                    session = ConverterSession(root, output, profile)
            if _external_drain(output, protocol, session, last_verified):
                return {"status": "STOPPED_DRAINED", "document_count": len(protocol["ids"]),
                        "eligible_count": None, "state_counts": {}}
        finally:
            original_error = sys.exception()
            try:
                session.close()
            except Exception as shutdown_error:
                failure = {"status": "HOLD_OWNED_CONVERTER_SHUTDOWN_UNKNOWN",
                           "primary_error_class": type(original_error).__name__ if original_error else None,
                           "shutdown_error_class": type(shutdown_error).__name__,
                           "worker_pid": session.worker_pid,
                           "session_start": session.session_start,
                           "launcher_pid": session.process.pid if session.process else None,
                           "protocol_sha256": digest(output / "protocol.json")}
                write_once(output / "sessions" / "shutdown-failures" / (uuid.uuid4().hex + ".json"), failure)
                if original_error is not None:
                    group = ExceptionGroup if isinstance(original_error, Exception) else BaseExceptionGroup
                    raise group("assessment and converter shutdown both failed",
                                [original_error, shutdown_error])
                raise
        _profile(root, profile)
        return _finalize(root, manifest, protocol, output, source_root)


def _finalize(root: Path, manifest: dict, protocol: dict, output: Path,
              source_root: Path | None) -> dict:
    _check_code(protocol)
    rows = {r["sample_id"]: r for r in manifest["pdfs"]}
    receipts = []
    for sid in protocol["ids"]:
        receipt, receipt_hash = _read(output / "rows" / (sid + ".json"))
        _verify_receipt(root, rows[sid], receipt, output, source_root, protocol)
        receipts.append((receipt, receipt_hash))
    entries = [{"sample_id": r["sample_id"], "assessment_relative": r["assessment_relative"],
                "assessment_sha256": r["assessment_sha256"],
                "native_sha256": rows[r["sample_id"]]["native_sha256"]}
               for r, _ in receipts if r["eligibility"] == "eligible"]
    mapping = {"schema_version": "retrieval-assessment-map-v1", "method": METHOD,
               "extractor_version": ASSESSMENT_VERSION, "entries": entries}
    map_hash = write_once(output / "assessment-map.json", mapping)
    summary = {"schema_version": "retrieval-assessment-ledger-v1", "status": "COMPLETE",
               "scope": protocol["scope"],
               "protocol_sha256": digest(output / "protocol.json"), "assessment_map_sha256": map_hash,
               "document_count": len(receipts), "eligible_count": len(entries),
               "eligibility_counts": dict(sorted(Counter(r["eligibility"] for r, _ in receipts).items())),
               "state_counts": dict(sorted(Counter(r["state"] for r, _ in receipts).items())),
               "row_receipt_sha256": {r["sample_id"]: h for r, h in receipts},
               "query_independent": True, "graph_admission_enabled": False,
               "new_paid_api_calls": 0, "production_graph_writes": 0}
    write_once(output / "ledger.json", summary)
    if _read(output / "ledger.json")[0] != summary or _read(output / "assessment-map.json")[0] != mapping:
        raise ValueError("final_assessment_readback_mismatch")
    return summary


def _docling_converter(root: Path, profile: dict):
    """Build the same offline CPU Heron/RapidOCR pipeline as paper_converter_worker."""
    import torch
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions, LayoutOptions
    from docling.datamodel.layout_model_specs import LayoutModelConfig
    from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice

    options = profile["engine"]["decoding"]
    torch.set_num_threads(4)
    opts = PdfPipelineOptions(do_ocr=True, do_table_structure=False,
                              enable_remote_services=False, allow_external_plugins=False)
    opts.ocr_options = RapidOcrOptions(backend="torch", lang=["ch"],
        det_model_path=str(child(root, options["det_model"])),
        cls_model_path=str(child(root, options["cls_model"])),
        rec_model_path=str(child(root, options["rec_model"])),
        rec_keys_path=str(child(root, options["rec_keys"])))
    opts.artifacts_path = child(root, options["layout_directory"]).parent
    opts.layout_options = LayoutOptions(model_spec=LayoutModelConfig(name="pinned_local_heron",
        repo_id="docling-project/docling-layout-heron",
        revision="8f39ad3c0b4c58e9c2d2c84a38465abf757272d8"))
    opts.accelerator_options = AcceleratorOptions(num_threads=4, device=AcceleratorDevice.CPU)
    opts.document_timeout = min(180, profile["limits"]["timeout_seconds"])
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def _session_start(root: Path, output: Path, protocol: dict, profile: dict) -> dict:
    folder = output / "sessions" / uuid.uuid4().hex
    own_handle, created_ticks = _windows_process_handle(os.getpid())
    _close_windows_handle(own_handle)
    started = {"schema_version": "retrieval-docling-session-start-v1",
               "protocol_sha256": digest(output / "protocol.json"),
               "converter_profile_sha256": protocol["profile_sha256"],
               "runtime": _runtime(), "worker_pid": os.getpid(),
               "started_ns": time.time_ns(), "network_guard": "nonlocal_connect_denied",
               "launcher_pid": os.getppid(), "process_created_ticks": created_ticks,
               "code_sha256": protocol["code_sha256"]}
    start_path = folder / "start.json"
    start_sha = write_once(start_path, started)
    return {"relative": start_path.relative_to(root).as_posix(), "sha256": start_sha}


def _convert_one(root: Path, output: Path, sid: str, converter=None, session_start=None) -> None:
    """Convert one hash-checked first page under an owned local worker."""
    protocol, _ = _read(output / "protocol.json")
    if sid not in protocol["ids"]:
        raise ValueError("worker_id_not_in_frozen_protocol")
    if method_hashes(REPO) != protocol["code_sha256"]:
        raise ValueError("assessment_worker_code_changed")
    source_manifest, _ = _read(child(root, protocol["manifest_relative"]), protocol["manifest_sha256"])
    row = next(r for r in source_manifest["pdfs"] if r["sample_id"] == sid)
    profile, _ = _read(child(root, protocol["profile_relative"]), protocol["profile_sha256"])
    if converter is None:
        _profile(root, profile, verify_runtime=True)
    source_root = Path(protocol["source_root"]) if protocol["source_root"] else None
    for key in ("source", "page", "image", "native"):
        path = source_path(root, row, source_root) if key == "source" else child(root, row[key + "_relative"])
        if digest(path) != row[key + "_sha256"]:
            raise ValueError("worker_source_asset_changed:" + key)
    folder = output / "attempts" / sid
    intent, _ = _read(folder / "intent.json")
    if intent.get("sample_id") != sid or intent.get("protocol_sha256") != digest(output / "protocol.json"):
        raise ValueError("worker_intent_mismatch")
    if (folder / "conversion.json").exists() or (folder / "document.json").exists():
        raise ValueError("worker_attempt_not_fresh")
    from src.paper_converter_worker import _docling, _network_guard, process_peak_memory
    page = child(root, row["page_relative"]).read_bytes()
    if _sha(page) != row["page_sha256"]:
        raise ValueError("worker_page_hash_mismatch")
    worker_plan = {"limits": {"timeout_seconds": profile["limits"]["timeout_seconds"]}}
    if converter is None:
        _network_guard("docling")
        session_start = _session_start(root, output, protocol, profile)
    if not isinstance(session_start, dict) or set(session_start) != {"relative", "sha256"}:
        raise ValueError("converter_session_start_required")
    started = time.perf_counter()
    model_called = False
    try:
        if converter is None:
            model_called = True
            outputs, raw, status, _ = _docling(root, profile["engine"]["decoding"], page, worker_plan)
        else:
            import io
            from docling.datamodel.base_models import DocumentStream
            request = DocumentStream(name="page.pdf", stream=io.BytesIO(page))
            model_called = True
            converted = converter.convert(request)
            status = "success" if str(converted.status) == "ConversionStatus.SUCCESS" else "error"
            outputs = {"docling": {"status": str(converted.status)},
                       "docling_document": converted.document.model_dump(mode="json")}
            from trace_gc.pdf_source_parallel_v4 import json_bytes
            raw = json_bytes(outputs["docling_document"])
        error_class = None
    except Exception as exc:
        if not model_called:
            raise
        status, raw, error_class = "error", b"", type(exc).__name__
        outputs = {"docling": {"status": "ConversionStatus.ERROR"}}
    if len(raw) > profile["limits"]["max_document_bytes"]:
        status, error_class = "error", "OutputLimit"
        outputs.pop("docling_document", None)
    if "docling_document" in outputs:
        document_hash = write_once(folder / "document.json", outputs["docling_document"])
    else:
        document_hash = None
    if converter is None:
        _profile(root, profile, verify_runtime=True)
    if method_hashes(REPO) != protocol["code_sha256"]:
        raise ValueError("assessment_worker_code_changed")
    if digest(child(root, row["page_relative"])) != row["page_sha256"]:
        raise ValueError("worker_page_changed_during_conversion")
    write_once(folder / "conversion.json", {"status": status,
        "docling_status": outputs["docling"]["status"], "document_sha256": document_hash,
        "worker_pid": os.getpid(), "runtime": _runtime(),
        "session_start": session_start,
        "model_called": model_called, "error_class": error_class,
        "wall_seconds": time.perf_counter() - started,
        "peak_process_memory_bytes": process_peak_memory()})


def _convert_session(root: Path, output: Path, launch_id: str) -> None:
    protocol, _ = _read(output / "protocol.json")
    if method_hashes(REPO) != protocol["code_sha256"]:
        raise ValueError("assessment_worker_code_changed")
    profile, _ = _read(child(root, protocol["profile_relative"]), protocol["profile_sha256"])
    _profile(root, profile, verify_runtime=True)
    from src.paper_converter_worker import _network_guard
    _network_guard("docling")
    session_start = _session_start(root, output, protocol, profile)
    start_body, _ = _read(child(root, session_start["relative"]), session_start["sha256"])
    write_once(output / "sessions" / "launches" / (launch_id + ".json"),
               {"launch_id": launch_id, "launcher_pid": os.getppid(),
                "worker_pid": os.getpid(), "process_created_ticks": start_body["process_created_ticks"],
                "session_start": session_start, "protocol_sha256": digest(output / "protocol.json")})
    converter = _docling_converter(root, profile)
    count = 0
    for raw in sys.stdin.buffer:
        command = parse_bound_json(raw)
        if (isinstance(command, dict) and set(command) == {"drain"} and
                isinstance(command["drain"], str) and re.fullmatch(r"[a-f0-9]{32}", command["drain"])):
            write_once(output / "sessions" / "drains" / (command["drain"] + ".json"),
                       {"nonce": command["drain"], "documents": count,
                        "session_start": session_start,
                        "protocol_sha256": digest(output / "protocol.json"), "worker_pid": os.getpid()})
            break
        if not isinstance(command, dict) or set(command) != {"sample_id"} or command["sample_id"] not in protocol["ids"]:
            raise ValueError("invalid_converter_session_command")
        if count >= protocol["converter_session"]["max_documents"]:
            raise ValueError("converter_session_document_limit_reached")
        _convert_one(root, output, command["sample_id"], converter, session_start)
        count += 1
    _profile(root, profile, verify_runtime=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    for name in ("run", "convert-one", "convert-session"):
        sub = commands.add_parser(name)
        sub.add_argument("--data-root", required=True)
        sub.add_argument("--output", required=True)
        if name == "run":
            sub.add_argument("--manifest", required=True)
            sub.add_argument("--profile", required=True)
            sub.add_argument("--source-root")
            sub.add_argument("--id", action="append", dest="selected_ids")
            sub.add_argument("--max-documents-per-session", type=int,
                             default=DEFAULT_MAX_DOCUMENTS_PER_SESSION)
        elif name == "convert-one":
            sub.add_argument("--id", required=True)
        elif name == "convert-session":
            sub.add_argument("--launch-id", required=True)
    args = p.parse_args()
    root = data_root(args.data_root)
    output = child(root, args.output)
    if args.command == "convert-one":
        _convert_one(root, output, args.id)
        return 0
    if args.command == "convert-session":
        if not re.fullmatch(r"[a-f0-9]{32}", args.launch_id):
            raise ValueError("invalid_converter_launch_id")
        _convert_session(root, output, args.launch_id)
        return 0
    summary = _run(root, child(root, args.manifest), child(root, args.profile), output,
                   Path(args.source_root).resolve() if args.source_root else None, args.selected_ids,
                   max_documents_per_session=args.max_documents_per_session)
    print(json.dumps({k: summary[k] for k in ("status", "document_count", "eligible_count", "state_counts")}))
    return 4 if summary["status"] == "STOPPED_DRAINED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
