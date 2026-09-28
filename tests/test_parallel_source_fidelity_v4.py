from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.parallel_source_v4.common import read, write_once, digest
from src.parallel_source_v4.fidelity import (
    FIDELITY_METRIC_VERSION, LEGACY_METRIC_VERSION, compare_notation,
    evaluate_fidelity as evaluate_at_time, text_hash,
)
from src.parallel_source_v4.fidelity_report import read_bound, rescore
from src.parallel_source_v4.metrics import score_case as score_at_time, summary
from trace_gc.pdf_source_parallel_v4 import compare
from trace_gc.pdf_structure_parallel_v4 import seal

TEXT = "The study establishes a bounded scientific statement. " * 5
EVALUATED_AT = "2026-09-28T12:00:00+00:00"


def evaluate_fidelity(prediction, reference):
    return evaluate_at_time(prediction, reference, evaluated_at=EVALUATED_AT)


def score_case(case_id, prediction, reference):
    return score_at_time(case_id, prediction, reference, evaluated_at=EVALUATED_AT)


def span(line_id, start, end, text=None):
    value = {"line_id": line_id, "start": start, "end": end, "page_no": 1}
    if text is not None:
        value["text"] = text
    return value


def reviewed(text=TEXT):
    source_spans = [span("line-a", 1, len(text) + 1, text)]
    review = {"reviewer_kind": "assistant", "reviewer": "authored-fixture-reviewer",
              "reviewed_at": "2026-09-28T10:00:00+00:00",
              "reference_text_sha256": text_hash(text),
              "source_sha256": "a" * 64, "page_sha256": "b" * 64,
              "notation": {"status": "pass", "evidence_id": "fixture:notation"},
              "boundary": {"status": "pass", "evidence_id": "fixture:boundary",
                           "representation": "native_spans", "native_sha256": "c" * 64,
                           "section_owner": "abstract", "reference_spans": source_spans,
                           "closing_boundary": {"kind": "body_section", "line_id": "introduction"}}}
    reference = {"status": "complete", "text": text, "fidelity_review": review}
    prediction = {"status": "complete", "proposal": True, "complete_candidate": True, "text": text,
                  "source_sha256": "a" * 64, "page_sha256": "b" * 64,
                  "native_sha256": "c" * 64, "section_owner": "abstract",
                  "spans": copy.deepcopy(source_spans)}
    return prediction, reference


