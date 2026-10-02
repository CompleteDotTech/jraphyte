"""Authored gate attacks; these fixtures are never empirical qualification."""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.parallel_source_v4 import extraction, promotion, promotion_io, promotion_review, promotion_observation
from src.parallel_source_v4.common import digest, write_once
from src.parallel_source_v4.fidelity import text_hash
from src.parallel_source_v4.metrics import score_case
from trace_gc.pdf_source_parallel_v4 import digest_value, json_bytes, source_lines
from trace_gc.pdf_structure_parallel_v4 import seal, verify_assessment

NOW = "2026-09-28T12:00:00+00:00"
REVIEWED = "2026-09-28T10:00:00+00:00"
PDF_STACK_AVAILABLE = bool(importlib.util.find_spec("fitz") and importlib.util.find_spec("PIL"))
TEXT = "We establish an exact scientific statement."
COMPLETE = {f"f{i:03}" for i in range(1, 108)} | {"f119", "f150", "f192", "f195"}
OLD = {f"f{i:03}" for i in range(1, 88)} | {"f119", "f150", "f192", "f195"}
PARTIAL = {f"f{i:03}" for i in range(108, 115)}


def gold(sid):
    return "complete" if sid in COMPLETE else "partial" if sid in PARTIAL else "absent"


def table():
    rows, old, replay = [], [], []
    for sid in sorted(promotion.CASE_IDS):
        proposed = sid in COMPLETE
        prediction = {"status": "complete" if proposed else gold(sid), "proposal": proposed,
                      "text": TEXT if proposed else "", "conversion_status": "success"}
        reference = {"status": gold(sid), "text": TEXT if proposed else ""}
        row = score_case(sid, prediction, reference)
        row["fidelity"] = {"verified_correct_proposal": proposed,
            **{key: {"status": "pass"} for key in ("notation", "boundary", "reading_order", "source_location")}}
        rows.append(row)
        old.append({**deepcopy(row), "proposed": sid in OLD})
        replay.append({"id": sid, **{key: True for key in
            ("same_text", "same_status", "same_proposal", "same_assessment_digest")}})
    return {name: deepcopy(rows) for name in promotion.METHODS}, old, replay


class PolicyTests(unittest.TestCase):
    def test_synthetic_scores_default_to_blocked(self):
        result = promotion.evaluate(*table())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["eligible_for_reviewed_selector_release"])
        self.assertFalse(result["graph_admission_enabled"])

    def test_preservation_uses_ids_not_replacement_count(self):
        arms, old, replay = table()
        row = next(x for x in arms[promotion.PRIMARY] if x["id"] == "f001")
        row["proposed"] = False
        result = promotion.evaluate(arms, old, replay, provenance_verified=True)
        self.assertEqual(result["gates"]["preserve_91"]["status"], "FAIL")
        self.assertEqual(result["gates"]["preserve_91"]["lost_correct_ids"], ["f001"])
        self.assertGreater(len(result["gates"]["preserve_91"]["gained_correct_ids"]), 0)

    def test_all_200_and_frozen_denominators_required(self):
        for attack in ("missing", "duplicate", "changed_gold", "bool_proposal"):
            arms, old, replay = table()
            rows = arms[promotion.PRIMARY]
            if attack == "missing": rows.pop()
            elif attack == "duplicate": rows[-1] = rows[0]
            elif attack == "changed_gold": rows[0]["gold"] = "absent"
            else: rows[0]["proposed"] = 1
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                promotion.evaluate(arms, old, replay, provenance_verified=True)

    def test_fidelity_replay_and_protected_outcomes_are_separate_gates(self):
        for sid, change, expected in (("f195", "unresolved", "BLOCKED"), ("f001", "fail", "FAIL")):
            arms, old, replay = table()
            row = next(x for x in arms[promotion.PRIMARY] if x["id"] == sid)
            row["fidelity"]["boundary"]["status"] = change
            row["fidelity"]["verified_correct_proposal"] = False
            self.assertEqual(promotion.evaluate(arms, old, replay, provenance_verified=True)["status"], expected)
        arms, old, replay = table()
        next(x for x in arms[promotion.PRIMARY] if x["id"] == "f199")["proposed"] = True
        replay[0]["same_assessment_digest"] = False
        result = promotion.evaluate(arms, old, replay, provenance_verified=True)
        self.assertEqual(result["gates"]["saved_v2_replay"]["status"], "FAIL")
        self.assertEqual(result["gates"]["original_source_outcomes"]["failed_ids"], ["f199"])

    def test_diagnostic_arm_cannot_become_fallback(self):
        arms, old, replay = table()
        name = next(name for name in arms if name != promotion.PRIMARY)
        next(row for row in arms[name] if row["id"] == "f199")["proposed"] = True
        result = promotion.evaluate(arms, old, replay, provenance_verified=True)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["arms"][name]["selection"], "diagnostic_only")
        self.assertFalse(result["automatic_fallback_enabled"])

    def test_configuration_is_exact_and_image_is_separate(self):
        for key, value in (("image_evidence_policy", "reviewed"), ("physical_page", True),
                           ("unknown", True), ("fallback_policy", "enabled")):
            config = deepcopy(promotion.CONFIGURATION)
            config[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "unsupported_promotion_configuration"):
                promotion.configuration(config)


