"""Externally authorized reconciliation of one preserved converter attempt.

This module does not infer that a provider never ran. It binds an attributed
closure review to immutable old bytes and permits one distinct successor name.
The application must pin the authority file hash independently of the receipt.
"""
from __future__ import annotations

import base64
import datetime as dt
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from trace_gc.canonical import canonical_bytes, loads
from src import paper_converter_smoke as smoke


AUTHORITY_VERSION = "paper-converter-reconciliation-authority-v1"
RECEIPT_VERSION = "paper-converter-manual-reconciliation-v1"
CLOSURE_VERSION = "paper-converter-attempt-closure-v1"
CLOSURE_VERSION_V2 = "paper-converter-attempt-closure-v2"
HISTORICAL_CONTROLLER_SHA256 = "16f36ef7a659bc064285561b8a4f6dde865c33e1efc4b1d41775350584fbe2ef"
HISTORICAL_WORKER_SHA256 = "63c1a67143a1fb220db59b84752721c12054405f3d72f7afb0b2eedc3497d2fa"


def _exact(value, keys, code):
    smoke.exact(value, keys, code)


def _read(root, relative, sha256):
    smoke.require(type(relative) is str and type(sha256) is str and
                  smoke.SHA.fullmatch(sha256), "invalid_reconciliation_descriptor")
    descriptor = {"relative": relative, "sha256": sha256}
    smoke.child(root, relative)
    target = root / relative
    for part in (target, *target.parents):
        if part == root:
            break
        if part.exists():
            state = part.lstat()
            smoke.require(not part.is_symlink() and
                          not (getattr(state, "st_file_attributes", 0) & 0x400),
                          "reconciliation_reparse_path_forbidden")
    return smoke.Inputs(root).read(descriptor)


def _inventory(root, output):
    path = smoke.output_path(root, output)
    smoke.require(path.is_dir() and not path.is_symlink() and
                  not (getattr(path.lstat(), "st_file_attributes", 0) & 0x400),
                  "old_attempt_directory_missing")
    rows = []
    for item in sorted(path.rglob("*")):
        state = item.lstat()
        smoke.require(not item.is_symlink() and
                      not (getattr(state, "st_file_attributes", 0) & 0x400) and
                      (item.is_file() or item.is_dir()), "old_attempt_nonfile_or_link")
        rows.append({"relative": item.relative_to(root).as_posix(),
                     "kind": "file" if item.is_file() else "directory",
                     "sha256": smoke.digest(item) if item.is_file() else None})
    return rows