class NotationTests(unittest.TestCase):
    def test_legacy_blind_spots_fail_additive_metric(self):
        for left, right in (("x = 1", "x != 1"), ("x + y", "x - y"), ("10^5", "105")):
            with self.subTest(left=left):
                self.assertTrue(compare(left, right)["text_match_98"])
                self.assertTrue(compare(left, right)["boundary_and_98_match"])
                self.assertEqual(compare_notation(left, right)["status"], "fail")

    def test_only_documented_rendering_equivalences_pass(self):
        for left, right in (("x=1", "x = 1"), ("x − y", "x - y"),
                            ("x² = 10⁵", "x^{2} = 10^5"),
                            ("H₂O", "H_{2}O"), ("ofﬁce", "office"),
                            ("cafe\u0301", "café"), ("alpha\n beta", "alpha beta")):
            with self.subTest(left=left):
                self.assertEqual(compare_notation(left, right)["status"], "pass")

    def test_sign_units_negation_order_and_script_are_significant(self):
        pairs = [("x=-1", "x=1"), ("x²", "x₂"), ("10^5", "10^6"),
                 ("1 mM", "1 mm"), ("1 mg", "1 g"), ("is not equal", "is equal"),
                 ("x=1; y=2", "y=2; x=1"), ("a b", "ab"), ("A", "a"),
                 ("1.0", "10"), ("x—y", "x-y"), ("x+y", "y+x")]
        for left, right in pairs:
            with self.subTest(left=left):
                self.assertEqual(compare_notation(left, right)["status"], "fail")

    def test_compound_operators_do_not_erase_lexical_boundaries(self):
        for left, right in (("n! = m", "n != m"), ("x < = y", "x <= y"),
                            ("x - > y", "x -> y"), ("x * * y", "x ** y"),
                            ("x + + y", "x ++ y")):
            with self.subTest(left=left):
                self.assertEqual(compare_notation(left, right)["status"], "fail")
        self.assertEqual(compare_notation("x != y", "x!=y")["status"], "pass")

    def test_unbraced_scripts_never_backtrack_to_a_partial_exponent(self):
        for left, right in (("x^12a", "x^{1}2a"), ("x_123a", "x_{12}3a"),
                            ("x^a2", "x^{a}2"), ("x^12ab", "x^{1}2ab"),
                            ("x^12α", "x^{12}α"), ("x^12.3", "x^{12}.3")):
            with self.subTest(left=left):
                self.assertEqual(compare_notation(left, right)["status"], "fail")
        self.assertEqual(compare_notation("x^12 + 1", "x^{12}+1")["status"], "pass")

    def test_identical_text_without_review_is_not_verified(self):
        prediction, reference = reviewed()
        reference.pop("fidelity_review")
        result = evaluate_fidelity(prediction, reference)
        self.assertEqual(result["notation_comparison"]["status"], "pass")
        self.assertEqual(result["notation"]["status"], "unresolved")
        self.assertFalse(result["verified_correct_proposal"])

    def test_attribution_and_source_binding_required(self):
        for mutation in ("reviewer", "timezone", "text", "source", "native"):
            prediction, reference = reviewed()
            review = reference["fidelity_review"]
            if mutation == "reviewer":
                del review["reviewer"]
            elif mutation == "timezone":
                review["reviewed_at"] = "2026-09-28T10:00:00"
            elif mutation == "text":
                review["reference_text_sha256"] = "d" * 64
            elif mutation == "source":
                prediction["source_sha256"] = "d" * 64
            else:
                prediction["native_sha256"] = "d" * 64
            with self.subTest(mutation=mutation):
                result = evaluate_fidelity(prediction, reference)
                self.assertFalse(result["verified_correct_proposal"])

    def test_unresolved_or_failed_reference_review_cannot_certify(self):
        for status in ("unresolved", "fail"):
            prediction, reference = reviewed()
            reference["fidelity_review"]["notation"]["status"] = status
            result = evaluate_fidelity(prediction, reference)
            self.assertEqual(result["notation"]["status"], "unresolved")
            self.assertEqual(result["notation"]["review_status"], status)
            self.assertFalse(result["verified_correct_proposal"])

    def test_not_applicable_requires_attribution_and_cannot_clear_math_hold(self):
        prediction, reference = reviewed()
        reference["fidelity_review"]["notation"]["status"] = "not_applicable"
        result = evaluate_fidelity(prediction, reference)
        self.assertEqual(result["notation"]["status"], "not_applicable")
        reference["math_review_required"] = True
        result = evaluate_fidelity(prediction, reference)
        self.assertEqual(result["notation"]["status"], "unresolved")
        self.assertFalse(result["verified_correct_proposal"])

    def test_review_requires_recorded_evaluation_time_and_cannot_postdate_it(self):
        prediction, reference = reviewed()
        missing = evaluate_at_time(prediction, reference)
        self.assertFalse(missing["verified_correct_proposal"])
        reference["fidelity_review"]["reviewed_at"] = "2999-01-01T00:00:00Z"
        future = evaluate_fidelity(prediction, reference)
        self.assertEqual(future["notation"]["status"], "unresolved")
        self.assertFalse(future["verified_correct_proposal"])
        self.assertEqual(future["evaluated_at"], EVALUATED_AT)