def closure_fixture(pages=1):
    import fitz
    with fitz.open() as doc:
        page = doc.new_page(width=500, height=500)
        page.insert_text((40, 70), TEXT)
        page.insert_text((40, 170), "Introduction")
        if pages == 2:
            page = doc.new_page(width=500, height=500)
            page.insert_text((40, 70), "1 Introduction")
        pdf_bytes = doc.tobytes()
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        native = source_lines(doc[0])
        assets = {"page1.png": doc[0].get_pixmap(dpi=120, colorspace=fitz.csRGB, alpha=False).tobytes("png")}
        if pages == 2:
            assets["page2.png"] = doc[1].get_pixmap(dpi=120, colorspace=fitz.csRGB, alpha=False).tobytes("png")
            assets["page2.json"] = json_bytes(doc[1].get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES))
    identity = {"source_sha256": hashlib.sha256(pdf_bytes).hexdigest(), "page_sha256": "b"*64,
                "image_sha256": hashlib.sha256(assets["page1.png"]).hexdigest()}
    def span(line):
        return {"line_id": line["id"], "start": 0, "end": len(line["text"]), "page_no": 1,
                "text": line["text"], "bbox": line["bbox"]}
    accepted, excluded = [span(native[0])], [{"role": "body", "spans": [span(native[1])]}]
    pred = seal({"status": "uncertain", "proposal": False, "complete_candidate": False,
        "text": TEXT, "conversion_status": "success", "request_budget": {"status": "within_budget"},
        "physical_page": 1, "native_sha256": digest_value(native), **identity, "section_owner": None,
        "spans": accepted, "closing_boundary": None, "eligible_for_jev": False, "verified_admission": False})
    def image(name, page):
        return {"relative": name, "sha256": hashlib.sha256(assets[name]).hexdigest(), "physical_page": page, "dpi": 120}
    closure = {"kind": "reviewed_section_transition", "page_one_image": image("page1.png", 1), "next_page": None}
    review = {"version": promotion_review.VERSION, **identity, "assessment_sha256": pred["assessment_sha256"],
        "text_sha256": pred["text_sha256"], "native_sha256": pred["native_sha256"], "physical_page": 1,
        "decision": "complete", "reviewer": "authored-fixture", "reviewer_kind": "assistant", "reviewed_at": REVIEWED,
        "independent_review": False, "exposure": "previously_examined_development", "source_before_predictions": False,
        "checks": {key: True for key in promotion_review.CHECKS}, "accepted_spans": accepted,
        "excluded_spans": excluded, "excluded_regions": [], "closure": closure}
    fidelity = {"reviewer": "authored-fixture", "reviewer_kind": "assistant", "reviewed_at": REVIEWED,
        "reference_text_sha256": text_hash(TEXT), "source_sha256": identity["source_sha256"],
        "page_sha256": identity["page_sha256"], "notation": {"status": "pass", "evidence_id": "fixture:notation"},
        "boundary": {"status": "pass", "evidence_id": "fixture:boundary", "representation": "native_spans",
            "native_sha256": pred["native_sha256"], "section_owner": "abstract", "reference_spans": accepted,
            "excluded_spans": excluded, "closing_boundary": {"kind": closure["kind"]}}}
    reference = {"status": "complete", "text": TEXT, "fidelity_review": fidelity}
    arguments = dict(native=native, source_identity=identity, pdf_bytes=pdf_bytes,
                     load_asset=assets.__getitem__, fidelity_reference=reference, evaluated_at=NOW)
    return pred, review, arguments, assets


