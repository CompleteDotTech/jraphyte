"""Source-bound, non-admitting math review packets for page-one abstracts.

This module narrows the existing notation sidecar to an assessed abstract. It
does not turn geometric relations into a scientific transcription or a proposal.
"""
from __future__ import annotations

import hashlib
import unicodedata

from .pdf_notation_parallel_v4 import capture_notation
from .pdf_source_parallel_v4 import digest_value, validate_source_spans
from .pdf_structure_parallel_v4 import verify_assessment

VERSION = "source-bound-math-review-packet-v1"


def _bbox(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _safe_character(char):
    """An observed glyph is still not an approved mathematical symbol."""
    return {"id": char["id"], "raw": char["raw"], "native_ref": char["native_ref"],
            "bbox": char["bbox"], "origin": char["origin"], "font": char["font"],
            "font_refs": char["font_refs"], "font_program_status": char["font_program_status"],
            "trace_witnesses": char["trace_witnesses"], "uncertainty": char["uncertainty"]}


def packet_from_sidecar(sidecar: dict, assessment: dict, native: list[dict], *, page_sha256: str) -> dict:
    """Bind abstract-owned glyphs and candidate relations to exact source spans.

    Fail closed if an accepted text region crosses an unbound native character,
    if an equation relation crosses the abstract boundary, or if a source hash
    or native projection is inconsistent. The result is always review-only.
    """
    verify_assessment(assessment)
    if (sidecar.get("status") != "diagnostic_only" or sidecar.get("accepted") is not False
            or sidecar.get("native_identity") != "exact" or sidecar.get("rawdict_projection") != "exact"):
        raise ValueError("sidecar_identity_not_exact")
    source = sidecar.get("source", {})
    if (assessment.get("source_sha256") != source.get("original_pdf_sha256")
            or assessment.get("physical_page") != source.get("physical_page")
            or assessment.get("physical_page") != 1
            or assessment.get("page_sha256") != page_sha256
            or assessment.get("page_size") != source.get("page_size")
            or assessment.get("source_geometry_policy", {}).get("source_sha256") != source.get("original_pdf_sha256")):
        raise ValueError("assessment_source_or_page_identity_mismatch")
    if assessment.get("native_sha256") != digest_value(native):
        raise ValueError("assessment_native_identity_mismatch")
    if source.get("native_content_sha256") != digest_value(native):
        raise ValueError("sidecar_native_identity_mismatch")
    if not source.get("original_pdf_sha256") or source.get("physical_page") != 1:
        raise ValueError("missing_original_pdf_identity")
    spans = [span for entry in assessment.get("region_ownership", [])
             if entry.get("decision") == "included" for span in entry.get("source_spans", [])]
    if not spans:
        raise ValueError("no_source_bound_abstract_content")
    validate_source_spans(spans, native)
    owned = {(str(span["line_id"]), offset)
             for span in spans for offset in range(span["start"], span["end"])}
    chars = sidecar.get("characters", [])
    if [char.get("id") for char in chars] != list(range(len(chars))):
        raise ValueError("noncontiguous_character_ids")
    by_id = {str(line["id"]): line for line in native}
    all_refs = []
    for char in chars:
        ref = char.get("native_ref", {})
        line = by_id.get(str(ref.get("line_id")))
        start, end = ref.get("start"), ref.get("end")
        if (line is None or type(start) is not int or type(end) is not int or
                not 0 <= start < len(line["text"]) or end != start + 1 or
                line["text"][start] != char.get("raw")):
            raise ValueError("invalid_native_character_projection")
        uncertainty = char.get("uncertainty")
        if not isinstance(uncertainty, list):
            raise ValueError("invalid_character_uncertainty")
        if (unicodedata.category(char["raw"])[0] == "C" or ord(char["raw"]) == 0xfffd):
            if "native_unicode_unresolved" not in uncertainty:
                raise ValueError("unmarked_unresolved_native_character")
        witnesses = char.get("trace_witnesses")
        if not isinstance(witnesses, list):
            raise ValueError("invalid_trace_witnesses")
        if len(witnesses) == 1 and witnesses[0].get("unicode") != ord(char["raw"]):
            if "rawdict_trace_unicode_disagreement" not in uncertainty:
                raise ValueError("unmarked_trace_unicode_disagreement")
        all_refs.append((str(ref["line_id"]), start))
    if len(set(all_refs)) != len(all_refs):
        raise ValueError("duplicate_native_character_projection")
    included = [char for char, ref in zip(chars, all_refs) if ref in owned]
    refs = {(str(char["native_ref"]["line_id"]), char["native_ref"]["start"])
            for char in included}
    if len(included) != len(owned) or refs != owned:
        raise ValueError("abstract_glyph_projection_incomplete")
    ids = {char["id"] for char in included}
    rules = {rule["id"]: rule for rule in sidecar.get("rules", [])}
    relations = []
    boundary_crossings = []
    for relation in sidecar.get("relations", []):
        member_ids = relation.get("character_ids", [])
        if not member_ids or any(not isinstance(i, int) or i < 0 or i >= len(chars) for i in member_ids):
            raise ValueError("invalid_relation_character_ids")
        intersection = ids.intersection(member_ids)
        if not intersection:
            continue
        if len(intersection) != len(set(member_ids)):
            boundary_crossings.append(relation["id"])
            continue
        rule_id = relation.get("evidence", {}).get("rule_id")
        rule = rules.get(rule_id) if rule_id is not None else None
        if rule_id is not None and rule is None:
            raise ValueError("missing_relation_rule")
        member_boxes = [chars[i]["bbox"] for i in member_ids]
        scope = _bbox(member_boxes + ([[rule["x0"], rule["y"], rule["x1"], rule["y"]]] if rule else []))
        relations.append({"id": relation["id"], "kind": relation["kind"],
                          "character_ids": member_ids, "numerator": relation.get("numerator"),
                          "denominator": relation.get("denominator"), "scope_bbox": scope,
                          "expression_scope": "unresolved_geometry_only",
                          "rule": rule, "competing_candidate_ids": relation.get("competing_candidate_ids", []),
                          "uncertainty": relation["uncertainty"], "accepted": False})
    unresolved = [char["id"] for char in included if char["uncertainty"]]
    controls = [char["id"] for char in included if ord(char["raw"]) in (0, 1, 0xfffd)]
    return {"version": VERSION, "source_sha256": source["original_pdf_sha256"],
            "page_sha256": page_sha256, "physical_page": 1,
            "native_sha256": source["native_content_sha256"],
            "render": source.get("render"), "coordinates": source.get("coordinates"),
            "fonts": [font for i, font in enumerate(sidecar.get("fonts", []))
                      if any(i in char["font_refs"] for char in included)],
            "assessment_sha256": assessment.get("assessment_sha256"),
            "abstract_source_spans_sha256": digest_value(spans),
            "characters": [_safe_character(char) for char in included],
            "relations": relations, "boundary_crossing_relation_ids": boundary_crossings,
            "unresolved_character_ids": unresolved, "control_or_replacement_character_ids": controls,
            "status": "review_required", "accepted": False, "proposal": False,
            "scientific_transcription": None, "section_owner": None,
            "review_requirements": ["source_image_or_verified_font_glyph_mapping",
                                    "complete_expression_order_and_scope",
                                    "complete_abstract_scientific_transcription",
                                    "independent_replay_and_preservation_gate"]}


def capture_math_review_packet(pdf_bytes: bytes, page_bytes: bytes,
                               native: list[dict], assessment: dict) -> dict:
    """Re-extract from original PDF bytes; no cached image or converter is trusted."""
    if not isinstance(pdf_bytes, bytes) or not isinstance(page_bytes, bytes):
        raise ValueError("original_pdf_and_cached_page_bytes_required")
    sidecar, _image = capture_notation(pdf_bytes, native)
    if sidecar.get("source", {}).get("original_pdf_sha256") != hashlib.sha256(pdf_bytes).hexdigest():
        raise ValueError("source_hash_mismatch")
    return packet_from_sidecar(sidecar, assessment, native,
                               page_sha256=hashlib.sha256(page_bytes).hexdigest())
