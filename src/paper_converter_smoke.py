"""Durable single exposed-page converter smoke; no prospective cohort access.

The controller never imports a model library. Real engine execution is an
explicit subprocess operation; a separate attributed readback is required to
publish readiness. Local receipts bind evidence, not graph or review authority.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tempfile

from trace_gc.canonical import loads
from src.parallel_source_v4.common import child, digest, method_hashes, write_once

VERSION = "paper-converter-smoke-plan-v1"
SHA = re.compile(r"[a-f0-9]{64}\Z")
METHODS = {"docling": "parallel_structure_v4", "grobid": "parallel_grobid_v4",
           "mineru": "parallel_mineru_v4", "olmocr": "parallel_olmocr_v4"}
CACHES = {"docling": {"docling", "docling_document"}, "grobid": {"grobid"},
          "mineru": {"mineru"}, "olmocr": {"olmocr"}}
REPO = Path(__file__).resolve().parents[1]


def require(value, code):
    if not value:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def stamp(value):
    require(type(value) is str, "invalid_timestamp")
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "timezone_required")
    return result


def exact(value, keys, code):
    require(type(value) is dict and set(value) == set(keys), code)


def write_bytes_once(path, payload):
    fd, name = tempfile.mkstemp(prefix=".smoke-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            require(path.read_bytes() == payload, "immutable_page_conflict")
    finally:
        temporary.unlink(missing_ok=True)


def code_identity():
    return {"controller": digest(Path(__file__)),
            "worker": digest(Path(__file__).with_name("paper_converter_worker.py")),
            "dependencies": method_hashes()}


class Inputs:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.hashes = {}

    def path(self, descriptor):
        exact(descriptor, {"relative", "sha256"}, "invalid_asset_descriptor")
        require(type(descriptor["sha256"]) is str and SHA.fullmatch(descriptor["sha256"]), "invalid_asset_hash")
        path = child(self.root, descriptor["relative"])
        original = self.root / descriptor["relative"]
        require(not any(p.is_symlink() for p in [original, *original.parents] if p != self.root), "symlink_asset_forbidden")
        require(path.is_file() and not path.is_symlink(), "asset_file_required")
        old = self.hashes.setdefault(descriptor["relative"], descriptor["sha256"])
        require(old == descriptor["sha256"], "conflicting_asset_identity")
        return path

    def read(self, descriptor):
        raw = self.path(descriptor).read_bytes()
        require(sha(raw) == descriptor["sha256"], "asset_hash_mismatch")
        return raw

    def json(self, descriptor):
        return loads(self.read(descriptor))

    def verify(self, descriptor):
        require(digest(self.path(descriptor)) == descriptor["sha256"], "asset_hash_mismatch")

    def recheck(self):
        for relative, expected in self.hashes.items():
            self.verify({"relative": relative, "sha256": expected})


def source_check(source, page):
    """Use the hash-checked buffers; never reopen a source path for rendering."""
    import fitz
    with fitz.open(stream=source, filetype="pdf") as original, fitz.open(stream=page, filetype="pdf") as isolated:
        require(len(original) >= 1 and len(isolated) == 1 and not original.is_encrypted,
                "physical_first_page_required")
        a, b = original[0].get_pixmap(dpi=120, alpha=False), isolated[0].get_pixmap(dpi=120, alpha=False)
        require((a.width, a.height, a.n) == (b.width, b.height, b.n) and a.samples == b.samples,
                "original_first_page_copy_mismatch")


def validate_plan(root, descriptor):
    inputs = Inputs(root)
    plan = inputs.json(descriptor)
    exact(plan, {"version", "mode", "created_at", "case_id", "source", "page", "exposure",
                 "engine", "runtime", "limits", "code_identity", "configuration_sha256",
                 "evaluation_runtime_sha256", "evaluation_code_sha256"}, "invalid_smoke_plan")
    require(plan["version"] == VERSION and plan["mode"] in {"EXPOSED_DEVELOPMENT", "AUTHORED_FIXTURE"},
            "unsupported_smoke_scope")
    require(type(plan["case_id"]) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", plan["case_id"]), "invalid_case_id")
    created = stamp(plan["created_at"])
    for key in ("configuration_sha256", "evaluation_runtime_sha256", "evaluation_code_sha256"):
        require(type(plan[key]) is str and SHA.fullmatch(plan[key]), "invalid_evaluation_identity")
    require(plan["code_identity"] == code_identity(), "smoke_code_changed")
    exposure = inputs.json(plan["exposure"])
    exact(exposure, {"version", "case_id", "source_sha256", "page_sha256", "scope", "attribution", "recorded_at"},
          "invalid_exposure_record")
    require(exposure["version"] == "paper-exposed-source-v1" and exposure["case_id"] == plan["case_id"]
            and exposure["source_sha256"] == plan["source"]["sha256"] and exposure["page_sha256"] == plan["page"]["sha256"]
            and exposure["scope"] == plan["mode"] and type(exposure["attribution"]) is str and exposure["attribution"].strip()
            and stamp(exposure["recorded_at"]) <= created, "exposure_binding_required")
    source, page = inputs.read(plan["source"]), inputs.read(plan["page"])
    source_check(source, page)
    engine = plan["engine"]
    exact(engine, {"name", "revision", "license", "device", "assets", "decoding", "prompt_sha256"}, "invalid_engine")
    require(engine["name"] in METHODS and all(type(engine[k]) is str and engine[k].strip() for k in ("revision", "license", "device")),
            "supported_local_engine_required")
    require(engine["prompt_sha256"] is None or (type(engine["prompt_sha256"]) is str and SHA.fullmatch(engine["prompt_sha256"])),
            "invalid_prompt_identity")
    require(type(engine["assets"]) is list and engine["assets"], "engine_assets_required")
    for asset in engine["assets"]:
        inputs.verify(asset)
    require(len({a["relative"] for a in engine["assets"]}) == len(engine["assets"]), "duplicate_engine_assets")
    runtime = plan["runtime"]
    exact(runtime, {"executable", "python_version", "packages", "files"}, "invalid_converter_runtime")
    require(type(runtime["packages"]) is dict and type(runtime["files"]) is list and runtime["files"]
            and type(runtime["python_version"]) is str
            and all(type(k) is str and type(v) is str and k and v for k, v in runtime["packages"].items()), "runtime_files_required")
    inputs.verify(runtime["executable"])
    for asset in runtime["files"]:
        inputs.verify(asset)
    require(len({a["relative"] for a in runtime["files"]}) == len(runtime["files"]), "duplicate_runtime_files")
    limits = plan["limits"]
    exact(limits, {"request_characters", "request_tokens", "retries", "timeout_seconds", "device_concurrency", "crop_policy"},
          "invalid_execution_limits")
    require(all(type(limits[k]) is int and limits[k] > 0 for k in ("request_characters", "request_tokens", "timeout_seconds"))
            and type(limits["retries"]) is int and limits["retries"] == 0
            and type(limits["device_concurrency"]) is int and limits["device_concurrency"] == 1
            and limits["crop_policy"] == "physical_page_one_only" and limits["timeout_seconds"] <= 3600,
            "bounded_single_attempt_required")
    from src.paper_converter_worker import validate_profile
    validate_profile(plan, inputs.root)
    inputs.recheck()
    return plan, inputs, page


_ENGINE_LOCK_ROOT = ContextVar("paper_converter_engine_lock_root", default=None)


def engine_lock_owned(root):
    """Report this process's active engine-lock context to an enrolled collector."""
    return _ENGINE_LOCK_ROOT.get() == str(Path(root).resolve())


