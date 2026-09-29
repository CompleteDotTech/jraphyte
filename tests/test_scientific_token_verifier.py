"""Authored evidence fixtures; these do not establish PDF or corpus quality."""

import hashlib
import json
import unittest

from trace_gc.scientific_token_verifier import (
    TokenLineageError, verify_scientific_token_packet,
)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def evidence_digest(packet):
    value = {"glyphs": packet["glyphs"], "rules": packet["rules"]}
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode()
    return digest(raw)


def fixture():
    pdf_hash = digest(b"authored pdf")
    notation_hash = digest(b"authored notation")
    tex = r"spin $\frac{1}{2}$"
    packet = {
        "source": {"pdf_sha256": pdf_hash, "notation_sha256": notation_hash,
                   "tex_sha256": digest(tex.encode())},
        "tex": tex, "text": "1/2",
        "glyphs": [
            {"id": 1, "char": "1", "box": [1, 1, 2, 2]},
            {"id": 2, "char": "2", "box": [1, 4, 2, 5]},
        ],
        "rules": [{"id": 4, "box": [0, 2.5, 3, 2.6],
                   "numerator_ids": [1], "denominator_ids": [2]}],
        "tokens": [{
            "range": [0, 3], "text": "1/2", "tex_anchor": r"\frac{1}{2}",
            "alternate_scopes": [{"decision": "rejected",
                                  "reason": "image and TeX show a stacked fraction"}],
            "characters": [
                {"char": "1", "kind": "glyph", "glyph_ids": [1]},
                {"char": "/", "kind": "fraction_slash", "rule_id": 4},
                {"char": "2", "kind": "glyph", "glyph_ids": [2]},
            ],
            "tree": {"kind": "fraction", "rule_id": 4, "children": {
                "numerator": {"kind": "literal", "glyph_ids": [1]},
                "denominator": {"kind": "literal", "glyph_ids": [2]},
            }},
        }],
    }
    return packet


def verify(packet, *, trusted_evidence=None):
    source = packet["source"]
    return verify_scientific_token_packet(
        packet, source_sha256=source["pdf_sha256"],
        notation_sha256=source["notation_sha256"],
        tex_sha256=source["tex_sha256"],
        evidence_sha256=trusted_evidence or evidence_digest(packet))


class ScientificTokenVerifierTest(unittest.TestCase):
    def test_fraction_with_exact_rule_and_output_lineage_stays_review_required(self):
        result = verify(fixture())
        self.assertEqual(result.status, "MECHANICALLY_VERIFIED_REVIEW_REQUIRED")
        self.assertEqual(result.token_count, 1)

    def test_missing_or_wrong_synthetic_slash_rule_rejected(self):
        for change in (None, 5):
            with self.subTest(change=change):
                packet = fixture()
                packet["tokens"][0]["characters"][1]["rule_id"] = change
                with self.assertRaises(TokenLineageError):
                    verify(packet)

    def test_alternate_scope_requires_explicit_rejection(self):
        packet = fixture()
        packet["tokens"][0]["alternate_scopes"] = []
        with self.assertRaisesRegex(TokenLineageError, "alternate scope"):
            verify(packet)

    def test_distant_earlier_glyph_cannot_be_fraction_numerator(self):
        packet = fixture()
        packet["glyphs"].append({"id": 3, "char": "1", "box": [20, 1, 21, 2]})
        packet["rules"][0]["numerator_ids"] = [3]
        with self.assertRaisesRegex(TokenLineageError, "horizontal scope"):
            verify(packet)

    def test_tampered_source_evidence_rejected_with_original_digest(self):
        packet = fixture()
        trusted = evidence_digest(packet)
        packet["glyphs"][0]["char"] = "9"
        with self.assertRaisesRegex(TokenLineageError, "evidence mismatch"):
            verify(packet, trusted_evidence=trusted)

    def test_unaccounted_output_character_rejected(self):
        packet = fixture()
        packet["tokens"][0]["characters"].pop()
        with self.assertRaisesRegex(TokenLineageError, "lineage incomplete"):
            verify(packet)

    def test_same_printed_glyphs_cannot_swap_fraction_roles(self):
        packet = fixture()
        packet["text"] = "1/1"
        packet["tokens"][0]["text"] = "1/1"
        packet["glyphs"][1]["char"] = "1"
        packet["tokens"][0]["characters"][2]["char"] = "1"
        packet["tokens"][0]["characters"][0]["glyph_ids"] = [2]
        packet["tokens"][0]["characters"][2]["glyph_ids"] = [1]
        with self.assertRaisesRegex(TokenLineageError, "order mismatch"):
            verify(packet)

    def test_unbound_scientific_output_span_rejected(self):
        packet = fixture()
        packet["text"] = "1/2x"
        with self.assertRaisesRegex(TokenLineageError, "fully tokenized"):
            verify(packet)

    def test_unbound_normalization_rejected(self):
        packet = fixture()
        packet["text"] = "1-2"
        token = packet["tokens"][0]
        token["text"] = "1-2"
        token["characters"][1] = {"char": "-", "kind": "glyph", "glyph_ids": [1],
                                   "normalization": "reviewed"}
        with self.assertRaises(TokenLineageError):
            verify(packet)

    def test_script_needs_vertical_scope(self):
        packet = fixture()
        packet["text"] = "A2"
        packet["tex"] = r"A_{2}"
        packet["source"]["tex_sha256"] = digest(packet["tex"].encode())
        packet["glyphs"][0]["char"] = "A"
        packet["rules"] = []
        token = packet["tokens"][0]
        token.update({"range": [0, 2], "text": "A2", "tex_anchor": "A_{2}",
                      "characters": [{"char": "A", "kind": "glyph", "glyph_ids": [1]},
                                     {"char": "2", "kind": "glyph", "glyph_ids": [2]}],
                      "tree": {"kind": "script", "children": {
                          "base": {"kind": "literal", "glyph_ids": [1]},
                          "subscript": {"kind": "literal", "glyph_ids": [2]},
                      }}})
        self.assertEqual(verify(packet).token_count, 1)
        packet["glyphs"][1]["box"] = [1, 0, 2, 1]
        with self.assertRaisesRegex(TokenLineageError, "vertical scope"):
            verify(packet)


if __name__ == "__main__":
    unittest.main()
