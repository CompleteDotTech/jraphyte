"""A page-two running title, author, and Introduction can close one source abstract."""
import hashlib
import unittest

try:
    import fitz
except ImportError:
    fitz = None

from trace_gc.pdf_source_parallel_v4 import SourceGeometry, source_lines
from trace_gc.pdf_structure_parallel_v4 import _next_page_bibliographic_intro_closure


@unittest.skipUnless(fitz, "optional PyMuPDF required")
class BibliographicIntroductionTests(unittest.TestCase):
    def fixture(self, *, running_title="A verified study of source evidence", intro="1. Introduction",
                footer_y=620, intervening=False):
        title = "A verified study of source evidence"
        author = "Alex R. Researcher"
        first = "We investigate the physical process using original measurements and a carefully bounded analysis."
        second = "The resulting evidence supports a complete conclusion for this research question."
        footer = "Proceedings of the Example Science Workshop, September 2026"
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.insert_text((65, 185), title, fontsize=16)
            page.insert_text((65, 225), author + " a,*", fontsize=11)
            page.insert_text((65, 310), first, fontsize=10)
            page.insert_text((65, 328), second, fontsize=10)
            if intervening:
                page.insert_text((65, 450), "This source paragraph continues after the apparent abstract.", fontsize=10)
            page.insert_text((65, footer_y), footer, fontsize=9)
            page = pdf.new_page(width=600, height=800)
            page.insert_text((65, 60), running_title, fontsize=9)
            page.insert_text((430, 60), author, fontsize=9)
            page.insert_text((65, 105), intro, fontsize=12)
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
        result = {"text": first + "\n" + second, "spans": [span(first), span(second)],
            "proposal_basis": "source_paragraph_group_corroborated_by_scholarly_field",
            "closing_boundary": {"kind": "unresolved_section_ownership", "reason": "large_source_gap",
                                 "ref": "#/texts/footer", "peer_refs": []}}
        ordered = [{"ref": "#/texts/footer", "text": footer, "boxes": [span(footer)["bbox"]]}]
        return result, native, ordered, [600, 800], geometry

    def test_matching_running_title_author_and_introduction_close_candidate(self):
        result, native, ordered, size, geometry = self.fixture()
        proof = _next_page_bibliographic_intro_closure(
            result, native, ordered, size, result["text"], geometry)
        self.assertEqual(proof["kind"], "source_page_two_bibliographic_intro_closure")
        self.assertEqual(proof["opening"]["preceding_bibliography"]["running_title"]["text"],
                         "A verified study of source evidence")
        self.assertEqual(proof["physical_page"], 2)

    def test_mismatch_continuation_and_unverified_source_remain_held(self):
        for options in ({"running_title": "An unrelated study of source evidence"},
                        {"intro": "The abstract continues here."},
                        {"footer_y": 520}, {"intervening": True}):
            with self.subTest(options=options):
                result, native, ordered, size, geometry = self.fixture(**options)
                self.assertIsNone(_next_page_bibliographic_intro_closure(
                    result, native, ordered, size, result["text"], geometry))
        result, native, ordered, size, geometry = self.fixture()
        self.assertIsNone(_next_page_bibliographic_intro_closure(
            result, native, ordered, size, result["text"], None))
        self.assertIsNone(_next_page_bibliographic_intro_closure(
            result, native, ordered, size, "An unrelated scholarly field.", geometry))


if __name__ == "__main__":
    unittest.main()
