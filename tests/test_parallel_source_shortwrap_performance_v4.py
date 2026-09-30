"""The optimized native wrap search retains its source ownership predicate."""
import copy
import unittest
from unittest.mock import patch

from test_parallel_source_structure_followup_v4 import ABSTRACT, BODY, line
from trace_gc.pdf_geometry_parallel_v4 import logical_rows
from trace_gc.pdf_source_parallel_v4 import _short_laneline_between
import trace_gc.pdf_source_parallel_v4 as source


def page():
    first = ABSTRACT + " " + BODY + " " + ABSTRACT
    second = BODY + " " + ABSTRACT
    return [line(0, "Abstract", 70), line(1, first, 100),
            line(2, "Small but vital.", 115, right=112),
            line(3, "Unrelated right column material.", 100, x=320, right=560),
            line(4, second, 140), line(5, "1 Introduction", 170)]


class ShortWrapPerformanceTests(unittest.TestCase):
    def test_cache_reuses_fonts_without_changing_acceptance(self):
        native = page()
        rows = logical_rows(native)
        original = source._paragraph_font
        with patch.object(source, "_paragraph_font", wraps=original) as font:
            cache = {}
            for _ in range(10):
                self.assertTrue(_short_laneline_between(native[1], native[2], native[4], rows, cache))
            self.assertEqual(font.call_count, 3)
        self.assertTrue(_short_laneline_between(native[1], native[2], native[4], rows))

    def test_geometry_and_typography_rejections_match_uncached(self):
        for change in ("off_lane", "large_gap", "other_font", "other_size",
                       "no_sentence", "intervening_row"):
            with self.subTest(change=change):
                native = copy.deepcopy(page())
                if change == "off_lane":
                    native[2]["bbox"][0] += 40
                elif change == "large_gap":
                    native[2]["bbox"][1] += 30
                    native[2]["bbox"][3] += 30
                elif change == "other_font":
                    native[2]["spans"][0]["font"] = "Other"
                elif change == "other_size":
                    native[2]["spans"][0]["size"] += 2
                elif change == "no_sentence":
                    native[2]["text"] = "Small but vital"
                else:
                    native.append(line(6, "Intervening source line.", 113, right=112))
                rows = logical_rows(native)
                uncached = _short_laneline_between(native[1], native[2], native[4], rows)
                cached = _short_laneline_between(native[1], native[2], native[4], rows, {})
                self.assertEqual(cached, uncached)
                self.assertFalse(cached)

    def test_invalid_geometry_skips_unneeded_candidate_font_work(self):
        native = page()
        native[2]["bbox"][0] += 40
        original = source._paragraph_font
        with patch.object(source, "_paragraph_font", wraps=original) as font:
            self.assertFalse(_short_laneline_between(native[1], native[2], native[4],
                                                      logical_rows(native), {}))
            self.assertEqual(font.call_count, 1)


if __name__ == "__main__":
    unittest.main()
