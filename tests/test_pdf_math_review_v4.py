import unittest

from trace_gc.pdf_math_review_v4 import packet_from_sidecar
from trace_gc.pdf_source_parallel_v4 import digest_value
from trace_gc.pdf_structure_parallel_v4 import seal

PAGE_HASH = "c" * 64


def packet(sidecar, assessment, native):
    return packet_from_sidecar(sidecar, assessment, native, page_sha256=PAGE_HASH)


def fixture():
    native = [{"id": 0, "text": "a1b", "bbox": [0, 0, 30, 10]},
              {"id": 1, "text": "x", "bbox": [0, 12, 10, 22]}]
    chars = []
    for i, (line, offset, raw, box) in enumerate([
        (0, 0, "a", [0, 0, 8, 10]), (0, 1, "1", [10, 0, 18, 5]),
        (0, 2, "b", [20, 0, 28, 10]), (1, 0, "x", [0, 12, 8, 22])]):
        chars.append({"id": i, "raw": raw, "native_ref": {"line_id": line, "start": offset, "end": offset + 1},
                      "bbox": box, "origin": [box[0], box[3]], "font": "Math", "font_refs": [0],
                      "font_program_status": "embedded_hash_bound", "trace_witnesses": [], "uncertainty": []})
    sidecar = {"status": "diagnostic_only", "accepted": False, "native_identity": "exact",
               "rawdict_projection": "exact", "source": {"original_pdf_sha256": "a" * 64,
               "native_content_sha256": digest_value(native), "physical_page": 1,
               "page_size": [100, 100]},
               "characters": chars, "rules": [{"id": 0, "x0": 9, "x1": 19, "y": 6}],
               "relations": [{"id": 0, "kind": "fraction", "character_ids": [1, 3],
                              "numerator": [1], "denominator": [3], "evidence": {"rule_id": 0},
                              "uncertainty": ["semantic_role_unreviewed"]}]}
    assessment = {"native_sha256": digest_value(native), "source_sha256": "a" * 64,
                  "page_sha256": PAGE_HASH, "physical_page": 1, "page_size": [100, 100],
                  "source_geometry_policy": {"source_sha256": "a" * 64},
                  "text": "a1bx", "spans": [], "closing_boundary": None,
                  "region_ownership": [{"decision": "included", "source_spans": [
                      {"line_id": 0, "start": 0, "end": 3, "text": "a1b", "bbox": [0, 0, 30, 10], "page_no": 1},
                      {"line_id": 1, "start": 0, "end": 1, "text": "x", "bbox": [0, 12, 10, 22], "page_no": 1}]}]}
    return sidecar, seal(assessment), native