def _closure(root, descriptor, old_intent, intent_sha256, old_plan, invalidation=None,
             invalidation_descriptor=None, old_output=None):
    _exact(descriptor, {"relative", "sha256"}, "invalid_closure_descriptor")
    value = loads(_read(root, descriptor["relative"], descriptor["sha256"]))
    _exact(value, {"version", "recorded_at", "intent_sha256", "worker", "server"},
           "invalid_closure_evidence")
    smoke.require(value["version"] in {CLOSURE_VERSION, CLOSURE_VERSION_V2} and
                  value["intent_sha256"] == intent_sha256,
                  "closure_intent_differs")
    observed = smoke.stamp(value["recorded_at"])
    worker = value["worker"]
    if value["version"] == CLOSURE_VERSION:
        _exact(worker, {"controller_pid", "worker_pid", "created_at", "observed_exit_at",
                        "owned_descendants_zero", "evidence"}, "invalid_worker_closure")
        smoke.require(type(worker["controller_pid"]) is int and
                      worker["controller_pid"] == old_intent["controller_pid"] and
                      type(worker["worker_pid"]) is int and worker["worker_pid"] > 0 and
                      worker["owned_descendants_zero"] is True and
                      smoke.stamp(old_intent["started_at"]) <= smoke.stamp(worker["created_at"]) <=
                      smoke.stamp(worker["observed_exit_at"]) <= observed,
                      "worker_closure_not_proved")
    else:
        smoke.require(type(old_plan) is dict and invalidation is not None and
                      invalidation_descriptor is not None and old_output is not None,
                      "unrecorded_pid_requires_exact_old_attempt")
        _exact(worker, {"controller_pid", "worker_pid", "current_absence_at",
                        "owned_descendants_zero", "evidence", "launcher_terminal_evidence"},
               "invalid_worker_closure")
        launch = worker["launcher_terminal_evidence"]
        _exact(launch, {"controller_source_sha256", "worker_source_sha256",
                        "stdout", "stderr", "invalidation", "interpretation"},
               "invalid_historical_launcher_evidence")
        old_dir = smoke.output_path(root, old_output)
        smoke.require(old_plan["engine"]["name"] == "docling" and
                      old_plan["mode"] == old_intent["mode"] == "EXPOSED_DEVELOPMENT" and
                      old_plan["code_identity"]["controller"] == HISTORICAL_CONTROLLER_SHA256 and
                      old_plan["code_identity"]["worker"] == HISTORICAL_WORKER_SHA256 and
                      launch["controller_source_sha256"] == HISTORICAL_CONTROLLER_SHA256 and
                      launch["worker_source_sha256"] == HISTORICAL_WORKER_SHA256 and
                      launch["interpretation"] == "LAUNCHER_TERMINAL_PROVIDER_OUTCOME_UNKNOWN" and
                      worker["controller_pid"] == old_intent["controller_pid"] and
                      worker["worker_pid"] is None and worker["owned_descendants_zero"] is True and
                      smoke.stamp(old_intent["started_at"]) <=
                      smoke.stamp(worker["current_absence_at"]) <= observed and
                      invalidation["reason"] == "FileNotFoundError" and
                      launch["invalidation"] == invalidation_descriptor,
                      "unrecorded_pid_closure_scope_differs")
        for name in ("stdout", "stderr"):
            expected = (old_dir / (name + ".txt")).relative_to(root).as_posix()
            smoke.require(launch[name]["relative"] == expected,
                          "historical_launcher_file_path_differs")
            _read(root, **launch[name])
        stderr = loads(_read(root, **launch["stderr"]))
        smoke.require(stderr == {"status": "WORKER_FAILED", "error": "ValueError"},
                      "historical_worker_terminal_message_differs")
        # This bounds the original launcher path; it does not establish the
        # old interpreter PID or whether a provider call happened.
        _read(root, **launch["invalidation"])
    _exact(worker["evidence"], {"relative", "sha256"}, "invalid_worker_evidence")
    _read(root, **worker["evidence"])
    server = value["server"]
    engine = old_plan if type(old_plan) is str else old_plan["engine"]["name"]
    if engine == "grobid":
        _exact(server, {"status", "request_id", "observed_closed_at", "inflight_zero",
                        "evidence"}, "server_closure_required")
        smoke.require(server["status"] == "REQUEST_CLOSED" and
                      type(server["request_id"]) is str and server["request_id"] and
                      server["inflight_zero"] is True and
                      smoke.stamp(server["observed_closed_at"]) <= observed,
                      "server_closure_not_proved")
        _exact(server["evidence"], {"relative", "sha256"}, "invalid_server_evidence")
        _read(root, **server["evidence"])
    else:
        smoke.require(server == {"status": "NOT_APPLICABLE_LOCAL_ENGINE"},
                      "unexpected_server_closure")
    return value


