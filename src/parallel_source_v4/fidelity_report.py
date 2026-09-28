"""Rescore saved assessments into a new immutable external metric receipt.

No extraction, provider calls, label edits or historical receipt rewrites.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

from trace_gc.pdf_structure_parallel_v4 import verify_assessment
from .common import child, data_root, digest, method_hashes, write_once
from .fidelity import FIDELITY_METRIC_VERSION, LEGACY_METRIC_VERSION
from .metrics import score_case, summary


def read_bound(path: Path) -> tuple[object, str]:
    """Parse and identify exactly the same bytes; reject ambiguous JSON inputs."""
    raw = path.read_bytes()
    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate_key_in_rescore_input")
            value[key] = item
        return value
    def reject_constant(value):
        raise ValueError("nonfinite_rescore_input")
    return (json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                       parse_constant=reject_constant), hashlib.sha256(raw).hexdigest())


def rescore(root: Path, run_relative: str, labels_relative: str,
            baseline_relative: str, output_relative: str, *, evaluated_at: str | None = None) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    evaluated_at = evaluated_at or now.isoformat()
    evaluation_time = dt.datetime.fromisoformat(evaluated_at.replace("Z", "+00:00"))
    if evaluation_time.tzinfo is None or evaluation_time > now:
        raise ValueError("evaluation_time_requires_timezone_and_cannot_be_future")
    run = child(root, run_relative)
    output = child(root, output_relative)
    baseline_folder = child(root, baseline_relative)
    if (output == root or output == run or run in output.parents or output in run.parents or
            output == baseline_folder or baseline_folder in output.parents or output in baseline_folder.parents or
            output.relative_to(root).parts[0] in {"validation_expanded200", "validation_v2", "validation_200_10k", "sample_comparison_100"}):
        raise ValueError("rescore_requires_new_external_output_outside_historical_inputs")
    labels_path = child(root, labels_relative)
    labels, labels_hash = read_bound(labels_path)
    existing_path = child(root, run_relative + "/results.json")
    existing, existing_hash = read_bound(existing_path)
    if not isinstance(labels, dict) or not labels:
        raise ValueError("nonempty_reference_labels_required")
    identities = {labels_relative: labels_hash, run_relative + "/results.json": existing_hash}
    by_method = {}
    for method, saved_details in existing["details"].items():
        if not isinstance(method, str) or not method.replace("_", "").isalnum():
            raise ValueError("invalid_saved_method_name")
        ids = [row["id"] for row in saved_details]
        if len(ids) != len(set(ids)) or set(ids) != set(labels):
            raise ValueError("saved_run_requires_all_unique_reference_cases")
        rows = []
        for sid in ids:
            if not isinstance(sid, str) or not sid.replace("_", "").replace("-", "").isalnum():
                raise ValueError("invalid_saved_case_id")
            relative = run_relative + "/assessments/" + method + "/" + sid + ".json"
            path = child(root, relative)
            prediction, prediction_hash = read_bound(path)
            verify_assessment(prediction)
            reference = dict(labels[sid])
            prior = next(row for row in saved_details if row["id"] == sid)
            reference["math_review_required"] = bool(reference.get("math_review_required") or prior.get("math_review_required"))
            scored = score_case(sid, prediction, reference, evaluated_at=evaluated_at)
            for key in ("gold", "predicted", "proposed", "precision", "recall",
                        "boundary_match", "text_match_98", "boundary_and_98_match"):
                if scored[key] != prior[key]:
                    raise ValueError("legacy_metric_replay_changed:" + method + ":" + sid + ":" + key)
            rows.append(scored)
            identities[relative] = prediction_hash
        by_method[method] = rows
    baseline = []
    for sid in labels:
        relative = baseline_relative + "/" + sid + ".json"
        path = child(root, relative)
        prediction, prediction_hash = read_bound(path)
        prediction = {**prediction, "proposal": bool(prediction.get("eligible_for_jev", False)),
                      "verified_admission": False}
        baseline.append(score_case(sid, prediction, labels[sid], evaluated_at=evaluated_at))
        identities[relative] = prediction_hash
    baseline_summary = summary(baseline)
    for key, expected in existing.get("v2_baseline", {}).items():
        if key in baseline_summary and key not in {"legacy_metric_version", "fidelity"} and baseline_summary[key] != expected:
            raise ValueError("legacy_baseline_summary_changed:" + key)
    # Verify no upstream artifact changed while read, before publishing a receipt.
    for relative, expected in identities.items():
        if digest(child(root, relative)) != expected:
            raise ValueError("rescore_input_changed")
    result = {"schema_version": 1, "status": "COMPLETE_SAVED_ASSESSMENT_RESCORE_NOT_QUALIFICATION",
              "legacy_metric_version": LEGACY_METRIC_VERSION, "fidelity_metric_version": FIDELITY_METRIC_VERSION,
              "method_hashes": method_hashes(), "input_hashes": identities,
              "metrics": {key: summary(rows) for key, rows in by_method.items()},
              "details": by_method, "v2_baseline": baseline_summary, "v2_details": baseline,
              "legacy_metrics_replayed": True, "v4_assessment_seals_verified": True,
              "evaluated_at": evaluated_at, "new_paid_api_calls": 0, "production_graph_writes": 0,
              "independent_human_validation": "outstanding"}
    write_once(child(root, output_relative + "/results.json"), result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--run", required=True, help="Existing run directory relative to data root")
    parser.add_argument("--labels", default="validation_expanded200/labels.json")
    parser.add_argument("--baseline", default="validation_expanded200/assessments/structure_v2")
    parser.add_argument("--output", required=True, help="New directory relative to data root")
    parser.add_argument("--evaluated-at", help="Timezone-aware evaluation time; reuse the recorded time for replay")
    args = parser.parse_args()
    result = rescore(data_root(args.data_root), args.run, args.labels, args.baseline, args.output,
                     evaluated_at=args.evaluated_at)
    print(result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
