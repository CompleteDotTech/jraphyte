"""Additive scientific-transcription and reviewed-source metrics; no admission authority.

Legacy canonical/compare remain unchanged. Review evidence is attributed, never
inferred from model agreement; recording an attribution does not authenticate it.
"""
from __future__ import annotations

from collections import Counter
import datetime as dt
import hashlib
import math
import re
import unicodedata

LEGACY_METRIC_VERSION = "ordered-alphanumeric-text98-boundary48-v1"
FIDELITY_METRIC_VERSION = "notation-reviewed-source-boundary-v1"
STATES = ("pass", "fail", "unresolved", "not_applicable")
_SUPER = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ", "0123456789+-=()ni"))
_SUB = dict(zip("₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎", "0123456789+-=()"))
_HASH = re.compile(r"[0-9a-f]{64}")
_MAX_POSITIONS = 100_000


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def notation_tokens(text: str) -> list[str]:
    """NFC, Unicode minus and presentation ligatures; explicit script structure.

    Case, punctuation, signs, units, negation and token order remain significant.
    Superscript/subscript runs equal their explicit braced forms; ASCII unbraced
    digits or a single letter after ^/_ are normalized to the same braced form.
    No NFKD/casefold, operator deletion, dehyphenation or algebraic equivalence.
    """
    text = unicodedata.normalize("NFC", text).replace("−", "-")
    text = "".join(unicodedata.normalize("NFKC", c) if "\ufb00" <= c <= "\ufb06" else c for c in text)
    pieces, index = [], 0
    while index < len(text):
        char = text[index]
        table = _SUPER if char in _SUPER else _SUB if char in _SUB else None
        if table is None:
            pieces.append(char)
            index += 1
            continue
        script = []
        while index < len(text) and text[index] in table:
            script.append(table[text[index]])
            index += 1
        pieces.append(("^" if table is _SUPER else "_") + "{" + "".join(script) + "}")
    # The terminal guard covers digits too: a failed match of ^12a must never
    # backtrack to ^1 and turn it into ^{1}2a. Ambiguous unbraced syntax stays
    # literal instead of inventing exponent ownership.
    text = re.sub(r"([\^_])\s*([0-9]+|[A-Za-z])(?![^\W_]|\.\d)", r"\1{\2}", "".join(pieces))
    # Compound operators are lexical units. In particular factorial followed by
    # equality (n! = m) cannot collapse into inequality (n != m).
    operators = r"<=>|!=|==|<=|>=|:=|->|<-|=>|&&|\|\||\+\+|--|\*\*|//|<<|>>"
    return re.findall(operators + r"|[^\W\d_]+|\d+(?:\.\d+)?|[^\s]", text, re.UNICODE)


def compare_notation(predicted: str, reference: str) -> dict:
    left, right = notation_tokens(predicted), notation_tokens(reference)
    return {"metric_version": FIDELITY_METRIC_VERSION,
            "status": "pass" if left == right else "fail",
            "exact_ordered_tokens": left == right,
            "predicted_tokens": len(left), "reference_tokens": len(right),
            "predicted_text_sha256": text_hash(predicted),
            "reference_text_sha256": text_hash(reference),
            "semantic_equivalence_claimed": False}


def _result(status: str, reason: str, **extra) -> dict:
    return {"status": status, "reason": reason, **extra}


def _attribution(review: dict, reference_text: str, evaluated_at: str | None) -> dict | None:
    if not isinstance(review, dict):
        return None
    try:
        timestamp = dt.datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
        evaluation = dt.datetime.fromisoformat(evaluated_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None or evaluation.tzinfo is None or timestamp > evaluation:
            return None
        if review.get("reviewer_kind") not in {"human", "assistant"} or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
            return None
        if review.get("reference_text_sha256") != text_hash(reference_text):
            return None
        if any(not isinstance(review.get(k), str) or not _HASH.fullmatch(review[k]) for k in ("source_sha256", "page_sha256")):
            return None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return {k: review[k] for k in ("reviewer", "reviewer_kind", "reviewed_at")}


def _dimension(review: dict, name: str) -> dict | None:
    value = review.get(name)
    if not isinstance(value, dict) or value.get("status") not in STATES or not isinstance(value.get("evidence_id"), str) or not value["evidence_id"].strip():
        return None
    return value


def _positions(spans: list[dict]) -> list[tuple]:
    if not isinstance(spans, list) or not spans:
        raise ValueError("source_spans_missing")
    points = []
    for span in spans:
        line = span.get("line_id")
        start, end = span.get("start"), span.get("end")
        if (isinstance(line, bool) or not isinstance(line, (str, int)) or not str(line) or
                span.get("page_no", 1) != 1 or type(start) is not int or type(end) is not int or
                not 0 <= start < end or len(points) + end - start > _MAX_POSITIONS):
            raise ValueError("invalid_source_spans")
        if "text" in span and (not isinstance(span["text"], str) or len(span["text"]) != end-start):
            raise ValueError("invalid_source_span_text_length")
        points.extend((str(line), i) for i in range(start, end))
    if len(set(points)) != len(points):
        raise ValueError("overlapping_source_spans")
    return points


def _image_regions(regions: list[dict], size: list[float]) -> list[tuple]:
    if not isinstance(size, list) or len(size) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in size):
        raise ValueError("invalid_image_page_size")
    if not isinstance(regions, list) or not regions:
        raise ValueError("image_regions_missing")
    result = []
    for region in regions:
        box = region.get("bbox", [])
        if (region.get("page_no") != 1 or region.get("coord_origin") != "TOPLEFT" or
                len(box) != 4 or any(type(x) not in (int, float) or not math.isfinite(x) for x in box)):
            raise ValueError("invalid_image_region")
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= size[0] and 0 <= y0 < y1 <= size[1]):
            raise ValueError("image_region_outside_page")
        result.append(tuple(box))
    if len(set(result)) != len(result):
        raise ValueError("duplicate_image_regions")
    return result


