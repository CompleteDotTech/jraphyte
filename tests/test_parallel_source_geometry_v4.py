"""Logical-row counterexamples; authored fixtures are not corpus validation."""
import copy
import importlib.util
import unittest

from trace_gc.pdf_geometry_parallel_v4 import VERSION, logical_rows
from trace_gc.pdf_source_parallel_v4 import locate, source_lines, validate_box, validate_source_spans


def line(i, text, x, y, right, *, size=10, block=0, height=12):
    return {"id": i, "text": text, "bbox": [x, y, right, y+height], "page_no": 1,
            "block_id": block, "line_in_block": i,
            "spans": [{"start": 0, "end": len(text), "text": text, "size": size,
                       "font": "Regular", "flags": 0, "color": 0}]}


class LogicalGeometryTests(unittest.TestCase):
    def assert_located(self, text, native, column_change=False, **kwargs):
        result = locate(text, native, **kwargs)
        self.assertEqual(result["status"], "located", result)
        self.assertEqual(result["column_change"], column_change, result)
        self.assertEqual(result["logical_geometry"]["version"], VERSION)
        validate_source_spans(result["spans"], native)
        return result

    def test_fragmented_row_reorders_native_units_without_losing_offsets(self):
        native = [line(0, "A stable paragraph begins here.", 40, 80, 280),
                  line(2, "preserve the response.", 161, 100, 280),
                  line(1, "Our observations", 40, 100, 150),
                  line(3, "The estimates remain consistent.", 40, 120, 280)]
        original = copy.deepcopy(native)
        result = self.assert_located("Our observations preserve the response. The estimates remain consistent.", native)
        self.assertEqual([s["line_id"] for s in result["spans"]], [1, 2, 3])
        self.assertEqual(native, original)
        self.assertEqual(result["logical_geometry"]["rows"][0]["native_line_ids"], [1, 2])

    def test_short_final_fragment_then_next_row_is_one_column(self):
        native = [line(0, "The prior row establishes this paragraph.", 40, 80, 280),
                  line(1, "Measurements establish", 40, 100, 250),
                  line(2, "stability.", 258, 100, 280),
                  line(3, "Repeated trials agree.", 40, 120, 240)]
        self.assert_located("Measurements establish stability. Repeated trials agree.", native)

    def test_superscript_and_font_split_keep_exact_native_characters(self):
        native = [line(0, "We obtain x", 40, 100, 130),
                  line(1, "2", 130, 95, 135, size=7, height=8),
                  line(2, " for each trial.", 135, 100, 280),
                  line(3, "Independent measurements agree.", 40, 120, 280)]
        result = self.assert_located("We obtain x2 for each trial.", native)
        self.assertEqual([s["text"] for s in result["spans"]], ["We obtain x", "2", " for each trial."])
        self.assertTrue(any(join["reason"] == "attached_script" for row in result["logical_geometry"]["rows"] for join in row["joins"]))

    def test_same_size_raised_formula_fragment_uses_owned_row_support(self):
        native = [line(0, "Prior continuous statement.", 40, 80, 280, block=1),
                  line(1, "We obtain x", 40, 100, 130, block=1),
                  line(2, "2", 130, 94, 137, height=10, block=1),
                  line(3, " for each trial.", 137, 100, 280, block=2),
                  line(4, "The next continuous statement.", 40, 120, 280, block=2)]
        result = self.assert_located("We obtain x2 for each trial.", native)
        self.assertEqual([s["line_id"] for s in result["spans"]], [1, 2, 3])

    def test_overlapping_font_run_keeps_corroborated_formula_row_context(self):
        native = [line(0, "Prior continuous statement.", 40, 80, 280, block=1),
                  line(1, "We obtain", 40, 100, 120, block=1),
                  line(2, " x", 112, 100, 130, block=1),
                  line(3, "2", 130, 94, 137, height=10, block=1),
                  line(4, " for each trial.", 137, 100, 280, block=2),
                  line(5, "The next continuous statement.", 40, 120, 280, block=2)]
        result = self.assert_located("We obtain x2 for each trial.", native)
        self.assertEqual([s["line_id"] for s in result["spans"]], [1, 2, 3, 4])

    def test_no_source_evidence_for_short_gutter_keeps_hold(self):
        native = [line(0, "Left column argument.", 40, 100, 280),
                  line(1, "Unrelated right column.", 290, 100, 530)]
        self.assert_located("Left column argument. Unrelated right column.", native, True)

    def test_smaller_adjacent_prose_is_not_an_attached_script(self):
        native = [line(0, "Main argument.", 40, 100, 200),
                  line(1, "Smaller side commentary.", 200, 102, 280, size=7, height=10)]
        self.assert_located("Main argument. Smaller side commentary.", native, True)

    def test_compact_smaller_text_needs_script_displacement_or_row_support(self):
        native = [line(0, "Main argument.", 40, 100, 200),
                  line(1, "See.", 200, 102, 213, size=7, height=10)]
        self.assert_located("Main argument. See.", native, True)

    def test_repeated_narrow_gutter_same_block_is_not_joined(self):
        native = [line(0, "A full-width heading", 40, 80, 530),
                  line(1, "Left argument begins.", 40, 100, 280),
                  line(2, "Right body begins.", 290, 100, 530),
                  line(3, "Left second row.", 40, 120, 280),
                  line(4, "Right second row.", 290, 120, 530),
                  line(5, "Left third row.", 40, 130, 280),
                  line(6, "Right third row.", 290, 130, 530)]
        self.assert_located("Left argument begins. Right body begins.", native, True)

    def test_full_width_abstract_cannot_support_join_across_body_blocks(self):
        native = [line(0, "Full width abstract closes here.", 40, 80, 530, block=0),
                  line(1, "Left body argument.", 40, 100, 280, block=1),
                  line(2, "Right body argument.", 290, 100, 530, block=2)]
        self.assert_located("Left body argument. Right body argument.", native, True)

    def test_single_full_width_row_cannot_bridge_same_block_columns(self):
        native = [line(0, "Full width content.", 40, 80, 530),
                  line(1, "Left body argument.", 40, 100, 280),
                  line(2, "Right body argument.", 290, 100, 530)]
        self.assert_located("Left body argument. Right body argument.", native, True)

    def test_two_preceding_full_width_rows_do_not_prove_body_continuation(self):
        native = [line(0, "Full width beginning.", 40, 72, 530),
                  line(1, "Full width ending.", 40, 86, 530),
                  line(2, "Left body argument.", 40, 100, 280),
                  line(3, "Right body argument.", 290, 100, 530)]
        self.assert_located("Left body argument. Right body argument.", native, True)

    def test_one_neighboring_gutter_pair_is_sufficient_to_keep_columns(self):
        native = [line(0, "Full width content.", 40, 80, 530),
                  line(1, "Left body argument.", 40, 100, 280),
                  line(2, "Right body argument.", 290, 100, 530),
                  line(3, "Left continuation.", 40, 120, 280),
                  line(4, "Right continuation.", 290, 120, 530)]
        self.assert_located("Left body argument. Right body argument.", native, True)

    def test_raised_compact_prose_needs_owned_row_corroboration(self):
        native = [line(0, "Main argument.", 40, 100, 200),
                  line(1, "See.", 200, 95, 213, size=7, height=10)]
        self.assert_located("Main argument. See.", native, True)

    @unittest.skipUnless(importlib.util.find_spec("fitz"), "PyMuPDF not installed")
    def test_real_rotated_text_without_saved_direction_stays_held(self):
        import fitz
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.insert_text((40, 110), "Main argument.", fontsize=10)
            edge = source_lines(page)[0]["bbox"][2]
            page.insert_text((edge+7.5, 105), "See.", fontsize=7, rotate=90)
            native = source_lines(page)
        self.assertTrue(all("dir" not in value for value in native))
        result = locate("Main argument. See.", native)
        self.assertIn(result["status"], {"unlocated", "located"})
        self.assertTrue(result["status"] == "unlocated" or result["column_change"], result)

    def test_full_width_abstract_above_two_columns_keeps_local_order(self):
        native = [line(0, "Full width abstract begins here.", 40, 60, 530),
                  line(1, "This complete result closes the abstract.", 40, 80, 530),
                  line(2, "Left body material.", 40, 130, 280),
                  line(3, "Right body material.", 310, 130, 550)]
        result = self.assert_located("Full width abstract begins here. This complete result closes the abstract.", native)
        self.assertEqual([s["line_id"] for s in result["spans"]], [0, 1])
        self.assert_located("Left body material. Right body material.", native, True)

    def test_wrong_neighboring_column_region_cannot_locate_text(self):
        native = [line(0, "Unique abstract content appears here.", 40, 100, 280),
                  line(1, "Different material appears here.", 310, 100, 550)]
        result = locate(native[0]["text"], native, region_boxes=[[310, 90, 550, 120]])
        self.assertEqual(result["status"], "unlocated")

    def test_duplicate_complete_occurrences_remain_ambiguous(self):
        text = "The same complete source statement appears twice."
        native = [line(0, text, 40, 100, 280), line(1, text, 310, 100, 550)]
        result = locate(text, native)
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["reason"], "multiple_source_occurrences")

    def test_rotated_sidebar_cannot_bridge_rows(self):
        native = [line(0, "A left fragment.", 40, 100, 130),
                  line(1, "A right fragment.", 140, 100, 280),
                  line(2, "Rotated sidebar.", 30, 80, 300, height=100)]
        native[2]["dir"] = [0, -1]
        self.assert_located("A left fragment. A right fragment.", native, True)

    def test_script_cannot_transitively_merge_adjacent_rows(self):
        native = [line(0, "The first row.", 40, 100, 150),
                  line(1, "2", 150, 106, 155, size=7, height=8),
                  line(2, "The second row.", 155, 114, 280)]
        rows = logical_rows(native)
        self.assertFalse(any({0, 2} <= {line["id"] for line in row["lines"]} for row in rows))

    def test_alignment_threshold_and_off_page_policy_are_unchanged(self):
        with self.assertRaisesRegex(ValueError, "alignment_threshold"):
            locate("text", [], threshold=.97)
        with self.assertRaisesRegex(ValueError, "outside_first_page"):
            validate_box([10, -.279, 100, 10], [612, 792])

    def test_native_extraction_does_not_write_logical_fields_or_change_schema(self):
        class Rect:
            width, height = 600, 800
        class Page:
            number, rect = 0, Rect()
            def get_text(self, kind, sort):
                return {"blocks": [{"type": 0, "lines": [{"bbox": [40, 100, 80, 112],
                    "spans": [{"text": "Exact x2.", "bbox": [40, 100, 80, 112],
                               "font": "Regular", "size": 10}]}]}]}
        native = source_lines(Page())
        expected = [{"id": 0, "block_id": 0, "line_in_block": 0, "page_no": 1,
                    "bbox": [40, 100, 80, 112], "text": "Exact x2.",
                    "spans": [{"start": 0, "end": 9, "text": "Exact x2.", "font": "Regular", "size": 10,
                               "flags": 0, "color": 0, "bbox": [40, 100, 80, 112]}]}]
        self.assertEqual(native, expected)
        logical_rows(native)
        self.assertEqual(native, expected)


if __name__ == "__main__":
    unittest.main()