class BoundaryTests(unittest.TestCase):
    def test_reviewed_exact_spans_and_ownership_pass(self):
        prediction, reference = reviewed()
        result = evaluate_fidelity(prediction, reference)
        self.assertTrue(result["verified_correct_proposal"])
        self.assertEqual(result["boundary"]["status"], "pass")
        self.assertEqual(result["source_location"]["status"], "pass")

    def test_adjacent_span_segmentation_is_not_a_boundary_error(self):
        prediction, reference = reviewed()
        prediction["spans"] = [span("line-a", 1, 10), span("line-a", 10, len(TEXT) + 1)]
        self.assertEqual(evaluate_fidelity(prediction, reference)["boundary"]["status"], "pass")

    def test_prefix_suffix_footnote_detected_despite_legacy_success(self):
        prediction, reference = reviewed()
        prediction["text"] = "*" + TEXT + "†"
        prediction["spans"] = [span("line-a", 0, len(TEXT) + 2, prediction["text"])]
        reference["fidelity_review"]["boundary"]["excluded_spans"] = [
            {"role": "footnote", "spans": [span("line-a", len(TEXT) + 1, len(TEXT) + 2)]}]
        self.assertTrue(compare(prediction["text"], TEXT)["boundary_and_98_match"])
        result = evaluate_fidelity(prediction, reference)
        self.assertEqual(result["boundary"]["status"], "fail")
        self.assertEqual(result["boundary"]["extra_prefix_positions"], 1)
        self.assertEqual(result["boundary"]["extra_suffix_positions"], 1)
        self.assertEqual(result["boundary"]["contamination_by_role"], {"footnote": 1})
        self.assertFalse(result["verified_correct_proposal"])

    def test_same_text_wrong_source_location_fails_boundary(self):
        prediction, reference = reviewed()
        prediction["spans"][0]["line_id"] = "duplicate-abstract"
        result = evaluate_fidelity(prediction, reference)
        self.assertEqual(result["notation_comparison"]["status"], "pass")
        self.assertEqual(result["boundary"]["status"], "fail")

    def test_body_contamination_and_missing_text_are_separate(self):
        prediction, reference = reviewed()
        prediction["spans"] = [span("line-a", 2, len(TEXT) + 1), span("body", 0, 4)]
        reference["fidelity_review"]["boundary"]["excluded_spans"] = [
            {"role": "body", "spans": [span("body", 0, 4)]}]
        boundary = evaluate_fidelity(prediction, reference)["boundary"]
        self.assertEqual(boundary["extra_source_positions"], 4)
        self.assertEqual(boundary["missing_source_positions"], 1)
        self.assertEqual(boundary["contamination_by_role"], {"body": 4})

    def test_reference_cannot_assign_same_spans_to_abstract_and_excluded_body(self):
        prediction, reference = reviewed()
        reference["fidelity_review"]["boundary"]["excluded_spans"] = [
            {"role": "body", "spans": copy.deepcopy(prediction["spans"])}]
        result = evaluate_fidelity(prediction, reference)
        self.assertEqual(result["boundary"]["status"], "unresolved")
        self.assertEqual(result["boundary"]["reason"], "reviewed_abstract_overlaps_excluded_source_role")
        self.assertFalse(result["verified_correct_proposal"])

    def test_reading_order_independent_of_extent(self):
        prediction, reference = reviewed("ABCD")
        spans = [span(key, 0, 1) for key in "abcd"]
        reference["fidelity_review"]["boundary"]["reference_spans"] = spans
        prediction["spans"] = [spans[i] for i in (0, 2, 1, 3)]
        result = evaluate_fidelity(prediction, reference)
        self.assertEqual(result["boundary"]["status"], "pass")
        self.assertEqual(result["reading_order"]["status"], "fail")
        self.assertFalse(result["verified_correct_proposal"])

    def test_unknown_or_wrong_section_owner_cannot_pass(self):
        for owner, expected in ((None, "unresolved"), ("body", "fail")):
            prediction, reference = reviewed()
            prediction["section_owner"] = owner
            self.assertEqual(evaluate_fidelity(prediction, reference)["boundary"]["status"], expected)

    def test_malformed_spans_remain_unresolved(self):
        for spans in ([], [span("x", 0, 2), span("x", 1, 3)],
                      [span("x", True, 2)], [span("x", 0, 100001)],
                      [span("x", 0, 4, "bad")]):
            prediction, reference = reviewed()
            prediction["spans"] = spans
            self.assertEqual(evaluate_fidelity(prediction, reference)["boundary"]["status"], "unresolved")

    def test_image_route_uses_reviewed_regions_without_native_offsets(self):
        prediction, reference = reviewed()
        region = {"page_no": 1, "coord_origin": "TOPLEFT", "bbox": [10, 20, 90, 80]}
        boundary = reference["fidelity_review"]["boundary"]
        boundary.update(representation="image_regions", image_sha256="d" * 64,
                        page_size=[100, 100], reference_regions=[region])
        prediction.update(image_sha256="d" * 64, image_regions=[copy.deepcopy(region)])
        prediction.pop("spans")
        self.assertTrue(evaluate_fidelity(prediction, reference)["verified_correct_proposal"])
        prediction["image_regions"][0]["bbox"][3] = 90
        self.assertEqual(evaluate_fidelity(prediction, reference)["boundary"]["status"], "fail")


