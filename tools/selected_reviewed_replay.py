"""Opt-in, source-bound replay of signed native-only abstract reviews.

The private map is an application-owned input under the data root. It contains
paths and public reviewer keys, never source text. Its file digest is recorded
in the derived receipt. Nothing here writes to graph or frozen corpus paths.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from trace_gc.pdf_source_parallel_v4 import digest_value, source_lines
from trace_gc.pdf_structure_parallel_v4 import verify_assessment
from trace_gc.reviewed_abstract_overlay import apply_reviewed_abstract
from trace_gc.trust import IssuerPolicy, TrustStore
from src.parallel_source_v4.common import REPO, child, method_hashes, read_hashed_json, verify_files, write_once, within
from src.parallel_source_v4.extraction import MATH_HOLDS, METHODS
from src.parallel_source_v4.metrics import fallback_increment, score_case, summary
from src.parallel_source_v4.runtime import DEFAULT_RUNTIME_LOCK, runtime_receipt


def _bytes(root: Path, relative: str) -> bytes:
    return child(root, relative).read_bytes()


def _json(root: Path, relative: str) -> dict:
    return json.loads(_bytes(root, relative))


def _hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _same(actual, expected, reason: str) -> None:
    if actual != expected:
        raise ValueError(reason)


def _trust(reviewers: list[dict]) -> TrustStore:
    if len(reviewers) != 2:
        raise ValueError("two_reviewers_required")
    trust = TrustStore()
    issuers = set()
    principals = set()
    for row in reviewers:
        if set(row) != {"issuer", "principal", "public_key_base64", "reviewer_kind"}:
            raise ValueError("reviewer_enrollment_shape_invalid")
        if row["reviewer_kind"] not in {"human", "assistant"}:
            raise ValueError("reviewer_kind_invalid")
        issuers.add(row["issuer"])
        principals.add(row["principal"])
        key = base64.b64decode(row["public_key_base64"], validate=True)
        trust.enroll(row["issuer"], IssuerPolicy(key, row["principal"],
            frozenset({"OBSERVATION"}), frozenset(), frozenset(), frozenset(), can_review=True))
    if len(issuers) != 2 or len(principals) != 2:
        raise ValueError("distinct_reviewers_required")
    return trust


def _receipt_enrollment_match(reviewers: list[dict], receipts: list[dict]) -> None:
    if len(receipts) != len(reviewers) or any(
        receipt.get("issuer") != reviewer["issuer"] or
        receipt.get("payload", {}).get("reviewer_kind") != reviewer["reviewer_kind"]
        for reviewer, receipt in zip(reviewers, receipts)
    ):
        raise ValueError("review_receipt_enrollment_mismatch")


def _reverify_receipts(trust: TrustStore, receipts: list[dict]) -> None:
    """A receipt valid during application must still be live at publication."""
    for receipt in receipts:
        trust.verify(receipt, "OBSERVATION")


def _bind_frozen_inputs(root: Path, gate: dict, labels_relative: str,
                        source_map: dict) -> None:
    """Tie externally supplied labels and every original path to the run gate."""
    labels_path = "validation_expanded200/labels.json"
    if labels_relative != labels_path:
        raise ValueError("frozen_labels_path_required")
    hashes = gate.get("input_file_hashes", {})
    if _hash(_bytes(root, labels_path)) != hashes.get(labels_path):
        raise ValueError("frozen_labels_hash_mismatch")
    verified = gate.get("verified_sources")
    if not isinstance(verified, list) or len(verified) != 200:
        raise ValueError("gate_verified_sources_incomplete")
    by_id = {item["id"]: item for item in verified}
    if len(by_id) != 200 or set(source_map) != set(by_id):
        raise ValueError("source_map_cohort_mismatch")
    for sid, relative in source_map.items():
        path = child(root, relative)
        canonical = path.relative_to(root).as_posix()
        if canonical != relative or not relative.endswith(".pdf"):
            raise ValueError("source_map_path_invalid")
        expected = by_id[sid]["source_sha256"]
        if hashes.get(relative) != expected or _hash(path.read_bytes()) != expected:
            raise ValueError("source_map_gate_binding_mismatch")


def _output_target(root: Path, output: str, baseline_relative: str) -> Path:
    target = child(root, output)
    private_parent = child(root, "validation_v3_private")
    if target.parent != private_parent or target.exists() or target.is_relative_to(child(root, baseline_relative)):
        raise ValueError("new_private_output_directory_required")
    return target


def _historical_correct(root: Path, gate: dict, labels: dict, result: dict) -> set[str]:
    """Recompute the original v2 text98 set from gate-pinned saved predictions."""
    old_details = []
    for sid in labels:
        relative = f"validation_expanded200/assessments/structure_v2/{sid}.json"
        payload = _bytes(root, relative)
        if _hash(payload) != gate["input_file_hashes"].get(relative):
            raise ValueError("historical_assessment_not_gate_pinned")
        prediction = json.loads(payload)
        adapted = {**prediction, "proposal": prediction.get("eligible_for_jev", False),
                   "eligible_for_jev": False}
        old_details.append(score_case(sid, adapted, labels[sid]))
    old_good = {row["id"] for row in old_details
                if row["proposed"] and row["gold"] == "complete" and row["text_match_98"]}
    if len(old_good) != 91:
        raise ValueError("historical_91_not_reproduced")
    _same(summary(old_details), result.get("v2_baseline"), "historical_baseline_summary_mismatch")
    current_good = {row["id"] for row in result["details"]["parallel_structure_v4"]
                    if row["proposed"] and row["gold"] == "complete" and row["text_match_98"]}
    expected = {"status": "PASS" if old_good <= current_good else "FAIL",
                "old_correct": 91, "lost_correct_ids": sorted(old_good - current_good)}
    _same(result.get("preserve_91_gate"), expected, "historical_preservation_gate_mismatch")
    return old_good


def _baseline(root: Path, repo: Path, baseline_relative: str, source_map: dict,
              labels: dict) -> tuple[dict, dict[str, dict[str, dict]], str, set[str]]:
    baseline_dir = child(root, baseline_relative)
    if not baseline_dir.is_dir():
        raise ValueError("completed_baseline_required")
    result_bytes = (baseline_dir / "results.json").read_bytes()
    result = json.loads(result_bytes)
    gate = _json(baseline_dir, "preflight.json")
    if gate.get("status") != "PASS" or gate.get("source_geometry_policy") != "source_fraction_v1":
        raise ValueError("baseline_preflight_not_qualified")
    if (result.get("cohort") != "regression200" or result.get("source_geometry_policy") != "source_fraction_v1"
            or result.get("saved_replay_gate", {}).get("status") != "PASS"
            or result.get("status") not in {"FAILED_REGRESSION_PRESERVATION_GATE", "COMPLETE_OFFLINE_ASSESSMENT_NOT_QUALIFICATION"}
            or result.get("experiment_sha256") != digest_value(gate)):
        raise ValueError("baseline_identity_or_completion_invalid")
    _same(method_hashes(repo), gate["method_hashes"], "baseline_code_drift")
    _same(runtime_receipt(DEFAULT_RUNTIME_LOCK), gate["runtime"], "baseline_runtime_drift")
    verify_files(root, gate["input_file_hashes"])
    verify_files(repo, gate["repository_input_hashes"])
    if set(source_map) != set(labels) or len(labels) != 200:
        raise ValueError("cohort_identity_invalid")
    expected = {f"assessments/{method}/{sid}.json" for method in METHODS for sid in labels}
    hashes = result.get("assessment_files_sha256", {})
    if set(hashes) != expected or len(hashes) != 800 or set(result.get("details", {})) != set(METHODS):
        raise ValueError("complete_800_assessment_baseline_required")
    automatic = {method: {} for method in METHODS}
    for method in METHODS:
        rows = result["details"][method]
        if len(rows) != 200 or {row["id"] for row in rows} != set(labels):
            raise ValueError("baseline_score_rows_incomplete")
        scored = {row["id"]: row for row in rows}
        for sid in labels:
            rel = f"assessments/{method}/{sid}.json"
            payload = _bytes(baseline_dir, rel)
            _same(_hash(payload), hashes[rel], "baseline_assessment_file_drift")
            prediction = json.loads(payload)
            verify_assessment(prediction)
            automatic[method][sid] = prediction
            reference = {**labels[sid], "math_review_required":
                         labels[sid].get("math_review_required", False) or sid in MATH_HOLDS}
            _same(score_case(sid, prediction, reference), scored[sid], "baseline_score_mismatch")
        _same(summary(rows), result["metrics"][method], "baseline_metric_mismatch")
    old_good = _historical_correct(root, gate, labels, result)
    return result, automatic, _hash(result_bytes), old_good


def selected_replay(*, root: Path, repo: Path, review_map: str, output: str) -> dict:
    """Verify full baseline and only configured reviews, then seal derived scores."""
    import fitz

    root, repo = Path(root).resolve(), Path(repo).resolve()
    if root == repo or repo in root.parents:
        raise ValueError("private_data_root_must_be_external")
    runner_hash = _hash(Path(__file__).read_bytes())
    map_bytes = _bytes(root, review_map)
    config = json.loads(map_bytes)
    if set(config) != {"schema_version", "baseline", "source_map", "labels", "reviewers", "cases"} or config["schema_version"] != 1:
        raise ValueError("selected_review_map_shape_invalid")
    source_map_bytes = _bytes(root, config["source_map"])
    source_map = json.loads(source_map_bytes)
    labels = _json(root, config["labels"])
    preflight_relative = f'{config["baseline"]}/preflight.json'
    preflight_bytes = _bytes(root, preflight_relative)
    gate = json.loads(preflight_bytes)
    _bind_frozen_inputs(root, gate, config["labels"], source_map)
    baseline, automatic, baseline_hash, old_good = _baseline(root, repo, config["baseline"], source_map, labels)
    trust = _trust(config["reviewers"])
    cases = config["cases"]
    if not cases or not set(cases) <= set(labels):
        raise ValueError("reviewed_ids_outside_frozen_cohort")
    reviewed = {}
    bindings = {}
    reviewed_file_hashes: dict[str, str] = {}
    signed_receipts: list[dict] = []
    for sid, entry in sorted(cases.items()):
        if set(entry) != {"source_pdf", "page_pdf", "page_image", "notation", "tex", "manifest", "reviews", "converter_assets"}:
            raise ValueError("review_case_shape_invalid")
        _same(entry["source_pdf"], source_map[sid], "review_source_map_mismatch")
        frozen = "validation_v2" if int(sid[1:]) <= 100 else "validation_expanded200"
        _same(entry["page_pdf"], f"{frozen}/pages/{sid}/page.pdf", "review_frozen_page_mismatch")
        expected_converter = {"docling_status": f"{frozen}/docling/{sid}.json",
                              "docling_document": f"{frozen}/docling/{sid}.document.json",
                              "grobid": f"{frozen}/grobid/{sid}.json"}
        _same(entry["converter_assets"], expected_converter, "review_converter_map_mismatch")
        if len(entry["reviews"]) != 2 or len(set(entry["reviews"])) != 2:
            raise ValueError("two_distinct_review_receipts_required")
        for relative in (entry["source_pdf"], entry["page_pdf"], entry["page_image"],
                         entry["notation"], entry["tex"], entry["manifest"],
                         *entry["reviews"], *entry["converter_assets"].values()):
            digest = _hash(_bytes(root, relative))
            if relative in reviewed_file_hashes and reviewed_file_hashes[relative] != digest:
                raise ValueError("review_asset_changed_during_run")
            reviewed_file_hashes[relative] = digest
        manifest_bytes = _bytes(root, entry["manifest"])
        manifest = json.loads(manifest_bytes)
        if manifest.get("decision") != "reviewed_legacy_proposal":
            raise ValueError("only_native_legacy_proposal_supported")
        source = _bytes(root, entry["source_pdf"])
        with fitz.open(stream=source, filetype="pdf") as pdf:
            native = source_lines(pdf[0])
        receipts = [_json(root, path) for path in entry["reviews"]]
        _receipt_enrollment_match(config["reviewers"], receipts)
        signed_receipts.extend(receipts)
        code_names = set(manifest["identity"]["code_sha256"]) - {"reviewed_abstract_overlay.py"}
        allowed = {"trace_gc/pdf_source_parallel_v4.py", "trace_gc/pdf_structure_parallel_v4.py",
                   "trace_gc/pdf_notation_parallel_v4.py", "src/parallel_source_v4/extraction.py",
                   "src/parallel_source_v4/adapters.py", "src/parallel_source_v4/common.py",
                   "src/parallel_source_v4/metrics.py", "src/parallel_source_v4/runtime.py"}
        _same(code_names, allowed, "review_code_inventory_invalid")
        code = {name: child(repo, name).read_bytes() for name in code_names}
        result = apply_reviewed_abstract(
            automatic=automatic["parallel_structure_v4"][sid], manifest=manifest,
            first_review=receipts[0], second_review=receipts[1], trust=trust,
            source_pdf=source, page_pdf=_bytes(root, entry["page_pdf"]),
            page_image=_bytes(root, entry["page_image"]), native_lines=native,
            converter_assets={name: _bytes(root, path) for name, path in entry["converter_assets"].items()},
            code_assets=code, tex_source=_bytes(root, entry["tex"]),
            notation_evidence=_bytes(root, entry["notation"]))
        if (result["eligible_for_jev"] or result["field_candidate"] or result["graph_admission_enabled"]
                or result["scientific_notation_qualified"] or result["visual_coverage_qualified"]
                or result["coverage_scope"] != "native_text_only"):
            raise ValueError("review_scope_escape")
        reviewed[sid] = result
        bindings[sid] = {"manifest_file_sha256": _hash(manifest_bytes),
                         "review_receipt_file_sha256": [_hash(_bytes(root, path)) for path in entry["reviews"]],
                         "reviewed_assessment_sha256": result["reviewed_assessment_sha256"],
                         "automatic_assessment_sha256": automatic["parallel_structure_v4"][sid]["assessment_sha256"]}
    details = {method: list(rows) for method, rows in baseline["details"].items()}
    selected_rows = {row["id"]: row for row in details["parallel_structure_v4"]}
    for sid, result in reviewed.items():
        reference = {**labels[sid], "math_review_required": True}
        selected_rows[sid] = score_case(sid, result, reference)
    details["parallel_structure_v4"] = [selected_rows[row["id"]] for row in baseline["details"]["parallel_structure_v4"]]
    metrics = {method: summary(rows) for method, rows in details.items()}
    previous = {row["id"] for row in baseline["details"]["parallel_structure_v4"]
                if row["proposed"] and row["gold"] == "complete" and row["text_match_98"]}
    current = {row["id"] for row in details["parallel_structure_v4"]
               if row["proposed"] and row["gold"] == "complete" and row["text_match_98"]}
    lost = old_good - previous
    preserved = (len(current) >= 91 and old_good <= current and previous <= current
                 and all(metric["false_proposals"] == 0 for metric in metrics.values()))
    receipt = {"schema_version": 1, "status": "SELECTED_REVIEWED_REPLAY_NOT_SCIENTIFIC_QUALIFICATION",
               "baseline_results_file_sha256": baseline_hash,
               "baseline_experiment_sha256": baseline["experiment_sha256"],
               "baseline_preflight_file_sha256": _hash(preflight_bytes),
               "source_map_file_sha256": _hash(source_map_bytes),
               "selected_runner_sha256": runner_hash,
               "review_map_file_sha256": _hash(map_bytes), "reviewed_bindings": bindings,
               "review_input_file_sha256": reviewed_file_hashes,
               "metrics": metrics, "details": details,
               "fallback_increment": {method: fallback_increment(details["parallel_structure_v4"], details[method])
                                      for method in ("parallel_mineru_v4", "parallel_olmocr_v4")},
               "preserve_legacy_text_gate": {"status": "PASS" if preserved else "FAIL",
                                             "baseline_correct": len(previous), "selected_correct": len(current),
                                             "remaining_lost_ids": sorted(lost - current)},
               "automatic_assessments_preserved": True,
               "coverage_scope": "native_text_only", "visual_coverage_qualified": False,
               "scientific_notation_qualified": False, "graph_admission_enabled": False,
               "independent_human_validation": "not_claimed", "new_paid_api_calls": 0,
               "production_graph_writes": 0}
    target = _output_target(root, output, config["baseline"])
    # Recheck sources after review work and before the derived receipt is published.
    verify_files(root, gate["input_file_hashes"])
    verify_files(repo, gate["repository_input_hashes"])
    verify_files(root, reviewed_file_hashes)
    _same(_hash(Path(__file__).read_bytes()), runner_hash, "selected_runner_changed_during_run")
    _same(_hash(_bytes(root, f'{config["baseline"]}/results.json')), baseline_hash,
          "baseline_results_changed_during_run")
    _same(_hash(_bytes(root, preflight_relative)), _hash(preflight_bytes), "baseline_preflight_changed_during_run")
    _same(_hash(_bytes(root, config["source_map"])), _hash(source_map_bytes), "source_map_changed_during_run")
    _same(_hash(_bytes(root, review_map)), _hash(map_bytes), "review_map_changed_during_run")
    _reverify_receipts(trust, signed_receipts)
    target.mkdir(parents=True)
    write_once(target / "selected-results.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--review-map", required=True, help="Root-relative trusted private map")
    parser.add_argument("--output", required=True, help="New root-relative private output directory")
    args = parser.parse_args()
    result = selected_replay(root=args.data_root, repo=REPO, review_map=args.review_map,
                             output=args.output)
    print(json.dumps({"status": result["status"], "metrics": result["metrics"],
                      "preserve_legacy_text_gate": result["preserve_legacy_text_gate"]}, sort_keys=True))
    return 0 if result["preserve_legacy_text_gate"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
