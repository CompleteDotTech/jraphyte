"""Explicit source-reviewed image route for the measured development policy.

No OCR is run here. All image artifacts and reviews must already exist under
the authorized root and are rechecked against the original source and code.
"""
from __future__ import annotations

from copy import deepcopy
import datetime as dt
import hashlib
from io import BytesIO
import math
import re

from trace_gc.pdf_source_parallel_v4 import digest_value
from trace_gc.pdf_structure_parallel_v4 import seal, verify_assessment
from .fidelity import evaluate_fidelity, compare_notation
from .promotion_review import _image_asset, _native_page_asset
from .promotion_observation import validate_failures

VERSION = "promotion-image-route-v1"
POLICY = "source-bound-attributed-image-review-v1"
FAILED_NATIVE_POLICY = "source-bound-failed-native-image-replacement-v1"
ROUTE_FIELDS = {"native_assessment_sha256", "source_sha256", "page_sha256", "route", "evidence", "scope_review"}
ASSETS = {"preparation", "reviewed_candidate", "raw_ocr", "page_image", "crop_image", "execution", "handoff", "catalog_records"}


def validate_manifest(value, *, case_ids, run_sha256, configuration_sha256):
    if (not isinstance(value, dict) or set(value) != {"version", "native_results_sha256", "configuration_sha256", "cases"}
            or value["version"] != VERSION or value["native_results_sha256"] != run_sha256
            or value["configuration_sha256"] != configuration_sha256
            or not isinstance(value["cases"], dict) or set(value["cases"]) != set(case_ids)):
        raise ValueError("exact_policy_and_all_200_image_routes_required")
    return value["cases"]


def _attribution(value, evaluated_at):
    if (not isinstance(value.get("reviewer"), str) or not value["reviewer"].strip()
            or value.get("reviewer_kind") not in {"assistant", "human"}
            or value.get("independent_review") is not False):
        raise ValueError("image_route_review_attribution_required")
    stamp = dt.datetime.fromisoformat(value["reviewed_at"].replace("Z", "+00:00"))
    evaluation = dt.datetime.fromisoformat(evaluated_at.replace("Z", "+00:00"))
    if stamp.tzinfo is None or evaluation.tzinfo is None or stamp > evaluation:
        raise ValueError("image_route_review_time_invalid")


