"""A source-painted full-lane rule can close an abstract before cross-lane body text."""
import hashlib
import unittest

try:
    import fitz
except ImportError:
    fitz = None

from trace_gc.pdf_source_parallel_v4 import SourceGeometry, source_lines
from trace_gc.pdf_structure_parallel_v4 import _source_divider_closes_cross_lane


@unittest.skipUnless(fitz, "optional PyMuPDF required")
class SourceDividerTests(unittest.TestCase):
    def fixture(self, *, rule=(50, 590, 395), heading="1 Introduction"):
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.insert_text((180, 260), "The source-located abstract establishes the complete result.", fontsize=10)
            page.insert_text((180, 280), "Its final sentence closes above the body divider.", fontsize=10)
            page.insert_text((50, 420), heading, fontsize=12)
            page.insert_text((330, 420), "deployed in manufacturing contexts and later body prose", fontsize=10)
            if rule:
                page.draw_line((rule[0], rule[2]), (rule[1], rule[2]), width=.4)
            raw = pdf.tobytes()
        with fitz.open(stream=raw, filetype="pdf") as pdf:
            native = source_lines(pdf[0])
        geometry = SourceGeometry.from_pdf(raw, native,
            expected_source_sha256=hashlib.sha256(raw).hexdigest())
        by_text = {row["text"]: row for row in native}
        def span(text):
            row = by_text[text]
            return {"line_id": row["id"], "start": 0, "end": len(text),
                    "text": text, "bbox": row["bbox"]}
        abstract = [span("The source-located abstract establishes the complete result."),
                    span("Its final sentence closes above the body divider.")]
        proof = {"kind": "body_section", "label": heading, "source_location": "located",
                 "source_spans": [span(heading)]}
        body = [span("deployed in manufacturing contexts and later body prose")]
        return abstract, proof, body, geometry

    def test_full_visible_rule_separates_abstract_from_both_body_lanes(self):
        abstract, heading, body, geometry = self.fixture()
        proof = _source_divider_closes_cross_lane(abstract, heading, body, geometry)
        self.assertEqual(proof["version"], "source-full-lane-abstract-body-divider-v1")
        self.assertGreater(proof["rule"]["y"], abstract[-1]["bbox"][3])
        self.assertLess(proof["rule"]["y"], min(heading["source_spans"][0]["bbox"][1], body[0]["bbox"][1]))
        self.assertEqual(proof["rule"]["visibility_check"], "no_later_overlapping_paint_v1")

    def test_missing_short_or_misplaced_rule_cannot_close(self):
        for rule in (None, (50, 300, 395), (50, 590, 275), (50, 590, 418)):
            with self.subTest(rule=rule):
                self.assertIsNone(_source_divider_closes_cross_lane(*self.fixture(rule=rule)))

    def test_heading_and_verified_geometry_are_required(self):
        abstract, heading, body, geometry = self.fixture()
        self.assertIsNone(_source_divider_closes_cross_lane(abstract, heading, body, None))
        self.assertIsNone(_source_divider_closes_cross_lane(abstract, heading, body, geometry.descriptor()))
        heading["label"] = "Results"
        self.assertIsNone(_source_divider_closes_cross_lane(abstract, heading, body, geometry))


if __name__ == "__main__":
    unittest.main()
