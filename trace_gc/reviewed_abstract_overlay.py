"""Opt-in, source-bound review of a first-page abstract; never graph authority.

This module does not alter the automatic selector or infer a correction. It
validates a separately authored transcript and two application-trusted reviews.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from .pdf_notation_parallel_v4 import capture_notation
from .pdf_source_parallel_v4 import digest_value, normalize, validate_lines, validate_source_spans
from .pdf_structure_parallel_v4 import verify_assessment
from .trust import TrustStore

PURPOSE = "OBSERVATION"  # Existing receipt schema; payload subtype isolates this review.
VERSION = "source-bound-reviewed-abstract-v1"
HEX = re.compile(r"[0-9a-f]{64}\Z")


def _hash(value: bytes) -> str:
    if type(value) is not bytes:
        raise ValueError("review_asset_must_be_bytes")
    return hashlib.sha256(value).hexdigest()


def verify_first_page_identity(source_pdf: bytes, page_pdf: bytes) -> None:
    """Check the cached page depicts physical page zero of the original PDF.

    Same-runtime rendering comparison follows the existing private-harness
    tolerance. It binds visible page content, not byte-identical PDF structure.
    """
    import fitz
    from PIL import Image, ImageChops

    with fitz.open(stream=source_pdf, filetype="pdf") as source, fitz.open(stream=page_pdf, filetype="pdf") as page:
        if len(source) < 1 or len(page) != 1:
            raise ValueError("review_page_pdf_not_single_first_page")
        left = source[0].get_pixmap(dpi=120, alpha=False)
        right = page[0].get_pixmap(dpi=120, alpha=False)
        if (left.width, left.height) != (right.width, right.height):
            raise ValueError("review_page_pdf_not_first_page")
        if left.samples != right.samples:
            a = Image.frombytes("RGB", (left.width, left.height), left.samples)
            b = Image.frombytes("RGB", (right.width, right.height), right.samples)
            delta = ImageChops.difference(a, b)
            if max(channel[1] for channel in delta.getextrema()) > 2:
                raise ValueError("review_page_pdf_not_first_page")


def _bound(expected: str, value: str, name: str) -> None:
    if type(expected) is not str or not HEX.fullmatch(expected) or expected != value:
        raise ValueError(name + "_hash_mismatch")


def _review(trust: TrustStore, receipt: dict, *, manifest_hash: str, decision: str,
            at: str | None) -> str:
    policy = trust.verify(receipt, PURPOSE, at=at)
    payload = receipt["payload"]
    if (not policy.can_review or set(payload) != {"review_kind", "manifest_sha256", "decision", "reviewer",
                                               "reviewer_kind", "reviewed_at"}
            or payload["review_kind"] != VERSION
            or payload["manifest_sha256"] != manifest_hash or payload["decision"] != decision
            or payload["reviewer"] != policy.principal or not payload["reviewer"]
            or payload["reviewer_kind"] not in {"human", "assistant"}
            or not isinstance(payload["reviewed_at"], str)
            or payload["reviewed_at"] != receipt["issued_at"]):
        raise ValueError("review_attribution_or_binding_invalid")
    return policy.principal


def _signed_time(receipt: dict) -> datetime:
    value = receipt["issued_at"]
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError("review_time_invalid")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise ValueError("review_time_invalid") from None


def _source_page_stamp(line: dict, notation: dict, page_size: list[float]) -> bool:
    """Require source-visible rotated arXiv margin evidence for an omitted line."""
    x0, y0, x1, y1 = line["bbox"]
    chars = [char for char in notation["characters"]
             if str(char.get("native_ref", {}).get("line_id")) == str(line["id"])]
    return (re.fullmatch(r"\s*arXiv:\d{4}\.\d{4,5}(?:v\d+)?"
                         r"(?:\s*\[[A-Za-z][A-Za-z0-9-]*(?:\.[A-Za-z][A-Za-z0-9-]*)?\])?"
                         r"(?:\s+\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})?\s*",
                         line["text"], re.I) is not None
            and y1-y0 > 3*(x1-x0)
            and (x1 < .1*page_size[0] or x0 > .9*page_size[0])
            and bool(chars) and all(char.get("direction") in ([0.0, -1.0], [0.0, 1.0])
                                    for char in chars))


def _split_section_number(line: dict, marker: dict) -> bool:
    """Recognize a source-located number printed beside its section title."""
    left, right = line["bbox"], marker["bbox"]
    return (int(line["id"]) + 1 == int(marker["id"])
            and re.fullmatch(r"\s*\d{1,3}\.?\s*", line["text"]) is not None
            and abs(left[1] - right[1]) <= 1.0 and abs(left[3] - right[3]) <= 1.0
            and 0 <= right[0] - left[2] <= 30)


def _unaccounted_visual_paint(source_pdf: bytes, top: float, bottom: float,
                              notation: dict | None = None, used_glyph_ids: set[int] | None = None,
                              reviewed_rules: list[dict] | None = None) -> bool:
    """Fail closed on raster/vector marks inside the candidate abstract band.

    Native glyph accounting cannot see prose drawn as an image or outlines.
    This deliberately holds mathematical rules too until they have a separate
    source-bound visual witness; it is a safety gate, not a completeness proof.
    """
    import fitz

    if reviewed_rules is None:
        reviewed_rules = []
    if used_glyph_ids is None:
        used_glyph_ids = set()
    if type(reviewed_rules) is not list or type(used_glyph_ids) is not set:
        return True
    notation = notation or {"rules": [], "characters": []}
    by_rule = {rule["id"]: rule for rule in notation.get("rules", [])}
    witnesses = {}
    overlap_crops = {}
    for entry in reviewed_rules:
        if (type(entry) is not dict or not {"rule_id", "numerator_glyph_ids", "denominator_glyph_ids"} <= set(entry)
                or set(entry) - {"rule_id", "numerator_glyph_ids", "denominator_glyph_ids", "overlap_crop_sha256", "visual_review"}
                or type(entry["rule_id"]) is not int or entry["rule_id"] in witnesses
                or entry["rule_id"] not in by_rule):
            return True
        numerator, denominator = entry["numerator_glyph_ids"], entry["denominator_glyph_ids"]
        if (type(numerator) is not list or type(denominator) is not list
                or not numerator or not denominator
                or any(type(gid) is not int for gid in numerator + denominator)
                or len(set(numerator + denominator)) != len(numerator + denominator)
                or not set(numerator + denominator) <= used_glyph_ids):
            return True
        chars = notation["characters"]
        if any(not 0 <= gid < len(chars) or chars[gid].get("id") != gid
               for gid in numerator + denominator):
            return True
        rule = by_rule[entry["rule_id"]]
        centers = lambda ids: [((chars[gid]["bbox"][0] + chars[gid]["bbox"][2])/2,
                                (chars[gid]["bbox"][1] + chars[gid]["bbox"][3])/2) for gid in ids]
        above, below = centers(numerator), centers(denominator)
        bounds = lambda ids: (min(chars[gid]["bbox"][0] for gid in ids),
                              max(chars[gid]["bbox"][2] for gid in ids))
        spans = [bounds(numerator), bounds(denominator)]
        widest = max(right-left for left, right in spans)
        overlap = lambda left, right: max(0.0, min(right, rule["x1"]) - max(left, rule["x0"]))
        overlap_depth = max(0.0,
            max(chars[gid]["bbox"][3] for gid in numerator) - (rule["y"] - rule["stroke_width"]/2),
            (rule["y"] + rule["stroke_width"]/2) - min(chars[gid]["bbox"][1] for gid in denominator))
        if (max(y for _, y in above) >= rule["y"] or min(y for _, y in below) <= rule["y"]
                or overlap_depth > 1.3
                or not any(rule["x0"] <= x <= rule["x1"] for x, _ in above)
                or not any(rule["x0"] <= x <= rule["x1"] for x, _ in below)
                or rule["x1"] - rule["x0"] > widest + max(8.0, widest * .3)
                or any(overlap(left, right) < .7*(right-left) for left, right in spans)):
            return True
        crop_hash = entry.get("overlap_crop_sha256")
        if overlap_depth > .05:
            if (type(crop_hash) is not str or not HEX.fullmatch(crop_hash)
                    or entry.get("visual_review") != {
                        "decision": "no_visible_ink_collision",
                        "scope": "original_pdf_eight_x_rule_crop"}):
                return True
            overlap_crops[entry["rule_id"]] = crop_hash
        elif crop_hash is not None or "visual_review" in entry:
            return True
        witnesses[entry["rule_id"]] = rule
    consumed = set()
    with fitz.open(stream=source_pdf, filetype="pdf") as document:
        page = document[0]
        for rule_id, expected in overlap_crops.items():
            rule = witnesses[rule_id]
            clip = fitz.Rect(rule["x0"]-8, rule["y"]-16, rule["x1"]+8, rule["y"]+16)
            cropped = page.get_pixmap(matrix=fitz.Matrix(8, 8), clip=clip, alpha=False).tobytes("png")
            if _hash(cropped) != expected:
                return True
        for appearance in list(page.annots() or []) + list(page.widgets() or []):
            box = appearance.rect
            if box.y1 > top and box.y0 < bottom and box.x1 > 0 and box.x0 < page.rect.width:
                return True
        drawings = {}
        for drawing in page.get_drawings():
            drawings.setdefault(drawing["seqno"], []).append(drawing)
        for seqno, (kind, box) in enumerate(page.get_bboxlog()):
            if not (box[3] > top and box[1] < bottom and box[2] > 0 and box[0] < page.rect.width):
                continue
            if kind == "fill-text":
                continue
            if kind != "stroke-path":
                return True
            match = [rid for rid, rule in witnesses.items() if rule["seqno"] == seqno]
            if len(match) != 1 or match[0] in consumed or len(drawings.get(seqno, [])) != 1:
                return True
            drawing = drawings[seqno][0]
            rule = witnesses[match[0]]
            items = drawing.get("items", [])
            if (drawing.get("type") != "s" or drawing.get("fill") is not None
                    or drawing.get("layer") or drawing.get("closePath")
                    or drawing.get("stroke_opacity") != 1.0
                    or drawing.get("color") != (0.0, 0.0, 0.0)
                    or drawing.get("dashes") != "[] 0"
                    or drawing.get("lineCap") != (0, 0, 0)
                    or drawing.get("lineJoin") != 0.0
                    or len(items) != 1 or items[0][0] != "l"):
                return True
            _, start, end = items[0]
            if (abs(start.y - end.y) > .01
                    or abs(min(start.x, end.x) - rule["x0"]) > .01
                    or abs(max(start.x, end.x) - rule["x1"]) > .01
                    or abs(start.y - rule["y"]) > .01
                    or abs(drawing["width"] - rule["stroke_width"]) > .01):
                return True
            consumed.add(match[0])
    return consumed != set(witnesses)


def _typed_expression(node: dict, glyph_ids: list[int], notation: dict) -> None:
    """Check a bounded typed shape against exact sidecar glyph/rule geometry.

    This is a structural witness check, not scientific interpretation.
    """
    if type(node) is not dict or type(node.get("kind")) is not str:
        raise ValueError("review_expression_tree_invalid")
    kind = node["kind"]
    ids = set(glyph_ids)
    chars = notation["characters"]
    def listed(value):
        return (type(value) is list and value and all(type(i) is int and i in ids for i in value)
                and len(set(value)) == len(value))
    def ymid(gid):
        box = chars[gid]["bbox"]
        return (box[1] + box[3]) / 2
    if kind == "word":
        if set(node) != {"kind", "glyph_ids"} or not listed(node["glyph_ids"]) or set(node["glyph_ids"]) != ids:
            raise ValueError("review_word_glyph_scope_invalid")
    elif kind == "fraction":
        if (set(node) != {"kind", "numerator", "denominator", "rule_id"}
                or not listed(node["numerator"]) or not listed(node["denominator"])
                or set(node["numerator"]) & set(node["denominator"])
                or set(node["numerator"] + node["denominator"]) != ids
                or type(node["rule_id"]) is not int):
            raise ValueError("review_fraction_scope_invalid")
        rules = [rule for rule in notation["rules"] if rule["id"] == node["rule_id"]]
        if len(rules) != 1 or not (max(ymid(i) for i in node["numerator"]) < rules[0]["y"]
                                   < min(ymid(i) for i in node["denominator"])):
            raise ValueError("review_fraction_rule_invalid")
    elif kind == "script":
        if (set(node) != {"kind", "base", "sub", "sup"} or type(node["base"]) is not int
                or node["base"] not in ids or not isinstance(node["sub"], list)
                or not isinstance(node["sup"], list) or not (node["sub"] or node["sup"])
                or set([node["base"]] + node["sub"] + node["sup"]) != ids):
            raise ValueError("review_script_scope_invalid")
        for role in ("sub", "sup"):
            for script in node[role]:
                matches = [r for r in notation["relations"] if r["kind"] == "script"
                           and r["base"] == node["base"] and r["script"] == script
                           and r["role"] == ("subscript_candidate" if role == "sub" else "superscript_candidate")]
                if len(matches) != 1:
                    raise ValueError("review_script_relation_invalid")
    elif kind == "accent":
        if (set(node) != {"kind", "base", "mark"} or node["base"] == node["mark"]
                or {node["base"], node["mark"]} != ids
                or ymid(node["mark"]) >= ymid(node["base"])):
            raise ValueError("review_accent_scope_invalid")
    elif kind in {"ligature", "control", "mapsto"}:
        if set(node) != {"kind", "glyph_ids", "unicode"} or not listed(node["glyph_ids"]) or set(node["glyph_ids"]) != ids:
            raise ValueError("review_special_glyph_scope_invalid")
        raw = "".join(chars[i]["raw"] for i in node["glyph_ids"])
        if ((kind == "ligature" and (len(ids) < 2 or not node["unicode"].isalpha()))
                or (kind == "control" and not any(ord(c) < 32 for c in raw))
                or (kind == "mapsto" and (node["unicode"] != "↦" or "→" not in raw))):
            raise ValueError("review_special_glyph_evidence_invalid")
    else:
        raise ValueError("review_expression_kind_unsupported")


def apply_reviewed_abstract(*, automatic: dict, manifest: dict, first_review: dict,
                            second_review: dict, trust: TrustStore, source_pdf: bytes,
                            page_pdf: bytes, page_image: bytes, native_lines: list[dict],
                            converter_assets: dict[str, bytes], code_assets: dict[str, bytes],
                            tex_source: bytes, notation_evidence: bytes,
                            at: str | None = None) -> dict:
    """Return a distinct, sealed review result after complete evidence verification.

    Asset bytes are supplied by the caller's trusted file adapter. The adapter
    must choose them from the frozen local manifest, never a path inside a review.
    The cached page is compared to source page zero by same-runtime rendering;
    this does not prove byte-identical PDF structure. A TeX anchor is only an
    exact substring witness, not automatic source/PDF semantic parity. A
    cryptographic review receipt is attribution, not proof of careful reading.
    """
    verify_assessment(automatic)
    before = digest_value(automatic)
    if manifest.get("version") != VERSION or manifest.get("physical_page") != 1:
        raise ValueError("review_version_or_page_invalid")
    if manifest.get("decision") not in {"accepted", "HOLD", "reviewed_legacy_proposal"}:
        raise ValueError("review_decision_invalid")
    # A signed transcript can still omit a paragraph or an in-scope glyph.
    # Acceptance remains disabled until complete source-order and glyph
    # coverage are proven against fresh PDF-derived evidence.
    if manifest["decision"] == "accepted":
        raise ValueError("review_acceptance_requires_complete_pdf_proof")
    legacy_proposal = manifest["decision"] == "reviewed_legacy_proposal"
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    manifest_hash = digest_value(body)
    _bound(manifest.get("manifest_sha256"), manifest_hash, "review_manifest")
    identity = manifest.get("identity", {})
    _bound(identity.get("source_sha256"), _hash(source_pdf), "source")
    _bound(identity.get("page_sha256"), _hash(page_pdf), "page")
    verify_first_page_identity(source_pdf, page_pdf)
    _bound(identity.get("image_sha256"), _hash(page_image), "image")
    _bound(identity.get("native_sha256"), digest_value(native_lines), "native")
    _bound(identity.get("automatic_assessment_sha256"), automatic["assessment_sha256"], "automatic")
    _bound(identity.get("tex_sha256"), _hash(tex_source), "tex")
    _bound(identity.get("notation_sha256"), _hash(notation_evidence), "notation")
    notation = json.loads(notation_evidence)
    if (notation.get("source", {}).get("original_pdf_sha256") != identity["source_sha256"]
            or notation.get("source", {}).get("render", {}).get("png_sha256") != identity["image_sha256"]):
        raise ValueError("notation_source_binding_invalid")
    fresh_notation, fresh_image = capture_notation(source_pdf, native_lines)
    if (fresh_notation.get("status") != "diagnostic_only"
            or fresh_notation.get("rawdict_projection") != "exact"
            or digest_value({key: notation.get(key) for key in fresh_notation}) != digest_value(fresh_notation)
            or fresh_image != page_image):
        raise ValueError("notation_pdf_replay_mismatch")
    if automatic["source_sha256"] != identity["source_sha256"] or automatic["page_sha256"] != identity["page_sha256"]:
        raise ValueError("automatic_source_binding_invalid")
    if (set(identity.get("converter_sha256", {})) != set(converter_assets)
            or set(identity.get("code_sha256", {})) != set(code_assets) | {"reviewed_abstract_overlay.py"}):
        raise ValueError("asset_inventory_mismatch")
    for name, value in converter_assets.items():
        _bound(identity["converter_sha256"][name], _hash(value), "converter")
    for name, value in {**code_assets, "reviewed_abstract_overlay.py": Path(__file__).read_bytes()}.items():
        _bound(identity["code_sha256"][name], _hash(value), "code")
    first = _review(trust, first_review, manifest_hash=manifest_hash, decision=manifest["decision"], at=at)
    second = _review(trust, second_review, manifest_hash=manifest_hash, decision=manifest["decision"], at=at)
    if (first == second or first_review["issuer"] == second_review["issuer"]
            or _signed_time(second_review) <= _signed_time(first_review)):
        raise ValueError("distinct_second_review_required")

    native = validate_lines(native_lines, automatic["page_size"])
    if not native or digest_value(native) != identity["native_sha256"]:
        raise ValueError("native_revalidation_mismatch")
    selected = manifest.get("native_spans")
    if not isinstance(selected, list) or not selected:
        raise ValueError("complete_review_requires_native_spans")
    validate_source_spans(selected, native)
    if [span.get("source_order") for span in selected] != list(range(len(selected))):
        raise ValueError("review_source_order_invalid")
    positions = [(int(span["line_id"]), span["start"], span["end"]) for span in selected]
    if positions != sorted(positions) or any(a[0] == b[0] and a[2] > b[1] for a, b in zip(positions, positions[1:])):
        raise ValueError("review_native_spans_overlap_or_reorder")
    by_id = {str(line["id"]): line for line in native}
    line_roles = manifest.get("line_roles")
    if not isinstance(line_roles, list) or len(line_roles) != len(native):
        raise ValueError("review_line_inventory_incomplete")
    valid_roles = {"abstract", "title", "authors", "page_stamp", "keywords", "body",
                   "heading", "footnote", "caption", "other_source"}
    selected_ids = {str(span["line_id"]) for span in selected}
    first_span = selected[0]
    first_line = by_id[str(first_span["line_id"])]
    heading_prefix = first_line["text"][:first_span["start"]]
    source_heading_prefix = bool(re.fullmatch(r"\s*Abstract\s*[:.]\s*", heading_prefix, re.I))
    if legacy_proposal:
        separate_heading = by_id.get(str(int(first_span["line_id"]) - 1))
        separate_heading_valid = (separate_heading is not None and
            re.fullmatch(r"\s*Abstract\s*[:.]?\s*", separate_heading["text"], re.I) is not None and
            separate_heading["bbox"][1] < first_line["bbox"][1])
        if not (source_heading_prefix or (first_span["start"] == 0 and separate_heading_valid)):
            raise ValueError("review_legacy_opening_not_source_bound")
        if (any(span["end"] != len(by_id[str(span["line_id"])]["text"]) for span in selected)
                or any(span["start"] != 0 for span in selected[1:])):
            raise ValueError("review_legacy_native_line_truncated")
    line_roles_by_id = {}
    for index, (entry, line) in enumerate(zip(line_roles, native)):
        if (entry.get("source_order") != index or str(entry.get("line_id")) != str(line["id"])
                or entry.get("bbox") != line["bbox"] or entry.get("text_sha256") != _hash(line["text"].encode())
                or entry.get("role") not in valid_roles or not isinstance(entry.get("reason"), str)
                or not entry["reason"].strip()):
            raise ValueError("review_line_role_not_source_bound")
        if (entry["role"] == "abstract") != (str(line["id"]) in selected_ids):
            raise ValueError("review_line_role_conflicts_with_selected_spans")
        expected_glyphs = [char["id"] for char in notation["characters"]
                           if str(char.get("native_ref", {}).get("line_id")) == str(line["id"])]
        if entry.get("glyph_ids") != expected_glyphs:
            raise ValueError("review_line_glyph_inventory_mismatch")
        line_roles_by_id[str(line["id"])] = entry
    if (legacy_proposal and not source_heading_prefix and
            line_roles_by_id[str(int(first_span["line_id"]) - 1)]["role"] != "heading"):
        raise ValueError("review_legacy_opening_role_invalid")
    first_selected = positions[0][0]
    last_selected = positions[-1][0]
    abstract_left = min(by_id[str(span["line_id"])]["bbox"][0] for span in selected)
    abstract_right = max(by_id[str(span["line_id"])]["bbox"][2] for span in selected)
    for line in native:
        if first_selected < int(line["id"]) < last_selected and str(line["id"]) not in selected_ids:
            role = line_roles_by_id[str(line["id"])]["role"]
            if (role != "page_stamp" or
                    not (line["bbox"][2] < abstract_left or line["bbox"][0] > abstract_right) or
                    (legacy_proposal and not _source_page_stamp(line, notation, automatic["page_size"]))):
                raise ValueError("review_interleaved_nonabstract_line")
    used_glyph_ids = set(manifest.get("used_glyph_ids", []))
    excluded = manifest.get("excluded_glyphs")
    if not isinstance(excluded, list) or not isinstance(manifest.get("used_glyph_ids"), list):
        raise ValueError("review_glyph_accounting_missing")
    excluded_ids = set()
    for item in excluded:
        gid = item.get("character_id")
        if (type(gid) is not int or not 0 <= gid < len(notation["characters"])
                or item.get("role") not in {"title", "authors", "page_stamp", "keywords", "body",
                                         "heading", "footnote", "caption", "other_source", "whitespace"}):
            raise ValueError("review_exclusion_invalid")
        excluded_ids.add(gid)
        char = notation["characters"][gid]
        if item["role"] == "whitespace" and (type(char.get("raw")) is not str or
                                              not char["raw"].isspace()):
            raise ValueError("review_nonwhitespace_excluded_as_whitespace")
        owner = line_roles_by_id.get(str(char.get("native_ref", {}).get("line_id")))
        same_line_heading = (item["role"] == "heading" and source_heading_prefix and
                             str(char.get("native_ref", {}).get("line_id")) == str(first_span["line_id"]) and
                             char["native_ref"]["end"] <= first_span["start"] and
                             owner is not None and owner["role"] == "abstract")
        if owner is None or (item["role"] != "whitespace" and item["role"] != owner["role"]
                             and not same_line_heading):
            raise ValueError("review_exclusion_role_conflict")
    if (len(used_glyph_ids) != len(manifest["used_glyph_ids"])
            or len(excluded_ids) != len(excluded) or used_glyph_ids & excluded_ids
            or used_glyph_ids | excluded_ids != set(range(len(notation["characters"])))):
        raise ValueError("review_glyph_partition_incomplete")
    for char in notation["characters"]:
        cid = char["id"]
        ref = char.get("native_ref", {})
        in_spans = any(str(ref.get("line_id")) == str(span["line_id"])
                       and span["start"] <= ref.get("start", -1) < ref.get("end", -1) <= span["end"]
                       for span in selected)
        if (cid in used_glyph_ids) != in_spans:
            raise ValueError("review_glyph_span_ownership_mismatch")
    boundary = manifest.get("closing_boundary", {})
    if boundary.get("kind") not in {"keywords", "introduction", "outer_section", "page_boundary"}:
        raise ValueError("review_boundary_kind_invalid")
    marker = by_id.get(str(boundary.get("line_id")))
    if marker is None or boundary.get("page_no") != 1 or boundary.get("bbox") != marker["bbox"]:
        raise ValueError("review_boundary_source_invalid")
    start, end = boundary.get("start"), boundary.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(marker["text"]):
        raise ValueError("review_boundary_offset_invalid")
    if marker["text"][start:end] != boundary.get("text") or (int(marker["id"]), start) <= (positions[-1][0], positions[-1][2]):
        raise ValueError("review_boundary_not_after_abstract")
    if legacy_proposal:
        opening_line = (int(first_span["line_id"]) if source_heading_prefix
                        else int(first_span["line_id"]) - 1)
        band_top = by_id[str(opening_line)]["bbox"][1]
        band_bottom = marker["bbox"][1]
        if band_bottom <= band_top or _unaccounted_visual_paint(
                source_pdf, band_top, band_bottom, notation, used_glyph_ids,
                manifest.get("reviewed_visual_rules", [])):
            raise ValueError("review_visual_paint_requires_source_review")
    for line in native:
        if last_selected < int(line["id"]) < int(marker["id"]):
            role = line_roles_by_id[str(line["id"])]["role"]
            split_number = (legacy_proposal and boundary["kind"] == "introduction"
                            and role == "heading" and _split_section_number(line, marker))
            stamp = (role == "page_stamp"
                     and (line["bbox"][2] < abstract_left or line["bbox"][0] > abstract_right)
                     and (not legacy_proposal or _source_page_stamp(line, notation, automatic["page_size"])))
            if not (split_number or stamp):
                raise ValueError("review_unowned_line_before_boundary")
    expected_boundary_role = "keywords" if boundary["kind"] == "keywords" else "heading"
    if boundary["kind"] in {"keywords", "introduction", "outer_section"} and line_roles_by_id[str(marker["id"])]["role"] != expected_boundary_role:
        raise ValueError("review_boundary_role_mismatch")
    if legacy_proposal:
        prefix = marker["text"][:boundary["end"]]
        if not ((boundary["kind"] == "keywords" and
                 re.fullmatch(r"\s*Keywords?\b\s*[:.]?", prefix, re.I)) or
                (boundary["kind"] == "introduction" and
                 re.fullmatch(r"\s*(?:1\.?\s+)?Introduction\b\s*[:.]?", prefix, re.I))):
            raise ValueError("review_legacy_closing_marker_not_source_bound")

    edits = manifest.get("corrections")
    if not isinstance(edits, list):
        raise ValueError("review_corrections_invalid")
    if legacy_proposal and edits:
        raise ValueError("review_legacy_corrections_forbidden")
    by_span: dict[int, list[dict]] = {index: [] for index in range(len(selected))}
    for edit in edits:
        index = edit.get("span_index")
        if type(index) is not int or index not in by_span:
            raise ValueError("review_correction_span_invalid")
        span = selected[index]
        a, b = edit.get("start"), edit.get("end")
        if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(span["text"]):
            raise ValueError("review_correction_offset_invalid")
        if span["text"][a:b] != edit.get("before") or not isinstance(edit.get("after"), str) or not edit["after"]:
            raise ValueError("review_correction_text_invalid")
        evidence = edit.get("evidence", {})
        anchor = evidence.get("tex_anchor")
        if (edit.get("kind") not in {"glyph", "expression", "hyphenation"}
                or not isinstance(anchor, str) or not anchor or anchor.encode() not in tex_source
                or not isinstance(evidence.get("expression_tree"), dict)
                or not isinstance(evidence.get("glyphs"), list) or not evidence["glyphs"]):
            raise ValueError("review_correction_evidence_incomplete")
        for glyph in evidence["glyphs"]:
            character_id = glyph.get("character_id")
            if type(character_id) is not int or not 0 <= character_id < len(notation["characters"]):
                raise ValueError("review_glyph_id_invalid")
            character = notation["characters"][character_id]
            font = next((item for item in notation["fonts"]
                         if item["name"].split("+")[-1] == character["font"]), None)
            ref = character["native_ref"]
            if (glyph.get("line_id") != span["line_id"] or ref["line_id"] != span["line_id"]
                    or not span["start"] + a <= ref["start"] < ref["end"] <= span["start"] + b
                    or glyph.get("bbox") != character["bbox"]
                    or font is None or glyph.get("font_sha256") != font.get("embedded_sha256")):
                raise ValueError("review_glyph_binding_invalid")
        _typed_expression(evidence["expression_tree"],
                          [glyph["character_id"] for glyph in evidence["glyphs"]], notation)
        by_span[index].append(edit)
    pieces = []
    transcript_lineage = []
    output_offset = 0
    for index, span in enumerate(selected):
        joiner = span.get("joiner", "" if index == 0 else " ")
        if not isinstance(joiner, str) or not re.fullmatch(r"\s*", joiner):
            raise ValueError("review_joiner_invalid")
        if legacy_proposal and joiner != ("" if index == 0 else " "):
            raise ValueError("review_legacy_joiner_not_frozen")
        if joiner:
            transcript_lineage.append({"kind": "layout_join", "output_start": output_offset,
                                       "output_end": output_offset + len(joiner), "span_index": index})
            pieces.append(joiner)
            output_offset += len(joiner)
        cursor = 0
        for edit in sorted(by_span[index], key=lambda value: value["start"]):
            if edit["start"] < cursor:
                raise ValueError("review_corrections_overlap")
            if edit["start"] > cursor:
                raw = span["text"][cursor:edit["start"]]
                transcript_lineage.append({"kind": "native", "output_start": output_offset,
                    "output_end": output_offset + len(raw), "span_index": index,
                    "line_id": span["line_id"], "native_start": span["start"] + cursor,
                    "native_end": span["start"] + edit["start"]})
                pieces.append(raw)
                output_offset += len(raw)
            transcript_lineage.append({"kind": "correction", "output_start": output_offset,
                "output_end": output_offset + len(edit["after"]), "span_index": index,
                "line_id": span["line_id"], "native_start": span["start"] + edit["start"],
                "native_end": span["start"] + edit["end"],
                "correction_sha256": digest_value(edit)})
            pieces.append(edit["after"])
            output_offset += len(edit["after"])
            cursor = edit["end"]
        if cursor < len(span["text"]):
            raw = span["text"][cursor:]
            transcript_lineage.append({"kind": "native", "output_start": output_offset,
                "output_end": output_offset + len(raw), "span_index": index,
                "line_id": span["line_id"], "native_start": span["start"] + cursor,
                "native_end": span["end"]})
            pieces.append(raw)
            output_offset += len(raw)
    diplomatic = "".join(pieces)
    if (manifest.get("diplomatic_abstract") != diplomatic or not diplomatic.strip()
            or manifest.get("normalized_abstract") != normalize(diplomatic)):
        raise ValueError("complete_review_transcript_not_derived_from_source")
    if len(diplomatic) > manifest.get("max_input_chars", 4000):
        raise ValueError("review_request_budget_exceeded")
    if digest_value(automatic) != before:
        raise ValueError("automatic_assessment_mutated")
    result = {"schema_version": 1, "origin": "source_reviewed_abstract_overlay", "decision": manifest["decision"],
              "status": "complete" if legacy_proposal else "uncertain",
              "proposal": legacy_proposal, "text": diplomatic,
              "coverage_scope": "native_text_only", "visual_coverage_qualified": False,
              "normalized_text": manifest["normalized_abstract"], "spans": selected,
              "transcript_lineage": transcript_lineage,
              "closing_boundary": boundary, "source_sha256": identity["source_sha256"],
              "page_sha256": identity["page_sha256"], "eligible_for_jev": False,
              "field_candidate": False, "graph_admission_enabled": False,
              "scientific_notation_qualified": False,
              "verified_admission": False, "admission": "source_review_required",
              "notation_fidelity": "HOLD", "math_review_required": legacy_proposal,
              "lineage": {"automatic_assessment_sha256": automatic["assessment_sha256"],
                          "review_manifest_sha256": manifest_hash, "first_review_sha256": digest_value(first_review),
                          "second_review_sha256": digest_value(second_review),
                          "reviewers": [first, second], "asset_hashes": identity}}
    result["reviewed_assessment_sha256"] = digest_value(result)
    return result