@unittest.skipUnless(PDF_STACK_AVAILABLE, "optional PyMuPDF/Pillow PDF stack unavailable")
class ClosureTests(unittest.TestCase):
    def test_exact_review_derives_separate_sealed_review_only_assessment(self):
        pred, review, args, assets = closure_fixture()
        original = deepcopy(pred)
        derived, audit = promotion_review.apply_closure_review(pred, review, **args)
        self.assertEqual(pred, original)
        self.assertEqual(derived["text"], pred["text"])
        self.assertEqual(derived["original_assessment_sha256"], pred["assessment_sha256"])
        self.assertTrue(derived["proposal"])
        self.assertFalse(derived["eligible_for_jev"])
        self.assertFalse(audit["independent_review"])
        verify_assessment(derived)

    def test_title_page_binds_actual_second_image_and_native(self):
        for pages in (1, 2):
            pred, review, args, assets = closure_fixture(pages)
            review["closure"]["kind"] = "reviewed_title_page_end"
            review["closure"]["next_page"] = {"document_end": True}
            if pages == 2:
                review["closure"]["next_page"] = {
                    "image": {"relative": "page2.png", "sha256": hashlib.sha256(assets["page2.png"]).hexdigest(), "physical_page": 2, "dpi": 120},
                    "native": {"relative": "page2.json", "sha256": hashlib.sha256(assets["page2.json"]).hexdigest(), "physical_page": 2, "representation": "pymupdf-page-dict-v1"}}
            derived, audit = promotion_review.apply_closure_review(pred, review, **args)
            self.assertEqual(derived["text"], TEXT)
            self.assertEqual(len(audit["asset_hashes"]), 1 if pages == 1 else 3)
            if pages == 2:
                review["closure"]["next_page"] = {"document_end": True}
                with self.assertRaisesRegex(ValueError, "page_two_image_and_native"):
                    promotion_review.apply_closure_review(pred, review, **args)

    def test_native_page_two_cannot_be_replaced_and_rehashed(self):
        import fitz
        pred, review, args, assets = closure_fixture(2)
        review["closure"].update(kind="reviewed_title_page_end", next_page={
            "image": {"relative": "page2.png", "sha256": hashlib.sha256(assets["page2.png"]).hexdigest(), "physical_page": 2, "dpi": 120},
            "native": {"relative": "page2.json", "sha256": hashlib.sha256(assets["page2.json"]).hexdigest(), "physical_page": 2, "representation": "pymupdf-page-dict-v1"}})
        value = json.loads(assets["page2.json"])
        value["blocks"][0]["lines"][0]["spans"][0]["text"] = "Forged content"
        assets["page2.json"] = json_bytes(value)
        review["closure"]["next_page"]["native"]["sha256"] = hashlib.sha256(assets["page2.json"]).hexdigest()
        with self.assertRaisesRegex(ValueError, "native_readback_mismatch"):
            promotion_review.apply_closure_review(pred, review, **args)

    def test_review_cannot_change_source_text_scope_or_claim_blinding(self):
        for attack in ("source", "text", "future", "blinding", "independent", "check", "notation", "overlap", "out_of_bounds", "reordered"):
            pred, review, args, assets = closure_fixture()
            if attack == "source": review["source_sha256"] = "f"*64
            elif attack == "text": review["accepted_spans"][0]["text"] += "x"
            elif attack == "future": review["reviewed_at"] = "2999-01-01T00:00:00Z"
            elif attack == "blinding": review["source_before_predictions"] = True
            elif attack == "independent": review["independent_review"] = True
            elif attack == "check": review["checks"]["no_page_continuation"] = False
            elif attack == "notation": args["fidelity_reference"]["fidelity_review"]["notation"]["status"] = "unresolved"
            elif attack == "overlap": review["excluded_spans"] = [{"role": "body", "spans": deepcopy(review["accepted_spans"])}]
            elif attack == "out_of_bounds": review["accepted_spans"][0]["end"] = 999
            else: review["accepted_spans"] += deepcopy(review["excluded_spans"][0]["spans"])
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                promotion_review.apply_closure_review(pred, review, **args)

    def test_partial_error_truncation_and_oversize_are_ineligible(self):
        for state in ("partial", "absent", "error", "truncated", "oversize"):
            pred, review, args, assets = closure_fixture()
            if state == "oversize": pred["text"] = "x"*4001
            else: pred["status"] = state
            seal(pred)
            review.update(assessment_sha256=pred["assessment_sha256"], text_sha256=pred["text_sha256"])
            with self.subTest(state=state), self.assertRaises(ValueError):
                promotion_review.apply_closure_review(pred, review, **args)

    def test_visual_regions_bind_image_and_cannot_cover_accepted_line(self):
        pred, review, args, assets = closure_fixture()
        region = {"role": "other", "bbox": [50, 250, 230, 300], "image_sha256": review["image_sha256"],
                  "physical_page": 1, "coordinate_system": "full-page-image-pixels-top-left"}
        review["excluded_regions"] = [region]
        promotion_review.apply_closure_review(pred, review, **args)
        for box in ([0, 0, 9999, 9999], [0, 0, 800, 200], [0, 0, float("nan"), 10]):
            region["bbox"] = box
            with self.assertRaises(ValueError):
                promotion_review.apply_closure_review(pred, review, **args)

    def test_blank_or_preceding_regions_and_bool_page_cannot_close_abstract(self):
        for attack in ("blank_region", "preceding_native", "bool_page"):
            pred, review, args, assets = closure_fixture()
            if attack == "blank_region":
                review["excluded_spans"] = []
                review["excluded_regions"] = [{"role": "body", "bbox": [0, 0, 10, 10],
                    "image_sha256": review["image_sha256"], "physical_page": 1,
                    "coordinate_system": "full-page-image-pixels-top-left"}]
            elif attack == "preceding_native":
                # A preceding source line may be metadata, but is not closure.
                args["native"][1]["bbox"] = [40, 10, 150, 30]
                review["excluded_spans"][0]["spans"][0]["bbox"] = [40, 10, 150, 30]
                pred["native_sha256"] = review["native_sha256"] = digest_value(args["native"])
                seal(pred); review["assessment_sha256"] = pred["assessment_sha256"]
            else:
                review["accepted_spans"][0]["page_no"] = True
                seal(pred); review["assessment_sha256"] = pred["assessment_sha256"]
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                promotion_review.apply_closure_review(pred, review, **args)

    def test_wrong_full_page_image_cannot_be_rehashed_into_validity(self):
        from io import BytesIO
        from PIL import Image
        pred, review, args, assets = closure_fixture()
        with Image.open(BytesIO(assets["page1.png"])) as image:
            image = image.crop((0, 0, 100, 100))
            output = BytesIO(); image.save(output, format="PNG")
        assets["page1.png"] = output.getvalue()
        changed = hashlib.sha256(output.getvalue()).hexdigest()
        args["source_identity"]["image_sha256"] = changed
        review["image_sha256"] = changed
        review["closure"]["page_one_image"]["sha256"] = changed
        with self.assertRaisesRegex(ValueError, "not_full_source_page"):
            promotion_review.apply_closure_review(pred, review, **args)