@contextmanager
def engine_lock(root):
    """An OS-released lock; a crashed process cannot leave a stale held lease."""
    path = child(root, ".paper-converter-smoke.lock")
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0"); stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("another_converter_owns_data_root") from exc
        token = _ENGINE_LOCK_ROOT.set(str(Path(root).resolve()))
        try:
            yield
        finally:
            _ENGINE_LOCK_ROOT.reset(token)
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def output_path(root, relative):
    output = child(root, relative)
    require(output != Path(root).resolve() and REPO not in output.parents and output != REPO, "private_output_required")
    return output


def generated_path(root, path):
    relative = Path(path).relative_to(Path(root).resolve()).as_posix()
    resolved = child(root, relative)  # containment before opening any bytes
    original = Path(root).resolve() / relative
    require(not any(p.is_symlink() for p in [original, *original.parents] if p != Path(root).resolve()), "symlink_asset_forbidden")
    return resolved


def descriptor(root, path):
    checked = generated_path(root, path)
    return {"relative": checked.relative_to(Path(root).resolve()).as_posix(), "sha256": digest(checked)}


def write_output(root, path, value):
    return write_once(generated_path(root, path), value)


def prepare(root, plan_descriptor, output):
    """Default operation: validates assets and copies only the already exposed page."""
    root = Path(root).resolve()
    with engine_lock(root):
        return _prepare(root, deepcopy(plan_descriptor), output)


