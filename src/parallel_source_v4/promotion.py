"""Strict development-corpus acceptance; no source, release or graph authority.

The file adapter proves artifact identity. These pure checks deliberately do not
turn caller-supplied scores or public synthetic fixtures into real evidence.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import re

from trace_gc.pdf_source_parallel_v4 import digest_value
from .extraction import METHODS
from .metrics import ABSENT, PARTIAL, fallback_increment, summary

VERSION = "selector-promotion-v1"
CASE_IDS = frozenset(f"f{i:03}" for i in range(1, 201))
PRIMARY = "parallel_structure_v4"
CONFIGURATION = {
    "version": "selector-promotion-configuration-v1",
    "selected_primary": PRIMARY,
    "measured_methods": list(METHODS),
    "physical_page": 1,
    "native_mode": "fresh",
    "fallback_policy": "disabled",
    "image_evidence_policy": "excluded",
    "manual_closure_policy": "source-bound-attributed-review-v1",
    "source_admission": "separate_review_required",
    "graph_admission": "disabled",
}
IMAGE_CONFIGURATION = {**CONFIGURATION, "image_evidence_policy": "source-bound-attributed-image-review-v1"}
FAILED_NATIVE_IMAGE_CONFIGURATION = {
    **IMAGE_CONFIGURATION, "native_failure_policy": "source-bound-failed-native-image-replacement-v1"}


def configuration(value: dict) -> dict:
    # Python's True == 1 must not allow a malformed physical-page setting.
    if not isinstance(value, dict) or digest_value(value) not in {
            digest_value(CONFIGURATION), digest_value(IMAGE_CONFIGURATION), digest_value(FAILED_NATIVE_IMAGE_CONFIGURATION)}:
        raise ValueError("unsupported_promotion_configuration")
    return deepcopy(value)


def gate(status: str, reason: str, **evidence) -> dict:
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        raise ValueError("invalid_acceptance_gate_status")
    return {"status": status, "reason": reason, **evidence}


def aggregate_status(gates: dict) -> str:
    states = [value["status"] for value in gates.values()]
    return "FAIL" if "FAIL" in states else "BLOCKED" if not states or "BLOCKED" in states else "PASS"


def _rows(values: list[dict]) -> dict[str, dict]:
    if not isinstance(values, list):
        raise ValueError("case_rows_required")
    ids = [row["id"] for row in values]
    if len(ids) != len(set(ids)) or set(ids) != CASE_IDS:
        raise ValueError("all_200_unique_original_case_ids_required")
    for row in values:
        if type(row["proposed"]) is not bool:
            raise ValueError("typed_proposal_state_required")
        if row["gold"] not in {"complete", *ABSENT, *PARTIAL}:
            raise ValueError("unsupported_reference_state")
    counts = Counter("complete" if x["gold"] == "complete" else "partial" if x["gold"] in PARTIAL else "absent"
                     for x in values)
    if counts != {"complete": 111, "partial": 7, "absent": 82}:
        raise ValueError("frozen_reference_denominators_required")
    return {row["id"]: row for row in values}


def _legacy_correct(row: dict) -> bool:
    return row["proposed"] and row["gold"] == "complete" and row["text_match_98"] is True


def _boundary_correct(row: dict) -> bool:
    return _legacy_correct(row) and row["boundary_and_98_match"] is True


def _fidelity_gate(rows: list[dict]) -> dict:
    failed, unresolved = [], []
    for row in rows:
        if not row["proposed"]:
            continue
        fidelity = row.get("fidelity", {})
        dimensions = [fidelity.get(k, {}).get("status", "unresolved")
                      for k in ("boundary", "reading_order", "source_location", "notation")]
        if "fail" in dimensions:
            failed.append(row["id"])
        elif fidelity.get("verified_correct_proposal") is not True:
            unresolved.append(row["id"])
    return gate("FAIL" if failed else "BLOCKED" if unresolved else "PASS",
                "reviewed_source_fidelity_for_every_proposal", failed_ids=failed,
                unresolved_ids=unresolved, proposed=sum(r["proposed"] for r in rows))


def evaluate(details: dict[str, list[dict]], baseline: list[dict], replay: list[dict],
             *, provenance_verified: bool = False) -> dict:
    """Recompute gates from case rows; only the IO audit may assert provenance.

    This internal arithmetic is testable with authored rows. Its default evidence
    scope is BLOCKED, so an otherwise green synthetic case table cannot promote.
    """
    if set(details) != set(METHODS):
        raise ValueError("all_four_measured_arms_required")
    indexed = {name: _rows(rows) for name, rows in details.items()}
    old = _rows(baseline)
    primary = indexed[PRIMARY]
    if any(row["gold"] != old[sid]["gold"] for arm in indexed.values() for sid, row in arm.items()):
        raise ValueError("reference_scope_changed_between_arms")
    replay_ids = [row["id"] for row in replay]
    if len(replay_ids) != len(set(replay_ids)) or set(replay_ids) != CASE_IDS:
        raise ValueError("all_200_historical_replays_required")
    replay_failed = [row["id"] for row in replay if any(row.get(k) is not True for k in
                     ("same_text", "same_status", "same_proposal", "same_assessment_digest"))]
    original = {sid for sid, row in old.items() if _legacy_correct(row)}
    current = {sid for sid, row in primary.items() if _legacy_correct(row)}
    gates = {
        "provenance": gate("PASS" if provenance_verified is True else "BLOCKED",
                           "real_frozen_corpus_artifact_audit_required"),
        "saved_v2_replay": gate("FAIL" if replay_failed else "PASS", "exact_saved_v2_replay",
                                failed_ids=sorted(replay_failed), cases=len(replay)),
        "preserve_91": gate("PASS" if len(original) == 91 and original <= current else "FAIL",
                            "original_success_id_set_inclusion", original_correct_ids=sorted(original),
                            lost_correct_ids=sorted(original-current), gained_correct_ids=sorted(current-original)),
    }
    false = sorted(sid for sid, row in primary.items() if row["proposed"] and not _boundary_correct(row))
    gates["zero_false_primary_proposals"] = gate("FAIL" if false else "PASS",
        "complete_scope_text98_and_boundary_required", failed_ids=false)
    gates["reviewed_fidelity"] = _fidelity_gate(details[PRIMARY])
    expected_complete = ("f030", "f192", "f119", "f150")
    failures = [sid for sid in expected_complete if not _boundary_correct(primary[sid])]
    if primary["f199"]["gold"] not in ABSENT or primary["f199"]["proposed"]:
        failures.append("f199")
    gates["original_source_outcomes"] = gate("FAIL" if failures else "PASS",
        "original_errors_require_complete_abstracts_or_author_list_abstention", failed_ids=failures)
    footnote = primary["f195"]
    boundary_state = footnote.get("fidelity", {}).get("boundary", {}).get("status", "unresolved")
    gates["f195_reviewed_boundary"] = gate(
        "FAIL" if not _boundary_correct(footnote) or boundary_state == "fail" else
        "PASS" if boundary_state == "pass" else "BLOCKED",
        "reviewed_abstract_extent_without_footnote_required", case_id="f195")
    per_arm = {}
    for name, rows in details.items():
        indexed_arm = indexed[name]
        bad = sorted(sid for sid, row in indexed_arm.items() if row["proposed"] and not _boundary_correct(row))
        per_arm[name] = {
            "selection": "primary" if name == PRIMARY else "diagnostic_only",
            "false_proposal_ids": bad,
            "fidelity": _fidelity_gate(rows),
            "f039": {"proposed": indexed_arm["f039"]["proposed"],
                     "boundary_and_text98_correct": _boundary_correct(indexed_arm["f039"]),
                     "predicted": indexed_arm["f039"]["predicted"]},
            "reasons": dict(Counter(reason if isinstance(reason, str) and re.fullmatch(r"[a-z0-9_]+", reason)
                                    else "redacted_reason" for row in rows for reason in row.get("reasons", []))),
            "metrics": summary(rows),
        }
    status = aggregate_status(gates)
    return {"version": VERSION, "status": status, "gates": gates, "arms": per_arm,
            "fallback_increment": {name: fallback_increment(details[PRIMARY], details[name])
                                   for name in METHODS if name != PRIMARY},
            "eligible_for_reviewed_selector_release": status == "PASS",
            "automatic_fallback_enabled": False, "graph_admission_enabled": False,
            "new_paid_api_calls": 0, "production_graph_writes": 0,
            "scope": "previously_examined_development_regression_not_independent_qualification"}


def redacted_cases(details: dict[str, list[dict]]) -> dict:
    """No source text, reviewer notes, private filenames or untrusted reason strings."""
    fields = ("gold", "predicted", "proposed", "conversion_status", "text_match_98", "boundary_and_98_match")
    return {name: [{"id": row["id"], **{key: row[key] for key in fields},
                   "review_dimensions": {key: row.get("fidelity", {}).get(key, {}).get("status", "unresolved")
                                         for key in ("notation", "boundary", "reading_order", "source_location")}}
                  for row in rows] for name, rows in details.items()}
