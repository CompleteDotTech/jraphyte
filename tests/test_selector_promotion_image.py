"""Authored image-route attacks, never an actual OCR or quality measurement."""
from copy import deepcopy
import hashlib
import json
import unittest

from src.parallel_source_v4 import promotion, promotion_image
from src.parallel_source_v4.image_ocr import code_identity
from tests.test_selector_promotion import closure_fixture, failure_observation, TEXT, NOW, REVIEWED
from trace_gc.canonical import digest as canonical_digest
from trace_gc.catalog import Catalog
from trace_gc.pdf_image_evidence import (CHECKS, candidate_hash, correct_transcription, handoff,
    image_candidate, render_source, review_image)
from trace_gc.pdf_source_parallel_v4 import json_bytes
from trace_gc.pdf_structure_parallel_v4 import seal


def fixture(*, correction=False, disposition="complete"):
    original, native_review, args, _ = closure_fixture()
    pdf = args["pdf_bytes"]
    code = code_identity()
    crop = [30, 45, 350, 85]
    metadata, page, crop_bytes = render_source(pdf, dpi=72, crop=crop)
    raw_text = TEXT.replace("exact", "exat") if correction else TEXT
    configuration = {"local_only": True, "implementation_sha256": code["tools/windows_image_ocr.ps1"]}
    raw = json_bytes({"version": "windows-local-image-ocr-v1", "engine": "Windows.Media.Ocr",
        "revision": "authored-test-no-ocr-call", "configuration": configuration,
        "input_crop_sha256": metadata["crop"]["png_sha256"], "output_status": "complete", "text": raw_text})
    candidate = image_candidate(pdf, source_id="authored-test", transcription=raw_text, raw_output=raw,
        engine="Windows.Media.Ocr", revision="authored-test-no-ocr-call", configuration=configuration,
        input_crop_sha256=metadata["crop"]["png_sha256"], dpi=72, crop=crop)
    initial_hash = candidate_hash(candidate)
    if correction:
        candidate = correct_transcription(candidate, transcription=TEXT, editor="authored-test", editor_kind="assistant",
            edited_at=REVIEWED, reason="Authored OCR error fixture; no actual OCR call.")
    candidate = review_image(candidate, pdf_bytes=pdf, raw_output=raw, reviewer="authored-test", reviewer_kind="assistant",
        reviewed_at=REVIEWED, disposition=disposition, checks={key: True for key in CHECKS})
    catalog = Catalog()
    recorded = handoff(catalog, candidate, pdf_bytes=pdf, raw_output=raw, scope="test")
    recorded.update(code_sha256=code, catalog_sha256=canonical_digest(catalog.all()), source_sha256=candidate["source_sha256"],
                    candidate_sha256=candidate_hash(candidate), new_paid_api_calls=0, production_graph_writes=0)
    preparation = {"version": "image-review-preparation-v1", "source_id": candidate["source_id"], "metadata": metadata,
        "source_relative": "source.pdf", "code_sha256": code, "new_paid_api_calls": 0, "production_graph_writes": 0}
    preparation_bytes = json_bytes(preparation)
    execution = {"version": "image-ocr-execution-v1", "status": "SOURCE_REVIEW_REQUIRED", "new_local_ocr_calls": 1,
        "new_paid_api_calls": 0, "production_graph_writes": 0, "candidate_sha256": initial_hash, "code_sha256": code,
        "preparation_sha256": hashlib.sha256(preparation_bytes).hexdigest()}
    blobs = {"reviewed_candidate": json_bytes(candidate), "raw_ocr": raw, "page_image": page, "crop_image": crop_bytes,
        "execution": json_bytes(execution), "handoff": json_bytes(recorded), "catalog_records": json_bytes(catalog.all()),
        "preparation": preparation_bytes}
    entry = {"native_assessment_sha256": original["assessment_sha256"], "source_sha256": args["source_identity"]["source_sha256"],
        "page_sha256": args["source_identity"]["page_sha256"], "route": "image_review",
        "evidence": {key: {"relative": key, "sha256": hashlib.sha256(value).hexdigest()} for key, value in blobs.items()},
        "scope_review": {"candidate_sha256": candidate_hash(candidate), "decision": disposition,
            "reviewer": "authored-test", "reviewer_kind": "assistant", "reviewed_at": REVIEWED, "independent_review": False,
            "exposure": "previously_examined_development", "source_before_predictions": False,
            "checks": {"native_image_disagreement_examined": True, "no_page_continuation": True},
            "closure": {"kind": "reviewed_section_transition", "excluded_regions": [[30, 140, 220, 180]], "next_page": None}}}
    reference = deepcopy(args["fidelity_reference"])
    reference["fidelity_review"]["boundary"] = {"status": "pass", "evidence_id": "authored-test:extent",
        "representation": "image_regions", "image_sha256": candidate["render"]["page_png_sha256"], "page_size": [500, 500],
        "reference_regions": [{"page_no": 1, "coord_origin": "TOPLEFT", "bbox": crop}], "section_owner": "abstract",
        "closing_boundary": {"kind": "reviewed_section_transition"}}
    blobs["source.pdf"] = pdf
    kwargs = dict(source_identity=args["source_identity"], pdf_bytes=pdf, load_json=lambda key: json.loads(blobs[key]),
                  load_asset=blobs.__getitem__, fidelity_reference=reference, evaluated_at=NOW)
    return original, entry, kwargs, blobs


