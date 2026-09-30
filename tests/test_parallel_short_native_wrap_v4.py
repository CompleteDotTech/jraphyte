"""A short exact native wrap must survive, without joining a competing lane."""
import unittest

from test_parallel_source_v4 import ABSTRACT, BODY, assess, line
from src.parallel_source_v4.adapters import document, item
from trace_gc.pdf_source_parallel_v4 import locate


FIRST = ABSTRACT + " " + BODY + " " + ABSTRACT
SECOND = BODY + " " + ABSTRACT
TEXT = FIRST + " Small but vital. " + SECOND


def case(*, short_x=40, short_y=115, short_bold=False, extra=()):
    native = [line(0, "Abstract", 70), line(1, FIRST, 100),
              line(2, "Small but vital.", short_y, x=short_x,
                   right=short_x + 72, bold=short_bold),
              line(3, "Unrelated right column material.", 100, x=320, right=560),
              line(4, SECOND, 140), line(5, "1 Introduction", 170), *extra]
    model = document([item(0, "Abstract", "section_header", [native[0]["bbox"]]),
                      item(1, FIRST + " Small but vital.", "text", [[40, 100, 280, 127]]),
                      item(2, SECOND, "text", [native[4]["bbox"]]),
                      item(3, "1 Introduction", "section_header", [native[5]["bbox"]])])
    return native, model


class NativeShortWrapTests(unittest.TestCase):
    def test_exact_short_wrap_retained_in_source_order(self):
        native, model = case()
        result = assess(native, model)
        self.assertTrue(result["proposal"], result)
        self.assertEqual(result["status"], "complete")
        self.assertEqual([s["line_id"] for s in result["spans"]], [1, 2, 4])
        self.assertEqual([s["line_id"] for s in locate(TEXT, native)["spans"]], [1, 2, 4])

    def test_duplicate_full_source_occurrence_is_ambiguous(self):
        duplicate = [line(6, FIRST, 200), line(7, "Small but vital.", 215, right=112),
                     line(8, SECOND, 240)]
        native, model = case(extra=duplicate)
        self.assertEqual(locate(TEXT, native)["status"], "ambiguous")
        self.assertFalse(assess(native, model)["proposal"])

    def test_competing_same_lane_row_blocks_wrap(self):
        native, model = case(extra=[line(6, "Interruption.", 113, right=112)])
        result = assess(native, model)
        self.assertFalse(result["proposal"], result)
        self.assertNotIn(2, [s["line_id"] for s in result["spans"]])

    def test_offlane_font_or_spacing_does_not_create_wrap_chain(self):
        for options in ({"short_x": 320}, {"short_bold": True}, {"short_y": 125}):
            with self.subTest(options=options):
                native, model = case(**options)
                result = assess(native, model)
                self.assertFalse(result["proposal"], result)
                self.assertNotIn(2, [s["line_id"] for s in result["spans"]])


if __name__ == "__main__":
    unittest.main()