def _prepare(root, plan_descriptor, output):
    plan, inputs, page = validate_plan(root, plan_descriptor)
    out = output_path(root, output)
    expected = {"version": "paper-converter-prepared-v1", "plan": plan_descriptor,
                "mode": plan["mode"], "input_hashes": dict(inputs.hashes), "code_identity": plan["code_identity"]}
    if out.exists():
        require((out / "prepared.json").is_file(), "existing_output_not_prepared")
        outputs = Inputs(root)
        require(outputs.json(descriptor(root, out / "prepared.json")) == expected, "prepared_identity_changed")
        outputs.verify({"relative": (out / "page.pdf").relative_to(root).as_posix(), "sha256": plan["page"]["sha256"]})
        outputs.recheck()
    else:
        out.mkdir(parents=True, exist_ok=False)
        write_bytes_once(out / "page.pdf", page)
        write_output(root, out / "prepared.json", expected)
    inputs.recheck()
    require(code_identity() == plan["code_identity"], "smoke_code_changed")
    return expected


def _worker(root, plan_descriptor, out, plan):
    executable = child(root, plan["runtime"]["executable"]["relative"])
    bytecode = out / "unused-bytecode"
    require(not bytecode.exists(), "fresh_bytecode_prefix_required")
    command = [str(executable), "-I", "-B", "-X", "utf8", "-X", "pycache_prefix=" + str(bytecode),
               str(Path(__file__).with_name("paper_converter_worker.py")),
               "--data-root", str(root), "--plan", plan_descriptor["relative"], "--expected-plan-sha256", plan_descriptor["sha256"],
               "--output", out.relative_to(root).as_posix()]
    environment = os.environ.copy()
    environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                       PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="4", MKL_NUM_THREADS="4")
    environment.pop("PYTHONPATH", None)
    with (out / "stdout.txt").open("xb") as stdout, (out / "stderr.txt").open("xb") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=environment, cwd=REPO)
        try:
            return process.wait(timeout=plan["limits"]["timeout_seconds"])
        except subprocess.TimeoutExpired:
            # Terminate only the exact owned worker. No VM/service/process-tree kill.
            process.kill(); process.wait()
            raise ValueError("worker_timeout_unknown_outcome") from None


def outstanding_attempts(root, reconciliation=None):
    """A crashed controller releases the OS lock, not its unresolved intent."""
    registry = child(root, ".paper-converter-attempts")
    if not registry.exists():
        return
    for path in sorted(registry.glob("*.json")):
        value = Inputs(root).json(descriptor(root, path))
        exact(value, {"version", "output", "plan", "intent_sha256"}, "invalid_attempt_registry")
        require(value["version"] == "paper-converter-active-attempt-v1", "invalid_attempt_registry")
        if reconciliation is not None and path.relative_to(root).as_posix() == reconciliation["old_registry_relative"]:
            from src.paper_converter_reconciliation import recheck
            require(descriptor(root, path)["sha256"] == reconciliation["old_registry_sha256"],
                    "reconciled_registry_changed")
            recheck(root, reconciliation, allow_successor_created=True)
            continue
        out = output_path(root, value["output"])
        require((out / "execution.json").is_file() and not (out / "INVALIDATED.json").exists(), "unreconciled_attempt_blocks_data_root")
        Inputs(root).verify({"relative": (out / "intent.json").relative_to(root).as_posix(), "sha256": value["intent_sha256"]})
        verify_execution(root, value["plan"], value["output"])


def execute(root, plan_descriptor, output):
    root = Path(root).resolve()
    plan_descriptor = deepcopy(plan_descriptor)
    with engine_lock(root):
        return _execute_locked(root, plan_descriptor, output)


