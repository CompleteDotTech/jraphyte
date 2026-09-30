"""Versioned, source-replayed adoption of sealed Docling conversions from a stopped run.

The origin run stays immutable. The new run re-assesses imported documents under
its own code identity and continues only after every import has a durable row.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from trace_gc.pdf_source_parallel_v4 import SourceGeometry, digest_value
from trace_gc.pdf_structure_parallel_v4 import assess_document, seal

from . import assessment_producer as producer
from .common import REPO, child, data_root, digest, method_hashes, write_once
from .extraction import validate_cached_input
from .fields import source_path
from .retrieval import verify_source_bound_assessment
from .runtime import runtime_receipt

VERSION = "retrieval-assessment-migration-v1"
ROW_VERSION = "retrieval-assessment-migrated-row-v1"


def _read(path: Path, expected: str | None = None):
    return producer._read(path, expected)[0]


def _origin_audit(root: Path, old_output: Path, old_checkout: Path,
                  old_interpreter: Path, expected_head: str) -> dict:
    """Use the unchanged old checkout to source-replay every completed receipt."""
    if (not old_checkout.is_dir() or not old_interpreter.is_file() or
            old_checkout.resolve() == REPO.resolve()):
        raise ValueError("separate_frozen_origin_runtime_required")
    protocol = _read(old_output / "protocol.json")
    # The evaluator and the Docling converter use different pinned interpreters.
    # The child converter is authenticated through its profile and session receipt;
    # this interpreter must match the evaluator runtime in the old protocol.
    profile = _read(child(root, protocol["profile_relative"]), protocol["profile_sha256"])
    converter_executable = child(root, profile["runtime"]["executable"])
    if digest(converter_executable) != profile["runtime"]["executable_sha256"]:
        raise ValueError("origin_converter_interpreter_identity_mismatch")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=old_checkout,
                                   text=True).strip()
    if head != expected_head or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=old_checkout, text=True).strip():
        raise ValueError("origin_checkout_not_frozen_at_expected_head")
    script = r'''
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[3])
from src.parallel_source_v4 import assessment_producer as p
from src.parallel_source_v4.common import method_hashes
from src.parallel_source_v4.runtime import runtime_receipt
root=Path(sys.argv[1]);output=Path(sys.argv[2])
protocol,protocol_hash=p._read(output/'protocol.json')
assert method_hashes(p.REPO)==protocol['code_sha256'],'origin_code_changed'
assert runtime_receipt()==protocol['evaluator_runtime'],'origin_evaluator_runtime_changed'
manifest,_=p._read(root/protocol['manifest_relative'],protocol['manifest_sha256'])
profile,_=p._read(root/protocol['profile_relative'],protocol['profile_sha256'])
p._profile(root,profile)
rows={r['sample_id']:r for r in manifest['pdfs']}
source_root=Path(protocol['source_root']) if protocol['source_root'] else None
hashes=[]
for sid in protocol['ids']:
    path=output/'rows'/(sid+'.json')
    if not path.is_file():break
    receipt,h=p._read(path)
    p._verify_receipt(root,rows[sid],receipt,output,source_root,protocol)
    hashes.append([sid,h])
print(json.dumps({'origin_protocol_sha256':protocol_hash,'completed_rows':len(hashes),
                  'row_hashes':hashes},sort_keys=True,separators=(',',':')))
'''
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run([str(old_interpreter), "-B", "-s", "-c", script,
        str(root), str(old_output), str(old_checkout)], cwd=old_checkout, env=env,
        capture_output=True, text=True, timeout=3600)
    if result.returncode:
        raise ValueError("origin_frozen_audit_failed:" + result.stderr[-2000:])
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    if len(lines) != 1:
        raise ValueError("origin_frozen_audit_receipt_missing")
    return json.loads(lines[0])


def _origin_records(root: Path, old_output: Path, old_protocol: dict) -> list[dict]:
    """Require a completed-row prefix and exactly one next sealed conversion."""
    records = []
    old_hash = digest(old_output / "protocol.json")
    for sid in old_protocol["ids"]:
        row_path = old_output / "rows" / (sid + ".json")
        attempt = old_output / "attempts" / sid
        if not row_path.is_file() and not attempt.exists():
            break
        if not attempt.is_dir():
            raise ValueError("migration_attempt_missing:" + sid)
        intent_path, conversion_path = attempt / "intent.json", attempt / "conversion.json"
        intent, conversion = _read(intent_path), _read(conversion_path)
        if intent.get("sample_id") != sid or intent.get("protocol_sha256") != old_hash:
            raise ValueError("migration_origin_intent_mismatch:" + sid)
        if conversion.get("model_called") is not True or conversion.get("status") not in {"success", "error"}:
            raise ValueError("migration_origin_conversion_not_sealed:" + sid)
        doc_hash = conversion.get("document_sha256")
        if doc_hash is not None:
            producer._read(attempt / "document.json", doc_hash)
        elif (attempt / "document.json").exists():
            raise ValueError("migration_unbound_origin_document:" + sid)
        receipt_hash = digest(row_path) if row_path.is_file() else None
        records.append({"sample_id": sid,
            "origin_receipt_sha256": receipt_hash,
            "origin_intent_sha256": digest(intent_path),
            "origin_conversion_sha256": digest(conversion_path),
            "origin_document_sha256": doc_hash})
        if receipt_hash is None:
            break
    if (not records or records[-1]["origin_receipt_sha256"] is not None or
            any(r["origin_receipt_sha256"] is None for r in records[:-1])):
        raise ValueError("migration_requires_one_sealed_pending_conversion")
    if any((old_output / "attempts" / sid).exists() or
           (old_output / "rows" / (sid + ".json")).exists()
           for sid in old_protocol["ids"][len(records):]):
        raise ValueError("migration_later_origin_work_requires_reconciliation")
    known = set(old_protocol["ids"])
    for folder in (old_output / "attempts", old_output / "rows"):
        if folder.is_dir() and any(p.stem not in known for p in folder.iterdir()):
            raise ValueError("migration_unknown_origin_artifact")
    return records


def prepare_plan(root: Path, old_output: Path, new_output: Path, old_checkout: Path,
                 old_interpreter: Path, expected_head: str, expected_protocol_sha: str,
                 expected_import_count: int) -> tuple[Path, dict]:
    """Read-only origin audit, followed by one immutable plan outside both runs."""
    if old_output.resolve() == new_output.resolve() or not old_output.is_dir() or new_output.exists():
        raise ValueError("fresh_distinct_migration_output_required")
    old_protocol, old_hash = producer._read(old_output / "protocol.json", expected_protocol_sha)
    manifest = _read(child(root, old_protocol["manifest_relative"]), old_protocol["manifest_sha256"])
    _read(child(root, old_protocol["profile_relative"]), old_protocol["profile_sha256"])
    if (manifest.get("query_independent") is not True or
            old_protocol["ids"] != [r["sample_id"] for r in manifest["pdfs"]]):
        raise ValueError("migration_original_manifest_identity_mismatch")
    records = _origin_records(root, old_output, old_protocol)
    if len(records) != expected_import_count:
        raise ValueError("migration_import_count_mismatch")
    audited = _origin_audit(root, old_output, old_checkout, old_interpreter, expected_head)
    expected_rows = [[r["sample_id"], r["origin_receipt_sha256"]] for r in records[:-1]]
    if (audited.get("origin_protocol_sha256") != old_hash or
            audited.get("completed_rows") != len(expected_rows) or
            audited.get("row_hashes") != expected_rows):
        raise ValueError("migration_frozen_source_replay_mismatch")
    plan = {"schema_version": VERSION,
        "origin_run_relative": old_output.relative_to(root).as_posix(),
        "origin_protocol_sha256": old_hash, "origin_head": expected_head,
        "origin_code_sha256": old_protocol["code_sha256"],
        "origin_evaluator_runtime": old_protocol["evaluator_runtime"],
        "manifest_relative": old_protocol["manifest_relative"],
        "manifest_sha256": old_protocol["manifest_sha256"],
        "profile_relative": old_protocol["profile_relative"],
        "profile_sha256": old_protocol["profile_sha256"],
        "source_root": old_protocol["source_root"], "ids": old_protocol["ids"],
        "new_code_sha256": method_hashes(REPO), "new_evaluator_runtime": runtime_receipt(),
        "origin_rows_source_replayed": len(expected_rows), "imports": records,
        "old_run_immutable": True, "query_independent": True,
        "new_model_calls_for_imports": 0}
    path = new_output.parent / (new_output.name + ".migration-v1.json")
    write_once(path, plan)
    return path, plan


def _validate_origin_attempt(root: Path, plan: dict, record: dict, row: dict):
    old_output = child(root, plan["origin_run_relative"])
    sid = record["sample_id"]
    old_protocol = _read(old_output / "protocol.json", plan["origin_protocol_sha256"])
    folder = old_output / "attempts" / sid
    intent = _read(folder / "intent.json", record["origin_intent_sha256"])
    conversion = _read(folder / "conversion.json", record["origin_conversion_sha256"])
    expected_hashes = {key: row[key + "_sha256"] for key in ("source", "page", "image", "native")}
    if (intent.get("sample_id") != sid or intent.get("protocol_sha256") != plan["origin_protocol_sha256"] or
            any(intent.get(key + "_sha256") != value for key, value in expected_hashes.items()) or
            conversion.get("model_called") is not True or conversion.get("status") not in {"success", "error"} or
            conversion.get("document_sha256") != record["origin_document_sha256"] or
            conversion.get("runtime") != {key: _read(child(root, plan["profile_relative"]))["runtime"][key]
                                           for key in ("python", "executable_sha256", "packages")}):
        raise ValueError("migration_origin_attempt_identity_mismatch:" + sid)
    if (conversion.get("status") == "success" and
            (conversion.get("docling_status") != "ConversionStatus.SUCCESS" or
             record["origin_document_sha256"] is None or conversion.get("error_class") is not None)):
        raise ValueError("migration_origin_success_not_authenticated:" + sid)
    start = conversion.get("session_start")
    if not isinstance(start, dict) or set(start) != {"relative", "sha256"}:
        raise ValueError("migration_origin_session_missing:" + sid)
    session = _read(child(root, start["relative"]), start["sha256"])
    if (session.get("protocol_sha256") != plan["origin_protocol_sha256"] or
            session.get("code_sha256") != old_protocol["code_sha256"] or
            session.get("converter_profile_sha256") != plan["profile_sha256"] or
            session.get("worker_pid") != conversion.get("worker_pid") or
            session.get("runtime") != conversion.get("runtime") or
            session.get("network_guard") != "nonlocal_connect_denied"):
        raise ValueError("migration_origin_session_identity_mismatch:" + sid)
    document = None
    if record["origin_document_sha256"] is not None:
        document = _read(folder / "document.json", record["origin_document_sha256"])
    if record["origin_receipt_sha256"] is not None:
        receipt = _read(old_output / "rows" / (sid + ".json"), record["origin_receipt_sha256"])
        if (receipt.get("sample_id") != sid or receipt.get("protocol_sha256") != plan["origin_protocol_sha256"] or
                receipt.get("conversion_sha256") != record["origin_conversion_sha256"] or
                receipt.get("document_sha256") != record["origin_document_sha256"]):
            raise ValueError("migration_origin_row_changed:" + sid)
    return conversion, document


def verify_migrated_receipt(root: Path, row: dict, receipt: dict, output: Path,
                            source_root: Path | None, protocol: dict,
                            native: list[dict], page_size: list) -> None:
    descriptor = protocol.get("migration")
    if not isinstance(descriptor, dict) or set(descriptor) != {"relative", "sha256"}:
        raise ValueError("migration_protocol_binding_missing")
    plan = _read(child(root, descriptor["relative"]), descriptor["sha256"])
    if (plan.get("schema_version") != VERSION or plan.get("new_code_sha256") != protocol["code_sha256"] or
            plan.get("manifest_sha256") != protocol["manifest_sha256"] or
            plan.get("profile_sha256") != protocol["profile_sha256"] or
            plan.get("source_root") != protocol["source_root"]):
        raise ValueError("migration_plan_current_identity_mismatch")
    record = next((r for r in plan["imports"] if r["sample_id"] == row["sample_id"]), None)
    if record is None or receipt.get("migration_sha256") != descriptor["sha256"]:
        raise ValueError("migration_row_not_in_plan")
    expected_conversion = (child(root, plan["origin_run_relative"]) / "attempts" /
                           row["sample_id"] / "conversion.json").relative_to(root).as_posix()
    expected_assessment = (output / "assessments" / producer.METHOD /
                           (row["sample_id"] + ".json")).relative_to(root).as_posix()
    if (receipt.get("conversion_relative") != expected_conversion or
            receipt.get("assessment_relative") != expected_assessment):
        raise ValueError("migration_row_artifact_path_mismatch")
    conversion, document = _validate_origin_attempt(root, plan, record, row)
    if (receipt.get("origin_protocol_sha256") != plan["origin_protocol_sha256"] or
            receipt.get("origin_attempt_sha256") != record["origin_intent_sha256"] or
            receipt.get("origin_row_receipt_sha256") != record["origin_receipt_sha256"] or
            receipt.get("conversion_sha256") != record["origin_conversion_sha256"] or
            receipt.get("document_sha256") != record["origin_document_sha256"] or
            receipt.get("new_model_call") is not False or
            receipt.get("state") != ("complete" if conversion["status"] == "success" else "error") or
            receipt.get("wall_seconds") != conversion["wall_seconds"]):
        raise ValueError("migration_row_lineage_mismatch")
    if conversion["status"] == "success":
        if document is None:
            raise ValueError("migration_success_document_missing")
        validate_cached_input("docling_document", document, page_size=page_size)
    elif document is not None:
        # Error attempts may carry a bounded partial document; never label it success.
        pass
    assessment = _read(child(root, receipt["assessment_relative"]), receipt["assessment_sha256"])
    stage = assessment.get("conversion_stage", {})
    if (assessment.get("status") != receipt.get("assessment_status") or
            stage.get("new_model_conversion") is not False or
            stage.get("origin_model_called") is not True or
            stage.get("origin_protocol_sha256") != plan["origin_protocol_sha256"] or
            stage.get("origin_attempt_sha256") != record["origin_intent_sha256"] or
            stage.get("origin_row_receipt_sha256") != record["origin_receipt_sha256"] or
            stage.get("migration_manifest_sha256") != descriptor["sha256"] or
            stage.get("input_hashes", {}).get("docling") != record["origin_conversion_sha256"] or
            stage.get("input_hashes", {}).get("docling_document") != record["origin_document_sha256"]):
        raise ValueError("migration_assessment_lineage_mismatch")
    geometry = SourceGeometry.from_pdf(source_path(root, row, source_root).read_bytes(), native,
                                       expected_source_sha256=row["source_sha256"])
    verify_source_bound_assessment(assessment, native, page_size=page_size,
        source_sha256=row["source_sha256"], page_sha256=row["page_sha256"],
        source_geometry=geometry)


def _initialize_imports(root: Path, output: Path, manifest: dict, protocol: dict,
                        source_root: Path | None) -> None:
    descriptor = protocol["migration"]
    plan = _read(child(root, descriptor["relative"]), descriptor["sha256"])
    rows = {r["sample_id"]: r for r in manifest["pdfs"]}
    if (plan["ids"] != protocol["ids"] or plan["new_code_sha256"] != protocol["code_sha256"] or
            plan["new_evaluator_runtime"] != protocol["evaluator_runtime"]):
        raise ValueError("migration_new_protocol_changed")
    for record in plan["imports"]:
        producer._check_code(protocol)
        sid = record["sample_id"]
        row = rows[sid]
        receipt_path = output / "rows" / (sid + ".json")
        if receipt_path.is_file():
            producer._verify_receipt(root, row, _read(receipt_path), output, source_root, protocol)
            continue
        native, size, decision = producer._verified_row(root, row, source_root)
        if decision != "eligible":
            raise ValueError("migration_origin_row_no_longer_eligible:" + sid)
        conversion, document = _validate_origin_attempt(root, plan, record, row)
        if conversion["status"] == "success":
            if document is None:
                raise ValueError("migration_success_document_missing:" + sid)
            validate_cached_input("docling_document", document, page_size=size)
        geometry = SourceGeometry.from_pdf(source_path(root, row, source_root).read_bytes(), native,
                                           expected_source_sha256=row["source_sha256"])
        assessment = assess_document(document or {}, page_size=size,
            source_sha256=row["source_sha256"], page_sha256=row["page_sha256"],
            native_lines=native, scholarly_abstract="", max_input_chars=4000,
            conversion_status=conversion["status"], source_geometry=geometry)
        assessment["source_hash_verification"] = "verified_original_page_native_image_during_migration"
        assessment["conversion_stage"] = {"status": conversion["status"],
            "input_hashes": {"docling": record["origin_conversion_sha256"],
                "docling_document": record["origin_document_sha256"]},
            "new_model_conversion": False, "origin_model_called": True,
            "origin_protocol_sha256": plan["origin_protocol_sha256"],
            "origin_attempt_sha256": record["origin_intent_sha256"],
            "origin_row_receipt_sha256": record["origin_receipt_sha256"],
            "migration_manifest_sha256": descriptor["sha256"],
            "session_start": conversion["session_start"],
            "converter_profile_sha256": plan["profile_sha256"],
            "wall_seconds": conversion["wall_seconds"]}
        seal(assessment)
        verify_source_bound_assessment(assessment, native, page_size=size,
            source_sha256=row["source_sha256"], page_sha256=row["page_sha256"],
            source_geometry=geometry)
        # Source files can change during assessment; repeat the complete readback
        # before sealing a row that claims the original source identity.
        native_after, size_after, decision_after = producer._verified_row(root, row, source_root)
        if native_after != native or size_after != size or decision_after != decision:
            raise ValueError("migration_source_changed_during_assessment:" + sid)
        path = output / "assessments" / producer.METHOD / (sid + ".json")
        assessment_hash = write_once(path, assessment)
        origin = child(root, plan["origin_run_relative"])
        conversion_relative = (origin / "attempts" / sid / "conversion.json").relative_to(root).as_posix()
        receipt = {"schema_version": ROW_VERSION, "sample_id": sid,
            "protocol_sha256": digest(output / "protocol.json"), "eligibility": decision,
            "source_hashes": {key: row[key + "_sha256"] for key in ("source", "page", "image", "native")},
            "state": "complete" if conversion["status"] == "success" else "error",
            "assessment_relative": path.relative_to(root).as_posix(),
            "assessment_sha256": assessment_hash, "assessment_status": assessment["status"],
            "conversion_relative": conversion_relative,
            "conversion_sha256": record["origin_conversion_sha256"],
            "document_sha256": record["origin_document_sha256"],
            "wall_seconds": conversion["wall_seconds"],
            "migration_sha256": descriptor["sha256"],
            "origin_protocol_sha256": plan["origin_protocol_sha256"],
            "origin_attempt_sha256": record["origin_intent_sha256"],
            "origin_row_receipt_sha256": record["origin_receipt_sha256"],
            "new_model_call": False}
        write_once(receipt_path, receipt)
        producer._verify_receipt(root, row, receipt, output, source_root, protocol)


def run_migrated(root: Path, old_output: Path, new_output: Path, old_checkout: Path,
                 old_interpreter: Path, expected_head: str, expected_protocol_sha: str,
                 expected_import_count: int) -> dict:
    old_protocol = _read(old_output / "protocol.json", expected_protocol_sha)
    plan_path = new_output.parent / (new_output.name + ".migration-v1.json")
    if plan_path.is_file():
        plan = _read(plan_path)
        if (plan.get("schema_version") != VERSION or
                plan.get("origin_protocol_sha256") != expected_protocol_sha or
                plan.get("origin_head") != expected_head or
                len(plan.get("imports", [])) != expected_import_count):
            raise ValueError("migration_existing_plan_identity_mismatch")
        # A crash resume repeats the frozen source replay, then pins the same plan.
        audit = _origin_audit(root, old_output, old_checkout, old_interpreter, expected_head)
        if (audit.get("origin_protocol_sha256") != expected_protocol_sha or
                audit.get("row_hashes") != [[r["sample_id"], r["origin_receipt_sha256"]]
                                               for r in plan["imports"][:-1]]):
            raise ValueError("migration_resumed_origin_audit_changed")
        if _origin_records(root, old_output, old_protocol) != plan["imports"]:
            raise ValueError("migration_resumed_origin_artifacts_changed")
    else:
        if new_output.exists():
            raise ValueError("migration_output_without_plan_requires_reconciliation")
        plan_path, plan = prepare_plan(root, old_output, new_output, old_checkout,
            old_interpreter, expected_head, expected_protocol_sha, expected_import_count)
    if (plan["new_code_sha256"] != method_hashes(REPO) or
            plan["new_evaluator_runtime"] != runtime_receipt()):
        raise ValueError("migration_new_code_or_runtime_changed")
    descriptor = {"relative": plan_path.relative_to(root).as_posix(), "sha256": digest(plan_path)}
    manifest = child(root, plan["manifest_relative"])
    profile = child(root, plan["profile_relative"])
    source_root = Path(plan["source_root"]) if plan["source_root"] else None
    return producer._run(root, manifest, profile, new_output, source_root,
        migration=descriptor, migration_initializer=_initialize_imports)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--origin-output", required=True)
    parser.add_argument("--new-output", required=True)
    parser.add_argument("--origin-checkout", required=True)
    parser.add_argument("--origin-interpreter", required=True)
    parser.add_argument("--origin-head", required=True)
    parser.add_argument("--origin-protocol-sha256", required=True)
    parser.add_argument("--expected-import-count", type=int, required=True)
    args = parser.parse_args()
    root = data_root(args.data_root)
    summary = run_migrated(root, child(root, args.origin_output),
        child(root, args.new_output), Path(args.origin_checkout).resolve(),
        Path(args.origin_interpreter).resolve(), args.origin_head,
        args.origin_protocol_sha256, args.expected_import_count)
    print(json.dumps({k: summary[k] for k in ("status", "document_count", "eligible_count", "state_counts")}))
    return 4 if summary["status"] == "STOPPED_DRAINED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
