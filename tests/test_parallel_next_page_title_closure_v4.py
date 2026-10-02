"""Source-owned title-page closure witnesses; authored PDFs only."""
import hashlib
import unittest

try:
    import fitz
except ImportError:
    fitz = None

from trace_gc.pdf_source_parallel_v4 import SourceGeometry, source_lines
from trace_gc.pdf_structure_parallel_v4 import _frontmatter_contents_closure, _next_page_title_closure


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

    def test_unlabelled_frontmatter_needs_matching_running_title_and_contents(self):
        title = "A complete study of transport across scientific networks"
        first = "We investigate transport across scientific networks using exact source measurements and reproducible evidence."
        second = "The results show a consistent effect and establish a complete first-page account for later review."

        def case(*, header=title, contents="Contents"):
            with fitz.open() as pdf:
                page = pdf.new_page(width=600, height=800)
                page.insert_text((65, 70), title, fontsize=16)
                page.insert_text((95, 105), "Alice Smith and Bob Jones", fontsize=11)
                page.insert_text((65, 130), "University of Example, Department of Physics", fontsize=9)
                page.insert_text((65, 200), first, fontsize=9)
                page.insert_text((65, 222), second, fontsize=9)
                page.insert_text((65, 255), "Correspondence: editor@example.org", fontsize=9)
                page = pdf.new_page(width=600, height=800)
                width = fitz.get_text_length(header, fontsize=9)
                page.insert_text(((600-width)/2, 60), header, fontsize=9)
                page.insert_text((65, 95), contents, fontsize=12)
                raw = pdf.tobytes()
            with fitz.open(stream=raw, filetype="pdf") as pdf:
                native = source_lines(pdf[0])
            geometry = SourceGeometry.from_pdf(raw, native,
                expected_source_sha256=hashlib.sha256(raw).hexdigest())
            by_text = {row["text"]: row for row in native}
            def span(value):
                row = by_text[value]
                return {"line_id": row["id"], "start": 0, "end": len(value),
                        "text": value, "bbox": row["bbox"]}
            result = {"text": first + "\n" + second, "spans": [span(first), span(second)],
                "candidate_scope": {"kind": "unlabelled_frontmatter_candidate_requires_source_review",
                    "title_source_spans": [span(title)],
                    "author_source_spans": [span("Alice Smith and Bob Jones")],
                    "affiliation_source_spans": [span("University of Example, Department of Physics")]},
                "closing_boundary": {"kind": "metadata_or_nonabstract_region",
                    "label": "Correspondence: editor@example.org", "source_location": "located",
                    "source_spans": [span("Correspondence: editor@example.org")]}}
            return result, geometry

        result, geometry = case()
        proof = _frontmatter_contents_closure(result, [600, 800], geometry)
        self.assertEqual(proof["kind"], "source_frontmatter_contents_closure")
        self.assertEqual(proof["opening"]["preceding_header"]["text"], title)
        self.assertIsNone(_frontmatter_contents_closure(result, [600, 800], None))
        mismatch, other_geometry = case(header="An unrelated running title")
        self.assertIsNone(_frontmatter_contents_closure(mismatch, [600, 800], other_geometry))
        result, geometry = case(contents="The abstract continues here.")
        self.assertIsNone(_frontmatter_contents_closure(result, [600, 800], geometry))
        result, geometry = case()
        result["closing_boundary"]["label"] = "Funding: Example Foundation"
        self.assertIsNone(_frontmatter_contents_closure(result, [600, 800], geometry))


if __name__ == "__main__":
    unittest.main()