def execute_successor(root, plan_descriptor, output, *, authority_relative,
                      authority_sha256, receipt_relative, receipt_sha256,
                      trusted_application=None):
    """One distinct attempt under an enrolled application's live exclusion.

    The standalone CLI cannot supply this capability. Its implementation must
    independently enroll the authority and hold launch exclusion for the full
    worker lifetime; a receipt or caller-supplied hash does neither.
    """
    from src.paper_converter_trusted_application_v1 import RootEnrolledConverterApplication
    require(type(trusted_application) is RootEnrolledConverterApplication,
            "root_owned_concrete_application_required")
    root = Path(root).resolve()
    plan_descriptor = deepcopy(plan_descriptor)
    with engine_lock(root):
        from src.paper_converter_reconciliation import verify_reconciliation
        existing = output_path(root, output)
        if (existing / "execution.json").is_file():
            proof = verify_reconciliation(root,
                authority_relative=authority_relative,
                authority_sha256=authority_sha256,
                receipt_relative=receipt_relative,
                receipt_sha256=receipt_sha256,
                successor_plan=plan_descriptor, successor_output=output,
                allow_successor_created=True, historical_readback=True)
            require(trusted_application.verify_authority(proof) is True,
                    "historical_authority_revoked_or_not_enrolled")
            return verify_execution(root, plan_descriptor, output,
                                    trusted_application=trusted_application)
        proof = verify_reconciliation(root, authority_relative=authority_relative,
            authority_sha256=authority_sha256, receipt_relative=receipt_relative,
            receipt_sha256=receipt_sha256, successor_plan=plan_descriptor,
            successor_output=output)
        require(trusted_application.verify_authority(proof) is True,
                "authority_not_independently_enrolled")
        with trusted_application.hold_live_exclusion(root, proof) as exclusion:
            require(callable(getattr(exclusion, "reobserve", None)),
                    "live_exclusion_observer_required")
            return _execute_locked(root, plan_descriptor, output,
                                   reconciliation=proof,
                                   trusted_application=trusted_application,
                                   live_exclusion=exclusion)


def _execute_locked(root, plan_descriptor, output, reconciliation=None,
                    trusted_application=None, live_exclusion=None):
        _prepare(root, plan_descriptor, output)
        out = output_path(root, output)
        plan, inputs, _ = validate_plan(root, plan_descriptor)
        require(not (out / "INVALIDATED.json").exists(), "attempt_invalidated")
        if (out / "execution.json").exists():
            return verify_execution(root, plan_descriptor, output,
                                    trusted_application=trusted_application)
        require(not (out / "intent.json").exists(), "unknown_attempt_requires_manual_reconciliation_no_retry")
        outstanding_attempts(root, reconciliation)
        if reconciliation is not None:
            from src.paper_converter_reconciliation import recheck
            recheck(root, reconciliation, allow_successor_created=True)
            write_output(root, out / "RECONCILIATION_PARENT.json", {
                "version": "paper-converter-successor-lineage-v1",
                "old_output": reconciliation["old_output"],
                "old_registry_sha256": reconciliation["old_registry_sha256"],
                "authority": {"relative": reconciliation["authority_relative"],
                              "sha256": reconciliation["authority_sha256"]},
                "receipt": {"relative": reconciliation["receipt_relative"],
                            "sha256": reconciliation["receipt_sha256"]},
                "successor_plan": plan_descriptor,
                "historical_outcome": "UNKNOWN_UNATTESTED_NO_RETRY"})
        write_output(root, out / "intent.json", {"version": "paper-converter-intent-v1", "plan": plan_descriptor,
                                        "started_at": now(), "mode": plan["mode"], "attempt": 1, "controller_pid": os.getpid()})
        registry = {"version": "paper-converter-active-attempt-v1", "output": out.relative_to(root).as_posix(),
                    "plan": plan_descriptor, "intent_sha256": descriptor(root, out / "intent.json")["sha256"]}
        registry_path = child(root, ".paper-converter-attempts/" + sha(registry["output"].encode()) + ".json")
        write_once(registry_path, registry)
        started = time.monotonic()
        try:
            if reconciliation is not None:
                recheck(root, reconciliation, allow_successor_created=True)
                from src.paper_converter_reconciliation import verify_live_exclusion
                verify_live_exclusion(reconciliation, live_exclusion.reobserve())
            exit_code = _worker(root, plan_descriptor, out, plan)
            if reconciliation is not None:
                recheck(root, reconciliation, allow_successor_created=True,
                        post_worker_readback=True)
                verify_live_exclusion(reconciliation, live_exclusion.reobserve())
            inputs.recheck()
            require(code_identity() == plan["code_identity"], "smoke_code_changed")
            result, artifacts = execution_evidence(root, out, plan_descriptor,
                                                    plan, inputs,
                                                    trusted_application=trusted_application,
                                                    post_worker_readback=True)
            require(type(exit_code) is int and exit_code == (0 if result["status"] == "success" else 1), "exit_status_mismatch")
            receipt = {"version": "paper-converter-execution-readback-v1", "plan": plan_descriptor,
                       "mode": plan["mode"], "engine": result["engine"], "status": result["status"], "exit_code": exit_code,
                       "wall_seconds": time.monotonic() - started, "artifacts": artifacts,
                       "input_hashes": dict(inputs.hashes), "code_identity": code_identity(), "readiness_pass": False}
            receipt_sha = write_output(root, out / "execution.json", receipt)
            inputs.recheck()
            require(code_identity() == plan["code_identity"] and descriptor(root, out / "execution.json")["sha256"] == receipt_sha, "smoke_code_or_execution_changed")
            return receipt
        except Exception as exc:
            write_output(root, out / "INVALIDATED.json", {"version": "paper-converter-invalidated-v1", "at": now(),
                       "reason": type(exc).__name__, "unknown_outcome": True})
            raise


