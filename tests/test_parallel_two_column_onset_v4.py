"""A simultaneous source body onset can bound a scholarly-matched inset summary."""
import hashlib
import unittest

try:
    import fitz
except ImportError:
    fitz = None

from trace_gc.pdf_source_parallel_v4 import SourceGeometry, source_lines
from trace_gc.pdf_structure_parallel_v4 import _source_two_column_onset_closure


@unittest.skipUnless(fitz, "optional PyMuPDF required")
class TwoColumnOnsetTests(unittest.TestCase):
    def fixture(self, *, right=True, right_y=181, intervening=False):
        first = "We find an exact scientific result in this bounded source paragraph with a clear conclusion."
        second = "The independent observations establish its complete finding for later review."
        left_first = "A detailed body paragraph starts with many different words."
        left_second = "Its second source line continues the body discussion clearly."
        right_first = "Another body column begins on the same source baseline."
        right_second = "Its next source line continues that independent body lane."
        with fitz.open() as pdf:
            page = pdf.new_page(width=612, height=792)
            page.insert_text((108, 138), first, fontsize=10)
            page.insert_text((108, 152), second, fontsize=10)
            if intervening:
                page.insert_text((108, 168), "The summary continues after its apparent end.", fontsize=9)
            page.insert_text((54, 181), left_first, fontsize=9)
            page.insert_text((54, 193), left_second, fontsize=9)
            page.insert_text((54, 205), "A third body line establishes a full paragraph.", fontsize=9)
            if right:
                page.insert_text((317, right_y), right_first, fontsize=9)
                page.insert_text((317, right_y+12), right_second, fontsize=9)
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
        body_box = [54, by_text[left_first]["bbox"][1],
                    max(by_text[left_first]["bbox"][2], by_text[left_second]["bbox"][2]),
                    by_text["A third body line establishes a full paragraph."]["bbox"][3]]
        result = {"text": first + "\n" + second, "spans": [span(first), span(second)],
            "proposal_basis": "source_paragraph_group_corroborated_by_scholarly_field",
            "closing_boundary": {"kind": "unresolved_section_ownership", "reason": "multiple_body_lanes",
                                 "ref": "#/texts/left", "peer_refs": ["#/texts/right"]}}
        ordered = [{"ref": "#/texts/left", "text": "\n".join((left_first,left_second,
                    "A third body line establishes a full paragraph.")), "boxes": [body_box]}]
        return result, native, ordered, [612, 792], geometry

    def test_two_continuing_source_lanes_close_only_the_inset_summary(self):
        args = self.fixture()
        proof = _source_two_column_onset_closure(*args[:4], args[0]["text"], args[4])
        self.assertEqual(proof["kind"], "source_two_column_body_onset_closure")
        self.assertNotEqual(proof["body_first_left_line_id"], proof["body_first_right_line_id"])

    def test_missing_offset_or_intervening_lanes_remain_held(self):
        for options in ({"right": False}, {"right_y": 190}, {"intervening": True}):
            with self.subTest(options=options):
                args = self.fixture(**options)
                self.assertIsNone(_source_two_column_onset_closure(
                    *args[:4], args[0]["text"], args[4]))
        args = self.fixture()
        self.assertIsNone(_source_two_column_onset_closure(*args[:4], "An unrelated field.", args[4]))
        self.assertIsNone(_source_two_column_onset_closure(*args[:4], args[0]["text"], None))


if __name__ == "__main__":
    unittest.main()
