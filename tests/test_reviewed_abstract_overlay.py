"""Authored evidence only; no private PDFs or frozen paper identifiers."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch
from pathlib import Path

from trace_gc.pdf_source_parallel_v4 import digest_value
from trace_gc.pdf_source_parallel_v4 import source_lines
from trace_gc.pdf_notation_parallel_v4 import capture_notation
from trace_gc.pdf_structure_parallel_v4 import assess_document
from trace_gc.reviewed_abstract_overlay import apply_reviewed_abstract, _source_page_stamp, _split_section_number, _typed_expression, _unaccounted_visual_paint, verify_first_page_identity
from trace_gc.trust import IssuerPolicy, Signer, TrustStore


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ReviewedAbstractOverlayTests(unittest.TestCase):
    def test_raster_sentence_in_abstract_band_is_held(self):
        import fitz
        from PIL import Image, ImageDraw
        import io

        visual = Image.new("RGB", (250, 25), "white")
        ImageDraw.Draw(visual).text((2, 2), "Omitted abstract sentence.", fill="black")
        image_bytes = io.BytesIO()
        visual.save(image_bytes, format="PNG")
        doc = fitz.open()
        page = doc.new_page(width=200, height=100)
        page.insert_text((10, 10), "Abstract", fontsize=8)
        page.insert_text((10, 20), "First sentence.", fontsize=8)
        page.insert_image(fitz.Rect(10, 21, 110, 28), stream=image_bytes.getvalue())
        page.insert_text((10, 35), "Last sentence.", fontsize=8)
        page.insert_text((10, 45), "Keywords: example", fontsize=8)
        pdf = doc.tobytes()
        self.assertTrue(_unaccounted_visual_paint(pdf, 4, 40))
        self.assertFalse(_unaccounted_visual_paint(pdf, 45, 60))

    def test_vector_paint_in_abstract_band_is_held(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=200, height=100)
        page.insert_text((10, 10), "Abstract", fontsize=8)
        page.insert_text((10, 20), "First sentence.", fontsize=8)
        page.draw_rect(fitz.Rect(10, 24, 110, 28), color=(0, 0, 0), fill=(0, 0, 0))
        page.insert_text((10, 35), "Last sentence.", fontsize=8)
        page.insert_text((10, 45), "Keywords: example", fontsize=8)
        self.assertTrue(_unaccounted_visual_paint(doc.tobytes(), 4, 40))

    def test_only_whole_reviewed_fraction_rule_may_pass_paint_gate(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=100, height=100)
        page.insert_text((20, 20), "A", fontsize=8)
        page.draw_line((18, 25), (30, 25), color=(0, 0, 0), width=.5)
        page.insert_text((20, 35), "B", fontsize=8)
        pdf = doc.tobytes()
        native = source_lines(fitz.open(stream=pdf, filetype="pdf")[0])
        notation, _ = capture_notation(pdf, native)
        self.assertEqual(len(notation["rules"]), 1)
        chars = {c["raw"]: c["id"] for c in notation["characters"]}
        witness = {"rule_id": notation["rules"][0]["id"],
                   "numerator_glyph_ids": [chars["A"]], "denominator_glyph_ids": [chars["B"]]}
        self.assertFalse(_unaccounted_visual_paint(pdf, 10, 40, notation,
                                                    set(chars.values()), [witness]))
        page.draw_rect(fitz.Rect(40, 24, 60, 27), color=(0, 0, 0))
        changed = doc.tobytes()
        self.assertTrue(_unaccounted_visual_paint(changed, 10, 40, notation,
                                                  set(chars.values()), [witness]))

    def test_composite_stroke_cannot_hide_extra_vector_content(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=100, height=100)
        page.insert_text((20, 20), "A", fontsize=8)
        page.insert_text((20, 35), "B", fontsize=8)
        shape = page.new_shape()
        shape.draw_line((18, 25), (30, 25))
        shape.draw_line((40, 26), (60, 26))
        shape.finish(color=(0, 0, 0), width=.5)
        shape.commit()
        pdf = doc.tobytes()
        native = source_lines(fitz.open(stream=pdf, filetype="pdf")[0])
        notation, _ = capture_notation(pdf, native)
        chars = {c["raw"]: c["id"] for c in notation["characters"]}
        rule = notation["rules"][0]
        witness = {"rule_id": rule["id"], "numerator_glyph_ids": [chars["A"]],
                   "denominator_glyph_ids": [chars["B"]]}
        self.assertTrue(_unaccounted_visual_paint(pdf, 10, 40, notation,
                                                  set(chars.values()), [witness]))

    def test_annotation_appearance_in_abstract_band_is_held(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=100, height=100)
        page.insert_text((10, 20), "A result.", fontsize=8)
        page.add_freetext_annot(fitz.Rect(10, 24, 80, 35), "Extra claim")
        self.assertTrue(_unaccounted_visual_paint(doc.tobytes(), 10, 40))

    def test_white_dashed_rule_cannot_be_reviewed_as_fraction(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=100, height=100)
        page.insert_text((20, 20), "A", fontsize=8)
        page.insert_text((20, 35), "B", fontsize=8)
        page.draw_line((18, 25), (30, 25), color=(1, 1, 1), width=.5,
                       dashes="[ 1 2 ] 0")
        pdf = doc.tobytes()
        native = source_lines(fitz.open(stream=pdf, filetype="pdf")[0])
        notation, _ = capture_notation(pdf, native)
        chars = {c["raw"]: c["id"] for c in notation["characters"]}
        witness = {"rule_id": notation["rules"][0]["id"],
                   "numerator_glyph_ids": [chars["A"]], "denominator_glyph_ids": [chars["B"]]}
        self.assertTrue(_unaccounted_visual_paint(pdf, 10, 40, notation,
                                                  set(chars.values()), [witness]))

    def test_long_divider_cannot_be_reviewed_as_two_glyph_fraction(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=200, height=100)
        page.insert_text((20, 20), "A", fontsize=8)
        page.insert_text((20, 35), "B", fontsize=8)
        page.draw_line((20, 25), (175, 25), color=(0, 0, 0), width=.5)
        pdf = doc.tobytes()
        native = source_lines(fitz.open(stream=pdf, filetype="pdf")[0])
        notation, _ = capture_notation(pdf, native)
        chars = {c["raw"]: c["id"] for c in notation["characters"]}
        witness = {"rule_id": notation["rules"][0]["id"],
                   "numerator_glyph_ids": [chars["A"]], "denominator_glyph_ids": [chars["B"]]}
        self.assertTrue(_unaccounted_visual_paint(pdf, 10, 40, notation,
                                                  set(chars.values()), [witness]))

    def test_rule_crossing_glyph_boxes_is_not_fraction_witness(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=100, height=100)
        page.insert_text((20, 20), "A", fontsize=8)
        page.insert_text((20, 28), "B", fontsize=8)
        page.draw_line((18, 20), (30, 20), color=(0, 0, 0), width=.5)
        pdf = doc.tobytes()
        native = source_lines(fitz.open(stream=pdf, filetype="pdf")[0])
        notation, _ = capture_notation(pdf, native)
        chars = {c["raw"]: c["id"] for c in notation["characters"]}
        witness = {"rule_id": notation["rules"][0]["id"],
                   "numerator_glyph_ids": [chars["A"]], "denominator_glyph_ids": [chars["B"]]}
        self.assertTrue(_unaccounted_visual_paint(pdf, 10, 40, notation,
                                                  set(chars.values()), [witness]))

    def test_small_font_box_overlap_requires_exact_source_crop(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=100, height=100)
        page.insert_text((20, 20), "A", fontsize=8)
        page.insert_text((20, 35), "B", fontsize=8)
        page.draw_line((18, 22.5), (30, 22.5), color=(0, 0, 0), width=.5)
        pdf = doc.tobytes()
        native = source_lines(fitz.open(stream=pdf, filetype="pdf")[0])
        notation, _ = capture_notation(pdf, native)
        chars = {c["raw"]: c["id"] for c in notation["characters"]}
        rule = notation["rules"][0]
        witness = {"rule_id": rule["id"], "numerator_glyph_ids": [chars["A"]],
                   "denominator_glyph_ids": [chars["B"]]}
        self.assertTrue(_unaccounted_visual_paint(pdf, 10, 40, notation,
                                                  set(chars.values()), [witness]))
        clip = fitz.Rect(rule["x0"]-8, rule["y"]-16, rule["x1"]+8, rule["y"]+16)
        witness["overlap_crop_sha256"] = sha(
            fitz.open(stream=pdf, filetype="pdf")[0].get_pixmap(
                matrix=fitz.Matrix(8, 8), clip=clip, alpha=False).tobytes("png"))
        self.assertTrue(_unaccounted_visual_paint(pdf, 10, 40, notation,
                                                  set(chars.values()), [witness]))
        witness["visual_review"] = {"decision": "no_visible_ink_collision",
                                     "scope": "original_pdf_eight_x_rule_crop"}
        self.assertFalse(_unaccounted_visual_paint(pdf, 10, 40, notation,
                                                    set(chars.values()), [witness]))
        witness["overlap_crop_sha256"] = "0"*64
        self.assertTrue(_unaccounted_visual_paint(pdf, 10, 40, notation,
                                                  set(chars.values()), [witness]))

    def test_page_stamp_must_contain_only_stamp_text(self):
        line = {"id": 2, "text": "arXiv:2604.12345v1", "bbox": [2, 20, 9, 90]}
        notation = {"characters": [{"native_ref": {"line_id": 2}, "direction": [0.0, -1.0]}]}
        self.assertTrue(_source_page_stamp(line, notation, [200, 100]))
        line["text"] = "arXiv:2604.12345v1  [cond-mat.str-el]  17 Apr 2026"
        self.assertTrue(_source_page_stamp(line, notation, [200, 100]))
        line["text"] = "arXiv:2604.12345v1 [Important omitted abstract result.] 17 Apr 2026"
        self.assertFalse(_source_page_stamp(line, notation, [200, 100]))
        line["text"] = "arXiv:2604.12345v1  [cond-mat.str-el]  17 Apr 2026"
        line["text"] += " New abstract sentence."
        self.assertFalse(_source_page_stamp(line, notation, [200, 100]))
        line["text"] = "arXiv:2604.12345v1 Important result."
        self.assertFalse(_source_page_stamp(line, notation, [200, 100]))

    def test_split_section_number_requires_adjacent_same_baseline_title(self):
        number = {"id": 29, "text": "1", "bbox": [91.8, 437.83, 98.97, 452.18]}
        title = {"id": 30, "text": "Introduction", "bbox": [113.32, 437.83, 191.22, 452.18]}
        self.assertTrue(_split_section_number(number, title))
        number["text"] = "1 New result."
        self.assertFalse(_split_section_number(number, title))
        number["text"] = "1"
        title["bbox"] = [150, 437.83, 191.22, 452.18]
        self.assertFalse(_split_section_number(number, title))

    def setUp(self):
        self.source, self.page, self.image = b"authored source PDF", b"authored page PDF", b"authored page image"
        self.tex = b"\\begin{abstract}A result.\\end{abstract}"
        self.converter = {"docling": b"authored converter receipt"}
        self.code = {"selector": Path("trace_gc/pdf_structure_parallel_v4.py").read_bytes()}
        self.native = [
            {"id": 0, "page_no": 1, "bbox": [1, 1, 90, 10], "text": "Abstract: A resu1t."},
            {"id": 1, "page_no": 1, "bbox": [1, 11, 90, 20], "text": "Keywords: example"},
        ]
        self.notation = json.dumps({"status": "diagnostic_only", "rawdict_projection": "exact",
                                   "source": {"original_pdf_sha256": sha(self.source),
                                   "render": {"png_sha256": sha(self.image)}},
                                   "fonts": [{"name": "TEST+CMR10", "embedded_sha256": sha(b"font")}],
                                   "characters": [{"id": 0, "raw": "1", "font": "CMR10", "bbox": [16, 1, 17, 10],
                                                   "native_ref": {"line_id": 0, "start": 16, "end": 17}}]},
                                   sort_keys=True).encode()
        self.auto = assess_document({}, page_size=[100, 100], source_sha256=sha(self.source),
                                    page_sha256=sha(self.page), native_lines=self.native,
                                    conversion_status="error")
        self.manifest = {
            "version": "source-bound-reviewed-abstract-v1", "physical_page": 1, "decision": "HOLD",
            "identity": {"source_sha256": sha(self.source), "page_sha256": sha(self.page),
                         "image_sha256": sha(self.image), "native_sha256": digest_value(self.native),
                         "automatic_assessment_sha256": self.auto["assessment_sha256"],
                         "tex_sha256": sha(self.tex),
                         "notation_sha256": sha(self.notation),
                         "converter_sha256": {"docling": sha(self.converter["docling"])},
                         "code_sha256": {"selector": sha(self.code["selector"]),
                                         "reviewed_abstract_overlay.py": sha(Path("trace_gc/reviewed_abstract_overlay.py").read_bytes())}},
            "native_spans": [{"line_id": 0, "page_no": 1, "start": 0, "end": 19,
                              "text": "Abstract: A resu1t.", "bbox": [1, 1, 90, 10], "source_order": 0}],
            "closing_boundary": {"kind": "keywords", "line_id": 1, "page_no": 1,
                                 "bbox": [1, 11, 90, 20], "start": 0, "end": 9, "text": "Keywords:"},
            "corrections": [{"span_index": 0, "start": 16, "end": 17, "before": "1", "after": "l",
                             "kind": "glyph", "evidence": {"tex_anchor": "result",
                             "expression_tree": {"kind": "word", "glyph_ids": [0]},
                             "glyphs": [{"character_id": 0, "line_id": 0, "bbox": [16, 1, 17, 10],
                                         "font_sha256": sha(b"font")}]} }],
            "diplomatic_abstract": "Abstract: A result.", "normalized_abstract": "Abstract: A result.",
            "used_glyph_ids": [0], "excluded_glyphs": [],
            "line_roles": [
                {"source_order": 0, "line_id": 0, "bbox": [1, 1, 90, 10],
                 "text_sha256": sha(b"Abstract: A resu1t."), "role": "abstract",
                 "reason": "explicit heading and paragraph", "glyph_ids": [0]},
                {"source_order": 1, "line_id": 1, "bbox": [1, 11, 90, 20],
                 "text_sha256": sha(b"Keywords: example"), "role": "keywords",
                 "reason": "source keyword heading", "glyph_ids": []}],
            "max_input_chars": 4000,
        }
        self._seal()
        self.trust = TrustStore()
        self.signers = [Signer.ephemeral("reviewer-a"), Signer.ephemeral("reviewer-b")]
        for signer in self.signers:
            self.trust.enroll(signer.issuer, IssuerPolicy(signer.public_key(), signer.issuer,
                              frozenset({"OBSERVATION"}), frozenset(), frozenset(), frozenset(),
                              can_review=True))
        self._sign()

    def _seal(self):
        self.manifest["manifest_sha256"] = digest_value({k: v for k, v in self.manifest.items() if k != "manifest_sha256"})

    def _sign(self):
        self.reviews = [signer.issue("OBSERVATION", {
            "review_kind": "source-bound-reviewed-abstract-v1",
            "manifest_sha256": self.manifest["manifest_sha256"], "decision": self.manifest["decision"],
            "reviewer": signer.issuer, "reviewer_kind": "assistant",
            "reviewed_at": f"2026-09-29T12:0{index}:00Z"},
            issued_at=f"2026-09-29T12:0{index}:00Z", expires_at="2026-09-30T12:00:00Z")
            for index, signer in enumerate(self.signers)]

    def run_review(self, **overrides):
        values = {"automatic": self.auto, "manifest": self.manifest, "first_review": self.reviews[0],
                  "second_review": self.reviews[1], "trust": self.trust, "source_pdf": self.source,
                  "page_pdf": self.page, "page_image": self.image, "native_lines": self.native,
                  "converter_assets": self.converter, "code_assets": self.code, "tex_source": self.tex,
                  "notation_evidence": self.notation,
                  "at": "2026-09-29T12:30:00Z"}
        values.update(overrides)
        with patch("trace_gc.reviewed_abstract_overlay.capture_notation",
                   return_value=(json.loads(self.notation), self.image)), patch(
                   "trace_gc.reviewed_abstract_overlay.verify_first_page_identity"):
            return apply_reviewed_abstract(**values)

    def test_reject_hash_bound_wrong_page_pdf(self):
        import fitz
        source = fitz.open()
        source.new_page(width=100, height=100).insert_text((1, 20), "Original page")
        wrong = fitz.open()
        wrong.new_page(width=100, height=100).insert_text((1, 20), "Different page")
        with self.assertRaisesRegex(ValueError, "review_page_pdf_not_first_page"):
            verify_first_page_identity(source.tobytes(), wrong.tobytes())

    def test_accepted_is_disabled_even_with_signed_evidence(self):
        before = copy.deepcopy(self.auto)
        self.manifest["decision"] = "accepted"
        self._seal(); self._sign()
        with self.assertRaisesRegex(ValueError, "review_acceptance_requires_complete_pdf_proof"):
            self.run_review()
        self.assertEqual(self.auto, before)

    def test_hold_never_proposes(self):
        self.manifest["decision"] = "HOLD"
        self._seal(); self._sign()
        result = self.run_review()
        self.assertFalse(result["proposal"])
        self.assertEqual(result["status"], "uncertain")
        lineage = result["transcript_lineage"]
        self.assertEqual([row["kind"] for row in lineage], ["native", "correction", "native"])
        self.assertEqual([row["output_start"] for row in lineage], [0, 16, 17])
        self.assertEqual([row["output_end"] for row in lineage], [16, 17, 19])
        self.assertEqual((lineage[1]["native_start"], lineage[1]["native_end"]), (16, 17))
        self.assertEqual(lineage[1]["correction_sha256"], digest_value(self.manifest["corrections"][0]))

    def test_reject_asset_drift_and_unsigned_mutation(self):
        with self.assertRaises(ValueError):
            self.run_review(page_pdf=b"different")
        self.manifest["normalized_abstract"] = "forged"
        with self.assertRaises(ValueError):
            self.run_review()

    def test_reject_code_converter_and_notation_drift(self):
        for override in ({"code_assets": {"selector": b"changed"}},
                         {"converter_assets": {"docling": b"changed"}},
                         {"notation_evidence": b"{}"}):
            with self.subTest(override=next(iter(override))):
                with self.assertRaises(ValueError):
                    self.run_review(**override)

    def test_reject_resealed_but_nonreplaying_sidecar(self):
        self.manifest["decision"] = "HOLD"
        self._seal(); self._sign()
        forged = json.loads(self.notation)
        forged["characters"][0]["bbox"] = [15, 1, 17, 10]
        forged_bytes = json.dumps(forged, sort_keys=True).encode()
        self.manifest["identity"]["notation_sha256"] = sha(forged_bytes)
        self._seal(); self._sign()
        values = {"notation_evidence": forged_bytes}
        with patch("trace_gc.reviewed_abstract_overlay.capture_notation",
                   return_value=(json.loads(self.notation), self.image)):
            with self.assertRaisesRegex(ValueError, "notation_pdf_replay_mismatch"):
                self.run_review(**values)

    def test_reject_incomplete_glyph_accounting(self):
        self.manifest["used_glyph_ids"] = []
        self._seal(); self._sign()
        with self.assertRaisesRegex(ValueError, "review_glyph_partition_incomplete"):
            self.run_review()

    def test_reject_nonspace_disguised_as_whitespace(self):
        self.manifest["used_glyph_ids"] = []
        self.manifest["excluded_glyphs"] = [{"character_id": 0, "role": "whitespace"}]
        self._seal(); self._sign()
        with self.assertRaisesRegex(ValueError, "review_nonwhitespace_excluded_as_whitespace"):
            self.run_review()

    def test_reject_omitted_native_line_inventory(self):
        self.native.insert(1, {"id": 2, "page_no": 1, "bbox": [1, 10, 90, 11],
                               "text": "omitted paragraph"})
        self.manifest["identity"]["native_sha256"] = digest_value(self.native)
        self._seal(); self._sign()
        with self.assertRaisesRegex(ValueError, "review_line_inventory_incomplete"):
            self.run_review()

    def test_reject_interleaved_body_or_fake_margin(self):
        import fitz
        for role in ("body", "page_stamp"):
            with self.subTest(role=role):
                doc = fitz.open()
                page = doc.new_page(width=150, height=100)
                for y, text in ((10, "Abstract: A result."), (20, "body intrusion"),
                                (30, "Continues."), (40, "Keywords: example")):
                    page.insert_text((1, y), text, fontsize=8)
                pdf = doc.tobytes()
                native = source_lines(fitz.open(stream=pdf, filetype="pdf")[0])
                notation, image = capture_notation(pdf, native)
                sidecar = json.dumps(notation, sort_keys=True).encode()
                auto = assess_document({}, page_size=[150, 100], source_sha256=sha(pdf),
                                       page_sha256=sha(pdf), native_lines=native, conversion_status="error")
                selected = [{"line_id": i, "page_no": 1, "start": 0, "end": len(native[i]["text"]),
                             "text": native[i]["text"], "bbox": native[i]["bbox"], "source_order": order}
                            for order, i in enumerate((0, 2))]
                used = [c["id"] for c in notation["characters"] if c["native_ref"]["line_id"] in (0, 2)]
                self.manifest.update(decision="HOLD", native_spans=selected, corrections=[],
                                     diplomatic_abstract="Abstract: A result. Continues.",
                                     normalized_abstract="Abstract: A result. Continues.",
                                     used_glyph_ids=used,
                                     excluded_glyphs=[{"character_id": c["id"],
                                                       "role": role if c["native_ref"]["line_id"] == 1 else "keywords"}
                                                      for c in notation["characters"]
                                                      if c["native_ref"]["line_id"] in (1, 3)],
                                     closing_boundary={"kind": "keywords", "line_id": 3, "page_no": 1,
                                                       "bbox": native[3]["bbox"], "start": 0, "end": 9,
                                                       "text": "Keywords:"})
                roles = ["abstract", role, "abstract", "keywords"]
                self.manifest["line_roles"] = [
                    {"source_order": i, "line_id": i, "bbox": line["bbox"],
                     "text_sha256": sha(line["text"].encode()), "role": roles[i],
                     "reason": "authored source role", "glyph_ids": [c["id"] for c in notation["characters"]
                                                                  if c["native_ref"]["line_id"] == i]}
                    for i, line in enumerate(native)]
                self.manifest["identity"].update(source_sha256=sha(pdf), page_sha256=sha(pdf),
                                                 image_sha256=sha(image), native_sha256=digest_value(native),
                                                 notation_sha256=sha(sidecar),
                                                 automatic_assessment_sha256=auto["assessment_sha256"])
                self._seal(); self._sign()
                with self.assertRaisesRegex(ValueError, "review_interleaved_nonabstract_line"):
                    apply_reviewed_abstract(automatic=auto, manifest=self.manifest,
                        first_review=self.reviews[0], second_review=self.reviews[1], trust=self.trust,
                        source_pdf=pdf, page_pdf=pdf, page_image=image, native_lines=native,
                        converter_assets=self.converter, code_assets=self.code, tex_source=self.tex,
                        notation_evidence=sidecar, at="2026-09-29T12:30:00Z")

    def test_reject_duplicate_glyph_inventory(self):
        self.manifest["used_glyph_ids"] = [0, 0]
        self._seal(); self._sign()
        with self.assertRaisesRegex(ValueError, "review_glyph_partition_incomplete"):
            self.run_review()

    def test_typed_expression_shapes_and_adversarial_scope(self):
        notation = {"characters": [
            {"bbox": [1, 1, 2, 2], "raw": "1"},
            {"bbox": [1, 3, 2, 4], "raw": "2"},
            {"bbox": [3, 3, 4, 4], "raw": "x"},
            {"bbox": [4, 1, 5, 2], "raw": "^"},
            {"bbox": [5, 3, 6, 4], "raw": "7"},
            {"bbox": [5, 3, 6, 4], "raw": "→"},
            {"bbox": [6, 3, 7, 4], "raw": "\x00"},
            {"bbox": [7, 3, 8, 4], "raw": "f"},
            {"bbox": [8, 3, 9, 4], "raw": "i"}],
            "rules": [{"id": 0, "y": 2.5}],
            "relations": [{"kind": "script", "base": 2, "script": 1,
                           "role": "subscript_candidate"}]}
        for node, ids in [
            ({"kind": "fraction", "numerator": [0], "denominator": [1], "rule_id": 0}, [0, 1]),
            ({"kind": "script", "base": 2, "sub": [1], "sup": []}, [2, 1]),
            ({"kind": "accent", "base": 2, "mark": 3}, [2, 3]),
            ({"kind": "ligature", "glyph_ids": [7, 8], "unicode": "fi"}, [7, 8]),
            ({"kind": "control", "glyph_ids": [6], "unicode": "("}, [6]),
            ({"kind": "mapsto", "glyph_ids": [4, 5], "unicode": "↦"}, [4, 5]),
        ]:
            with self.subTest(node=node):
                _typed_expression(node, ids, notation)
        bad = [
            ({"kind": "fraction", "numerator": [1], "denominator": [0], "rule_id": 0}, [0, 1]),
            ({"kind": "fraction", "numerator": [0], "denominator": [1], "rule_id": 99}, [0, 1]),
            ({"kind": "script", "base": 2, "sub": [], "sup": [1]}, [2, 1]),
            ({"kind": "accent", "base": 3, "mark": 2}, [2, 3]),
            ({"kind": "ligature", "glyph_ids": [7], "unicode": "fi"}, [7]),
            ({"kind": "control", "glyph_ids": [7], "unicode": "("}, [7]),
            ({"kind": "mapsto", "glyph_ids": [4, 5], "unicode": "→"}, [4, 5]),
            ({"kind": "word", "glyph_ids": [7]}, [7, 8]),
        ]
        for node, ids in bad:
            with self.subTest(rejected=node):
                with self.assertRaises(ValueError):
                    _typed_expression(node, ids, notation)

    def test_reject_wrong_authority_and_changed_automatic(self):
        other = Signer.ephemeral("unauthorized")
        self.trust.enroll(other.issuer, IssuerPolicy(other.public_key(), other.issuer,
                          frozenset({"OBSERVATION"}), frozenset(), frozenset(), frozenset(),
                          can_review=False))
        bad_review = other.issue("OBSERVATION", {"review_kind": "source-bound-reviewed-abstract-v1",
            "manifest_sha256": self.manifest["manifest_sha256"], "decision": "HOLD",
            "reviewer": other.issuer, "reviewer_kind": "assistant", "reviewed_at": "2026-09-29T12:00:00Z"},
            issued_at="2026-09-29T12:00:00Z", expires_at="2026-09-30T12:00:00Z")
        with self.assertRaises(ValueError):
            self.run_review(second_review=bad_review)
        changed = copy.deepcopy(self.auto)
        changed["text"] = "modified"
        with self.assertRaises(ValueError):
            self.run_review(automatic=changed)

    def test_reject_same_reviewer_and_wrong_boundary(self):
        with self.assertRaises(ValueError):
            self.run_review(second_review=self.reviews[0])
        with self.assertRaisesRegex(ValueError, "distinct_second_review_required"):
            self.run_review(first_review=self.reviews[1], second_review=self.reviews[0])
        fractional_first = self.signers[0].issue("OBSERVATION", {
            "review_kind": "source-bound-reviewed-abstract-v1",
            "manifest_sha256": self.manifest["manifest_sha256"], "decision": "HOLD",
            "reviewer": self.signers[0].issuer, "reviewer_kind": "assistant",
            "reviewed_at": "2026-09-29T12:01:00.1Z"},
            issued_at="2026-09-29T12:01:00.1Z", expires_at="2026-09-30T12:00:00Z")
        with self.assertRaisesRegex(ValueError, "distinct_second_review_required"):
            self.run_review(first_review=fractional_first, second_review=self.reviews[1])
        self.manifest["closing_boundary"]["line_id"] = 0
        self._seal(); self._sign()
        with self.assertRaises(ValueError):
            self.run_review()

    def test_reject_unbacked_or_overlapping_correction(self):
        self.manifest["corrections"][0]["evidence"]["tex_anchor"] = "absent"
        self._seal(); self._sign()
        with self.assertRaises(ValueError):
            self.run_review()
        self.manifest["corrections"][0]["evidence"]["tex_anchor"] = "result"
        self.manifest["corrections"].append(copy.deepcopy(self.manifest["corrections"][0]))
        self._seal(); self._sign()
        with self.assertRaises(ValueError):
            self.run_review()

    def test_reject_wrong_glyph_and_missing_transcription(self):
        self.manifest["corrections"][0]["evidence"]["glyphs"][0]["font_sha256"] = sha(b"wrong")
        self._seal(); self._sign()
        with self.assertRaises(ValueError):
            self.run_review()
        self.manifest["corrections"][0]["evidence"]["glyphs"][0]["font_sha256"] = sha(b"font")
        self.manifest["diplomatic_abstract"] = "A result."
        self._seal(); self._sign()
        with self.assertRaises(ValueError):
            self.run_review()

    def test_real_pdf_notation_replay_holds_without_admission(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=100, height=100)
        page.insert_text((1, 10), "Abstract: A result.", fontsize=8)
        page.insert_text((1, 20), "Keywords: example", fontsize=8)
        pdf = doc.tobytes()
        native = source_lines(fitz.open(stream=pdf, filetype="pdf")[0])
        notation, image = capture_notation(pdf, native)
        sidecar = json.dumps(notation, sort_keys=True).encode()
        automatic = assess_document({}, page_size=[100, 100], source_sha256=sha(pdf),
                                    page_sha256=sha(pdf), native_lines=native, conversion_status="error")
        span = {"line_id": 0, "page_no": 1, "start": 0, "end": len(native[0]["text"]),
                "text": native[0]["text"], "bbox": native[0]["bbox"], "source_order": 0}
        self.manifest.update(decision="HOLD", native_spans=[span], corrections=[],
                             diplomatic_abstract=span["text"], normalized_abstract=span["text"],
                             used_glyph_ids=[c["id"] for c in notation["characters"]
                                             if c["native_ref"]["line_id"] == 0],
                             excluded_glyphs=[{"character_id": c["id"], "role": "keywords"}
                                              for c in notation["characters"] if c["native_ref"]["line_id"] == 1],
                             closing_boundary={"kind": "keywords", "line_id": 1, "page_no": 1,
                                               "bbox": native[1]["bbox"], "start": 0, "end": 9,
                                               "text": "Keywords:"})
        self.manifest["line_roles"] = [
            {"source_order": i, "line_id": i, "bbox": line["bbox"],
             "text_sha256": sha(line["text"].encode()), "role": "abstract" if i == 0 else "keywords",
             "reason": "visible section heading", "glyph_ids": [c["id"] for c in notation["characters"]
                                                        if c["native_ref"]["line_id"] == i]}
            for i, line in enumerate(native)]
        self.manifest["identity"].update(source_sha256=sha(pdf), page_sha256=sha(pdf), image_sha256=sha(image),
                                         native_sha256=digest_value(native), notation_sha256=sha(sidecar),
                                         automatic_assessment_sha256=automatic["assessment_sha256"])
        self._seal(); self._sign()
        result = apply_reviewed_abstract(automatic=automatic, manifest=self.manifest,
                  first_review=self.reviews[0], second_review=self.reviews[1], trust=self.trust,
                  source_pdf=pdf, page_pdf=pdf, page_image=image, native_lines=native,
                  converter_assets=self.converter, code_assets=self.code, tex_source=self.tex,
                  notation_evidence=sidecar, at="2026-09-29T12:30:00Z")
        self.assertFalse(result["proposal"])
        self.assertFalse(result["eligible_for_jev"])

    def test_same_line_heading_is_excluded_by_source_offsets(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=150, height=100)
        page.insert_text((1, 10), "Abstract: A result.", fontsize=8)
        page.insert_text((1, 20), "Keywords: example", fontsize=8)
        pdf = doc.tobytes()
        native = source_lines(fitz.open(stream=pdf, filetype="pdf")[0])
        notation, image = capture_notation(pdf, native)
        sidecar = json.dumps(notation, sort_keys=True).encode()
        automatic = assess_document({}, page_size=[150, 100], source_sha256=sha(pdf),
                                    page_sha256=sha(pdf), native_lines=native, conversion_status="error")
        first = native[0]
        heading_end = len("Abstract: ")
        body = first["text"][heading_end:]
        self.manifest.update(decision="reviewed_legacy_proposal", corrections=[],
            native_spans=[{"line_id": 0, "page_no": 1, "start": heading_end,
                           "end": len(first["text"]), "text": body,
                           "bbox": first["bbox"], "source_order": 0}],
            diplomatic_abstract=body, normalized_abstract=body,
            used_glyph_ids=[c["id"] for c in notation["characters"]
                            if c["native_ref"]["line_id"] == 0 and
                               c["native_ref"]["start"] >= heading_end],
            excluded_glyphs=[{"character_id": c["id"],
                              "role": ("heading" if c["native_ref"]["line_id"] == 0
                                       and c["native_ref"]["end"] <= heading_end else
                                       "keywords" if c["native_ref"]["line_id"] == 1 else "whitespace")}
                             for c in notation["characters"]
                             if c["native_ref"]["line_id"] == 1 or
                                c["native_ref"]["end"] <= heading_end],
            closing_boundary={"kind": "keywords", "line_id": 1, "page_no": 1,
                              "bbox": native[1]["bbox"], "start": 0,
                              "end": len("Keywords:"), "text": "Keywords:"})
        self.manifest["line_roles"] = [
            {"source_order": i, "line_id": i, "bbox": line["bbox"],
             "text_sha256": sha(line["text"].encode()),
             "role": "abstract" if i == 0 else "keywords",
             "reason": "visible section heading and keyword closure",
             "glyph_ids": [c["id"] for c in notation["characters"]
                           if c["native_ref"]["line_id"] == i]}
            for i, line in enumerate(native)]
        self.manifest["identity"].update(source_sha256=sha(pdf), page_sha256=sha(pdf),
            image_sha256=sha(image), native_sha256=digest_value(native),
            notation_sha256=sha(sidecar),
            automatic_assessment_sha256=automatic["assessment_sha256"])
        self._seal(); self._sign()
        result = apply_reviewed_abstract(automatic=automatic, manifest=self.manifest,
            first_review=self.reviews[0], second_review=self.reviews[1], trust=self.trust,
            source_pdf=pdf, page_pdf=pdf, page_image=image, native_lines=native,
            converter_assets=self.converter, code_assets=self.code, tex_source=self.tex,
            notation_evidence=sidecar, at="2026-09-29T12:30:00Z")
        self.assertEqual(result["text"], "A result.")
        self.assertTrue(result["proposal"])
        self.assertEqual(result["notation_fidelity"], "HOLD")
        self.assertFalse(result["eligible_for_jev"])
        self.assertFalse(result["field_candidate"])
        self.assertFalse(result["graph_admission_enabled"])
        self.assertFalse(result["scientific_notation_qualified"])
        self.assertEqual(result["transcript_lineage"][0]["native_start"], heading_end)
        frozen = copy.deepcopy(self.manifest)

        def checked_failure(reason):
            self._seal(); self._sign()
            with self.assertRaisesRegex(ValueError, reason):
                apply_reviewed_abstract(automatic=automatic, manifest=self.manifest,
                    first_review=self.reviews[0], second_review=self.reviews[1], trust=self.trust,
                    source_pdf=pdf, page_pdf=pdf, page_image=image, native_lines=native,
                    converter_assets=self.converter, code_assets=self.code, tex_source=self.tex,
                    notation_evidence=sidecar, at="2026-09-29T12:30:00Z")

        self.manifest = copy.deepcopy(frozen)
        self.manifest["closing_boundary"].update(start=10, end=17, text="example")
        checked_failure("review_legacy_closing_marker_not_source_bound")

        self.manifest = copy.deepcopy(frozen)
        self.manifest["native_spans"][0]["end"] -= 2
        self.manifest["native_spans"][0]["text"] = body[:-2]
        checked_failure("review_legacy_native_line_truncated")

        self.manifest = copy.deepcopy(frozen)
        self.manifest["corrections"] = [copy.deepcopy(self.manifest["corrections"][0])] if self.manifest["corrections"] else [
            {"span_index": 0, "start": 0, "end": 1, "before": "A", "after": "X", "kind": "glyph"}]
        checked_failure("review_legacy_corrections_forbidden")

    def test_separate_heading_requires_all_content_lines(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=150, height=100)
        for y, value in ((10, "Abstract"), (20, "A result."),
                         (30, "Further sentence."), (40, "Keywords: example")):
            page.insert_text((1, y), value, fontsize=8)
        pdf = doc.tobytes()
        native = source_lines(fitz.open(stream=pdf, filetype="pdf")[0])
        notation, image = capture_notation(pdf, native)
        sidecar = json.dumps(notation, sort_keys=True).encode()
        automatic = assess_document({}, page_size=[150, 100], source_sha256=sha(pdf),
                                    page_sha256=sha(pdf), native_lines=native, conversion_status="error")
        selected = [{"line_id": i, "page_no": 1, "start": 0,
                     "end": len(native[i]["text"]), "text": native[i]["text"],
                     "bbox": native[i]["bbox"], "source_order": order}
                    for order, i in enumerate((1, 2))]
        self.manifest.update(decision="reviewed_legacy_proposal", corrections=[],
            native_spans=selected, diplomatic_abstract="A result. Further sentence.",
            normalized_abstract="A result. Further sentence.",
            used_glyph_ids=[c["id"] for c in notation["characters"]
                            if c["native_ref"]["line_id"] in (1, 2)],
            excluded_glyphs=[{"character_id": c["id"],
                              "role": "heading" if c["native_ref"]["line_id"] == 0 else "keywords"}
                             for c in notation["characters"]
                             if c["native_ref"]["line_id"] in (0, 3)],
            closing_boundary={"kind": "keywords", "line_id": 3, "page_no": 1,
                              "bbox": native[3]["bbox"], "start": 0,
                              "end": len("Keywords:"), "text": "Keywords:"})
        roles = ["heading", "abstract", "abstract", "keywords"]
        self.manifest["line_roles"] = [
            {"source_order": i, "line_id": i, "bbox": line["bbox"],
             "text_sha256": sha(line["text"].encode()), "role": roles[i],
             "reason": "visible source section role",
             "glyph_ids": [c["id"] for c in notation["characters"]
                           if c["native_ref"]["line_id"] == i]}
            for i, line in enumerate(native)]
        self.manifest["identity"].update(source_sha256=sha(pdf), page_sha256=sha(pdf),
            image_sha256=sha(image), native_sha256=digest_value(native),
            notation_sha256=sha(sidecar),
            automatic_assessment_sha256=automatic["assessment_sha256"])

        def run():
            self._seal(); self._sign()
            return apply_reviewed_abstract(automatic=automatic, manifest=self.manifest,
                first_review=self.reviews[0], second_review=self.reviews[1], trust=self.trust,
                source_pdf=pdf, page_pdf=pdf, page_image=image, native_lines=native,
                converter_assets=self.converter, code_assets=self.code, tex_source=self.tex,
                notation_evidence=sidecar, at="2026-09-29T12:30:00Z")

        result = run()
        self.assertTrue(result["proposal"])
        self.assertEqual(result["coverage_scope"], "native_text_only")
        self.assertFalse(result["visual_coverage_qualified"])
        self.assertEqual(result["text"], "A result. Further sentence.")
        self.manifest["native_spans"] = selected[:1]
        self.manifest["diplomatic_abstract"] = "A result."
        self.manifest["normalized_abstract"] = "A result."
        with self.assertRaisesRegex(ValueError, "review_line_role_conflicts_with_selected_spans"):
            run()

    def test_horizontal_side_sentence_cannot_be_called_page_stamp(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=200, height=100)
        for x, y, value in ((100, 10, "Abstract"), (100, 20, "First sentence."),
                            (5, 25, "Omitted abstract fact."),
                            (100, 30, "Last sentence."),
                            (100, 40, "Keywords: example")):
            page.insert_text((x, y), value, fontsize=8)
        pdf = doc.tobytes()
        native = source_lines(fitz.open(stream=pdf, filetype="pdf")[0])
        notation, image = capture_notation(pdf, native)
        sidecar = json.dumps(notation, sort_keys=True).encode()
        automatic = assess_document({}, page_size=[200, 100], source_sha256=sha(pdf),
                                    page_sha256=sha(pdf), native_lines=native, conversion_status="error")
        selected = [{"line_id": i, "page_no": 1, "start": 0,
                     "end": len(native[i]["text"]), "text": native[i]["text"],
                     "bbox": native[i]["bbox"], "source_order": order}
                    for order, i in enumerate((1, 3))]
        roles = ["heading", "abstract", "page_stamp", "abstract", "keywords"]
        self.manifest.update(decision="reviewed_legacy_proposal", corrections=[],
            native_spans=selected, diplomatic_abstract="First sentence. Last sentence.",
            normalized_abstract="First sentence. Last sentence.",
            used_glyph_ids=[c["id"] for c in notation["characters"]
                            if c["native_ref"]["line_id"] in (1, 3)],
            excluded_glyphs=[{"character_id": c["id"], "role": roles[c["native_ref"]["line_id"]]}
                             for c in notation["characters"]
                             if c["native_ref"]["line_id"] in (0, 2, 4)],
            closing_boundary={"kind": "keywords", "line_id": 4, "page_no": 1,
                              "bbox": native[4]["bbox"], "start": 0,
                              "end": len("Keywords:"), "text": "Keywords:"})
        self.manifest["line_roles"] = [
            {"source_order": i, "line_id": i, "bbox": line["bbox"],
             "text_sha256": sha(line["text"].encode()), "role": roles[i],
             "reason": "authored adversarial source role",
             "glyph_ids": [c["id"] for c in notation["characters"]
                           if c["native_ref"]["line_id"] == i]}
            for i, line in enumerate(native)]
        self.manifest["identity"].update(source_sha256=sha(pdf), page_sha256=sha(pdf),
            image_sha256=sha(image), native_sha256=digest_value(native),
            notation_sha256=sha(sidecar),
            automatic_assessment_sha256=automatic["assessment_sha256"])
        self._seal(); self._sign()
        with self.assertRaisesRegex(ValueError, "review_interleaved_nonabstract_line"):
            apply_reviewed_abstract(automatic=automatic, manifest=self.manifest,
                first_review=self.reviews[0], second_review=self.reviews[1], trust=self.trust,
                source_pdf=pdf, page_pdf=pdf, page_image=image, native_lines=native,
                converter_assets=self.converter, code_assets=self.code, tex_source=self.tex,
                notation_evidence=sidecar, at="2026-09-29T12:30:00Z")


if __name__ == "__main__":
    unittest.main()