def execution_evidence(root, out, plan_descriptor, plan, inputs,
                       trusted_application=None, post_worker_readback=False):
    """Reconstruct receipt claims from owned artifacts, with same-buffer parsing."""
    base_hashes = dict(inputs.hashes)
    artifacts = {key: descriptor(root, out / filename) for key, filename in {
        "worker_result": "worker-result.json", "stdout": "stdout.txt", "stderr": "stderr.txt",
        "prepared": "prepared.json", "intent": "intent.json", "page": "page.pdf"}.items()}
    lineage = out / "RECONCILIATION_PARENT.json"
    if lineage.exists():
        require(trusted_application is not None and
                callable(getattr(trusted_application, "verify_authority", None)),
                "independent_reconciliation_readback_required")
        artifacts["reconciliation_parent"] = descriptor(root, lineage)
        parent = inputs.json(artifacts["reconciliation_parent"])
        exact(parent, {"version", "old_output", "old_registry_sha256", "authority",
                       "receipt", "successor_plan", "historical_outcome"},
              "invalid_successor_lineage")
        require(parent["version"] == "paper-converter-successor-lineage-v1" and
                parent["successor_plan"] == plan_descriptor and
                parent["historical_outcome"] == "UNKNOWN_UNATTESTED_NO_RETRY",
                "successor_lineage_differs")
        from src.paper_converter_reconciliation import verify_reconciliation
        proof = verify_reconciliation(root,
            authority_relative=parent["authority"]["relative"],
            authority_sha256=parent["authority"]["sha256"],
            receipt_relative=parent["receipt"]["relative"],
            receipt_sha256=parent["receipt"]["sha256"],
            successor_plan=plan_descriptor,
            successor_output=out.relative_to(root).as_posix(),
            allow_successor_created=True,
            historical_readback=(out / "execution.json").is_file(),
            post_worker_readback=post_worker_readback and
                                 not (out / "execution.json").is_file())
        require(proof["old_output"] == parent["old_output"] and
                proof["old_registry_sha256"] == parent["old_registry_sha256"] and
                trusted_application.verify_authority(proof) is True,
                "successor_authority_or_old_inventory_differs")
    prepared = inputs.json(artifacts["prepared"])
    require(prepared == {"version": "paper-converter-prepared-v1", "plan": plan_descriptor, "mode": plan["mode"],
                         "input_hashes": base_hashes, "code_identity": plan["code_identity"]}, "prepared_identity_changed")
    intent = inputs.json(artifacts["intent"])
    exact(intent, {"version", "plan", "started_at", "mode", "attempt", "controller_pid"}, "invalid_execution_intent")
    require(intent["version"] == "paper-converter-intent-v1" and intent["plan"] == plan_descriptor
            and intent["mode"] == plan["mode"] and type(intent["attempt"]) is int and intent["attempt"] == 1
            and type(intent["controller_pid"]) is int and intent["controller_pid"] > 0, "intent_identity_mismatch")
    result = inputs.json(artifacts["worker_result"])
    exact(result, {"version", "mode", "engine", "revision", "plan_sha256", "status", "outputs", "raw_response",
                   "started_at", "completed_at", "runtime", "resources"}, "invalid_worker_result")
    require(result["version"] == "paper-converter-worker-result-v1" and result["mode"] == plan["mode"]
            and result["engine"] == plan["engine"]["name"] and result["revision"] == plan["engine"]["revision"]
            and result["plan_sha256"] == plan_descriptor["sha256"] and result["status"] in {"success", "truncated", "error"}
            and type(result["outputs"]) is dict and set(result["outputs"]) == CACHES[result["engine"]]
            and result["runtime"] == {"python_version": plan["runtime"]["python_version"], "packages": plan["runtime"]["packages"]}
            and stamp(intent["started_at"]) <= stamp(result["started_at"]) <= stamp(result["completed_at"]), "worker_identity_mismatch")
    require(type(result["resources"]) is dict and result["resources"].get("authored_fixture", False)
            is (plan["mode"] == "AUTHORED_FIXTURE"), "synthetic_worker_evidence_mismatch")
    artifacts.update({"cache_" + k: v for k, v in result["outputs"].items()})
    artifacts["raw_response"] = result["raw_response"]
    require(artifacts["page"]["sha256"] == plan["page"]["sha256"], "worker_page_changed")
    for asset in artifacts.values():
        require(child(root, asset["relative"]).is_relative_to(out), "worker_output_outside_attempt")
        inputs.verify(asset)
    for asset in result["outputs"].values():
        require(type(inputs.json(asset)) is dict, "converter_object_required")
    return result, artifacts


