"""Authored PDF fixtures only; no private paper content or corpus qualification."""
import copy
import hashlib
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

try:
    import fitz
except ImportError:
    fitz = None

from trace_gc.pdf_source_parallel_v4 import (
    SourceGeometry, digest_value, locate, source_lines, validate_source_spans,
)
import trace_gc.pdf_source_parallel_v4 as source_module


@unittest.skipIf(fitz is None, "optional PyMuPDF is required for authored PDF geometry")
class FractionSeamTests(unittest.TestCase):
    def fixture(self, *, rule="normal", lower_y=104, lower_size=6, upper_y=95.8,
                tail_font="tiro", extra=None, rotation=0, numerator="1", denominator="2", overpaint=None):
        with fitz.open() as doc:
            page = doc.new_page(width=600, height=800)
            prefix = "An authored paragraph describes spin-"
            page.insert_text((100, 100), prefix, fontsize=9, fontname="tiro")
            edge = 100 + fitz.get_text_length(prefix, fontname="tiro", fontsize=9)
            page.insert_text((edge+1, upper_y), numerator, fontsize=6, fontname="tiro")
            page.insert_text((edge+1, lower_y), denominator, fontsize=lower_size, fontname="tiro")
            page.insert_text((edge+8, 100), "chain", fontsize=9, fontname=tail_font)
            page.insert_text((100, 110.5), "with stable structure and a final result.",
                             fontsize=9, fontname="tiro")
            if extra == "later_owner":
                page.insert_text((100, 121), "A later source line invalidates a two-line owner.", fontsize=9, fontname="tiro")
            elif extra == "gutter":
                page.insert_text((100, 116), "Left narrow prose.", fontsize=9, fontname="tiro")
                page.insert_text((edge+8, 116), "Right column prose.", fontsize=9, fontname="tiro")
            elif extra == "intervening":
                page.insert_text((180, 105), "Other source", fontsize=5, fontname="tiro")
            elif extra == "duplicate":
                page.insert_text((100, 300), prefix, fontsize=9, fontname="tiro")
                page.insert_text((edge+1, 295.8), numerator, fontsize=6, fontname="tiro")
                page.insert_text((edge+1, 304), denominator, fontsize=6, fontname="tiro")
                page.insert_text((edge+8, 300), "chain", fontsize=9, fontname="tiro")
                page.insert_text((100, 310.5), "with stable structure and a final result.", fontsize=9, fontname="tiro")
                page.draw_line((edge+1, 297.55), (edge+4, 297.55), width=.35)
            if rule != "missing":
                x = edge+1+(10 if rule == "remote" else 0)
                endpoint = (x+3, 100.55 if rule == "diagonal" else 97.55)
                if rule == "rectangle":
                    page.draw_rect(fitz.Rect(x, 97.55, x+3, 98), width=.35)
                elif rule == "multi_segment":
                    shape = page.new_shape()
                    shape.draw_line((x, 97.55), endpoint)
                    shape.draw_line(endpoint, (x+3, 99))
                    shape.finish(width=.35)
                    shape.commit()
                else:
                    layer = doc.add_ocg("authored optional layer", on=True) if rule == "layer" else 0
                    page.draw_line((x, 97.55), endpoint, width=2 if rule == "thick" else .35,
                                   stroke_opacity=.2 if rule == "transparent" else 1,
                                   color=(1, 1, 1) if rule == "white" else (0, 0, 0), oc=layer)
                    if rule == "duplicate":
                        page.draw_line((x, 97.55), endpoint, width=.35)
            if overpaint == "rectangle":
                page.draw_rect(fitz.Rect(edge, 97, edge+5, 98), color=None, fill=(1, 1, 1))
            elif overpaint == "image":
                white = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 2, 2), False)
                white.clear_with(255)
                page.insert_image(fitz.Rect(edge, 97, edge+5, 98), pixmap=white, keep_proportion=False)
            elif overpaint == "text":
                page.insert_text((edge+1, 98), "x", fontsize=4, fontname="tiro", color=(1, 1, 1))
            elif overpaint == "annotation":
                annotation = page.add_rect_annot(fitz.Rect(edge, 97, edge+5, 98))
                annotation.set_colors(fill=(1, 1, 1))
                annotation.update()
            elif overpaint in {"numerator", "denominator"}:
                # Cover the glyph while keeping the thin fraction bar visible.
                top, bottom = (89, 97.3) if overpaint == "numerator" else (98, 107)
                page.draw_rect(fitz.Rect(edge+.9, top, edge+4.1, bottom), color=None, fill=(1, 1, 1))
            elif overpaint == "clip":
                # Authored stream clips the fraction stroke out of view. Text
                # extraction is still available, so a draw-command-only proof
                # would incorrectly accept the hidden line.
                xref = page.get_contents()[-1]
                doc.update_stream(xref, b"q 0 0 10 10 re W n\n" + doc.xref_stream(xref) + b"\nQ")
            page.set_rotation(rotation)
            payload = doc.tobytes()
        with fitz.open(stream=payload, filetype="pdf") as doc:
            native = source_lines(doc[0])
        context = SourceGeometry.from_pdf(payload, native, expected_source_sha256=hashlib.sha256(payload).hexdigest())
        return payload, native, context

    @staticmethod
    def joins(result):
        return [join for row in result.get("logical_geometry", {}).get("rows", []) for join in row["joins"]
                if join["reason"] == "source_vector_fraction_seam"]

    def test_exact_pdf_rule_recovers_only_raw_order(self):
        payload, native, context = self.fixture()
        before = copy.deepcopy(native)
        text = "\n".join(line["text"] for line in native)
        old = locate(text, native)
        self.assertTrue(old["column_change"])
        found = locate(text, native, source_geometry=context)
        self.assertEqual(found["status"], "located")
        self.assertFalse(found["column_change"])
        self.assertTrue(found["logical_geometry"]["notation_review_required"])
        self.assertEqual(found["text"], text)
        self.assertEqual(found["spans"], old["spans"])
        validate_source_spans(found["spans"], native)
        self.assertEqual(native, before)
        proof, = self.joins(found)
        self.assertEqual(proof["source_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(proof["native_sha256"], digest_value(native))
        self.assertEqual(proof["scope"], "raw_reading_order_only")
        for run in proof["native_runs"]:
            line = next(line for line in native if line["id"] == run["line_id"])
            self.assertTrue(line["text"][run["start"]:run["end"]])
            self.assertEqual(len(run["painted_glyphs"]), len(run["text"]) if "text" in run
                             else sum(not c.isspace() for c in line["text"][run["start"]:run["end"]]))
        self.assertEqual(proof["support_visibility"]["scope"], "source_line_endpoints_geometry_only")
        self.assertNotIn("/", found["text"])
        self.assertNotIn("proposal", found)

    def test_rule_missing_remote_invisible_ambiguous_or_not_standalone_holds(self):
        for rule in ("missing", "remote", "transparent", "white", "duplicate", "thick", "diagonal", "rectangle", "multi_segment", "layer"):
            with self.subTest(rule=rule):
                _, native, context = self.fixture(rule=rule)
                result = locate("\n".join(line["text"] for line in native), native, source_geometry=context)
                self.assertFalse(self.joins(result))
                self.assertTrue(result.get("column_change", True))

    def test_native_typography_and_vertical_stack_are_required(self):
        for changes in ({"lower_y": 99}, {"upper_y": 104}, {"lower_size": 9},
                        {"tail_font": "tibo"}, {"numerator": "a"}, {"denominator": "0"},
                        {"numerator": "12"}):
            with self.subTest(changes=changes):
                _, native, context = self.fixture(**changes)
                result = locate("\n".join(line["text"] for line in native), native, source_geometry=context)
                self.assertFalse(self.joins(result))

    def test_later_overpaint_and_clipping_cannot_supply_visible_rule(self):
        for overlay in ("rectangle", "image", "text", "annotation", "clip"):
            with self.subTest(overlay=overlay):
                _, native, context = self.fixture(overpaint=overlay)
                self.assertEqual(context.descriptor()["rules"], [])
                result = locate("\n".join(line["text"] for line in native), native, source_geometry=context)
                self.assertFalse(self.joins(result))
                self.assertTrue(result.get("column_change", True))

    def test_hidden_transparent_or_white_seam_runs_and_support_hold(self):
        real_insert = fitz.Page.insert_text
        targets = ("1", "2", "An authored paragraph describes spin-", "chain",
                   "with stable structure and a final result.")
        for target in targets:
            for override in ({"render_mode": 3}, {"fill_opacity": 0}, {"color": (1, 1, 1)}):
                with self.subTest(target=target, override=override):
                    def insert(page, point, text, **kwargs):
                        return real_insert(page, point, text, **{**kwargs, **(override if text == target else {})})
                    with patch.object(fitz.Page, "insert_text", insert):
                        _, native, context = self.fixture()
                    self.assertTrue(context.descriptor()["rules"])
                    result = locate("\n".join(line["text"] for line in native), native, source_geometry=context)
                    self.assertFalse(self.joins(result))
                    self.assertTrue(result.get("column_change", True))

    def test_glyph_overpaint_holds_even_when_fraction_bar_remains_visible(self):
        for overlay in ("numerator", "denominator"):
            with self.subTest(overlay=overlay):
                _, native, context = self.fixture(overpaint=overlay)
                self.assertTrue(context.descriptor()["rules"])
                result = locate("\n".join(line["text"] for line in native), native, source_geometry=context)
                self.assertFalse(self.joins(result))

    def test_duplicate_hidden_and_painted_numeric_glyph_is_not_a_seam(self):
        real_insert = fitz.Page.insert_text
        def duplicate(page, point, text, **kwargs):
            value = real_insert(page, point, text, **kwargs)
            if text == "1":
                real_insert(page, point, text, **{**kwargs, "render_mode": 3})
            return value
        with patch.object(fitz.Page, "insert_text", duplicate):
            _, native, context = self.fixture()
        result = locate("\n".join(line["text"] for line in native), native, source_geometry=context)
        self.assertFalse(self.joins(result))

    def test_later_owner_intervening_prose_and_gutter_hold(self):
        for extra in ("later_owner", "intervening", "gutter"):
            with self.subTest(extra=extra):
                _, native, context = self.fixture(extra=extra)
                result = locate("\n".join(line["text"] for line in native), native, source_geometry=context)
                self.assertFalse(self.joins(result))

    def test_rotation_cannot_authorize_seam(self):
        for rotation in (90, 180, 270):
            with self.subTest(rotation=rotation):
                _, native, context = self.fixture(rotation=rotation)
                found = locate("\n".join(line["text"] for line in native), native, source_geometry=context)
                self.assertFalse(self.joins(found))

    def test_region_crop_does_not_import_excluded_native_extent(self):
        _, native, context = self.fixture()
        found = locate("\n".join(line["text"] for line in native), native, source_geometry=context,
                       region_boxes=[[239, 89, 280, 115]])
        self.assertEqual(found["status"], "unlocated")
        self.assertEqual(found["spans"], [])

    def test_duplicate_occurrence_remains_ambiguous(self):
        _, native, context = self.fixture(extra="duplicate")
        found = locate("\n".join(line["text"] for line in native[:3]), native, source_geometry=context)
        self.assertEqual(found["status"], "ambiguous")
        self.assertEqual(found["spans"], [])

    def test_source_hash_and_native_tampering_rejected(self):
        payload, native, context = self.fixture()
        with self.assertRaisesRegex(ValueError, "pdf_hash_mismatch"):
            SourceGeometry.from_pdf(payload, native, expected_source_sha256="0"*64)
        for mutate in (lambda n: n[0].update(id=True), lambda n: n[0].update(text=n[0]["text"]+"!"),
                       lambda n: n[1].update(id=n[0]["id"]), lambda n: n[2].update(line_in_block=0)):
            changed = copy.deepcopy(native)
            mutate(changed)
            with self.assertRaisesRegex(ValueError, "native_mismatch"):
                SourceGeometry.from_pdf(payload, changed, expected_source_sha256=hashlib.sha256(payload).hexdigest())
            with self.assertRaisesRegex(ValueError, "native_changed"):
                locate(native[0]["text"], changed, source_geometry=context)

    def test_owned_context_not_serialized_authority(self):
        payload, native, context = self.fixture()
        mutable = bytearray(payload)
        owned = SourceGeometry.from_pdf(mutable, native, expected_source_sha256=hashlib.sha256(payload).hexdigest())
        mutable[:] = b"not the PDF"
        descriptor = owned.descriptor()
        descriptor["rules"].clear()
        self.assertEqual(owned.descriptor(), context.descriptor())
        with self.assertRaises(FrozenInstanceError):
            owned._evidence = b"{}"
        with self.assertRaisesRegex(ValueError, "verified_pdf_factory"):
            SourceGeometry()
        with self.assertRaisesRegex(ValueError, "verified_context_required"):
            locate(native[0]["text"], native, source_geometry=descriptor)

    def test_caller_mutation_after_digest_check_cannot_change_used_source(self):
        _, native, context = self.fixture()
        expected = copy.deepcopy(native)
        text = "\n".join(line["text"] for line in native)
        real_runs = source_module._exact_runs
        changed = False

        def mutate_after_verification(line):
            nonlocal changed
            if not changed:
                changed = True
                # The digest check already succeeded before run inspection.
                # A consistent replacement must not be traversed under that pin.
                native[0]["text"] = native[0]["text"][:-1]+"9"
                native[0]["spans"][-1]["text"] = "9"
            return real_runs(line)

        with patch.object(source_module, "_exact_runs", side_effect=mutate_after_verification):
            found = locate(text, native, source_geometry=context)
        self.assertTrue(changed)
        self.assertEqual(found["text"], text)
        self.assertFalse(found["column_change"])
        validate_source_spans(found["spans"], expected)


if __name__ == "__main__":
    unittest.main()