class MathReviewPacketTest(unittest.TestCase):
    def test_fraction_geometry_is_bound_but_not_accepted(self):
        sidecar, assessment, native = fixture()
        result = packet(sidecar, assessment, native)
        self.assertEqual(result["relations"][0]["numerator"], [1])
        self.assertEqual(result["relations"][0]["denominator"], [3])
        self.assertEqual(result["relations"][0]["rule"]["id"], 0)
        self.assertFalse(result["accepted"])
        self.assertIsNone(result["scientific_transcription"])

    def test_fraction_crossing_abstract_boundary_is_exposed_and_excluded(self):
        sidecar, assessment, native = fixture()
        assessment["region_ownership"][0]["source_spans"].pop()
        seal(assessment)
        result = packet(sidecar, assessment, native)
        self.assertEqual(result["relations"], [])
        self.assertEqual(result["boundary_crossing_relation_ids"], [0])
        self.assertFalse(result["proposal"])

    def test_control_glyph_and_trace_disagreement_remain_unresolved(self):
        sidecar, assessment, native = fixture()
        native[0]["text"] = "a\x00b"
        sidecar["source"]["native_content_sha256"] = digest_value(native)
        assessment["native_sha256"] = digest_value(native)
        assessment["region_ownership"][0]["source_spans"][0]["text"] = "a\x00b"
        seal(assessment)
        sidecar["characters"][1]["raw"] = "\x00"
        sidecar["characters"][1]["uncertainty"] = ["native_unicode_unresolved", "rawdict_trace_unicode_disagreement"]
        result = packet(sidecar, assessment, native)
        self.assertEqual(result["control_or_replacement_character_ids"], [1])
        self.assertEqual(result["unresolved_character_ids"], [1])
        self.assertFalse(result["accepted"])

    def test_changed_native_or_missing_rule_fails_closed(self):
        sidecar, assessment, native = fixture()
        assessment["native_sha256"] = "0" * 64
        seal(assessment)
        with self.assertRaisesRegex(ValueError, "assessment_native_identity_mismatch"):
            packet(sidecar, assessment, native)
        assessment["native_sha256"] = digest_value(native)
        seal(assessment)
        sidecar["rules"] = []
        with self.assertRaisesRegex(ValueError, "missing_relation_rule"):
            packet(sidecar, assessment, native)

    def test_source_and_page_identity_mismatch_fail_closed(self):
        sidecar, assessment, native = fixture()
        assessment["source_sha256"] = "f" * 64
        seal(assessment)
        with self.assertRaisesRegex(ValueError, "assessment_source_or_page_identity_mismatch"):
            packet(sidecar, assessment, native)
        assessment["source_sha256"] = "a" * 64
        seal(assessment)
        with self.assertRaisesRegex(ValueError, "assessment_source_or_page_identity_mismatch"):
            packet_from_sidecar(sidecar, assessment, native, page_sha256="e" * 64)

    def test_duplicate_and_misaligned_native_character_refs_fail_closed(self):
        sidecar, assessment, native = fixture()
        sidecar["characters"][2]["native_ref"] = dict(sidecar["characters"][1]["native_ref"])
        sidecar["characters"][2]["raw"] = "1"
        with self.assertRaisesRegex(ValueError, "duplicate_native_character_projection"):
            packet(sidecar, assessment, native)
        sidecar, assessment, native = fixture()
        sidecar["characters"][1]["native_ref"]["end"] = 3
        with self.assertRaisesRegex(ValueError, "invalid_native_character_projection"):
            packet(sidecar, assessment, native)

    def test_unmarked_control_or_trace_conflict_fails_closed(self):
        sidecar, assessment, native = fixture()
        native[0]["text"] = "a\x00b"
        sidecar["source"]["native_content_sha256"] = digest_value(native)
        assessment["native_sha256"] = digest_value(native)
        assessment["region_ownership"][0]["source_spans"][0]["text"] = "a\x00b"
        seal(assessment)
        sidecar["characters"][1]["raw"] = "\x00"
        with self.assertRaisesRegex(ValueError, "unmarked_unresolved_native_character"):
            packet(sidecar, assessment, native)
        sidecar["characters"][1]["uncertainty"] = ["native_unicode_unresolved"]
        sidecar["characters"][1]["trace_witnesses"] = [{"unicode": ord("1")}]
        with self.assertRaisesRegex(ValueError, "unmarked_trace_unicode_disagreement"):
            packet(sidecar, assessment, native)

    def test_held_formula_is_separate_and_keywords_cannot_bleed(self):
        sidecar, assessment, native = fixture()
        assessment["region_ownership"][0]["source_spans"].pop()
        held = {"decision": "held", "candidate_native_extent": {"status": "canonical_extent_only",
                "accepted": False, "spans": [{"line_id": 1, "start": 0, "end": 1, "text": "x",
                "bbox": [0, 12, 10, 22], "page_no": 1}]}}
        assessment["region_ownership"].append(held)
        assessment["closing_boundary"] = {"source_spans": [{"bbox": [0, 30, 30, 40]}]}
        seal(assessment)
        result = packet(sidecar, assessment, native)
        self.assertEqual([c["raw"] for c in result["held_candidate"]["characters"]], ["x"])
        self.assertFalse(result["held_candidate"]["accepted"])
        self.assertEqual(result["boundary_crossing_relation_ids"], [0])
        with self.assertRaisesRegex(ValueError, "reviewer_witness_not_bounded_before_closure"):
            packet_from_sidecar(sidecar, assessment, native, page_sha256=PAGE_HASH,
                                witness_line_ids=(0,))


if __name__ == "__main__":
    unittest.main()