def verify_execution(root, plan_descriptor, output, *, trusted_application=None):
    root = Path(root).resolve()
    plan_descriptor = deepcopy(plan_descriptor)
    plan, inputs, _ = validate_plan(root, plan_descriptor)
    out = output_path(root, output)
    require(not (out / "INVALIDATED.json").exists(), "attempt_invalidated")
    payload = Inputs(root).read(descriptor(root, out / "execution.json"))
    record = loads(payload)
    exact(record, {"version", "plan", "mode", "engine", "status", "exit_code", "wall_seconds", "artifacts",
                   "input_hashes", "code_identity", "readiness_pass"}, "invalid_execution_record")
    require(record["version"] == "paper-converter-execution-readback-v1" and record["plan"] == plan_descriptor
            and record["mode"] == plan["mode"] and record["code_identity"] == plan["code_identity"], "execution_identity_changed")
    result, artifacts = execution_evidence(root, out, plan_descriptor, plan,
                                           inputs, trusted_application=trusted_application)
    require(record["engine"] == result["engine"] and record["status"] == result["status"]
            and type(record["exit_code"]) is int and record["exit_code"] == (0 if result["status"] == "success" else 1)
            and record["artifacts"] == artifacts and record["input_hashes"] == inputs.hashes
            and type(record["wall_seconds"]) in {int, float} and record["wall_seconds"] >= 0
            and record["readiness_pass"] is False, "execution_claim_mismatch")
    inputs.recheck()
    require(not (out / "INVALIDATED.json").exists() and code_identity() == plan["code_identity"]
            and descriptor(root, out / "execution.json")["sha256"] == sha(payload), "attempt_changed")
    return record


