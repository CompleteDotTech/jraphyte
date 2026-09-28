"""Corpus-wide retrieval eligibility; no query labels, graph admission or repairs.

The only OCR route uses an unedited, full-page local execution on empty native
text. Missing artifacts remain denominator rows and block a repaired trial.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter

from trace_gc.pdf_source_parallel_v4 import digest_value

VERSION = "retrieval-corpus-policy-v1"
METHODS = {"parallel_structure_v4", "parallel_grobid_v4", "parallel_mineru_v4", "parallel_olmocr_v4"}


def validate_policy(policy):
    if not isinstance(policy, dict) or set(policy) != {"schema_version", "abstract_mode", "assessment_method", "ocr_mode", "ocr_identity"}:
        raise ValueError("explicit_corpus_field_policy_required")
    if policy["schema_version"] != VERSION or policy["abstract_mode"] not in {"disabled", "native_assessments"}:
        raise ValueError("unsupported_abstract_field_policy")
    if ((policy["abstract_mode"] == "disabled" and policy["assessment_method"] is not None) or
            (policy["abstract_mode"] == "native_assessments" and policy["assessment_method"] not in METHODS)):
        raise ValueError("single_corpus_assessment_method_required")
    if policy["ocr_mode"] not in {"disabled", "empty_native_local"}:
        raise ValueError("unsupported_corpus_ocr_policy")
    identity = policy["ocr_identity"]
    if policy["ocr_mode"] == "disabled":
        if identity is not None:
            raise ValueError("disabled_ocr_cannot_have_identity")
    elif (not isinstance(identity, dict) or set(identity) != {"engine", "revision", "configuration"}
          or identity["engine"] != "Windows.Media.Ocr" or not isinstance(identity["revision"], str)
          or not re.fullmatch(r"[0-9a-f]{64}", identity["revision"]) or not isinstance(identity["configuration"], dict)
          or identity["configuration"].get("local_only") is not True):
        raise ValueError("frozen_local_ocr_identity_required")
    return policy


def eligibility(row, native, page_cache):
    if row.get("native_extraction_state", "complete") != "complete":
        return {"abstract": "native_error", "ocr": "native_error"}
    if page_cache["state"] == "render_mismatch_review_required":
        return {"abstract": "page_mismatch", "ocr": "page_mismatch"}
    populated = any(line["text"].strip() for line in native)
    return {"abstract": "eligible" if populated else "empty_native",
            "ocr": "native_present" if populated else "eligible"}


def field_decisions(policy, eligibility, assessment, ocr):
    result = {}
    for name, value, mode in (("abstract", assessment, policy["abstract_mode"]), ("ocr", ocr, policy["ocr_mode"])):
        state = eligibility[name]
        if mode == "disabled":
            if value is not None:
                raise ValueError("disabled_field_policy_received_artifact:" + name)
            result[name] = "disabled"
        elif state != "eligible":
            if value is not None:
                raise ValueError("ineligible_field_policy_received_artifact:" + name)
            result[name] = "ineligible_" + state
        elif value is None:
            result[name] = "missing"
        elif name == "abstract":
            result[name] = "proposal" if value["proposal"] else "held_" + value["status"]
        else:
            result[name] = "candidate" if value["status"] == "success" else "held_" + value["status"]
    return result


def coverage(fields, policy):
    validate_policy(policy)
    for field in fields:
        for key, mode, states in (("abstract", policy["abstract_mode"], {"proposal", "missing", "held_complete", "held_partial", "held_absent", "held_uncertain", "held_error", "held_truncated", "ineligible_native_error", "ineligible_page_mismatch", "ineligible_empty_native"}),
                                   ("ocr", policy["ocr_mode"], {"candidate", "missing", "held_error", "held_truncated", "ineligible_native_error", "ineligible_page_mismatch", "ineligible_native_present"})):
            state = field["corpus_policy"][key]
            if state not in ({"disabled"} if mode == "disabled" else states):
                raise ValueError("field_decision_does_not_match_corpus_policy")
        if bool(field["abstract"]) != (field["corpus_policy"]["abstract"] == "proposal"):
            raise ValueError("abstract_text_does_not_match_corpus_policy_decision")
    axes = {key: dict(sorted(Counter(f["corpus_policy"][key] for f in fields).items()))
            for key in ("abstract", "ocr")}
    return {"policy": policy, "policy_sha256": digest_value(policy), "document_count": len(fields),
            "counts": axes, "missing_input_ids": {key: [f["id"] for f in fields if f["corpus_policy"][key] == "missing"]
                                                     for key in axes},
            "status": "BLOCKED_MISSING_INPUTS" if any(axis.get("missing", 0) for axis in axes.values()) else "READY",
            "denominator_axes": {
                "native": dict(sorted(Counter(f.get("native_extraction_state", "unrecorded") for f in fields).items())),
                "page_cache": dict(sorted(Counter(f.get("cached_page_render", {}).get("state", "unrecorded") for f in fields).items())),
                "searchability": dict(Counter("searchable" if any(f[k].strip() for k in ("title", "abstract", "body")) else "unsearchable" for f in fields)),
                "empty_fields": {k: sum(not f[k].strip() for f in fields) for k in ("title", "abstract", "body")}},
            "scope": "retrieval_candidates_only", "graph_admission_enabled": False}


def local_ocr_cache(entry, *, root, row, pdf_bytes, policy, code, read_asset):
    """Validate #18 producer lineage from exactly the bytes retained by the caller.

    No reviewed/corrected text is accepted here. Retrieval OCR remains unreviewed
    candidate text; image abstracts and corruption replacement need other routes.
    """
    from trace_gc.pdf_image_evidence import candidate_hash, verify_artifacts
    from .fields import parse_bound_json
    names = {"preparation", "candidate", "execution", "raw_ocr", "page_image", "crop_image"}
    if not isinstance(entry, dict) or set(entry) != names:
        raise ValueError("retrieval_ocr_requires_all_producer_assets")
    raw = {name: read_asset(entry[name]) for name in names}
    preparation, candidate, execution, record = [parse_bound_json(raw[name])
                                                for name in ("preparation", "candidate", "execution", "raw_ocr")]
    verify_artifacts(candidate, pdf_bytes=pdf_bytes, raw_output=raw["raw_ocr"],
                     page_png=raw["page_image"], crop_png=raw["crop_image"])
    dimensions = candidate["render"]["dimensions"]
    metadata = {k: candidate[k] for k in ("source_sha256", "physical_page", "page_identity_sha256", "render", "crop", "native_observation")}
    if (candidate["source_sha256"] != row["source_sha256"] or candidate["physical_page"] != 1
            or candidate["source_id"] != row["sample_id"] or candidate["crop"]["bbox"] != [0, 0, *dimensions]
            or candidate["render"]["dpi"] != 144
            or candidate["ocr"]["input_binding"] != "verified-crop"
            or candidate.get("correction") is not None or candidate.get("review") is not None
            or candidate["transcription"] != record.get("text")):
        raise ValueError("retrieval_ocr_requires_unedited_full_first_page")
    if (preparation.get("version") != "image-review-preparation-v1" or preparation.get("source_id") != row["sample_id"]
            or preparation.get("metadata") != metadata or preparation.get("code_sha256") != code
            or execution.get("version") != "image-ocr-execution-v1" or execution.get("status") != "SOURCE_REVIEW_REQUIRED"
            or execution.get("preparation_sha256") != hashlib.sha256(raw["preparation"]).hexdigest()
            or execution.get("candidate_sha256") != candidate_hash(candidate) or execution.get("code_sha256") != code
            or type(execution.get("new_local_ocr_calls")) is not int or execution["new_local_ocr_calls"] != 1
            or any(value.get("new_paid_api_calls") != 0 or value.get("production_graph_writes") != 0 for value in (preparation, execution))):
        raise ValueError("retrieval_ocr_preparation_execution_lineage_mismatch")
    if (record.get("version") != "windows-local-image-ocr-v1"
            or {k: record.get(k) for k in ("engine", "revision", "configuration")} != policy["ocr_identity"]
            or record["configuration"].get("implementation_sha256") != code["tools/windows_image_ocr.ps1"]
            or any(record.get(k) != candidate["ocr"][k] for k in ("engine", "revision", "configuration", "input_crop_sha256", "output_status"))):
        raise ValueError("retrieval_ocr_runtime_identity_mismatch")
    state = record["output_status"]
    if state not in {"complete", "error", "truncated"}:
        raise ValueError("retrieval_ocr_output_state_invalid")
    return {"status": "success" if state == "complete" else state, "raw_text": record["text"],
            "source_sha256": row["source_sha256"], "page_sha256": row["page_sha256"],
            "image_sha256": row["image_sha256"], "producer_assets": entry, "title": ""}
