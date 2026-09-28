"""Negative-only, candidate-bound observations from attributed source review."""
from __future__ import annotations

from copy import deepcopy
import datetime as dt

from trace_gc.pdf_source_parallel_v4 import digest_value
from .fidelity import text_hash

VERSION = "candidate-fidelity-failure-v1"
FIELDS = {"version", "assessment_sha256", "text_sha256", "source_sha256", "page_sha256",
          "native_sha256", "image_sha256", "physical_page", "reviewer", "reviewer_kind",
          "reviewed_at", "independent_review", "exposure", "source_before_predictions",
          "dimension", "status", "evidence_id", "note"}


def validate_failures(observations: list, prediction: dict, source_identity: dict,
                      *, evaluated_at: str) -> list[dict]:
    """A failed reference review cannot itself establish a candidate defect.

    These observations instead bind an explicitly inspected native candidate.
    They can only record failure, never certify a reference or an amended result.
    The caller verifies the original source, image and native bytes first.
    """
    if not isinstance(observations, list) or not observations:
        raise ValueError("nonempty_candidate_failure_observations_required")
    seen = set()
    for item in observations:
        if not isinstance(item, dict) or set(item) != FIELDS:
            raise ValueError("invalid_candidate_failure_observation_fields")
        if (item["version"] != VERSION or item["status"] != "fail"
                or item["dimension"] not in {"notation", "boundary", "reading_order"}
                or item["dimension"] in seen):
            raise ValueError("candidate_observations_only_record_unique_dimension_failures")
        seen.add(item["dimension"])
        if (item["assessment_sha256"] != prediction["assessment_sha256"]
                or item["text_sha256"] != text_hash(prediction["text"])
                or type(item["physical_page"]) is not int or item["physical_page"] != 1
                or any(item[key] != prediction[key] or item[key] != source_identity[key]
                       for key in ("source_sha256", "page_sha256"))
                or item["native_sha256"] != prediction.get("native_sha256")
                or item["native_sha256"] != source_identity["native_identity"]["native_sha256"]
                or item["image_sha256"] != source_identity["image_sha256"]):
            raise ValueError("candidate_failure_observation_identity_mismatch")
        if (item["reviewer_kind"] not in {"assistant", "human"}
                or any(not isinstance(item[key], str) or not item[key].strip()
                       for key in ("reviewer", "evidence_id", "note"))
                or item["independent_review"] is not False
                or item["source_before_predictions"] is not False
                or item["exposure"] != "previously_examined_development"):
            raise ValueError("candidate_failure_requires_honest_attributed_development_review")
        try:
            reviewed = dt.datetime.fromisoformat(item["reviewed_at"].replace("Z", "+00:00"))
            evaluated = dt.datetime.fromisoformat(evaluated_at.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            raise ValueError("candidate_failure_review_time_invalid") from None
        if reviewed.tzinfo is None or evaluated.tzinfo is None or reviewed > evaluated:
            raise ValueError("candidate_failure_review_postdates_evaluation")
    return deepcopy(observations)


def apply_failures(fidelity: dict, prediction: dict, observations: list[dict]) -> dict:
    """Preserve failures for the candidate and its closure-only derivations.

    A reviewed closure cannot repair transcription, order or contaminated spans.
    A separately reviewed image transcription has a different representation
    and no manual-closure link, so it requires its own fidelity evidence.
    """
    result = deepcopy(fidelity)
    for item in observations:
        same_candidate = item["assessment_sha256"] == prediction.get("assessment_sha256")
        closure_only = (item["assessment_sha256"] == prediction.get("original_assessment_sha256")
                        and bool(prediction.get("manual_closure_review_sha256"))
                        and item["native_sha256"] == prediction.get("native_sha256"))
        if not (same_candidate or closure_only):
            continue
        result[item["dimension"]] = {
            "status": "fail", "reason": "attributed_source_observed_candidate_failure",
            "observation_sha256": digest_value(item),
            "assessment_sha256": item["assessment_sha256"],
        }
        result["verified_correct_proposal"] = False
    return result