def readiness_evidence(root, plan_descriptor, output, attestation_descriptor,
                       *, trusted_application=None):
    execution = verify_execution(root, plan_descriptor, output,
                                 trusted_application=trusted_application)
    out = output_path(root, output)
    plan, inputs, _ = validate_plan(root, plan_descriptor)
    attestation = inputs.json(attestation_descriptor)
    exact(attestation, {"version", "execution_sha256", "custodian", "reviewed_at", "actual_engine_execution_confirmed",
                        "assets_and_raw_outputs_checked", "independent_human", "mode"}, "custodian_readback_required")
    raw = inputs.json(execution["artifacts"]["worker_result"])
    require(attestation["version"] == "paper-converter-custodian-readback-v1"
            and attestation["execution_sha256"] == descriptor(root, out / "execution.json")["sha256"]
            and type(attestation["custodian"]) is str and attestation["custodian"].strip()
            and attestation["actual_engine_execution_confirmed"] is True and attestation["assets_and_raw_outputs_checked"] is True
            and attestation["independent_human"] is False and attestation["mode"] == plan["mode"]
            and stamp(attestation["reviewed_at"]) >= stamp(raw["completed_at"]), "custodian_binding_mismatch")
    require(execution["exit_code"] == 0 and execution["status"] == "success", "failed_or_truncated_engine_not_ready")
    prefix = "synthetic-" if plan["mode"] == "AUTHORED_FIXTURE" else ""
    engine = plan["engine"]
    readiness = {"version": prefix + "paper-local-readiness-v1", "engine": engine["name"], "revision": engine["revision"],
                 "asset_sha256": [a["sha256"] for a in engine["assets"]], "exit_code": 0, "local_only": True,
                 "stdout": execution["artifacts"]["stdout"], "completed_at": raw["completed_at"]}
    return readiness, inputs, plan


def finalize(root, plan_descriptor, output, attestation_descriptor,
             *, trusted_application=None):
    """Explicit attributed custodian readback; never invent or auto-sign it."""
    root = Path(root).resolve()
    plan_descriptor, attestation_descriptor = deepcopy(plan_descriptor), deepcopy(attestation_descriptor)
    with engine_lock(root):
        readiness, inputs, plan = readiness_evidence(root, plan_descriptor, output,
            attestation_descriptor, trusted_application=trusted_application)
        out = output_path(root, output)
        write_output(root, out / "readiness.json", readiness)
        marker = {"version": "paper-converter-readiness-completion-v1", "mode": plan["mode"],
                  "execution": descriptor(root, out / "execution.json"), "attestation": attestation_descriptor,
                  "readiness": descriptor(root, out / "readiness.json"), "prospective_execution_authorized": False,
                  "graph_admission_enabled": False, "independent_human": False}
        try:
            verify_execution(root, plan_descriptor, output,
                             trusted_application=trusted_application); inputs.recheck()
            write_output(root, out / "COMPLETE.json", marker)
            verify_execution(root, plan_descriptor, output,
                             trusted_application=trusted_application); inputs.recheck()
            require(Inputs(root).json(descriptor(root, out / "COMPLETE.json")) == marker
                    and descriptor(root, out / "readiness.json")["sha256"] == marker["readiness"]["sha256"], "publication_changed")
            return marker
        except Exception as exc:
            write_output(root, out / "INVALIDATED.json", {"version": "paper-converter-invalidated-v1", "at": now(),
                       "reason": type(exc).__name__, "unknown_outcome": False})
            raise


def verify_readiness(root, plan_descriptor, output, attestation_descriptor,
                     *, trusted_application=None):
    """Verify completion against the external plan AND custodian pins."""
    root = Path(root).resolve()
    plan_descriptor, attestation_descriptor = deepcopy(plan_descriptor), deepcopy(attestation_descriptor)
    out = output_path(root, output)
    original = Inputs(root).read(descriptor(root, out / "COMPLETE.json"))
    marker = loads(original)
    exact(marker, {"version", "mode", "execution", "attestation", "readiness", "prospective_execution_authorized",
                   "graph_admission_enabled", "independent_human"}, "invalid_completion_marker")
    require(marker["version"] == "paper-converter-readiness-completion-v1" and marker["attestation"] == attestation_descriptor
            and marker["prospective_execution_authorized"] is False and marker["graph_admission_enabled"] is False
            and marker["independent_human"] is False, "completion_identity_mismatch")
    readiness, inputs, plan = readiness_evidence(root, plan_descriptor, output,
        attestation_descriptor, trusted_application=trusted_application)
    require(marker["mode"] == plan["mode"] and marker["execution"] == descriptor(root, out / "execution.json")
            and marker["readiness"] == descriptor(root, out / "readiness.json")
            and inputs.json(marker["readiness"]) == readiness, "readiness_fields_changed")
    inputs.recheck()
    verify_execution(root, plan_descriptor, output,
                     trusted_application=trusted_application)
    inputs.recheck()
    require(sha(original) == descriptor(root, out / "COMPLETE.json")["sha256"]
            and not (out / "INVALIDATED.json").exists(), "completion_changed")
    return marker