class ImagePromotionTests(unittest.TestCase):
    def test_supported_image_policy_has_distinct_exact_identity(self):
        self.assertEqual(promotion.configuration(promotion.IMAGE_CONFIGURATION), promotion.IMAGE_CONFIGURATION)
        self.assertNotEqual(promotion.IMAGE_CONFIGURATION, promotion.CONFIGURATION)
        self.assertEqual(promotion.configuration(promotion.FAILED_NATIVE_IMAGE_CONFIGURATION), promotion.FAILED_NATIVE_IMAGE_CONFIGURATION)
        self.assertNotEqual(promotion.FAILED_NATIVE_IMAGE_CONFIGURATION, promotion.IMAGE_CONFIGURATION)

    def test_failed_native_requires_distinct_policy_and_actual_reviewed_transcription_repair(self):
        for disposition in ("complete", "partial", "absent"):
            original, entry, args, blobs = fixture(correction=True, disposition=disposition)
            original = seal({**original, "status": "complete", "proposal": True, "complete_candidate": True,
                             "section_owner": "abstract", "text": TEXT.replace("exact", "exat")})
            entry["native_assessment_sha256"] = original["assessment_sha256"]
            args["source_identity"]["native_identity"] = {"native_sha256": original["native_sha256"]}
            failure = failure_observation(original, args["source_identity"])
            with self.assertRaisesRegex(ValueError, "cannot_replace_selected_native"):
                promotion_image.apply_image_route(original, original, entry, candidate_failures=[failure], **args)
            args.update(native_failure_policy=promotion_image.FAILED_NATIVE_POLICY, candidate_failures=[failure])
            derived, audit = promotion_image.apply_image_route(original, original, entry, **args)
            self.assertEqual(audit["failed_native_assessment_sha256"], original["assessment_sha256"])
            self.assertEqual(len(audit["native_failure_observations_sha256"]), 1)
            if disposition == "complete":
                self.assertEqual(audit["superseded_native_assessment_sha256"], original["assessment_sha256"])
                self.assertEqual(derived["text"], TEXT)
                self.assertEqual(derived["native_failure_observations_sha256"], audit["native_failure_observations_sha256"])
                self.assertFalse(derived["verified_admission"])
            else:
                self.assertIsNone(derived)
                self.assertEqual(audit["status"], "HELD")
                self.assertNotIn("superseded_native_assessment_sha256", audit)

    def test_failed_native_replacement_rejects_forged_stale_and_unchanged_content(self):
        original, entry, args, blobs = fixture()
        original = seal({**original, "status": "complete", "proposal": True, "complete_candidate": True, "section_owner": "abstract"})
        entry["native_assessment_sha256"] = original["assessment_sha256"]
        args["source_identity"]["native_identity"] = {"native_sha256": original["native_sha256"]}
        failure = failure_observation(original, args["source_identity"])
        downgraded = seal({**original, "proposal": False})
        with self.assertRaisesRegex(ValueError, "cannot_replace_selected_native"):
            promotion_image.apply_image_route(original, downgraded, entry, **args)
        args.update(native_failure_policy=promotion_image.FAILED_NATIVE_POLICY)
        with self.assertRaisesRegex(ValueError, "cannot_replace_selected_native"):
            promotion_image.apply_image_route(original, downgraded, entry, candidate_failures=[failure], **args)
        for change in ({"assessment_sha256": "f"*64}, {"image_sha256": "f"*64}, {"status": "pass"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                promotion_image.apply_image_route(original, original, entry, candidate_failures=[{**failure, **change}], **args)
        with self.assertRaises(ValueError):
            promotion_image.apply_image_route(original, original, entry, candidate_failures=[], **args)
        with self.assertRaisesRegex(ValueError, "did_not_repair_observed_transcription"):
            promotion_image.apply_image_route(original, original, entry, candidate_failures=[failure], **args)
        resealed = seal({**original, "original_assessment_sha256": original["assessment_sha256"], "manual_closure_review_sha256": "c"*64})
        with self.assertRaisesRegex(ValueError, "cannot_replace_selected_native"):
            promotion_image.apply_image_route(original, resealed, entry, candidate_failures=[failure], **args)

    def test_source_bound_image_result_has_no_fabricated_native_offsets(self):
        for corrected in (False, True):
            original, entry, args, blobs = fixture(correction=corrected)
            derived, audit = promotion_image.apply_image_route(original, original, entry, **args)
            self.assertTrue(derived["proposal"])
            self.assertEqual(derived["spans"], [])
            self.assertNotIn("native_sha256", derived)
            self.assertFalse(derived["verified_admission"])
            self.assertEqual(derived["text"], TEXT)
            self.assertEqual(audit["corrected_transcription"], corrected)
            self.assertEqual(audit["raw_ocr_matches_reviewed_transcription"], not corrected)

    def test_partial_and_absent_image_reviews_stay_held(self):
        for status in ("partial", "absent"):
            original, entry, args, blobs = fixture(disposition=status)
            derived, audit = promotion_image.apply_image_route(original, original, entry, **args)
            self.assertIsNone(derived)
            self.assertEqual(audit["status"], "HELD")

    def test_stale_tree_handoff_raw_image_and_reference_attacks_fail(self):
        for attack in ("tree", "preparation_link", "preparation_metadata", "raw", "image", "catalog", "notation", "native_scope", "blank_closure", "missing_closure", "blinding", "future"):
            original, entry, args, blobs = fixture()
            def replace(name, value):
                blobs[name] = json_bytes(value)
                entry["evidence"][name]["sha256"] = hashlib.sha256(blobs[name]).hexdigest()
            if attack == "tree":
                execution = json.loads(blobs["execution"]); execution["code_sha256"] = {}
                replace("execution", execution)
            elif attack == "preparation_link":
                execution = json.loads(blobs["execution"]); execution["preparation_sha256"] = "f"*64
                replace("execution", execution)
            elif attack == "preparation_metadata":
                preparation = json.loads(blobs["preparation"]); preparation["metadata"] = {}
                replace("preparation", preparation)
                execution = json.loads(blobs["execution"]); execution["preparation_sha256"] = entry["evidence"]["preparation"]["sha256"]
                replace("execution", execution)
            elif attack == "raw":
                raw = json.loads(blobs["raw_ocr"]); raw["text"] += " fabricated"
                replace("raw_ocr", raw)
            elif attack == "image": blobs["page_image"] = b"wrong image"
            elif attack == "catalog": replace("catalog_records", [])
            elif attack == "notation": args["fidelity_reference"]["fidelity_review"]["notation"]["status"] = "unresolved"
            elif attack == "native_scope": args["fidelity_reference"]["fidelity_review"]["boundary"]["representation"] = "native_spans"
            elif attack == "blank_closure": entry["scope_review"]["closure"]["excluded_regions"] = [[0, 100, 10, 120]]
            elif attack == "missing_closure": entry["scope_review"]["closure"] = None
            elif attack == "blinding": entry["scope_review"]["source_before_predictions"] = True
            else: entry["scope_review"]["reviewed_at"] = "2999-01-01T00:00:00Z"
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                promotion_image.apply_image_route(original, original, entry, **args)

    def test_selected_native_proposals_cannot_be_replaced_by_image(self):
        original, entry, args, blobs = fixture()
        with self.assertRaisesRegex(ValueError, "cannot_replace_selected_native"):
            promotion_image.apply_image_route(original, {"proposal": True}, entry, **args)

    def test_manifest_requires_every_original_case_and_exact_run_and_policy(self):
        value = {"version": promotion_image.VERSION, "native_results_sha256": "a"*64,
                 "configuration_sha256": "b"*64, "cases": {sid: {} for sid in promotion.CASE_IDS}}
        args = dict(case_ids=promotion.CASE_IDS, run_sha256="a"*64, configuration_sha256="b"*64)
        promotion_image.validate_manifest(value, **args)
        for field in ("native_results_sha256", "configuration_sha256", "cases"):
            changed = deepcopy(value); changed[field] = {} if field == "cases" else "c"*64
            with self.assertRaises(ValueError): promotion_image.validate_manifest(changed, **args)


if __name__ == "__main__":
    unittest.main()
