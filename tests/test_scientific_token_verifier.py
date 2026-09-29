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
    if packet.get("source_lines"):
        value["source_lines"] = packet["source_lines"]
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
                {"char": "1", "kind": "glyph", "glyph_ids": [1], "glyph_offset": 0},
                {"char": "/", "kind": "fraction_slash", "rule_id": 4},
                {"char": "2", "kind": "glyph", "glyph_ids": [2], "glyph_offset": 0},
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


def join_fixture():
    packet = fixture()
    packet["tex"] = "Alpha Beta"
    packet["source"]["tex_sha256"] = digest(packet["tex"].encode())
    packet["text"] = "A B"
    packet["rules"] = []
    packet["glyphs"] = [
        {"id": 1, "char": "A", "box": [1, 1, 2, 2],
         "line_id": 20, "line_offset": 0, "role": "abstract_body"},
        {"id": 2, "char": "B", "box": [1, 3, 2, 4],
         "line_id": 21, "line_offset": 0, "role": "abstract_body"},
    ]
    packet["source_lines"] = [
        {"id": 20, "role": "abstract_body", "glyph_ids": [1], "box": [1, 1, 2, 2]},
        {"id": 21, "role": "abstract_body", "glyph_ids": [2], "box": [1, 3, 2, 4]},
    ]
    join = {"left_line_id": 20, "right_line_id": 21,
            "left_glyph_id": 1, "right_glyph_id": 2,
            "left_box": [1, 1, 2, 2], "right_box": [1, 3, 2, 4],
            "left_role": "abstract_body", "right_role": "abstract_body",
            "left_line_offset": 0, "right_line_offset": 0}
    packet["tokens"] = [{
        "range": [0, 3], "text": "A B", "tex_anchor": "Alpha Beta",
        "alternate_scopes": [{"decision": "rejected", "reason": "reviewed source lines"}],
        "characters": [
            {"char": "A", "kind": "glyph", "glyph_ids": [1], "glyph_offset": 0},
            {"char": " ", "kind": "line_join_space", **join},
            {"char": "B", "kind": "glyph", "glyph_ids": [2], "glyph_offset": 0},
        ],
        "tree": {"kind": "line_join", **join, "children": {
            "left": {"kind": "literal", "glyph_ids": [1]},
            "right": {"kind": "literal", "glyph_ids": [2]},
        }},
    }]
    return packet


def delta_fixture():
    packet = fixture()
    packet["tex"] = r"$\Delta$"
    packet["source"]["tex_sha256"] = digest(packet["tex"].encode())
    packet["text"] = "Δ"
    packet["glyphs"] = [{"id": 1, "char": "∆", "box": [1, 1, 2, 2],
                         "line_id": 20, "line_offset": 0, "role": "abstract_body"}]
    packet["source_lines"] = [{"id": 20, "role": "abstract_body",
                               "glyph_ids": [1], "box": [1, 1, 2, 2]}]
    packet["rules"] = []
    packet["tokens"] = [{
        "range": [0, 1], "text": "Δ", "tex_anchor": r"\Delta",
        "alternate_scopes": [{"decision": "rejected", "reason": "reviewed PDF shape and TeX"}],
        "characters": [{"char": "Δ", "kind": "reviewed_delta_alias",
                        "glyph_ids": [1], "glyph_offset": 0, "raw_char": "∆",
                        "source_box": [1, 1, 2, 2], "source_line_id": 20,
                        "source_line_offset": 0, "source_role": "abstract_body"}],
        "tree": {"kind": "literal", "glyph_ids": [1]},
    }]
    return packet