class ReceiptTests(unittest.TestCase):
    def test_altered_or_missing_derived_outputs_fail_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            derived = seal({"text": TEXT, "status": "complete", "proposal": True,
                            "eligible_for_jev": False, "verified_admission": False})
            relative = "reviewed-assessments/f001.json"
            sha = write_once(root/relative, derived)
            receipt = {"version": promotion.VERSION, "status": "PASS", "eligible_for_reviewed_selector_release": True,
                "configuration_sha256": "c"*64, "evaluated_at": NOW, "invocation": {"run_relative": "run"},
                "derived_assessments": {"f001": derived}, "derived_assessment_files_sha256": {relative: sha}}
            pinned = write_once(root/"acceptance.json", receipt)
            with patch.object(promotion_io, "analyze", return_value=receipt):
                promotion_io.verify(root, "acceptance.json", pinned, configuration_relative="config", source_map_relative="map")
                (root/relative).write_text('{"text":"changed"}')
                with self.assertRaisesRegex(ValueError, "derived_assessment_changed"):
                    promotion_io.verify(root, "acceptance.json", pinned, configuration_relative="config", source_map_relative="map")
                (root/relative).unlink()
                with self.assertRaises(FileNotFoundError):
                    promotion_io.verify(root, "acceptance.json", pinned, configuration_relative="config", source_map_relative="map")

    def test_receipt_hash_is_external_and_pass_is_rebuilt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = {"version": promotion.VERSION, "status": "PASS", "eligible_for_reviewed_selector_release": True,
                       "configuration_sha256": "c"*64, "evaluated_at": NOW, "invocation": {"run_relative": "run"}}
            sha = write_once(root/"acceptance.json", receipt)
            for expected in (None, "a"*64):
                with self.assertRaises(ValueError):
                    promotion_io.verify(root, "acceptance.json", expected, configuration_relative="config", source_map_relative="map")
            with patch.object(promotion_io, "analyze", return_value=receipt) as analyze:
                result = promotion_io.verify(root, "acceptance.json", sha, configuration_relative="config", source_map_relative="map")
                self.assertFalse(result["release_selection_performed"])
                self.assertEqual(analyze.call_args.kwargs["evaluated_at"], NOW)
            for field in ("configuration_sha256", "method_hashes", "runtime", "input_file_hashes", "eligible_for_reviewed_selector_release"):
                changed = {**receipt, field: False}
                with patch.object(promotion_io, "analyze", return_value=changed), self.assertRaisesRegex(ValueError, "stale_configuration"):
                    promotion_io.verify(root, "acceptance.json", sha, configuration_relative="config", source_map_relative="map")

    def test_containment_is_checked_before_any_receipt_read(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(promotion_io, "read_bound") as read:
            with self.assertRaises(ValueError):
                promotion_io.verify(Path(directory), "../outside.json", "a"*64,
                                    configuration_relative="config", source_map_relative="map")
            read.assert_not_called()

    def test_publication_redacts_private_source_and_is_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            derived = {"text": "private fixture text"}
            result = {"version": promotion.VERSION, "status": "BLOCKED", "invocation": {"run_relative": "run"},
                      "input_file_hashes": {"private/input": "a"*64}, "derived_assessments": {"f001": derived},
                      "derived_assessment_files_sha256": {"reviewed-assessments/f001.json": hashlib.sha256(json_bytes(derived)+b"\n").hexdigest()}}
            public = promotion_io.publish(root, "receipt", result)
            self.assertNotIn("private fixture", json.dumps(public))
            self.assertNotIn("private/input", json.dumps(public))
            self.assertEqual(public["private_acceptance_sha256"], digest(root/"receipt/acceptance.json"))
            with self.assertRaises(ValueError): promotion_io.publish(root, "receipt", result)
            with self.assertRaises(ValueError): promotion_io.publish(root, "run/child", result)

    @unittest.skipUnless(PDF_STACK_AVAILABLE, "optional PyMuPDF/Pillow PDF stack unavailable")
    def test_run_output_manifest_pins_exact_assessment_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prediction = seal({"text": TEXT, "status": "uncertain", "proposal": False})
            case = {"id": "fixture", "native_lines": [], "page_path": root/"unused.pdf", "page_size": [500, 500],
                    "source_sha256": "a"*64, "page_sha256": "b"*64, "paths": {}}
            with patch.object(extraction, "predict", return_value=prediction):
                result = extraction.run_cases([case], {"fixture": {"text": TEXT, "status": "complete"}}, root/"run", "authored_fixture", (promotion.PRIMARY,))
            relative = "assessments/" + promotion.PRIMARY + "/fixture.json"
            self.assertEqual(result["assessment_files_sha256"], {relative: digest(root/"run"/relative)})


def authored_run(root, *, native_reference=False):
    """Only preflight is replaced; all 1,000+ artifact reads/hashes are real."""
    native = [{"id": 0, "text": TEXT, "bbox": [40, 40, 400, 60], "page_no": 1, "spans": []}]
    native_hash = digest_value(native)
    span = {"line_id": 0, "start": 0, "end": len(TEXT), "text": TEXT, "bbox": native[0]["bbox"], "page_no": 1}
    labels, baseline, cases, input_hashes, native_records = {}, {}, [], {}, []
    details, files, reviews = {method: [] for method in promotion.METHODS}, {}, {}
    code = {"fixture.py": "a"*64}
    for sid in sorted(promotion.CASE_IDS):
        labels[sid] = {"status": gold(sid), "text": TEXT if sid in COMPLETE else ""}
        baseline[sid] = {"status": "complete" if sid in OLD else "uncertain", "text": labels[sid]["text"],
                         "eligible_for_jev": sid in OLD, "assessment_sha256": digest_value(sid)}
        relative = "validation_expanded200/assessments/structure_v2/" + sid + ".json"
        input_hashes[relative] = write_once(root/relative, baseline[sid])
        identity = {"id": sid, "native_sha256": native_hash}
        cases.append({"id": sid, "native_lines": native, "native_identity": identity,
                      "source_sha256": "a"*64, "page_sha256": "b"*64, "image_sha256": "c"*64})
        relative = "run/native/" + sid + ".json"
        sha = write_once(root/relative, native)
        native_records.append({**identity, "native_relative": relative, "file_sha256": sha})
        prediction = seal({"status": "complete" if sid in COMPLETE else gold(sid), "proposal": sid in COMPLETE,
            "complete_candidate": sid in COMPLETE, "text": labels[sid]["text"], "physical_page": 1,
            "conversion_status": "success", "source_sha256": "a"*64, "page_sha256": "b"*64,
            "native_sha256": native_hash, "section_owner": "abstract" if sid in COMPLETE else None,
            "eligible_for_jev": False, "verified_admission": False, "spans": [span] if sid in COMPLETE else [],
            "closing_boundary": None, "reasons": [], "request_budget": {"status": "within_budget"}})
        for method in promotion.METHODS:
            relative = f"assessments/{method}/{sid}.json"
            files[relative] = write_once(root/"run"/relative, prediction)
            details[method].append(score_case(sid, prediction, labels[sid]))
        if sid in COMPLETE:
            reviews[sid] = {**labels[sid], "fidelity_review": {
                "reviewer": "authored-fixture", "reviewer_kind": "assistant", "reviewed_at": REVIEWED,
                "reference_text_sha256": text_hash(TEXT), "source_sha256": "a"*64, "page_sha256": "b"*64,
                "notation": {"status": "pass", "evidence_id": "fixture:notation"},
                "boundary": {"status": "pass", "evidence_id": "fixture:boundary", "representation": "native_spans",
                    "native_sha256": native_hash, "reference_spans": [span], "section_owner": "abstract",
                    "closing_boundary": {"kind": "fixture"}}}}
    gate = {"status": "PASS", "method_hashes": code, "runtime": {"fixture": True},
        "cases": cases, "labels": labels, "baseline_predictions": baseline, "input_file_hashes": input_hashes,
        "native_mode": "fresh", "native_manifest_sha256": None, "extractor_identity": {"fixture": True}, "native_comparison": {}}
    if native_reference:
        records = []
        for record in native_records:
            relative = "archive/" + record["id"] + ".json"
            sha = write_once(root/relative, native)
            records.append({**record, "native_relative": relative, "file_sha256": sha,
                "page_size": [500, 500], "source_sha256": "a"*64, "page_sha256": "b"*64,
                "image_sha256": "c"*64})
        sha = write_once(root/"reference.json", {"schema_version": 1, "cases": records,
            "extractor_identity": {"fixture": True}})
        gate["input_file_hashes"]["reference.json"] = sha
        gate["native_manifest_sha256"] = sha
        gate["native_comparison"] = {"status": "COMPARED", "changed_ids": []}
    saved = extraction.public_preflight(gate)
    write_once(root/"run/preflight.json", saved)
    write_once(root/"run/protocol.json", {"cohort": "regression200_already_examined", "method_hashes": code, "frozen_at": REVIEWED})
    native_sha = write_once(root/"run/native_manifest.json", {"mode": "fresh", "cases": native_records,
        "experiment_sha256": digest_value(saved), "extractor_identity": gate["extractor_identity"]})
    result = {"cohort": "regression200", "status": "COMPLETE_OFFLINE_ASSESSMENT_NOT_QUALIFICATION",
        "automatic_fallback_enabled": False, "production_graph_writes": 0, "new_paid_api_calls": 0,
        "experiment_sha256": digest_value(saved), "execution_identity": {key: gate[key] for key in
            ("runtime", "method_hashes", "native_mode", "native_manifest_sha256", "extractor_identity", "native_comparison")},
        "native_manifest_sha256": native_sha, "details": details, "assessment_files_sha256": files}
    results_sha = write_once(root/"run/results.json", result)
    write_once(root/"config.json", promotion.CONFIGURATION)
    write_once(root/"map.json", {sid: "unused/" + sid + ".pdf" for sid in promotion.CASE_IDS})
    review_sha = write_once(root/"reviews.json", {"version": "promotion-fidelity-review-v1", "cases": reviews})
    kwargs = dict(run_relative="run", run_sha256=results_sha, configuration_relative="config.json", source_map_relative="map.json",
                  review_relative="reviews.json", review_sha256=review_sha, evaluated_at=NOW)
    return gate, code, kwargs


class ArtifactAuditTests(unittest.TestCase):
    def test_observed_candidate_failure_overrides_only_exact_primary_and_never_certifies(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            gate, code, kwargs = authored_run(root)
            stack.enter_context(patch.object(extraction, "preflight", return_value=gate))
            stack.enter_context(patch.object(extraction, "verify_preflight_inputs"))
            stack.enter_context(patch.object(promotion_io, "method_hashes", return_value=code))
            prediction = json.loads((root/"run/assessments"/promotion.PRIMARY/"f001.json").read_bytes())
            observation = failure_observation(prediction, gate["cases"][0])
            reviews = json.loads((root/"reviews.json").read_bytes())
            reviews["cases"]["f001"]["candidate_observations"] = [observation]
            (root/"reviews.json").write_bytes(json_bytes(reviews))
            kwargs["review_sha256"] = digest(root/"reviews.json")
            result = promotion_io.analyze(root, **kwargs)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["gates"]["reviewed_fidelity"]["failed_ids"], ["f001"])
            self.assertEqual(result["automatic_assessment"]["gates"]["reviewed_fidelity"]["failed_ids"], ["f001"])
            self.assertEqual(result["arms"]["parallel_grobid_v4"]["fidelity"]["status"], "PASS")
            self.assertNotIn(observation["note"], json.dumps(result))
            observation["assessment_sha256"] = "f"*64
            (root/"reviews.json").write_bytes(json_bytes(reviews))
            kwargs["review_sha256"] = digest(root/"reviews.json")
            self.assertEqual(promotion_io.analyze(root, **kwargs)["reason"], "candidate_failure_observation_identity_mismatch")

    def test_image_policy_requires_its_own_manifest_and_real_route_exercise(self):
        from src.parallel_source_v4 import promotion_image
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            gate, code, kwargs = authored_run(root)
            # Real frozen labels carry metadata beyond the image-reference
            # contract. A native-only route needs no invented image review.
            for sid, reference in gate["labels"].items():
                reference.update(id=sid, review_notes="authored frozen-label metadata")
            stack.enter_context(patch.object(extraction, "preflight", return_value=gate))
            stack.enter_context(patch.object(extraction, "verify_preflight_inputs"))
            stack.enter_context(patch.object(promotion_io, "method_hashes", return_value=code))
            (root/"config.json").write_bytes(json_bytes(promotion.IMAGE_CONFIGURATION))
            result = promotion_io.analyze(root, **kwargs)
            self.assertEqual(result["reason"], "image_enabled_policy_requires_pinned_all_200_routes")
            routes = {}
            for sid in sorted(promotion.CASE_IDS):
                original = json.loads((root/"run/assessments"/promotion.PRIMARY/(sid+".json")).read_bytes())
                routes[sid] = {"native_assessment_sha256": original["assessment_sha256"], "source_sha256": "a"*64,
                               "page_sha256": "b"*64, "route": "native_or_hold", "evidence": None, "scope_review": None}
            manifest = {"version": promotion_image.VERSION, "native_results_sha256": kwargs["run_sha256"],
                        "configuration_sha256": digest_value(promotion.IMAGE_CONFIGURATION), "cases": routes}
            sha = write_once(root/"image-routes.json", manifest)
            kwargs.update(image_relative="image-routes.json", image_sha256=sha)
            result = promotion_io.analyze(root, **kwargs)
            self.assertEqual(result["status"], "BLOCKED", result)
            self.assertEqual(result["gates"]["image_route"]["route_count"], 200)
            self.assertEqual(result["image_review"]["count"], 0)
            (root/"config.json").write_bytes(json_bytes(promotion.CONFIGURATION))
            result = promotion_io.analyze(root, **kwargs)
            self.assertEqual(result["reason"], "native_only_policy_cannot_consume_image_routes")

    def test_source_adapter_rebuilds_all_arms_and_rejects_resealed_output(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            gate, code, kwargs = authored_run(root)
            stack.enter_context(patch.object(extraction, "preflight", return_value=gate))
            stack.enter_context(patch.object(extraction, "verify_preflight_inputs"))
            stack.enter_context(patch.object(promotion_io, "method_hashes", return_value=code))
            result = promotion_io.analyze(root, **kwargs)
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(len(result["cases"][promotion.PRIMARY]), 200)
            self.assertEqual(result["manual_closure"]["count"], 0)
            self.assertEqual(result["automatic_assessment"]["arms"][promotion.PRIMARY]["metrics"]["correct_proposals_98"], 111)
            target = root/"run/assessments"/promotion.PRIMARY/"f001.json"
            original = target.read_bytes()
            changed = json.loads(original)
            changed["reasons"] = ["resealed_after_measurement"]
            target.write_bytes(json_bytes(seal(changed)))
            blocked = promotion_io.analyze(root, **kwargs)
            self.assertEqual(blocked["reason"], "assessment_differs_from_pinned_measured_output")
            target.write_bytes(original)
            path = root/"run/results.json"
            original = path.read_bytes()
            changed = json.loads(original)
            changed.pop("assessment_files_sha256")
            path.write_bytes(json_bytes(changed))
            blocked = promotion_io.analyze(root, **kwargs)
            self.assertEqual(blocked["reason"], "externally_pinned_experiment_results_sha256_required")
            # Even explicitly pinning an old-format result does not synthesize
            # an assessment manifest after the measurement.
            kwargs["run_sha256"] = digest(path)
            blocked = promotion_io.analyze(root, **kwargs)
            self.assertEqual(blocked["reason"], "complete_measured_assessment_output_manifest_required")

    def test_missing_reviews_and_changed_input_during_audit_cannot_promote(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            gate, code, kwargs = authored_run(root)
            stack.enter_context(patch.object(extraction, "preflight", return_value=gate))
            verify = stack.enter_context(patch.object(extraction, "verify_preflight_inputs"))
            stack.enter_context(patch.object(promotion_io, "method_hashes", return_value=code))
            without = {**kwargs, "review_relative": None, "review_sha256": None}
            result = promotion_io.analyze(root, **without)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(len(result["gates"]["reviewed_fidelity"]["unresolved_ids"]), 111)
            def mutate(*args):
                (root/"config.json").write_text("{}")
            verify.side_effect = mutate
            result = promotion_io.analyze(root, **kwargs)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertFalse(result["eligible_for_reviewed_selector_release"])

    def test_reference_extent_readback_rejects_copied_text_for_different_positions(self):
        native = [{"id": 0, "text": "x=1 and x=2", "bbox": [0, 0, 100, 20]}]
        review = {"boundary": {"representation": "native_spans", "status": "pass",
                              "reference_spans": [{"line_id": 0, "start": 8, "end": 11, "page_no": 1}]}}
        with self.assertRaisesRegex(ValueError, "reference_text_differs"):
            promotion_io._review_spans(review, native, "x=1")


def failure_observation(prediction, identity):
    return {"version": promotion_observation.VERSION, "assessment_sha256": prediction["assessment_sha256"],
        "text_sha256": text_hash(prediction["text"]), "source_sha256": identity["source_sha256"],
        "page_sha256": identity["page_sha256"], "native_sha256": prediction["native_sha256"],
        "image_sha256": identity["image_sha256"], "physical_page": 1, "reviewer": "authored-fixture",
        "reviewer_kind": "assistant", "reviewed_at": REVIEWED, "independent_review": False,
        "exposure": "previously_examined_development", "source_before_predictions": False,
        "dimension": "notation", "status": "fail", "evidence_id": "authored-fixture:visual-fault",
        "note": "Private authored observation, never a real paper review."}


@unittest.skipUnless(PDF_STACK_AVAILABLE, "optional PyMuPDF/Pillow PDF stack unavailable")
class CandidateFailureTests(unittest.TestCase):
    def test_negative_observation_cannot_clear_review_or_follow_a_changed_candidate(self):
        prediction, closure_review, args, _ = closure_fixture()
        identity = {**args["source_identity"], "native_identity": {"native_sha256": prediction["native_sha256"]}}
        observation = failure_observation(prediction, identity)
        validated = promotion_observation.validate_failures([observation], prediction, identity, evaluated_at=NOW)
        fidelity = {"notation": {"status": "unresolved"}, "verified_correct_proposal": False}
        failed = promotion_observation.apply_failures(fidelity, prediction, validated)
        self.assertEqual(failed["notation"]["status"], "fail")
        self.assertFalse(failed["verified_correct_proposal"])
        amended = {**prediction, "assessment_sha256": "f"*64}
        self.assertEqual(promotion_observation.apply_failures(fidelity, amended, validated), fidelity)
        closed, _ = promotion_review.apply_closure_review(prediction, closure_review, **args)
        self.assertNotEqual(closed["assessment_sha256"], prediction["assessment_sha256"])
        self.assertEqual(closed["text"], prediction["text"])
        passed = {"notation": {"status": "pass"}, "verified_correct_proposal": True}
        preserved = promotion_observation.apply_failures(passed, closed, validated)
        self.assertEqual(preserved["notation"]["status"], "fail")
        self.assertFalse(preserved["verified_correct_proposal"])

    def test_failure_identity_attribution_and_negative_only_contract_are_strict(self):
        prediction, _, args, _ = closure_fixture()
        identity = {**args["source_identity"], "native_identity": {"native_sha256": prediction["native_sha256"]}}
        original = failure_observation(prediction, identity)
        for key, value in [(key, "f"*64) for key in ("assessment_sha256", "text_sha256", "source_sha256", "page_sha256", "native_sha256", "image_sha256")]+[
                ("physical_page", True), ("reviewer", ""), ("reviewed_at", "2999-01-01T00:00:00Z"),
                ("reviewed_at", "2026-09-28T10:00:00"), ("independent_review", True),
                ("source_before_predictions", True), ("status", "pass"), ("dimension", "unknown"), ("note", "")]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                promotion_observation.validate_failures([{**original, key: value}], prediction, identity, evaluated_at=NOW)
        with self.assertRaises(ValueError):
            promotion_observation.validate_failures([original, original], prediction, identity, evaluated_at=NOW)


if __name__ == "__main__":
    unittest.main()
