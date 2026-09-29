"""Authored two-column keyword boundary fixtures; no private corpus text."""
import hashlib
import unittest

try:
    import fitz
except ImportError:
    fitz = None

from trace_gc.pdf_source_parallel_v4 import SourceGeometry, source_lines
from trace_gc.pdf_structure_parallel_v4 import _source_two_column_keywords_closure


@unittest.skipUnless(fitz, "optional PyMuPDF required")
class TwoColumnKeywordsTests(unittest.TestCase):
    def fixture(self, *, right=True, body=True, pipes=True, continuation=False,
                all_bold=True, right_bold=False):
        abstract = [
            "We establish a complete scientific finding using source observations.",
            "The independent method measures the result under controlled conditions.",
            "Our second experiment confirms the same behavior across many samples.",
            "The collected measurements support a precise and stable conclusion.",
            "We compare several alternatives and retain the strongest evidence.",
            "These observations explain the mechanism without adding body text.",
            "Our analysis excludes unrelated material from the measured result.",
            "The final result follows directly from the complete experiment.",
        ]
        keywords = [
            "scientific method | evidence quality |",
            "reproducible results | controlled experiment",
        ] if pipes else [
            "The scientific discussion continues as ordinary narrative prose.",
            "Further analysis belongs to the same section and is not metadata.",
        ]
        right_lines = [
            "The body begins beside the abstract in a separate column.",
            "Its next paragraph develops the larger methodological context.",
            "Additional body discussion continues in this source lane.",
            "The surrounding section uses a distinct regular text style.",
            "Further observations are described after the section onset.",
            "The same column continues below the abstract opening.",
        ]
        left_lines = [
            "The outer body starts below the separate keyword list.",
            "It continues with source prose in the left column.",
            "The third line confirms this independent body flow.",
        ]
        with fitz.open() as pdf:
            page = pdf.new_page(width=612, height=792)
            for i, value in enumerate(abstract):
                page.insert_text((52, 175 + 11*i), value, fontsize=6.5,
                                 fontname="hebo" if all_bold or i else "helv")
            if right:
                for i, value in enumerate(right_lines):
                    page.insert_text((315, 175 + 12*i), value, fontsize=9,
                                     fontname="hebo" if right_bold else "helv")
            if continuation:
                page.insert_text((52, 268), "Continued.", fontsize=8)
            for i, value in enumerate(keywords):
                page.insert_text((52, 280 + 11*i), value, fontsize=6)
            if body:
                for i, value in enumerate(left_lines):
                    page.insert_text((52, 317 + 12*i), value, fontsize=9)
            raw = pdf.tobytes()
        with fitz.open(stream=raw, filetype="pdf") as pdf:
            native = source_lines(pdf[0])
        geometry = SourceGeometry.from_pdf(raw, native,
            expected_source_sha256=hashlib.sha256(raw).hexdigest())
        by_text = {row["text"]: row for row in native}
        def span(value):
            row = by_text[value]
            return {"line_id": row["id"], "start": 0, "end": len(value),
                    "text": value, "bbox": row["bbox"], "page_no": 1,
                    "box_scope": "native_line_not_character_box"}
        result = {"text": "\n".join(abstract), "spans": [span(v) for v in abstract],
            "proposal_basis": "source_bold_narrative_region",
            "closing_boundary": {"kind": "unresolved_section_ownership",
                "reason": "unlabelled_group_typography_transition", "ref": "#/texts/keywords",
                "source_spans": [span(v) for v in keywords],
                "before_style": {"bold": True}, "after_style": {"bold": False}}}
        return result, native, [612, 792], geometry

    def proof(self, args, scholarly=""):
        return _source_two_column_keywords_closure(*args[:3], scholarly, args[3])

    def test_concurrent_right_body_and_left_keyword_boundary(self):
        args = self.fixture()
        proof = self.proof(args)
        self.assertEqual(proof["kind"], "source_two_column_unlabelled_keywords_closure")
        self.assertGreaterEqual(len(proof["right_body_line_ids"]), 5)
        self.assertEqual(len(proof["left_body_line_ids"]), 3)
        self.assertEqual(proof["keyword_terms"], 4)

    def test_missing_role_or_column_evidence_remains_held(self):
        for options in ({"right": False}, {"body": False}, {"pipes": False},
                        {"continuation": True}, {"all_bold": False},
                        {"right_bold": True}):
            with self.subTest(options=options):
                self.assertIsNone(self.proof(self.fixture(**options)))

    def test_conflicting_field_and_unverified_geometry_remain_held(self):
        args = self.fixture()
        self.assertIsNone(self.proof(args, "An unrelated scholarly abstract."))
        self.assertIsNone(_source_two_column_keywords_closure(*args[:3], "", None))


if __name__ == "__main__":
    unittest.main()
