"""Causal source fixtures, not private-paper labels or held-out accuracy claims."""
import copy
import unittest

from trace_gc.pdf_source_v3 import assess_document, align_text, compare, digest, reconstruct, verify_scholarly_field
from src.abstract_validation_v3.adapters import native_document, olmocr_assess, mineru_assess

ABSTRACT_TEXT = ("We investigate transport in a layered material using controlled measurements. "
                 "The results show that boundary conditions determine the response, and we establish a reproducible estimate.")
BODY_TEXT = "This section describes the experiments and motivates a distinct set of measurements."


def line(i, text, y=100, x=40, right=285, *, color=0, bold=False, block=None):
    return {"id": i, "page_no": 1, "text": text, "bbox": [x, y, right, y+12],
            "font": "Fixture-Bold" if bold else "Fixture-Regular", "flags": 16 if bold else 0,
            "size": 11, "color": color, "block_id": i if block is None else block}


def assess(lines, doc=None, **kwargs):
    return assess_document(doc or native_document(lines), page_size=(600, 800),
                           source_sha256="a"*64, page_sha256="b"*64,
                           native_lines=lines, **kwargs)


class SourceBoundaryTests(unittest.TestCase):
    def test_dot_leader_near_abstract_heading_is_not_a_proposal(self):
        lines = [line(0, "Abstract", 70), line(1, ". . . . . . . . . . . . .", 90),
                 line(2, "1 Introduction", 115)]
        result = assess(lines)
        self.assertEqual(result["status"], "uncertain")
        self.assertFalse(result["proposed"])
        self.assertIn("insufficient_abstract_prose", result["reasons"])

    def test_marked_author_footnote_closes_abstract_without_contamination(self):
        for note in ("∗Both authors contributed equally to this research.",
                     "*Work done while at another institution."):
            with self.subTest(note=note):
                lines = [line(0, "Abstract", 70), line(1, ABSTRACT_TEXT, 90),
                         line(2, note, 130)]
                result = assess(lines)
                self.assertEqual(result["status"], "complete")
                self.assertEqual(result["text"], ABSTRACT_TEXT)
                self.assertEqual(result["closing_boundary"]["kind"], "metadata_or_non_abstract")

    def test_zero_width_combining_glyph_keeps_valid_native_line(self):
        text = "Abstract " + ABSTRACT_TEXT + " ã"
        first = line(0, text, 70)
        first["runs"] = [
            {"start": 0, "end": len(text)-1, "text": text[:-1], "bbox": first["bbox"]},
            {"start": len(text)-1, "end": len(text), "text": "̃", "bbox": [200, 70, 200, 82]},
        ]
        result = assess([first, line(1, "1 Introduction", 115)])
        self.assertNotEqual(result["status"], "error")
        first["runs"][-1]["text"] = "x"
        first["text"] = text[:-1] + "x"
        self.assertEqual(assess([first, line(1, "1 Introduction", 115)])["status"], "error")

    def test_explicit_abstract_with_source_boundary(self):
        lines = [line(0, "Abstract", 70), line(1, ABSTRACT_TEXT, 90), line(2, "1 Introduction", 115)]
        p = assess(lines)
        self.assertEqual(p["text"], ABSTRACT_TEXT)
        self.assertTrue(p["proposed"])
        self.assertEqual(p["status"], "complete")
        self.assertEqual(reconstruct(p["spans"], lines), ABSTRACT_TEXT)
        self.assertFalse(p["eligible_for_jev"])
        self.assertFalse(p["verified_admission"])
        self.assertFalse(p["source_bytes_verified"])

    def test_inline_overview_in_same_region_is_not_abstract(self):
        lines = [line(0, "Abstract " + ABSTRACT_TEXT + " Overview: " + BODY_TEXT)]
        p = assess(lines)
        self.assertEqual(p["text"], ABSTRACT_TEXT)
        self.assertTrue(p["proposed"])
        self.assertEqual(p["closing_boundary"]["kind"], "body_section")
        self.assertIn("Overview", p["closing_boundary"]["source_span"]["text"])

    def test_overview_word_in_prose_is_not_a_boundary(self):
        text = "We provide an overview of the observed measurements. " + ABSTRACT_TEXT
        p = assess([line(0, "Abstract " + text), line(1, "2 Methods", 130)])
        self.assertEqual(p["text"], text)
        self.assertTrue(p["proposed"])

    def test_colored_synopsis_is_separate_and_review_only(self):
        lines = [line(0, "Abstract", 70), line(1, ABSTRACT_TEXT, 90, bold=True),
                 line(2, "Our laboratory studies unusual phases for a broader audience.", 125, color=0x1666FF),
                 line(3, "1 Introduction", 160)]
        p = assess(lines)
        self.assertEqual(p["text"], ABSTRACT_TEXT)
        self.assertEqual(p["status"], "uncertain")
        self.assertFalse(p["proposed"])
        self.assertEqual(p["closing_boundary"]["kind"], "separate_styled_region")

    def test_wrong_tree_order_cannot_select_other_column(self):
        lines = [line(0, "Abstract", 70), line(1, ABSTRACT_TEXT, 90, bold=True),
                 line(2, "1 Introduction", 130), line(3, BODY_TEXT, 90, 330, 570)]
        doc = native_document(lines)
        doc["body"]["children"] = list(reversed(doc["body"]["children"]))
        p = assess(lines, doc)
        self.assertEqual(p["text"], ABSTRACT_TEXT)
        self.assertNotIn(3, [s["line_id"] for s in p["spans"]])
        self.assertTrue(p["proposed"])

    def test_right_column_abstract_is_not_replaced_by_left_preference(self):
        lines = [line(0, BODY_TEXT, 80), line(1, "Abstract", 70, 330, 570),
                 line(2, ABSTRACT_TEXT, 90, 330, 570), line(3, "1 Introduction", 130, 330, 570)]
        self.assertEqual(assess(lines)["text"], ABSTRACT_TEXT)

    def test_inline_dedication_is_not_abstract(self):
        lines = [line(0, "Abstract " + ABSTRACT_TEXT + " Dedicated to our colleagues.")]
        p = assess(lines)
        self.assertEqual(p["text"], ABSTRACT_TEXT)
        self.assertTrue(p["proposed"])
        self.assertEqual(p["closing_boundary"]["kind"], "metadata_or_non_abstract")

    def test_author_list_is_not_unlabelled_abstract_even_with_field(self):
        text = "Mira Stone, Dev Shah, Li Park, J. Jones, K. Smith, R. Roy and N. Fox."
        p = assess([line(0, text), line(1, "1 Introduction", 140)], scholarly_abstract=text)
        self.assertFalse(p["proposed"])
        self.assertNotEqual(p["status"], "complete")

    def test_affiliation_is_not_abstract_even_if_field_matches(self):
        text = "Department of Physics, Example University, Centre for Advanced Measurements."
        p = assess([line(0, text), line(1, "1 Introduction", 140)], scholarly_abstract=text)
        self.assertFalse(p["proposed"])

    def test_author_note_field_cannot_create_abstract(self):
        text = "Author notes: We investigate measurements at two institutions and contributed equally."
        p = assess([line(0, text), line(1, "1 Introduction", 140)], scholarly_abstract=text)
        self.assertEqual(p["status"], "absent")
        self.assertFalse(p["proposed"])

    def test_inline_author_note_closes_before_metadata(self):
        p = assess([line(0, "Abstract " + ABSTRACT_TEXT + " Author notes: The contributors are listed below.")])
        self.assertEqual(p["text"], ABSTRACT_TEXT)
        self.assertTrue(p["proposed"])

    def test_unlabelled_field_needs_actual_bounded_source(self):
        lines = [line(0, ABSTRACT_TEXT), line(1, "1 Introduction", 140)]
        p = assess(lines, scholarly_abstract=ABSTRACT_TEXT)
        self.assertEqual(p["status"], "complete")
        self.assertEqual(p["scholarly_field_location"]["status"], "located")
        self.assertFalse(p["eligible_for_jev"])

    def test_unlabelled_body_not_rescued_by_scholarly_field(self):
        p = assess([line(0, "1 Introduction", 70), line(1, ABSTRACT_TEXT)], scholarly_abstract=ABSTRACT_TEXT)
        self.assertFalse(p["proposed"])

    def test_highlights_key_points_and_executive_summary_remain_absent(self):
        for label in ("Highlights", "Key Points", "Executive Summary", "Graphical Abstract", "Contents"):
            with self.subTest(label=label):
                p = assess([line(0, label, 70), line(1, ABSTRACT_TEXT), line(2, "1 Introduction", 150)], scholarly_abstract=ABSTRACT_TEXT)
                self.assertEqual(p["status"], "absent")
                self.assertFalse(p["proposed"])

    def test_grobid_error_is_isolated_even_with_nonempty_field(self):
        p = verify_scholarly_field("do not invent this abstract", native_document([]), page_size=(600,800),
                                  source_sha256="a"*64, page_sha256="b"*64,
                                  native_lines=[], conversion_status="error", conversion_http_status=500)
        self.assertEqual(p["status"], "error")
        self.assertEqual(p["text"], "")
        self.assertFalse(p["scholarly_field_verified"])

    def test_partial_is_not_complete_even_with_matching_grobid_field(self):
        text = ABSTRACT_TEXT[:-1] + " while"
        p = assess([line(0, "Abstract " + text, 730)], scholarly_abstract=text)
        self.assertEqual(p["status"], "partial")
        self.assertFalse(p["proposed"])

    def test_terminal_sentence_without_closing_boundary_always_held(self):
        for y in (100, 730):
            p = assess([line(0, "Abstract " + ABSTRACT_TEXT, y)])
            self.assertEqual(p["status"], "uncertain")
            self.assertFalse(p["proposed"])

    def test_first_page_only_rejects_page_two_layout_and_native_spans(self):
        lines = [line(0, "Abstract " + ABSTRACT_TEXT), line(1, "1 Introduction", 140)]
        doc = native_document(lines)
        doc["texts"][0]["prov"][0]["page_no"] = 2
        self.assertEqual(assess(lines, doc)["status"], "error")
        lines[0]["page_no"] = 2
        self.assertEqual(assess(lines)["status"], "error")

    def test_empty_image_page_needs_source_review(self):
        p = assess([])
        self.assertEqual(p["status"], "uncertain")
        self.assertEqual(p["spans"], [])
        self.assertFalse(p["proposed"])

    def test_reading_order_cycle_and_invalid_boxes_fail_closed(self):
        lines = [line(0, "Abstract " + ABSTRACT_TEXT)]
        doc = native_document(lines)
        doc["texts"][0]["children"] = [{"cref": "#/texts/0"}]
        self.assertEqual(assess(lines, doc)["status"], "error")
        lines[0]["bbox"][0] = float("nan")
        # Invalid source geometry is never serialized into an evidence span.
        self.assertEqual(assess(lines)["status"], "error")

    def test_generation_cap_and_request_budget_are_separate(self):
        lines = [line(0, "Abstract " + ABSTRACT_TEXT), line(1, "1 Introduction", 140)]
        truncated = assess(lines, generation_tokens=4096, generation_limit=4096)
        self.assertEqual(truncated["status"], "truncated")
        self.assertEqual(truncated["request_budget_status"], "not_assessed")
        budget = assess(lines, max_input_chars=50)
        self.assertEqual(budget["status"], "complete")
        self.assertEqual(budget["text"], ABSTRACT_TEXT)
        self.assertEqual(budget["request_budget_status"], "exceeds_character_budget")
        self.assertFalse(budget["proposed"])
        self.assertTrue(budget["selector_proposal"])

    def test_eos_at_token_limit_not_automatically_truncated(self):
        p = assess([line(0,"Abstract "+ABSTRACT_TEXT),line(1,"1 Introduction",140)], generation_tokens=4096, finish_reason="eos")
        self.assertEqual(p["status"], "complete")

    def test_budget_over_4000_never_silently_slices_source(self):
        text = ABSTRACT_TEXT * 25
        p = assess([line(0, "Abstract " + text), line(1, "1 Introduction", 140)])
        self.assertGreater(len(p["text"]), 4000)
        self.assertEqual(p["text"], text)
        self.assertFalse(p["proposed"])

    def test_source_intervals_detect_text_mutation(self):
        lines = [line(0, "Abstract " + ABSTRACT_TEXT), line(1, "1 Introduction", 140)]
        p = assess(lines)
        lines[0]["text"] = lines[0]["text"].replace("transport", "disorder")
        with self.assertRaises(ValueError):
            reconstruct(p["spans"], lines)

    def test_boundary_receipt_is_sealed_with_source(self):
        p = assess([line(0,"Abstract "+ABSTRACT_TEXT),line(1,"1 Introduction",140)])
        value = dict(p); checksum = value.pop("assessment_sha256")
        self.assertEqual(digest(value), checksum)
        value["closing_boundary"]["source_span"]["start"] += 1
        self.assertNotEqual(digest(value), checksum)

    def test_structured_abstract_sections_are_not_body_boundaries(self):
        lines = [line(0,"Abstract",70), line(1,"Methods: We measure the response.",90),
                 line(2,"Results: We observe reproducible transport.",110), line(3,"1 Introduction",140)]
        p = assess(lines)
        self.assertEqual(p["text"], "Methods: We measure the response. Results: We observe reproducible transport.")
        self.assertTrue(p["structured"])
        self.assertTrue(p["proposed"])