class SummaryTests(unittest.TestCase):
    def test_proposal_on_known_partial_or_absent_reference_is_false(self):
        for status in ("partial_on_page_one", "no_abstract_text"):
            prediction, reference = reviewed()
            reference["status"] = status
            result = summary([score_case("wrong-scope", prediction, reference)])
            self.assertEqual(result["fidelity"]["reviewed_false_proposals"], 1)
            self.assertEqual(result["fidelity"]["gold_scope_false_proposals"], 1)
            self.assertEqual(result["fidelity"]["source_dimension_false_proposals"], 0)
            self.assertEqual(result["fidelity"]["verified_correct_proposals"], 0)

    def test_inconsistent_proposal_state_cannot_be_verified(self):
        for changes in ({"status": "error"}, {"status": "partial"},
                        {"complete_candidate": False}, {"proposal": 1}, {"proposal": "true"}):
            prediction, reference = reviewed()
            prediction.update(changes)
            with self.subTest(changes=changes):
                self.assertFalse(evaluate_fidelity(prediction, reference)["verified_correct_proposal"])

    def test_withheld_and_unresolved_do_not_become_correct_proposals(self):
        prediction, reference = reviewed()
        prediction["proposal"] = False
        rows = [score_case("withheld", prediction, reference)]
        result = summary(rows)
        self.assertEqual(result["correct_proposals_98"], 0)
        self.assertEqual(result["fidelity"]["verified_correct_proposals"], 0)
        self.assertEqual(result["fidelity"]["verified_complete_abstract_recall"], 0.0)
        self.assertIsNone(result["fidelity"]["verified_fraction_of_all_proposals"])

    def test_mixed_denominators_keep_absent_partial_error_and_unresolved(self):
        rows = []
        for sid, status in (("complete", "complete"), ("partial", "partial_on_page_one"),
                            ("absent", "no_abstract_text"), ("unknown", "uncertain")):
            rows.append(score_case(sid, {"text": "", "status": "error", "proposal": False},
                                   {"text": TEXT if status == "complete" else "", "status": status}))
        result = summary(rows)
        self.assertEqual(result["pages"], 4)
        self.assertEqual(result["states"], {"error": 4})
        fidelity = result["fidelity"]
        self.assertEqual(fidelity["pages"], 4)
        self.assertEqual(fidelity["review_workload"], 4)
        self.assertEqual(fidelity["notation"]["eligible_reviewed_cases"], 0)
        self.assertIsNone(fidelity["notation"]["pass_fraction_among_eligible"])
        self.assertEqual(fidelity["notation"]["states"]["unresolved"], 4)
        self.assertEqual(len(fidelity["gold_states"]), 4)
        self.assertEqual(result["legacy_metric_version"], LEGACY_METRIC_VERSION)
        self.assertEqual(fidelity["metric_version"], FIDELITY_METRIC_VERSION)

    def test_false_and_unverified_proposals_are_separate(self):
        prediction, reference = reviewed("x = 1")
        prediction["text"] = "x != 1"
        rows = [score_case("bad", prediction, reference),
                score_case("missing", {"text": TEXT, "status": "complete", "proposal": True},
                           {"text": TEXT, "status": "complete"})]
        result = summary(rows)["fidelity"]
        self.assertEqual(result["reviewed_false_proposals"], 1)
        self.assertEqual(result["not_verified_proposals"], 2)


