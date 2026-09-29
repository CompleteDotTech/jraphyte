"""Source-owned title-page closure witnesses; authored PDFs only."""
import hashlib
import unittest

try:
    import fitz
except ImportError:
    fitz = None

from trace_gc.pdf_source_parallel_v4 import SourceGeometry, source_lines
from trace_gc.pdf_structure_parallel_v4 import _next_page_title_closure


@unittest.skipUnless(fitz, "optional PyMuPDF required")
class NextPageTitleClosureTests(unittest.TestCase):
    def fixture(self, *, opening="1 Introduction", trailing=False):
        first = "We observe a complete and carefully bounded abstract with source evidence."
        second = "The methods and results are recorded with enough detail to support review."
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.insert_text((65, 270), "Abstract", fontsize=12)
            page.insert_text((65, 310), first, fontsize=10)
            page.insert_text((65, 326), second, fontsize=10)
            if trailing:
                page.insert_text((65, 510), "Further abstract details continue below.", fontsize=10)
            page = pdf.new_page(width=600, height=800)
            page.insert_text((65, 105), opening, fontsize=12)
            raw = pdf.tobytes()
        with fitz.open(stream=raw, filetype="pdf") as pdf:
            native = source_lines(pdf[0])
        geometry = SourceGeometry.from_pdf(raw, native,
            expected_source_sha256=hashlib.sha256(raw).hexdigest())
        spans = [{"line_id": row["id"], "start": 0, "end": len(row["text"]),
                  "text": row["text"], "bbox": row["bbox"]}
                 for row in native if row["text"] in {first, second}]
        return "\n".join((first, second)), spans, native, [600, 800], geometry

    def test_verified_next_page_introduction_closes_only_first_page_text(self):
        text, spans, native, size, geometry = self.fixture()
        proof = _next_page_title_closure(text, spans, native, size, text, geometry, explicit=True)
        self.assertEqual(proof["opening"]["kind"], "body_section")
        self.assertEqual(proof["physical_page"], 2)
        self.assertEqual(proof["source"], "verified_original_pdf")

    def test_contents_opening_is_separate_from_first_page_abstract(self):
        text, spans, native, size, geometry = self.fixture(opening="Contents")
        proof = _next_page_title_closure(text, spans, native, size, "", geometry, explicit=True)
        self.assertEqual(proof["opening"]["kind"], "contents")
        self.assertFalse(proof["scholarly_text_98_corroborated"])

    def test_continuation_or_page_one_prose_remains_held(self):
        args = self.fixture(opening="The abstract continues on this page.")
        self.assertIsNone(_next_page_title_closure(*args[:4], args[0], args[4], explicit=True))
        args = self.fixture(trailing=True)
        self.assertIsNone(_next_page_title_closure(*args[:4], args[0], args[4], explicit=True))
        args = self.fixture()
        self.assertIsNone(_next_page_title_closure(*args[:4], args[0], None, explicit=True))


if __name__ == "__main__":
    unittest.main()