def verify_reconciliation(root, *, authority_relative, authority_sha256,
                          receipt_relative, receipt_sha256, successor_plan,
                          successor_output, allow_successor_created=False,
                          historical_readback=False, post_worker_readback=False):
    """Return a recheckable proof; never discover a key from the receipt."""
    root = Path(root).resolve()
    authority = loads(_read(root, authority_relative, authority_sha256))
    _exact(authority, {"version", "issuer", "public_key_hex", "old_registry_sha256",
                       "successor_plan_sha256", "successor_output", "expires_at"},
           "invalid_reconciliation_authority")
    smoke.require(authority["version"] == AUTHORITY_VERSION and
                  type(authority["issuer"]) is str and authority["issuer"].strip() and
                  type(authority["public_key_hex"]) is str and
                  len(authority["public_key_hex"]) == 64 and
                  authority["successor_plan_sha256"] == successor_plan["sha256"] and
                  authority["successor_output"] == successor_output,
                  "reconciliation_authority_not_enrolled_for_successor")
    successor_dir = smoke.output_path(root, successor_output)
    smoke.require(not (historical_readback and post_worker_readback),
                  "ambiguous_successor_readback_mode")
    if historical_readback or post_worker_readback:
        smoke.require(allow_successor_created and
                      (successor_dir / ("execution.json" if historical_readback
                                        else "worker-result.json")).is_file() and
                      not (successor_dir / "INVALIDATED.json").exists(),
                      "completed_worker_or_successor_required_for_readback")
        successor_intent = loads(_read(root,
            (successor_dir / "intent.json").relative_to(root).as_posix(),
            smoke.descriptor(root, successor_dir / "intent.json")["sha256"]))
        smoke.require(successor_intent.get("version") == "paper-converter-intent-v1" and
                      successor_intent.get("plan") == successor_plan and
                      successor_intent.get("attempt") == 1,
                      "historical_successor_intent_differs")
        authorized_at = smoke.stamp(successor_intent["started_at"])
    else:
        authorized_at = smoke.stamp(smoke.now())
    smoke.require(authorized_at <= smoke.stamp(authority["expires_at"]),
                  "reconciliation_authority_expired_for_action")
    envelope = loads(_read(root, receipt_relative, receipt_sha256))
    _exact(envelope, {"version", "issuer", "issued_at", "payload", "signature"},
           "invalid_reconciliation_receipt")
    smoke.require(envelope["version"] == RECEIPT_VERSION and
                  envelope["issuer"] == authority["issuer"] and
                  smoke.stamp(envelope["issued_at"]) <= authorized_at and
                  smoke.stamp(envelope["issued_at"]) <= smoke.stamp(authority["expires_at"]),
                  "reconciliation_receipt_issuer_or_time_differs")
    payload = envelope["payload"]
    _exact(payload, {"old_output", "old_registry", "old_intent", "old_invalidation",
                     "old_inventory", "closure", "historical_outcome", "successor_plan",
                     "successor_output", "old_retry_authorized"},
           "invalid_reconciliation_payload")
    smoke.require(payload["historical_outcome"] == "UNKNOWN_UNATTESTED_NO_RETRY" and
                  payload["old_retry_authorized"] is False and
                  payload["successor_plan"] == successor_plan and
                  payload["successor_output"] == successor_output and
                  payload["old_output"] != successor_output,
                  "reconciliation_scope_differs")
    smoke.require(type(envelope["signature"]) is str, "invalid_reconciliation_signature")
    try:
        signature = base64.b64decode(envelope["signature"], validate=True)
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(authority["public_key_hex"]))
        key.verify(signature, canonical_bytes({key: envelope[key] for key in
                     ("version", "issuer", "issued_at", "payload")}))
    except (ValueError, InvalidSignature) as exc:
        raise ValueError("reconciliation_signature_untrusted") from exc
    old_output = payload["old_output"]
    registry_relative = ".paper-converter-attempts/" + smoke.sha(old_output.encode()) + ".json"
    smoke.require(payload["old_registry"]["relative"] == registry_relative and
                  payload["old_registry"]["sha256"] == authority["old_registry_sha256"],
                  "old_registry_identity_differs")
    registry = loads(_read(root, **payload["old_registry"]))
    _exact(registry, {"version", "output", "plan", "intent_sha256"}, "invalid_old_registry")
    smoke.require(registry["version"] == "paper-converter-active-attempt-v1" and
                  registry["output"] == old_output and
                  registry["intent_sha256"] == payload["old_intent"]["sha256"] and
                  registry["plan"]["sha256"] != successor_plan["sha256"],
                  "old_attempt_or_successor_plan_differs")
    old_dir = smoke.output_path(root, old_output)
    smoke.require(payload["old_intent"]["relative"] == (old_dir / "intent.json").relative_to(root).as_posix() and
                  payload["old_invalidation"]["relative"] == (old_dir / "INVALIDATED.json").relative_to(root).as_posix(),
                  "old_attempt_receipt_path_differs")
    intent = loads(_read(root, **payload["old_intent"]))
    invalidation = loads(_read(root, **payload["old_invalidation"]))
    _exact(intent, {"version", "plan", "started_at", "mode", "attempt", "controller_pid"},
           "invalid_old_intent")
    smoke.require(intent["version"] == "paper-converter-intent-v1" and
                  intent["plan"] == registry["plan"] and intent["attempt"] == 1 and
                  type(intent["controller_pid"]) is int and intent["controller_pid"] > 0,
                  "old_intent_binding_differs")
    _exact(invalidation, {"version", "at", "reason", "unknown_outcome"},
           "invalid_old_invalidation")
    smoke.require(invalidation["version"] == "paper-converter-invalidated-v1" and
                  invalidation["unknown_outcome"] is True and
                  smoke.stamp(invalidation["at"]) >= smoke.stamp(intent["started_at"]),
                  "old_attempt_not_invalidated_unknown")
    old_plan = loads(_read(root, **registry["plan"]))
    smoke.require(old_plan.get("engine", {}).get("name") in smoke.METHODS and
                  old_plan["mode"] == intent["mode"], "old_plan_identity_differs")
    smoke.require(payload["old_inventory"] == _inventory(root, old_output) and
                  any(row["relative"] == payload["old_intent"]["relative"] for row in payload["old_inventory"]) and
                  any(row["relative"] == payload["old_invalidation"]["relative"] for row in payload["old_inventory"]),
                  "old_attempt_inventory_changed")
    closure = _closure(root, payload["closure"], intent,
                       payload["old_intent"]["sha256"], old_plan,
                       invalidation, payload["old_invalidation"], old_output)
    if not allow_successor_created:
        smoke.require(not successor_dir.exists(),
                      "successor_output_must_be_absent")
    return {"old_registry_relative": registry_relative,
            "old_registry_sha256": payload["old_registry"]["sha256"],
            "old_output": old_output,
            "authority_relative": authority_relative,
            "authority_sha256": authority_sha256,
            "receipt_relative": receipt_relative,
            "receipt_sha256": receipt_sha256,
            "successor_plan": successor_plan,
            "successor_output": successor_output,
            "old_controller_pid": intent["controller_pid"],
            "old_worker_pid": closure["worker"]["worker_pid"],
            "old_engine": old_plan["engine"]["name"],
            "old_runtime_executable_relative": old_plan["runtime"]["executable"]["relative"],
            "historical_readback": historical_readback,
            "post_worker_readback": post_worker_readback,
            "historical_outcome": "UNKNOWN_UNATTESTED_NO_RETRY"}