class SidecarTests(unittest.TestCase):
    def make_saved(self, root):
        prediction, reference = reviewed()
        reference.pop("fidelity_review")
        seal(prediction)
        row = score_case("f001", prediction, reference)
        row.pop("fidelity")
        row.pop("legacy_metric_version")
        write_once(root / "labels.json", {"f001": reference})
        write_once(root / "old/assessments/primary/f001.json", prediction)
        write_once(root / "old/results.json", {"details": {"primary": [row]}})
        write_once(root / "baseline/f001.json", {**prediction, "eligible_for_jev": True})
        return prediction

    def test_rescore_preserves_inputs_and_rejects_historical_destinations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_saved(root)
            original = digest(root / "old/results.json")
            result = rescore(root, "old", "labels.json", "baseline", "fresh")
            self.assertTrue(result["legacy_metrics_replayed"])
            self.assertEqual(result["metrics"]["primary"]["correct_proposals_98"], 1)
            self.assertEqual(result["metrics"]["primary"]["fidelity"]["verified_correct_proposals"], 0)
            self.assertEqual(digest(root / "old/results.json"), original)
            self.assertEqual(read(root / "fresh/results.json")["v2_baseline"]["correct_proposals_98"], 1)
            for destination in ("old/sidecar", "baseline", "validation_v2/new"):
                with self.assertRaises(ValueError):
                    rescore(root, "old", "labels.json", "baseline", destination)

    def test_bound_reader_hashes_the_bytes_it_parses(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            initial = b'{"generation":"A"}'
            path.write_bytes(initial)
            original_read = Path.read_bytes
            def changing_read(file):
                raw = original_read(file)
                file.write_bytes(b'{"generation":"B"}')
                return raw
            with patch.object(Path, "read_bytes", changing_read):
                value, identity = read_bound(path)
            self.assertEqual(value, {"generation": "A"})
            self.assertEqual(identity, hashlib.sha256(initial).hexdigest())

    def test_rescore_rechecks_parsed_input_hashes_before_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_saved(root)
            def changing_reader(path):
                value, identity = read_bound(path)
                if path.name == "labels.json":
                    path.write_text(json.dumps(value) + " ", encoding="utf-8")
                return value, identity
            with patch("src.parallel_source_v4.fidelity_report.read_bound", changing_reader):
                with self.assertRaisesRegex(ValueError, "rescore_input_changed"):
                    rescore(root, "old", "labels.json", "baseline", "fresh")
            self.assertFalse((root / "fresh/results.json").exists())

    def test_rescore_rejects_broken_assessment_seal_and_future_evaluation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prediction = self.make_saved(root)
            prediction["source_sha256"] = "d" * 64
            (root / "old/assessments/primary/f001.json").write_text(json.dumps(prediction), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "assessment_digest_mismatch"):
                rescore(root, "old", "labels.json", "baseline", "fresh")
            with self.assertRaisesRegex(ValueError, "evaluation_time_requires_timezone_and_cannot_be_future"):
                rescore(root, "old", "labels.json", "baseline", "future", evaluated_at="2999-01-01T00:00:00Z")

    def test_bound_reader_rejects_duplicate_keys_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            for text in ('{"id":1,"id":2}', '{"value":NaN}'):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_bound(path)


if __name__ == "__main__":
    unittest.main()