def _boundary(prediction: dict, dimension: dict) -> tuple[dict, dict, dict]:
    unresolved = _result("unresolved", "reviewed_source_boundaries_unavailable")
    if dimension["status"] != "pass":
        state = "not_applicable" if dimension["status"] == "not_applicable" else "unresolved"
        return _result(state, "reference_boundary_review_" + dimension["status"]), unresolved, unresolved
    if dimension.get("section_owner") != "abstract" or not dimension.get("closing_boundary"):
        return _result("unresolved", "reviewed_section_ownership_or_closure_missing"), unresolved, unresolved
    representation = dimension.get("representation")
    identity_key = "native_sha256" if representation == "native_spans" else "image_sha256"
    expected_hash = dimension.get(identity_key)
    if not isinstance(expected_hash, str) or not _HASH.fullmatch(expected_hash) or prediction.get(identity_key) != expected_hash:
        return _result("unresolved", "source_representation_not_bound"), unresolved, unresolved
    try:
        if representation == "native_spans":
            expected = _positions(dimension.get("reference_spans"))
            actual = _positions(prediction.get("spans"))
        elif representation == "image_regions":
            expected = _image_regions(dimension.get("reference_regions"), dimension.get("page_size"))
            actual = _image_regions(prediction.get("image_regions"), dimension.get("page_size"))
        else:
            raise ValueError("unknown_source_representation")
    except (TypeError, AttributeError, ValueError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) else "invalid_source_boundary_evidence"
        return _result("unresolved", reason), unresolved, unresolved
    actual_set, expected_set = set(actual), set(expected)
    extra, missing = actual_set - expected_set, expected_set - actual_set
    contamination = Counter()
    if representation == "native_spans":
        try:
            for excluded in dimension.get("excluded_spans", []):
                role = excluded["role"]
                if role not in {"footnote", "metadata", "body", "other"}:
                    raise ValueError("invalid_excluded_source_role")
                excluded_positions = set(_positions(excluded["spans"]))
                if expected_set & excluded_positions:
                    return (_result("unresolved", "reviewed_abstract_overlaps_excluded_source_role",
                                    conflicting_role=role), unresolved, unresolved)
                contamination[role] += len(actual_set & excluded_positions)
        except (KeyError, TypeError, AttributeError, ValueError):
            return _result("unresolved", "invalid_excluded_source_evidence"), unresolved, unresolved
    first = actual.index(expected[0]) if expected[0] in actual_set else None
    last = actual.index(expected[-1]) if expected[-1] in actual_set else None
    owner = prediction.get("section_owner")
    endpoints_match = actual[0] == expected[0] and actual[-1] == expected[-1]
    boundary_state = ("fail" if extra or missing or not endpoints_match or owner not in (None, "abstract") else
                      "unresolved" if owner is None else "pass")
    boundary = _result(boundary_state, "compared_reviewed_source_extent",
                       representation=representation, extra_source_positions=len(extra),
                       missing_source_positions=len(missing),
                       start_matches=actual[0] == expected[0], end_matches=actual[-1] == expected[-1],
                       extra_prefix_positions=sum(x in extra for x in actual[:first]) if first is not None else None,
                       extra_suffix_positions=sum(x in extra for x in actual[last+1:]) if last is not None else None,
                       contamination_by_role=dict(contamination), section_owner=owner)
    common_actual = [x for x in actual if x in expected_set]
    common_expected = [x for x in expected if x in actual_set]
    order = _result("fail" if common_actual != common_expected else "unresolved" if missing else "pass",
                    "compared_reviewed_source_order")
    location = _result("pass", "source_identity_and_representation_bound",
                       representation=representation, identity_sha256=expected_hash)
    return boundary, order, location


