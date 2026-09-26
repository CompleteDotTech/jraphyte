"""Freeze source-reviewed cohorts before prediction; cannot certify human review."""
from __future__ import annotations

import argparse
import datetime as dt
import re
from collections import Counter
from pathlib import Path
from .common import child, data_root, digest, method_hashes, read, verify_files, write_once, verify_first_page_bundle
from trace_gc.pdf_source_parallel_v4 import digest_value, validate_source_spans, compare

VALID_LABELS = {"complete", "partial_on_page_one", "no_abstract_text", "uncertain"}


def _timestamp(value: str) -> dt.datetime:
    date = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("review_time_requires_timezone")
    return date


def freeze_cohort(root: Path, manifest: dict, labels: dict, exposure_registry: list[dict], destination: Path,
                  *, cohort_kind="unseen_source_reviewed", now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    if cohort_kind not in {"unseen_source_reviewed", "synthetic_causal_fixture"}:
        raise ValueError("invalid_cohort_kind")
    rows = manifest["pdfs"]
    ids = [r["sample_id"] for r in rows]
    if not ids or len(ids) != len(set(ids)) or set(ids) != set(labels):
        raise ValueError("cohort_requires_nonempty_unique_exact_labels")
    if cohort_kind == "unseen_source_reviewed" and not exposure_registry:
        raise ValueError("unseen_cohort_requires_prior_exposure_registry")
    seen_hashes = {r[k] for r in exposure_registry for k in ("source_sha256", "page_sha256", "page_pdf_sha256") if r.get(k)}
    seen_works = {r["work_id"] for r in exposure_registry if r.get("work_id")}
    source_hashes, page_hashes, works, bound_rows = set(), set(), set(), []
    for row in rows:
        sid = row["sample_id"]
        if not isinstance(sid,str) or not re.fullmatch(r"[A-Za-z0-9_-]+",sid):
            raise ValueError("unsafe_sample_id")
        if row.get("physical_page") != 1 or not row.get("work_id"):
            raise ValueError("first_page_and_work_identity_required")
        verified = {}
        for key in ("source", "page", "image", "native"):
            path = child(root, row[key+"_relative"])
            actual = digest(path)
            if actual != row[key+"_sha256"]:
                raise ValueError("source_review_hash_mismatch:"+sid+":"+key)
            verified[key+"_sha256"] = actual
        native=verify_first_page_bundle(root,row)
        if row["source_sha256"] in source_hashes or row["page_sha256"] in page_hashes or row["work_id"] in works:
            raise ValueError("duplicate_source_or_work_in_cohort")
        if cohort_kind == "unseen_source_reviewed" and (row["source_sha256"] in seen_hashes or row["page_sha256"] in seen_hashes or row["work_id"] in seen_works):
            raise ValueError("previously_exposed_source_is_not_unseen")
        source_hashes.add(row["source_sha256"])
        page_hashes.add(row["page_sha256"])
        works.add(row["work_id"])
        label = labels[sid]
        if label.get("status") not in VALID_LABELS or not isinstance(label.get("text"), str):
            raise ValueError("invalid_reference_label")
        if label["status"] in {"complete", "partial_on_page_one"} and not label["text"].strip():
            raise ValueError("complete_reference_cannot_be_empty")
        review = label.get("source_review", {})
        if review.get("reviewer_kind") not in {"assistant", "human"} or not review.get("reviewer"):
            raise ValueError("source_reviewer_attribution_required")
        if review.get("source_before_predictions") is not True or row.get("predictions_examined") is not False:
            raise ValueError("source_first_review_attestation_required")
        if _timestamp(review["reviewed_at"]) > now:
            raise ValueError("source_review_must_precede_freeze")
        if review.get("image_sha256") != verified["image_sha256"] or review.get("native_sha256") != verified["native_sha256"]:
            raise ValueError("review_not_bound_to_image_and_native_spans")
        if label["status"] == "no_abstract_text" and label["text"].strip():
            raise ValueError("absent_reference_must_not_contain_abstract_text")
        if label["text"].strip():
            spans=review.get("reference_spans", [])
            if native:
                validate_source_spans(spans,native)
                if not spans or not compare(label["text"], "\n".join(s["text"] for s in spans))["text_match_98"]:
                    raise ValueError("reference_text_not_supported_by_reviewed_native_spans")
            elif review.get("text_provenance") != "source_image_transcription":
                raise ValueError("image_only_reference_requires_attributed_visual_transcription")
            if label["status"]=="complete" and not review.get("closing_boundary"):
                raise ValueError("complete_reference_requires_reviewed_closing_boundary")
        if cohort_kind == "unseen_source_reviewed":
            for relative in row.get("conversion_outputs", {}).values():
                if child(root,relative).exists():
                    raise ValueError("unseen_conversion_outputs_must_be_created_after_freeze")
        bound_rows.append({**row, **verified})
    result = {"schema_version": 3, "cohort_kind": cohort_kind, "frozen_at": now.isoformat(),
              "manifest": {"pdfs": bound_rows}, "labels": labels, "method_hashes": method_hashes(),
              "exposure_registry_sha256": digest_value(exposure_registry),
              "counts": dict(Counter(label["status"] for label in labels.values())),
              "review_attribution": dict(Counter(label["source_review"]["reviewer_kind"] for label in labels.values())),
              "independence": "review attestations recorded; human independence not inferred or certified"}
    result["freeze_sha256"] = digest_value(result)
    write_once(destination, result)
    return result


def verify_freeze(root: Path, value: dict) -> None:
    payload = dict(value)
    expected = payload.pop("freeze_sha256")
    if digest_value(payload) != expected or value["method_hashes"] != method_hashes():
        raise ValueError("frozen_cohort_or_methods_changed")
    for row in value["manifest"]["pdfs"]:
        verify_files(root, {row[k+"_relative"]: row[k+"_sha256"] for k in ("source", "page", "image", "native")})


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--labels", required=True)
    p.add_argument("--exposure-registry", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    root = data_root(a.data_root)
    from .common import REPO
    known=read(REPO/"review/first_page_expanded200/source_hashes.json")
    if len(known)!=200:
        raise ValueError("complete_public_regression_exposure_registry_required")
    supplied=read(child(root,a.exposure_registry))
    if isinstance(supplied,dict):supplied=[{"id":key,**value} for key,value in supplied.items()]
    exposure=supplied+[{"id":key,**value} for key,value in known.items()]
    freeze_cohort(root, read(child(root, a.manifest)), read(child(root, a.labels)), exposure, child(root, a.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