def validate_prospective_execution(value):
    """Strict existing #20 wire contract; this smoke never authorizes its use."""
    exact(value, {"version", "method", "engine", "revision", "access_sha256", "source_sha256", "page_sha256",
                  "configuration_sha256", "runtime_sha256", "code_sha256", "limits_sha256", "started_at", "completed_at",
                  "execution_kind", "status", "output_sha256", "raw_response", "new_paid_api_calls", "production_graph_writes"},
          "invalid_prospective_converter_receipt")
    require(value["version"] == "paper-converter-execution-v1" and value["engine"] in METHODS
            and value["method"] == METHODS[value["engine"]] and value["execution_kind"] == "LOCAL_CONVERTER"
            and value["status"] in {"success", "error", "truncated"}, "invalid_converter_execution_identity")
    for key in ("access_sha256", "source_sha256", "page_sha256", "configuration_sha256", "runtime_sha256", "code_sha256", "limits_sha256"):
        require(type(value[key]) is str and SHA.fullmatch(value[key]), "invalid_converter_execution_hash")
    require(type(value["revision"]) is str and value["revision"].strip() and type(value["output_sha256"]) is dict
            and set(value["output_sha256"]) == CACHES[value["engine"]]
            and all(type(v) is str and SHA.fullmatch(v) for v in value["output_sha256"].values()), "invalid_converter_output_identity")
    for key in ("new_paid_api_calls", "production_graph_writes"):
        require(type(value[key]) is int and value[key] == 0, "local_zero_effects_required")
    exact(value["raw_response"], {"relative", "sha256"}, "raw_response_required")
    child(REPO, value["raw_response"]["relative"])
    require(type(value["raw_response"]["sha256"]) is str and SHA.fullmatch(value["raw_response"]["sha256"])
            and stamp(value["started_at"]) <= stamp(value["completed_at"]), "invalid_execution_time_or_response")
    return deepcopy(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "execute", "execute-successor", "verify", "finalize", "verify-readiness"))
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--attestation")
    parser.add_argument("--expected-attestation-sha256")
    parser.add_argument("--reconciliation-authority")
    parser.add_argument("--expected-reconciliation-authority-sha256")
    parser.add_argument("--reconciliation-receipt")
    parser.add_argument("--expected-reconciliation-receipt-sha256")
    args = parser.parse_args()
    plan = {"relative": args.plan, "sha256": args.expected_plan_sha256}
    try:
        reconciliation_args = (args.reconciliation_authority,
            args.expected_reconciliation_authority_sha256,
            args.reconciliation_receipt,
            args.expected_reconciliation_receipt_sha256)
        require((args.action == "execute-successor" and all(reconciliation_args)) or
                (args.action != "execute-successor" and not any(reconciliation_args)),
                "explicit_reconciliation_authority_and_receipt_required")
        if args.action in {"finalize", "verify-readiness"}:
            require(args.attestation and args.expected_attestation_sha256, "external_attestation_pin_required")
            function = finalize if args.action == "finalize" else verify_readiness
            result = function(args.data_root, plan, args.output, {"relative": args.attestation, "sha256": args.expected_attestation_sha256})
        elif args.action == "execute-successor":
            raise ValueError("standalone_successor_execution_requires_enrolled_application")
        else:
            result = {"prepare": prepare, "execute": execute, "verify": verify_execution}[args.action](args.data_root, plan, args.output)
        print(json.dumps({"status": args.action.upper(), "mode": result["mode"], "readiness_pass": args.action in {"finalize", "verify-readiness"}
                          and result["mode"] == "EXPOSED_DEVELOPMENT", "prospective_execution_authorized": False}))
        return 0
    except (ValueError, OSError, KeyError, TypeError, ImportError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": type(exc).__name__, "readiness_pass": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