def evaluate_fidelity(prediction: dict, reference: dict, *, evaluated_at: str | None = None) -> dict:
    """Evaluate additive measures; missing or failed reference review is unresolved."""
    comparison = compare_notation(prediction.get("text", ""), reference["text"])
    unresolved = _result("unresolved", "missing_invalid_or_post_evaluation_fidelity_review")
    result = {"metric_version": FIDELITY_METRIC_VERSION, "notation_comparison": comparison,
              "notation": dict(unresolved), "boundary": dict(unresolved),
              "reading_order": dict(unresolved), "source_location": dict(unresolved),
              "review_attribution": None, "evaluated_at": evaluated_at, "verified_correct_proposal": False}
    review = reference.get("fidelity_review", {})
    attribution = _attribution(review, reference["text"], evaluated_at)
    if not attribution:
        return result
    result["review_attribution"] = attribution
    if any(prediction.get(k) != review[k] for k in ("source_sha256", "page_sha256")):
        for key in ("notation", "boundary", "reading_order", "source_location"):
            result[key] = _result("unresolved", "prediction_reference_source_identity_mismatch")
        return result
    notation = _dimension(review, "notation")
    if notation:
        if notation["status"] == "pass":
            result["notation"] = _result(comparison["status"], "compared_against_reviewed_transcription")
        elif notation["status"] == "not_applicable" and not (reference.get("math_review_required") or prediction.get("math_review_required")):
            result["notation"] = _result("not_applicable", "attributed_no_scientific_notation")
        else:
            result["notation"] = _result("unresolved", "reference_notation_review_" + notation["status"])
        result["notation"]["review_status"] = notation["status"]
        result["notation"]["evidence_id"] = notation["evidence_id"]
    boundary = _dimension(review, "boundary")
    if boundary:
        result["boundary"], result["reading_order"], result["source_location"] = _boundary(prediction, boundary)
        result["boundary"].update(review_status=boundary["status"], evidence_id=boundary["evidence_id"])
    result["verified_correct_proposal"] = bool(
        prediction.get("proposal") is True and prediction.get("status") == "complete" and
        prediction.get("complete_candidate") is True and reference["status"] == "complete" and
        comparison["status"] == "pass" and result["notation"]["status"] in {"pass", "not_applicable"} and
        all(result[k]["status"] == "pass" for k in ("boundary", "reading_order", "source_location")))
    return result


def fidelity_summary(details: list[dict]) -> dict:
    """Keep every input case and every unresolved state in explicit denominators."""
    def measure(name: str) -> dict:
        counts = Counter(d.get("fidelity", {}).get(name, {}).get("status", "unresolved") for d in details)
        eligible = counts["pass"] + counts["fail"]
        proposed_counts = Counter(d.get("fidelity", {}).get(name, {}).get("status", "unresolved") for d in details if d["proposed"])
        return {"states": {s: counts[s] for s in STATES}, "eligible_reviewed_cases": eligible,
                "pass_fraction_among_eligible": counts["pass"]/eligible if eligible else None,
                "proposed_states": {s: proposed_counts[s] for s in STATES}}
    complete = sum(d["gold"] == "complete" for d in details)
    proposed = sum(d["proposed"] for d in details)
    certified = sum(d.get("fidelity", {}).get("verified_correct_proposal", False) for d in details)
    def dimension_failed(row):
        return any(row.get("fidelity", {}).get(k, {}).get("status") == "fail"
                   for k in ("notation", "boundary", "reading_order"))
    def wrong_scope(row):
        return row["gold"] in {"partial", "partial_on_page_one", "absent", "no_abstract_text"}
    needs_review = [d["id"] for d in details if any(
        d.get("fidelity", {}).get(k, {}).get("status", "unresolved") == "unresolved"
        for k in ("notation", "boundary", "reading_order", "source_location"))]
    return {"metric_version": FIDELITY_METRIC_VERSION, "pages": len(details),
            "gold_states": dict(Counter(d["gold"] for d in details)),
            "complete_available": complete, "proposed": proposed,
            "verified_correct_proposals": certified,
            "verified_fraction_of_all_proposals": certified/proposed if proposed else None,
            "verified_complete_abstract_recall": certified/complete if complete else None,
            "not_verified_proposals": proposed-certified, "review_workload": len(needs_review),
            "reviewed_false_proposals": sum(d["proposed"] and (wrong_scope(d) or dimension_failed(d)) for d in details),
            "gold_scope_false_proposals": sum(d["proposed"] and wrong_scope(d) for d in details),
            "source_dimension_false_proposals": sum(d["proposed"] and dimension_failed(d) for d in details),
            "unresolved_case_ids": needs_review, "cases_without_fidelity_metrics": sum("fidelity" not in d for d in details),
            "notation": measure("notation"), "boundary": measure("boundary"),
            "reading_order": measure("reading_order"), "source_location": measure("source_location"),
            "notation_token_mismatch_cases": sum(d.get("fidelity", {}).get("notation_comparison", {}).get("status") == "fail" for d in details),
            "claim": "attributed evidence and conservative transcription comparison; independence not certified"}