def apply_image_route(original, selected, entry, *, source_identity, pdf_bytes,
                      load_json, load_asset, fidelity_reference, evaluated_at,
                      native_failure_policy="disabled", candidate_failures=None,
                      native_lines=None, source_geometry=None):
    """Return a reviewed image assessment or an explicit hold; no native offsets."""
    from trace_gc.canonical import digest as canonical_digest, loads, text_digest
    from trace_gc.catalog import Catalog
    from trace_gc.pdf_image_evidence import candidate_hash, handoff, held_reason, verify_artifacts
    from .image_ocr import code_identity
    verify_assessment(original)
    from trace_gc.pdf_source_parallel_v4 import digest_value, verify_source_geometry_policy
    if original.get('source_geometry_policy') is not None and native_lines is None:
        raise ValueError('image_route_enabled_geometry_requires_original_native')
    if native_lines is not None or original.get('source_geometry_policy') is not None:
        verify_source_geometry_policy(original.get('source_geometry_policy'), source_geometry,
            source_sha256=source_identity['source_sha256'],
            native_sha256=digest_value(native_lines))
    if selected is not None and selected.get('source_geometry_policy') != original.get('source_geometry_policy'):
        raise ValueError('image_route_selected_geometry_policy_mismatch')
    if native_failure_policy not in {"disabled", FAILED_NATIVE_POLICY}:
        raise ValueError("unknown_failed_native_image_policy")
    if not isinstance(entry, dict) or set(entry) != ROUTE_FIELDS:
        raise ValueError("invalid_image_route_case_contract")
    if (entry["native_assessment_sha256"] != original["assessment_sha256"] or
            any(entry[k] != source_identity[k] for k in ("source_sha256", "page_sha256"))):
        raise ValueError("image_route_targets_another_native_run_or_source")
    if entry["route"] == "native_or_hold":
        if entry["evidence"] is not None or entry["scope_review"] is not None:
            raise ValueError("nonimage_route_cannot_carry_unchecked_image_evidence")
        return None, {"route": "native_or_hold", "status": "NATIVE_OR_HELD", "graph_admission_enabled": False}
    replacement_failures = []
    if (entry["route"] == "image_review" and selected.get("proposal") is True
            and native_failure_policy == FAILED_NATIVE_POLICY and original.get("proposal") is True
            and selected == original):
        replacement_failures = validate_failures(candidate_failures, original, source_identity, evaluated_at=evaluated_at)
    if (entry["route"] != "image_review" or
            (original.get("proposal") is True or selected.get("proposal") is not False) and not replacement_failures):
        raise ValueError("image_route_cannot_replace_selected_native_proposal")
    current_code = code_identity()
    evidence = entry["evidence"]
    if not isinstance(evidence, dict) or set(evidence) != ASSETS:
        raise ValueError("image_route_requires_all_bound_image_artifacts")
    def asset(name, *, json=False):
        descriptor = evidence[name]
        if (not isinstance(descriptor, dict) or set(descriptor) != {"relative", "sha256"}
                or not isinstance(descriptor["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", descriptor["sha256"])):
            raise ValueError("image_route_invalid_asset_descriptor")
        raw = load_asset(descriptor["relative"])
        if hashlib.sha256(raw).hexdigest() != descriptor["sha256"]:
            raise ValueError("image_route_asset_hash_mismatch")
        return load_json(descriptor["relative"]) if json else raw
    candidate = asset("reviewed_candidate", json=True)
    raw = asset("raw_ocr")
    page_png, crop_png = asset("page_image"), asset("crop_image")
    execution, recorded_handoff = asset("execution", json=True), asset("handoff", json=True)
    preparation = asset("preparation", json=True)
    recorded_catalog = asset("catalog_records", json=True)
    if candidate.get("physical_page") != 1 or candidate.get("source_sha256") != source_identity["source_sha256"]:
        raise ValueError("image_route_first_original_physical_page_required")
    verify_artifacts(candidate, pdf_bytes=pdf_bytes, raw_output=raw, page_png=page_png, crop_png=crop_png)
    metadata_keys = {"source_sha256", "physical_page", "page_identity_sha256", "render", "crop", "native_observation"}
    if (preparation.get("version") != "image-review-preparation-v1" or preparation.get("source_id") != candidate["source_id"]
            or preparation.get("code_sha256") != current_code or preparation.get("new_paid_api_calls") != 0
            or preparation.get("production_graph_writes") != 0 or not isinstance(preparation.get("metadata"), dict)
            or set(preparation["metadata"]) != metadata_keys
            or any(preparation["metadata"][key] != candidate[key] for key in metadata_keys)
            or execution.get("preparation_sha256") != evidence["preparation"]["sha256"]
            or load_asset(preparation["source_relative"]) != pdf_bytes):
        raise ValueError("image_route_preparation_source_or_execution_link_mismatch")
    if (execution.get("version") != "image-ocr-execution-v1" or execution.get("status") != "SOURCE_REVIEW_REQUIRED"
            or type(execution.get("new_local_ocr_calls")) is not int or execution["new_local_ocr_calls"] != 1
            or execution.get("new_paid_api_calls") != 0 or execution.get("production_graph_writes") != 0
            or execution.get("code_sha256") != current_code or recorded_handoff.get("code_sha256") != current_code):
        raise ValueError("image_route_requires_fresh_exact_tree_local_ocr_and_handoff")
    if (recorded_handoff.get("source_sha256") != candidate["source_sha256"]
            or recorded_handoff.get("candidate_sha256") != candidate_hash(candidate)
            or recorded_handoff.get("new_paid_api_calls") != 0 or recorded_handoff.get("production_graph_writes") != 0):
        raise ValueError("image_route_handoff_source_or_operation_mismatch")
    raw_record = loads(raw.decode("utf-8"))
    if (raw_record.get("version") != "windows-local-image-ocr-v1" or raw_record.get("engine") != "Windows.Media.Ocr"
            or any(candidate["ocr"][key] != raw_record.get(key) for key in ("engine", "revision", "configuration", "input_crop_sha256", "output_status"))
            or raw_record.get("configuration", {}).get("local_only") is not True
            or raw_record["configuration"].get("implementation_sha256") != current_code["tools/windows_image_ocr.ps1"]):
        raise ValueError("image_route_local_ocr_runtime_or_raw_record_mismatch")
    # A single explicitly recorded correction is supported. Multi-step histories
    # require an additional lineage adapter rather than silently losing links.
    initial = deepcopy(candidate)
    initial.update(transcription=raw_record["text"], transcription_sha256=text_digest(raw_record["text"]), correction=None, review=None)
    initial_hash = candidate_hash(initial)
    if (candidate.get("correction") and (candidate["correction"]["previous_candidate_sha256"] != initial_hash
            or candidate["correction"]["previous_transcription_sha256"] != initial["transcription_sha256"])) or (
            not candidate.get("correction") and candidate["transcription"] != raw_record["text"]):
        raise ValueError("image_route_correction_does_not_bind_original_ocr_text")
    if execution.get("candidate_sha256") != initial_hash:
        raise ValueError("image_route_ocr_candidate_lineage_mismatch")
    if candidate["review"] is None:
        raise ValueError("image_route_source_review_required")
    _attribution(candidate["review"], evaluated_at)
    if candidate.get("correction"):
        edit = candidate["correction"]
        _attribution({"reviewer": edit["editor"], "reviewer_kind": edit["editor_kind"], "reviewed_at": edit["edited_at"], "independent_review": False}, candidate["review"]["reviewed_at"])
    reason = held_reason(candidate)
    scope = entry["scope_review"]
    if not isinstance(scope, dict) or set(scope) != {"candidate_sha256", "decision", "reviewer", "reviewer_kind", "reviewed_at", "independent_review", "exposure", "source_before_predictions", "checks", "closure"}:
        raise ValueError("image_route_abstract_scope_review_required")
    _attribution(scope, evaluated_at)
    if (scope["candidate_sha256"] != candidate_hash(candidate) or scope["exposure"] != "previously_examined_development"
            or scope["source_before_predictions"] is not False or scope["decision"] not in {"complete", "partial", "absent", "uncertain"}
            or not isinstance(scope["checks"], dict) or set(scope["checks"]) != {"native_image_disagreement_examined", "no_page_continuation"}
            or any(type(x) is not bool for x in scope["checks"].values())):
        raise ValueError("image_route_scope_identity_or_exposure_invalid")
    # The catalog is in memory, contains no assertions and is never persisted to
    # an application graph. Rebuilding it verifies typed handoff lineage.
    catalog = Catalog()
    source_records = [record for record in recorded_catalog if record.get("kind") == "source"]
    security_scope = source_records[0]["body"]["security_scope"] if len(source_records) == 1 else "private-development-review"
    rebuilt = handoff(catalog, candidate, pdf_bytes=pdf_bytes, raw_output=raw, scope=security_scope)
    if (any(recorded_handoff.get(key) != value for key, value in rebuilt.items()) or
            recorded_handoff.get("catalog_sha256") != canonical_digest(recorded_catalog)):
        raise ValueError("image_route_handoff_receipt_mismatch")
    # Security scope is not an accuracy gate, but must be preserved exactly.
    if recorded_catalog != catalog.all():
        raise ValueError("image_route_catalog_lineage_mismatch")
    audit = {"route": "image_review", "status": "HELD", "candidate_sha256": candidate_hash(candidate),
             "corrected_transcription": candidate.get("correction") is not None,
             "raw_ocr_matches_reviewed_transcription": raw_record["text"] == candidate["transcription"],
             "raw_ocr_sha256": candidate["ocr"]["raw_output_sha256"], "asset_hashes": {key: evidence[key]["sha256"] for key in sorted(ASSETS)},
             "independent_review": False, "graph_admission_enabled": False}
    if replacement_failures:
        audit.update(failed_native_assessment_sha256=original["assessment_sha256"],
            failed_native_proposal=True,
            native_failure_observations_sha256=[digest_value(item) for item in replacement_failures])
    if reason or scope["decision"] != "complete" or not all(scope["checks"].values()):
        audit["reason"] = reason or "image_abstract_scope_unresolved_or_not_complete"
        return None, audit
    if (any(item["dimension"] in {"notation", "reading_order"} for item in replacement_failures)
            and compare_notation(candidate["transcription"], original["text"])["status"] == "pass"):
        raise ValueError("image_replacement_did_not_repair_observed_transcription")
    closure = scope["closure"]
    if not isinstance(closure, dict) or set(closure) != {"kind", "excluded_regions", "next_page"}:
        raise ValueError("image_route_closure_evidence_required")
    width, height = candidate["render"]["dimensions"]
    crop = candidate["crop"]["bbox"]
    if not isinstance(closure["excluded_regions"], list):
        raise ValueError("image_route_excluded_regions_invalid")
    following = False
    for box in closure["excluded_regions"]:
        if (not isinstance(box, list) or len(box) != 4 or any(type(x) not in (int, float) or not math.isfinite(x) for x in box)
                or not 0 <= box[0] < box[2] <= width or not 0 <= box[1] < box[3] <= height
                or min(box[2], crop[2]) > max(box[0], crop[0]) and min(box[3], crop[3]) > max(box[1], crop[1])):
            raise ValueError("image_route_excluded_region_conflicts_with_crop")
        from PIL import Image
        with Image.open(BytesIO(page_png)) as observed:
            minimum, maximum = observed.crop(tuple(box)).convert("L").getextrema()
            if maximum - minimum < 8:
                raise ValueError("image_route_transition_region_is_blank")
        following = following or (box[1] >= crop[3] - 2 and
            min(box[2], crop[2]) - max(box[0], crop[0]) > .1 * min(box[2]-box[0], crop[2]-crop[0]))
    if closure["kind"] == "reviewed_section_transition":
        if not following or closure["next_page"] is not None:
            raise ValueError("image_route_source_transition_required")
    elif closure["kind"] == "reviewed_title_page_end":
        import fitz
        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
            if len(pdf) == 1:
                if closure["next_page"] != {"document_end": True}:
                    raise ValueError("image_route_actual_document_end_required")
            else:
                following = closure["next_page"]
                if not isinstance(following, dict) or set(following) != {"image", "native"}:
                    raise ValueError("image_route_page_two_image_and_native_required")
                _image_asset(following["image"], pdf[1], load_asset, expected_page=2)
                _native_page_asset(following["native"], pdf[1], load_asset)
    else:
        raise ValueError("image_route_unknown_closure_kind")
    result = {"schema_version": 3, "extractor_version": VERSION, "physical_page": 1,
        "status": "complete", "proposal": True, "complete_candidate": True, "section_owner": "abstract",
        "text": candidate["transcription"], "source_sha256": source_identity["source_sha256"],
        "page_sha256": source_identity["page_sha256"], "image_sha256": candidate["render"]["page_png_sha256"],
        "spans": [], "image_regions": [{"page_no": 1, "coord_origin": "TOPLEFT", "bbox": crop}],
        "representation": "reviewed-image-transcription-v1", "conversion_status": "success",
        "closing_boundary": {"kind": closure["kind"], "review_sha256": digest_value(scope)},
        "image_candidate_sha256": candidate_hash(candidate), "original_assessment_sha256": original["assessment_sha256"],
        "eligible_for_jev": False, "verified_admission": False, "admission": "source_review_required",
        "request_budget": {"status": "within_budget"}, "reasons": ["attributed_image_source_review"]}
    if replacement_failures:
        result["native_failure_observations_sha256"] = audit["native_failure_observations_sha256"]
    result = seal(result)
    if evaluate_fidelity(result, fidelity_reference, evaluated_at=evaluated_at)["verified_correct_proposal"] is not True:
        raise ValueError("image_route_requires_reviewed_image_extent_order_and_notation")
    if code_identity() != current_code:
        raise ValueError("image_route_code_changed_during_readback")
    audit.update(status="REVIEWED_IMAGE_PROPOSAL", derived_assessment_sha256=result["assessment_sha256"])
    if replacement_failures:
        audit["superseded_native_assessment_sha256"] = original["assessment_sha256"]
    return result, audit