def recheck(root, proof, *, allow_successor_created=False,
            post_worker_readback=False):
    current = verify_reconciliation(root,
        authority_relative=proof["authority_relative"],
        authority_sha256=proof["authority_sha256"],
        receipt_relative=proof["receipt_relative"],
        receipt_sha256=proof["receipt_sha256"],
        successor_plan=proof["successor_plan"],
        successor_output=proof["successor_output"],
        allow_successor_created=allow_successor_created,
        historical_readback=proof["historical_readback"],
        post_worker_readback=post_worker_readback)
    expected = dict(proof, post_worker_readback=post_worker_readback)
    smoke.require(current == expected, "reconciliation_changed")
    return current


def verify_live_exclusion(proof, observation):
    """Check a fresh observation supplied by an enrolled owning application.

    The application must hold its launch exclusion through the whole successor
    worker and perform the OS/server inspection; this helper cannot establish
    that authority or reconstruct a historic process tree from a PID alone.
    """
    _exact(observation, {"old_controller_pid", "old_worker_pid", "observed_at",
                         "controller_absent", "worker_absent", "descendants_absent",
                         "provider_idle", "launch_exclusion_held"},
           "invalid_live_closure_observation")
    observed = smoke.stamp(observation["observed_at"])
    age = dt.datetime.now(dt.timezone.utc) - observed
    smoke.require(dt.timedelta(0) <= age <= dt.timedelta(seconds=5) and
                  observation["old_controller_pid"] == proof["old_controller_pid"] and
                  observation["old_worker_pid"] == proof["old_worker_pid"] and
                  observation["controller_absent"] is True and
                  observation["worker_absent"] is True and
                  observation["descendants_absent"] is True and
                  observation["launch_exclusion_held"] is True and
                  (proof["old_engine"] != "grobid" or
                   observation["provider_idle"] is True),
                  "live_closure_or_launch_exclusion_unproved")
    return observation
