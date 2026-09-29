"""Authored PDF geometry cases for a separate filled synopsis inset."""
import hashlib
import unittest

try:
    import fitz
except ImportError:
    fitz = None

from trace_gc.pdf_source_parallel_v4 import SourceGeometry, source_lines
from trace_gc.pdf_structure_parallel_v4 import _source_shaded_synopsis_closure


@unittest.skipUnless(fitz, "optional PyMuPDF required")
class ShadedSynopsisClosureTests(unittest.TestCase):
    def fixture(self, *, fill=True, heading=True, extra=False, extra_short=False,
                overlay=False,
                color=(.98, .92, .94)):
        abstract = [
            "The first experiment establishes a reproducible scientific result with clear evidence.",
            "A second paragraph confirms the finding using independent methods and observations.",
        ]
        inset = [
            "This separate synopsis describes the broad motivation for a study.",
            "Its distinct presentation concerns practical background and context.",
            "It is not part of the preceding source abstract paragraph group.",
        ]
        body = "The numbered outer section begins a longer source body discussion."
        with fitz.open() as pdf:
            page = pdf.new_page(width=612, height=792)
            if fill:
                page.draw_rect(fitz.Rect(65, 210, 548, 310), color=None, fill=color)
            if overlay:
                page.draw_rect(fitz.Rect(65, 210, 548, 310), color=None, fill=(1, 1, 1))
            for y, value in zip((180, 194), abstract):
                page.insert_text((75, y), value, fontsize=10, fontname="hebo")
            for y, value in zip((230, 248, 266), inset):
                page.insert_text((75, y), value, fontsize=10)
            if extra:
                page.insert_text((75, 290), "Another unowned source sentence appears inside the filled box.", fontsize=10)
            if extra_short:
                page.insert_text((75, 316), "Continued.", fontsize=10)
            if heading:
                page.insert_text((75, 337), "1 Introduction", fontsize=12, fontname="hebo")
            page.insert_text((75, 369), body, fontsize=10)
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
            "closing_boundary": {"kind": "unresolved_section_ownership",
                "reason": "unlabelled_group_typography_transition", "ref": "#/texts/inset",
                "source_spans": [span(v) for v in inset]}}
        ordered = []
        if heading:
            value = "1 Introduction"
            ordered.append({"ref": "#/texts/heading", "text": value,
                            "bbox": by_text[value]["bbox"], "boxes": [by_text[value]["bbox"]],
                            "tree_order": 1})
        ordered.append({"ref": "#/texts/body", "text": body,
                        "bbox": by_text[body]["bbox"], "boxes": [by_text[body]["bbox"]],
                        "tree_order": 2, "label": "text"})
        return result, native, ordered, [612, 792], geometry

    def proof(self, args, scholarly=None):
        return _source_shaded_synopsis_closure(*args[:4],
            args[0]["text"] if scholarly is None else scholarly, args[4])

    def test_source_fill_inset_and_outer_heading_bound_abstract(self):
        args = self.fixture()
        proof = self.proof(args)
        self.assertEqual(proof["kind"], "source_shaded_synopsis_outer_heading_closure")
        self.assertEqual(proof["synopsis_ref"], "#/texts/inset")
        self.assertEqual(len(proof["synopsis_source_spans"]), 3)
        self.assertEqual(len(args[4].descriptor()["shaded_regions"]), 1)

    def test_missing_fill_heading_or_unowned_inset_text_remains_held(self):
        for options in ({"fill": False}, {"heading": False}, {"extra": True},
                        {"extra_short": True},
                        {"overlay": True}, {"color": (1, 1, 1)}):
            with self.subTest(options=options):
                self.assertIsNone(self.proof(self.fixture(**options)))

    def test_field_match_and_verified_pdf_context_are_required(self):
        args = self.fixture()
        self.assertIsNone(self.proof(args, scholarly="An unrelated abstract field."))
        self.assertIsNone(_source_shaded_synopsis_closure(*args[:4], args[0]["text"], None))


if __name__ == "__main__":
    unittest.main()