class NativeAlignmentTests(unittest.TestCase):
    def test_paragraph_merging_and_split_native_lines(self):
        lines = [line(0,"We measure trans-",90,block=1), line(1,"port and ﬁnite effects.",106,block=1)]
        p = align_text("We measure transport and finite effects.", lines, (600,800))
        self.assertEqual(p["status"], "located")
        self.assertEqual([s["line_id"] for s in p["spans"]],[0,1])
        self.assertEqual(p["text"], "We measure trans- port and ﬁnite effects.")

    def test_native_line_contains_multiple_model_paragraphs(self):
        lines = [line(0,"Header. "+ABSTRACT_TEXT+" Keywords: transport.")]
        p = align_text(ABSTRACT_TEXT,lines,(600,800))
        self.assertEqual(p["status"],"located")
        self.assertEqual(p["spans"][0]["start"],len("Header. "))
        self.assertEqual(p["spans"][0]["text"],ABSTRACT_TEXT)

    def test_repeated_native_text_is_ambiguous(self):
        p = align_text(ABSTRACT_TEXT,[line(0,ABSTRACT_TEXT),line(1,ABSTRACT_TEXT,180)],(600,800))
        self.assertEqual(p["status"],"ambiguous")
        self.assertEqual(p["spans"],[])

    def test_unlocated_ocr_does_not_receive_whole_page_box(self):
        lines = [line(0,"A different document cover")]
        p = olmocr_assess({"status":"success","raw_text":"# Abstract\n\n"+ABSTRACT_TEXT},
                          page_size=(600,800),source_sha256="a"*64,page_sha256="b"*64,native_lines=lines)
        self.assertFalse(p["proposed"])
        self.assertTrue(all(not x["spans"] for x in p["ocr_paragraph_locations"]))
        self.assertFalse(p["model_predicted_coordinates"])

    def test_ocr_paragraph_split_inside_native_line_recovers_source(self):
        lines = [line(0,"Abstract "+ABSTRACT_TEXT),line(1,"1 Introduction",140)]
        raw = {"status":"success","raw_text":"# Abstract\n\n"+ABSTRACT_TEXT.replace("The results", "\n\nThe results")+"\n\n# 1 Introduction"}
        p = olmocr_assess(raw,page_size=(600,800),source_sha256="a"*64,page_sha256="b"*64,native_lines=lines)
        self.assertTrue(p["proposed"])
        self.assertTrue(p["selected_text_in_conversion"])
        self.assertEqual(p["text"],ABSTRACT_TEXT)

    def test_missing_ocr_word_remains_review_only(self):
        lines = [line(0,"Abstract "+ABSTRACT_TEXT),line(1,"1 Introduction",140)]
        raw = {"status":"success","raw_text":"Abstract\n\n"+ABSTRACT_TEXT.replace("controlled ", "")+"\n\n1 Introduction"}
        p = olmocr_assess(raw,page_size=(600,800),source_sha256="a"*64,page_sha256="b"*64,native_lines=lines)
        self.assertFalse(p["proposed"])
        self.assertEqual(p["status"],"uncertain")

    def test_ocr_truncation_has_no_proposal_even_when_prefix_matches(self):
        lines = [line(0,"Abstract "+ABSTRACT_TEXT),line(1,"1 Introduction",140)]
        p = olmocr_assess({"status":"truncated","raw_text":ABSTRACT_TEXT},page_size=(600,800),
                          source_sha256="a"*64,page_sha256="b"*64,native_lines=lines)
        self.assertEqual(p["status"],"truncated")
        self.assertFalse(p["proposed"])

    def test_scoring_definition_including_empty_and_boundary(self):
        self.assertTrue(compare("","")["text_match_98"])
        self.assertFalse(compare("x","")["text_match_98"])
        ref = "a"*1000
        score = compare("z"+ref, ref)
        self.assertTrue(score["text_match_98"])
        self.assertFalse(score["boundary_match"])


if __name__ == "__main__":
    unittest.main()
