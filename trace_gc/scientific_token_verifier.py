"""Fail-closed mechanical checks for reviewed scientific output token lineage.

This module checks a review packet, not the scientific truth of a reading. It
never grants extraction, source-fidelity, or graph admission.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any
import unicodedata


class TokenLineageError(ValueError):
    """A scientific token has incomplete or inconsistent source lineage."""


@dataclass(frozen=True)
class TokenLineageResult:
    status: str
    token_count: int
    packet_sha256: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TokenLineageError(message)


def _ids(value: Any, name: str) -> tuple[int, ...]:
    _require(isinstance(value, list) and bool(value), f"{name}: missing glyph IDs")
    _require(all(type(item) is int and item >= 0 for item in value), f"{name}: invalid glyph ID")
    _require(len(set(value)) == len(value), f"{name}: repeated glyph ID")
    return tuple(value)


def _glyph_output(source_character: str) -> str:
    """Permit only exact characters or the five explicit Latin ligature forms."""
    _require(len(source_character) == 1, "source glyph must be one code point")
    if source_character in "\ufb00\ufb01\ufb02\ufb03\ufb04":
        return unicodedata.normalize("NFKC", source_character)
    return source_character


def verify_scientific_token_packet(packet: dict, *, source_sha256: str,
                                   notation_sha256: str, tex_sha256: str,
                                   evidence_sha256: str) -> TokenLineageResult:
    """Check exact output spans, typed scopes, and source identities.

    Packet keys are ``text``, ``source`` (three SHA-256 values), ``glyphs``
    (ID, printed character and box), ``rules`` (ID, box and numerator and
    denominator IDs), ``tex`` (matching-version exact source), and ``tokens``.
    Each token supplies an output range, typed tree, ordered output-character
    lineage, exact TeX anchor, and a review of alternate parses. A synthetic
    fraction slash must cite the rule plus numerator and denominator IDs.
    The caller must independently bind and regenerate all source assets and
    obtain actual source-first review; this verifier cannot do either.
    """
    import json

    _require(isinstance(packet, dict), "packet must be an object")
    source = packet.get("source")
    _require(isinstance(source, dict), "missing source bindings")
    for field, expected in (("pdf_sha256", source_sha256),
                            ("notation_sha256", notation_sha256),
                            ("tex_sha256", tex_sha256)):
        _require(isinstance(expected, str) and len(expected) == 64,
                 f"invalid expected {field}")
        _require(source.get(field) == expected, f"{field} mismatch")
    text = packet.get("text")
    tex = packet.get("tex")
    _require(isinstance(text, str) and text, "missing output text")
    _require(isinstance(tex, str) and tex, "missing TeX source")
    _require(sha256(tex.encode("utf-8")).hexdigest() == tex_sha256,
             "TeX source hash mismatch")
    glyphs = packet.get("glyphs")
    rules = packet.get("rules")
    tokens = packet.get("tokens")
    _require(isinstance(glyphs, list) and isinstance(rules, list)
             and isinstance(tokens, list) and tokens, "missing evidence inventory")
    source_lines = packet.get("source_lines", [])
    _require(isinstance(source_lines, list), "invalid source line inventory")
    evidence_body = {"glyphs": glyphs, "rules": rules}
    if source_lines:
        evidence_body["source_lines"] = source_lines
    evidence = json.dumps(evidence_body, ensure_ascii=False,
                          sort_keys=True, separators=(",", ":")).encode("utf-8")
    _require(sha256(evidence).hexdigest() == evidence_sha256,
             "source glyph/rule evidence mismatch")
    glyph_map = {}
    for glyph in glyphs:
        _require(isinstance(glyph, dict), "invalid glyph")
        gid = glyph.get("id")
        _require(type(gid) is int and gid >= 0 and gid not in glyph_map,
                 "duplicate or invalid glyph ID")
        _require(isinstance(glyph.get("char"), str) and glyph["char"],
                 "missing source glyph character")
        _glyph_output(glyph["char"])
        box = glyph.get("box")
        _require(isinstance(box, list) and len(box) == 4
                 and all(type(v) in (int, float) for v in box)
                 and box[0] < box[2] and box[1] < box[3], "invalid glyph box")
        glyph_map[gid] = glyph
    line_map = {}
    for line in source_lines:
        _require(isinstance(line, dict), "invalid source line")
        lid = line.get("id")
        _require(type(lid) is int and lid >= 0 and lid not in line_map,
                 "duplicate or invalid source line ID")
        role = line.get("role")
        _require(isinstance(role, str)
                 and role in {"abstract_body", "excluded_margin", "excluded_other"},
                 "invalid source line role")
        ids = _ids(line.get("glyph_ids"), "source line")
        _require(set(ids) <= glyph_map.keys(), "source line has unknown glyph")
        for offset, gid in enumerate(ids):
            glyph = glyph_map[gid]
            _require(glyph.get("line_id") == lid and glyph.get("line_offset") == offset,
                     "glyph source line or offset mismatch")
            _require(glyph.get("role") == line["role"], "glyph source role mismatch")
        box = line.get("box")
        _require(isinstance(box, list) and len(box) == 4
                 and all(type(v) in (int, float) for v in box)
                 and box[0] < box[2] and box[1] < box[3], "invalid source line box")
        for gid in ids:
            gb = glyph_map[gid]["box"]
            _require(box[0] <= gb[0] < gb[2] <= box[2]
                     and box[1] <= gb[1] < gb[3] <= box[3],
                     "glyph outside source line box")
        line_map[lid] = line
    if source_lines:
        all_line_ids = [gid for line in source_lines for gid in line["glyph_ids"]]
        _require(len(all_line_ids) == len(set(all_line_ids))
                 and set(all_line_ids) == glyph_map.keys(),
                 "source lines must partition glyph inventory")

    def checked_join(node: dict) -> tuple[int, int]:
        left, right = node.get("left_line_id"), node.get("right_line_id")
        _require(type(left) is int and type(right) is int
                 and left in line_map and right in line_map and left < right,
                 "line join lacks ordered source lines")
        _require(line_map[left]["role"] == line_map[right]["role"] == "abstract_body",
                 "line join lacks abstract body roles")
        _require(all(i in line_map for i in range(left + 1, right)),
                 "line join omits intervening source line")
        between = [line_map[i] for i in sorted(line_map) if left < i < right]
        _require(all(line["role"].startswith("excluded_") for line in between),
                 "line join crosses unowned source line")
        _require(node.get("left_glyph_id") == line_map[left]["glyph_ids"][-1]
                 and node.get("right_glyph_id") == line_map[right]["glyph_ids"][0],
                 "line join lacks exact source endpoints")
        for side, gid in (("left", node["left_glyph_id"]),
                          ("right", node["right_glyph_id"])):
            glyph = glyph_map[gid]
            _require(node.get(f"{side}_box") == glyph["box"]
                     and node.get(f"{side}_role") == glyph["role"]
                     and node.get(f"{side}_line_offset") == glyph["line_offset"],
                     "line join source witness mismatch")
        return node["left_glyph_id"], node["right_glyph_id"]
    rule_map = {}
    for rule in rules:
        _require(isinstance(rule, dict), "invalid rule")
        rid = rule.get("id")
        _require(type(rid) is int and rid >= 0 and rid not in rule_map,
                 "duplicate or invalid rule ID")
        numerator = _ids(rule.get("numerator_ids"), "rule numerator")
        denominator = _ids(rule.get("denominator_ids"), "rule denominator")
        _require(not set(numerator) & set(denominator), "rule operand overlap")
        _require(set(numerator + denominator) <= glyph_map.keys(),
                 "rule references unknown glyph")
        box = rule.get("box")
        _require(isinstance(box, list) and len(box) == 4
                 and all(type(v) in (int, float) for v in box)
                 and box[0] < box[2] and box[1] < box[3], "invalid rule box")
        # A rule cannot claim an unrelated earlier or neighboring occurrence.
        for gid in numerator + denominator:
            gbox = glyph_map[gid]["box"]
            center_x = (gbox[0] + gbox[2]) / 2
            _require(box[0] <= center_x <= box[2], "rule operand outside horizontal scope")
        _require(all(glyph_map[gid]["box"][3] <= box[1] for gid in numerator),
                 "numerator not above rule")
        _require(all(glyph_map[gid]["box"][1] >= box[3] for gid in denominator),
                 "denominator not below rule")
        rule_map[rid] = rule

    def verify_node(node: dict, output_ids: set[int], used_rules: set[int]) -> set[int]:
        _require(isinstance(node, dict), "invalid typed node")
        kind = node.get("kind")
        _require(kind in {"literal", "script", "fraction", "relation", "quantity", "line_join"},
                 "unknown typed node")
        if kind == "literal":
            ids = _ids(node.get("glyph_ids"), "literal")
            _require(set(ids) <= glyph_map.keys(), "literal references unknown glyph")
            _require(set(ids) <= output_ids, "literal is absent from output")
            return set(ids)
        if kind == "line_join":
            left, right = checked_join(node)
            children = node.get("children")
            _require(isinstance(children, dict) and set(children) == {"left", "right"},
                     "incomplete line join operands")
            a = verify_node(children["left"], output_ids, used_rules)
            b = verify_node(children["right"], output_ids, used_rules)
            _require(a and b and not a & b and left in a and right in b,
                     "line join operands lack source endpoints")
            return a | b
        children = node.get("children")
        expected = {"script": ("base", "subscript"),
                    "fraction": ("numerator", "denominator"),
                    "relation": ("left", "operator", "right"),
                    "quantity": ("value", "unit")}[kind]
        _require(isinstance(children, dict) and set(children) == set(expected),
                 "incomplete typed operands")
        child_sets = [verify_node(children[key], output_ids, used_rules) for key in expected]
        union = set()
        for ids in child_sets:
            _require(not union & ids, "typed operands reuse glyphs")
            union |= ids
        if kind == "fraction":
            rid = node.get("rule_id")
            _require(rid in rule_map and rid not in used_rules,
                     "missing or reused fraction rule")
            rule = rule_map[rid]
            _require(child_sets[0] == set(rule["numerator_ids"])
                     and child_sets[1] == set(rule["denominator_ids"]),
                     "fraction operands disagree with source rule")
            used_rules.add(rid)
        if kind == "script":
            base_y = min(glyph_map[gid]["box"][1] for gid in child_sets[0])
            sub_y = min(glyph_map[gid]["box"][1] for gid in child_sets[1])
            _require(sub_y > base_y, "subscript lacks source vertical scope")
        return union

    def tree_order(node: dict) -> list[int]:
        if node["kind"] == "literal":
            return node["glyph_ids"]
        if node["kind"] == "line_join":
            return tree_order(node["children"]["left"]) + tree_order(node["children"]["right"])
        order = {"script": ("base", "subscript"),
                 "fraction": ("numerator", "denominator"),
                 "relation": ("left", "operator", "right"),
                 "quantity": ("value", "unit")}[node["kind"]]
        return [gid for key in order for gid in tree_order(node["children"][key])]

    def tree_events(node: dict) -> list[tuple[str, int, int]]:
        """Serialize each typed node to its exact output lineage events."""
        kind = node["kind"]
        if kind == "literal":
            return [("glyph", gid, offset)
                    for gid in node["glyph_ids"]
                    for offset in range(len(_glyph_output(glyph_map[gid]["char"])))
                   ]
        children = node["children"]
        if kind == "line_join":
            left, right = checked_join(node)
            return (tree_events(children["left"])
                    + [("line_join_space", left, right)]
                    + tree_events(children["right"]))
        if kind == "fraction":
            return (tree_events(children["numerator"])
                    + [("fraction_slash", node["rule_id"], 0)]
                    + tree_events(children["denominator"]))
        order = {"script": ("base", "subscript"),
                 "relation": ("left", "operator", "right"),
                 "quantity": ("value", "unit")}[kind]
        return [event for key in order for event in tree_events(children[key])]

    position = 0
    global_ids: set[int] = set()
    for token in tokens:
        _require(isinstance(token, dict), "invalid token")
        span = token.get("range")
        _require(isinstance(span, list) and len(span) == 2, "invalid token range")
        start, end = span
        _require(type(start) is int and type(end) is int and start == position
                 and start < end <= len(text), "gap, overlap or invalid token range")
        position = end
        token_text = text[start:end]
        _require(token.get("text") == token_text, "token text mismatch")
        anchor = token.get("tex_anchor")
        _require(isinstance(anchor, str) and anchor and tex.count(anchor) == 1,
                 "TeX anchor absent or ambiguous")
        alternatives = token.get("alternate_scopes")
        _require(isinstance(alternatives, list) and alternatives
                 and all(isinstance(a, dict) and a.get("decision") == "rejected"
                         and isinstance(a.get("reason"), str) and a["reason"].strip()
                         for a in alternatives), "alternate scope review incomplete")
        chars = token.get("characters")
        _require(isinstance(chars, list) and len(chars) == len(token_text),
                 "output character lineage incomplete")
        local_ids: set[int] = set()
        character_order: list[int] = []
        consumed_offsets: dict[int, list[int]] = {}
        consumed_positions: dict[int, list[int]] = {}
        synthetic_rule_counts: dict[int, int] = {}
        actual_events: list[tuple[str, int, int]] = []
        for output_position, (actual, record) in enumerate(zip(token_text, chars)):
            _require(isinstance(record, dict) and record.get("char") == actual,
                     "output character mismatch")
            kind = record.get("kind")
            if kind == "glyph":
                ids = _ids(record.get("glyph_ids"), "output character")
                _require(len(ids) == 1, "output character must use one glyph")
                _require(set(ids) <= glyph_map.keys(), "unknown output glyph")
                gid = ids[0]
                offset = record.get("glyph_offset")
                source_output = _glyph_output(glyph_map[gid]["char"])
                _require(type(offset) is int and 0 <= offset < len(source_output),
                         "missing or invalid glyph character offset")
                _require(actual == source_output[offset],
                         "output character lacks exact source character")
                consumed_offsets.setdefault(gid, []).append(offset)
                consumed_positions.setdefault(gid, []).append(output_position)
                actual_events.append(("glyph", gid, offset))
                local_ids.update(ids)
                character_order.extend(ids)
            elif kind == "reviewed_delta_alias":
                ids = _ids(record.get("glyph_ids"), "delta alias")
                _require(len(ids) == 1 and ids[0] in glyph_map,
                         "delta alias has unknown source glyph")
                gid = ids[0]
                _require(actual == "Δ" and glyph_map[gid]["char"] == "∆"
                         and record.get("raw_char") == "∆" and record.get("glyph_offset") == 0,
                         "delta alias lacks exact raw glyph")
                glyph = glyph_map[gid]
                _require(type(glyph.get("line_id")) is int
                         and glyph["line_id"] in line_map
                         and line_map[glyph["line_id"]]["role"] == "abstract_body"
                         and record.get("source_box") == glyph["box"]
                         and record.get("source_line_id") == glyph["line_id"]
                         and record.get("source_line_offset") == glyph["line_offset"]
                         and record.get("source_role") == glyph["role"],
                         "delta alias source witness mismatch")
                consumed_offsets.setdefault(gid, []).append(0)
                consumed_positions.setdefault(gid, []).append(output_position)
                actual_events.append(("glyph", gid, 0))
                local_ids.add(gid)
                character_order.append(gid)
            elif kind == "line_join_space":
                _require(actual == " ", "line join must emit one space")
                left, right = checked_join(record)
                last_offset = len(_glyph_output(glyph_map[left]["char"])) - 1
                _require(actual_events and actual_events[-1] == ("glyph", left, last_offset),
                         "line join is not after left endpoint")
                actual_events.append(("line_join_space", left, right))
            elif kind == "fraction_slash":
                rid = record.get("rule_id")
                _require(actual == "/" and rid in rule_map, "unbound synthetic fraction slash")
                synthetic_rule_counts[rid] = synthetic_rule_counts.get(rid, 0) + 1
                actual_events.append(("fraction_slash", rid, 0))
            else:
                raise TokenLineageError("unbound output character")
        for gid, offsets in consumed_offsets.items():
            _require(offsets == list(range(len(_glyph_output(glyph_map[gid]["char"])))),
                     "source glyph not consumed exactly once in order")
            positions = consumed_positions[gid]
            _require(positions == list(range(positions[0], positions[0] + len(positions))),
                     "source glyph expansion is not contiguous")
        _require(not global_ids & local_ids, "glyph reused by another token")
        global_ids |= local_ids
        used_rules: set[int] = set()
        tree_ids = verify_node(token.get("tree"), local_ids, used_rules)
        _require(tree_ids == local_ids, "typed tree does not cover output glyphs")
        # A ligature may produce more than one output character from one glyph.
        _require(list(dict.fromkeys(character_order)) == tree_order(token["tree"]),
                 "typed tree/output glyph order mismatch")
        _require(set(synthetic_rule_counts) == used_rules
                 and all(count == 1 for count in synthetic_rule_counts.values()),
                 "fraction rule must emit exactly one output slash")
        _require(actual_events == tree_events(token["tree"]),
                 "output events disagree with typed serialization")
    _require(position == len(text), "output text is not fully tokenized")
    canonical = json.dumps(packet, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    return TokenLineageResult("MECHANICALLY_VERIFIED_REVIEW_REQUIRED", len(tokens),
                              sha256(canonical).hexdigest())
