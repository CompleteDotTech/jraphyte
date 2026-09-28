"""Versioned runtime and saved-native identities for cached PDF experiments.

This module never invokes a converter/provider. Capture imports legacy archived
native bytes only after the caller supplies the expected results hash; it does
not claim that archived native bytes were re-extracted in the current runtime.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import struct
import sys
import unicodedata

from trace_gc.pdf_source_parallel_v4 import digest_value, validate_lines
from .common import REPO, child, data_root, digest, read_hashed_json, verify_files, within, write_once

DEFAULT_RUNTIME_LOCK = Path(__file__).with_name("runtime-windows-py312.lock.json")
DEPENDENCIES = ("attrs", "cffi", "cryptography", "jsonschema", "jsonschema-specifications",
                "Pillow", "pycparser", "PyMuPDF", "referencing", "rpds-py", "typing-extensions")
SHA256 = re.compile(r"[a-f0-9]{64}")


class InputGateError(ValueError):
    """Only curated codes and relative identifiers may cross this boundary."""

    def __init__(self, code: str, **details):
        super().__init__(code)
        self.code, self.details = code, details


def runtime_environment() -> dict:
    try:
        import fitz
        packages = {name: importlib.metadata.version(name) for name in DEPENDENCIES}
    except (ImportError, importlib.metadata.PackageNotFoundError) as exc:
        raise InputGateError("runtime_dependency_missing", action="install_locked_replay_requirements") from exc
    if fitz.VersionBind != packages["PyMuPDF"]:
        raise InputGateError("loaded_pymupdf_differs_from_installed_distribution", action="restart_with_locked_runtime")
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "python_build": list(platform.python_build()), "unicode": unicodedata.unidata_version,
            "system": platform.system(), "machine": platform.machine(), "pointer_bits": struct.calcsize("P")*8,
            "platform": platform.platform(), "mupdf": fitz.VersionFitz, "packages": packages}


def runtime_receipt(lock: Path = DEFAULT_RUNTIME_LOCK) -> dict:
    try:
        expected, lock_sha = read_hashed_json(lock)
        current = runtime_environment()
        if not isinstance(expected, dict) or expected.get("schema_version") != 1 or not isinstance(expected.get("environment"), dict):
            raise InputGateError("invalid_runtime_lock", action="supply_versioned_runtime_lock")
        if expected["environment"] != current:
            keys = sorted(k for k in set(current) | set(expected["environment"])
                          if current.get(k) != expected["environment"].get(k))
            raise InputGateError("runtime_lock_mismatch", differing_fields=keys,
                                 action="use_locked_interpreter_or_record_new_experiment_profile")
        identities = {}
        for name in DEPENDENCIES:
            distribution = importlib.metadata.distribution(name)
            identities[name] = {
                "version": current["packages"][name],
                "metadata_sha256": digest_value(distribution.read_text("METADATA") or ""),
                "wheel_sha256": digest_value(distribution.read_text("WHEEL") or ""),
                "native_libraries": {
                    p.as_posix(): digest(Path(distribution.locate_file(p)))
                    for p in distribution.files or []
                    if p.suffix.lower() in {".pyd", ".dll", ".so", ".dylib"}
                }}
        if digest(lock) != lock_sha:
            raise InputGateError("runtime_lock_changed_during_verification", action="restore_lock_and_restart")
        value = {"schema_version": 1, "lock_sha256": lock_sha, "environment": current,
                 "distribution_identities": identities,
                 "scope": "cached_conversion_experiment_runtime_not_model_or_quality_qualification"}
        value["runtime_sha256"] = digest_value(value)
        return value
    except InputGateError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise InputGateError("runtime_lock_unreadable_or_invalid", action="check_runtime_lock") from exc


def configure_baseline(root: Path):
    """Validate every cached import-time root before running any assessment."""
    root = root.resolve()
    configured = os.environ.get("TRACE_GC_TEST_DATA_ROOT")
    if configured and Path(configured).expanduser().resolve() != root:
        raise InputGateError("data_root_environment_mismatch", action="align_data_root_and_environment")
    os.environ["TRACE_GC_TEST_DATA_ROOT"] = str(root)
    common = importlib.import_module("src.abstract_validation.common")
    if common.DATA.resolve() != root:
        raise InputGateError("baseline_import_root_mismatch", action="restart_python_with_correct_data_root")
    old = importlib.import_module("src.abstract_validation_expanded.extraction")
    prefixes = {"src.abstract_validation": "validation_200_10k",
                "src.abstract_validation_v2": "validation_v2",
                "src.abstract_validation_expanded": "validation_expanded200"}
    for name, module in list(sys.modules.items()):
        prefix = next((p for p in prefixes if name == p or name.startswith(p+".")), None)
        if prefix is None:
            continue
        location = Path(module.__file__).resolve()
        if REPO.resolve() not in location.parents:
            raise InputGateError("baseline_import_from_other_checkout", action="restart_python_in_selected_checkout")
        for field, expected in {"DATA":root,"OUT":root/prefixes[prefix]}.items():
            if hasattr(module, field) and Path(getattr(module, field)).resolve() != expected:
                raise InputGateError("baseline_import_root_mismatch", action="restart_python_with_correct_data_root")
    return old


def verify_native_manifest(root: Path, path: Path, expected_sha256: str) -> dict:
    """Verify an externally pinned manifest and every archived native payload."""
    if not isinstance(expected_sha256, str) or not SHA256.fullmatch(expected_sha256):
        raise InputGateError("native_manifest_expected_hash_required", action="supply_recorded_manifest_sha256")
    try:
        root = root.resolve()
        path = within(root,path)
        value, manifest_sha = read_hashed_json(path)
        if manifest_sha != expected_sha256:
            raise InputGateError("native_manifest_hash_mismatch", action="use_original_manifest")
        snapshots = {within(root,path).relative_to(root).as_posix(): manifest_sha}
        if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("cases"), list):
            raise InputGateError("invalid_native_manifest", action="capture_native_manifest")
        identities = set()
        for row in value["cases"]:
            sid = row["id"]
            if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", sid) or sid in identities:
                raise InputGateError("native_manifest_case_identity_invalid")
            identities.add(sid)
            native_path = child(root, row["native_relative"])
            native, native_sha = read_hashed_json(native_path)
            if native_sha != row["file_sha256"]:
                raise InputGateError("native_file_hash_mismatch", case_id=sid)
            snapshots[native_path.relative_to(root).as_posix()] = native_sha
            if digest_value(native) != row["native_sha256"]:
                raise InputGateError("native_representation_hash_mismatch", case_id=sid)
            validate_lines(native, row["page_size"])
            if not all(isinstance(row.get(k), str) and SHA256.fullmatch(row[k])
                       for k in ("source_sha256", "page_sha256", "image_sha256")):
                raise InputGateError("native_source_identity_invalid", case_id=sid)
        if not identities or not isinstance(value.get("extractor_identity"), dict):
            raise InputGateError("native_extractor_identity_required")
        try:
            verify_files(root,snapshots)
        except (OSError,ValueError) as exc:
            raise InputGateError("native_inputs_changed_during_verification", action="restore_archive_and_retry") from exc
        return value
    except InputGateError:
        raise
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise InputGateError("native_manifest_unreadable_or_invalid", action="check_external_native_manifest") from exc


def capture_archived_native(root: Path, run: Path, expected_results_sha256: str, output: Path) -> dict:
    """Bind a selected historical run without editing it or inventing provenance.

    Source binding is checked against the original page receipt and each saved
    assessment. The old run supplied only Python/PyMuPDF and partial code hashes;
    retain that provenance limitation rather than backfilling the current runtime.
    """
    try:
        root = root.resolve()
        run, output = within(root,run), within(root,output)
        snapshots = {}
        def load(path):
            path = within(root,path)
            value, sha = read_hashed_json(path)
            snapshots[path.relative_to(root).as_posix()] = sha
            return value, sha
        results_path, preflight_path = run/"results.json", run/"preflight.json"
        results, results_sha = load(results_path)
        if not isinstance(expected_results_sha256,str) or not SHA256.fullmatch(expected_results_sha256) or results_sha != expected_results_sha256:
            raise InputGateError("archived_results_hash_mismatch")
        gate, preflight_sha = load(preflight_path)
        protocol, protocol_sha = load(run/"protocol.json")
        if not all(isinstance(v,dict) for v in (results,gate,protocol)):
            raise InputGateError("invalid_archived_run_receipt")
        if gate.get("status") != "PASS" or not isinstance(gate.get("verified_sources"), list):
            raise InputGateError("archived_source_preflight_required")
        rows = []
        for source in gate["verified_sources"]:
            sid = source["id"]
            if not re.fullmatch(r"f\d{3}", sid):
                raise InputGateError("invalid_archived_case_id")
            page = root/("validation_v2" if int(sid[1:]) <= 100 else "validation_expanded200")/"pages"/sid
            receipt, _ = load(page/"receipt.json")
            if any(source[k] != receipt[r] for k, r in
                   (("source_sha256", "source_sha256"), ("page_sha256", "page_pdf_sha256"), ("image_sha256", "image_sha256"))):
                raise InputGateError("archived_source_binding_mismatch", case_id=sid)
            native_path = run/"native"/(sid+".json")
            native, native_sha = load(native_path)
            validate_lines(native, receipt["page_size"])
            for method in results["details"]:
                prediction, _ = load(run/"assessments"/method/(sid+".json"))
                if not isinstance(prediction,dict):
                    raise InputGateError("invalid_archived_assessment",case_id=sid)
                if prediction.get("source_sha256") != source["source_sha256"] or prediction.get("page_sha256") != source["page_sha256"]:
                    raise InputGateError("archived_assessment_source_mismatch", case_id=sid)
            rows.append({**source, "page_size": receipt["page_size"],
                         "native_relative": native_path.relative_to(root).as_posix(),
                         "file_sha256": native_sha, "native_sha256": digest_value(native)})
        if len(rows) != 200 or len({row["id"] for row in rows}) != 200:
            raise InputGateError("archived_exact_200_cases_required")
        manifest = {"schema_version": 1, "mode": "imported_historical_saved_native",
                    "results_sha256": results_sha, "preflight_sha256": preflight_sha,
                    "protocol_sha256": protocol_sha, "cases": rows,
                    "archive_input_hashes": snapshots,
                    "extractor_identity": {"reported_environment": results.get("environment", {}),
                        "reported_method_hashes": protocol.get("method_hashes", {}),
                        "provenance_limit": "historical_report_incomplete_runtime_identity_not_current_reextraction"}}
        try:
            verify_files(root,snapshots)
        except (OSError,ValueError) as exc:
            raise InputGateError("archive_changed_during_capture", action="restore_archive_and_use_new_output") from exc
        sha = write_once(output, manifest)
        return {"status": "CAPTURED_SAVED_NATIVE_NOT_REEXTRACTED", "cases": len(rows), "manifest_sha256": sha}
    except InputGateError:
        raise
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise InputGateError("archived_native_capture_failed", action="verify_authorized_archive_layout") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("capture-lock", "verify-lock", "capture-native"))
    parser.add_argument("--data-root")
    parser.add_argument("--output")
    parser.add_argument("--runtime-lock", type=Path, default=DEFAULT_RUNTIME_LOCK)
    parser.add_argument("--run")
    parser.add_argument("--results-sha256")
    args = parser.parse_args()
    try:
        if args.stage == "verify-lock":
            receipt = runtime_receipt(args.runtime_lock)
            result = {"status": "PASS", "runtime_sha256": receipt["runtime_sha256"],
                      "environment": receipt["environment"]}
        else:
            if not args.output:
                parser.error("--output is required for capture")
            root = data_root(args.data_root)
            destination = child(root, args.output)
            if args.stage == "capture-lock":
                value = {"schema_version": 1, "environment": runtime_environment(),
                         "scope": "explicit_new_runtime_profile_not_historical_or_quality_qualification"}
                result = {"status": "CAPTURED_RUNTIME_PROFILE", "lock_sha256": write_once(destination, value)}
            else:
                if not args.run or not args.results_sha256:
                    parser.error("capture-native requires --run and --results-sha256")
                result = capture_archived_native(root, child(root, args.run), args.results_sha256, destination)
    except InputGateError as exc:
        result = {"status": "BLOCKED", "reason": exc.code, **exc.details}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"status":"BLOCKED", "reason":"invalid_runtime_capture_configuration",
                  "error_class":type(exc).__name__, "action":"check_authorized_root_and_new_output_path"}
    print(json.dumps(result, sort_keys=True))
    return 2 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
