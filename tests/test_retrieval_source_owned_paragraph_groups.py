"""Source-bound verification of abstract paragraphs interleaved by another PDF column."""
from copy import deepcopy
import hashlib
import unittest

try:
    import fitz
except ImportError:
    fitz = None

from trace_gc.pdf_source_parallel_v4 import SourceGeometry, source_lines
from trace_gc.pdf_structure_parallel_v4 import _compose_section_spans, assess_document, seal
from src.parallel_source_v4.adapters import document, item
from src.parallel_source_v4.retrieval import verify_source_bound_assessment


@unittest.skipUnless(fitz, "optional PyMuPDF required for two-column source replay")
class SourceOwnedParagraphGroupTests(unittest.TestCase):
    def fixture(self):
        left = [
            "The abstract opens with a complete scientific claim about the left lane.",
            "A second paragraph measures a stable response across repeated trials.",
            "The final paragraph reports the result and closes the abstract.",
        ]
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.insert_text((40, 70), "Abstract", fontsize=12)
            page.insert_text((40, 95), left[0], fontsize=8)
            page.insert_text((330, 92), "1 Introduction", fontsize=12)
            page.insert_text((330, 115), "This right lane contains unrelated body prose.", fontsize=8)
            page.insert_text((40, 120), left[1], fontsize=8)
            page.insert_text((330, 140), "A second right-lane sentence is also unrelated.", fontsize=8)
            page.insert_text((40, 145), left[2], fontsize=8)
            page.insert_text((40, 170), "Keywords", fontsize=12)
            payload = pdf.tobytes()
        with fitz.open(stream=payload, filetype="pdf") as pdf:
            native = source_lines(pdf[0])
        source_hash = hashlib.sha256(payload).hexdigest()
        geometry = SourceGeometry.from_pdf(payload, native, expected_source_sha256=source_hash)
        by_text = {line["text"]: line for line in native}
        doc = document([
            item(0, "Abstract", "section_header", [by_text["Abstract"]["bbox"]]),
            *[item(i + 1, value, "text", [by_text[value]["bbox"]])
              for i, value in enumerate(left)],
            item(4, "Keywords", "section_header", [by_text["Keywords"]["bbox"]]),
            item(5, "1 Introduction", "section_header", [by_text["1 Introduction"]["bbox"]]),
            item(6, "This right lane contains unrelated body prose.", "text",
                 [by_text["This right lane contains unrelated body prose."]["bbox"]]),
        ])
        params = {"page_size": [600, 800], "source_sha256": source_hash,
                  "page_sha256": source_hash, "source_geometry": geometry}
        assessment = assess_document(doc, native_lines=native, **params)
        composed = _compose_section_spans({"alignment_failure": None,
            "refs": assessment["region_refs"],
            "ownership": assessment["region_ownership"],
            "text": assessment["text"]}, native)
        self.assertIsNotNone(composed)
        assessment["spans"] = composed["spans"]
        assessment["text"] = composed["text"]
        assessment["source_alignment"] = {key: value for key, value in composed.items()
                                          if key not in {"text", "spans"}}
        assessment["closing_boundary"] = {"kind": "metadata_or_nonabstract_region",
            "ref": "#/texts/4", "label": "Keywords", "source_spans": [{
                "line_id": by_text["Keywords"]["id"], "start": 0, "end": len("Keywords"),
                "text": "Keywords", "bbox": by_text["Keywords"]["bbox"],
                "box_scope": "native_line_not_character_box", "page_no": 1}]}
        assessment["status"] = "complete"
        assessment["proposal"] = True
        assessment["complete_candidate"] = True
        seal(assessment)
        return assessment, native, params

    def test_source_owned_groups_replay_without_accepting_right_column(self):
        assessment, native, params = self.fixture()
        self.assertEqual(assessment["source_alignment"].get("method"),
                         "source_owned_monotone_paragraph_groups", assessment)
        self.assertEqual(assessment["status"], "complete", assessment)
        verify_source_bound_assessment(assessment, native, **params)

    def test_resealed_group_tampering_fails(self):
        assessment, native, params = self.fixture()
        self.assertEqual(assessment["status"], "complete", assessment)
        attacks = {
            "skip_group": lambda a: a["region_refs"].pop(1),
            "wrong_owner": lambda a: next(x for x in a["region_ownership"]
                                          if x.get("decision") == "included").update(ref="#/texts/99"),
            "wrong_group_box": lambda a: a["source_alignment"]["paragraph_groups"][1]["bbox"].__setitem__(0, 330),
            "wrong_closure": lambda a: a["closing_boundary"].update(source_spans=a["spans"][:1]),
        }
        for name, attack in attacks.items():
            with self.subTest(name=name):
                changed = deepcopy(assessment)
                attack(changed)
                seal(changed)
                with self.assertRaises(ValueError):
                    verify_source_bound_assessment(changed, native, **params)

    def test_same_lane_middle_paragraph_cannot_be_skipped(self):
        assessment, native, params = self.fixture()
        changed = deepcopy(assessment)
        changed["region_refs"].pop(1)
        next(entry for entry in changed["region_ownership"]
             if entry.get("ref") == "#/texts/2")["decision"] = "excluded"
        first, middle, last = changed["spans"]
        changed["spans"] = [first, last]
        changed["text"] = first["text"] + "\n" + last["text"]
        changed["source_alignment"]["paragraph_groups"].pop(1)
        seal(changed)
        with self.assertRaisesRegex(ValueError, "abstract_paragraph_groups_not_source_owned"):
            verify_source_bound_assessment(changed, native, **params)


if __name__ == "__main__":
    unittest.main()
