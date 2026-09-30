"""Reassess mixed sealed rows and one sealed pending converter result.

The stopped origin is immutable. All imports are source-verified and consume
existing converter documents without making another converter call.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_gc.pdf_source_parallel_v4 import SourceGeometry
from trace_gc.pdf_structure_parallel_v4 import assess_document, seal

from . import assessment_migration as migration_v1
from . import assessment_migration_v2 as migration_v2
from . import assessment_producer as producer
from .common import REPO, child, data_root, digest, method_hashes, write_once
from .extraction import validate_cached_input
from .fields import source_path
from .retrieval import verify_source_bound_assessment
from .runtime import runtime_receipt

VERSION = "retrieval-assessment-mixed-pending-migration-v3"
ROW_VERSION = "retrieval-assessment-mixed-prefix-import-row-v3"
PENDING_ROW_VERSION = "retrieval-assessment-pending-import-row-v3"


def _read(path: Path, expected: str | None = None) -> dict:
    return producer._read(path, expected)[0]


def _prefix(root: Path, origin: Path, protocol: dict, expected_count: int) -> tuple[list[dict], dict]:
    """Require exact rows and one sealed, unassessed next conversion."""
    ids = protocol["ids"]
    if not 1 <= expected_count < len(ids):
        raise ValueError("prefix_count_out_of_range")
    row_dir, attempt_dir = origin / "rows", origin / "attempts"
    if not row_dir.is_dir() or not attempt_dir.is_dir():
        raise ValueError("origin_rows_or_attempts_missing")
    if {path.stem for path in row_dir.iterdir() if path.is_file()} != set(ids[:expected_count]) or any(
            not path.is_file() or path.suffix != ".json" for path in row_dir.iterdir()):
        raise ValueError("origin_row_prefix_not_exact")
    next_id = ids[expected_count]
    next_dir = attempt_dir / next_id
    if (not next_dir.is_dir() or next_dir.is_symlink() or
            getattr(next_dir.lstat(), "st_file_attributes", 0) & 0x400 or
            {p.name for p in next_dir.iterdir()} != {"intent.json", "conversion.json", "document.json"} or
            any(not p.is_file() or p.is_symlink() or
                getattr(p.lstat(), "st_file_attributes", 0) & 0x400 for p in next_dir.iterdir()) or
            (row_dir / (next_id + ".json")).exists() or
            (origin / "assessments" / producer.METHOD / (next_id + ".json")).exists()):
        raise ValueError("next_attempt_not_exact_sealed_unassessed_conversion")
    allowed = set(ids[:expected_count]) | {next_id}
    if any(not path.is_dir() or path.name not in allowed for path in attempt_dir.iterdir()):
        raise ValueError("later_or_unknown_attempt_requires_reconciliation")
    old_code = protocol["code_sha256"]
    if (not isinstance(old_code, dict) or
            old_code.get("src/parallel_source_v4/assessment_producer.py") !=
            digest(Path(protocol["stopped_execution_checkout"]) /
                   "src/parallel_source_v4/assessment_producer.py")):
        raise ValueError("origin_pre_intent_call_order_code_unverified")
    records = []
    for sid in ids[:expected_count]:
        receipt_path = row_dir / (sid + ".json")
        receipt, row_sha = producer._read(receipt_path)
        if receipt.get("sample_id") != sid or receipt.get("protocol_sha256") != digest(origin / "protocol.json"):
            raise ValueError("origin_row_identity_mismatch:" + sid)
        records.append({"sample_id": sid, "origin_row_sha256": row_sha,
                        "eligibility": receipt["eligibility"], "state": receipt["state"],
                        "assessment_sha256": receipt.get("assessment_sha256"),
                        "assessment_relative": receipt.get("assessment_relative")})
    intent_path, conversion_path, document_path = (next_dir / name for name in
        ("intent.json", "conversion.json", "document.json"))
    intent, intent_sha = producer._read(intent_path)
    conversion, conversion_sha = producer._read(conversion_path)
    document, document_sha = producer._read(document_path, conversion.get("document_sha256"))
    if (intent.get("sample_id") != next_id or
            intent.get("protocol_sha256") != digest(origin / "protocol.json") or
            conversion.get("status") != "success" or conversion.get("model_called") is not True or
            conversion.get("docling_status") != "ConversionStatus.SUCCESS" or
            conversion.get("error_class") is not None or
            document_sha != conversion.get("document_sha256")):
        raise ValueError("pending_conversion_lineage_invalid")
    return records, {"sample_id": next_id, "origin_receipt_sha256": None,
        "origin_intent_sha256": intent_sha, "origin_conversion_sha256": conversion_sha,
        "origin_document_sha256": document_sha}


def prepare_plan(root: Path, origin: Path, output: Path, old_checkout: Path,
                 old_interpreter: Path, old_head: str, old_protocol_sha256: str,
                 expected_count: int, max_documents_per_session: int) -> tuple[Path, dict]:
    if (output.exists() or not origin.is_dir() or
            origin.resolve() in (output.resolve(), *output.resolve().parents) or
            output.resolve() in origin.resolve().parents):
        raise ValueError("fresh_distinct_bounded_output_required")
    old_protocol = _read(origin / "protocol.json", old_protocol_sha256)
    if (old_protocol.get("query_independent") is not True or
            old_protocol.get("scope") != "FULL_CORPUS" or
            old_protocol.get("ids") != [r["sample_id"] for r in _read(
                child(root, old_protocol["manifest_relative"]), old_protocol["manifest_sha256"])["pdfs"]]):
        raise ValueError("origin_full_query_independent_manifest_required")
    old_protocol = dict(old_protocol, stopped_execution_checkout=str(old_checkout.resolve()))
    records, pending = _prefix(root, origin, old_protocol, expected_count)
    audited = migration_v1._origin_audit(root, origin, old_checkout, old_interpreter, old_head)
    if (audited.get("origin_protocol_sha256") != old_protocol_sha256 or
            audited.get("completed_rows") != expected_count or
            audited.get("row_hashes") != [[r["sample_id"], r["origin_row_sha256"]] for r in records]):
        raise ValueError("complete_origin_source_replay_mismatch")
    if type(max_documents_per_session) is not int or not 1 <= max_documents_per_session <= 64:
        raise ValueError("bounded_new_session_limit_required")
    plan_path = output.parent / (output.name + ".mixed-pending-migration-v3.json")
    plan = {"schema_version": VERSION, "origin_run_relative": origin.relative_to(root).as_posix(),
            "origin_protocol_sha256": old_protocol_sha256, "origin_head": old_head,
            "origin_code_sha256": old_protocol["code_sha256"],
            "origin_evaluator_runtime": old_protocol["evaluator_runtime"],
            "manifest_relative": old_protocol["manifest_relative"],
            "manifest_sha256": old_protocol["manifest_sha256"],
            "profile_relative": old_protocol["profile_relative"],
            "profile_sha256": old_protocol["profile_sha256"],
            "source_root": old_protocol["source_root"], "ids": old_protocol["ids"],
            "origin_checkout": str(old_checkout.resolve()),
            "origin_interpreter": str(old_interpreter.resolve()),
            "new_code_sha256": method_hashes(REPO), "new_evaluator_runtime": runtime_receipt(),
            "imported_prefix_count": expected_count, "pending_sealed_conversion": pending,
            "new_max_documents_per_session": max_documents_per_session,
            "imports": records, "query_independent": True, "graph_admission_enabled": False,
            "new_model_calls_for_imports": 0, "origin_immutable": True}
    pending_row = next(row for row in _read(child(root, old_protocol["manifest_relative"]),
                                            old_protocol["manifest_sha256"])["pdfs"]
                       if row["sample_id"] == pending["sample_id"])
    _pending_origin(root, plan, pending_row)
    write_once(plan_path, plan)
    return plan_path, plan


def _origin_receipt(root: Path, plan: dict, record: dict, row: dict) -> tuple[dict, dict]:
    origin = child(root, plan["origin_run_relative"])
    old_protocol = _read(origin / "protocol.json", plan["origin_protocol_sha256"])
    if (old_protocol.get("code_sha256") != plan["origin_code_sha256"] or
            old_protocol.get("evaluator_runtime") != plan["origin_evaluator_runtime"] or
            old_protocol.get("ids") != plan["ids"]):
        raise ValueError("origin_protocol_changed_during_import")
    receipt = _read(origin / "rows" / (record["sample_id"] + ".json"),
                    record["origin_row_sha256"])
    source_root = Path(plan["source_root"]) if plan["source_root"] else None
    producer._verify_receipt(root, row, receipt, origin, source_root, old_protocol)
    if any(receipt.get(key) != record[value] for key, value in (
            ("eligibility", "eligibility"), ("state", "state"),
            ("assessment_relative", "assessment_relative"),
            ("assessment_sha256", "assessment_sha256"))):
        raise ValueError("origin_record_changed_during_import")
    return receipt, old_protocol


def _leaf_conversion_receipt(root: Path, receipt: dict, protocol: dict, row: dict) -> dict:
    """Resolve a nested V2 prefix import to its original converter receipt."""
    seen: set[str] = set()
    while receipt.get("eligibility") == "eligible" and "conversion_relative" not in receipt:
        if receipt.get("schema_version") != migration_v2.ROW_VERSION:
            raise ValueError("imported_origin_conversion_lineage_unknown")
        descriptor = protocol.get("migration")
        if not isinstance(descriptor, dict) or set(descriptor) != {"relative", "sha256"}:
            raise ValueError("nested_origin_migration_descriptor_missing")
        if descriptor["sha256"] in seen:
            raise ValueError("nested_origin_migration_cycle")
        seen.add(descriptor["sha256"])
        old_plan = _read(child(root, descriptor["relative"]), descriptor["sha256"])
        if old_plan.get("schema_version") != migration_v2.VERSION:
            raise ValueError("nested_origin_migration_version_invalid")
        record = next((item for item in old_plan["imports"]
                       if item["sample_id"] == row["sample_id"]), None)
        if record is None:
            raise ValueError("nested_origin_row_not_in_plan")
        receipt, protocol = migration_v2._origin_receipt(root, old_plan, record, row)
    if receipt.get("eligibility") == "eligible" and not all(
            key in receipt for key in ("conversion_relative", "conversion_sha256", "document_sha256")):
        raise ValueError("origin_conversion_leaf_incomplete")
    return receipt


def verify_prefix_receipt(root: Path, row: dict, receipt: dict, output: Path,
                          source_root: Path | None, protocol: dict,
                          native: list[dict], page_size: list) -> None:
    descriptor = protocol.get("migration")
    if not isinstance(descriptor, dict) or set(descriptor) != {"relative", "sha256"}:
        raise ValueError("sealed_prefix_plan_binding_missing")
    plan = _read(child(root, descriptor["relative"]), descriptor["sha256"])
    if (plan.get("schema_version") != VERSION or plan.get("new_code_sha256") != protocol["code_sha256"] or
            plan.get("manifest_sha256") != protocol["manifest_sha256"] or
            plan.get("profile_sha256") != protocol["profile_sha256"] or
            plan.get("source_root") != protocol["source_root"] or
            plan.get("new_max_documents_per_session") != protocol["converter_session"]["max_documents"]):
        raise ValueError("sealed_prefix_current_protocol_changed")
    record = next((item for item in plan["imports"] if item["sample_id"] == row["sample_id"]), None)
    if record is None:
        raise ValueError("row_not_in_sealed_prefix")
    original, _ = _origin_receipt(root, plan, record, row)
    expected = {"schema_version": ROW_VERSION, "sample_id": row["sample_id"],
                "protocol_sha256": digest(output / "protocol.json"),
                "eligibility": record["eligibility"], "state": record["state"],
                "source_hashes": {key: row[key + "_sha256"] for key in ("source", "page", "image", "native")},
                "assessment_relative": (output / "assessments" / producer.METHOD /
                    (row["sample_id"] + ".json")).relative_to(root).as_posix()
                    if record["eligibility"] == "eligible" else None,
                "assessment_sha256": receipt.get("assessment_sha256")
                    if record["eligibility"] == "eligible" else None,
                "origin_row_sha256": record["origin_row_sha256"],
                "origin_protocol_sha256": plan["origin_protocol_sha256"],
                "migration_sha256": descriptor["sha256"], "new_model_call": False}
    if receipt != expected:
        raise ValueError("sealed_prefix_row_lineage_changed")
    if original["eligibility"] != "eligible":
        return
    if not isinstance(receipt["assessment_sha256"], str) or len(receipt["assessment_sha256"]) != 64:
        raise ValueError("sealed_prefix_assessment_hash_missing")
    assessment = _read(child(root, receipt["assessment_relative"]), receipt["assessment_sha256"])
    leaf = _leaf_conversion_receipt(root, original, _read(
        child(root, plan["origin_run_relative"]) / "protocol.json", plan["origin_protocol_sha256"]), row)
    conversion = _read(child(root, leaf["conversion_relative"]), leaf["conversion_sha256"])
    expected_stage = {"status": conversion["status"],
        "input_hashes": {"docling": leaf["conversion_sha256"],
                         "docling_document": leaf["document_sha256"]},
        "new_model_conversion": False, "origin_model_called": True,
        "origin_protocol_sha256": plan["origin_protocol_sha256"],
        "origin_row_sha256": record["origin_row_sha256"],
        "migration_manifest_sha256": descriptor["sha256"],
        "session_start": conversion["session_start"],
        "converter_profile_sha256": plan["profile_sha256"],
        "wall_seconds": conversion["wall_seconds"]}
    if (assessment.get("conversion_stage") != expected_stage or
            assessment.get("source_hash_verification") !=
                "verified_original_page_native_image_during_prefix_migration" or
            (receipt["state"] == "complete") != (conversion["status"] == "success")):
        raise ValueError("sealed_prefix_reassessment_lineage_changed")
    geometry = SourceGeometry.from_pdf(source_path(root, row, source_root).read_bytes(), native,
                                       expected_source_sha256=row["source_sha256"])
    verify_source_bound_assessment(assessment, native, page_size=page_size,
        source_sha256=row["source_sha256"], page_sha256=row["page_sha256"],
        source_geometry=geometry)


def _pending_origin(root: Path, plan: dict, row: dict) -> tuple[dict, dict]:
    record = plan["pending_sealed_conversion"]
    if record["sample_id"] != row["sample_id"] or record["origin_receipt_sha256"] is not None:
        raise ValueError("pending_import_identity_invalid")
    conversion, document = migration_v1._validate_origin_attempt(root, plan, record, row)
    if conversion["status"] != "success" or document is None:
        raise ValueError("pending_import_requires_sealed_success_document")
    worker_keys = {"status", "docling_status", "document_sha256", "worker_pid",
        "runtime", "session_start", "wall_seconds", "peak_process_memory_bytes",
        "error_class", "model_called"}
    if (set(conversion) != worker_keys or
            not isinstance(conversion.get("worker_pid"), int) or
            conversion.get("document_sha256") != record["origin_document_sha256"]):
        raise ValueError("pending_import_converter_receipt_shape_invalid")
    start = conversion["session_start"]
    session = _read(child(root, start["relative"]), start["sha256"])
    if session.get("schema_version") != "retrieval-docling-session-start-v1":
        raise ValueError("pending_import_session_schema_invalid")
    return conversion, document


def _pending_stage(plan: dict, record: dict, conversion: dict, descriptor: dict) -> dict:
    return {"status": conversion["status"],
        "input_hashes": {"docling": record["origin_conversion_sha256"],
                         "docling_document": record["origin_document_sha256"]},
        "new_model_conversion": False, "origin_model_called": True,
        "origin_protocol_sha256": plan["origin_protocol_sha256"],
        "origin_attempt_sha256": record["origin_intent_sha256"],
        "origin_row_receipt_sha256": None,
        "migration_manifest_sha256": descriptor["sha256"],
        "session_start": conversion["session_start"],
        "converter_profile_sha256": plan["profile_sha256"],
        "wall_seconds": conversion["wall_seconds"]}


def verify_pending_receipt(root: Path, row: dict, receipt: dict, output: Path,
                           source_root: Path | None, protocol: dict,
                           native: list[dict], page_size: list) -> None:
    descriptor = protocol.get("migration")
    if not isinstance(descriptor, dict) or set(descriptor) != {"relative", "sha256"}:
        raise ValueError("pending_migration_descriptor_missing")
    plan = _read(child(root, descriptor["relative"]), descriptor["sha256"])
    record = plan.get("pending_sealed_conversion")
    if (plan.get("schema_version") != VERSION or
            plan.get("new_code_sha256") != protocol["code_sha256"] or
            plan.get("manifest_sha256") != protocol["manifest_sha256"] or
            plan.get("profile_sha256") != protocol["profile_sha256"] or
            plan.get("source_root") != protocol["source_root"] or
            plan.get("new_max_documents_per_session") != protocol["converter_session"]["max_documents"] or
            not isinstance(record, dict) or record.get("sample_id") != row["sample_id"]):
        raise ValueError("pending_migration_plan_mismatch")
    conversion, document = _pending_origin(root, plan, row)
    validate_cached_input("docling_document", document, page_size=page_size)
    assessment_path = output / "assessments" / producer.METHOD / (row["sample_id"] + ".json")
    expected = {"schema_version": PENDING_ROW_VERSION, "sample_id": row["sample_id"],
        "protocol_sha256": digest(output / "protocol.json"), "eligibility": "eligible",
        "state": "complete", "source_hashes": {key: row[key + "_sha256"]
            for key in ("source", "page", "image", "native")},
        "assessment_relative": assessment_path.relative_to(root).as_posix(),
        "assessment_sha256": receipt.get("assessment_sha256"),
        "assessment_status": receipt.get("assessment_status"),
        "origin_protocol_sha256": plan["origin_protocol_sha256"],
        "origin_attempt_sha256": record["origin_intent_sha256"],
        "origin_conversion_sha256": record["origin_conversion_sha256"],
        "origin_document_sha256": record["origin_document_sha256"],
        "migration_sha256": descriptor["sha256"], "new_model_call": False}
    if receipt != expected:
        raise ValueError("pending_import_row_lineage_changed")
    assessment = _read(assessment_path, receipt["assessment_sha256"])
    if (assessment["conversion_stage"] != _pending_stage(plan, record, conversion, descriptor) or
            assessment["status"] != receipt["assessment_status"] or
            assessment.get("source_hash_verification") !=
                "verified_original_page_native_image_during_pending_conversion_import"):
        raise ValueError("pending_import_assessment_lineage_changed")
    geometry = SourceGeometry.from_pdf(source_path(root, row, source_root).read_bytes(), native,
                                       expected_source_sha256=row["source_sha256"])
    verify_source_bound_assessment(assessment, native, page_size=page_size,
        source_sha256=row["source_sha256"], page_sha256=row["page_sha256"],
        source_geometry=geometry)


def _initialize(root: Path, output: Path, manifest: dict, protocol: dict,
                source_root: Path | None) -> None:
    descriptor = protocol["migration"]
    plan = _read(child(root, descriptor["relative"]), descriptor["sha256"])
    rows = {row["sample_id"]: row for row in manifest["pdfs"]}
    if (plan["ids"] != protocol["ids"] or plan["new_code_sha256"] != protocol["code_sha256"] or
            plan["new_evaluator_runtime"] != protocol["evaluator_runtime"]):
        raise ValueError("sealed_prefix_new_protocol_changed")
    for record in plan["imports"]:
        producer._check_code(protocol)
        sid = record["sample_id"]
        row = rows[sid]
        row_path = output / "rows" / (sid + ".json")
        if row_path.is_file():
            producer._verify_receipt(root, row, _read(row_path), output, source_root, protocol)
            continue
        old_receipt, _ = _origin_receipt(root, plan, record, row)
        native, size, decision = producer._verified_row(root, row, source_root)
        if decision != record["eligibility"]:
            raise ValueError("sealed_prefix_current_source_eligibility_changed:" + sid)
        assessment_relative = None
        assessment_sha = None
        if decision == "eligible":
            leaf = _leaf_conversion_receipt(root, old_receipt, _read(
                child(root, plan["origin_run_relative"]) / "protocol.json", plan["origin_protocol_sha256"]), row)
            conversion = _read(child(root, leaf["conversion_relative"]),
                               leaf["conversion_sha256"])
            document = (_read(child(root, leaf["conversion_relative"]).parent / "document.json",
                              leaf["document_sha256"])
                        if leaf["document_sha256"] else {})
            if conversion["status"] == "success":
                validate_cached_input("docling_document", document, page_size=size)
            geometry = SourceGeometry.from_pdf(source_path(root, row, source_root).read_bytes(), native,
                                               expected_source_sha256=row["source_sha256"])
            assessment = assess_document(document, page_size=size,
                source_sha256=row["source_sha256"], page_sha256=row["page_sha256"],
                native_lines=native, scholarly_abstract="", max_input_chars=4000,
                conversion_status=conversion["status"], source_geometry=geometry)
            assessment["source_hash_verification"] = "verified_original_page_native_image_during_prefix_migration"
            assessment["conversion_stage"] = {"status": conversion["status"],
                "input_hashes": {"docling": leaf["conversion_sha256"],
                                 "docling_document": leaf["document_sha256"]},
                "new_model_conversion": False, "origin_model_called": True,
                "origin_protocol_sha256": plan["origin_protocol_sha256"],
                "origin_row_sha256": record["origin_row_sha256"],
                "migration_manifest_sha256": descriptor["sha256"],
                "session_start": conversion["session_start"],
                "converter_profile_sha256": plan["profile_sha256"],
                "wall_seconds": conversion["wall_seconds"]}
            seal(assessment)
            verify_source_bound_assessment(assessment, native, page_size=size,
                source_sha256=row["source_sha256"], page_sha256=row["page_sha256"],
                source_geometry=geometry)
            after_native, after_size, after_decision = producer._verified_row(root, row, source_root)
            if (after_native, after_size, after_decision) != (native, size, decision):
                raise ValueError("sealed_prefix_source_changed_during_reassessment:" + sid)
            path = output / "assessments" / producer.METHOD / (sid + ".json")
            assessment_sha = write_once(path, assessment)
            assessment_relative = path.relative_to(root).as_posix()
        receipt = {"schema_version": ROW_VERSION, "sample_id": sid,
            "protocol_sha256": digest(output / "protocol.json"), "eligibility": decision,
            "state": record["state"],
            "source_hashes": {key: row[key + "_sha256"] for key in ("source", "page", "image", "native")},
            "assessment_relative": assessment_relative, "assessment_sha256": assessment_sha,
            "origin_row_sha256": record["origin_row_sha256"],
            "origin_protocol_sha256": plan["origin_protocol_sha256"],
            "migration_sha256": descriptor["sha256"], "new_model_call": False}
        write_once(row_path, receipt)
        producer._verify_receipt(root, row, receipt, output, source_root, protocol)
    record = plan["pending_sealed_conversion"]
    sid = record["sample_id"]
    row = rows[sid]
    receipt_path = output / "rows" / (sid + ".json")
    if receipt_path.is_file():
        producer._verify_receipt(root, row, _read(receipt_path), output, source_root, protocol)
        return
    producer._check_code(protocol)
    native, size, decision = producer._verified_row(root, row, source_root)
    if decision != "eligible":
        raise ValueError("pending_conversion_source_no_longer_eligible")
    conversion, document = _pending_origin(root, plan, row)
    validate_cached_input("docling_document", document, page_size=size)
    geometry = SourceGeometry.from_pdf(source_path(root, row, source_root).read_bytes(), native,
                                       expected_source_sha256=row["source_sha256"])
    assessment = assess_document(document, page_size=size,
        source_sha256=row["source_sha256"], page_sha256=row["page_sha256"],
        native_lines=native, scholarly_abstract="", max_input_chars=4000,
        conversion_status=conversion["status"], source_geometry=geometry)
    assessment["source_hash_verification"] = (
        "verified_original_page_native_image_during_pending_conversion_import")
    assessment["conversion_stage"] = _pending_stage(plan, record, conversion, descriptor)
    seal(assessment)
    verify_source_bound_assessment(assessment, native, page_size=size,
        source_sha256=row["source_sha256"], page_sha256=row["page_sha256"],
        source_geometry=geometry)
    after_native, after_size, after_decision = producer._verified_row(root, row, source_root)
    if (after_native, after_size, after_decision) != (native, size, decision):
        raise ValueError("pending_conversion_source_changed_during_reassessment")
    assessment_path = output / "assessments" / producer.METHOD / (sid + ".json")
    assessment_sha = write_once(assessment_path, assessment)
    receipt = {"schema_version": PENDING_ROW_VERSION, "sample_id": sid,
        "protocol_sha256": digest(output / "protocol.json"), "eligibility": "eligible",
        "state": "complete", "source_hashes": {key: row[key + "_sha256"]
            for key in ("source", "page", "image", "native")},
        "assessment_relative": assessment_path.relative_to(root).as_posix(),
        "assessment_sha256": assessment_sha, "assessment_status": assessment["status"],
        "origin_protocol_sha256": plan["origin_protocol_sha256"],
        "origin_attempt_sha256": record["origin_intent_sha256"],
        "origin_conversion_sha256": record["origin_conversion_sha256"],
        "origin_document_sha256": record["origin_document_sha256"],
        "migration_sha256": descriptor["sha256"], "new_model_call": False}
    write_once(receipt_path, receipt)
    producer._verify_receipt(root, row, receipt, output, source_root, protocol)


def run(root: Path, origin: Path, output: Path, old_checkout: Path, old_interpreter: Path,
        old_head: str, old_protocol_sha256: str, expected_count: int,
        max_documents_per_session: int, *, gate: dict | None = None) -> dict:
    plan_path = output.parent / (output.name + ".mixed-pending-migration-v3.json")
    if plan_path.is_file():
        plan = _read(plan_path)
        if (plan.get("schema_version") != VERSION or
                plan.get("origin_run_relative") != origin.relative_to(root).as_posix() or
                plan.get("origin_protocol_sha256") != old_protocol_sha256 or
                plan.get("origin_head") != old_head or
                plan.get("origin_checkout") != str(old_checkout.resolve()) or
                plan.get("origin_interpreter") != str(old_interpreter.resolve()) or
                plan.get("imported_prefix_count") != expected_count or
                plan.get("new_max_documents_per_session") != max_documents_per_session):
            raise ValueError("existing_sealed_prefix_plan_changed")
        audited = migration_v1._origin_audit(root, origin, old_checkout, old_interpreter, old_head)
        old_protocol = dict(_read(origin / "protocol.json", old_protocol_sha256),
                            stopped_execution_checkout=str(old_checkout.resolve()))
        records, pending = _prefix(root, origin, old_protocol, expected_count)
        if (records != plan["imports"] or pending != plan["pending_sealed_conversion"] or
                audited.get("completed_rows") != expected_count or
                audited.get("row_hashes") != [[r["sample_id"], r["origin_row_sha256"]] for r in records]):
            raise ValueError("resumed_sealed_prefix_origin_changed")
    else:
        plan_path, plan = prepare_plan(root, origin, output, old_checkout, old_interpreter,
            old_head, old_protocol_sha256, expected_count, max_documents_per_session)
    if (plan["new_code_sha256"] != method_hashes(REPO) or
            plan["new_evaluator_runtime"] != runtime_receipt()):
        raise ValueError("sealed_prefix_new_code_or_runtime_changed")
    if gate is None:
        return {"status": "PLAN_PREPARED_NO_MODEL_CALL", "plan_relative": plan_path.relative_to(root).as_posix(),
                "plan_sha256": digest(plan_path), "imported_prefix_count": expected_count}
    from src import paper_selector_acceptance_v2 as acceptance
    verified = acceptance.verify(root, gate["receipt"], gate["receipt_sha256"],
        policy_relative=gate["policy"], policy_sha256=gate["policy_sha256"],
        configuration_relative=gate["configuration"], source_map_relative=gate["source_map"])
    if verified.get("status") != "PASS" or verified.get("source_verified_original_91_included") is not True:
        raise ValueError("current_source_verified_gate_required_before_model_run")
    acceptance_receipt = _read(child(root, gate["receipt"]), gate["receipt_sha256"])
    if acceptance_receipt.get("base_method_hashes") != method_hashes(REPO):
        raise ValueError("current_source_gate_method_closure_required_before_model_run")
    descriptor = {"relative": plan_path.relative_to(root).as_posix(), "sha256": digest(plan_path)}
    return producer._run(root, child(root, plan["manifest_relative"]),
        child(root, plan["profile_relative"]), output,
        Path(plan["source_root"]) if plan["source_root"] else None,
        migration=descriptor, migration_initializer=_initialize,
        max_documents_per_session=max_documents_per_session)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "run"))
    for name in ("data-root", "origin-output", "new-output", "origin-checkout",
                 "origin-interpreter", "origin-head", "origin-protocol-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--expected-prefix-count", type=int, required=True)
    parser.add_argument("--max-documents-per-session", type=int, default=64)
    for name in ("gate-receipt", "gate-receipt-sha256", "gate-policy", "gate-policy-sha256",
                 "gate-configuration", "gate-source-map"):
        parser.add_argument("--" + name)
    args = parser.parse_args()
    gate = None
    if args.stage == "run":
        values = (args.gate_receipt, args.gate_receipt_sha256, args.gate_policy,
                  args.gate_policy_sha256, args.gate_configuration, args.gate_source_map)
        if any(value is None for value in values):
            parser.error("run requires all six exact current source gate arguments")
        gate = dict(zip(("receipt", "receipt_sha256", "policy", "policy_sha256",
                         "configuration", "source_map"), values))
    root = data_root(args.data_root)
    summary = run(root, child(root, args.origin_output), child(root, args.new_output),
        Path(args.origin_checkout).resolve(), Path(args.origin_interpreter).resolve(),
        args.origin_head, args.origin_protocol_sha256, args.expected_prefix_count,
        args.max_documents_per_session, gate=gate)
    print(json.dumps({k: summary[k] for k in summary if k in
        ("status", "document_count", "eligible_count", "state_counts", "plan_relative",
         "plan_sha256", "imported_prefix_count")}, sort_keys=True))
    if summary.get("status") == "STOPPED_DRAINED":
        return 4
    if summary.get("status") not in ("COMPLETE", "PLAN_PREPARED_NO_MODEL_CALL"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