class ScientificTokenVerifierTest(unittest.TestCase):
    def test_source_line_join_and_delta_alias_stay_review_required(self):
        for packet in (join_fixture(), delta_fixture()):
            with self.subTest(packet=packet["text"]):
                self.assertEqual(verify(packet).status,
                                 "MECHANICALLY_VERIFIED_REVIEW_REQUIRED")

    def test_line_join_requires_exact_bound_source_and_output(self):
        changes = (
            lambda p: p["source_lines"][1].update(role="excluded_margin"),
            lambda p: p["glyphs"][1].update(line_offset=1),
            lambda p: p["tokens"][0]["characters"][1].update(right_glyph_id=1),
            lambda p: p["tokens"][0]["tree"].update(left_glyph_id=2),
            lambda p: p["tokens"][0]["characters"][1].update(left_box=[0, 0, 1, 1]),
            lambda p: p["tokens"][0]["tree"].update(right_role="excluded_margin"),
            lambda p: p["tokens"][0]["characters"][1].update(char="/"),
            lambda p: p["tokens"][0]["characters"][1].update(left_line_id=[]),
            lambda p: p["tokens"][0]["tree"].update(right_line_id={}),
            lambda p: p["source_lines"][0].update(role=[]),
        )
        for change in changes:
            packet = join_fixture()
            change(packet)
            with self.assertRaises(TokenLineageError):
                verify(packet)

    def test_line_join_rejects_intervening_abstract_line(self):
        packet = join_fixture()
        packet["source_lines"].insert(1, {"id": 20 + 1, "role": "abstract_body",
                                         "glyph_ids": [3], "box": [3, 2, 4, 3]})
        packet["source_lines"][2]["id"] = 22
        packet["glyphs"][1]["line_id"] = 22
        packet["glyphs"].append({"id": 3, "char": "X", "box": [3, 2, 4, 3],
                                  "line_id": 21, "line_offset": 0, "role": "abstract_body"})
        join = packet["tokens"][0]["characters"][1]
        join["right_line_id"] = 22
        packet["tokens"][0]["tree"]["right_line_id"] = 22
        with self.assertRaisesRegex(TokenLineageError, "unowned source line"):
            verify(packet)

    def test_line_join_crosses_explicit_excluded_margin_only(self):
        packet = join_fixture()
        packet["source_lines"].insert(1, {"id": 21, "role": "excluded_margin",
                                         "glyph_ids": [3], "box": [3, 2, 4, 3]})
        packet["source_lines"][2]["id"] = 22
        packet["glyphs"][1]["line_id"] = 22
        packet["glyphs"].append({"id": 3, "char": "X", "box": [3, 2, 4, 3],
                                  "line_id": 21, "line_offset": 0, "role": "excluded_margin"})
        packet["tokens"][0]["characters"][1]["right_line_id"] = 22
        packet["tokens"][0]["tree"]["right_line_id"] = 22
        self.assertEqual(verify(packet).status, "MECHANICALLY_VERIFIED_REVIEW_REQUIRED")
        packet["source_lines"].pop(1)
        packet["glyphs"].pop()
        with self.assertRaisesRegex(TokenLineageError, "omits intervening"):
            verify(packet)

    def test_delta_alias_rejects_unreviewed_normalization(self):
        for change in (
            lambda p: p["glyphs"][0].update(char="δ"),
            lambda p: p["tokens"][0]["characters"][0].update(raw_char="Δ"),
            lambda p: p["tokens"][0]["characters"][0].update(glyph_offset=1),
            lambda p: p["tokens"][0]["characters"][0].update(source_box=[0, 0, 1, 1]),
            lambda p: p["tokens"][0]["characters"][0].update(source_role="excluded_margin"),
            lambda p: p["tokens"][0]["characters"][0].update(kind="glyph"),
            lambda p: p["glyphs"][0].update(line_id=[]),
            lambda p: p["source_lines"][0].update(role={}),
        ):
            packet = delta_fixture()
            change(packet)
            with self.assertRaises(TokenLineageError):
                verify(packet)

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
        token["characters"][1] = {"char": "-", "kind": "glyph", "glyph_ids": [1], "glyph_offset": 0,
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
                      "characters": [{"char": "A", "kind": "glyph", "glyph_ids": [1], "glyph_offset": 0},
                                     {"char": "2", "kind": "glyph", "glyph_ids": [2], "glyph_offset": 0}],
                      "tree": {"kind": "script", "children": {
                          "base": {"kind": "literal", "glyph_ids": [1]},
                          "subscript": {"kind": "literal", "glyph_ids": [2]},
                      }}})
        self.assertEqual(verify(packet).token_count, 1)
        packet["glyphs"][1]["box"] = [1, 0, 2, 1]
        with self.assertRaisesRegex(TokenLineageError, "vertical scope"):
            verify(packet)

    def test_same_glyph_cannot_emit_digit_twice(self):
        packet = fixture()
        packet["text"] = "11/2"
        token = packet["tokens"][0]
        token["range"] = [0, 4]
        token["text"] = "11/2"
        token["characters"].insert(1, {"char": "1", "kind": "glyph",
                                          "glyph_ids": [1], "glyph_offset": 0})
        with self.assertRaisesRegex(TokenLineageError, "exactly once"):
            verify(packet)

    def test_multichar_glyph_cannot_emit_only_first_character(self):
        packet = fixture()
        packet["glyphs"][0]["char"] = "\ufb01"
        packet["text"] = "f/2"
        token = packet["tokens"][0]
        token["text"] = "f/2"
        token["characters"][0]["char"] = "f"
        with self.assertRaisesRegex(TokenLineageError, "exactly once"):
            verify(packet)

    def test_ligature_requires_both_output_characters_in_order(self):
        packet = fixture()
        packet["glyphs"][0]["char"] = "\ufb01"
        packet["text"] = "fi/2"
        token = packet["tokens"][0]
        token["range"] = [0, 4]
        token["text"] = "fi/2"
        token["characters"][0]["char"] = "f"
        token["characters"].insert(1, {"char": "i", "kind": "glyph",
                                          "glyph_ids": [1], "glyph_offset": 1})
        self.assertEqual(verify(packet).token_count, 1)
        token["characters"][0]["glyph_offset"] = 1
        token["characters"][1]["glyph_offset"] = 0
        with self.assertRaises(TokenLineageError):
            verify(packet)

    def test_fraction_rule_cannot_emit_two_slashes(self):
        packet = fixture()
        packet["text"] = "1//2"
        token = packet["tokens"][0]
        token["range"] = [0, 4]
        token["text"] = "1//2"
        token["characters"].insert(2, {"char": "/", "kind": "fraction_slash",
                                          "rule_id": 4})
        with self.assertRaisesRegex(TokenLineageError, "exactly one output slash"):
            verify(packet)

    def test_ligature_cannot_straddle_synthetic_slash(self):
        packet = fixture()
        packet["glyphs"][0]["char"] = "\ufb01"
        packet["text"] = "f/i2"
        token = packet["tokens"][0]
        token["range"] = [0, 4]
        token["text"] = "f/i2"
        token["characters"][0]["char"] = "f"
        token["characters"].insert(2, {"char": "i", "kind": "glyph",
                                          "glyph_ids": [1], "glyph_offset": 1})
        with self.assertRaisesRegex(TokenLineageError, "not contiguous"):
            verify(packet)

    def test_fraction_slash_must_follow_numerator_and_precede_denominator(self):
        for value, order in (("/12", (1, 0, 2)), ("12/", (0, 2, 1))):
            with self.subTest(value=value):
                packet = fixture()
                original = packet["tokens"][0]["characters"]
                packet["text"] = value
                packet["tokens"][0]["text"] = value
                packet["tokens"][0]["characters"] = [original[i] for i in order]
                with self.assertRaisesRegex(TokenLineageError, "typed serialization"):
                    verify(packet)

    def test_fraction_slash_cannot_split_multiglyph_numerator(self):
        packet = fixture()
        packet["text"] = "1/23"
        packet["glyphs"][1]["char"] = "3"
        packet["glyphs"].append({"id": 3, "char": "2", "box": [2, 1, 3, 2]})
        packet["rules"][0]["numerator_ids"] = [1, 3]
        token = packet["tokens"][0]
        token["range"] = [0, 4]
        token["text"] = "1/23"
        token["characters"].insert(2, {"char": "2", "kind": "glyph",
                                          "glyph_ids": [3], "glyph_offset": 0})
        token["characters"][3]["char"] = "3"
        token["tree"]["children"]["numerator"]["glyph_ids"] = [1, 3]
        with self.assertRaisesRegex(TokenLineageError, "typed serialization"):
            verify(packet)


if __name__ == "__main__":
    unittest.main()
