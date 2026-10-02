"""Authored two-column wrap witnesses; no private papers or converter caches."""
import hashlib
import unittest

try:
    import fitz
except ImportError:
    fitz = None

from trace_gc.pdf_source_parallel_v4 import SourceGeometry, source_lines
from trace_gc.pdf_structure_parallel_v4 import _body_column_wrap_after_heading


@unittest.skipUnless(fitz, "optional PyMuPDF required for source geometry")
class BodyColumnWrapTests(unittest.TestCase):
    def fixture(self, *, left="Learning from Hu-", right="man Feedback describes the result."):
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.insert_text((50, 410), "Abstract We observe robust behavior in several trials.", fontsize=11)
            page.insert_text((50, 450), "1 Introduction", fontsize=11)
            page.insert_text((50, 740), left, fontsize=11)
            page.insert_text((320, 190), right, fontsize=11)
            page.insert_text((320, 435), "In this paper, we investigate the result.", fontsize=11)
            raw = pdf.tobytes()
        with fitz.open(stream=raw, filetype="pdf") as pdf:
            native = source_lines(pdf[0])
        geometry = SourceGeometry.from_pdf(raw, native,
            expected_source_sha256=hashlib.sha256(raw).hexdigest())
        def spans(text):
            line = next(row for row in native if row["text"] == text)
            return [{"line_id": line["id"], "start": 0, "end": len(text),
                     "text": text, "bbox": line["bbox"]}]
        abstract = spans("Abstract We observe robust behavior in several trials.")
        heading = {"kind": "body_section", "source_spans": spans("1 Introduction")}
        witness = {"spans": spans("In this paper, we investigate the result.")}
        return witness, heading, abstract, native, [600, 800], geometry

    def test_source_body_wrap_excludes_right_column_only_with_exact_bridge(self):
        witness, heading, abstract, native, size, geometry = self.fixture()
        proof = _body_column_wrap_after_heading(witness, heading, abstract, native, size, geometry)
        self.assertIsNotNone(proof)
        self.assertEqual(proof["version"], "source-body-column-wrap-v1")
        self.assertNotEqual(proof["left_line_id"], proof["right_line_id"])

    def test_missing_wrap_or_unverified_context_retains_hold(self):
        for changes in ({"left": "Learning from Humans."},
                        {"right": "Many Feedback findings follow."}):
            with self.subTest(changes=changes):
                args = self.fixture(**changes)
                self.assertIsNone(_body_column_wrap_after_heading(*args))
        args = self.fixture()
        self.assertIsNone(_body_column_wrap_after_heading(*args[:-1], None))


if __name__ == "__main__":
    unittest.main()
