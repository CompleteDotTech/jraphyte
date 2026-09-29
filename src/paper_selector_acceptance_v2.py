"""Separate source-verified selector gate over an immutable v1 promotion audit.

The historical scorer and its FAIL result are retained verbatim. This module
replays that scorer, then applies the user-approved source-fidelity criterion.
It never authorizes graph writes or independent scientific qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from trace_gc.pdf_source_parallel_v4 import json_bytes
from trace_gc.pdf_structure_parallel_v4 import verify_assessment
from src.parallel_source_v4.common import child, data_root, digest, verify_files, write_once
from src.parallel_source_v4.fidelity_report import read_bound
from src.parallel_source_v4.promotion import CASE_IDS, METHODS, PRIMARY, VERSION as BASE_VERSION
from src.parallel_source_v4.promotion_io import _analyze
from src.parallel_source_v4.runtime import DEFAULT_RUNTIME_LOCK

VERSION = "paper-selector-source-verified-acceptance-v2"
POLICY_VERSION = "paper-selector-source-verified-policy-v2"
LEGACY_EXCEPTIONS = frozenset({"preserve_91", "zero_false_primary_proposals"})
DIMENSIONS = frozenset({"notation", "boundary", "reading_order", "source_location"})
REQUIRED_BASE_GATES = frozenset({"provenance", "saved_v2_replay", "preserve_91",
    "zero_false_primary_proposals", "reviewed_fidelity", "original_source_outcomes",
    "f195_reviewed_boundary", "image_route"})
SHA = re.compile(r"[0-9a-f]{64}\Z")
QUALITY_DENIALS = frozenset({"nonlegacy_base_gate_failed", "legacy_blocked_gate_cannot_be_reclassified",
    "source_false_or_unverified_proposal", "source_verified_original_91_not_preserved",
    "no_source_verified_proposals", "trusted_verified_correct_count_or_ids_mismatch",
    "all_200_image_route_audit_required", "frozen_gold_counts_changed"})


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _descriptor(value: object, reason: str) -> dict:
    _require(isinstance(value, dict) and set(value) == {"relative", "sha256"}
             and isinstance(value["relative"], str) and bool(value["relative"])
             and isinstance(value["sha256"], str) and SHA.fullmatch(value["sha256"]) is not None, reason)
    return value


def _bound(root: Path, descriptor: dict, reason: str) -> dict:
    value, actual = read_bound(child(root, descriptor["relative"]))
    _require(actual == descriptor["sha256"], reason)
    return value


def _code_identity() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _base_readback(root: Path, descriptor: dict, *, configuration_relative: str,
                   source_map_relative: str, runtime_lock: Path) -> dict:
    base = _bound(root, descriptor, "base_acceptance_hash_mismatch")
    _require(isinstance(base, dict) and base.get("version") == BASE_VERSION,
             "authentic_v1_acceptance_required")
    invocation = base.get("invocation")
    _require(isinstance(invocation, dict) and invocation.get("configuration_relative") == configuration_relative
             and invocation.get("source_map_relative") == source_map_relative,
             "base_invocation_configuration_or_source_map_mismatch")
    derived = base.get("derived_assessments")
    outputs = base.get("derived_assessment_files_sha256")
    _require(isinstance(derived, dict) and isinstance(outputs, dict)
             and set(outputs) == {"reviewed-assessments/" + sid + ".json" for sid in derived}
             and not set(derived) - CASE_IDS, "invalid_base_derived_output_manifest")
    directory = child(root, descriptor["relative"]).parent
    for sid, expected in derived.items():
        relative = "reviewed-assessments/" + sid + ".json"
        value, actual = read_bound(child(directory, relative))
        _require(actual == outputs[relative] and value == expected,
                 "base_derived_output_changed")
        verify_assessment(value)
    replay = _analyze(root, **invocation, evaluated_at=base["evaluated_at"], runtime_lock=runtime_lock)
    _require(replay == base, "base_acceptance_replay_mismatch")
    verify_files(directory, outputs)
    _require(digest(child(root, descriptor["relative"])) == descriptor["sha256"],
             "base_acceptance_changed_during_readback")
    return replay


def _source_gate(base: dict) -> dict:
    gates = base.get("gates")
    _require(isinstance(gates, dict) and REQUIRED_BASE_GATES <= set(gates), "base_gates_missing")
    failures = {name for name, value in gates.items() if value.get("status") != "PASS"}
    _require(failures <= LEGACY_EXCEPTIONS, "nonlegacy_base_gate_failed")
    _require(all(gates[name]["status"] == "FAIL" for name in failures),
             "legacy_blocked_gate_cannot_be_reclassified")
    _require(base.get("status") == ("FAIL" if failures else "PASS")
             and base.get("eligible_for_reviewed_selector_release") is (not failures),
             "base_aggregate_or_eligibility_mismatch")
    _require(base.get("graph_admission_enabled") is False
             and base.get("production_graph_writes") == 0
             and base.get("automatic_fallback_enabled") is False,
             "base_graph_or_fallback_must_remain_disabled")
    arms = base.get("arms")
    _require(isinstance(arms, dict) and set(arms) == set(METHODS), "all_four_arms_required")
    _require(all(isinstance(arm, dict) for arm in arms.values()), "all_four_arm_metrics_required")
    cases = base.get("cases")
    _require(isinstance(cases, dict) and set(cases) == set(METHODS), "all_four_case_rows_required")
    for name, arm in cases.items():
        _require(isinstance(arm, list) and len(arm) == 200
                 and {row.get("id") for row in arm} == CASE_IDS,
                 "all_200_case_rows_required")
    primary = {row["id"]: row for row in cases[PRIMARY]}
    counts = {gold: sum(row["gold"] == gold for row in primary.values())
              for gold in ("complete", "partial_on_page_one", "no_abstract_text")}
    _require(counts == {"complete": 111, "partial_on_page_one": 7, "no_abstract_text": 82},
             "frozen_gold_counts_changed")
    selected = {sid for sid, row in primary.items() if row["proposed"] is True}
    _require(bool(selected), "no_source_verified_proposals")
    _require(gates["reviewed_fidelity"].get("proposed") == len(selected)
             and gates["reviewed_fidelity"].get("failed_ids") == []
             and gates["reviewed_fidelity"].get("unresolved_ids") == [],
             "trusted_verified_correct_count_or_ids_mismatch")
    for sid in selected:
        row = primary[sid]
        _require(row["gold"] == "complete" and row["predicted"] == "complete"
                 and row["conversion_status"] == "success"
                 and isinstance(row.get("review_dimensions"), dict)
                 and set(row["review_dimensions"]) == DIMENSIONS
                 and all(row["review_dimensions"][dim] == "pass" for dim in DIMENSIONS),
                 "source_false_or_unverified_proposal")
    old = gates["preserve_91"].get("original_correct_ids")
    _require(isinstance(old, list) and len(old) == 91 and len(set(old)) == 91
             and set(old) <= CASE_IDS and set(old) <= selected,
             "source_verified_original_91_not_preserved")
    _require(base.get("image_review", {}).get("enabled") is True
             and base.get("image_review", {}).get("count", 0) > 0,
             "all_200_image_route_audit_required")
    _require(base.get("postrun_source_code_runtime_recheck") == "PASS"
             and base.get("independent_qualification") is False,
             "source_recheck_or_review_attribution_invalid")
    return {"status": "PASS", "selected_source_verified_count": len(selected),
            "selected_source_verified_ids": sorted(selected),
            "original_91_included": True, "gold_counts": counts,
            "all_four_arms_case_count": {name: len(arm) for name, arm in cases.items()},
            "legacy_failed_gate_names": sorted(failures)}


def assess(root: Path, *, policy_relative: str, policy_sha256: str,
           configuration_relative: str, source_map_relative: str,
           runtime_lock: Path = DEFAULT_RUNTIME_LOCK) -> dict:
    code_before = _code_identity()
    _require(isinstance(policy_sha256, str) and SHA.fullmatch(policy_sha256) is not None,
             "externally_pinned_source_policy_sha256_required")
    policy_descriptor = {"relative": policy_relative, "sha256": policy_sha256}
    policy = _bound(root, _descriptor(policy_descriptor, "policy_descriptor_required"), "policy_hash_mismatch")
    _require(isinstance(policy, dict) and set(policy) == {"version", "approval", "base_acceptance", "configuration", "source_map"}
             and policy["version"] == POLICY_VERSION, "exact_source_verified_policy_required")
    approval = _descriptor(policy["approval"], "externally_pinned_user_approval_required")
    approved = _bound(root, approval, "approval_artifact_hash_mismatch")
    _require(isinstance(approved, dict)
             and approved.get("version") == "user-approved-source-verified-gate-amendment-v1"
             and approved.get("approval") == "Approve source-verified gate; preserve legacy results"
             and approved.get("automatic_fallback_authorized") is False
             and approved.get("graph_admission_authorized") is False
             and approved.get("scope") == ("Source-verified preservation of all 91 original IDs and zero source-false selected proposals; "
                 "every selected proposal must pass original-source notation, boundary, reading order and location. "
                 "Retain unchanged legacy scorer, historical references, scores and failures; "
                 "no silent glyph folding, threshold or ID exemption."),
             "user_approved_source_policy_scope_required")
    base_descriptor = _descriptor(policy["base_acceptance"], "base_descriptor_required")
    config_descriptor = _descriptor(policy["configuration"], "configuration_descriptor_required")
    map_descriptor = _descriptor(policy["source_map"], "source_map_descriptor_required")
    _require(config_descriptor["relative"] == configuration_relative
             and map_descriptor["relative"] == source_map_relative,
             "policy_configuration_or_source_map_mismatch")
    _bound(root, config_descriptor, "configuration_hash_mismatch")
    _bound(root, map_descriptor, "source_map_hash_mismatch")
    base = _base_readback(root, base_descriptor, configuration_relative=configuration_relative,
                          source_map_relative=source_map_relative, runtime_lock=runtime_lock)
    source = _source_gate(base)
    result = {"version": VERSION, "status": "PASS", "eligible_for_source_verified_selector_release": True,
              "eligible_for_reviewed_selector_release": base["eligible_for_reviewed_selector_release"],
              "graph_admission_enabled": False, "production_graph_writes": 0,
              "automatic_fallback_enabled": False, "new_paid_api_calls": 0,
              "independent_human_qualification": False, "release_selection_performed": False,
              "policy": policy_descriptor, "policy_version": POLICY_VERSION,
              "approval": approval, "base_acceptance": base_descriptor,
              "configuration": config_descriptor, "source_map": map_descriptor,
              "source_verified_gate": source, "legacy_base_status": base["status"],
              "legacy_base_gates": base["gates"], "legacy_base_scope": base["scope"],
              "legacy_base_arms": base["arms"], "legacy_base_fallback_increment": base["fallback_increment"],
              "base_method_hashes": base["method_hashes"], "base_image_code_sha256": base["image_code_sha256"],
              "base_runtime": base["runtime"], "base_input_manifest_sha256": base["input_manifest_sha256"],
              "base_derived_assessment_files_sha256": base["derived_assessment_files_sha256"],
              "code_sha256": code_before}
    _require(digest(child(root, policy_relative)) == policy_sha256
             and digest(child(root, approval["relative"])) == approval["sha256"]
             and digest(child(root, config_descriptor["relative"])) == config_descriptor["sha256"]
             and digest(child(root, map_descriptor["relative"])) == map_descriptor["sha256"]
             and _code_identity() == code_before,
             "source_policy_inputs_changed_during_assessment")
    return result


def publish(root: Path, output_relative: str, result: dict, *, policy_relative: str,
            policy_sha256: str, configuration_relative: str, source_map_relative: str,
            runtime_lock: Path = DEFAULT_RUNTIME_LOCK) -> str:
    _require(result == assess(root, policy_relative=policy_relative, policy_sha256=policy_sha256,
                              configuration_relative=configuration_relative,
                              source_map_relative=source_map_relative, runtime_lock=runtime_lock),
             "source_policy_changed_before_publication")
    output = child(root, output_relative)
    _require(output != root and not output.exists() and output_relative.startswith("validation_v3_private/"),
             "new_private_source_gate_output_required")
    return write_once(output / "source-verified-acceptance.json", result)


def verify(root: Path, receipt_relative: str, expected_sha256: str, *, policy_relative: str,
           policy_sha256: str, configuration_relative: str, source_map_relative: str,
           runtime_lock: Path = DEFAULT_RUNTIME_LOCK) -> dict:
    receipt = _bound(root, _descriptor({"relative": receipt_relative, "sha256": expected_sha256},
                                      "externally_pinned_v2_receipt_required"), "v2_receipt_hash_mismatch")
    _require(isinstance(receipt, dict) and receipt.get("version") == VERSION and receipt.get("status") == "PASS",
             "passing_v2_source_verified_receipt_required")
    replay = assess(root, policy_relative=policy_relative, policy_sha256=policy_sha256,
                    configuration_relative=configuration_relative,
                    source_map_relative=source_map_relative, runtime_lock=runtime_lock)
    _require(receipt == replay and digest(child(root, receipt_relative)) == expected_sha256,
             "v2_source_verified_receipt_replay_mismatch")
    return {"status": "PASS", "acceptance_version": VERSION, "acceptance_sha256": expected_sha256,
            "policy_sha256": policy_sha256, "source_verified_original_91_included": True,
            "legacy_base_status": replay["legacy_base_status"],
            "graph_admission_enabled": False, "production_graph_writes": 0,
            "automatic_fallback_enabled": False, "new_paid_api_calls": 0,
            "release_selection_performed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("assess", "verify"))
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--source-map", required=True)
    parser.add_argument("--runtime-lock", type=Path, default=DEFAULT_RUNTIME_LOCK)
    parser.add_argument("--output")
    parser.add_argument("--receipt")
    parser.add_argument("--receipt-sha256")
    args = parser.parse_args()
    if args.stage == "assess" and not args.output:
        parser.error("assess requires --output")
    if args.stage == "verify" and (not args.receipt or not args.receipt_sha256):
        parser.error("verify requires --receipt and --receipt-sha256")
    try:
        root = data_root(args.data_root)
        common = dict(policy_relative=args.policy, policy_sha256=args.policy_sha256,
                      configuration_relative=args.configuration, source_map_relative=args.source_map,
                      runtime_lock=args.runtime_lock)
        if args.stage == "assess":
            result = assess(root, **common)
            sha = publish(root, args.output, result, **common)
            print(json.dumps({"status": result["status"], "version": VERSION,
                              "receipt_relative": args.output + "/source-verified-acceptance.json",
                              "receipt_sha256": sha, "legacy_base_status": result["legacy_base_status"]}, sort_keys=True))
        else:
            print(json.dumps(verify(root, args.receipt, args.receipt_sha256, **common), sort_keys=True))
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError) as error:
        reason = str(error) if type(error) is ValueError and str(error) in QUALITY_DENIALS else "invalid_or_stale_source_verified_evidence"
        status = "FAIL" if reason in QUALITY_DENIALS else "BLOCKED"
        print(json.dumps({"version": VERSION, "status": status, "reason": reason,
                          "eligible_for_source_verified_selector_release": False,
                          "automatic_fallback_enabled": False, "graph_admission_enabled": False,
                          "new_paid_api_calls": 0, "production_graph_writes": 0}, sort_keys=True))
        return 1 if status == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
