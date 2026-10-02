"""A source-owned vector figure can bound an explicit first-page abstract."""
import hashlib
import unittest

try:
    import fitz
except ImportError:
    fitz = None

from trace_gc.pdf_source_parallel_v4 import SourceGeometry, source_lines
from trace_gc.pdf_structure_parallel_v4 import _source_figure_then_intro_closure


@unittest.skipUnless(fitz, "optional PyMuPDF required")
class FigureClosureTests(unittest.TestCase):
    def fixture(self, *, caption=True, intro=True, bars=True, prose=False,
                adjacent_narrative=False, figure_y=250):
        first = "Our controlled study measures visual evidence with exact source attribution."
        last = "The resulting method improves these measurements across every reviewed setting."
        with fitz.open() as pdf:
            page = pdf.new_page(width=612, height=792)
            page.insert_text((108, 100), "Abstract", fontsize=11)
            page.insert_text((108, 210), first, fontsize=10)
            page.insert_text((108, 224), last, fontsize=10)
            page.draw_rect(fitz.Rect(155, figure_y, 455, figure_y+150), color=(0, 0, 0))
            if bars:
                for i in range(9):
                    x = 175+i*28
                    page.draw_rect(fitz.Rect(x, figure_y+30+i*2, x+12, figure_y+125),
                                   color=None, fill=(.2, .5, .8))
            for i in range(9):
                page.insert_text((175+i*28, figure_y+27), str(90-i), fontsize=6)
            if prose:
                page.insert_text((108, figure_y+158), "The abstract continues after the apparent figure boundary.", fontsize=9)
            if caption:
                page.insert_text((108, figure_y+168), "Figure 1: Measurements across the reviewed settings.", fontsize=9)
            if adjacent_narrative:
                page.insert_text((108, figure_y+180),
                                 "This adjacent narrative paragraph continues beyond the figure caption.", fontsize=9)
            second = pdf.new_page(width=612, height=792)
            second.insert_text((108, 90), "1 Introduction" if intro else "Notes", fontsize=12)
            raw = pdf.tobytes()
        with fitz.open(stream=raw, filetype="pdf") as pdf:
            native = source_lines(pdf[0])
        geometry = SourceGeometry.from_pdf(raw, native,
            expected_source_sha256=hashlib.sha256(raw).hexdigest())
        by_text = {n["text"]: n for n in native}
        spans = [{"line_id": by_text[t]["id"], "bbox": by_text[t]["bbox"],
                  "start": 0, "end": len(t), "text": t} for t in (first, last)]
        label = by_text["90"]
        result = {"text": first+"\n"+last, "explicit_heading": True, "spans": spans,
                  "closing_boundary": {"kind": "unresolved_section_ownership",
                                       "reason": "smaller_separate_source_region",
                                       "source_spans": [{"line_id": label["id"]}]}}
        return result, native, [612, 792], geometry

    def test_bounded_vector_figure_before_page_two_introduction(self):
        args = self.fixture()
        proof = _source_figure_then_intro_closure(*args)
        self.assertEqual(proof["kind"], "source_vector_figure_page_two_intro_closure")
        self.assertGreaterEqual(len(proof["figure_label_line_ids"]), 8)

    def test_missing_ownership_witnesses_remain_held(self):
        for options in ({"caption": False}, {"intro": False}, {"bars": False},
                        {"prose": True}, {"adjacent_narrative": True}, {"figure_y": 224}):
            with self.subTest(options=options):
                self.assertIsNone(_source_figure_then_intro_closure(*self.fixture(**options)))
        args = self.fixture()
        self.assertIsNone(_source_figure_then_intro_closure(*args[:3], None))

    def test_nonfigure_geometry_keeps_prior_descriptor_shape(self):
        *_, geometry = self.fixture(bars=False)
        self.assertNotIn("vector_figure_regions", geometry.descriptor())


if __name__ == "__main__":
    unittest.main()
